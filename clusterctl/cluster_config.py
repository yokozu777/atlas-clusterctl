"""Cluster config (clusters/<id>/cluster.yaml) loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML required") from exc

from clusterctl.cluster_layout import (
    CLUSTER_CONFIG_NAME,
    canonical_cluster_id,
    infer_repo_root_from_config_dir,
    is_deployable_config_dir,
    register_cluster_id_aliases,
)
from clusterctl.cluster_vars_loader import (
    discover_group_vars_cascade,
    require_group_vars_all,
)
from clusterctl.host_vars import discover_host_vars
from clusterctl.exceptions import (
    ClusterctlError,
    PhaseAliasesRemovedError,
    StacksRemovedError,
)
from clusterctl.execution import ExecutionConfig, execution_config_from_cluster_data
from clusterctl.playbooks_config import (
    SCHEMA_VERSION,
    ClusterConfigV2,
    resolve_playbooks_enabled,
)
from clusterctl.playbooks_registry import required_playbook_repo_names
from clusterctl.playbooks_repos import (
    ResolvedPlaybooksRepos,
    empty_resolved_playbooks_repos,
)

CLUSTER_CONFIG_NAME = CLUSTER_CONFIG_NAME  # re-export for cluster_config_path consumers


def reject_removed_stacks_key(data: dict, *, source: str) -> None:
    """ADR 005: YAML ``stacks:`` is a hard error (``StacksRemovedError``)."""
    if "stacks" not in data:
        return
    raise StacksRemovedError(source)


def reject_removed_phase_aliases_key(data: dict, *, source: str) -> None:
    """ADR 007: YAML ``phase_aliases:`` is a hard error (``PhaseAliasesRemovedError``)."""
    if "phase_aliases" not in data:
        return
    raise PhaseAliasesRemovedError(source)


@dataclass(frozen=True)
class ClusterConfig:
    cluster_id: str
    config_dir: Path
    inventory: Path
    group_var_files: tuple[Path, ...]
    host_var_files: tuple[tuple[str, Path], ...] = ()
    display_name: str | None = None
    workspace_id_override: str | None = None
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    playbooks_enabled: bool = False
    legacy_profile: str | None = None
    playbook_repos: ResolvedPlaybooksRepos = field(
        default_factory=empty_resolved_playbooks_repos
    )
    schema_version: int = 1
    config_v2: ClusterConfigV2 | None = None
    deployable: bool = True
    canonical_cluster_id: str | None = None
    cascade_paths: tuple[Path, ...] = ()

    @property
    def role_repos(self) -> ResolvedPlaybooksRepos:
        """Deprecated alias for :attr:`playbook_repos` (soft-compat Phase 5)."""
        return self.playbook_repos

    @property
    def profile(self) -> str | None:
        """Deprecated v1 profile key from leaf cluster.yaml (ignored by v2 runner)."""
        return self.legacy_profile


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ClusterctlError(f"invalid cluster config (expected mapping): {path}")
    reject_removed_stacks_key(data, source=str(path))
    reject_removed_phase_aliases_key(data, source=str(path))
    return data


def cluster_config_path(config_dir: Path) -> Path:
    return config_dir / CLUSTER_CONFIG_NAME


def has_cluster_layout(config_dir: Path) -> bool:
    return cluster_config_path(config_dir).is_file()


def _resolve_group_var_files(
    config_dir: Path,
    *,
    cluster_id: str,
    repo_root: Path,
) -> tuple[Path, ...]:
    """Leaf must still have overlays; merge list includes org/env policy layers."""
    require_group_vars_all(config_dir)
    from clusterctl.paths import cascade_group_vars_dirs_for_cluster

    cascade_dirs = cascade_group_vars_dirs_for_cluster(repo_root, cluster_id)
    if not cascade_dirs:
        return require_group_vars_all(config_dir)
    return discover_group_vars_cascade(cascade_dirs)


def _resolve_host_var_files(config_dir: Path) -> tuple[tuple[str, Path], ...]:
    return discover_host_vars(config_dir)


def _fragment_uses_schema_v2(data: dict) -> bool:
    if int(data.get("schema_version", 0) or 0) == SCHEMA_VERSION:
        return True
    if data.get("playbooks") or data.get("playbooks_enabled"):
        return True
    return False


def _uses_schema_v2_cascade(cascade_paths: tuple[Path, ...]) -> bool:
    for path in cascade_paths:
        if not path.is_file():
            continue
        if _fragment_uses_schema_v2(_load_yaml(path)):
            return True
    return False


def _infer_schema_version(data: dict, config_v2: ClusterConfigV2 | None) -> int:
    if config_v2 is not None:
        return SCHEMA_VERSION
    raw = int(data.get("schema_version", 0) or 0)
    if raw == SCHEMA_VERSION:
        return SCHEMA_VERSION
    if data.get("playbooks") or data.get("playbooks_enabled") or data.get("phases"):
        return SCHEMA_VERSION
    return raw or 1


def _load_merged_v2(cascade_paths: tuple[Path, ...]) -> ClusterConfigV2 | None:
    if not cascade_paths or not _uses_schema_v2_cascade(cascade_paths):
        return None
    from clusterctl.cluster_config_loader import load_cluster_config_v2_fragments

    merged = load_cluster_config_v2_fragments(list(cascade_paths))
    if merged.cluster_id_aliases:
        register_cluster_id_aliases(merged.cluster_id_aliases)
    return merged


def load_cluster_config(
    config_dir: Path,
    cluster_id: str,
    *,
    repo_root: Path | None = None,
) -> ClusterConfig:
    config_dir = config_dir.resolve()
    root = (repo_root or infer_repo_root_from_config_dir(config_dir)).resolve()
    from clusterctl.paths import cascade_paths_for_cluster, clusters_root as resolve_clusters_root

    # Prefer explicit ATLAS_CLUSTER_ROOT when inventory lives outside the checkout
    # (config.yaml / ATLAS_CLUSTERS_ROOT). infer_repo_root_from_config_dir would point at
    # the inventory parent and break playbook path resolution.
    if repo_root is None:
        try:
            from clusterctl.paths import repo_root as ambient_repo_root

            ambient = ambient_repo_root()
            inventory_root = resolve_clusters_root(ambient)
            config_dir.relative_to(inventory_root)
            root = ambient
        except (ValueError, OSError):
            pass

    canonical = canonical_cluster_id(cluster_id)
    cascade_paths = tuple(cascade_paths_for_cluster(root, canonical))
    config_v2 = _load_merged_v2(cascade_paths)
    deployable = is_deployable_config_dir(config_dir)

    cfg_path = cluster_config_path(config_dir)
    data: dict = _load_yaml(cfg_path) if cfg_path.is_file() else {}

    inventory_rel = str(
        (config_v2.inventory if config_v2 and config_v2.inventory else None)
        or data.get("inventory", "hosts")
    ).strip() or "hosts"
    inventory = config_dir / inventory_rel

    group_var_files = _resolve_group_var_files(
        config_dir,
        cluster_id=canonical,
        repo_root=root,
    )
    host_var_files = _resolve_host_var_files(config_dir)

    display_name = (
        (config_v2.display_name if config_v2 and config_v2.display_name else None)
        or data.get("display_name")
    )
    workspace_id = data.get("workspace_id")
    if workspace_id is None and config_v2 is not None:
        workspace_id = config_v2.workspace_id
    if workspace_id is not None:
        workspace_id = str(workspace_id).strip() or None

    profile = data.get("profile")
    legacy_profile = str(profile).strip() or None if profile is not None else None

    if config_v2 and config_v2.execution:
        execution = execution_config_from_cluster_data({"execution": config_v2.execution})
    else:
        execution = execution_config_from_cluster_data(data)

    playbooks_enabled = resolve_playbooks_enabled(data, config_v2=config_v2)

    playbook_repos = empty_resolved_playbooks_repos()
    if playbooks_enabled:
        if config_v2 is not None and config_v2.playbooks is not None:
            from clusterctl.playbooks_resolve import build_resolved_playbooks_repos

            required = required_playbook_repo_names(
                config_v2.playbooks,
                config_v2.phases,
            )
            playbook_repos = build_resolved_playbooks_repos(
                config_v2.playbooks,
                required_repos=required if required else None,
            )
        else:
            # Legacy v1 / missing playbooks cascade — runtime guards reject execution.
            playbook_repos = empty_resolved_playbooks_repos()

    resolved_id = str(
        (config_v2.cluster_id if config_v2 and config_v2.cluster_id else None)
        or data.get("id")
        or canonical
    )

    schema_version = _infer_schema_version(data, config_v2)

    return ClusterConfig(
        cluster_id=resolved_id,
        config_dir=config_dir,
        inventory=inventory,
        group_var_files=group_var_files,
        host_var_files=host_var_files,
        display_name=str(display_name) if display_name else None,
        workspace_id_override=workspace_id,
        execution=execution,
        playbooks_enabled=playbooks_enabled,
        legacy_profile=legacy_profile,
        playbook_repos=playbook_repos,
        schema_version=schema_version,
        config_v2=config_v2,
        deployable=deployable,
        canonical_cluster_id=canonical,
        cascade_paths=cascade_paths,
    )
