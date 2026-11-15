"""Phase 3: _template leaves ship atlas-*.yml + atlas-*.secrets.yml pairs."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "clusters" / "_template"

LEAF_PRODUCTS = {
    "redis": ("atlas-redis", "atlas-compute-provision", "atlas-node-foundation"),
    "kafka": ("atlas-kafka", "atlas-compute-provision", "atlas-node-foundation"),
    "clickhouse": ("atlas-clickhouse", "atlas-compute-provision", "atlas-node-foundation"),
    "mongodb": ("atlas-mongodb", "atlas-compute-provision", "atlas-node-foundation"),
    "postgresql": ("atlas-postgresql", "atlas-compute-provision", "atlas-node-foundation"),
    "jenkins_agent": ("atlas-jenkins-agent", "atlas-compute-provision", "atlas-node-foundation"),
    "gitlab_runner": ("atlas-gitlab-runner", "atlas-compute-provision", "atlas-node-foundation"),
    "infra_edge": ("atlas-infra-edge", "atlas-compute-provision", "atlas-node-foundation"),
    "k8s_full": ("atlas-k8s-core", "atlas-k8s-addons", "atlas-compute-provision", "atlas-node-foundation"),
    "devops_stack": ("atlas-devops-stack", "atlas-compute-provision", "atlas-node-foundation"),
    "mlops_stack": ("atlas-mlops-stack", "atlas-compute-provision", "atlas-node-foundation"),
    "soc_stack": ("atlas-soc-stack", "atlas-compute-provision", "atlas-node-foundation"),
    "pve_templates": ("atlas-compute-provision",),
}

DEFAULT_DIR = TEMPLATE / "default" / "group_vars" / "all"

SECRET_FORBIDDEN_IN_CATALOG = {
    "atlas-redis": ("vip_auth_pass", "redis_requirepass"),
    "atlas-clickhouse": ("clickhouse_default_password", "vip_auth_pass"),
    "atlas-mongodb": ("mongodb_admin_password", "mongodb_keyfile"),
    "atlas-postgresql": ("vip_auth_pass", "pgsql_postgres_password", "pgsql_replicator_password"),
    "atlas-jenkins-agent": ("jenkins_admin_password",),
    "atlas-compute-provision": (
        "provision_pve_ssh_password",
        "provision_proxmox_token_secret",
        "provision_dns_key_secret",
        "provision_vm_cipassword",
    ),
    "atlas-node-foundation": ("initial_password", "new_root_password", "system_user_password"),
    "atlas-infra-edge": ("stepca_init_password", "bind_apex_tsig_secret"),
    "atlas-k8s-core": ("vip_auth_pass",),
    "atlas-k8s-addons": ("grafana_admin_password",),
    "atlas-devops-stack": (
        "devops_nexus_admin_password",
        "devops_gitlab_root_password",
        "devops_jenkins_admin_password",
        "devops_gitea_admin_password",
        "devops_sonar_admin_password",
        "devops_sonar_db_password",
        "devops_defectdojo_admin_password",
        "devops_defectdojo_db_password",
        "devops_defectdojo_secret_key",
        "devops_defectdojo_credential_aes_key",
        "devops_wiki_admin_password",
        "devops_wiki_db_password",
        "devops_harbor_admin_password",
        "devops_harbor_db_password",
        "devops_harbor_core_secret",
        "devops_harbor_jobservice_secret",
        "devops_openbao_admin_password",
        "devops_portainer_admin_password",
        "devops_dns_tsig_secret",
        "devops_stepca_provisioner_password",
    ),
    "atlas-mlops-stack": (
        "mlops_postgres_password",
        "mlops_mlflow_db_password",
        "mlops_mlflow_admin_password",
        "mlops_airflow_db_password",
        "mlops_airflow_admin_password",
        "mlops_airflow_web_secret",
        "mlops_superset_db_password",
        "mlops_superset_admin_password",
        "mlops_superset_secret_key",
        "mlops_redis_password",
        "mlops_jupyterhub_admin_password",
        "mlops_portainer_admin_password",
        "mlops_dns_tsig_secret",
        "mlops_stepca_provisioner_password",
    ),
    "atlas-soc-stack": (
        "soc_iris_db_password",
        "soc_iris_rabbitmq_password",
        "soc_iris_secret_key",
        "soc_iris_password_salt",
        "soc_iris_admin_password",
        "soc_wazuh_indexer_password",
        "soc_wazuh_dashboard_password",
        "soc_wazuh_api_password",
        "soc_cortex_secret_key",
        "soc_misp_db_password",
        "soc_misp_db_root_password",
        "soc_misp_redis_password",
        "soc_misp_admin_password",
        "soc_misp_admin_key",
        "soc_greenbone_db_password",
        "soc_greenbone_admin_password",
        "soc_shuffle_admin_password",
        "soc_shuffle_opensearch_password",
        "soc_shuffle_api_key",
        "soc_portainer_admin_password",
        "soc_dns_tsig_secret",
        "soc_stepca_provisioner_password",
    ),
}


class TemplateSecretsPhase3Test(unittest.TestCase):
    def test_no_legacy_secrets_example_under_clusters(self) -> None:
        hits = list((Path(__file__).resolve().parents[1] / "clusters").rglob("secrets.yml.example"))
        self.assertEqual(hits, [], hits)

    def test_each_leaf_has_product_pairs(self) -> None:
        for leaf, products in LEAF_PRODUCTS.items():
            all_dir = TEMPLATE / leaf / "group_vars" / "all"
            for product in products:
                cat = all_dir / f"{product}.yml"
                self.assertTrue(cat.is_file(), cat)
                catalog = cat.read_text(encoding="utf-8")
                catalog_keys = set(yaml.safe_load(catalog) or {})
                sec_leaf = all_dir / f"{product}.secrets.yml"
                sec_default = DEFAULT_DIR / f"{product}.secrets.yml"
                secrets_keys: set[str] = set()
                if sec_leaf.is_file():
                    secrets_keys |= set(yaml.safe_load(sec_leaf.read_text(encoding="utf-8")) or {})
                if sec_default.is_file():
                    secrets_keys |= set(
                        yaml.safe_load(sec_default.read_text(encoding="utf-8")) or {}
                    )
                self.assertTrue(
                    secrets_keys or sec_leaf.is_file() or sec_default.is_file(),
                    f"{leaf}/{product}: secrets overlay missing on leaf and _template/default",
                )
                for key in SECRET_FORBIDDEN_IN_CATALOG.get(product, ()):
                    self.assertNotIn(key, catalog_keys, f"{leaf}/{product}: {key} still in catalog")
                    if product != "atlas-kafka":
                        self.assertIn(
                            key,
                            secrets_keys,
                            f"{leaf}/{product}: {key} missing from leaf+_template/default secrets",
                        )


if __name__ == "__main__":
    unittest.main()
