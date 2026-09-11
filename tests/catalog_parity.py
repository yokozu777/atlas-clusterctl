"""Phase 5 helpers: sibling ↔ template ↔ inventory key parity.

Orchestrated leaves declare DNS identity in every ``atlas-*.yml`` that uses it
(ADR 003 — no ``cluster.yml``). Path/workspace keys are injected by clusterctl.
Sibling standalone catalogs may still declare identity keys for ``./run.sh``.
Compute templates only ship the current stack's TF maps.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SIBLING_ROOT = REPO_ROOT.parent
TEMPLATE_ROOT = REPO_ROOT / "clusters" / "_template"

# Sibling repo basename == product overlay stem.
PRODUCT_REPOS: tuple[str, ...] = (
    "atlas-redis",
    "atlas-kafka",
    "atlas-postgresql",
    "atlas-jenkins-agent",
    "atlas-gitlab-runner",
    "atlas-infra-edge",
    "atlas-k8s-core",
    "atlas-k8s-addons",
    "atlas-compute-provision",
    "atlas-node-foundation",
)

LEAF_PRODUCTS: dict[str, tuple[str, ...]] = {
    "redis": ("atlas-redis", "atlas-compute-provision", "atlas-node-foundation"),
    "kafka": ("atlas-kafka", "atlas-compute-provision", "atlas-node-foundation"),
    "postgresql": ("atlas-postgresql", "atlas-compute-provision", "atlas-node-foundation"),
    "jenkins_agent": ("atlas-jenkins-agent", "atlas-compute-provision", "atlas-node-foundation"),
    "gitlab_runner": ("atlas-gitlab-runner", "atlas-compute-provision", "atlas-node-foundation"),
    "infra_edge": ("atlas-infra-edge", "atlas-compute-provision", "atlas-node-foundation"),
    "k8s_full": (
        "atlas-k8s-core",
        "atlas-k8s-addons",
        "atlas-compute-provision",
        "atlas-node-foundation",
    ),
}

LEAF_STACK: dict[str, str] = {
    "redis": "redis",
    "kafka": "kafka",
    "postgresql": "postgresql",
    "jenkins_agent": "jenkins",
    "gitlab_runner": "gitlab_runner",
    "infra_edge": "infra",
    "k8s_full": "k8s",
}

ALL_STACKS: frozenset[str] = frozenset(
    {"redis", "kafka", "postgresql", "jenkins", "gitlab_runner", "infra", "k8s"}
)

# Identity / controller / workspace — sibling-standalone only (not template/inventory SoT).
PARITY_EXCLUDE: frozenset[str] = frozenset(
    {
        "ansible_user",
        "atlas_cluster_root",
        "atlas_clusters_root",
        "atlas_inventory_root",
        "cluster_domain",
        "cluster_id",
        "cluster_workspace_id",
        "cluster_workspace_parent",
        "cluster_workspace_root",
        "dns_domain_suffix",
        "k8s_cluster_domain",
        "dns_server_ip",
        "controller_bin_dir",
        "controller_ca_cert_dir",
        "controller_ca_cert_path",
        "controller_ssl_cert_file",
        "controller_tls_environment",
        "controller_helm_cache_dir",
        "controller_helm_config_dir",
        "controller_kubeconfig",
        "controller_manifests_dir",
        "controller_python_venv",
        "controller_reports_dir",
        "controller_secrets_dir",
        "controller_staging_dir",
        "controller_workspace",
        "k8s_admin_home",
        "k8s_admin_user",
        "k8s_ca_cert_filename",
        "k8s_cluster_fact_host",
        "k8s_control_plane_master_host",
        "k8s_control_plane_scripts_dir",
        "k8s_control_plane_ssh_extra_args",
        "k8s_control_plane_ssh_private_key_file",
        "k8s_control_plane_ssh_target",
        "k8s_control_plane_ssh_user",
        "k8s_copy_kubeconfig_to_admin_home",
        "k8s_kubeadm_admin_kubeconfig",
        "k8s_node_kubeconfig",
        "build_state_file",
        "build_workdir",
        "keycloak_tf_workspace",
        "k8s_lb_dns_tf_workspace",
        "provision_generated_variables_tf",
        "provision_tf_state_cluster_path",
        "provision_tf_state_local_dir",
        "provision_tf_state_repo_dir",
        "provision_tf_state_repo_file",
        "provision_tf_state_repo_prefix",
        "provision_tf_workspace_dir",
        # Golden PVE factory catalog — sibling defaults; stack leaves omit these
        # (SoT: ``_template/pve_templates`` only).
        "build_cloud_image_customize_enabled",
        "build_cloud_image_packages",
        "provision_pve_templates",
        "provision_pve_upload_dir",
        # Infra-edge leaf nginx mirror baking (sibling standalone uses pkg_repo_base).
        "pkg_repo_nginx_domain",
        # Optional inventory split; templates may keep monolithic pkg_repos only.
        "pkg_repos_extra",
    }
)

# Must never appear as active keys in product catalogs (live in *.secrets.yml).
SECRET_FORBIDDEN_IN_CATALOG: dict[str, frozenset[str]] = {
    "atlas-redis": frozenset({"vip_auth_pass", "redis_requirepass"}),
    "atlas-kafka": frozenset(),
    "atlas-postgresql": frozenset(
        {"vip_auth_pass", "pgsql_postgres_password", "pgsql_replicator_password"}
    ),
    "atlas-jenkins-agent": frozenset(
        {"jenkins_admin_password", "jenkins_java_truststore_password"}
    ),
    "atlas-gitlab-runner": frozenset({"gitlab_runner_authentication_token"}),
    "atlas-compute-provision": frozenset(
        {
            "provision_pve_ssh_password",
            "provision_proxmox_token_id",
            "provision_proxmox_token_secret",
            "provision_dns_key_secret",
            "provision_vm_cipassword",
        }
    ),
    "atlas-node-foundation": frozenset(
        {"initial_password", "new_root_password", "system_user_password"}
    ),
    "atlas-infra-edge": frozenset(
        {
            "bind_apex_tsig_secret",
            "bind_k8s_tsig_secret",
            "bind_istio_tsig_secret",
            "external_dns_tsig_secret",
            "external_dns_istio_tsig_secret",
            "stepca_init_password",
            "nginx_cache_sync_ssh_password",
            "infra_cache_seed_publish_registry_user",
            "infra_cache_seed_publish_registry_password",
            "infra_cache_seed_load_registry_user",
            "infra_cache_seed_load_registry_password",
        }
    ),
    "atlas-k8s-core": frozenset({"vip_auth_pass", "k8s_lb_dns_key_secret"}),
    "atlas-k8s-addons": frozenset(
        {
            "grafana_admin_password",
            "keycloak_admin_password",
            "keycloak_oidc_user_password",
            "oauth2_proxy_client_secret",
            "oauth2_proxy_cookie_secret",
            "envoy_gateway_oidc_client_secret",
            "vault_oidc_client_secret",
            "argocd_oidc_client_secret",
            "external_dns_tsig_secret",
            "external_dns_istio_tsig_secret",
            "elastic_password",
            "elastic_cert_password",
            "elastic_logger_password",
            "elastic_admin_password",
            "elastic_jaeger_password",
            "kibana_elastic_password",
            "kibana_encryption_key",
            "argocd_admin_password_bcrypt",
            "ceph_dashboard_password",
            "sentry_smtp_password",
            "sentry_admin_password",
            "graylog_root_password",
            "vault_admin_password",
        }
    ),
}

# Active keys required in sibling/template *.secrets.yml (scaffolds use CHANGEME).
SECRET_REQUIRED_IN_SECRETS: dict[str, frozenset[str]] = {
    "atlas-redis": frozenset({"vip_auth_pass", "redis_requirepass"}),
    "atlas-postgresql": frozenset(
        {"vip_auth_pass", "pgsql_postgres_password", "pgsql_replicator_password"}
    ),
    "atlas-jenkins-agent": frozenset({"jenkins_admin_password"}),
    "atlas-gitlab-runner": frozenset({"gitlab_runner_authentication_token"}),
    "atlas-compute-provision": frozenset(
        {
            "provision_pve_ssh_password",
            "provision_proxmox_token_id",
            "provision_proxmox_token_secret",
            "provision_dns_key_secret",
            "provision_vm_cipassword",
        }
    ),
    "atlas-node-foundation": frozenset(
        {"initial_password", "new_root_password", "system_user_password"}
    ),
    "atlas-infra-edge": frozenset(
        {
            "bind_apex_tsig_secret",
            "bind_k8s_tsig_secret",
            "bind_istio_tsig_secret",
            "external_dns_tsig_secret",
            "external_dns_istio_tsig_secret",
            "stepca_init_password",
            "nginx_cache_sync_ssh_password",
            "infra_cache_seed_publish_registry_user",
            "infra_cache_seed_publish_registry_password",
            "infra_cache_seed_load_registry_user",
            "infra_cache_seed_load_registry_password",
        }
    ),
    "atlas-k8s-core": frozenset({"vip_auth_pass"}),
    "atlas-k8s-addons": frozenset(
        {
            "grafana_admin_password",
            "keycloak_admin_password",
            "keycloak_oidc_user_password",
            "oauth2_proxy_client_secret",
            "oauth2_proxy_cookie_secret",
            "envoy_gateway_oidc_client_secret",
            "vault_oidc_client_secret",
            "argocd_oidc_client_secret",
            "external_dns_tsig_secret",
            "external_dns_istio_tsig_secret",
            "elastic_password",
            "elastic_cert_password",
            "elastic_logger_password",
            "elastic_admin_password",
            "elastic_jaeger_password",
            "kibana_elastic_password",
            "kibana_encryption_key",
            "argocd_admin_password_bcrypt",
            "ceph_dashboard_password",
            "sentry_smtp_password",
            "sentry_admin_password",
            "graylog_root_password",
            "vault_admin_password",
        }
    ),
}

# Inventory labs: only secrets that Phase 4 actually materialised (site-specific).
INVENTORY_SECRET_REQUIRED: dict[str, frozenset[str]] = {
    "atlas-redis": frozenset({"vip_auth_pass", "redis_requirepass"}),
    "atlas-postgresql": frozenset(
        {"vip_auth_pass", "pgsql_postgres_password", "pgsql_replicator_password"}
    ),
    "atlas-jenkins-agent": frozenset({"jenkins_admin_password"}),
    "atlas-gitlab-runner": frozenset({"gitlab_runner_authentication_token"}),
    "atlas-compute-provision": frozenset(
        {
            "provision_pve_ssh_password",
            "provision_proxmox_token_id",
            "provision_proxmox_token_secret",
            "provision_dns_key_secret",
            "provision_vm_cipassword",
        }
    ),
    "atlas-node-foundation": frozenset({"initial_password"}),
    "atlas-infra-edge": frozenset(
        {
            "external_dns_tsig_secret",
            "external_dns_istio_tsig_secret",
            "stepca_init_password",
            "nginx_cache_sync_ssh_password",
        }
    ),
    "atlas-k8s-core": frozenset({"vip_auth_pass"}),
    "atlas-k8s-addons": frozenset(
        {
            "grafana_admin_password",
            "keycloak_admin_password",
            "keycloak_oidc_user_password",
            "oauth2_proxy_client_secret",
            "oauth2_proxy_cookie_secret",
            "envoy_gateway_oidc_client_secret",
            "vault_oidc_client_secret",
            "argocd_oidc_client_secret",
            "external_dns_tsig_secret",
            "external_dns_istio_tsig_secret",
            "elastic_password",
            "elastic_cert_password",
            "elastic_logger_password",
            "elastic_admin_password",
            "elastic_jaeger_password",
            "kibana_elastic_password",
            "kibana_encryption_key",
            "argocd_admin_password_bcrypt",
            "ceph_dashboard_password",
            "sentry_smtp_password",
            "sentry_admin_password",
            "graylog_root_password",
            "vault_admin_password",
        }
    ),
}

# Inventory must-add by product (Phase 0/4) — checked against cascade-merged vars.
# Not keyed by cluster path (ci/*, dev/*); discover leaves at runtime.
PRODUCT_MUST_ADD: dict[str, frozenset[str]] = {
    "atlas-redis": frozenset({"vip_address", "haproxy_log_facility"}),
    "atlas-kafka": frozenset({"kafka_controller_hosts", "kafka_broker_hosts"}),
    "atlas-postgresql": frozenset(
        {"vip_address", "haproxy_log_facility", "pgsql_pgdg_repo_from_init"}
    ),
    "atlas-jenkins-agent": frozenset({"jenkins_agent_hosts", "jenkins_url"}),
    "atlas-gitlab-runner": frozenset(
        {"gitlab_runner_hosts", "gitlab_url", "gitlab_runner_executor"}
    ),
    "atlas-infra-edge": frozenset(
        {"infra_platform_hosts", "nginx_cache_sync_skip_if_fresh"}
    ),
    "atlas-k8s-core": frozenset(
        {"vip_address", "k8s_lb_dns_tf_manage_a_record", "ntp_servers"}
    ),
    "atlas-k8s-addons": frozenset({"debug_tooling_calicoctl_enabled"}),
    "atlas-compute-provision": frozenset(
        {"provision_stack", "gitea_host", "provision_dns_tf_manage_a_records"}
    ),
    "atlas-node-foundation": frozenset({"node_foundation_init_hosts"}),
}

# Thin infra-edge client bridge on k8s leaves (no full infra_platform SoT).
PRODUCT_MUST_ADD_THIN_INFRA: frozenset[str] = frozenset(
    {"dns_server_ip", "nginx_cache_sync_skip_if_fresh"}
)


def load_mapping(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_keys(path: Path) -> set[str]:
    return set(load_mapping(path))


def product_pair_keys(all_dir: Path, product: str) -> tuple[set[str], set[str], set[str]]:
    cat = load_keys(all_dir / f"{product}.yml")
    sec = load_keys(all_dir / f"{product}.secrets.yml")
    return cat, sec, cat | sec


def sibling_all_dir(product: str) -> Path:
    return SIBLING_ROOT / product / "group_vars" / "all"


def sibling_present(product: str) -> bool:
    return (sibling_all_dir(product) / f"{product}.yml").is_file()


def other_stack_map_keys(stack: str) -> frozenset[str]:
    """TF inventory/module maps for stacks other than ``stack``."""
    keys: set[str] = set()
    for other in ALL_STACKS - {stack}:
        keys.add(f"provision_inventory_group_map_{other}")
        keys.add(f"provision_tf_module_map_{other}")
    return frozenset(keys)


def parity_keys(keys: set[str], *, stack: str | None = None) -> set[str]:
    out = set(keys) - PARITY_EXCLUDE
    if stack is not None:
        out -= other_stack_map_keys(stack)
    return out


def assert_no_forbidden_secrets(catalog_keys: set[str], product: str) -> list[str]:
    forbidden = SECRET_FORBIDDEN_IN_CATALOG.get(product, frozenset())
    return sorted(catalog_keys & forbidden)


def leaf_product_overlays(all_dir: Path) -> tuple[str, ...]:
    """Product stems from ``atlas-*.yml`` catalogs present on a leaf (not secrets)."""
    if not all_dir.is_dir():
        return ()
    found: list[str] = []
    for path in sorted(all_dir.glob("atlas-*.yml")):
        name = path.name
        if name.endswith(".secrets.yml"):
            continue
        stem = name[: -len(".yml")]
        if stem in PRODUCT_REPOS:
            found.append(stem)
    return tuple(found)


def must_add_for_product(product: str, merged_vars: dict) -> frozenset[str]:
    """Required site keys for *product*, with thin infra / factory-leaf profiles."""
    if product == "atlas-infra-edge" and "infra_platform_hosts" not in merged_vars:
        return PRODUCT_MUST_ADD_THIN_INFRA
    required = PRODUCT_MUST_ADD.get(product, frozenset())
    if product == "atlas-compute-provision" and not merged_vars.get("provision_stack"):
        # Golden PVE factory leaves omit guest TF stack selector.
        return required - {"provision_stack"}
    return required


def foundation_repo_surface_ok(merged_vars: dict) -> bool:
    """True when cascade has any pkg_repos and/or pkg_repos_extra entries."""
    repos = merged_vars.get("pkg_repos") or []
    extra = merged_vars.get("pkg_repos_extra") or []
    if not isinstance(repos, list):
        repos = []
    if not isinstance(extra, list):
        extra = []
    return (len(repos) + len(extra)) > 0
