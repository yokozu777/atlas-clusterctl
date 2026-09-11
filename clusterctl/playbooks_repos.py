"""Resolved playbook-repo view for mounts, summary, and readiness checks.

Schema v2 SoT remains ``playbooks:`` in the cluster.yaml cascade
(:mod:`clusterctl.playbooks_config`). This module derives a layout-normalized
view used by docker mounts, ANSIBLE_ROLES_PATH resolution, and context summary.

Prefer importing from here (or :mod:`clusterctl.playbooks_resolve` /
:mod:`clusterctl.playbooks_paths`). The legacy module ``clusterctl.role_repos``
is a deprecated re-export shim (soft-compat Phase 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clusterctl.exceptions import ClusterctlError
from clusterctl.paths import repo_root
from clusterctl.pipeline_fixture import ORG_BASELINE_REL, REFERENCE_CLUSTER_ID, REFERENCE_CLUSTER_REL
from clusterctl.playbooks_config import SYNC_VALUES
from clusterctl.playbooks_paths import (
    WORKSPACE_REPOS_DIRNAME,
    layout_dir_ready,
    normalize_layout,
    workspace_materialized_playbook_repo_root,
    workspace_repos_root,
)

ORG_BASELINE_CLUSTER_YAML = str(ORG_BASELINE_REL)
REFERENCE_CLUSTER_YAML = str(REFERENCE_CLUSTER_REL)
ORG_BASELINE_CLUSTER_ID = "default/default"

# Re-export path helpers so callers need one module for the resolved-repos view.
__all__ = [
    "ORG_BASELINE_CLUSTER_ID",
    "ORG_BASELINE_CLUSTER_YAML",
    "REFERENCE_CLUSTER_ID",
    "REFERENCE_CLUSTER_YAML",
    "ResolvedPlaybookRepo",
    "ResolvedPlaybooksRepos",
    "WORKSPACE_REPOS_DIRNAME",
    "ansible_roles_dir_ready",
    "ansible_roles_subpath",
    "empty_resolved_playbooks_repos",
    "org_baseline_cluster_yaml_path",
    "playbook_repos_summary_lines",
    "require_playbook_repos",
    "resolve_ansible_roles_dir_for_spec",
    "resolve_local_repo_path",
    "resolved_playbook_repos_from_config",
    "uses_playbook_repos",
    "validate_resolved_playbook_repo",
    "workspace_materialized_playbook_repo_root",
    "workspace_materialized_repo_root",
    "workspace_repos_root",
]


@dataclass(frozen=True)
class ResolvedPlaybookRepo:
    """Layout-normalized view of one playbook repo (from ``playbooks:`` cascade)."""

    name: str
    source: str
    url: str | None = None
    ref: str | None = None
    path: str | None = None
    path_relative_to: str = "sibling"
    shallow: bool = True
    sync: str = "always"
    layout: str = "roles/"
    readiness_markers: tuple[str, ...] = ()

    def default_sync_for_source(self) -> str:
        return "never" if self.source == "local" else "always"

    @property
    def effective_sync(self) -> str:
        return self.sync if self.sync in SYNC_VALUES else self.default_sync_for_source()


@dataclass(frozen=True)
class ResolvedPlaybooksRepos:
    """Resolved playbook repos for docker / summary (derived from playbooks cascade)."""

    specs: dict[str, ResolvedPlaybookRepo]
    defaults_loaded: bool
    cluster_overrides: bool
    env_overrides: bool

    def is_configured(self) -> bool:
        return bool(self.specs)

    def get(self, logical_name: str) -> ResolvedPlaybookRepo:
        if logical_name not in self.specs:
            raise ClusterctlError(f"playbook repo not configured: {logical_name!r}")
        return self.specs[logical_name]


def empty_resolved_playbooks_repos() -> ResolvedPlaybooksRepos:
    return ResolvedPlaybooksRepos(
        specs={},
        defaults_loaded=False,
        cluster_overrides=False,
        env_overrides=False,
    )


def org_baseline_cluster_yaml_path(root: Path | None = None) -> Path:
    base = (root or repo_root()).resolve()
    return base / ORG_BASELINE_CLUSTER_YAML


def validate_resolved_playbook_repo(spec: ResolvedPlaybookRepo) -> None:
    if spec.source == "git":
        if not spec.url:
            raise ClusterctlError(f"playbooks.{spec.name}: source=git requires url")
        if not spec.ref:
            raise ClusterctlError(f"playbooks.{spec.name}: source=git requires ref")
        if spec.path:
            raise ClusterctlError(f"playbooks.{spec.name}: path is only valid with source=local")
        return

    if spec.source == "local":
        if not spec.path:
            raise ClusterctlError(f"playbooks.{spec.name}: source=local requires path")
        if spec.path_relative_to == "absolute" and not Path(spec.path).is_absolute():
            raise ClusterctlError(
                f"playbooks.{spec.name}: path_relative_to=absolute requires an absolute path"
            )
        if spec.url:
            raise ClusterctlError(f"playbooks.{spec.name}: url is only valid with source=git")


def _playbook_repo_to_resolved(repo_name: str, spec) -> ResolvedPlaybookRepo:
    sync = spec.sync if spec.sync in SYNC_VALUES else spec.default_sync_for_source()
    resolved = ResolvedPlaybookRepo(
        name=repo_name,
        source=spec.source,
        url=spec.url if spec.source == "git" else None,
        ref=spec.ref if spec.source == "git" else None,
        path=spec.path if spec.source == "local" else None,
        path_relative_to=spec.path_relative_to,
        shallow=spec.shallow,
        sync=sync,
        layout=normalize_layout(spec.layout),
        readiness_markers=spec.readiness_markers,
    )
    validate_resolved_playbook_repo(resolved)
    return resolved


def resolved_playbook_repos_from_config(playbooks) -> dict[str, ResolvedPlaybookRepo]:
    """Build resolved-repo view from merged schema v2 ``playbooks``."""
    from clusterctl.playbooks_config import PlaybooksConfig

    if not isinstance(playbooks, PlaybooksConfig):
        raise ClusterctlError(
            "resolved_playbook_repos_from_config expects PlaybooksConfig, "
            f"got {type(playbooks).__name__}"
        )
    return {
        repo_name: _playbook_repo_to_resolved(repo_name, pb_spec)
        for repo_name, pb_spec in playbooks.repos.items()
    }


def workspace_materialized_repo_root(workspace_root: Path, logical_name: str) -> Path:
    """Alias for :func:`workspace_materialized_playbook_repo_root` with name validation."""
    from clusterctl.playbooks_config import _validate_repo_name

    _validate_repo_name(logical_name)
    return workspace_materialized_playbook_repo_root(workspace_root, logical_name)


def ansible_roles_subpath(spec: ResolvedPlaybookRepo) -> str:
    return normalize_layout(spec.layout)


def resolve_local_repo_path(spec: ResolvedPlaybookRepo, *, repo_root_path: Path) -> Path:
    validate_resolved_playbook_repo(spec)
    if spec.source != "local" or not spec.path:
        raise ClusterctlError(f"resolve_local_repo_path requires source=local: {spec.name}")

    raw = Path(spec.path)
    if spec.path_relative_to == "absolute":
        return raw.resolve()
    if spec.path_relative_to == "repo_root":
        return (repo_root_path / raw).resolve()
    if spec.path_relative_to == "sibling":
        return (repo_root_path.parent / raw).resolve()

    raise ClusterctlError(
        f"playbooks.{spec.name}: unsupported path_relative_to={spec.path_relative_to!r}"
    )


def resolve_ansible_roles_dir_for_spec(
    spec: ResolvedPlaybookRepo,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> Path:
    subpath = ansible_roles_subpath(spec)
    if spec.source == "git":
        base = workspace_materialized_repo_root(workspace_root, spec.name)
    else:
        base = resolve_local_repo_path(spec, repo_root_path=repo_root_path)
    return (base / subpath).resolve() if subpath else base.resolve()


def uses_playbook_repos(
    playbooks_enabled: bool,
    playbook_repos: ResolvedPlaybooksRepos | None,
) -> bool:
    return bool(playbooks_enabled and playbook_repos and playbook_repos.is_configured())


def require_playbook_repos(
    playbooks_enabled: bool,
    playbook_repos: ResolvedPlaybooksRepos | None,
) -> ResolvedPlaybooksRepos:
    if not uses_playbook_repos(playbooks_enabled, playbook_repos):
        raise ClusterctlError(
            "playbooks resolver required — define playbooks: in cluster.yaml "
            "(omit playbooks_enabled to infer; use false to disable — "
            "see docs/cluster-config-v2.md / ADR 006)"
        )
    assert playbook_repos is not None
    return playbook_repos


def ansible_roles_dir_ready(roles_dir: Path, spec: ResolvedPlaybookRepo) -> bool:
    return layout_dir_ready(roles_dir, markers=spec.readiness_markers)


def playbook_repos_summary_lines(
    config: ResolvedPlaybooksRepos,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> list[str]:
    if not config.is_configured():
        return ["Playbooks:  (not configured)"]

    lines = ["Playbooks (workspace/local resolver):"]
    for name in sorted(config.specs):
        spec = config.specs[name]
        roles_dir = resolve_ansible_roles_dir_for_spec(
            spec,
            workspace_root=workspace_root,
            repo_root_path=repo_root_path,
        )
        if spec.source == "git":
            lines.append(
                f"  {name}: git {spec.url} @ {spec.ref} → {roles_dir} (sync={spec.effective_sync})"
            )
        else:
            local_root = resolve_local_repo_path(spec, repo_root_path=repo_root_path)
            lines.append(
                f"  {name}: local {local_root} → ANSIBLE_ROLES_PATH={roles_dir} (direct, no copy)"
            )
    return lines
