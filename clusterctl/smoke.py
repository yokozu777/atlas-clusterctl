"""Multi-cluster smoke — validate + plan for all clusters."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.paths import list_deployable_cluster_ids, repo_root
from clusterctl.phase_plan import resolve_phase_execution_plan
from clusterctl.playbooks_resolve import require_phase_runner
from clusterctl.validate import (
    ValidationReport,
    format_report_text,
    report_cluster_load_failure,
    validate_cluster,
    validate_repo,
)


@dataclass(frozen=True)
class SmokeResult:
    cluster_id: str
    validate_ok: bool
    plan_ok: bool
    phases: tuple[str, ...] = ()
    invocations: int = 0
    skipped_phases: tuple[str, ...] = ()
    error: str | None = None


def run_cluster_smoke(ctx: ClusterContext) -> tuple[ValidationReport, SmokeResult]:
    report = validate_cluster(ctx, root=ctx.repo_root)
    if not report.ok:
        return report, SmokeResult(
            cluster_id=ctx.cluster_id,
            validate_ok=False,
            plan_ok=False,
            error="validation failed",
        )

    try:
        require_phase_runner(ctx)
        plan = resolve_phase_execution_plan(ctx)
        skipped = tuple(phase_ref for phase_ref, _reason in plan.filter_skipped)
        return report, SmokeResult(
            cluster_id=ctx.cluster_id,
            validate_ok=True,
            plan_ok=True,
            phases=plan.summary.phases,
            invocations=plan.summary.invocation_count,
            skipped_phases=skipped,
        )
    except ClusterctlError as exc:
        report.add(
            Severity.ERROR,
            "smoke_plan_failed",
            str(exc),
        )
        return report, SmokeResult(
            cluster_id=ctx.cluster_id,
            validate_ok=True,
            plan_ok=False,
            error=str(exc),
        )


def run_smoke(
    root: Path | None = None,
    *,
    cluster_id: str | None = None,
    include_repo: bool = True,
) -> list[tuple[ValidationReport, SmokeResult | None]]:
    base = (root or repo_root()).resolve()
    results: list[tuple[ValidationReport, SmokeResult | None]] = []

    if include_repo:
        repo_report = validate_repo(base)
        results.append((repo_report, None))

    if cluster_id:
        cluster_ids = [cluster_id]
    else:
        cluster_ids = list_deployable_cluster_ids(base)

    for cid in cluster_ids:
        try:
            ctx = ClusterContext.load(cluster_id=cid)
            report, smoke = run_cluster_smoke(ctx)
            results.append((report, smoke))
        except ClusterctlError as exc:
            fail = report_cluster_load_failure(cid, exc)
            results.append(
                (
                    fail,
                    SmokeResult(
                        cluster_id=cid,
                        validate_ok=False,
                        plan_ok=False,
                        error=str(exc),
                    ),
                )
            )

    return results


def format_smoke_text(results: list[tuple[ValidationReport, SmokeResult | None]]) -> str:
    lines: list[str] = []
    for report, smoke in results:
        lines.append(format_report_text(report))
        if smoke is not None:
            if smoke.plan_ok:
                skipped = (
                    f", skipped={','.join(smoke.skipped_phases)}"
                    if smoke.skipped_phases
                    else ""
                )
                lines.append(
                    f"SMOKE OK: phases={len(smoke.phases)}, "
                    f"invocations={smoke.invocations}{skipped}"
                )
            else:
                lines.append(f"SMOKE FAIL: {smoke.error or 'plan failed'}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_smoke_json(results: list[tuple[ValidationReport, SmokeResult | None]]) -> str:
    payload = {
        "ok": all(report.ok for report, _ in results)
        and all(smoke is None or smoke.plan_ok for _, smoke in results),
        "results": [],
    }
    for report, smoke in results:
        entry = {
            "cluster_id": report.cluster_id,
            "validate_ok": report.ok,
            "issues": [
                asdict(issue)
                for issue in report.issues
                if issue.severity.value != "ok"
            ],
        }
        if smoke is not None:
            entry["smoke"] = asdict(smoke)
        payload["results"].append(entry)
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
