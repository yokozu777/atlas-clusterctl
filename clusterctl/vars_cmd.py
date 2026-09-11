"""`./cluster vars` — catalog of connected YAML (paths only, no file bodies)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from clusterctl.cluster_layout import (
    CLUSTER_CONFIG_NAME,
    canonical_cluster_id,
    discover_config_dir,
)
from clusterctl.cluster_vars_loader import (
    discover_group_vars_cascade,
    is_legacy_secrets_overlay,
    is_product_secrets_overlay,
)
from clusterctl.host_vars import discover_host_vars
from clusterctl.paths import cascade_group_vars_dirs_for_cluster, clusters_root, inventory_path


def _layer(clusters: Path, path: Path, cluster_id: str) -> str:
    try:
        rel = path.resolve().relative_to(clusters.resolve())
    except ValueError:
        return "other"
    parts = rel.parts
    if len(parts) >= 2:
        env, name = parts[0], parts[1]
        if env == "default" and name == "default":
            return "org"
        if name == "default":
            return "env"
        if f"{env}/{name}" == cluster_id:
            return "leaf"
    if len(parts) >= 1 and parts[0] == cluster_id:
        return "leaf"
    return "leaf"


def _rel_to_clusters(clusters: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(clusters.resolve()).as_posix()
    except ValueError:
        return None


def _is_secret(name: str) -> bool:
    return is_product_secrets_overlay(name) or is_legacy_secrets_overlay(name)


def collect_cluster_vars(root: Path, cluster_id: str) -> dict[str, Any]:
    """JSON catalog for ``./cluster vars --json`` (paths only)."""
    clusters = clusters_root(root)
    cid = canonical_cluster_id(cluster_id)
    config_dir = discover_config_dir(clusters, cid)

    files: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(path: Path, kind: str) -> None:
        if not path.is_file():
            return
        rel = _rel_to_clusters(clusters, path)
        if rel is None or rel in seen:
            return
        seen.add(rel)
        files.append(
            {
                "rel": rel,
                "layer": _layer(clusters, path, cid),
                "kind": kind,
                "secret": _is_secret(path.name),
            }
        )

    add(config_dir / CLUSTER_CONFIG_NAME, "cluster")
    add(inventory_path(config_dir), "inventory")
    cascade_dirs = cascade_group_vars_dirs_for_cluster(root, cid)
    for path in discover_group_vars_cascade(cascade_dirs):
        add(path, "group_vars")
    for _host, path in discover_host_vars(config_dir):
        add(path, "host_vars")

    return {
        "cluster_id": cid,
        "clusters_root": str(clusters.resolve()),
        "files": files,
    }


def cmd_vars(root: Path, cluster_id: str, *, as_json: bool = False) -> int:
    try:
        payload = collect_cluster_vars(root, cluster_id)
    except FileNotFoundError as exc:
        print(f"cluster: {exc}", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", end="")
        return 0

    files = payload["files"]
    if not files:
        print("(no connected vars files)")
        return 0
    for row in files:
        secret = " secret" if row["secret"] else ""
        print(f"{row['layer']:5}  {row['kind']:10}{secret:8}  {row['rel']}")
    return 0
