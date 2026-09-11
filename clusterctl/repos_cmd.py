"""Unified repository sync — schema v2 playbooks."""

from __future__ import annotations

from clusterctl.context import ClusterContext
from clusterctl.playbooks_cmd import (
    cmd_playbooks_show,
    cmd_playbooks_status,
    cmd_playbooks_sync,
)


def cmd_repos_sync(
    ctx: ClusterContext,
    *,
    dry_run: bool = False,
    repo: str | None = None,
    phase_ref: str | None = None,
    phase: str | None = None,
) -> int:
    return cmd_playbooks_sync(
        ctx,
        dry_run=dry_run,
        repo=repo,
        phase_ref=phase_ref,
        phase=phase,
    )


def cmd_repos_status(ctx: ClusterContext, *, as_json: bool = False) -> int:
    return cmd_playbooks_status(ctx, as_json=as_json)


def cmd_repos_show(ctx: ClusterContext) -> int:
    return cmd_playbooks_show(ctx)
