"""Repository layout conventions (formerly scripts/check_workspace_conventions.sh)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_registry import org_baseline_playbook_repo_names
from clusterctl.workspace_id import resolve_workspace_id
from clusterctl.workspace_paths import (
    legacy_repo_root_ansible_entries,
    workspace_ansible_summary_lines,
    workspace_ansible_tmp_dir,
    workspace_facts_cache_dir,
)

JOB_NAME = re.compile(r"JOB_NAME")
K8S_CONTROLLER = re.compile(r"k8s_controller_")
JINJA_IN_NAME = re.compile(r"\{\{|\}\}")

LEGACY_ROOT_ENTRIES = (
    ".ansible",
    ".ansible-k8s-state",
    ".ansible_facts_cache",
    "tf_state",
    "tf_workspace",
    "build_workspace",
    "build_templates_state.json",
    "variables.tf",
    "ansible_local_execute.cfg",
    "hosts.zip",
)

# Deprecated in-repo / docker-mount stub dirs at atlas-clusterctl root (use workspace/<id>/repos/).
# Repo names come from org baseline playbooks catalog (G1/G6).
_REPO_SCAN_SUFFIXES = {".sh", ".yml", ".yaml"}
_REPO_SKIP_DIRS = frozenset({"logs", ".git", "workspace", "__pycache__", ".venv", "venv", "node_modules"})
_SIBLING_SCAN_SUFFIXES = {".yaml", ".yml", ".j2"}
_ANSIBLE_CFG_LEGACY_FACT_CACHE = re.compile(
    r"^\s*fact_caching_connection\s*=",
    re.MULTILINE,
)

_LEGACY_ANSIBLE_ROOT_HINT = "rm -rf .ansible .ansible_facts_cache (runtime belongs under workspace/<id>/)"


@dataclass(frozen=True)
class ConventionFinding:
    severity: str  # "error" | "warning" | "ok"
    code: str
    message: str
    hint: str | None = None


def _iter_files(base: Path, suffixes: set[str]) -> list[Path]:
    if not base.is_dir():
        return []
    results: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        rel_parts = path.relative_to(base).parts
        if any(part in _REPO_SKIP_DIRS for part in rel_parts):
            continue
        results.append(path)
    return results


def _scan_pattern(
    base: Path,
    pattern: re.Pattern[str],
    suffixes: set[str],
    *,
    code: str,
    label: str,
) -> list[ConventionFinding]:
    findings: list[ConventionFinding] = []
    for path in _iter_files(base, suffixes):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(
                ConventionFinding(
                    severity="warning",
                    code=f"{code}_unreadable",
                    message=f"cannot read {path.relative_to(base)}: {exc}",
                )
            )
            continue
        if pattern.search(text):
            findings.append(
                ConventionFinding(
                    severity="error",
                    code=code,
                    message=f"{label}: {path.relative_to(base)}",
                )
            )
    return findings


def _legacy_root_is_populated(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return True
    if not path.is_dir():
        return True
    try:
        return any(path.iterdir())
    except OSError:
        return True


def _legacy_root_findings(base: Path) -> list[ConventionFinding]:
    findings: list[ConventionFinding] = []
    legacy_ansible = {path.name for path in legacy_repo_root_ansible_entries(base)}

    for name in LEGACY_ROOT_ENTRIES:
        path = base / name
        if not _legacy_root_is_populated(path):
            continue
        hint = (
            _LEGACY_ANSIBLE_ROOT_HINT
            if name in legacy_ansible
            else "move runtime data under workspace/<id>/"
        )
        findings.append(
            ConventionFinding(
                severity="error",
                code="legacy_root_path",
                message=f"legacy path at repo root: {name}",
                hint=hint,
            )
        )
    return findings


def _ansible_cfg_findings(base: Path) -> list[ConventionFinding]:
    cfg = base / "ansible.cfg"
    if not cfg.is_file():
        return []

    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [
            ConventionFinding(
                severity="warning",
                code="ansible_cfg_unreadable",
                message=f"cannot read ansible.cfg: {exc}",
            )
        ]

    findings: list[ConventionFinding] = []
    if _ANSIBLE_CFG_LEGACY_FACT_CACHE.search(text):
        findings.append(
            ConventionFinding(
                severity="error",
                code="ansible_cfg_legacy_fact_cache",
                message=(
                    "ansible.cfg must not set fact_caching_connection "
                    "(legacy repo-root fact cache)"
                ),
                hint=(
                    "remove fact_caching_connection from ansible.cfg; "
                    "clusterctl sets ANSIBLE_CACHE_PLUGIN_CONNECTION under workspace/<id>/"
                ),
            )
        )
    return findings


def _workspace_dir_findings(base: Path) -> list[ConventionFinding]:
    from clusterctl.paths import workspace_parent

    findings: list[ConventionFinding] = []
    workspace = workspace_parent(base)
    if not workspace.is_dir():
        findings.append(
            ConventionFinding(
                severity="warning",
                code="workspace_dir_missing",
                message=f"{workspace} not created yet",
                hint=(
                    "run any playbook with 00_ensure_workspace, or "
                    "./cluster run --dry-run / ./cluster run --phases provision"
                ),
            )
        )
        return findings

    for entry in workspace.rglob("*"):
        if entry.is_dir() and JINJA_IN_NAME.search(entry.name):
            try:
                rel = entry.relative_to(workspace)
            except ValueError:
                rel = entry.name
            findings.append(
                ConventionFinding(
                    severity="error",
                    code="workspace_dir_unresolved_jinja",
                    message=(
                        f"invalid workspace directory name (unresolved Jinja?): "
                        f"workspace/{rel}"
                    ),
                    hint="rm -rf the bad directory and fix cluster vars",
                )
            )
    return findings


def _active_workspace_findings(base: Path) -> list[ConventionFinding]:
    from clusterctl.paths import workspace_parent, workspace_relpath

    findings: list[ConventionFinding] = []
    try:
        ctx = ClusterContext.load()
        ws = ctx.workspace_root.resolve()
        try:
            rel_path = ws.relative_to(workspace_parent(base))
        except ValueError:
            rel_path = workspace_relpath(ctx.cluster_id)
        label = f"workspace/{rel_path}"
        if ws.is_dir():
            findings.append(
                ConventionFinding(
                    severity="ok",
                    code="workspace_runtime_ok",
                    message=(
                        f"active cluster workspace: {label}/ "
                        f"(id={ctx.workspace_id})"
                    ),
                )
            )
            findings.extend(_active_workspace_ansible_findings(base, ctx))
        else:
            findings.append(
                ConventionFinding(
                    severity="warning",
                    code="workspace_runtime_missing",
                    message=f"{label}/ does not exist yet",
                    hint="./cluster run --dry-run  # or ./cluster run --phases provision",
                )
            )
    except ClusterctlError as exc:
        try:
            workspace_id = resolve_workspace_id(base)
        except ValueError as resolve_exc:
            findings.append(
                ConventionFinding(
                    severity="error",
                    code="workspace_id_resolve_failed",
                    message=f"cannot resolve workspace id: {exc}; {resolve_exc}",
                )
            )
            return findings
        findings.append(
            ConventionFinding(
                severity="warning",
                code="workspace_id_resolved_no_context",
                message=f"resolved workspace id (fallback): {workspace_id}",
                hint=str(exc),
            )
        )
    return findings


def _active_workspace_ansible_findings(base: Path, ctx: ClusterContext) -> list[ConventionFinding]:
    ws = ctx.workspace_root.resolve()
    if not ws.is_dir():
        return []

    tmp_dir = workspace_ansible_tmp_dir(ws)
    cache_dir = workspace_facts_cache_dir(ws)
    docker_executor = ctx.execution_configured.is_docker
    missing: list[str] = []
    if not docker_executor and not tmp_dir.is_dir():
        missing.append(str(tmp_dir.relative_to(base)))
    if not cache_dir.is_dir():
        missing.append(str(cache_dir.relative_to(base)))

    if not missing:
        summary = "; ".join(
            workspace_ansible_summary_lines(
                ws,
                workspace_id=ctx.workspace_id,
                controller_temp="container" if docker_executor else "workspace",
            )
        )
        return [
            ConventionFinding(
                severity="ok",
                code="workspace_ansible_runtime_ok",
                message=f"workspace ansible runtime OK ({summary})",
            )
        ]

    return [
        ConventionFinding(
            severity="warning",
            code="workspace_ansible_runtime_missing",
            message=(
                "workspace ansible runtime dirs missing (created on first ./cluster run): "
                + ", ".join(missing)
            ),
            hint=(
                "./cluster run --dry-run  # or any mutating "
                "./cluster run --phases …"
            ),
        )
    ]


def _legacy_in_repo_role_repo_findings(base: Path) -> list[ConventionFinding]:
    """Error on deprecated role repo dirs at atlas-clusterctl root (legacy layout removed)."""
    findings: list[ConventionFinding] = []

    stub_names = org_baseline_playbook_repo_names(base)
    for name in stub_names:
        path = base / name
        if not path.is_dir():
            continue

        populated = _legacy_root_is_populated(path)
        if populated:
            findings.append(
                ConventionFinding(
                    severity="error",
                    code="legacy_role_repo_in_repo",
                    message=(
                        f"legacy role repo directory at repo root: {name}/ "
                        "(removed — use playbooks cascade → workspace/<id>/repos/)"
                    ),
                    hint=f"rm -rf {name}/ — define playbooks: then ./cluster repos sync "
                    "(ADR 006)",
                )
            )
        else:
            findings.append(
                ConventionFinding(
                    severity="error",
                    code="legacy_role_repo_stub_empty",
                    message=(
                        f"empty role repo stub at repo root: {name}/ "
                        "(legacy docker bind-mount artifact)"
                    ),
                    hint=f"rm -rf {name}/ — playbook repos belong under workspace/<id>/repos/",
                )
            )
    return findings


def _root_scripts_findings(base: Path) -> list[ConventionFinding]:
    findings: list[ConventionFinding] = []

    root_scripts = base / "scripts"
    if root_scripts.is_dir():
        findings.append(
            ConventionFinding(
                severity="error",
                code="root_scripts_dir_removed",
                message="repo root scripts/ must not exist — use ./cluster",
                hint="rm -rf scripts/",
            )
        )
    return findings


def check_repo_conventions(base: Path) -> list[ConventionFinding]:
    """Return layout convention findings for repository root."""
    root = base.resolve()
    findings: list[ConventionFinding] = []

    findings.extend(
        _scan_pattern(
            root,
            JOB_NAME,
            _REPO_SCAN_SUFFIXES,
            code="job_name_forbidden",
            label="JOB_NAME must not appear in shell/yaml",
        )
    )

    for repo_name in org_baseline_playbook_repo_names(root):
        sibling = root.parent / repo_name
        if not sibling.is_dir():
            continue
        findings.extend(
            _scan_pattern(
                sibling,
                K8S_CONTROLLER,
                _SIBLING_SCAN_SUFFIXES,
                code="k8s_controller_deprecated",
                label=f"k8s_controller_* deprecated naming in {repo_name}",
            )
        )

    findings.extend(_legacy_root_findings(root))
    findings.extend(_legacy_in_repo_role_repo_findings(root))
    findings.extend(_ansible_cfg_findings(root))

    logs_dir = root / "logs"
    if logs_dir.is_dir():
        try:
            has_files = any(logs_dir.iterdir())
        except OSError:
            has_files = False
        if has_files:
            findings.append(
                ConventionFinding(
                    severity="warning",
                    code="root_logs_legacy",
                    message="root logs/ still has files — new runs should write to workspace/<id>/logs/ only",
                )
            )

    findings.extend(_workspace_dir_findings(root))
    findings.extend(_active_workspace_findings(root))
    findings.extend(_root_scripts_findings(root))
    return findings
