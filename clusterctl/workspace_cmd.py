"""Workspace show / reset / id commands."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError, WorkspaceResetAborted
from clusterctl.paths import repo_root, workspace_parent
from clusterctl.workspace_id import resolve_workspace_id
from clusterctl.workspace_paths import workspace_ansible_summary_lines


def cmd_workspace_show(ctx: ClusterContext, *, as_json: bool = False) -> int:
    if as_json:
        payload = {
            "cluster_id": ctx.cluster_id,
            "workspace_id": ctx.workspace_id,
            "workspace_root": str(ctx.workspace_root),
            "logs": str(ctx.workspace_logs),
            "kubeconfig": str(ctx.kubeconfig),
            "kubeconfig_exists": ctx.kubeconfig.is_file(),
            "lines": list(ctx.summary_lines()),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", end="")
        return 0
    for line in ctx.summary_lines():
        print(line)
    print("")
    print("Repo-root .ansible/ and .ansible_facts_cache/ are legacy — ./cluster validate --repo")
    return 0


def cmd_workspace_reset(ctx: ClusterContext, *, assume_yes: bool = False) -> int:
    target = ctx.workspace_root.resolve()
    parent = workspace_parent(ctx.repo_root).resolve()

    try:
        target.relative_to(parent)
    except ValueError as exc:
        raise ClusterctlError(
            f"refusing to delete path outside workspace parent {parent}: {target}"
        ) from exc
    if target == parent:
        raise ClusterctlError(f"refusing to delete workspace parent itself: {target}")

    if not target.exists():
        print(f"workspace already absent: {target}")
        return 0

    print("This will permanently delete cluster runtime data:")
    print(f"  {target}")
    for line in workspace_ansible_summary_lines(
        target,
        workspace_id=ctx.workspace_id,
        controller_temp=ctx.controller_temp_location(),
    ):
        print(f"    {line}")
    print("    controller-state/, tf_workspace/, logs/, build/, generated/, …")
    print("  Durable TF state (not deleted): tfstate/<env>/<name>/")

    if not assume_yes:
        try:
            answer = input("Type the workspace id to confirm: ").strip()
        except EOFError:
            raise WorkspaceResetAborted("confirmation required (use --yes in CI)") from None
        if answer != ctx.workspace_id:
            raise WorkspaceResetAborted("confirmation did not match workspace id")

    shutil.rmtree(target)
    print(f"removed {target}")
    return 0


def resolve_repo_root_from_env() -> Path:
    return repo_root()


def cmd_workspace_id(cluster_id: str | None = None) -> int:
    """Print resolved workspace id for shell bootstrap (stdout only)."""
    root = repo_root()
    os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))

    try:
        ctx = ClusterContext.load(cluster_id=cluster_id)
        print(ctx.workspace_id)
        return 0
    except ClusterctlError as ctx_exc:
        try:
            print(resolve_workspace_id(root))
            return 0
        except ValueError as resolve_exc:
            print(
                f"cluster: workspace id: {ctx_exc}; {resolve_exc}",
                file=sys.stderr,
            )
            return 1
