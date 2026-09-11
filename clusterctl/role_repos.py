"""Deprecated shim — use :mod:`clusterctl.playbooks_repos`.

Kept for soft-compat Phase 5 so older imports (`RoleRepoSpec`,
``RoleReposConfig``, ``build_role_repos_config`` callers via this module)
continue to resolve. New code must import playbooks-named symbols.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "clusterctl.role_repos is deprecated; import from clusterctl.playbooks_repos "
    "(or clusterctl.playbooks_resolve / clusterctl.playbooks_paths)",
    DeprecationWarning,
    stacklevel=2,
)

from clusterctl.playbooks_repos import (  # noqa: E402
    ORG_BASELINE_CLUSTER_ID,
    ORG_BASELINE_CLUSTER_YAML,
    REFERENCE_CLUSTER_YAML,
    ResolvedPlaybookRepo,
    ResolvedPlaybooksRepos,
    WORKSPACE_REPOS_DIRNAME,
    ansible_roles_dir_ready,
    ansible_roles_subpath,
    empty_resolved_playbooks_repos,
    org_baseline_cluster_yaml_path,
    playbook_repos_summary_lines,
    require_playbook_repos,
    resolve_ansible_roles_dir_for_spec,
    resolve_local_repo_path,
    resolved_playbook_repos_from_config,
    uses_playbook_repos,
    validate_resolved_playbook_repo,
    workspace_materialized_playbook_repo_root,
    workspace_materialized_repo_root,
    workspace_repos_root,
)
from clusterctl.pipeline_fixture import REFERENCE_CLUSTER_ID  # noqa: E402
from clusterctl.playbooks_validate import validate_org_baseline_playbooks  # noqa: E402

# Legacy type / function aliases (same objects).
RoleRepoSpec = ResolvedPlaybookRepo
RoleReposConfig = ResolvedPlaybooksRepos
empty_role_repos_config = empty_resolved_playbooks_repos
role_repos_defaults_path = org_baseline_cluster_yaml_path
validate_role_repo_spec = validate_resolved_playbook_repo
role_repos_specs_from_playbooks = resolved_playbook_repos_from_config
uses_playbooks_resolver = uses_playbook_repos
require_playbooks_resolver = require_playbook_repos
role_repos_summary_lines = playbook_repos_summary_lines
validate_role_repos_defaults_file = validate_org_baseline_playbooks

__all__ = [
    "ORG_BASELINE_CLUSTER_ID",
    "ORG_BASELINE_CLUSTER_YAML",
    "REFERENCE_CLUSTER_ID",
    "REFERENCE_CLUSTER_YAML",
    "ResolvedPlaybookRepo",
    "ResolvedPlaybooksRepos",
    "RoleRepoSpec",
    "RoleReposConfig",
    "WORKSPACE_REPOS_DIRNAME",
    "ansible_roles_dir_ready",
    "ansible_roles_subpath",
    "empty_resolved_playbooks_repos",
    "empty_role_repos_config",
    "org_baseline_cluster_yaml_path",
    "playbook_repos_summary_lines",
    "require_playbook_repos",
    "require_playbooks_resolver",
    "resolve_ansible_roles_dir_for_spec",
    "resolve_local_repo_path",
    "resolved_playbook_repos_from_config",
    "role_repos_defaults_path",
    "role_repos_specs_from_playbooks",
    "role_repos_summary_lines",
    "uses_playbook_repos",
    "uses_playbooks_resolver",
    "validate_org_baseline_playbooks",
    "validate_resolved_playbook_repo",
    "validate_role_repo_spec",
    "validate_role_repos_defaults_file",
    "workspace_materialized_playbook_repo_root",
    "workspace_materialized_repo_root",
    "workspace_repos_root",
]
