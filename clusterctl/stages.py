"""Pipeline stages — derived from org baseline cluster.yaml (schema v2)."""

from __future__ import annotations

from clusterctl.pipeline import PlaybookInvocation, StageDefinition, load_pipeline

__all__ = [
    "PlaybookInvocation",
    "StageDefinition",
    "STAGES",
    "PHASE_BY_ALIAS",
    "RUN_ORDER",
    "load_pipeline",
]

_LAZY_EXPORTS = frozenset(
    {
        "STAGES",
        "PHASE_BY_ALIAS",
        "RUN_ORDER",
        "load_pipeline",
        "PlaybookInvocation",
        "StageDefinition",
    }
)


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        from clusterctl import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
