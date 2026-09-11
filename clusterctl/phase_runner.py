"""Schema v2 phase runner — execute playbooks from sibling repos by phase ref."""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from clusterctl.ansible_config import configure_entry_env
from clusterctl.controller_extra_vars import materialize_controller_extra_vars
from clusterctl.exceptions import ClusterctlError
from clusterctl.logging_util import run_subprocess_logged
from clusterctl.phase_plan import PhaseStagePlan
from clusterctl.playbooks_config import InvocationSpec, PlaybookEntrySpec, PlaybookRepoSpec, PlaybooksConfig
from clusterctl.playbooks_paths import resolve_repo_base

if TYPE_CHECKING:
    from clusterctl.ansible_runner import AnsibleRunner


def resolve_phase_repo_base(
    repo_spec: PlaybookRepoSpec,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> Path:
    return resolve_repo_base(
        repo_spec,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    ).resolve()


def resolve_phase_playbook_path(repo_base: Path, entry: PlaybookEntrySpec) -> Path:
    playbook = Path(entry.file)
    if playbook.is_absolute():
        return playbook.resolve()
    return (repo_base / playbook).resolve()


def build_phase_invocation_command(
    runner: AnsibleRunner,
    *,
    repo_base: Path,
    entry: PlaybookEntrySpec,
    invocation: InvocationSpec,
    cluster_extra_vars: Path,
    controller_extra_vars: Path,
) -> list[str]:
    playbook_path = resolve_phase_playbook_path(repo_base, entry)
    # Planned/collapsed invocation.limit wins over env (CLI --limit already baked
    # in by apply_run_cli_overrides). Env LIMIT remains last-mile for catalog
    # invocations that have no limit of their own.
    limit = (invocation.limit or "").strip() or os.environ.get("LIMIT", "").strip() or None

    cmd = [
        "ansible-playbook",
        str(playbook_path),
        "-i",
        str(runner.ctx.inventory),
    ]
    if invocation.tags and invocation.tags != "all":
        cmd.extend(["--tags", invocation.tags])
    if limit:
        cmd.extend(["--limit", limit])
    cmd.extend(["-e", f"@{cluster_extra_vars}"])
    cmd.extend(["-e", f"@{controller_extra_vars}"])
    if invocation.root_ssh:
        cmd.extend(
            [
                "-e",
                "ansible_user=root",
                "-e",
                "ansible_ssh_user=root",
                "-e",
                f"ansible_ssh_private_key_file={runner.ctx.ssh_key}",
            ]
        )
    for item in invocation.extra_e:
        cmd.extend(["-e", item])
    return cmd


def run_phase_stage(
    runner: AnsibleRunner,
    stage: PhaseStagePlan,
    *,
    playbooks: PlaybooksConfig,
    dry_run: bool = False,
) -> None:
    repo_spec, entry = playbooks.resolve_entry(stage.phase_ref)
    repo_base = resolve_phase_repo_base(
        repo_spec,
        workspace_root=runner.ctx.workspace_root,
        repo_root_path=runner.ctx.repo_root,
    )

    header = f"--- phase {stage.phase_ref} ({stage.playbook_file}) ---"
    if runner._log_session:
        runner._log_session.write_line(header, stage=stage.phase_ref)
    else:
        print(header)

    if stage.git_ssh:
        runner._enable_git_ssh(dry_run=dry_run)

    cluster_extra_vars = runner._ensure_playbook_extra_vars()
    controller_extra_vars = materialize_controller_extra_vars(runner.ctx)

    for inv_plan in stage.invocations:
        invocation = inv_plan.invocation
        inv_header = (
            f"--- {stage.phase_ref} [{inv_plan.invocation_index}/{len(stage.invocations)}] "
            f"tags={invocation.tags} ---"
        )
        if runner._log_session:
            runner._log_session.write_line(inv_header, stage=stage.phase_ref)
        else:
            print(inv_header)

        env = runner._controller_env()
        configure_entry_env(
            env,
            runner.ctx.repo_root,
            repo_spec,
            entry,
            workspace_root=runner.ctx.workspace_root,
            repo_root_path=runner.ctx.repo_root,
        )
        if not dry_run:
            runner._apply_mitogen_env(env)
            runner._sync_env(env)

        cmd = build_phase_invocation_command(
            runner,
            repo_base=repo_base,
            entry=entry,
            invocation=invocation,
            cluster_extra_vars=cluster_extra_vars,
            controller_extra_vars=controller_extra_vars,
        )

        if dry_run:
            for line in (
                f"[dry-run] cwd={repo_base}",
                f"[dry-run] ANSIBLE_CONFIG={env['ANSIBLE_CONFIG']}",
                f"[dry-run] ANSIBLE_ROLES_PATH={env['ANSIBLE_ROLES_PATH']}",
                f"[dry-run] ANSIBLE_STRATEGY={env['ANSIBLE_STRATEGY']} forks={env['ANSIBLE_FORKS']}",
                f"[dry-run] {shlex.join(cmd)}",
            ):
                if runner._log_session:
                    runner._log_session.write_line(line, stage=stage.phase_ref)
                else:
                    print(line)
            continue

        streams = (
            runner._log_session.log_streams(stage=stage.phase_ref)
            if runner._log_session
            else None
        )
        result = run_subprocess_logged(
            cmd,
            cwd=repo_base,
            env=env,
            log_streams=streams,
        )
        if result != 0:
            raise ClusterctlError(
                f"ansible-playbook failed (exit {result}) "
                f"phase={stage.phase_ref} tags={invocation.tags}"
            )


def run_phase_stages(
    runner: AnsibleRunner,
    stages: tuple[PhaseStagePlan, ...] | list[PhaseStagePlan],
    *,
    playbooks: PlaybooksConfig,
    dry_run: bool = False,
) -> None:
    runner.bootstrap(dry_run=dry_run)
    try:
        for stage in stages:
            run_phase_stage(runner, stage, playbooks=playbooks, dry_run=dry_run)
    finally:
        if not dry_run:
            runner.teardown()
