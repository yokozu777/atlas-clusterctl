"""Unified config show (cluster + execution + ansible phase)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from clusterctl.ansible_config import summary_lines_for_boundary
from clusterctl.cluster_config_loader import (
    cluster_config_v2_to_yaml_dict,
    dump_cluster_config_v2,
)
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.execution import (
    check_ssh_key,
    docker_cli_available,
    resolve_docker_image_ref,
)
from clusterctl.playbooks_resolve import effective_playbooks_config, require_phase_runner
from clusterctl.workspace_paths import workspace_ansible_summary_lines


@dataclass(frozen=True)
class ConfigShowReport:
    cluster_id: str
    display_name: str | None
    execution_effective: str
    execution_configured: str
    execution_source: str
    docker_image: str | None
    docker_available: bool
    ssh_key: str
    ssh_key_ok: bool
    workspace_id: str
    workspace_root: str
    inventory: str
    boundary: str
    phase_ref: str
    ansible_lines: tuple[str, ...]
    ansible_runtime_lines: tuple[str, ...]
    schema_version: int
    deployable: bool
    cascade_paths: tuple[str, ...]
    has_config_v2: bool


def build_config_show_report(ctx: ClusterContext, boundary: str) -> ConfigShowReport:
    require_phase_runner(ctx)
    assert ctx.config_v2 is not None
    assert ctx.config_v2.phases is not None
    playbooks = effective_playbooks_config(ctx)
    phases = ctx.config_v2.phases
    from clusterctl.ansible_config import resolve_boundary_entry

    phase_ref, _, _ = resolve_boundary_entry(boundary, playbooks, phases)
    ssh_error = check_ssh_key(ctx.ssh_key)
    return ConfigShowReport(
        cluster_id=ctx.cluster_id,
        display_name=ctx.display_name,
        execution_effective=ctx.execution.summary(),
        execution_configured=ctx.execution_configured.summary(),
        execution_source=ctx.execution_source,
        docker_image=(
            resolve_docker_image_ref(ctx.execution.docker) if ctx.execution.is_docker else None
        ),
        docker_available=docker_cli_available(),
        ssh_key=str(ctx.ssh_key),
        ssh_key_ok=ssh_error is None,
        workspace_id=ctx.workspace_id,
        workspace_root=str(ctx.workspace_root.resolve()),
        inventory=str(ctx.inventory),
        boundary=boundary,
        phase_ref=phase_ref,
        ansible_lines=tuple(
            summary_lines_for_boundary(
                ctx.repo_root,
                boundary,
                playbooks=playbooks,
                phases=phases,
                workspace_root=ctx.workspace_root,
            )
        ),
        ansible_runtime_lines=tuple(
            workspace_ansible_summary_lines(
                ctx.workspace_root,
                workspace_id=ctx.workspace_id,
                controller_temp=ctx.controller_temp_location(),
            )
        ),
        schema_version=ctx.schema_version,
        deployable=ctx.deployable,
        cascade_paths=tuple(str(path) for path in ctx.cascade_paths),
        has_config_v2=ctx.config_v2 is not None,
    )


def format_config_show_text(report: ConfigShowReport) -> str:
    lines = [
        f"=== Cluster: {report.cluster_id} ===",
    ]
    if report.display_name:
        lines.append(f"Display:     {report.display_name}")
    lines.append(f"Schema:      v{report.schema_version}")
    lines.append(f"Deployable:  {'yes' if report.deployable else 'no'}")
    if report.cascade_paths:
        lines.append(f"Cascade:     {len(report.cascade_paths)} fragment(s)")
        for path in report.cascade_paths:
            lines.append(f"             - {path}")
    lines.extend(
        [
            f"Inventory:   {report.inventory}",
            f"Workspace:   {report.workspace_id}",
            "",
            "=== Execution ===",
            f"Effective:   {report.execution_effective}",
            f"Configured:  {report.execution_configured} (cluster.yaml)",
            f"Resolved via: {report.execution_source}",
        ]
    )
    if report.execution_effective != report.execution_configured:
        lines.append("Note:        effective mode differs from cluster.yaml (override active)")
    if report.docker_image:
        lines.append(f"Docker image: {report.docker_image}")
    lines.append(f"Docker CLI:  {'available' if report.docker_available else 'not found'}")
    ssh_status = "ok" if report.ssh_key_ok else "missing or unreadable"
    lines.append(f"SSH key:     {report.ssh_key} ({ssh_status})")
    lines.extend(
        [
            "",
            f"=== Ansible runtime ({report.workspace_root}) ===",
            *report.ansible_runtime_lines,
            "",
            f"=== Ansible ({report.boundary} → {report.phase_ref}) ===",
            *report.ansible_lines,
        ]
    )
    return "\n".join(lines) + "\n"


def format_config_show_json(report: ConfigShowReport) -> str:
    payload = {
        **asdict(report),
        "ansible": {
            "boundary": report.boundary,
            "phase_ref": report.phase_ref,
            "runtime_lines": list(report.ansible_runtime_lines),
            "lines": list(report.ansible_lines),
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def cmd_config_show(
    ctx: ClusterContext,
    boundary: str,
    *,
    as_json: bool = False,
) -> int:
    report = build_config_show_report(ctx, boundary)
    if as_json:
        print(format_config_show_json(report), end="")
    else:
        print(format_config_show_text(report), end="")
    return 0


def cmd_config_effective(
    ctx: ClusterContext | None,
    *,
    cluster_id: str,
    repo_root_path: Path,
    as_json: bool = False,
) -> int:
    from clusterctl.cluster_config_loader import load_merged_cluster_config_v2_for_repo
    from clusterctl.paths import cascade_paths_for_cluster

    config_v2 = ctx.config_v2 if ctx is not None else None
    if config_v2 is None:
        config_v2 = load_merged_cluster_config_v2_for_repo(repo_root_path, cluster_id)

    config_dir = ctx.config_dir if ctx is not None else None
    deployable = ctx.deployable if ctx is not None else config_v2.deployable
    cascade_paths = ctx.cascade_paths if ctx is not None else ()
    if not cascade_paths:
        cascade_paths = tuple(cascade_paths_for_cluster(repo_root_path, cluster_id))

    if as_json:
        payload = {
            "cluster_id": cluster_id,
            "config_dir": str(config_dir) if config_dir else None,
            "deployable": deployable,
            "cascade_paths": [str(path) for path in cascade_paths],
            "effective": cluster_config_v2_to_yaml_dict(config_v2),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", end="")
    else:
        print(f"# Effective cluster config: {cluster_id}")
        if config_dir is not None:
            print(f"# Config dir: {config_dir}")
        print(f"# Deployable: {'yes' if deployable else 'no'}")
        if cascade_paths:
            print("# Cascade fragments:")
            for path in cascade_paths:
                print(f"#   - {path}")
        print("---")
        print(dump_cluster_config_v2(config_v2), end="")
    return 0
