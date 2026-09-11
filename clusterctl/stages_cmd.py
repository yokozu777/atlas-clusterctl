"""`./cluster stages` — org baseline or cluster-effective phase listing."""

from __future__ import annotations

import json
import sys

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.phase_plan import (
    PhaseExecutionPlan,
    format_phase_plan_json,
    resolve_phase_execution_plan,
)
from clusterctl.pipeline import PHASE_BY_ALIAS, RUN_ORDER, load_pipeline
from clusterctl.playbooks_config import stage_name_for_phase_ref
from clusterctl.playbooks_resolve import require_phase_runner


def format_org_baseline_stages_text() -> str:
    lines: list[str] = []
    for name in RUN_ORDER:
        stage = PHASE_BY_ALIAS[name]
        inv_count = len(stage.invocations)
        lines.append(
            f"{name:12}  {stage.phase_ref:32}  "
            f"{stage.playbook}  ({inv_count} invocations)"
        )
    return "\n".join(lines) + "\n"


def format_cluster_stages_text(plan: PhaseExecutionPlan, *, aliases: dict[str, str]) -> str:
    total = len(plan.stages)
    lines = [
        f"Cluster:     {plan.summary.cluster_id}",
        f"Workspace:   {plan.summary.workspace_id}",
        f"Phases:      {len(plan.summary.phases)} effective "
        f"({plan.summary.invocation_count} invocations)",
        "",
    ]
    for index, stage in enumerate(plan.stages, start=1):
        alias = stage_name_for_phase_ref(stage.phase_ref, aliases)
        lines.append(
            f"{alias:12}  {stage.phase_ref:32}  "
            f"{stage.playbook_file}  ({len(stage.invocations)} invocations)"
        )
        lines.append(f"{'':12}  [{index}/{total}] repo: {stage.repo_base}")
    if plan.filter_skipped:
        lines.append("When filter skipped:")
        for phase_ref, reason in plan.filter_skipped:
            lines.append(f"  - {phase_ref}: {reason}")
    return "\n".join(lines).rstrip() + "\n"


def format_org_baseline_stages_json() -> str:
    payload = {
        "baseline": True,
        "stages": [
            {
                "alias": name,
                "phase_ref": PHASE_BY_ALIAS[name].phase_ref,
                "playbook": PHASE_BY_ALIAS[name].playbook,
                "invocation_count": len(PHASE_BY_ALIAS[name].invocations),
            }
            for name in RUN_ORDER
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def format_cluster_stages_json(plan: PhaseExecutionPlan, *, aliases: dict[str, str]) -> str:
    plan_payload = json.loads(format_phase_plan_json(plan))
    for stage, detail in zip(plan.stages, plan_payload.get("stage_details", [])):
        detail["alias"] = stage_name_for_phase_ref(stage.phase_ref, aliases)
    plan_payload["baseline"] = False
    return json.dumps(plan_payload, indent=2, ensure_ascii=False) + "\n"


def cmd_stages(
    ctx: ClusterContext | None = None,
    *,
    baseline: bool = False,
    as_json: bool = False,
) -> int:
    if baseline or ctx is None:
        print(
            "clusterctl: ./cluster stages --baseline lists org baseline only — "
            "omit --baseline (or ./cluster stages --cluster <id>) for effective cluster phases",
            file=sys.stderr,
        )
        if as_json:
            print(format_org_baseline_stages_json(), end="")
        else:
            print(format_org_baseline_stages_text(), end="")
        return 0

    require_phase_runner(ctx)
    assert ctx.config_v2 is not None
    assert ctx.config_v2.phases is not None

    try:
        plan = resolve_phase_execution_plan(ctx)
    except ClusterctlError as exc:
        print(f"cluster: {exc}", file=sys.stderr)
        return 1

    if not plan.stages:
        print(
            "clusterctl: effective stage list is empty after when filters — "
            "see ./cluster plan --cluster "
            f"{ctx.cluster_id}",
            file=sys.stderr,
        )
        return 1

    aliases = ctx.config_v2.phases.phase_aliases
    if as_json:
        print(format_cluster_stages_json(plan, aliases=aliases), end="")
    else:
        print(format_cluster_stages_text(plan, aliases=aliases), end="")
    return 0


def cmd_stages_baseline_from_root(root) -> int:
    """Org baseline listing using an explicit repo root (tests)."""
    from clusterctl.pipeline import reset_pipeline_cache_for_tests

    reset_pipeline_cache_for_tests()
    load_pipeline(root)
    print(
        "clusterctl: ./cluster stages --baseline lists org baseline only — "
        "omit --baseline (or ./cluster stages --cluster <id>) for effective cluster phases",
        file=sys.stderr,
    )
    print(format_org_baseline_stages_text(), end="")
    return 0
