"""Unified ansible configuration (schema v2 boundary → entry env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import (
    PhasesConfig,
    PlaybookEntrySpec,
    PlaybookRepoSpec,
    PlaybooksConfig,
)


@dataclass(frozen=True)
class PhaseSettings:
    strategy: str
    forks: int


def repo_root() -> Path:
    from clusterctl.paths import repo_root as _repo_root

    return _repo_root()


def resolve_ansible_config(root: Path | None = None) -> Path:
    base = root or repo_root()
    cfg = base / "ansible.cfg"
    if not cfg.is_file():
        raise ClusterctlError(f"ansible config not found: {cfg}")
    return cfg


def resolve_boundary_entry(
    boundary: str,
    playbooks: PlaybooksConfig,
    phases: PhasesConfig,
) -> tuple[str, PlaybookRepoSpec, PlaybookEntrySpec]:
    """Resolve CLI boundary (alias or repo/entry) to playbook entry."""
    from clusterctl.phase_plan import resolve_phase_boundary

    phase_ref = resolve_phase_boundary(boundary, phases)
    repo_spec, entry = playbooks.resolve_entry(phase_ref)
    return phase_ref, repo_spec, entry


def entry_settings(entry: PlaybookEntrySpec) -> PhaseSettings:
    return PhaseSettings(strategy=entry.ansible.strategy, forks=entry.ansible.forks)


def configure_entry_env(
    env: dict[str, str],
    root: Path,
    repo_spec: PlaybookRepoSpec,
    entry: PlaybookEntrySpec,
    *,
    workspace_root: Path | None = None,
    repo_root_path: Path | None = None,
) -> None:
    from clusterctl.playbooks_paths import resolve_layout_dir, resolve_repo_base

    if workspace_root is None:
        raise ClusterctlError("configure_entry_env requires workspace_root")

    base = repo_root_path or root
    repo_base = resolve_repo_base(
        repo_spec,
        workspace_root=workspace_root,
        repo_root_path=base,
    )
    env["ANSIBLE_CONFIG"] = str(resolve_repo_ansible_config(repo_base, base))
    env["ANSIBLE_ROLES_PATH"] = str(
        resolve_layout_dir(
            repo_spec,
            workspace_root=workspace_root,
            repo_root_path=base,
        )
    )
    settings = entry_settings(entry)
    env["ANSIBLE_STRATEGY"] = settings.strategy
    env["ANSIBLE_FORKS"] = str(settings.forks)


def configure_boundary_env(
    env: dict[str, str],
    root: Path,
    boundary: str,
    *,
    playbooks: PlaybooksConfig,
    phases: PhasesConfig,
    workspace_root: Path,
) -> str:
    """Configure ansible env for a phase alias or repo/entry ref; returns phase_ref."""
    phase_ref, repo_spec, entry = resolve_boundary_entry(boundary, playbooks, phases)
    configure_entry_env(
        env,
        root,
        repo_spec,
        entry,
        workspace_root=workspace_root,
        repo_root_path=root,
    )
    return phase_ref


def resolve_repo_ansible_config(repo_base: Path, controller_root: Path) -> Path:
    repo_cfg = repo_base / "ansible.cfg"
    if repo_cfg.is_file():
        return repo_cfg.resolve()
    return resolve_ansible_config(controller_root)


def resolve_ansible_roles_path_for_boundary(
    boundary: str,
    *,
    playbooks: PlaybooksConfig,
    phases: PhasesConfig,
    workspace_root: Path,
    repo_root_path: Path,
) -> str:
    from clusterctl.playbooks_paths import resolve_ansible_roles_path_for_spec

    _, repo_spec, _ = resolve_boundary_entry(boundary, playbooks, phases)
    return resolve_ansible_roles_path_for_spec(
        repo_spec,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    )


def summary_lines_for_boundary(
    root: Path,
    boundary: str,
    *,
    playbooks: PlaybooksConfig,
    phases: PhasesConfig,
    workspace_root: Path,
) -> list[str]:
    from clusterctl.playbooks_paths import (
        resolve_ansible_roles_path_for_spec,
        resolve_repo_base,
    )

    phase_ref, repo_spec, entry = resolve_boundary_entry(boundary, playbooks, phases)
    roles_path = resolve_ansible_roles_path_for_spec(
        repo_spec,
        workspace_root=workspace_root,
        repo_root_path=root,
    )
    repo_base = resolve_repo_base(
        repo_spec,
        workspace_root=workspace_root,
        repo_root_path=root,
    )
    settings = entry_settings(entry)
    return [
        "Layout:     playbooks entry (schema v2)",
        f"Config:     {resolve_repo_ansible_config(repo_base, root)}",
        f"Boundary:   {boundary}",
        f"Phase ref:  {phase_ref}",
        f"Playbook:   {entry.file}",
        f"Roles path: {roles_path}",
        f"Strategy:   {settings.strategy}",
        f"Forks:      {settings.forks}",
    ]
