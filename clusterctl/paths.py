"""Repository and cluster path resolution."""

from __future__ import annotations

import os
from pathlib import Path

from clusterctl.cluster_layout import (
    canonical_cluster_id,
    cascade_fragment_paths,
    cascade_group_vars_dirs,
    cluster_id_from_config_dir,
    discover_config_dir,
    is_deployable_cluster_id as layout_is_deployable_cluster_id,
    list_cluster_ids as layout_list_cluster_ids,
    list_deployable_cluster_ids as layout_list_deployable_cluster_ids,
)
from clusterctl.cluster_layout import CLUSTER_CONFIG_NAME as _CLUSTER_CONFIG_NAME
from clusterctl.cluster_vars_loader import optional_cluster_var_file
from clusterctl.user_config import (
    ENV_CLUSTERS_ROOT,
    ENV_WORKSPACE_ROOT,
    clusters_path_from_user_config,
    workspace_path_from_user_config,
)

ACTIVE_CLUSTER_FILE = ".cluster-active"
DEFAULT_CLUSTER_ID = "default"


def repo_root() -> Path:
    return Path(os.environ.get("ATLAS_CLUSTER_ROOT", Path.cwd())).resolve()


def product_clusters_root(root: Path | None = None) -> Path:
    """Scaffolds shipped with the controller checkout (``clusters/_template``, stubs)."""
    return (root or repo_root()) / "clusters"


def clusters_root(root: Path | None = None) -> Path:
    """Live inventory tree (list / use / validate / init target).

    Resolution order:

    1. ``ATLAS_CLUSTERS_ROOT``
    2. ``clusters.path`` in ``$ATLAS_CLUSTER_ROOT/.config/config.yaml``
    3. ``$ATLAS_CLUSTER_ROOT/clusters`` (same as :func:`product_clusters_root`)
    """
    base = root or repo_root()
    env = os.environ.get(ENV_CLUSTERS_ROOT, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    from_cfg = clusters_path_from_user_config(repo_root=base)
    if from_cfg is not None:
        return from_cfg
    return product_clusters_root(base)


def atlas_inventory_root(root: Path | None = None) -> Path:
    """Git checkout root that owns ``clusters/`` (and usually ``tfstate/``).

    When ``clusters.path`` / ``ATLAS_CLUSTERS_ROOT`` ends with a ``clusters``
    segment (normal layout), this is its parent — e.g.
    ``…/atlas-inventory`` for ``…/atlas-inventory/clusters``.

    If the configured path is already the inventory checkout (unusual), that
    path is returned unchanged.
    """
    clusters = clusters_root(root).resolve()
    if clusters.name == "clusters":
        return clusters.parent.resolve()
    return clusters


def cascade_paths_for_cluster(root: Path, cluster_id: str) -> list[Path]:
    """Cascade fragments under inventory root, with product org-baseline fallback."""
    inventory = clusters_root(root)
    product = product_clusters_root(root)
    product_arg = None if inventory.resolve() == product.resolve() else product
    return cascade_fragment_paths(
        inventory,
        cluster_id,
        product_clusters_root=product_arg,
    )


def cascade_group_vars_dirs_for_cluster(root: Path, cluster_id: str) -> list[Path]:
    """``group_vars/all`` dirs org → env → leaf (inventory + product org fallback)."""
    inventory = clusters_root(root)
    product = product_clusters_root(root)
    product_arg = None if inventory.resolve() == product.resolve() else product
    return cascade_group_vars_dirs(
        inventory,
        cluster_id,
        product_clusters_root=product_arg,
    )


def active_cluster_file(root: Path | None = None) -> Path:
    return (root or repo_root()) / ACTIVE_CLUSTER_FILE


def read_active_cluster_id(root: Path | None = None) -> str | None:
    path = active_cluster_file(root)
    if not path.is_file():
        return None
    cluster_id = path.read_text(encoding="utf-8").strip()
    return cluster_id or None


def write_active_cluster_id(cluster_id: str, root: Path | None = None) -> Path:
    path = active_cluster_file(root)
    canonical = canonical_cluster_id(cluster_id)
    path.write_text(f"{canonical}\n", encoding="utf-8")
    return path


def resolve_cluster_id(explicit: str | None = None, root: Path | None = None) -> str:
    base = root or repo_root()
    raw = (
        (explicit or "").strip()
        or os.environ.get("CLUSTER_ID", "").strip()
        or read_active_cluster_id(base)
        or DEFAULT_CLUSTER_ID
    )
    return canonical_cluster_id(raw) if raw else DEFAULT_CLUSTER_ID


def cluster_dir(root: Path, cluster_id: str) -> Path:
    try:
        return discover_config_dir(clusters_root(root), cluster_id)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"cluster config not found: clusters/... ({cluster_id!r})"
        ) from exc


def list_cluster_ids(root: Path) -> list[str]:
    return layout_list_cluster_ids(clusters_root(root))


def is_deployable_cluster_id(root: Path, cluster_id: str) -> bool:
    return layout_is_deployable_cluster_id(clusters_root(root), cluster_id)


def list_deployable_cluster_ids(root: Path) -> list[str]:
    return layout_list_deployable_cluster_ids(clusters_root(root))


def inventory_path(config_dir: Path) -> Path:
    return config_dir / "hosts"


def cluster_var_file_path(config_dir: Path, root: Path) -> Path | None:
    """Return optional ``group_vars/all/cluster.yml`` after validating the leaf.

    ADR 003 Phase 1: may be ``None`` when the stub is absent.
    """
    from clusterctl.cluster_config import load_cluster_config

    cluster_id = cluster_id_from_config_dir(
        config_dir,
        clusters_root=clusters_root(root),
    )
    load_cluster_config(config_dir, cluster_id, repo_root=root)
    return optional_cluster_var_file(config_dir)


def cluster_config_path_for_dir(config_dir: Path) -> Path:
    return config_dir / _CLUSTER_CONFIG_NAME


def workspace_relpath(cluster_id: str) -> Path:
    """Relative path under the workspace parent, mirroring ``clusters/<env>/<name>/``."""
    from clusterctl.cluster_layout import canonical_cluster_id, cluster_id_path_parts

    parts = cluster_id_path_parts(canonical_cluster_id(cluster_id))
    return Path(*parts)


def workspace_parent(root: Path | None = None) -> Path:
    """Parent directory that contains per-cluster workspace trees.

    Resolution order:

    1. ``ATLAS_WORKSPACE_ROOT``
    2. ``workspace.path`` in ``$ATLAS_CLUSTER_ROOT/.config/config.yaml``
    3. ``$ATLAS_CLUSTER_ROOT/workspace``
    """
    base = root or repo_root()
    env = os.environ.get(ENV_WORKSPACE_ROOT, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    from_cfg = workspace_path_from_user_config(repo_root=base)
    if from_cfg is not None:
        return from_cfg
    return (base / "workspace").resolve()


def workspace_root(root: Path, cluster_id: str) -> Path:
    """Per-cluster runtime tree: ``<workspace.parent>/<env>/<name>/``."""
    return workspace_parent(root) / workspace_relpath(cluster_id)


def workspace_log_dir(root: Path, cluster_id: str) -> Path:
    return workspace_root(root, cluster_id) / "logs"


def kubeconfig_path(root: Path, cluster_id: str) -> Path:
    return (
        workspace_root(root, cluster_id)
        / "controller-state"
        / "kubeconfig"
        / "admin.conf"
    )


def iter_workspace_cluster_dirs(root: Path | None = None) -> list[Path]:
    """Leaf workspace dirs that look like per-cluster runtime trees."""
    parent = workspace_parent(root)
    if not parent.is_dir():
        return []
    markers = ("repos", "controller-state", "logs", ".ansible", "playbooks.lock")
    found: list[Path] = []
    for path in sorted(parent.rglob("*")):
        if not path.is_dir():
            continue
        if any(
            (path / name).exists() if name != "playbooks.lock" else (path / name).is_file()
            for name in markers
        ):
            found.append(path)
    return found
