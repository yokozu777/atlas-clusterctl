"""`./cluster list` — inventory leaves under clusters/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clusterctl.cluster_layout import canonical_cluster_id
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError, ClusterNotFoundError
from clusterctl.paths import (
    is_deployable_cluster_id,
    list_cluster_ids,
    read_active_cluster_id,
)


def collect_cluster_list(root: Path) -> list[dict[str, Any]]:
    """Rows for ``./cluster list --json``.

    ``kind``: ``deployable`` | ``policy`` | ``broken``.
    """
    entries: list[dict[str, Any]] = []
    ids = list_cluster_ids(root)
    active = read_active_cluster_id(root)
    for cluster_id in ids:
        if not is_deployable_cluster_id(root, cluster_id):
            entries.append(
                {
                    "id": cluster_id,
                    "display_name": None,
                    "active": False,
                    "kind": "policy",
                }
            )
            continue
        try:
            ctx = ClusterContext.load(cluster_id=cluster_id)
            active_match = bool(active and canonical_cluster_id(active) == cluster_id)
            entries.append(
                {
                    "id": cluster_id,
                    "display_name": ctx.display_name or None,
                    "active": active_match,
                    "kind": "deployable" if ctx.deployable else "policy",
                }
            )
        except ClusterNotFoundError:
            entries.append(
                {
                    "id": cluster_id,
                    "display_name": None,
                    "active": False,
                    "kind": "broken",
                    "error": "config fragment only",
                }
            )
        except ClusterctlError as exc:
            entries.append(
                {
                    "id": cluster_id,
                    "display_name": None,
                    "active": False,
                    "kind": "broken",
                    "error": str(exc),
                }
            )
    return entries


def print_cluster_list_text(root: Path) -> None:
    """Human listing — keep byte-stable with the pre-JSON CLI."""
    ids = list_cluster_ids(root)
    if not ids:
        print("(no clusters under clusters/ — ./cluster init <id>)")
        return
    for cluster_id in ids:
        if not is_deployable_cluster_id(root, cluster_id):
            print(f"{cluster_id}  [policy]")
            continue
        try:
            ctx = ClusterContext.load(cluster_id=cluster_id)
            active = read_active_cluster_id(root)
            active_match = active and canonical_cluster_id(active) == cluster_id
            label = "  ← active" if active_match else ""
            name = f" ({ctx.display_name})" if ctx.display_name else ""
            deployable = "" if ctx.deployable else "  [policy/template]"
            print(f"{cluster_id}{name}{deployable}{label}")
        except ClusterNotFoundError:
            print(f"{cluster_id}  [config fragment only]")
        except ClusterctlError as exc:
            print(f"{cluster_id}  [broken: {exc}]")


def cmd_list(root: Path, *, as_json: bool = False) -> int:
    if as_json:
        print(json.dumps(collect_cluster_list(root), indent=2, ensure_ascii=False) + "\n", end="")
        return 0
    print_cluster_list_text(root)
    return 0
