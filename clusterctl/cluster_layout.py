"""Cluster directory layout for hierarchical clusters/<env>/<name>/ paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Mapping

from clusterctl.exceptions import ClusterctlError

CLUSTER_CONFIG_NAME = "cluster.yaml"
_LEGACY_CLUSTER_ID = re.compile(r"^[a-z][a-z0-9._-]*$")
_HIERARCHICAL_CLUSTER_ID = re.compile(r"^[a-z][a-z0-9._-]+/[a-z][a-z0-9._-]+$")

ORG_BASELINE_SEGMENTS = ("default", "default")
ENV_DEFAULT_SUFFIX = "default"

# Built-in aliases removed (soft-compat Phase 4). Use cascade `cluster_id_aliases`
# on the leaf / org baseline (e.g. inventory `dev/mxhash` declares dev-mxhash.com).
_BUILTIN_CLUSTER_ID_ALIASES: dict[str, str] = {}

_registered_cluster_id_aliases: dict[str, str] = {}
_warned_cluster_id_aliases: set[str] = set()


def register_cluster_id_aliases(aliases: Mapping[str, str] | None) -> None:
    """Register cascade-declared cluster id aliases for canonical resolution."""
    _registered_cluster_id_aliases.clear()
    if not aliases:
        return
    for alias, target in aliases.items():
        alias_text = str(alias).strip()
        target_text = str(target).strip()
        if alias_text and target_text:
            _registered_cluster_id_aliases[alias_text] = target_text


def reset_cluster_id_aliases_for_tests() -> None:
    _registered_cluster_id_aliases.clear()
    _warned_cluster_id_aliases.clear()


def effective_cluster_id_aliases() -> dict[str, str]:
    merged = dict(_BUILTIN_CLUSTER_ID_ALIASES)
    merged.update(_registered_cluster_id_aliases)
    return merged


CLUSTER_ID_ALIASES = _BUILTIN_CLUSTER_ID_ALIASES  # deprecated module constant (empty)


def canonical_cluster_id(cluster_id: str, *, warn: bool = True) -> str:
    text = normalize_cluster_id(cluster_id)
    aliases = effective_cluster_id_aliases()
    target = aliases.get(text, text)
    if warn and target != text:
        _warn_deprecated_cluster_id_alias(text, target)
    return target


def _warn_deprecated_cluster_id_alias(alias: str, canonical: str) -> None:
    if alias in _warned_cluster_id_aliases:
        return
    _warned_cluster_id_aliases.add(alias)
    print(
        f"clusterctl: deprecated cluster id alias {alias!r} — use {canonical!r}",
        file=sys.stderr,
    )


def legacy_cluster_ids_for_canonical(canonical_id: str) -> tuple[str, ...]:
    aliases = effective_cluster_id_aliases()
    return tuple(
        alias
        for alias, target in aliases.items()
        if target == canonical_id
    )


def normalize_cluster_id(cluster_id: str) -> str:
    text = str(cluster_id).strip().strip("/")
    if not text:
        raise ClusterctlError("cluster id is empty")
    return text


def validate_cluster_id(cluster_id: str, *, allow_policy_ids: bool = False) -> str:
    text = normalize_cluster_id(cluster_id)
    if text == "default":
        return text
    if _HIERARCHICAL_CLUSTER_ID.fullmatch(text):
        env, name = text.split("/", 1)
        if name == ENV_DEFAULT_SUFFIX:
            if env == "default":
                return text  # org baseline: default/default
            if not allow_policy_ids:
                raise ClusterctlError(
                    f"cluster id {text!r} is an env policy path — use a deployable "
                    f"cluster id (e.g. {env}/mycluster)"
                )
        return text
    if _LEGACY_CLUSTER_ID.fullmatch(text):
        return text
    raise ClusterctlError(
        f"invalid cluster id {cluster_id!r} — use env/name (e.g. dev/mxhash) "
        "or legacy single-segment id"
    )


def cluster_id_path_parts(cluster_id: str) -> tuple[str, ...]:
    text = validate_cluster_id(cluster_id)
    if "/" in text:
        return tuple(part for part in text.split("/") if part)
    return (text,)


def cluster_config_dir(clusters_root: Path, cluster_id: str) -> Path:
    parts = cluster_id_path_parts(cluster_id)
    return clusters_root.joinpath(*parts)


def infer_repo_root_from_config_dir(config_dir: Path) -> Path:
    """Derive atlas-clusterctl repo root from a path under ``clusters/<…>/``."""
    config_dir = config_dir.resolve()
    for parent in config_dir.parents:
        if parent.name == "clusters":
            return parent.parent
    raise ClusterctlError(
        f"cannot infer repository root from config_dir {config_dir} "
        f"(expected path under .../clusters/<id>/)"
    )


def cluster_id_from_config_dir(
    config_dir: Path,
    *,
    clusters_root: Path | None = None,
) -> str:
    """Map ``clusters/<env>/<name>/`` (or legacy flat ``clusters/<id>/``) to cluster id."""
    config_dir = config_dir.resolve()
    if clusters_root is None:
        clusters_root = infer_repo_root_from_config_dir(config_dir) / "clusters"
    else:
        clusters_root = clusters_root.resolve()
    try:
        rel = config_dir.relative_to(clusters_root)
    except ValueError as exc:
        raise ClusterctlError(
            f"config_dir {config_dir} is not under clusters root {clusters_root}"
        ) from exc
    if not rel.parts:
        raise ClusterctlError(
            f"config_dir must be a cluster leaf directory, not clusters root: {config_dir}"
        )
    return "/".join(rel.parts)


def cluster_config_path(clusters_root: Path, cluster_id: str) -> Path:
    return cluster_config_dir(clusters_root, cluster_id) / CLUSTER_CONFIG_NAME


def is_env_policy_dir(config_dir: Path) -> bool:
    return config_dir.name == ENV_DEFAULT_SUFFIX and config_dir.parent.name != "default"


def is_org_baseline_dir(config_dir: Path) -> bool:
    return config_dir.name == "default" and config_dir.parent.name == "default"


def is_org_baseline_cluster_id(cluster_id: str) -> bool:
    return normalize_cluster_id(cluster_id) == "default/default"


def is_deployable_config_dir(config_dir: Path) -> bool:
    if is_org_baseline_dir(config_dir):
        return False
    if is_env_policy_dir(config_dir):
        return False
    if config_dir.name == ENV_DEFAULT_SUFFIX:
        return False
    return True


def cascade_fragment_paths(
    clusters_root: Path,
    cluster_id: str,
    *,
    product_clusters_root: Path | None = None,
) -> list[Path]:
    """Return existing cluster.yaml fragments from org → env → leaf (in order).

    When the live inventory tree omits ``default/default``, optionally fall back to
    ``product_clusters_root/default/default`` (controller checkout stubs).
    """
    clusters_root = clusters_root.resolve()
    text = normalize_cluster_id(cluster_id)
    paths: list[Path] = []

    org_baseline = clusters_root / "default" / "default" / CLUSTER_CONFIG_NAME
    if org_baseline.is_file():
        paths.append(org_baseline)
    elif product_clusters_root is not None:
        product_org = (
            product_clusters_root.resolve() / "default" / "default" / CLUSTER_CONFIG_NAME
        )
        if product_org.is_file():
            paths.append(product_org)

    if "/" in text:
        env, name = text.split("/", 1)
        env_default = clusters_root / env / ENV_DEFAULT_SUFFIX / CLUSTER_CONFIG_NAME
        if env_default.is_file():
            paths.append(env_default)
        leaf = clusters_root / env / name / CLUSTER_CONFIG_NAME
        if leaf.is_file():
            paths.append(leaf)
        else:
            for legacy_id in legacy_cluster_ids_for_canonical(text):
                legacy_path = clusters_root / legacy_id / CLUSTER_CONFIG_NAME
                if legacy_path.is_file() and legacy_path not in paths:
                    paths.append(legacy_path)
        return paths

    legacy = clusters_root / text / CLUSTER_CONFIG_NAME
    if legacy.is_file() and legacy not in paths:
        paths.append(legacy)
    return paths


def cascade_group_vars_dirs(
    clusters_root: Path,
    cluster_id: str,
    *,
    product_clusters_root: Path | None = None,
) -> list[Path]:
    """Return existing ``group_vars/all`` dirs from org → env → leaf (in order).

    Mirrors :func:`cascade_fragment_paths` path rules. Policy layers are optional;
    only directories that exist are returned. Product org-baseline fallback applies
    when inventory omits ``default/default/group_vars/all``.
    """
    clusters_root = clusters_root.resolve()
    text = normalize_cluster_id(cluster_id)
    dirs: list[Path] = []

    def _add(config_dir: Path) -> None:
        all_dir = (config_dir / "group_vars" / "all").resolve()
        if all_dir.is_dir() and all_dir not in dirs:
            dirs.append(all_dir)

    org = clusters_root / "default" / "default"
    if (org / "group_vars" / "all").is_dir():
        _add(org)
    elif product_clusters_root is not None:
        product_org = product_clusters_root.resolve() / "default" / "default"
        if (product_org / "group_vars" / "all").is_dir():
            _add(product_org)

    if "/" in text:
        env, name = text.split("/", 1)
        _add(clusters_root / env / ENV_DEFAULT_SUFFIX)
        leaf = clusters_root / env / name
        if (leaf / "group_vars" / "all").is_dir():
            _add(leaf)
        else:
            for legacy_id in legacy_cluster_ids_for_canonical(text):
                legacy = clusters_root / legacy_id
                if (legacy / "group_vars" / "all").is_dir():
                    _add(legacy)
                    break
        return dirs

    _add(clusters_root / text)
    return dirs


def _has_any_group_vars_all(config_dir: Path) -> bool:
    all_dir = config_dir / "group_vars" / "all"
    if not all_dir.is_dir():
        return False
    for path in all_dir.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix not in {".yml", ".yaml"}:
            continue
        if path.name.endswith(".example"):
            continue
        return True
    return False


def config_dir_is_usable(config_dir: Path) -> bool:
    """True when the directory looks like a cluster leaf (ADR 003 Phase 1).

    ``cluster.yml`` is no longer required; any mergeable ``group_vars/all/*.yml`` counts.
    """
    return (
        (config_dir / CLUSTER_CONFIG_NAME).is_file()
        or (config_dir / "hosts").is_file()
        or _has_any_group_vars_all(config_dir)
    )


def discover_config_dir(clusters_root: Path, cluster_id: str) -> Path:
    """Resolve clusters/<path>/ for legacy flat, hierarchical, and alias ids."""
    clusters_root = clusters_root.resolve()
    requested = normalize_cluster_id(cluster_id)
    canonical = canonical_cluster_id(requested)

    candidates: list[Path] = []

    def _add(path: Path) -> None:
        if path not in candidates:
            candidates.append(path)

    if "/" in canonical:
        _add(clusters_root.joinpath(*canonical.split("/")))
    else:
        _add(clusters_root / canonical)

    if requested != canonical:
        if "/" in requested:
            _add(clusters_root.joinpath(*requested.split("/")))
        else:
            _add(clusters_root / requested)

    for legacy_id in legacy_cluster_ids_for_canonical(canonical):
        _add(clusters_root / legacy_id)

    for path in candidates:
        if config_dir_is_usable(path):
            return path.resolve()

    raise FileNotFoundError(
        f"cluster config not found for {cluster_id!r} (canonical {canonical!r})"
    )


def is_deployable_cluster_id(clusters_root: Path, cluster_id: str) -> bool:
    """True when *cluster_id* resolves to a deployable leaf (not org/env policy)."""
    clusters_root = clusters_root.resolve()
    try:
        config_dir = discover_config_dir(clusters_root, cluster_id)
    except FileNotFoundError:
        return False
    return is_deployable_config_dir(config_dir)


def list_deployable_cluster_ids(clusters_root: Path) -> list[str]:
    """Cluster IDs that pass :func:`is_deployable_cluster_id` (validate/smoke targets)."""
    return [
        cluster_id
        for cluster_id in list_cluster_ids(clusters_root)
        if is_deployable_cluster_id(clusters_root, cluster_id)
    ]


def list_cluster_ids(clusters_root: Path) -> list[str]:
    clusters_root = clusters_root.resolve()
    if not clusters_root.is_dir():
        return []

    ids: list[str] = []

    def _maybe_add(config_dir: Path) -> None:
        if not config_dir_is_usable(config_dir):
            return
        try:
            rel = config_dir.relative_to(clusters_root)
        except ValueError:
            return
        if rel.parts and rel.parts[0].startswith("_"):
            return
        if len(rel.parts) == 2:
            ids.append(f"{rel.parts[0]}/{rel.parts[1]}")
        elif len(rel.parts) == 1:
            ids.append(rel.parts[0])

    for env_dir in sorted(clusters_root.iterdir()):
        if not env_dir.is_dir() or env_dir.name.startswith("_"):
            continue
        for child in sorted(env_dir.iterdir()):
            if child.is_dir():
                _maybe_add(child)
        _maybe_add(env_dir)

    canonical_ids: list[str] = []
    seen_dirs: set[Path] = set()
    for cluster_id in sorted(set(ids)):
        try:
            config_dir = discover_config_dir(clusters_root, cluster_id)
        except FileNotFoundError:
            continue
        if config_dir in seen_dirs:
            continue
        seen_dirs.add(config_dir)
        canonical_ids.append(canonical_cluster_id(cluster_id))
    return sorted(set(canonical_ids))
