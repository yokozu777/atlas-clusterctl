"""Ansible-playbook execution."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from clusterctl.cluster_vars_loader import materialize_playbook_extra_vars
from clusterctl.controller_extra_vars import materialize_controller_extra_vars
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.logging_util import RunLogSession, run_subprocess_logged
from clusterctl.playbooks_resolve import effective_playbooks_config
from clusterctl.playbooks_requirements import (
    PLAYBOOK_REQUIREMENTS_ENV,
    discover_playbook_requirements_files,
    playbook_requirements_env_value,
)
from clusterctl.playbooks_sync import ensure_playbooks_synced, uses_playbooks_sync
from clusterctl.execution import is_inside_docker_container
from clusterctl.git_ssh import git_ssh_command_has_identity, resolve_git_ssh_command
from clusterctl.workspace_paths import (
    assert_no_legacy_repo_root_ansible,
    ensure_container_controller_tmp_dir,
    ensure_workspace_ansible_dirs,
    resolve_controller_temp_location,
    validate_workspace_ansible_env,
)


class AnsibleRunner:
    def __init__(self, ctx: ClusterContext, *, log_session: RunLogSession | None = None) -> None:
        self.ctx = ctx
        self._log_session = log_session
        self._bootstrapped = False
        self._git_ssh = False
        self._playbook_extra_vars_path: Path | None = None
        self._controller_extra_vars_path: Path | None = None

    def bootstrap(self, *, dry_run: bool = False) -> None:
        if self._bootstrapped:
            return
        self._ensure_playbook_extra_vars()
        assert_no_legacy_repo_root_ansible(self.ctx.repo_root)
        if not dry_run:
            ensure_workspace_ansible_dirs(self.ctx.workspace_root)
            if resolve_controller_temp_location(
                inside_docker_container=is_inside_docker_container(),
            ) == "container":
                ensure_container_controller_tmp_dir(self.ctx.workspace_id)
        self._sync_repos(dry_run=dry_run)
        if dry_run:
            req_files = self._discover_playbook_requirements_files()
            print(
                "[dry-run] bootstrap: ansible-galaxy + mitogen env "
                f"({len(req_files)} requirements.yml)"
            )
            self._bootstrapped = True
            return
        script = self.ctx.repo_root / "clusterctl" / "bootstrap" / "bootstrap.sh"
        env = self._bootstrap_env()
        streams = self._log_session.log_streams() if self._log_session else None
        result = run_subprocess_logged(
            ["bash", str(script)],
            cwd=self.ctx.repo_root,
            env=env,
            log_streams=streams,
        )
        if result != 0:
            raise ClusterctlError("bootstrap failed — check playbooks sync and ansible-galaxy")
        self._apply_mitogen_env(env)
        self._sync_env(env)
        self._bootstrapped = True

    def _effective_playbooks(self):
        return effective_playbooks_config(self.ctx)

    def _discover_playbook_requirements_files(self) -> list[Path]:
        playbooks = self._effective_playbooks()
        phases = self.ctx.config_v2.phases if self.ctx.config_v2 else None
        return discover_playbook_requirements_files(
            playbooks,
            phases,
            workspace_root=self.ctx.workspace_root,
            repo_root_path=self.ctx.repo_root,
        )

    def _bootstrap_env(self) -> dict[str, str]:
        env = self._controller_env()
        req_files = self._discover_playbook_requirements_files()
        env[PLAYBOOK_REQUIREMENTS_ENV] = playbook_requirements_env_value(req_files)
        return env

    def _sync_repos(self, *, dry_run: bool = False) -> None:
        v2 = self.ctx.config_v2
        if not uses_playbooks_sync(
            self.ctx.playbooks_enabled,
            v2.playbooks if v2 else None,
        ):
            return
        if v2 is None or v2.playbooks is None:
            return

        playbooks = self._effective_playbooks()
        env = self._controller_env() if not dry_run else os.environ.copy()
        streams = self._log_session.log_streams() if self._log_session and not dry_run else None
        results = ensure_playbooks_synced(
            playbooks_enabled=self.ctx.playbooks_enabled,
            playbooks=playbooks,
            phases=v2.phases,
            workspace_root=self.ctx.workspace_root,
            repo_root_path=self.ctx.repo_root,
            env=env,
            dry_run=dry_run,
            log_streams=streams,
        )
        for result in results:
            if result.action in {"skipped", "local", "never"}:
                continue
            line = f"playbooks sync: {result.name}: {result.action} → {result.path}"
            if dry_run:
                line = f"[dry-run] {line}"
            if self._log_session:
                self._log_session.write_line(line)
            else:
                print(line)

    def teardown(self) -> None:
        for key in (
            "ANSIBLE_CONFIG",
            "ANSIBLE_ROLES_PATH",
            "ANSIBLE_STRATEGY",
            "ANSIBLE_FORKS",
            "GIT_SSH_COMMAND",
            "CLUSTER_WORKSPACE_ID",
            "CLUSTER_WORKSPACE_ROOT",
            "ANSIBLE_CACHE_PLUGIN_CONNECTION",
            "ANSIBLE_LOCAL_TEMP",
            "TMPDIR",
            "ANSIBLE_STRATEGY_PLUGINS",
            PLAYBOOK_REQUIREMENTS_ENV,
        ):
            os.environ.pop(key, None)
        self._git_ssh = False
        self._bootstrapped = False

    def run_phase_execution_plan(
        self,
        plan,
        *,
        playbooks=None,
        dry_run: bool = False,
    ) -> None:
        from clusterctl.phase_runner import run_phase_stages

        if playbooks is None:
            playbooks = self._effective_playbooks()
        run_phase_stages(self, plan.stages, playbooks=playbooks, dry_run=dry_run)

    def _ensure_playbook_extra_vars(self) -> Path:
        if self._playbook_extra_vars_path is None:
            self._playbook_extra_vars_path = materialize_playbook_extra_vars(
                self.ctx.config_dir,
                self.ctx.workspace_root,
                group_var_files=self.ctx.group_var_files,
            )
        return self._playbook_extra_vars_path

    def _ensure_controller_extra_vars(self) -> Path:
        if self._controller_extra_vars_path is None:
            self._controller_extra_vars_path = materialize_controller_extra_vars(self.ctx)
        return self._controller_extra_vars_path

    def _controller_env(self) -> dict[str, str]:
        env = self.ctx.ansible_env()
        env.setdefault("SSH_KEY", str(self.ctx.ssh_key))
        env.setdefault("ANSIBLE_PRIVATE_KEY_FILE", str(self.ctx.ssh_key))
        validate_workspace_ansible_env(
            env,
            self.ctx.workspace_root,
            workspace_id=self.ctx.workspace_id,
            controller_temp=resolve_controller_temp_location(
                inside_docker_container=is_inside_docker_container(),
            ),
        )
        return env

    def _enable_git_ssh(self, *, dry_run: bool = False) -> None:
        if self._git_ssh:
            return
        # Prefer tfstate-specific key when set; else host/controller SSH_KEY.
        ssh_key = (
            os.environ.get("TFSTATE_SSH_KEY", "").strip()
            or os.environ.get("SSH_KEY", "").strip()
            or os.environ.get("ANSIBLE_PRIVATE_KEY_FILE", "").strip()
            or str(self.ctx.ssh_key)
        )
        cmd = resolve_git_ssh_command(
            existing=os.environ.get("GIT_SSH_COMMAND"),
            ssh_key=ssh_key,
        )
        if dry_run:
            print(f"[dry-run] export GIT_SSH_COMMAND={cmd!r}")
        else:
            os.environ["GIT_SSH_COMMAND"] = cmd
        self._git_ssh = True

    @staticmethod
    def _sync_env(env: dict[str, str]) -> None:
        for key in (
            "ATLAS_CLUSTER_ROOT",
            "CLUSTER_WORKSPACE_ID",
            "CLUSTER_WORKSPACE_ROOT",
            "SSH_KEY",
            "ANSIBLE_PRIVATE_KEY_FILE",
            "ANSIBLE_CACHE_PLUGIN_CONNECTION",
            "ANSIBLE_LOCAL_TEMP",
            "TMPDIR",
            "ANSIBLE_CONFIG",
            "ANSIBLE_ROLES_PATH",
            "ANSIBLE_STRATEGY",
            "ANSIBLE_FORKS",
            "ANSIBLE_STRATEGY_PLUGINS",
            "GIT_SSH_COMMAND",
        ):
            if key in env:
                os.environ[key] = env[key]

    @staticmethod
    def _apply_mitogen_env(env: dict[str, str]) -> None:
        mitogen_script = Path(env["ATLAS_CLUSTER_ROOT"]) / "clusterctl" / "bootstrap" / "mitogen.sh"
        result = subprocess.run(
            [
                "bash",
                "-c",
                (
                    f"source '{mitogen_script}' && ansible_mitogen_configure_strategy_plugins "
                    '&& printf %s "${ANSIBLE_STRATEGY_PLUGINS:-}"'
                ),
            ],
            cwd=env["ATLAS_CLUSTER_ROOT"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        plugins = result.stdout.strip()
        if plugins:
            env["ANSIBLE_STRATEGY_PLUGINS"] = plugins

    @staticmethod
    def _clear_mitogen_env(env: dict[str, str]) -> None:
        env.pop("ANSIBLE_STRATEGY_PLUGINS", None)
