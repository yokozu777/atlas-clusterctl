"""Org baseline and playbooks validation (no playbooks_resolve import at module load)."""

from __future__ import annotations

from pathlib import Path

from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import ORG_BASELINE_REL, load_org_baseline_cluster_config
from clusterctl.playbooks_registry import validate_playbooks_phases_alignment


def validate_org_baseline_playbooks(root: Path | None = None):
    """Validate org baseline (seeded default/default, lab, or public template) playbooks vs phases."""
    from clusterctl.playbooks_resolve import build_resolved_playbooks_repos

    config = load_org_baseline_cluster_config(root)
    config.validate()
    if config.playbooks is None or config.phases is None:
        raise ClusterctlError(
            f"org baseline missing playbooks or phases ({ORG_BASELINE_REL})"
        )

    required = validate_playbooks_phases_alignment(config.playbooks, config.phases)
    return build_resolved_playbooks_repos(config.playbooks, required_repos=required)
