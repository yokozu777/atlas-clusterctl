"""ADR 009 — classify and apply ``./cluster run`` CLI overrides.

Phase 0 locked ``classify_run_overrides``. Phase 1 wires ``apply_run_cli_overrides``
into ``run`` (argparse + execution). ``stage`` / ``play`` aliases come in Phase 2.
Post-cleanup A1: ``resolve_run_limit`` unifies CLI ``--limit`` / env ``LIMIT`` for
all execute verbs.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from enum import Enum

from clusterctl.exceptions import ClusterctlError
from clusterctl.phase_plan import (
    PhaseExecutionPlan,
    PhaseInvocationPlan,
    PhaseStagePlan,
)
from clusterctl.playbooks_config import InvocationSpec


class RunOverrideMode(str, Enum):
    """How ``run`` applies CLI overrides to the selected phase window."""

    CATALOG = "catalog"
    """No selective overrides and no ``-e`` — YAML invocations unchanged."""

    MERGE_EXTRA = "merge_e"
    """Only ``-e`` / ``--extra-vars`` — append to every catalog invocation (no collapse)."""

    COLLAPSE = "collapse"
    """``--tags`` / ``--limit`` / ``--root-ssh`` on a single phase — one invocation."""

    ERROR_MULTI_PHASE_SELECTIVE = "error_multi_phase_selective"
    """Selective overrides with more than one phase — reject before ansible."""


def normalize_run_tags(tags: str | None) -> str:
    """Empty / whitespace ``--tags`` means ``all`` (no selective tag filter)."""
    text = (tags or "all").strip()
    return text if text else "all"


def normalize_run_extra_vars(extra_vars: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    """Drop blank ``-e`` tokens; preserve order."""
    if not extra_vars:
        return ()
    return tuple(str(item).strip() for item in extra_vars if str(item).strip())


def resolve_run_limit(
    cli_limit: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve ansible ``--limit`` for ADR 009 classify / apply.

    CLI ``--limit`` wins. Otherwise non-empty env ``LIMIT`` (for ``run``).
    Whitespace-only is treated as unset.
    """
    text = (cli_limit or "").strip()
    if text:
        return text
    source = os.environ if env is None else env
    env_text = str(source.get("LIMIT", "") or "").strip()
    return env_text or None


def classify_run_overrides(
    *,
    phase_count: int,
    tags: str | None = None,
    limit: str | None = None,
    extra_vars: tuple[str, ...] = (),
    root_ssh: bool = False,
) -> RunOverrideMode:
    """Return override mode for a resolved phase window.

    ``phase_count`` is the number of phases after ADR 008 ``--phases`` resolve.
    ``phase_count < 1`` is a plan-resolve concern (caller should not reach here).

    ``--git-ssh`` alone does not affect this classifier (flag-only on the stage).
    """
    if phase_count < 1:
        raise ValueError("phase_count must be >= 1 (empty plan is resolved earlier)")

    tags_text = normalize_run_tags(tags)
    has_tags = tags_text != "all"
    has_limit = bool(limit and str(limit).strip())
    has_extra = bool(normalize_run_extra_vars(extra_vars))
    # Parity with historical ``apply_play_cli_overrides`` selective triggers
    # (tags / limit / root_ssh) — but ``-e`` alone is merge_e, not collapse.
    has_selective = has_tags or has_limit or bool(root_ssh)

    if has_selective and phase_count > 1:
        return RunOverrideMode.ERROR_MULTI_PHASE_SELECTIVE
    if has_selective:
        return RunOverrideMode.COLLAPSE
    if has_extra:
        return RunOverrideMode.MERGE_EXTRA
    return RunOverrideMode.CATALOG


def _collapse_stage(
    stage: PhaseStagePlan,
    *,
    tags: str,
    limit: str | None,
    extra: tuple[str, ...],
    root_ssh: bool,
    git_ssh: bool,
) -> PhaseStagePlan:
    invocation = InvocationSpec(
        tags=tags,
        limit=limit if (limit and str(limit).strip()) else None,
        root_ssh=root_ssh,
        extra_e=extra,
    )
    return PhaseStagePlan(
        phase_ref=stage.phase_ref,
        repo_name=stage.repo_name,
        entry_name=stage.entry_name,
        playbook_file=stage.playbook_file,
        repo_base=stage.repo_base,
        git_ssh=bool(git_ssh or stage.git_ssh),
        invocations=(
            PhaseInvocationPlan(
                phase_ref=stage.phase_ref,
                repo_name=stage.repo_name,
                entry_name=stage.entry_name,
                repo_base=stage.repo_base,
                playbook_file=stage.playbook_file,
                invocation_index=1,
                invocation=invocation,
            ),
        ),
    )


def _merge_extra_into_phase_plan(
    stage: PhaseStagePlan,
    *,
    extra: tuple[str, ...],
    git_ssh: bool,
) -> PhaseStagePlan:
    if not extra and not (git_ssh and not stage.git_ssh):
        return stage
    new_invocations: list[PhaseInvocationPlan] = []
    for index, inv_plan in enumerate(stage.invocations, start=1):
        inv = inv_plan.invocation
        if extra:
            inv = replace(inv, extra_e=tuple(inv.extra_e) + extra)
        new_invocations.append(
            replace(
                inv_plan,
                invocation_index=index,
                invocation=inv,
            )
        )
    return replace(
        stage,
        git_ssh=bool(git_ssh or stage.git_ssh),
        invocations=tuple(new_invocations),
    )


def _with_git_ssh(stage: PhaseStagePlan, *, git_ssh: bool) -> PhaseStagePlan:
    if not git_ssh or stage.git_ssh:
        return stage
    return replace(stage, git_ssh=True)


def apply_run_cli_overrides(
    plan: PhaseExecutionPlan,
    *,
    tags: str | None = "all",
    limit: str | None = None,
    extra_vars: tuple[str, ...] | list[str] | None = (),
    root_ssh: bool = False,
    git_ssh: bool = False,
) -> PhaseExecutionPlan:
    """Apply ADR 009 override policy to a non-empty execution plan.

    Raises:
        ClusterctlError: empty plan, or selective overrides with multiple phases.
    """
    if not plan.stages:
        raise ClusterctlError("run plan has no stages")

    tags_text = normalize_run_tags(tags)
    limit_text = str(limit).strip() if limit and str(limit).strip() else None
    extra = normalize_run_extra_vars(extra_vars)
    mode = classify_run_overrides(
        phase_count=len(plan.stages),
        tags=tags_text,
        limit=limit_text,
        extra_vars=extra,
        root_ssh=root_ssh,
    )

    if mode is RunOverrideMode.ERROR_MULTI_PHASE_SELECTIVE:
        names = ", ".join(plan.summary.phases)
        raise ClusterctlError(
            "selective run overrides (--tags / --limit / --root-ssh) require a single "
            f"phase (got {len(plan.stages)}: {names}). "
            "Narrow with --phases NAME, or pass only -e / --extra-vars for multi-phase "
            "runs (ADR 009)."
        )

    if mode is RunOverrideMode.COLLAPSE:
        stage = _collapse_stage(
            plan.stages[0],
            tags=tags_text,
            limit=limit_text,
            extra=extra,
            root_ssh=root_ssh,
            git_ssh=git_ssh,
        )
        return PhaseExecutionPlan(
            summary=replace(
                plan.summary,
                phases=(stage.phase_ref,),
                invocation_count=1,
            ),
            stages=(stage,),
            filter_skipped=plan.filter_skipped,
        )

    if mode is RunOverrideMode.MERGE_EXTRA:
        stages = tuple(
            _merge_extra_into_phase_plan(stage, extra=extra, git_ssh=git_ssh)
            for stage in plan.stages
        )
        invocation_count = sum(len(stage.invocations) for stage in stages)
        return PhaseExecutionPlan(
            summary=replace(plan.summary, invocation_count=invocation_count),
            stages=stages,
            filter_skipped=plan.filter_skipped,
        )

    # catalog — optional git_ssh flip only
    if not git_ssh:
        return plan
    stages = tuple(_with_git_ssh(stage, git_ssh=True) for stage in plan.stages)
    if stages == plan.stages:
        return plan
    return replace(plan, stages=stages)
