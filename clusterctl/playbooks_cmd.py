"""Playbook repository sync / status / show commands (schema v2)."""

from __future__ import annotations

import json

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import PhasesConfig, PlaybooksConfig
from clusterctl.playbooks_resolve import require_effective_playbooks_context
from clusterctl.playbooks_sync import (
    ensure_playbooks_synced,
    playbook_repo_status_lines,
    playbook_repo_status_records,
    playbooks_summary_lines,
    repo_names_for_all_phases,
    repo_names_for_phase_alias,
    repo_names_for_phase_refs,
)
from clusterctl.playbooks_lock import (
    playbooks_lock_status_lines,
    read_playbooks_lock,
    update_playbooks_lock,
)
from clusterctl.playbooks_paths import workspace_repos_root


def _require_playbooks(ctx: ClusterContext) -> tuple[PlaybooksConfig, PhasesConfig]:
    return require_effective_playbooks_context(ctx)


def cmd_playbooks_sync(
    ctx: ClusterContext,
    *,
    dry_run: bool = False,
    repo: str | None = None,
    phase_ref: str | None = None,
    phase: str | None = None,
) -> int:
    playbooks, phases = _require_playbooks(ctx)

    selectors = [repo, phase_ref, phase]
    if sum(1 for value in selectors if value) > 1:
        raise ClusterctlError("use only one of --repo, --phase-ref, or --phase")

    repo_names: tuple[str, ...] | None = None
    if repo:
        repo_names = (repo,)
    elif phase_ref:
        repo_names = repo_names_for_phase_refs((phase_ref,))
    elif phase:
        repo_names = repo_names_for_phase_alias(phase, phases=phases)
    else:
        repo_names = repo_names_for_all_phases(phases)

    results = ensure_playbooks_synced(
        playbooks_enabled=ctx.playbooks_enabled,
        playbooks=playbooks,
        phases=phases,
        workspace_root=ctx.workspace_root,
        repo_root_path=ctx.repo_root,
        repo_names=repo_names,
        dry_run=dry_run,
    )

    prefix = "[dry-run] " if dry_run else ""
    for result in results:
        detail = f" — {result.detail}" if result.detail else ""
        print(f"{prefix}{result.name}: {result.action} → {result.path}{detail}")

    if not dry_run and results:
        lock_path = update_playbooks_lock(
            cluster_id=ctx.cluster_id,
            workspace_id=ctx.workspace_id,
            workspace_root=ctx.workspace_root,
            playbooks=playbooks,
            results=results,
            repo_root_path=ctx.repo_root,
            repo_names=repo_names,
        )
        print(f"playbooks.lock updated → {lock_path}")

    return 0


def cmd_playbooks_status(ctx: ClusterContext, *, as_json: bool = False) -> int:
    playbooks, phases = _require_playbooks(ctx)
    repo_names = repo_names_for_all_phases(phases)
    lock = read_playbooks_lock(ctx.workspace_root)
    if as_json:
        payload = {
            "cluster_id": ctx.cluster_id,
            "workspace_root": str(ctx.workspace_root.resolve()),
            "repos": playbook_repo_status_records(
                playbooks,
                workspace_root=ctx.workspace_root,
                repo_root_path=ctx.repo_root,
                repo_names=repo_names,
            ),
            "lock": lock.to_dict() if lock is not None else None,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", end="")
        return 0
    for line in playbook_repo_status_lines(
        playbooks,
        workspace_root=ctx.workspace_root,
        repo_root_path=ctx.repo_root,
        repo_names=repo_names,
    ):
        print(line)
    for line in playbooks_lock_status_lines(lock, workspace_root=ctx.workspace_root):
        print(line)
    return 0


def cmd_playbooks_show(ctx: ClusterContext) -> int:
    playbooks, phases = _require_playbooks(ctx)
    ws = ctx.workspace_root.resolve()
    repo_names = repo_names_for_all_phases(phases)
    print(f"=== Playbooks: {ctx.cluster_id} ===")
    print(f"Schema:      v{ctx.schema_version}")
    print(f"Workspace:   {ws}")
    print(f"Git material: {workspace_repos_root(ws)}")
    print(f"Phases:      {len(phases.phases)} configured")
    for alias, target in sorted(phases.phase_aliases.items()):
        print(f"  alias {alias!r} → {target}")
    print("")
    for line in playbooks_summary_lines(
        playbooks,
        workspace_root=ws,
        repo_root_path=ctx.repo_root,
        repo_names=repo_names,
    ):
        print(line)
    print("")
    for line in playbook_repo_status_lines(
        playbooks,
        workspace_root=ws,
        repo_root_path=ctx.repo_root,
        repo_names=repo_names,
    ):
        print(line)
    lock = read_playbooks_lock(ws)
    print("")
    for line in playbooks_lock_status_lines(lock, workspace_root=ws):
        print(line)
    return 0
