"""Pipeline stages — derived from org baseline cluster.yaml (schema v2)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import load_org_baseline_cluster_config
from clusterctl.playbooks_config import parse_phase_ref, stage_name_for_phase_ref


@dataclass(frozen=True)
class PlaybookInvocation:
    tags: str
    limit: str | None = None
    extra_e: tuple[str, ...] = ()
    root_ssh: bool = False


@dataclass(frozen=True)
class StageDefinition:
    name: str
    phase_ref: str
    playbook: str
    invocations: tuple[PlaybookInvocation, ...]
    git_ssh: bool = False


@dataclass(frozen=True)
class _PipelineIndexes:
    stages: tuple[StageDefinition, ...]
    phase_by_alias: dict[str, StageDefinition]
    run_order: list[str]


_indexes: _PipelineIndexes | None = None


def stages_from_org_baseline(root: Path | None = None) -> tuple[StageDefinition, ...]:
    cfg = load_org_baseline_cluster_config(root)
    if cfg.playbooks is None or cfg.phases is None:
        raise ClusterctlError("org baseline missing playbooks or phases")

    aliases = cfg.phases.phase_aliases
    stages: list[StageDefinition] = []

    for phase_ref in cfg.phases.phases:
        stage_name = stage_name_for_phase_ref(phase_ref, aliases)
        repo_name, entry_id = parse_phase_ref(phase_ref)
        repo = cfg.playbooks.repos.get(repo_name)
        if repo is None:
            raise ClusterctlError(f"org baseline missing playbooks.{repo_name}")
        entry = repo.entries.get(entry_id)
        if entry is None:
            raise ClusterctlError(f"org baseline missing playbooks.{repo_name}.entries.{entry_id}")

        invocations = tuple(
            PlaybookInvocation(
                tags=inv.tags,
                limit=inv.limit,
                extra_e=inv.extra_e,
                root_ssh=inv.root_ssh,
            )
            for inv in entry.invocations
        )
        stages.append(
            StageDefinition(
                name=stage_name,
                phase_ref=phase_ref,
                playbook=entry.file,
                invocations=invocations,
                git_ssh=entry.git_ssh,
            )
        )
    return tuple(stages)


@lru_cache(maxsize=1)
def _load_pipeline_cached() -> tuple[StageDefinition, ...]:
    return stages_from_org_baseline(None)


def _build_indexes(stages: tuple[StageDefinition, ...]) -> _PipelineIndexes:
    return _PipelineIndexes(
        stages=stages,
        phase_by_alias={stage.name: stage for stage in stages},
        run_order=[stage.name for stage in stages],
    )


def _get_indexes() -> _PipelineIndexes:
    global _indexes
    if _indexes is None:
        _indexes = _build_indexes(_load_pipeline_cached())
    return _indexes


def reset_pipeline_cache_for_tests() -> None:
    """Clear cached org-baseline pipeline indexes (unit tests only)."""
    global _indexes
    _load_pipeline_cached.cache_clear()
    _indexes = None


def load_pipeline(root: Path | None = None) -> tuple[StageDefinition, ...]:
    if root is not None:
        return stages_from_org_baseline(root)
    return _get_indexes().stages


def stages() -> tuple[StageDefinition, ...]:
    return load_pipeline()


def __getattr__(name: str):
    if name == "STAGES":
        return _get_indexes().stages
    if name in ("PHASE_BY_ALIAS",):
        return _get_indexes().phase_by_alias
    if name == "RUN_ORDER":
        return _get_indexes().run_order
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
