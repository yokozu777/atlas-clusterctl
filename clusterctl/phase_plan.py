"""Execution plan for schema v2 phases (replaces profiles/pipeline for v2 clusters)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from clusterctl.cluster_vars_loader import load_cluster_vars_from_paths
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.phase_filter import PhaseFilterContext, PhaseFilterResult, filter_phases
from clusterctl.playbooks_config import (
    InvocationSpec,
    PhasesConfig,
    PlaybookEntrySpec,
    PlaybookRepoSpec,
    PlaybooksConfig,
    parse_phase_ref,
    resolve_phase_alias,
)
from clusterctl.playbooks_resolve import effective_playbooks_config, require_phase_runner


@dataclass(frozen=True)
class PhaseInvocationPlan:
    phase_ref: str
    repo_name: str
    entry_name: str
    repo_base: str
    playbook_file: str
    invocation_index: int
    invocation: InvocationSpec


@dataclass(frozen=True)
class PhaseStagePlan:
    phase_ref: str
    repo_name: str
    entry_name: str
    playbook_file: str
    repo_base: str
    git_ssh: bool
    invocations: tuple[PhaseInvocationPlan, ...]


@dataclass(frozen=True)
class PhasePlanSummary:
    cluster_id: str
    workspace_id: str
    execution: str
    execution_source: str
    phases: tuple[str, ...]
    invocation_count: int
    inventory: str
    schema_version: int


@dataclass(frozen=True)
class PhaseExecutionPlan:
    summary: PhasePlanSummary
    stages: tuple[PhaseStagePlan, ...]
    filter_skipped: tuple[tuple[str, str], ...]


def resolve_play_phase_target(*, playbook: str, phase: str | None) -> str:
    """Resolve ``play`` positional vs optional ``--phase`` (must agree when both set)."""
    target = str(playbook or "").strip()
    if not target:
        raise ClusterctlError("playbook/phase name is empty")
    if phase is None:
        return target
    explicit = str(phase).strip()
    if not explicit:
        raise ClusterctlError("--phase is empty")
    if explicit != target:
        raise ClusterctlError(
            f"conflicting play targets: positional {target!r} and --phase {explicit!r} "
            "(omit --phase, or pass the same value)"
        )
    return explicit


def apply_play_cli_overrides(
    plan: PhaseExecutionPlan,
    *,
    tags: str = "all",
    limit: str | None = None,
    extra_vars: tuple[str, ...] = (),
    root_ssh: bool = False,
    git_ssh: bool = False,
) -> PhaseExecutionPlan:
    """Historical collapse helper — **DO NOT use from CLI / new call sites**.

    Pre-ADR 009 behaviour: ``-e`` / ``--tags`` / ``--limit`` / ``--root-ssh``
    alone each collapse the phase to **one** custom invocation.

    Production ``run`` / ``stage`` / ``play`` (ADR 009 Phase 2+) call
    ``clusterctl.run_overrides.apply_run_cli_overrides`` instead, where ``-e``
    alone is ``merge_e`` (no collapse). This function remains only for unit
    tests that lock the historical contract (`tests/test_play_cli_phase2.py`).
    """
    from dataclasses import replace

    if not plan.stages:
        raise ClusterctlError("play plan has no stages")
    stage = plan.stages[0]
    tags_text = tags or "all"
    extra = tuple(extra_vars)
    collapse = tags_text != "all" or bool(limit) or bool(extra) or root_ssh
    if collapse:
        invocation = InvocationSpec(
            tags=tags_text,
            limit=limit,
            root_ssh=root_ssh,
            extra_e=extra,
        )
        stage = PhaseStagePlan(
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
        return PhaseExecutionPlan(
            summary=replace(
                plan.summary,
                phases=(stage.phase_ref,),
                invocation_count=1,
            ),
            stages=(stage,),
            filter_skipped=plan.filter_skipped,
        )
    if git_ssh and not stage.git_ssh:
        return replace(plan, stages=(replace(stage, git_ssh=True),))
    return plan


def ensure_run_plan_nonempty(plan: PhaseExecutionPlan) -> PhaseExecutionPlan:
    """Fail ``run`` when phase/when filters left no stages (avoid silent success)."""
    if plan.stages:
        return plan
    skipped_hint = ""
    if plan.filter_skipped:
        names = ", ".join(ref for ref, _ in plan.filter_skipped[:8])
        more = ", …" if len(plan.filter_skipped) > 8 else ""
        skipped_hint = f"; when-filter skipped: {names}{more}"
    raise ClusterctlError(
        "execution plan is empty after phase/when filters"
        f"{skipped_hint} (check --phases / inventory when:)"
    )


def resolve_phase_boundary(
    name: str,
    phases: PhasesConfig,
) -> str:
    text = str(name).strip()
    if not text:
        raise ClusterctlError("phase boundary name is empty")
    if "/" in text:
        parse_phase_ref(text)
        return text
    try:
        return resolve_phase_alias(text, phases.phase_aliases)
    except ClusterctlError:
        available = (
            ", ".join(sorted(phases.phase_aliases))
            if phases.phase_aliases
            else "(none — define short names inline in phases: — ADR 007)"
        )
        raise ClusterctlError(
            f"unknown phase boundary {name!r} — use repo/entry or a phase alias "
            f"({available})"
        ) from None


def _phase_list_available(phase_refs: tuple[str, ...]) -> str:
    return ", ".join(phase_refs) if phase_refs else "(none)"


def slice_phase_refs(
    phase_refs: tuple[str, ...],
    *,
    from_phase: str | None = None,
    to_phase: str | None = None,
    phases: PhasesConfig,
) -> tuple[str, ...]:
    if not phase_refs:
        return ()
    start = 0
    end = len(phase_refs) - 1
    if from_phase is not None:
        boundary = resolve_phase_boundary(from_phase, phases)
        try:
            start = phase_refs.index(boundary)
        except ValueError as exc:
            raise ClusterctlError(
                f"phase boundary {from_phase!r} ({boundary!r}) not in effective phase list "
                f"(available: {_phase_list_available(phase_refs)})"
            ) from exc
    if to_phase is not None:
        boundary = resolve_phase_boundary(to_phase, phases)
        try:
            end = phase_refs.index(boundary)
        except ValueError as exc:
            raise ClusterctlError(
                f"phase boundary {to_phase!r} ({boundary!r}) not in effective phase list "
                f"(available: {_phase_list_available(phase_refs)})"
            ) from exc
    if start > end:
        raise ClusterctlError(
            f"invalid phase range: from {from_phase!r} is after to {to_phase!r}"
        )
    return phase_refs[start : end + 1]


def select_explicit_phase_refs(
    phase_refs: tuple[str, ...],
    *,
    only_phases: tuple[str, ...],
    phases: PhasesConfig,
) -> tuple[str, ...]:
    """Pick an explicit set of phases; order follows leaf ``phases:`` (ADR 008 Phase 3)."""
    if not only_phases:
        raise ClusterctlError("phases list is empty")
    wanted: set[str] = set()
    for name in only_phases:
        ref = resolve_phase_boundary(name, phases)
        if ref not in phase_refs:
            raise ClusterctlError(
                f"phase {name!r} ({ref!r}) not in effective phase list "
                f"(available: {_phase_list_available(phase_refs)})"
            )
        if ref in wanted:
            raise ClusterctlError(
                f"duplicate phase {name!r} ({ref!r}) in --phases list"
            )
        wanted.add(ref)
    return tuple(ref for ref in phase_refs if ref in wanted)


def _repo_base_label(
    repo_spec: PlaybookRepoSpec,
    *,
    workspace_root,
    repo_root_path,
) -> str:
    from clusterctl.playbooks_paths import resolve_repo_base

    return str(
        resolve_repo_base(
            repo_spec,
            workspace_root=workspace_root,
            repo_root_path=repo_root_path,
        ).resolve()
    )


def build_phase_stage_plans(
    ctx: ClusterContext,
    phase_refs: tuple[str, ...],
    playbooks: PlaybooksConfig,
) -> tuple[PhaseStagePlan, ...]:
    stages: list[PhaseStagePlan] = []
    for phase_ref in phase_refs:
        repo_spec, entry = playbooks.resolve_entry(phase_ref)
        repo_name, entry_name = parse_phase_ref(phase_ref)
        repo_base = _repo_base_label(
            repo_spec,
            workspace_root=ctx.workspace_root,
            repo_root_path=ctx.repo_root,
        )
        inv_plans = tuple(
            PhaseInvocationPlan(
                phase_ref=phase_ref,
                repo_name=repo_name,
                entry_name=entry_name,
                repo_base=repo_base,
                playbook_file=entry.file,
                invocation_index=index,
                invocation=invocation,
            )
            for index, invocation in enumerate(entry.invocations, start=1)
        )
        stages.append(
            PhaseStagePlan(
                phase_ref=phase_ref,
                repo_name=repo_name,
                entry_name=entry_name,
                playbook_file=entry.file,
                repo_base=repo_base,
                git_ssh=entry.git_ssh,
                invocations=inv_plans,
            )
        )
    return tuple(stages)


def resolve_phase_execution_plan(
    ctx: ClusterContext,
    *,
    from_phase: str | None = None,
    to_phase: str | None = None,
    only_phases: tuple[str, ...] | None = None,
) -> PhaseExecutionPlan:
    """Build the effective plan from ``phases:`` (+ inventory ``when`` filters).

    ADR 005: YAML ``stacks:`` is rejected at load; not applied here.
    ADR 008: ``only_phases`` selects an explicit set (leaf order); mutually
    exclusive with ``from_phase``/``to_phase``.
    """
    require_phase_runner(ctx)

    assert ctx.config_v2 is not None
    assert ctx.config_v2.phases is not None
    phases = ctx.config_v2.phases
    playbooks = effective_playbooks_config(ctx)

    all_refs = phases.phases
    if only_phases is not None:
        if from_phase is not None or to_phase is not None:
            raise ClusterctlError(
                "only_phases cannot be combined with from_phase/to_phase"
            )
        sliced = select_explicit_phase_refs(
            all_refs,
            only_phases=only_phases,
            phases=phases,
        )
    else:
        sliced = slice_phase_refs(
            all_refs,
            from_phase=from_phase,
            to_phase=to_phase,
            phases=phases,
        )

    filter_ctx = PhaseFilterContext.from_inventory(
        ctx.inventory,
        load_cluster_vars_from_paths(ctx.group_var_files),
    )
    filter_result: PhaseFilterResult = filter_phases(sliced, playbooks, filter_ctx)

    stages = build_phase_stage_plans(ctx, filter_result.included, playbooks)
    invocation_count = sum(len(stage.invocations) for stage in stages)

    summary = PhasePlanSummary(
        cluster_id=ctx.cluster_id,
        workspace_id=ctx.workspace_id,
        execution=ctx.execution.summary(),
        execution_source=ctx.execution_source,
        phases=filter_result.included,
        invocation_count=invocation_count,
        inventory=str(ctx.inventory),
        schema_version=ctx.schema_version,
    )
    return PhaseExecutionPlan(
        summary=summary,
        stages=stages,
        filter_skipped=filter_result.skipped,
    )


def format_phase_plan_text(
    plan: PhaseExecutionPlan,
    *,
    verbose: bool = False,
) -> str:
    summary = plan.summary
    lines = [
        f"Schema:      v{summary.schema_version} (phases)",
        f"Cluster:     {summary.cluster_id}",
        f"Execution:   {summary.execution} ({summary.execution_source})",
        f"Workspace:   {summary.workspace_id}",
        f"Inventory:   {summary.inventory}",
        f"Phases:      {len(summary.phases)}",
        f"Invocations: {summary.invocation_count}",
        "",
    ]
    for index, stage in enumerate(plan.stages, start=1):
        lines.append(
            f"[{index}/{len(plan.stages)}] {stage.phase_ref} "
            f"({stage.playbook_file}, {len(stage.invocations)} invocations)"
        )
        lines.append(f"      repo: {stage.repo_base}")
        if verbose:
            for inv in stage.invocations:
                limit = f" limit={inv.invocation.limit}" if inv.invocation.limit else ""
                root = " root_ssh" if inv.invocation.root_ssh else ""
                lines.append(
                    f"      {inv.invocation_index:3d}. tags={inv.invocation.tags}{limit}{root}"
                )
        lines.append("")
    if plan.filter_skipped:
        lines.append("When filter skipped:")
        for phase_ref, reason in plan.filter_skipped:
            lines.append(f"  - {phase_ref}: {reason}")
    return "\n".join(lines).rstrip() + "\n"


def format_phase_plan_json(plan: PhaseExecutionPlan) -> str:
    payload = {
        **asdict(plan.summary),
        "filter_skipped": [
            {"phase_ref": phase_ref, "reason": reason}
            for phase_ref, reason in plan.filter_skipped
        ],
        "stage_details": [
            {
                "phase_ref": stage.phase_ref,
                "repo_name": stage.repo_name,
                "entry_name": stage.entry_name,
                "playbook_file": stage.playbook_file,
                "repo_base": stage.repo_base,
                "git_ssh": stage.git_ssh,
                "invocation_count": len(stage.invocations),
                "invocations": [
                    {
                        "tags": inv.invocation.tags,
                        "root_ssh": inv.invocation.root_ssh,
                        "extra_e": list(inv.invocation.extra_e),
                        # Omit null limit: Jenkins readJSON turns JSON null into
                        # JSONNull, which stringifies to "null" and breaks --limit.
                        **({"limit": inv.invocation.limit} if inv.invocation.limit else {}),
                    }
                    for inv in stage.invocations
                ],
            }
            for stage in plan.stages
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
