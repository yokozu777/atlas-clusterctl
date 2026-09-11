"""Schema-driven playbook repo registry (G1 — no hardcoded repo names in Python)."""

from __future__ import annotations

from pathlib import Path

from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import (
    PhasesConfig,
    PlaybooksConfig,
    parse_phase_ref,
)


def repo_name_to_env_suffix(repo_name: str) -> str:
    return repo_name.upper().replace("-", "_").replace(".", "_")


def env_suffix_to_repo_name(suffix: str, known_names: frozenset[str] | set[str]) -> str:
    upper = suffix.upper()
    for name in known_names:
        if repo_name_to_env_suffix(name) == upper:
            return name
    raise ClusterctlError(
        f"unknown PLAYBOOKS/ROLE_REPOS env key suffix {suffix!r} — "
        f"expected one of: {', '.join(sorted(repo_name_to_env_suffix(n) for n in known_names))}"
    )


def repo_names_from_phase_refs(phase_refs: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Unique repo names in phase order (first occurrence wins)."""
    names: list[str] = []
    seen: set[str] = set()
    for phase_ref in phase_refs:
        repo_name, _ = parse_phase_ref(phase_ref)
        if repo_name not in seen:
            names.append(repo_name)
            seen.add(repo_name)
    return tuple(names)


def required_playbook_repo_names(
    playbooks: PlaybooksConfig | None,
    phases: PhasesConfig | None,
) -> frozenset[str]:
    """Repos referenced by the effective ``phases`` list."""
    if phases is None or not phases.phases:
        return frozenset()
    if playbooks is None:
        return frozenset(repo_names_from_phase_refs(phases.phases))

    names: set[str] = set()
    for phase_ref in phases.phases:
        repo_name, _ = parse_phase_ref(phase_ref)
        if repo_name not in playbooks.repos:
            raise ClusterctlError(
                f"phase {phase_ref!r} references unknown playbook repo {repo_name!r} — "
                f"define playbooks.{repo_name} in cluster.yaml cascade"
            )
        playbooks.resolve_entry(phase_ref)
        names.add(repo_name)
    return frozenset(names)


def known_playbook_repo_names(playbooks: PlaybooksConfig | None) -> frozenset[str]:
    if playbooks is None:
        return frozenset()
    return frozenset(playbooks.repos)


def validate_playbooks_phases_alignment(
    playbooks: PlaybooksConfig | None,
    phases: PhasesConfig | None,
) -> frozenset[str]:
    """Ensure every phase ref resolves; return required repo names."""
    if phases is None:
        return frozenset()
    if playbooks is None:
        raise ClusterctlError("phases require playbooks section in cluster.yaml")
    phases.validate(playbooks)
    return required_playbook_repo_names(playbooks, phases)


def org_baseline_playbook_repo_names(root: Path | None = None) -> tuple[str, ...]:
    """Sorted playbook repo names from org baseline catalog (G6 — no hardcoded stub list)."""
    try:
        from clusterctl.pipeline_fixture import load_org_baseline_cluster_config

        config = load_org_baseline_cluster_config(root)
        return tuple(sorted(known_playbook_repo_names(config.playbooks)))
    except (FileNotFoundError, ClusterctlError):
        return ()
