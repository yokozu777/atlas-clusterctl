"""Discover playbook repo requirements.yml files for bootstrap galaxy install."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from clusterctl.playbooks_config import PhasesConfig, PlaybooksConfig, parse_phase_ref
from clusterctl.playbooks_paths import resolve_repo_base

PLAYBOOK_REQUIREMENTS_FILENAME = "requirements.yml"
PLAYBOOK_REQUIREMENTS_ENV = "PLAYBOOK_REQUIREMENTS_FILES"
_PATH_ENV_SEPARATOR = ":"


def _ordered_playbook_repo_names(
    playbooks: PlaybooksConfig,
    phases: PhasesConfig | None,
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    if phases is not None:
        for phase_ref in phases.phases:
            repo_name, _entry_id = parse_phase_ref(phase_ref)
            if repo_name not in playbooks.repos or repo_name in seen:
                continue
            ordered.append(repo_name)
            seen.add(repo_name)

    for repo_name in sorted(playbooks.repos):
        if repo_name not in seen:
            ordered.append(repo_name)
            seen.add(repo_name)

    return ordered


def discover_playbook_requirements_files(
    playbooks: PlaybooksConfig,
    phases: PhasesConfig | None,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> list[Path]:
    """Return existing requirements.yml paths from effective playbook repos (phase order)."""
    files: list[Path] = []
    seen_paths: set[Path] = set()

    for repo_name in _ordered_playbook_repo_names(playbooks, phases):
        spec = playbooks.repos[repo_name]
        base = resolve_repo_base(
            spec,
            workspace_root=workspace_root,
            repo_root_path=repo_root_path,
        )
        req = (base / PLAYBOOK_REQUIREMENTS_FILENAME).resolve()
        if not req.is_file() or req in seen_paths:
            continue
        files.append(req)
        seen_paths.add(req)

    return files


def playbook_requirements_env_value(paths: list[Path]) -> str:
    """Colon-separated absolute paths for bootstrap.sh (Linux controller paths)."""
    return _PATH_ENV_SEPARATOR.join(str(path.resolve()) for path in paths)


def playbook_requirements_from_env(env: Mapping[str, str]) -> list[Path]:
    raw = env.get(PLAYBOOK_REQUIREMENTS_ENV, "").strip()
    if not raw:
        return []
    return [Path(part).resolve() for part in raw.split(_PATH_ENV_SEPARATOR) if part]
