"""Orchestration contract for atlas-infra-edge via clusterctl.

SoT: ``_template/infra_edge``. Optional local lab: discovered via ``lab_id_for('infra')`` (see docs/local-labs.md).
"""

from __future__ import annotations

import os
import unittest

import yaml

from clusterctl.cluster_config_loader import load_merged_cluster_config_v2
from clusterctl.context import ClusterContext
from clusterctl.inventory import extract_inventory_groups
from clusterctl.playbooks_config import parse_cluster_config_v2_fragment
from tests.lab_support import (
    lab_id_for,
    lab_path_for,
    skip_unless_stack,

    group_vars_all_file,
    PUBLIC_INFRA_TEMPLATE,
    ROOT,
)

STACK = "infra"
TEMPLATE = PUBLIC_INFRA_TEMPLATE

# Phase 4–6 SoT: compose phases; Phase 6 merges docker baseline into one invocation.
EXPECTED_INFRA_TAGS = (
    "00_ensure_workspace",
    "01_validate_vars",
    "00_bootstrap_infra_repos,01_install_docker_engine,02_configure_docker_daemon",
    "compose_render",
    "compose_pull",
    "compose_start_core",
    "11_sync_infra_cache_pull,14_infra_cache_seed_load",
    "compose_start_registry",
    "compose_reconcile",
    "11_sync_infra_cache_push",
)
# Full leaf plan: provision(10)+init-infra(5)+infra(10)+init-infra-post(7).
EXPECTED_FULL_PLAN_INVOCATION_COUNT = 32
DOCKER_BASELINE_TAG = (
    "00_bootstrap_infra_repos,01_install_docker_engine,02_configure_docker_daemon"
)
LEGACY_INFRA_PLAN_TAGS = (
    "06_enable_compose_systemd_deploy",
    "03_deploy_bind_compose",
    "12_deploy_ntp_compose",
    "04_deploy_stepca_compose",
    "05_deploy_registry_compose",
    "07_deploy_registry_nginx_compose",
    "08_deploy_pkg_repo_nginx_compose",
    "09_deploy_helm_repo_nginx_compose",
    "helm_repo_cache_warm",
    "10_deploy_custom_nginx_compose",
    "06_enable_compose_systemd_reconcile",
)

EXPECTED_PHASES = (
    "atlas-compute-provision/provision",
    "atlas-node-foundation/init-infra",
    "atlas-infra-edge/infra",
    "atlas-node-foundation/init-infra-post",
)

EXPECTED_INIT_INFRA_TAGS = (
    "00_ensure_workspace",
    "00_gather_facts,00_init,01_backup_etc,02_init_sshd,03_configure_users,04_configure_hostname",
    "06_configure_kernel,08_configure_security,09_configure_locales,10_manage_services",
    "14_install_software,15_configure_journald,16_configure_bash",
    "19_configure_sysctl_limits,20_disable_swap,21_grow_disk_to_full,22_extend_swap_to_root",
)

EXPECTED_INIT_INFRA_POST_TAGS = (
    "00_ensure_workspace",
    "00_gather_facts,17_configure_network",
    "18_remove_unwanted_services",
    "11_certificates",
    "13_configure_repo",
    "12_date_timezone",
    "99_update_reboot",
)


def _load_template_config():
    raw = yaml.safe_load((TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")) or {}
    return parse_cluster_config_v2_fragment(raw)


class InfraEdgeOrchestrationTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import list_deployable_cluster_ids, repo_root

        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    def test_phases_are_infra_only(self) -> None:
        config = _load_template_config()
        assert config.phases is not None
        phases = list(config.phases.phases)
        self.assertEqual(phases, list(EXPECTED_PHASES))
        for ref in phases:
            self.assertNotIn("k8s-core", ref)
            self.assertNotIn("k8s-addons", ref)
        self.assertNotIn("atlas-node-foundation/init", phases)
        aliases = config.phases.phase_aliases
        self.assertEqual(aliases.get("infra"), "atlas-infra-edge/infra")
        self.assertEqual(aliases.get("init-infra"), "atlas-node-foundation/init-infra")
        self.assertEqual(aliases.get("init-infra-post"), "atlas-node-foundation/init-infra-post")
        self.assertNotIn("k8s-core", aliases)
        self.assertNotIn("k8s-addons", aliases)
        raw = yaml.safe_load((TEMPLATE / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("stacks", raw)
        self.assertNotIn("phase_aliases", raw)
        raw_phase_refs = [
            next(iter(item.values())) if isinstance(item, dict) else str(item)
            for item in raw["phases"]
        ]
        self.assertIn("atlas-infra-edge/infra", raw_phase_refs)
        self.assertNotIn("atlas-k8s-core/cluster", raw_phase_refs)
        self.assertNotIn("atlas-k8s-addons/addons", raw_phase_refs)
        init_infra = raw["playbooks"]["atlas-node-foundation"]["entries"]["init-infra"]["invocations"]
        self.assertEqual([item["tags"] for item in init_infra], list(EXPECTED_INIT_INFRA_TAGS))
        post = raw["playbooks"]["atlas-node-foundation"]["entries"]["init-infra-post"]["invocations"]
        self.assertEqual([item["tags"] for item in post], list(EXPECTED_INIT_INFRA_POST_TAGS))
        for item in init_infra + post:
            if item["tags"] == "00_ensure_workspace":
                self.assertIsNone(item.get("limit"))
                continue
            self.assertEqual(item.get("limit"), "infra_platform")
        # Short init must not pull DNS/apt/CA before BIND exists.
        init_tags = " ".join(EXPECTED_INIT_INFRA_TAGS)
        self.assertNotIn("17_configure_network", init_tags)
        self.assertNotIn("11_certificates", init_tags)
        self.assertNotIn("18_remove_unwanted_services", init_tags)

    def test_playbooks_include_atlas_infra_edge(self) -> None:
        config = _load_template_config()
        assert config.playbooks is not None
        self.assertIn("atlas-infra-edge", config.playbooks.repos)
        self.assertNotIn("atlas-k8s-core", config.playbooks.repos)
        self.assertNotIn("atlas-k8s-addons", config.playbooks.repos)
        entry = config.playbooks.repos["atlas-infra-edge"].entries["infra"]
        self.assertEqual(entry.file, "playbooks/infra_hosts.yaml")
        tags = [inv.tags for inv in entry.invocations]
        self.assertEqual(tags, list(EXPECTED_INFRA_TAGS))
        self.assertEqual(len(tags), 10)
        for legacy in LEGACY_INFRA_PLAN_TAGS:
            self.assertNotIn(legacy, tags)
        self.assertLess(tags.index("01_validate_vars"), tags.index(DOCKER_BASELINE_TAG))
        self.assertLess(tags.index(DOCKER_BASELINE_TAG), tags.index("compose_render"))
        self.assertLess(tags.index("compose_render"), tags.index("compose_pull"))
        self.assertLess(tags.index("compose_pull"), tags.index("compose_start_core"))
        self.assertLess(tags.index("compose_start_core"), tags.index("11_sync_infra_cache_pull,14_infra_cache_seed_load"))
        self.assertLess(tags.index("11_sync_infra_cache_pull,14_infra_cache_seed_load"), tags.index("compose_start_registry"))
        self.assertLess(tags.index("compose_start_registry"), tags.index("compose_reconcile"))
        self.assertLess(tags.index("compose_reconcile"), tags.index("11_sync_infra_cache_push"))

    @skip_unless_stack(STACK)
    def test_lab_plan_provision_to_init_infra_post(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.phase_plan import resolve_phase_execution_plan

        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)
        ctx = ClusterContext.load(cluster_id=lab)
        plan = resolve_phase_execution_plan(
            ctx,
            from_phase="provision",
            to_phase="init-infra-post",
        )
        self.assertEqual(list(plan.summary.phases), list(EXPECTED_PHASES))
        self.assertEqual(plan.summary.invocation_count, EXPECTED_FULL_PLAN_INVOCATION_COUNT)
        infra_stage = next(
            stage for stage in plan.stages if stage.phase_ref == "atlas-infra-edge/infra"
        )
        infra_tags = [inv.invocation.tags for inv in infra_stage.invocations]
        self.assertEqual(infra_tags, list(EXPECTED_INFRA_TAGS))
        for legacy in LEGACY_INFRA_PLAN_TAGS:
            self.assertNotIn(legacy, infra_tags)

    def test_infra_yml_targeting(self) -> None:
        text = (TEMPLATE / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(encoding="utf-8")
        self.assertIn("infra_platform_hosts: infra_platform", text)
        self.assertIn("docs/stacks/infra-edge.md", text)
        self.assertIn("groups[infra_platform_hosts]", text)
        self.assertNotIn("groups['infra_platform']", text)
        self.assertNotIn("mxhash", text.lower())
        self.assertNotIn("Welcomeback", text)

    def test_provision_yml_uses_infra_stack(self) -> None:
        text = (TEMPLATE / "group_vars" / "all" / "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: infra", text)
        self.assertIn("provision_inventory_group_map_infra:", text)
        self.assertIn("provision_tf_module_map_infra:", text)
        self.assertNotIn("provision_inventory_group_map_k8s:", text)
        self.assertNotIn("provision_stack: k8s", text)
        self.assertFalse((TEMPLATE / "group_vars" / "all" / "cluster.yml").exists())
        infra = (TEMPLATE / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(encoding="utf-8")
        self.assertIn("bind_zones:", infra)
        self.assertIn("update_mode: allow-update", infra)
        self.assertNotIn("bind_k8s_zone:", infra)
        self.assertNotIn("bind_apex_zone:", infra)

    @skip_unless_stack(STACK)
    def test_lab_provision_yml_uses_infra_stack(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: infra", text)
        self.assertIn("provision_inventory_group_map_infra:", text)
        self.assertNotIn("provision_inventory_group_map_k8s:", text)
        self.assertNotIn("provision_stack: k8s", text)
        self.assertFalse((path / "group_vars" / "all" / "cluster.yml").exists())
        infra = group_vars_all_file(path, "atlas-infra-edge.yml").read_text(encoding="utf-8")
        self.assertIn("bind_zones:", infra)
        self.assertNotIn("bind_k8s_zone:", infra)

    @skip_unless_stack(STACK)
    def test_lab_infra_yml_targeting(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-infra-edge.yml").read_text(encoding="utf-8")
        self.assertIn("infra_platform_hosts: infra_platform", text)
        self.assertIn("docs/stacks/infra-edge.md", text)
        self.assertIn("groups[infra_platform_hosts]", text)
        self.assertNotIn("groups['infra_platform']", text)
        self.assertNotIn("Welcomeback", text)
        self.assertNotIn("stepca_init_password:", text)

    def test_prepare_hosts_targets_infra_platform(self) -> None:
        text = (TEMPLATE / "group_vars" / "all" / "atlas-node-foundation.yml").read_text(encoding="utf-8")
        self.assertIn("node_foundation_init_hosts: infra_platform", text)
        self.assertIn("docs/stacks/infra-edge.md", text)

    @skip_unless_stack(STACK)
    def test_lab_prepare_hosts_targets_infra_platform(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-node-foundation.yml").read_text(encoding="utf-8")
        self.assertIn("node_foundation_init_hosts: infra_platform", text)
        self.assertIn("docs/stacks/infra-edge.md", text)

    def test_inventory_has_infra_platform_group(self) -> None:
        groups = extract_inventory_groups(TEMPLATE / "hosts")
        self.assertIn("infra_platform", groups)
        self.assertNotIn("k8s_masters", groups)
        self.assertNotIn("k8s_workers", groups)
        self.assertNotIn("k8s_lbs", groups)

    @skip_unless_stack(STACK)
    def test_lab_inventory_has_infra_platform_group(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        groups = extract_inventory_groups(path / "hosts")
        self.assertIn("infra_platform", groups)

    def test_template_invocation_limits_aligned(self) -> None:
        path = TEMPLATE / "cluster.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        inv = data["playbooks"]["atlas-infra-edge"]["entries"]["infra"]["invocations"]
        tags = [item["tags"] for item in inv]
        self.assertEqual(tags, list(EXPECTED_INFRA_TAGS), path)
        limits = {item["tags"]: item.get("limit") for item in inv}
        self.assertIsNone(limits.get("01_validate_vars"), f"{path}: validate must not set limit")
        self.assertIsNone(limits.get("00_ensure_workspace"), f"{path}: ensure must not set limit")
        for tag in EXPECTED_INFRA_TAGS:
            if tag in ("01_validate_vars", "00_ensure_workspace"):
                continue
            self.assertEqual(limits[tag], "infra_platform", f"{path}: {tag} limit")
        when = data["playbooks"]["atlas-infra-edge"]["entries"]["infra"]["when"]
        self.assertIn("infra_platform", when["inventory_groups_any"])
        content = path.read_text(encoding="utf-8")
        self.assertIn("docs/stacks/infra-edge.md", content)
        self.assertNotIn("atlas-k8s-core:", content)
        self.assertNotIn("atlas-k8s-addons:", content)
        self.assertNotIn("stacks", data)
        self.assertNotIn("atlas-k8s-core/cluster", data["phases"])
        self.assertNotIn("atlas-k8s-addons/addons", data["phases"])

    @skip_unless_stack(STACK)
    def test_lab_invocations_match_template(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        for path in (path / "cluster.yaml", TEMPLATE / "cluster.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            inv = data["playbooks"]["atlas-infra-edge"]["entries"]["infra"]["invocations"]
            tags = [item["tags"] for item in inv]
            self.assertEqual(tags, list(EXPECTED_INFRA_TAGS), path)
            init_infra = data["playbooks"]["atlas-node-foundation"]["entries"]["init-infra"]["invocations"]
            self.assertEqual(
                [item["tags"] for item in init_infra],
                list(EXPECTED_INIT_INFRA_TAGS),
                path,
            )
            post = data["playbooks"]["atlas-node-foundation"]["entries"]["init-infra-post"]["invocations"]
            self.assertEqual(
                [item["tags"] for item in post],
                list(EXPECTED_INIT_INFRA_POST_TAGS),
                path,
            )
            self.assertEqual(
                [
                    next(iter(item.values())) if isinstance(item, dict) else str(item)
                    for item in data["phases"]
                ],
                list(EXPECTED_PHASES),
                path,
            )

    def test_infra_edge_template_exists(self) -> None:
        self.assertTrue(TEMPLATE.is_dir())
        content = (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas-infra-edge", content)
        self.assertIn("infra: atlas-infra-edge/infra", content)
        self.assertIn("playbooks/infra_hosts.yaml", content)
        self.assertIn("docs/stacks/infra-edge.md", content)

    def test_secrets_examples_point_to_overlay(self) -> None:
        text = (TEMPLATE / "group_vars" / "all" / "atlas-infra-edge.secrets.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("stepca_init_password", text)
        self.assertIn("docs/stacks/infra-edge.md", text)
        self.assertNotIn("Welcomeback", text)

    @skip_unless_stack(STACK)
    def test_lab_secrets_examples_point_to_overlay(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        secrets_path = path / "group_vars" / "all" / "atlas-infra-edge.secrets.yml"
        self.assertTrue(secrets_path.is_file(), secrets_path)
        text = secrets_path.read_text(encoding="utf-8")
        self.assertIn("stepca_init_password", text)
        self.assertIn("docs/stacks/infra-edge.md", text)
        # Lab leaf may hold live credentials (private inventory); template stays CHANGEME.

    def test_orchestration_docs_and_readme_links(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        docs = (ROOT / "docs" / "stacks" / "infra-edge.md").read_text(encoding="utf-8")
        self.assertIn("infra_platform_hosts", docs)
        self.assertIn("00_ensure_workspace", docs)
        self.assertIn("01_validate_vars", docs)
        self.assertIn("01_install_docker_engine", docs)
        self.assertIn("compose_render", docs)
        self.assertIn("compose_start_core", docs)
        self.assertIn("compose_start_registry", docs)
        self.assertIn("compose_reconcile", docs)
        self.assertIn("11_sync_infra_cache_pull", docs)
        self.assertIn("14_infra_cache_seed_load", docs)
        self.assertIn("14_infra_cache_seed_publish", docs)
        self.assertIn("regular files", docs)
        self.assertIn("sha256", docs)
        self.assertIn("./run.sh", docs)
        self.assertIn("Adding a compose stack", docs)
        self.assertIn("without editing `cluster.yaml`", docs)
        self.assertIn("03_deploy_bind_compose", docs)
        self.assertIn("atlas-infra-edge", docs)
        self.assertIn("_template/infra_edge", docs)
        self.assertIn("init-infra-post", docs)
        self.assertIn("omit", docs.lower())
        self.assertIn("k8s_full", docs)
        self.assertNotIn("stacks.k8s", docs)
        self.assertNotIn("option A", docs)
        self.assertNotIn("SoT = `_template/k8s_full`", docs)
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("infra-edge.md", index)
        clusters_doc = (ROOT / "docs" / "clusters.md").read_text(encoding="utf-8")
        self.assertIn("infra-edge.md", clusters_doc)
        self.assertIn("infra_edge", clusters_doc)
        playbooks_doc = (ROOT / "docs" / "playbooks.md").read_text(encoding="utf-8")
        self.assertIn("infra-edge.md", playbooks_doc)
        clusterctl_doc = (ROOT / "docs" / "clusterctl.md").read_text(encoding="utf-8")
        self.assertIn("infra-edge.md", clusterctl_doc)
        validate_doc = (ROOT / "docs" / "validate.md").read_text(encoding="utf-8")
        self.assertIn("infra-edge.md", validate_doc)
        template_readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/infra-edge.md", template_readme)
        self.assertIn("compose_render", template_readme)
        self.assertIn("compose_start_registry", template_readme)
        leaf = path
        readme = None if leaf is None else leaf / "README.md"
        if readme is not None and readme.is_file():
            ref_readme = (readme).read_text(encoding="utf-8")
            self.assertIn("docs/stacks/infra-edge.md", ref_readme)
            self.assertIn("compose_render", ref_readme)

    @skip_unless_stack(STACK)
    def test_context_loads_reference(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import clusters_root

        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)
        ctx = ClusterContext.load(cluster_id=lab)
        self.assertEqual(ctx.cluster_id, lab)
        self.assertTrue(group_vars_all_file(ctx.config_dir, "atlas-infra-edge.yml").is_file())
        provision = group_vars_all_file(ctx.config_dir, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: infra", provision)
        self.assertNotIn("provision_inventory_group_map_k8s:", provision)
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.phases is not None
        self.assertEqual(config.phases.phase_aliases.get("infra"), "atlas-infra-edge/infra")
        self.assertEqual(list(config.phases.phases), list(EXPECTED_PHASES))


if __name__ == "__main__":
    unittest.main()
