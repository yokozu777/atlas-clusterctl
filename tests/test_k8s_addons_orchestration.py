"""Orchestration contract for atlas-k8s-addons via clusterctl.

SoT: ``_template/k8s_full``. Optional local lab: discovered via ``lab_id_for('k8s')`` (see docs/local-labs.md).
"""

from __future__ import annotations

import os
import unittest

import yaml

from clusterctl.context import ClusterContext
from clusterctl.inventory import extract_inventory_groups
from clusterctl.pipeline_fixture import load_public_reference_cluster_config
from tests.lab_support import (
    lab_id_for,
    lab_path_for,
    skip_unless_stack,

    group_vars_all_file,
    PUBLIC_K8S_TEMPLATE,
    ROOT,
)

STACK = "k8s"
TEMPLATE = PUBLIC_K8S_TEMPLATE

# Order matches playbooks/cluster_addons.yaml (first invocation: 110_workspace).
EXPECTED_ADDONS_TAGS = (
    "110_workspace",
    "120_controller_tooling",
    "130_validate_vars",
    "140_fetch_kubeconfig",
    "210_helm_bootstrap",
    "220_calico",
    "310_prometheus",
    "320_blackbox",
    "330_prometheus_adapter",
    "340_calico_metrics",
    "410_snapshotter",
    "420_rook_operator",
    "430_rook_cluster",
    "440_rook_csi_drivers",
    "450_thanos",
    "510_metallb",
    "520_envoy_gateway",
    "530_external_dns",
    "540_cert_manager",
    "550_trust_manager",
    "560_apply_ingress",
    "610_elasticsearch_prepare",
    "620_elasticsearch",
    "630_kibana_prepare",
    "640_kibana",
    "650_fluentbit",
    "710_istio",
    "720_external_dns_istio",
    "730_tracing",
    "740_kiali",
    "800_chaos_mesh",
    "810_falco",
    "820_kyverno",
    "830_policy_reporter",
    "840_trivy",
    "910_cloudnative_pg",
    "920_keycloak",
    "930_keycloak_realm",
    "940_apiserver_oidc",
    "941_k8s_oidc",
    "942_pinniped",
    "950_mailu",
    "954_opencost",
    "960_oauth2_proxy",
    "961_apply_oidc_ingress",
    "962_headlamp",
    "970_consul",
    "971_vault",
    "972_external_secrets",
    "980_argocd",
    "982_argocd_rollouts",
    "990_rook_ceph_dashboard",
    "992_kibana_dashboards",
    "994_sentry",
    "996_cluster_report",
    "999_debug_tooling",
)

LOCALHOST_TAGS = tuple(
    t for t in EXPECTED_ADDONS_TAGS if t not in ("940_apiserver_oidc", "999_debug_tooling")
)


class K8sAddonsOrchestrationTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import list_deployable_cluster_ids, repo_root

        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    def test_phases_include_k8s_addons(self) -> None:
        config = load_public_reference_cluster_config(ROOT)
        assert config.phases is not None
        phases = config.phases.phases
        self.assertIn("atlas-k8s-core/cluster", phases)
        self.assertIn("atlas-k8s-addons/addons", phases)
        self.assertLess(
            phases.index("atlas-k8s-core/cluster"),
            phases.index("atlas-k8s-addons/addons"),
        )
        aliases = config.phases.phase_aliases
        self.assertEqual(aliases.get("k8s-addons"), "atlas-k8s-addons/addons")
        self.assertEqual(aliases.get("k8s-core"), "atlas-k8s-core/cluster")

    def test_playbooks_include_atlas_k8s_addons(self) -> None:
        config = load_public_reference_cluster_config(ROOT)
        assert config.playbooks is not None
        self.assertIn("atlas-k8s-addons", config.playbooks.repos)
        entry = config.playbooks.repos["atlas-k8s-addons"].entries["addons"]
        self.assertEqual(entry.file, "playbooks/cluster_addons.yaml")
        tags = [inv.tags for inv in entry.invocations]
        self.assertEqual(tags, list(EXPECTED_ADDONS_TAGS))
        self.assertLess(tags.index("120_controller_tooling"), tags.index("130_validate_vars"))
        self.assertLess(tags.index("130_validate_vars"), tags.index("140_fetch_kubeconfig"))
        self.assertLess(tags.index("140_fetch_kubeconfig"), tags.index("210_helm_bootstrap"))
        # Kiali CR targets istio_namespace; tracing must exist for Jaeger wait.
        self.assertLess(tags.index("710_istio"), tags.index("740_kiali"))
        self.assertLess(tags.index("720_external_dns_istio"), tags.index("740_kiali"))
        self.assertLess(tags.index("730_tracing"), tags.index("740_kiali"))
        self.assertLess(tags.index("710_istio"), tags.index("730_tracing"))
        self.assertLess(tags.index("960_oauth2_proxy"), tags.index("961_apply_oidc_ingress"))
        self.assertLess(tags.index("961_apply_oidc_ingress"), tags.index("962_headlamp"))
        self.assertLess(tags.index("941_k8s_oidc"), tags.index("950_mailu"))
        self.assertLess(tags.index("942_pinniped"), tags.index("950_mailu"))
        self.assertLess(tags.index("830_policy_reporter"), tags.index("840_trivy"))
        self.assertLess(tags.index("840_trivy"), tags.index("910_cloudnative_pg"))
        self.assertLess(tags.index("840_trivy"), tags.index("954_opencost"))
        self.assertLess(tags.index("954_opencost"), tags.index("960_oauth2_proxy"))
        self.assertLess(tags.index("972_external_secrets"), tags.index("980_argocd"))
        self.assertLess(tags.index("810_falco"), tags.index("820_kyverno"))
        self.assertLess(tags.index("820_kyverno"), tags.index("830_policy_reporter"))
        self.assertLess(tags.index("830_policy_reporter"), tags.index("910_cloudnative_pg"))
        self.assertLess(tags.index("980_argocd"), tags.index("982_argocd_rollouts"))
        self.assertLess(tags.index("982_argocd_rollouts"), tags.index("990_rook_ceph_dashboard"))
        self.assertLess(tags.index("994_sentry"), tags.index("996_cluster_report"))
        self.assertLess(tags.index("996_cluster_report"), tags.index("999_debug_tooling"))

    def test_atlas_k8s_core_targeting(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        leaves = [TEMPLATE]
        if lab:
            leaves.append(path)
        for leaf in leaves:
            core = (leaf / "group_vars" / "all" / "atlas-k8s-core.yml").read_text(encoding="utf-8")
            self.assertIn("k8s_master_hosts: k8s_masters", core, leaf)
            self.assertIn("k8s_worker_hosts: k8s_workers", core, leaf)
            self.assertIn("groups.get(k8s_master_hosts", core, leaf)
        # Public template documents the addons contract path.
        addons = (TEMPLATE / "group_vars" / "all" / "atlas-k8s-addons.yml").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/k8s-addons.md", addons)

    def test_inventory_has_k8s_groups(self) -> None:
        groups = extract_inventory_groups(TEMPLATE / "hosts")
        for name in ("k8s_masters", "k8s_workers"):
            self.assertIn(name, groups)

    @skip_unless_stack(STACK)
    def test_lab_inventory_has_k8s_groups(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        groups = extract_inventory_groups(path / "hosts")
        for name in ("k8s_masters", "k8s_workers"):
            self.assertIn(name, groups)

    def test_template_invocation_limits_aligned(self) -> None:
        path = TEMPLATE / "cluster.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        inv = data["playbooks"]["atlas-k8s-addons"]["entries"]["addons"]["invocations"]
        tags = [item["tags"] for item in inv]
        self.assertEqual(tags, list(EXPECTED_ADDONS_TAGS), path)
        limits = {item["tags"]: item.get("limit") for item in inv}
        self.assertEqual(
            limits["940_apiserver_oidc"],
            "k8s_masters",
            f"{path}: 940_apiserver_oidc",
        )
        self.assertEqual(
            limits["999_debug_tooling"],
            "k8s_masters:k8s_workers",
            f"{path}: 999_debug_tooling",
        )
        for tag in LOCALHOST_TAGS:
            self.assertIsNone(limits.get(tag), f"{path}: {tag} must not set limit")

    @skip_unless_stack(STACK)
    def test_lab_invocations_match_template(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        for path in (path / "cluster.yaml", TEMPLATE / "cluster.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            inv = data["playbooks"]["atlas-k8s-addons"]["entries"]["addons"]["invocations"]
            tags = [item["tags"] for item in inv]
            self.assertEqual(tags, list(EXPECTED_ADDONS_TAGS), path)

    def test_k8s_full_template_exists(self) -> None:
        self.assertTrue(TEMPLATE.is_dir())
        content = (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas-k8s-addons", content)
        self.assertIn("k8s-addons: atlas-k8s-addons/addons", content)
        self.assertIn("playbooks/cluster_addons.yaml", content)

    def test_orchestration_docs_and_readme_links(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        docs = (ROOT / "docs" / "stacks" / "k8s-addons.md").read_text(encoding="utf-8")
        self.assertIn("k8s_master_hosts", docs)
        self.assertIn("k8s_worker_hosts", docs)
        self.assertIn("110_workspace", docs)
        self.assertIn("130_validate_vars", docs)
        self.assertIn("140_fetch_kubeconfig", docs)
        self.assertIn("710_istio`, `720_external_dns_istio`, `730_tracing`, `740_kiali", docs)
        self.assertIn("Istio NS before Kiali", docs)
        self.assertIn("980_argocd", docs)
        self.assertIn("982_argocd_rollouts", docs)
        self.assertIn("820_kyverno", docs)
        self.assertIn("830_policy_reporter", docs)
        self.assertNotIn("56_kasten", docs)
        self.assertIn("after external-secrets", docs)
        self.assertIn("996_cluster_report", docs)
        self.assertIn("999_debug_tooling", docs)
        self.assertIn("atlas-k8s-addons.yml", docs)
        self.assertIn("atlas-k8s-core", docs)
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("k8s-addons.md", index)
        clusters_doc = (ROOT / "docs" / "clusters.md").read_text(encoding="utf-8")
        self.assertIn("k8s-addons.md", clusters_doc)
        playbooks_doc = (ROOT / "docs" / "playbooks.md").read_text(encoding="utf-8")
        self.assertIn("k8s-addons.md", playbooks_doc)
        clusterctl_doc = (ROOT / "docs" / "clusterctl.md").read_text(encoding="utf-8")
        self.assertIn("k8s-addons.md", clusterctl_doc)
        core_doc = (ROOT / "docs" / "stacks" / "k8s-core.md").read_text(encoding="utf-8")
        self.assertIn("k8s-addons.md", core_doc)
        template_readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/k8s-addons.md", template_readme)
        leaf = path
        readme = None if leaf is None else leaf / "README.md"
        if readme is not None and readme.is_file():
            ref_readme = (readme).read_text(encoding="utf-8")
            self.assertIn("docs/stacks/k8s-addons.md", ref_readme)

    @skip_unless_stack(STACK)
    def test_context_loads_reference(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import clusters_root

        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)
        ctx = ClusterContext.load(cluster_id=lab)
        self.assertEqual(ctx.cluster_id, lab)
        self.assertTrue(group_vars_all_file(ctx.config_dir, "atlas-k8s-addons.yml").is_file())

    def test_k8s_full_oidc_leaf_enable_only(self) -> None:
        addons = (TEMPLATE / "group_vars" / "all" / "atlas-k8s-addons.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("kube_apiserver_oidc_enabled: true", addons)
        self.assertIn("oidc_issuer_url:", addons)
        self.assertNotIn("kube_oidc_issuer_url:", addons)
        self.assertNotIn("kube_oidc_client_id:", addons)
        self.assertNotIn("kube_oidc_ca_file:", addons)
        docs = (ROOT / "docs" / "stacks" / "k8s-addons.md").read_text(encoding="utf-8")
        self.assertIn("issuer is `oidc_issuer_url`", docs)

    def test_template_catalog_has_logging_ilm_and_snapshot_keys(self) -> None:
        addons = (TEMPLATE / "group_vars" / "all" / "atlas-k8s-addons.yml").read_text(encoding="utf-8")
        self.assertIn("elasticsearch_ilm_delete_after: 7d", addons)
        self.assertIn("elasticsearch_logs_index_replicas: 0", addons)
        self.assertIn("elasticsearch_snapshot_backend: rook-rgw", addons)
        self.assertIn("elasticsearch_snapshot_storage_class: ceph-bucket", addons)
        self.assertIn('elasticsearch_slm_schedule: "0 30 1 * * ?"', addons)

    def test_template_chart_state_skip_sentry_and_ingress_vars(self) -> None:
        addons = (TEMPLATE / "group_vars" / "all" / "atlas-k8s-addons.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("sentry_chart_state: skip", addons)
        self.assertNotIn("sentry_chart_state: absent", addons)
        self.assertIn("chart_state_var: mailu_chart_state", addons)
        self.assertIn("chart_state_var: kibana_chart_state", addons)
        docs = (ROOT / "docs" / "stacks" / "k8s-addons.md").read_text(encoding="utf-8")
        self.assertIn("`*_chart_state`", docs)
        self.assertIn("`skip`", docs)
        self.assertIn("intentional teardown", docs)
        self.assertIn("994_sentry", list(EXPECTED_ADDONS_TAGS))


if __name__ == "__main__":
    unittest.main()
