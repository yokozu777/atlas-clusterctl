"""Resolve effective playbooks config for execution (cascade + env overrides)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import PhasesConfig, PlaybookRepoSpec, PlaybooksConfig
from clusterctl.playbooks_repos import (
    ResolvedPlaybookRepo,
    ResolvedPlaybooksRepos,
    empty_resolved_playbooks_repos,
    resolved_playbook_repos_from_config,
)

if TYPE_CHECKING:
    from clusterctl.context import ClusterContext

__all__ = [
    "build_resolved_playbooks_repos",
    "build_role_repos_config",
    "effective_playbooks_config",
    "empty_resolved_playbooks_repos",
    "playbooks_config_from_resolved_repos",
    "playbooks_config_from_role_repo_specs",
    "require_effective_playbooks_context",
    "require_phase_runner",
    "uses_phase_runner",
    "validate_org_baseline_playbooks",
]


def playbooks_config_from_resolved_repos(
    specs: dict[str, ResolvedPlaybookRepo],
) -> PlaybooksConfig:
    repos: dict[str, PlaybookRepoSpec] = {}
    for name, spec in specs.items():
        repos[name] = PlaybookRepoSpec(
            name=name,
            source=spec.source,
            url=spec.url,
            ref=spec.ref,
            path=spec.path,
            path_relative_to=spec.path_relative_to,
            layout=spec.layout,
            shallow=spec.shallow,
            sync=spec.sync,
            readiness_markers=spec.readiness_markers,
            entries={},
        )
    return PlaybooksConfig(repos=repos)


def playbooks_config_from_role_repo_specs(
    specs: dict[str, ResolvedPlaybookRepo],
) -> PlaybooksConfig:
    """Deprecated alias for :func:`playbooks_config_from_resolved_repos`."""
    return playbooks_config_from_resolved_repos(specs)


def build_resolved_playbooks_repos(
    playbooks: PlaybooksConfig,
    *,
    required_repos: frozenset[str] | set[str] | None = None,
) -> ResolvedPlaybooksRepos:
    """Derive resolved playbook-repos view (with PLAYBOOKS_* env overrides)."""
    from clusterctl.playbooks_sync import (
        apply_playbooks_env_overrides,
        playbooks_env_overrides_active,
    )

    env_active = playbooks_env_overrides_active(set(playbooks.repos))
    playbooks_view = apply_playbooks_env_overrides(playbooks)
    specs = resolved_playbook_repos_from_config(playbooks_view)

    if required_repos:
        missing = sorted(set(required_repos) - set(specs))
        if missing:
            raise ClusterctlError(
                "incomplete playbooks configuration — missing repos referenced in phases: "
                + ", ".join(missing)
                + " (define playbooks.<repo> in cluster.yaml cascade)"
            )
        specs = {name: specs[name] for name in sorted(required_repos)}

    return ResolvedPlaybooksRepos(
        specs=specs,
        defaults_loaded=bool(specs),
        cluster_overrides=False,
        env_overrides=env_active,
    )


def build_role_repos_config(
    playbooks: PlaybooksConfig,
    *,
    required_repos: frozenset[str] | set[str] | None = None,
) -> ResolvedPlaybooksRepos:
    """Deprecated alias for :func:`build_resolved_playbooks_repos`."""
    return build_resolved_playbooks_repos(playbooks, required_repos=required_repos)


def effective_playbooks_config(ctx: ClusterContext) -> PlaybooksConfig:
    if ctx.config_v2 is None or ctx.config_v2.playbooks is None:
        raise ClusterctlError(
            "effective playbooks config requires schema v2 playbooks in cluster cascade "
            "(see docs/cluster-config-v2.md)"
        )
    from clusterctl.playbooks_sync import apply_playbooks_env_overrides

    return apply_playbooks_env_overrides(ctx.config_v2.playbooks)


def uses_phase_runner(ctx: ClusterContext) -> bool:
    v2 = ctx.config_v2
    if v2 is None or v2.phases is None or not v2.phases.phases:
        return False
    if v2.playbooks is None or not v2.playbooks.repos:
        return False
    return True


def require_phase_runner(ctx: ClusterContext) -> None:
    """Raise when cluster cascade lacks schema v2 playbooks + phases."""
    if not uses_phase_runner(ctx):
        raise ClusterctlError(
            "schema v2 playbooks + phases required "
            "(see docs/cluster-config-v2.md)"
        )


def require_effective_playbooks_context(
    ctx: ClusterContext,
) -> tuple[PlaybooksConfig, PhasesConfig]:
    """Require v2 phase runner + enabled playbooks; return sync-ready effective config."""
    require_phase_runner(ctx)
    assert ctx.config_v2 is not None
    assert ctx.config_v2.phases is not None
    from clusterctl.playbooks_sync import require_playbooks_sync

    playbooks = require_playbooks_sync(
        ctx.playbooks_enabled,
        effective_playbooks_config(ctx),
    )
    return playbooks, ctx.config_v2.phases


from clusterctl.playbooks_validate import validate_org_baseline_playbooks  # noqa: E402
