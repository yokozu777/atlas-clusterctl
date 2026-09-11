"""Load and merge schema v2 cluster.yaml fragments (cascade)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from clusterctl.cluster_layout import (
    cascade_fragment_paths,
    cluster_config_dir,
    is_deployable_config_dir,
    validate_cluster_id,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import (
    SCHEMA_VERSION,
    ClusterConfigV2,
    load_cluster_config_v2_yaml,
    merge_cluster_config_v2,
    playbooks_config_to_raw,
    phases_config_to_raw,
)


def load_cluster_config_v2_fragments(paths: list[Path]) -> ClusterConfigV2:
    merged: ClusterConfigV2 | None = None
    for path in paths:
        fragment = load_cluster_config_v2_yaml(path)
        merged = merge_cluster_config_v2(merged, fragment)
    if merged is None:
        raise ClusterctlError("no cluster config fragments to load")
    return merged


def load_merged_cluster_config_v2(
    clusters_root: Path,
    cluster_id: str,
    *,
    product_clusters_root: Path | None = None,
) -> ClusterConfigV2:
    cluster_id = validate_cluster_id(cluster_id, allow_policy_ids=True)
    paths = cascade_fragment_paths(
        clusters_root,
        cluster_id,
        product_clusters_root=product_clusters_root,
    )
    if not paths:
        raise ClusterctlError(
            f"no cluster.yaml cascade found for {cluster_id!r} under {clusters_root}"
        )
    config = load_cluster_config_v2_fragments(paths)
    config_dir = cluster_config_dir(clusters_root, cluster_id)
    deployable = is_deployable_config_dir(config_dir)
    if config.cluster_id is None:
        config = replace(config, cluster_id=cluster_id)
    config = replace(config, deployable=deployable)
    return config


def load_merged_cluster_config_v2_for_repo(
    repo_root: Path,
    cluster_id: str,
) -> ClusterConfigV2:
    """Load cascade using inventory + product org-baseline resolution."""
    from clusterctl.paths import (
        cascade_paths_for_cluster,
        clusters_root as resolve_clusters_root,
    )

    cluster_id = validate_cluster_id(cluster_id, allow_policy_ids=True)
    paths = cascade_paths_for_cluster(repo_root, cluster_id)
    if not paths:
        inventory = resolve_clusters_root(repo_root)
        raise ClusterctlError(
            f"no cluster.yaml cascade found for {cluster_id!r} under {inventory}"
        )
    config = load_cluster_config_v2_fragments(paths)
    inventory = resolve_clusters_root(repo_root)
    config_dir = cluster_config_dir(inventory, cluster_id)
    deployable = is_deployable_config_dir(config_dir) if config_dir.is_dir() else False
    if config.cluster_id is None:
        config = replace(config, cluster_id=cluster_id)
    return replace(config, deployable=deployable)

def cluster_config_v2_to_yaml_dict(config: ClusterConfigV2) -> dict[str, Any]:
    data: dict[str, Any] = {"schema_version": config.schema_version or SCHEMA_VERSION}
    if config.cluster_id:
        data["id"] = config.cluster_id
    if config.display_name:
        data["display_name"] = config.display_name
    if config.inventory:
        data["inventory"] = config.inventory
    if config.workspace_id:
        data["workspace_id"] = config.workspace_id
    if config.deployable is not None:
        data["deployable"] = config.deployable
    if config.cluster_id_aliases:
        data["cluster_id_aliases"] = dict(config.cluster_id_aliases)
    if config.playbooks_enabled is True:
        data["playbooks_enabled"] = True
    elif config.playbooks_enabled is False:
        data["playbooks_enabled"] = False
    if config.playbooks is not None:
        data["playbooks"] = playbooks_config_to_raw(config.playbooks)
    if config.phases is not None:
        data.update(phases_config_to_raw(config.phases))
    if config.execution:
        data["execution"] = dict(config.execution)
    return data


def dump_cluster_config_v2(config: ClusterConfigV2) -> str:
    return yaml.safe_dump(
        cluster_config_v2_to_yaml_dict(config),
        sort_keys=False,
        allow_unicode=True,
    )
