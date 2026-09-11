"""Cluster execution context."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from clusterctl.cluster_config import ClusterConfig, load_cluster_config
from clusterctl.playbooks_config import SCHEMA_VERSION, ClusterConfigV2
from clusterctl.cluster_vars_loader import optional_cluster_var_file
from clusterctl.execution import ExecutionConfig, is_inside_docker_container, resolve_execution
from clusterctl.cluster_layout import is_deployable_config_dir
from clusterctl.exceptions import ClusterNotFoundError
from clusterctl.playbooks_repos import (
    ResolvedPlaybooksRepos,
    empty_resolved_playbooks_repos,
    playbook_repos_summary_lines,
)
from clusterctl.paths import (
    cluster_dir,
    inventory_path,
    kubeconfig_path,
    repo_root,
    resolve_cluster_id,
    workspace_log_dir,
    workspace_root,
)
from clusterctl.workspace_id import resolve_workspace_id
from clusterctl.workspace_paths import (
    configure_workspace_ansible_env,
    effective_controller_temp_location,
    resolve_controller_temp_location,
    workspace_ansible_summary_lines,
)


@dataclass(frozen=True)
class ClusterContext:
    repo_root: Path
    cluster_id: str
    config_dir: Path
    inventory: Path
    cluster_var_file: Path | None
    group_var_files: tuple[Path, ...]
    host_var_files: tuple[tuple[str, Path], ...]
    workspace_id: str
    workspace_root: Path
    workspace_logs: Path
    kubeconfig: Path
    display_name: str | None = None
    execution_configured: ExecutionConfig = field(default_factory=ExecutionConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    execution_source: str = "default"
    playbooks_enabled: bool = False
    playbook_repos: ResolvedPlaybooksRepos = field(
        default_factory=empty_resolved_playbooks_repos
    )
    schema_version: int = 1
    config_v2: ClusterConfigV2 | None = None
    deployable: bool = True
    cascade_paths: tuple[Path, ...] = ()
    ssh_key: Path = field(default_factory=lambda: Path(os.environ.get("SSH_KEY", os.path.expanduser("~/.ssh/id_rsa"))))
    # Leaf cluster.yaml ``profile:`` (schema v1 only; ignored by v2 runner).
    legacy_profile: str | None = None

    @property
    def role_repos(self) -> ResolvedPlaybooksRepos:
        """Deprecated alias for :attr:`playbook_repos` (soft-compat Phase 5)."""
        return self.playbook_repos

    @property
    def default_profile(self) -> str | None:
        """Deprecated alias for :attr:`legacy_profile` (packaging Phase 6)."""
        import warnings

        warnings.warn(
            "ClusterContext.default_profile is deprecated; use legacy_profile",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.legacy_profile

    @classmethod
    def load(
        cls,
        cluster_id: str | None = None,
        *,
        executor: str | None = None,
    ) -> ClusterContext:
        root = repo_root()
        os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))

        resolved_cluster_id = resolve_cluster_id(cluster_id, root)

        try:
            config = cluster_dir(root, resolved_cluster_id)
        except FileNotFoundError as exc:
            raise ClusterNotFoundError(str(exc)) from exc

        if not is_deployable_config_dir(config):
            raise ClusterNotFoundError(
                f"cluster {resolved_cluster_id!r} is not deployable "
                f"(policy/org baseline — use ./cluster config effective)"
            )

        cfg = load_cluster_config(config, resolved_cluster_id, repo_root=root)
        inv = cfg.inventory if cfg.inventory.is_file() else inventory_path(config)
        if not inv.is_file():
            raise ClusterNotFoundError(f"inventory not found: {inv}")

        group_var_files = cfg.group_var_files
        host_var_files = cfg.host_var_files
        cluster_var_file = optional_cluster_var_file(config)

        workspace_id = resolve_workspace_id(
            root,
            group_var_files=list(group_var_files),
            cluster_var_file=cluster_var_file,
            override=cfg.workspace_id_override,
        )
        ws_root = workspace_root(root, resolved_cluster_id)
        resolution = resolve_execution(cfg.execution, explicit=executor)

        return cls(
            repo_root=root,
            cluster_id=resolved_cluster_id,
            config_dir=config,
            inventory=inv,
            cluster_var_file=cluster_var_file,
            group_var_files=group_var_files,
            host_var_files=host_var_files,
            workspace_id=workspace_id,
            workspace_root=ws_root,
            workspace_logs=workspace_log_dir(root, resolved_cluster_id),
            kubeconfig=kubeconfig_path(root, resolved_cluster_id),
            display_name=cfg.display_name,
            execution_configured=resolution.configured,
            execution=resolution.effective,
            execution_source=resolution.source,
            playbooks_enabled=cfg.playbooks_enabled,
            playbook_repos=cfg.playbook_repos,
            schema_version=cfg.schema_version,
            config_v2=cfg.config_v2,
            deployable=cfg.deployable,
            cascade_paths=cfg.cascade_paths,
            legacy_profile=cfg.legacy_profile,
        )

    def ansible_env(self, *, ensure_dirs: bool = True) -> dict[str, str]:
        env = os.environ.copy()
        env["ATLAS_CLUSTER_ROOT"] = str(self.repo_root)
        env["CLUSTER_ID"] = self.cluster_id
        env["CLUSTER_WORKSPACE_ID"] = self.workspace_id
        env["CLUSTER_WORKSPACE_ROOT"] = str(self.workspace_root.resolve())
        env["SSH_KEY"] = str(self.ssh_key)
        env["ANSIBLE_PRIVATE_KEY_FILE"] = str(
            os.environ.get("ANSIBLE_PRIVATE_KEY_FILE", self.ssh_key)
        )
        configure_workspace_ansible_env(
            env,
            self.workspace_root,
            workspace_id=self.workspace_id,
            controller_temp=resolve_controller_temp_location(
                inside_docker_container=is_inside_docker_container(),
            ),
            ensure_dirs=ensure_dirs,
        )
        return env

    def controller_temp_location(self) -> str:
        """Effective ANSIBLE_LOCAL_TEMP policy (workspace bind-mount vs container FS)."""
        return effective_controller_temp_location(
            inside_docker_container=is_inside_docker_container(),
            configured_docker=self.execution_configured.is_docker,
        )

    def summary_lines(self) -> list[str]:
        lines = [
            f"Cluster:    {self.cluster_id}"
            + (f" ({self.display_name})" if self.display_name else ""),
            f"Schema:     v{self.schema_version}"
            + (" (cascade)" if self.config_v2 is not None else ""),
            f"Deployable: {'yes' if self.deployable else 'no (policy/template)'}",
        ]
        if self.cascade_paths:
            lines.append(f"Cascade:    {len(self.cascade_paths)} fragment(s)")
            for path in self.cascade_paths:
                try:
                    rel = path.relative_to(self.repo_root)
                except ValueError:
                    rel = path
                lines.append(f"              - {rel}")
        if self.legacy_profile and self.schema_version < SCHEMA_VERSION:
            lines.append(f"Profile:    {self.legacy_profile} (cluster.yaml legacy)")
        lines.append(f"Execution:  {self.execution.summary()} ({self.execution_source})")
        lines.extend(
            [
                f"Config:     {self.config_dir}",
                f"Inventory:  {self.inventory}",
                f"Group vars: {len(self.group_var_files)} file(s) (org→env→leaf cascade)",
            ]
        )
        for path in self.group_var_files:
            try:
                rel = path.relative_to(self.repo_root)
            except ValueError:
                try:
                    rel = path.relative_to(self.config_dir)
                except ValueError:
                    rel = path
            lines.append(f"              - {rel}")
        if self.host_var_files:
            lines.append(f"Host vars:  {len(self.host_var_files)} file(s) under host_vars/")
            for hostname, path in self.host_var_files:
                try:
                    rel = path.relative_to(self.config_dir)
                except ValueError:
                    rel = path
                lines.append(f"              - {rel} ({hostname})")
        lines.extend(
            [
                f"Workspace:  {self.workspace_root}",
                f"Workspace id: {self.workspace_id}",
                *workspace_ansible_summary_lines(
                    self.workspace_root,
                    workspace_id=self.workspace_id,
                    controller_temp=self.controller_temp_location(),
                ),
            ]
        )
        if self.config_v2 and self.config_v2.playbooks is not None:
            if self.playbooks_enabled and self.playbook_repos.is_configured():
                lines.extend(
                    playbook_repos_summary_lines(
                        self.playbook_repos,
                        workspace_root=self.workspace_root,
                        repo_root_path=self.repo_root,
                    )
                )
            else:
                playbooks = self.config_v2.playbooks
                phase_count = (
                    len(self.config_v2.phases.phases) if self.config_v2.phases else 0
                )
                lines.append(
                    f"Playbooks:  {len(playbooks.repos)} repo(s), "
                    f"{phase_count} phase(s) (cascade)"
                )
        lines.extend(
            [
                f"Kubeconfig: {self.kubeconfig} ({'exists' if self.kubeconfig.is_file() else 'missing'})",
                f"Logs:       {self.workspace_logs} (latest run → logs/latest/)",
            ]
        )
        return lines
