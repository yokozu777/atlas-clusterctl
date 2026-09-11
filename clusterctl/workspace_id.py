"""Resolve cluster workspace id (Ansible cluster_workspace_id / shell bootstrap)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from clusterctl.cluster_vars_loader import discover_group_vars_all, load_cluster_vars_from_paths

_VALID_ID = re.compile(r"^[a-zA-Z0-9.-]+$")
_JINJA_MARKERS = ("{{", "}}")
_ANSIBLE_EXPR_MARKERS = ("lookup(", "| default(")
_CANONICAL_DEFAULT_CONFIG = Path("clusters") / "default" / "default"


class WorkspaceIdSource(str, Enum):
    """Where the resolved workspace id came from."""

    ENV = "CLUSTER_WORKSPACE_ID"
    CLUSTER_YAML = "cluster.yaml workspace_id"
    VARS_LITERAL = "cluster_workspace_id (literal)"
    CLUSTER_DOMAIN = "cluster_domain"


@dataclass(frozen=True)
class WorkspaceIdResolution:
    workspace_id: str
    source: WorkspaceIdSource


def reset_workspace_id_warnings_for_tests() -> None:
    """No-op retained for test compatibility (flat-default fallback removed)."""
    return


def _default_cluster_vars_fallback(repo_root: Path) -> list[Path]:
    """Merge org baseline ``group_vars/all`` from ``clusters/default/default`` only."""
    canonical = (repo_root / _CANONICAL_DEFAULT_CONFIG).resolve()
    if canonical.is_dir():
        files = list(discover_group_vars_all(canonical))
        if files:
            return files
    return []


def _load_vars(
    repo_root: Path,
    group_var_files: list[Path] | None = None,
) -> dict:
    if group_var_files:
        existing = [path for path in group_var_files if path.is_file()]
        if existing:
            return load_cluster_vars_from_paths(existing)

    fallback = _default_cluster_vars_fallback(repo_root)
    if fallback:
        return load_cluster_vars_from_paths(fallback)
    return {}


def _contains_jinja(text: str) -> bool:
    return any(marker in text for marker in _JINJA_MARKERS)


def _contains_ansible_expr(text: str) -> bool:
    return any(marker in text for marker in _ANSIBLE_EXPR_MARKERS)


def _substitute_dns_suffix(text: str, suffix: str) -> str:
    return text.replace("{{ dns_domain_suffix }}", suffix)


def _literal_var_value(raw: object) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or _contains_jinja(text) or _contains_ansible_expr(text):
        return None
    return text


def _resolve_cluster_domain(vars_data: dict) -> str:
    suffix = str(vars_data.get("dns_domain_suffix") or "").strip()
    raw = vars_data.get("cluster_domain")
    if raw is None:
        return ""

    domain = str(raw).strip()
    if "{{ dns_domain_suffix }}" in domain:
        domain = _substitute_dns_suffix(domain, suffix)
    if _contains_jinja(domain):
        return ""
    return domain.strip()


def _resolve_k8s_cluster_domain(vars_data: dict) -> str:
    suffix = str(vars_data.get("dns_domain_suffix") or "").strip()
    raw = vars_data.get("k8s_cluster_domain")
    if raw is None:
        return ""

    domain = str(raw).strip()
    if domain == "{{ cluster_domain }}" or "{{ cluster_domain }}" in domain:
        resolved = _resolve_cluster_domain(vars_data)
        if resolved:
            return resolved
        if "{{ cluster_domain }}" in domain and not _contains_jinja(domain.replace("{{ cluster_domain }}", "")):
            return domain.replace("{{ cluster_domain }}", "").strip()

    if "{{ dns_domain_suffix }}" in domain:
        domain = _substitute_dns_suffix(domain, suffix)
    if _contains_jinja(domain):
        return ""
    return domain.strip()


def _resolve_from_vars(vars_data: dict) -> tuple[str, WorkspaceIdSource | None]:
    literal = _literal_var_value(vars_data.get("cluster_workspace_id"))
    if literal:
        return literal, WorkspaceIdSource.VARS_LITERAL

    domain = _resolve_cluster_domain(vars_data)
    if domain:
        return domain, WorkspaceIdSource.CLUSTER_DOMAIN

    # k8s_cluster_domain alone is not a workspace-id source (soft-compat Phase 4).
    # Prefer cluster_domain (+ optional k8s_cluster_domain: "{{ cluster_domain }}").
    return "", None


def _validate_workspace_id(workspace_id: str) -> str:
    if not workspace_id:
        raise ValueError(
            "cluster workspace id is empty — set CLUSTER_WORKSPACE_ID or "
            "cluster_domain in cluster vars"
        )
    if _contains_jinja(workspace_id):
        raise ValueError(
            f"unresolved Jinja in workspace id {workspace_id!r} — "
            "fix cluster vars or set CLUSTER_WORKSPACE_ID"
        )
    if not _VALID_ID.match(workspace_id):
        raise ValueError(
            f"invalid workspace id {workspace_id!r} — allowed charset: a-zA-Z0-9.-"
        )
    return workspace_id


def resolve_cluster_domain_from_vars(vars_data: dict) -> str:
    """Resolve ``cluster_domain`` after substituting ``dns_domain_suffix``."""
    return _resolve_cluster_domain(vars_data)


def resolve_k8s_cluster_domain_from_vars(vars_data: dict) -> str:
    """Resolve ``k8s_cluster_domain`` (including ``{{ cluster_domain }}`` alias)."""
    return _resolve_k8s_cluster_domain(vars_data)


def literal_cluster_workspace_id(vars_data: dict) -> str | None:
    """Return ``cluster_workspace_id`` when set to a plain string (no Jinja/Ansible expr)."""
    return _literal_var_value(vars_data.get("cluster_workspace_id"))


def resolve_workspace_id_details(
    repo_root: Path | None = None,
    *,
    cluster_var_file: Path | None = None,
    group_var_files: list[Path] | None = None,
    override: str | None = None,
) -> WorkspaceIdResolution:
    """
    Resolve workspace id with source metadata.

    Priority:
      CLUSTER_WORKSPACE_ID → cluster.yaml workspace_id → literal cluster_workspace_id
      → cluster_domain

    ``k8s_cluster_domain`` alone is not a workspace-id source (soft-compat Phase 4).
    """
    root = repo_root or Path(os.environ.get("ATLAS_CLUSTER_ROOT", Path.cwd()))

    env_override = os.environ.get("CLUSTER_WORKSPACE_ID", "").strip()
    if env_override:
        return WorkspaceIdResolution(
            _validate_workspace_id(env_override),
            WorkspaceIdSource.ENV,
        )
    if override:
        return WorkspaceIdResolution(
            _validate_workspace_id(override),
            WorkspaceIdSource.CLUSTER_YAML,
        )

    paths: list[Path] = []
    if group_var_files:
        paths.extend(group_var_files)
    elif cluster_var_file is not None and cluster_var_file.is_file():
        paths.append(cluster_var_file)

    workspace_id, source = _resolve_from_vars(_load_vars(root, paths or None))
    if source is None:
        raise ValueError(
            "cluster workspace id is empty — set CLUSTER_WORKSPACE_ID or "
            "cluster_domain in cluster vars"
        )
    return WorkspaceIdResolution(_validate_workspace_id(workspace_id), source)


def resolve_workspace_id(
    repo_root: Path | None = None,
    *,
    cluster_var_file: Path | None = None,
    group_var_files: list[Path] | None = None,
    override: str | None = None,
) -> str:
    return resolve_workspace_id_details(
        repo_root,
        cluster_var_file=cluster_var_file,
        group_var_files=group_var_files,
        override=override,
    ).workspace_id
