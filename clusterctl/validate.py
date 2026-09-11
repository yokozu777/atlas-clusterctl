"""Cluster and repository validation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

import yaml

from clusterctl.ansible_config import resolve_ansible_config
from clusterctl.cluster_config import cluster_config_path, load_cluster_config
from clusterctl.controller_extra_vars import (
    build_controller_extra_vars,
    controller_contract_warnings,
    validate_controller_contract,
)
from clusterctl.cluster_vars_loader import (
    discover_legacy_secrets_overlays,
    is_product_secrets_overlay,
    load_cluster_vars_from_paths,
    optional_cluster_var_file,
    secrets_example_file,
    secrets_file_configured,
    validate_secrets_content,
)
from clusterctl.host_vars import discover_host_vars, host_vars_dir, validate_host_var_content
from clusterctl.context import ClusterContext
from clusterctl.docker_validate import skip_docker_smoke_from_env, validate_docker_deep
from clusterctl.execution import ExecutionCheck, ExecutionResolution, validate_execution_runtime
from clusterctl.exceptions import (
    ClusterctlError,
    PhaseAliasesRemovedError,
    StacksRemovedError,
)
from clusterctl.legacy_guard import find_legacy_artifacts
from clusterctl.tools.check_no_legacy_repos import find_legacy_repo_references
from clusterctl.inventory import (
    DATA_GROUPS,
    INFRA_GROUPS,
    K8S_GROUPS,
    KAFKA_GROUPS,
    PGSQL_GROUPS,
    REDIS_GROUPS,
    extract_inventory_groups,
    extract_inventory_hostnames,
)
from clusterctl.pipeline_fixture import load_org_baseline_cluster_config
from clusterctl.paths import list_cluster_ids, list_deployable_cluster_ids, repo_root
from clusterctl.phase_intent import PhaseIntent, infer_phase_intent
from clusterctl.repo_conventions import ConventionFinding, check_repo_conventions
from clusterctl.pipeline_fixture import REFERENCE_CLUSTER_REL
from clusterctl.playbooks_validate import validate_org_baseline_playbooks

REFERENCE_CLUSTER_YAML = str(REFERENCE_CLUSTER_REL)
from clusterctl.playbooks_paths import resolve_playbook_entry_location
from clusterctl.playbooks_paths import playbook_repo_layout_ready, resolve_layout_dir
from clusterctl.playbooks_resolve import effective_playbooks_config, uses_phase_runner
from clusterctl.playbooks_lock import validate_playbooks_lock
from clusterctl.phase_plan import resolve_phase_execution_plan
from clusterctl.workspace_id import (
    literal_cluster_workspace_id,
    resolve_cluster_domain_from_vars,
    resolve_k8s_cluster_domain_from_vars,
    resolve_workspace_id_details,
)

JINJA_IN_PATH = re.compile(r"\{\{|\}\}")


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    OK = "ok"


@dataclass
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    hint: str | None = None
    cluster_id: str | None = None

    @property
    def is_error(self) -> bool:
        return self.severity == Severity.ERROR


@dataclass
class ValidationReport:
    cluster_id: str | None = None
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.is_error]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        cluster_id: str | None = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                severity=severity,
                code=code,
                message=message,
                hint=hint,
                cluster_id=cluster_id or self.cluster_id,
            )
        )


def report_cluster_load_failure(
    cluster_id: str,
    exc: BaseException,
) -> ValidationReport:
    """Map load failures to validate issue codes (ADR 005 / ADR 007)."""
    fail = ValidationReport(cluster_id=cluster_id)
    if isinstance(exc, StacksRemovedError):
        fail.add(
            Severity.ERROR,
            StacksRemovedError.code,
            str(exc),
            hint=StacksRemovedError.hint,
        )
    elif isinstance(exc, PhaseAliasesRemovedError):
        fail.add(
            Severity.ERROR,
            PhaseAliasesRemovedError.code,
            str(exc),
            hint=PhaseAliasesRemovedError.hint,
        )
    else:
        fail.add(Severity.ERROR, "cluster_load_failed", str(exc))
    return fail


def _issue(
    severity: Severity,
    code: str,
    message: str,
    *,
    hint: str | None = None,
    cluster_id: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,
        code=code,
        message=message,
        hint=hint,
        cluster_id=cluster_id,
    )


def _append_convention_findings(
    report: ValidationReport,
    findings: list[ConventionFinding],
) -> None:
    for finding in findings:
        if finding.severity == "ok":
            report.add(
                Severity.OK,
                finding.code,
                finding.message,
                hint=finding.hint,
            )
            continue
        severity = Severity.ERROR if finding.severity == "error" else Severity.WARNING
        report.add(
            severity,
            finding.code,
            finding.message,
            hint=finding.hint,
        )


def validate_repo(root: Path | None = None) -> ValidationReport:
    base = (root or repo_root()).resolve()
    report = ValidationReport(cluster_id="(repo)")

    cfg = resolve_ansible_config(base)
    report.add(Severity.OK, "ansible_cfg", f"ansible.cfg: {cfg}")

    for artifact in find_legacy_artifacts(base):
        report.add(
            Severity.ERROR,
            "legacy_artifact_present",
            f"remove legacy {artifact.kind}: {artifact.path.relative_to(base)}",
            hint=artifact.hint,
        )

    for rel, line_no, line in find_legacy_repo_references(base):
        report.add(
            Severity.ERROR,
            "legacy_repo_reference",
            f"{rel}:{line_no}: {line}",
            hint="use atlas-* playbook repo names only (see clusters/default/default/cluster.yaml)",
        )

    try:
        org = load_org_baseline_cluster_config(base)
        org.validate()
        assert org.playbooks is not None and org.phases is not None
        invocations = org.phases.invocation_count(org.playbooks)
        report.add(
            Severity.OK,
            "org_baseline",
            (
                f"{REFERENCE_CLUSTER_YAML}: schema v2 reference cluster, "
                f"{len(org.phases.phases)} phases, {invocations} invocations"
            ),
        )
        validate_org_baseline_playbooks(base)
        report.add(
            Severity.OK,
            "org_baseline_playbooks",
            "org baseline playbooks align with phases (all phase repos defined)",
        )
    except FileNotFoundError as exc:
        report.add(
            Severity.ERROR,
            "org_baseline_missing",
            str(exc),
            hint="ensure clusters/_template/k8s_full/cluster.yaml exists (optional lab: clusters/dev/mxhash)",
        )
    except ClusterctlError as exc:
        report.add(Severity.ERROR, "org_baseline_invalid", str(exc))

    clusters_dir = base / "clusters"
    from clusterctl.paths import clusters_root as resolve_clusters_root

    inventory_dir = resolve_clusters_root(base)
    if not inventory_dir.is_dir():
        report.add(
            Severity.WARNING,
            "clusters_dir_missing",
            f"clusters inventory directory not found: {inventory_dir}",
            hint="set clusters.path in $ATLAS_CLUSTER_ROOT/.config/config.yaml "
            "(from .config/config.yaml.example) or ATLAS_CLUSTERS_ROOT, "
            "or keep clusters/ under the controller checkout",
        )
    elif inventory_dir.resolve() != clusters_dir.resolve() and not clusters_dir.is_dir():
        report.add(
            Severity.WARNING,
            "product_clusters_dir_missing",
            "controller clusters/ directory not found (templates / org stubs)",
            hint="ensure ATLAS_CLUSTER_ROOT points at the atlas-clusterctl checkout",
        )
    _append_convention_findings(report, check_repo_conventions(base))

    return report


def _execution_checks_blocking_docker_deep(checks: list[ExecutionCheck]) -> bool:
    blocking = {
        "execution_docker_cli_missing",
        "execution_docker_image_missing",
        "execution_ssh_key",
        "execution_docker_image_resolve",
    }
    return any(check.severity == "error" and check.code in blocking for check in checks)


def _append_execution_checks(
    report: ValidationReport,
    checks: list[ExecutionCheck],
) -> None:
    for check in checks:
        if check.severity == "ok":
            report.add(Severity.OK, check.code, check.message, hint=check.hint)
        elif check.severity == "error":
            report.add(Severity.ERROR, check.code, check.message, hint=check.hint)
        else:
            report.add(Severity.WARNING, check.code, check.message, hint=check.hint)


def _validate_phase_intent_vs_inventory(
    report: ValidationReport,
    flags: PhaseIntent,
    groups: set[str],
) -> None:
    has_k8s_groups = bool(groups & K8S_GROUPS)
    has_infra = bool(groups & INFRA_GROUPS)
    has_pgsql_groups = bool(groups & PGSQL_GROUPS)
    has_redis_groups = bool(groups & REDIS_GROUPS)
    has_kafka_groups = bool(groups & KAFKA_GROUPS)
    has_data = bool(groups & DATA_GROUPS)

    if flags.k8s and not has_k8s_groups:
        report.add(
            Severity.ERROR,
            "phase_intent_k8s_no_inventory",
            "phases include k8s but inventory has no k8s_lbs/k8s_masters/k8s_workers groups",
            hint="add k8s groups to hosts or remove atlas-k8s-* refs from phases:",
        )
    if not flags.k8s and has_k8s_groups:
        report.add(
            Severity.WARNING,
            "inventory_k8s_phases_omitted",
            "inventory defines k8s groups but phases: omit k8s refs",
            hint="add atlas-k8s-core/cluster (and addons) to phases: or drop k8s inventory groups",
        )

    if flags.infra and not has_infra:
        report.add(
            Severity.WARNING,
            "phase_intent_infra_no_inventory",
            "phases include infra but inventory has no infra_platform group",
            hint="add infra_platform to hosts or remove infra phase refs from phases:",
        )
    if not flags.infra and has_infra:
        report.add(
            Severity.WARNING,
            "inventory_infra_phases_omitted",
            "inventory defines infra_platform but phases: omit infra refs",
            hint="add atlas-infra-edge/infra (or init-infra*) to phases: or drop infra_platform",
        )

    if flags.postgresql and not has_pgsql_groups:
        report.add(
            Severity.ERROR,
            "phase_intent_postgresql_no_inventory",
            "phases include postgresql but inventory has no "
            "pgsql_etcd_cluster/pgsql_cluster/pgsql_lbs groups",
            hint="add pgsql_* groups in hosts or remove atlas-postgresql/cluster from phases:",
        )
    if not flags.postgresql and has_pgsql_groups:
        report.add(
            Severity.WARNING,
            "inventory_postgresql_phases_omitted",
            "inventory defines pgsql groups but phases: omit postgresql refs",
            hint="add atlas-postgresql/cluster to phases: or drop pgsql_* inventory groups",
        )
    if "postgresql" in groups and not has_pgsql_groups:
        report.add(
            Severity.WARNING,
            "inventory_postgresql_parent_empty",
            "inventory has postgresql parent group but no pgsql_* child groups",
            hint="nest pgsql_etcd_cluster, pgsql_cluster, pgsql_lbs under postgresql",
        )
    if flags.mysql and "mysql" not in groups:
        report.add(
            Severity.ERROR,
            "phase_intent_mysql_no_inventory",
            "provision_stack=mysql but inventory has no mysql group",
            hint="add mysql group to hosts or set provision_stack to a non-mysql value",
        )

    if flags.redis and not has_redis_groups:
        report.add(
            Severity.ERROR,
            "phase_intent_redis_no_inventory",
            "phases include redis but inventory has no "
            "redis_cluster_masters/redis_cluster_replicas/redis_proxies/redis_lbs groups",
            hint="add redis_* groups in hosts or remove atlas-redis/cluster from phases:",
        )
    if not flags.redis and has_redis_groups:
        report.add(
            Severity.WARNING,
            "inventory_redis_phases_omitted",
            "inventory defines redis groups but phases: omit redis refs",
            hint="add atlas-redis/cluster to phases: or drop redis_* inventory groups",
        )
    if "redis" in groups and not has_redis_groups:
        report.add(
            Severity.WARNING,
            "inventory_redis_parent_empty",
            "inventory has redis parent group but no redis_* child groups",
            hint="nest redis_cluster_masters, redis_cluster_replicas, redis_proxies, redis_lbs under redis",
        )

    if flags.kafka and not has_kafka_groups:
        report.add(
            Severity.ERROR,
            "phase_intent_kafka_no_inventory",
            "phases include kafka but inventory has no "
            "kafka_controllers/kafka_brokers groups",
            hint="add kafka_* groups in hosts or remove atlas-kafka/cluster from phases:",
        )
    if not flags.kafka and has_kafka_groups:
        report.add(
            Severity.WARNING,
            "inventory_kafka_phases_omitted",
            "inventory defines kafka groups but phases: omit kafka refs",
            hint="add atlas-kafka/cluster to phases: or drop kafka_* inventory groups",
        )
    if "kafka" in groups and not has_kafka_groups:
        report.add(
            Severity.WARNING,
            "inventory_kafka_parent_empty",
            "inventory has kafka parent group but no kafka_* child groups",
            hint="nest kafka_controllers and kafka_brokers under kafka",
        )

    if flags.data and not has_data and flags.provision_stack not in {
        "postgresql",
        "mysql",
        "redis",
        "kafka",
    }:
        report.add(
            Severity.WARNING,
            "provision_stack_no_inventory",
            f"provision_stack={flags.provision_stack!r} but no data groups in inventory",
        )


def _validate_cluster_domain_vars(
    report: ValidationReport,
    merged: dict,
    *,
    k8s_intent: bool,
) -> None:
    cluster_domain_raw = merged.get("cluster_domain")
    k8s_domain_raw = merged.get("k8s_cluster_domain")

    if cluster_domain_raw is None:
        if k8s_domain_raw is not None and resolve_k8s_cluster_domain_from_vars(merged):
            report.add(
                Severity.ERROR,
                "cluster_domain_missing",
                "cluster_domain not set — k8s_cluster_domain alone is not a workspace-id fallback",
                hint='add cluster_domain: "k8s.{{ dns_domain_suffix }}" and k8s_cluster_domain: "{{ cluster_domain }}"',
            )
        else:
            report.add(
                Severity.ERROR,
                "cluster_domain_missing",
                "cluster_domain not set in group_vars/all (atlas-*.yml overlays)",
                hint='set cluster_domain (e.g. "k8s.{{ dns_domain_suffix }}") in product overlays',
            )
    else:
        resolved = resolve_cluster_domain_from_vars(merged)
        report.add(
            Severity.OK,
            "cluster_domain",
            f"cluster_domain resolves to: {resolved or cluster_domain_raw!r}",
        )

    if k8s_intent and k8s_domain_raw is not None:
        alias = str(k8s_domain_raw).strip()
        if alias and alias != "{{ cluster_domain }}":
            resolved_k8s = resolve_k8s_cluster_domain_from_vars(merged)
            resolved_cluster = resolve_cluster_domain_from_vars(merged)
            if resolved_cluster and resolved_k8s and resolved_k8s != resolved_cluster:
                report.add(
                    Severity.WARNING,
                    "k8s_cluster_domain_diverged",
                    f"k8s_cluster_domain ({resolved_k8s!r}) differs from cluster_domain ({resolved_cluster!r})",
                    hint='prefer k8s_cluster_domain: "{{ cluster_domain }}"',
                )

    literal_ws = literal_cluster_workspace_id(merged)
    if literal_ws:
        report.add(
            Severity.OK,
            "cluster_workspace_id_literal",
            f"literal cluster_workspace_id: {literal_ws}",
        )


def _policy_cluster_ids(base: Path) -> list[str]:
    """Usable cluster IDs that are org/env policy or scaffold — not deployable leaves."""
    all_ids = set(list_cluster_ids(base))
    deployable = set(list_deployable_cluster_ids(base))
    return sorted(all_ids - deployable)


def _validate_workspace_collisions(
    reports: list[ValidationReport],
    *,
    executor: str | None = None,
    root: Path,
) -> None:
    by_id: dict[str, list[str]] = {}
    for cluster_id in list_deployable_cluster_ids(root):
        try:
            ctx = ClusterContext.load(cluster_id=cluster_id, executor=executor)
            by_id.setdefault(ctx.workspace_id, []).append(cluster_id)
        except ClusterctlError:
            continue

    for workspace_id, cluster_ids in sorted(by_id.items()):
        if len(cluster_ids) < 2:
            continue
        message = (
            f"workspace id {workspace_id!r} shared by clusters: {', '.join(sorted(cluster_ids))}"
        )
        hint = "use distinct cluster_domain or cluster.yaml workspace_id per cluster"
        for cluster_id in cluster_ids:
            for report in reports:
                if report.cluster_id == cluster_id:
                    report.add(
                        Severity.ERROR,
                        "workspace_id_collision",
                        message,
                        hint=hint,
                        cluster_id=cluster_id,
                    )
                    break


def _validate_host_vars(
    report: ValidationReport,
    ctx: ClusterContext,
    inventory_hosts: set[str],
) -> None:
    directory = host_vars_dir(ctx.config_dir)
    if not directory.is_dir():
        return

    try:
        host_vars = discover_host_vars(ctx.config_dir)
    except ClusterctlError as exc:
        report.add(Severity.ERROR, "host_vars_invalid", str(exc))
        return

    if not host_vars:
        return

    report.add(
        Severity.OK,
        "host_vars_present",
        f"host_vars: {len(host_vars)} file(s) under host_vars/",
    )

    for hostname, path in host_vars:
        content_error = validate_host_var_content(path)
        if content_error:
            report.add(
                Severity.ERROR,
                "host_vars_invalid",
                f"host_vars/{path.name}: {content_error}",
                hint="use a YAML mapping per host",
            )
            continue
        if hostname not in inventory_hosts:
            report.add(
                Severity.WARNING,
                "host_vars_orphan",
                f"host_vars/{path.name} — host {hostname!r} not in inventory",
                hint="rename file to match inventory host key or remove it",
            )
        else:
            try:
                rel = path.relative_to(ctx.config_dir)
            except ValueError:
                rel = path
            report.add(
                Severity.OK,
                "host_var_file",
                f"{rel} → {hostname!r}",
            )


def _validate_controller_contract(report: ValidationReport, ctx: ClusterContext) -> None:
    errors = validate_controller_contract(ctx)
    if errors:
        for message in errors:
            report.add(
                Severity.ERROR,
                "controller_contract",
                message,
                hint="ensure clusters/<id>/hosts and pub_keys/ exist; see docs/clusters.md",
            )
        return

    for message in controller_contract_warnings(ctx):
        report.add(
            Severity.WARNING,
            "controller_contract_workspace",
            message,
        )

    data = build_controller_extra_vars(ctx)
    report.add(
        Severity.OK,
        "controller_contract",
        (
            f"controller inject: atlas_cluster_root={data['atlas_cluster_root']}, "
            f"atlas_inventory_root={data['atlas_inventory_root']}, "
            f"workspace={data['cluster_workspace_root']}"
        ),
    )


def _validate_playbooks_resolver(
    report: ValidationReport,
    ctx: ClusterContext,
    cfg,
    *,
    base: Path,
    strict: bool = False,
) -> None:
    if not uses_phase_runner(ctx):
        report.add(
            Severity.ERROR,
            "playbooks_incomplete",
            "schema v2 cluster is missing phases or playbooks configuration",
            hint="see docs/cluster-config-v2.md",
        )
        return

    report.add(
        Severity.OK,
        "playbooks_resolver_active",
        f"schema v{ctx.schema_version} phase runner active",
    )

    try:
        playbooks = effective_playbooks_config(ctx)
        playbooks.validate()
        if ctx.config_v2 is not None and ctx.config_v2.phases is not None:
            ctx.config_v2.phases.validate(playbooks)
    except ClusterctlError as exc:
        report.add(Severity.ERROR, "playbooks_invalid", str(exc))
        return

    phase_repo_names: set[str] = set()
    if ctx.config_v2 is not None and ctx.config_v2.phases is not None:
        from clusterctl.playbooks_config import parse_phase_ref

        for phase_ref in ctx.config_v2.phases.phases:
            repo_name, _ = parse_phase_ref(phase_ref)
            phase_repo_names.add(repo_name)

    for repo_name, spec in playbooks.repos.items():
        if phase_repo_names and repo_name not in phase_repo_names:
            continue
        layout_dir = resolve_layout_dir(
            spec,
            workspace_root=ctx.workspace_root,
            repo_root_path=base,
        )
        if playbook_repo_layout_ready(spec, layout_dir):
            report.add(
                Severity.OK,
                f"playbooks_{repo_name}",
                f"{repo_name}: layout ready at {layout_dir}",
            )
        else:
            report.add(
                Severity.ERROR,
                f"playbooks_{repo_name}_missing",
                f"{repo_name}: layout not ready at {layout_dir}",
                hint="./cluster playbooks sync",
            )

        if ctx.config_v2 is None or ctx.config_v2.phases is None:
            continue
        from clusterctl.playbooks_config import parse_phase_ref

        for phase_ref in ctx.config_v2.phases.phases:
            ref_repo, entry_id = parse_phase_ref(phase_ref)
            if ref_repo != repo_name:
                continue
            try:
                _repo, entry = playbooks.resolve_entry(phase_ref)
            except ClusterctlError:
                continue
            location = resolve_playbook_entry_location(
                spec,
                entry.file,
                workspace_root=ctx.workspace_root,
                repo_root_path=base,
            )
            if location.playbook_path.is_file():
                report.add(
                    Severity.OK,
                    f"playbook_file_{repo_name}_{entry_id}",
                    f"{phase_ref}: {location.playbook_path.name}",
                )
            elif spec.source == "git":
                report.add(
                    Severity.WARNING,
                    f"playbook_file_{repo_name}_{entry_id}_pending_sync",
                    f"{phase_ref}: playbook not in workspace yet ({location.playbook_path})",
                    hint="./cluster playbooks sync",
                )
            else:
                report.add(
                    Severity.ERROR,
                    f"playbook_file_{repo_name}_{entry_id}_missing",
                    f"{phase_ref}: playbook not found at {location.playbook_path}",
                    hint="check playbooks.<repo>.entries or local repo path",
                )

    lock_issues = validate_playbooks_lock(
        cluster_id=ctx.cluster_id,
        workspace_id=ctx.workspace_id,
        playbooks=playbooks,
        workspace_root=ctx.workspace_root,
        repo_root_path=base,
        phase_repo_names=phase_repo_names,
        strict=strict,
    )
    for severity, code, message, hint in lock_issues:
        report.add(
            Severity.ERROR if severity == "error" else Severity.WARNING,
            code,
            message,
            hint=hint,
        )


def _validate_execution_plan(
    report: ValidationReport,
    ctx: ClusterContext,
    cfg,
    flags: PhaseIntent,
    *,
    base: Path,
) -> None:
    del cfg, flags, base  # plan is phases-only (ADR 005); flags used elsewhere
    if not uses_phase_runner(ctx):
        report.add(
            Severity.ERROR,
            "plan_requires_v2",
            "execution plan requires schema v2 playbooks + phases",
            hint="see docs/cluster-config-v2.md",
        )
        return

    try:
        plan = resolve_phase_execution_plan(ctx)
        if not plan.summary.phases:
            report.add(
                Severity.ERROR,
                "plan_empty",
                "v2 execution plan is empty after phase/when filters",
            )
            return
        skipped_parts: list[str] = []
        if plan.filter_skipped:
            skipped_parts.append(
                "when: "
                + ", ".join(f"{ref} ({reason})" for ref, reason in plan.filter_skipped)
            )
        report.add(
            Severity.OK,
            "plan_resolved",
            (
                f"v2 phases: {len(plan.summary.phases)} phases, "
                f"{plan.summary.invocation_count} invocations"
                + (f" (skipped: {'; '.join(skipped_parts)})" if skipped_parts else "")
            ),
        )
    except ClusterctlError as exc:
        report.add(Severity.ERROR, "plan_invalid", str(exc))


def validate_cluster(
    ctx: ClusterContext,
    *,
    root: Path | None = None,
    docker_smoke: bool = True,
    strict: bool = False,
) -> ValidationReport:
    base = (root or ctx.repo_root).resolve()
    report = ValidationReport(cluster_id=ctx.cluster_id)

    config_path = cluster_config_path(ctx.config_dir)
    if not config_path.is_file() and ctx.cluster_id != "default":
        report.add(
            Severity.ERROR,
            "cluster_config_missing",
            f"missing {config_path}",
            hint="./cluster init <id>",
        )
    else:
        report.add(Severity.OK, "cluster_config", f"config: {ctx.config_dir}")

    if not ctx.inventory.is_file():
        report.add(Severity.ERROR, "inventory_missing", f"inventory not found: {ctx.inventory}")
        return report

    try:
        groups = extract_inventory_groups(ctx.inventory)
        report.add(Severity.OK, "inventory_groups", f"inventory groups: {', '.join(sorted(groups))}")
        inventory_hosts = extract_inventory_hostnames(ctx.inventory)
        report.add(
            Severity.OK,
            "inventory_hosts",
            f"inventory hosts: {len(inventory_hosts)}",
        )
    except ClusterctlError as exc:
        report.add(Severity.ERROR, "inventory_invalid", str(exc))
        return report

    if not ctx.group_var_files:
        report.add(Severity.ERROR, "group_vars_missing", "no group_vars/all/*.yml files resolved")
        return report

    for path in ctx.group_var_files:
        if not path.is_file():
            report.add(Severity.ERROR, "group_var_missing", f"group var file not found: {path}")

    product_secrets = [
        path for path in ctx.group_var_files if is_product_secrets_overlay(path.name)
    ]
    legacy_secrets = list(discover_legacy_secrets_overlays(ctx.config_dir))

    for path in product_secrets:
        secrets_error = validate_secrets_content(path)
        if secrets_error:
            report.add(
                Severity.ERROR,
                "secrets_invalid",
                f"group_vars/all/{path.name}: {secrets_error}",
                hint="use a YAML mapping or remove the file",
            )
        elif secrets_file_configured(path):
            report.add(Severity.OK, "secrets_present", f"secrets: {path}")
        else:
            report.add(
                Severity.WARNING,
                "secrets_unconfigured",
                f"group_vars/all/{path.name} has no active keys (comments only)",
                hint="add secret overrides as a YAML mapping, vault-encrypt, or remove the file",
            )

    if legacy_secrets:
        names = ", ".join(p.name for p in legacy_secrets)
        report.add(
            Severity.ERROR,
            "secrets_legacy_monolith",
            f"legacy group_vars/all/{names} is not allowed — use atlas-<repo>.secrets.yml",
            hint="split keys into per-product *.secrets.yml overlays and delete secrets.yml (see docs/clusters.md)",
        )

    legacy_cluster_yml = optional_cluster_var_file(ctx.config_dir)
    if legacy_cluster_yml is not None:
        report.add(
            Severity.ERROR,
            "cluster_yml_legacy",
            "legacy group_vars/all/cluster.yml is not allowed — omit this file",
            hint=(
                "move DNS identity into atlas-*.yml Leaf DNS blocks, then delete "
                "cluster.yml (ADR 003); do not test -f …/cluster.yml in scripts"
            ),
        )

    if not product_secrets:
        # Prefer documenting product secrets when any product catalog is present.
        all_dir = ctx.config_dir / "group_vars" / "all"
        has_product_catalog = False
        if all_dir.is_dir():
            has_product_catalog = any(
                p.is_file()
                and p.name.startswith("atlas-")
                and p.name.endswith(".yml")
                and not p.name.endswith(".secrets.yml")
                for p in all_dir.iterdir()
            )
        if has_product_catalog or secrets_example_file(ctx.config_dir).is_file():
            report.add(
                Severity.WARNING,
                "secrets_missing",
                "no group_vars/all/*.secrets.yml present",
                hint=(
                    "add atlas-<repo>.secrets.yml next to each product catalog "
                    "(CHANGEME examples / ansible-vault encrypt in place)"
                ),
            )

    _validate_host_vars(report, ctx, inventory_hosts)
    _validate_controller_contract(report, ctx)

    try:
        cfg = load_cluster_config(ctx.config_dir, ctx.cluster_id, repo_root=base)
        if cfg.cluster_id != ctx.cluster_id and ctx.cluster_id != "default":
            report.add(
                Severity.WARNING,
                "cluster_id_mismatch",
                f"cluster.yaml id={cfg.cluster_id!r} differs from directory {ctx.cluster_id!r}",
            )
        if not uses_phase_runner(ctx):
            if ctx.deployable:
                report.add(
                    Severity.ERROR,
                    "schema_v1_removed",
                    "deployable clusters must use schema v2 playbooks + phases",
                    hint="see docs/cluster-config-v2.md and clusters/_template/k8s_full/",
                )
            else:
                report.add(
                    Severity.WARNING,
                    "schema_v1_removed",
                    "schema v1 profiles/pipeline removed — policy dirs need playbooks + phases for deploy",
                    hint="define playbooks: + phases: on deployable leaves "
                    "(omit playbooks_enabled: true — ADR 006; see docs/cluster-config-v2.md)",
                )
        else:
            _validate_playbooks_resolver(report, ctx, cfg, base=base, strict=strict)
            if cfg.playbooks_enabled and not cfg.role_repos.is_configured():
                report.add(
                    Severity.ERROR,
                    "playbooks_specs_incomplete",
                    "playbooks runner enabled but no specs derived from playbooks cascade",
                    hint="ensure clusters/default/default/cluster.yaml defines playbooks for every phase repo",
                )
            elif cfg.role_repos.is_configured():
                report.add(
                    Severity.OK,
                    "playbooks_from_cascade",
                    "playbook repo specs derived from effective playbooks cascade",
                )
            if cfg.legacy_profile:
                severity = Severity.ERROR if ctx.deployable else Severity.WARNING
                report.add(
                    severity,
                    "profile_legacy_removed",
                    f"cluster.yaml profile={cfg.legacy_profile!r} is removed in schema v2",
                    hint="use phases: / --phases instead of profile",
                )
            leaf_cfg_path = cluster_config_path(ctx.config_dir)
            if leaf_cfg_path.is_file():
                leaf_raw = yaml.safe_load(leaf_cfg_path.read_text(encoding="utf-8")) or {}
                if (
                    isinstance(leaf_raw, dict)
                    and uses_phase_runner(ctx)
                    and "schema_version" not in leaf_raw
                ):
                    report.add(
                        Severity.WARNING,
                        "schema_version_implicit",
                        "leaf cluster.yaml omits schema_version — inferred v2 from cascade",
                        hint="set schema_version: 2 explicitly in the leaf cluster.yaml",
                    )
    except ClusterctlError as exc:
        report.add(Severity.ERROR, "cluster_config_invalid", str(exc))
        return report

    execution_checks = validate_execution_runtime(
        ExecutionResolution(
            configured=cfg.execution,
            effective=ctx.execution,
            source=ctx.execution_source,
        ),
        ssh_key=ctx.ssh_key,
    )
    _append_execution_checks(report, execution_checks)

    if (
        docker_smoke
        and not skip_docker_smoke_from_env()
        and not _execution_checks_blocking_docker_deep(execution_checks)
    ):
        _append_execution_checks(report, validate_docker_deep(ctx))

    merged = load_cluster_vars_from_paths(ctx.group_var_files)
    phase_refs: tuple[str, ...] = ()
    if cfg.config_v2 is not None and cfg.config_v2.phases is not None:
        phase_refs = cfg.config_v2.phases.phases
    flags = infer_phase_intent(phase_refs, merged)
    report.add(
        Severity.OK,
        "phase_intent_resolved",
        (
            f"phase intent: infra={flags.infra} k8s={flags.k8s} "
            f"postgresql={flags.postgresql} mysql={flags.mysql} redis={flags.redis} "
            f"kafka={flags.kafka} "
            f"(provision_stack={flags.provision_stack})"
        ),
    )

    _validate_phase_intent_vs_inventory(report, flags, groups)
    _validate_cluster_domain_vars(report, merged, k8s_intent=flags.k8s)

    try:
        resolution = resolve_workspace_id_details(
            base,
            group_var_files=list(ctx.group_var_files),
            override=cfg.workspace_id_override,
        )
        workspace_id = resolution.workspace_id
        if JINJA_IN_PATH.search(workspace_id):
            report.add(
                Severity.ERROR,
                "workspace_id_unresolved",
                f"workspace id contains unresolved Jinja: {workspace_id!r}",
                hint="set cluster_workspace_id or cluster_domain in atlas-*.yml overlays",
            )
        else:
            report.add(
                Severity.OK,
                "workspace_id",
                f"workspace id: {workspace_id} (source: {resolution.source.value})",
            )
    except (ClusterctlError, ValueError) as exc:
        report.add(Severity.ERROR, "workspace_id_invalid", str(exc))

    _validate_execution_plan(report, ctx, cfg, flags, base=base)

    return report


def validate_all_clusters(
    root: Path | None = None,
    *,
    executor: str | None = None,
    docker_smoke: bool = True,
    strict: bool = False,
) -> list[ValidationReport]:
    """Validate repository layout and every deployable cluster under clusters/.

    Org baseline, env policy dirs (``*/default``), and flat scaffolds are reported
    with ``cluster_policy_skipped`` and are not loaded via :class:`ClusterContext`.
    """
    base = (root or repo_root()).resolve()
    reports: list[ValidationReport] = []

    repo_report = validate_repo(base)
    reports.append(repo_report)

    for policy_id in _policy_cluster_ids(base):
        skip = ValidationReport(cluster_id=policy_id)
        skip.add(
            Severity.OK,
            "cluster_policy_skipped",
            "not deployable (org/env policy or scaffold — skipped in --all)",
            hint="./cluster config effective --cluster <id>  # inspect cascade only",
        )
        reports.append(skip)

    deployable_ids = list_deployable_cluster_ids(base)
    if not deployable_ids:
        empty = ValidationReport(cluster_id="(clusters)")
        empty.add(
            Severity.WARNING,
            "no_deployable_clusters",
            "no deployable cluster leaves under clusters/ (only policy/scaffold dirs)",
            hint="./cluster init <env>/<name>",
        )
        reports.append(empty)
    else:
        for cluster_id in deployable_ids:
            try:
                ctx = ClusterContext.load(cluster_id=cluster_id, executor=executor)
                reports.append(
                    validate_cluster(
                        ctx,
                        root=base,
                        docker_smoke=docker_smoke,
                        strict=strict,
                    )
                )
            except ClusterctlError as exc:
                reports.append(report_cluster_load_failure(cluster_id, exc))

    _validate_workspace_collisions(reports, executor=executor, root=base)

    return reports


def format_report_text(report: ValidationReport) -> str:
    lines = [f"=== {report.cluster_id} ==="]
    if not report.issues:
        lines.append("OK: no issues")
        return "\n".join(lines)

    for issue in report.issues:
        if issue.severity == Severity.OK:
            prefix = "OK"
        elif issue.severity == Severity.WARNING:
            prefix = "WARN"
        else:
            prefix = "FAIL"
        line = f"{prefix} [{issue.code}] {issue.message}"
        if issue.hint:
            line += f" — {issue.hint}"
        lines.append(line)

    errors = len(report.errors)
    warnings = len(report.warnings)
    lines.append(f"summary: {errors} error(s), {warnings} warning(s)")
    return "\n".join(lines)


def format_reports_json(reports: list[ValidationReport]) -> str:
    payload = {
        "ok": all(report.ok for report in reports),
        "reports": [
            {
                "cluster_id": report.cluster_id,
                "ok": report.ok,
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "issues": [asdict(issue) for issue in report.issues if issue.severity != Severity.OK],
            }
            for report in reports
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
