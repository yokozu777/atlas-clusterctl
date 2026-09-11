"""Orchestration contract for atlas-compute-provision via clusterctl.

SoT: ``_template/k8s_full`` (+ stack ``_template/{jenkins_agent,postgresql,redis,kafka}``).
Optional local labs: discovered k8s leaf (``lab_id_for('k8s')``) and stack leaves.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config_loader import load_merged_cluster_config_v2
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

EXPECTED_TEMPLATES_TAGS = (
    "00_ensure_workspace",
    "00_check_pve_templates,01_prepare_system",
    "02_download_images",
    "03_customize_images",
    "04_upload_images",
    "05_create_pve_templates",
)

EXPECTED_PROVISION_TAGS = (
    "00_ensure_workspace",
    "00_validate_provision",
    "06_configure_git",
    "07_tf_state_pull",
    "08_generate_tf_vars",
    "09a_tf_destroy_dns",
    "09_hypervisor_cleaner",
    "10_tf_apply",
    "provision_wait_ssh",
    "11_tf_state_push",
)

STACK_TEMPLATE_LEAVES = (
    ROOT / "clusters" / "_template" / "infra_edge",
    ROOT / "clusters" / "_template" / "jenkins_agent",
    ROOT / "clusters" / "_template" / "postgresql",
    ROOT / "clusters" / "_template" / "redis",
    ROOT / "clusters" / "_template" / "kafka",
)


def _discovered_stack_lab_leaves() -> list[Path]:
    leaves: list[Path] = []
    for stack in ("jenkins", "postgresql", "redis", "kafka"):
        path = lab_path_for(stack)
        if path is not None:
            leaves.append(path)
    return leaves


def _compute_entries(cluster_yaml: Path) -> tuple[list[dict], list[dict]]:
    data = yaml.safe_load(cluster_yaml.read_text(encoding="utf-8"))
    repo = data["playbooks"]["atlas-compute-provision"]["entries"]
    return repo["templates"]["invocations"], repo["provision"]["invocations"]


def _tag_list(invocations: list[dict]) -> list[str]:
    return [item["tags"] for item in invocations]


def _assert_compute_invocation_contract(test: unittest.TestCase, leaf: Path) -> None:
    path = leaf / "cluster.yaml"
    test.assertTrue(path.is_file(), path)
    templates_inv, provision_inv = _compute_entries(path)
    test.assertEqual(_tag_list(templates_inv), list(EXPECTED_TEMPLATES_TAGS), path)
    test.assertEqual(_tag_list(provision_inv), list(EXPECTED_PROVISION_TAGS), path)
    wait = next(item for item in provision_inv if item["tags"] == "provision_wait_ssh")
    test.assertTrue(wait.get("root_ssh"), f"{path}: provision_wait_ssh needs root_ssh")
    provision_yml = group_vars_all_file(leaf, "atlas-compute-provision.yml").read_text(encoding="utf-8")
    test.assertIn("docs/stacks/compute-provision.md", provision_yml, leaf)
    test.assertIn("provision_stack:", provision_yml, leaf)


class ComputeProvisionOrchestrationTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import clusters_root, list_deployable_cluster_ids, repo_root

        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    def test_phases_include_compute_provision(self) -> None:
        config = load_public_reference_cluster_config(ROOT)
        assert config.phases is not None
        phases = list(config.phases.phases)
        self.assertEqual(phases[0], "atlas-compute-provision/provision")
        aliases = config.phases.phase_aliases
        self.assertEqual(aliases.get("provision"), "atlas-compute-provision/provision")
        # templates stays a playbooks entry for emergency rebuild / pve_templates leaf
        self.assertNotIn("atlas-compute-provision/templates", phases)

    def test_playbooks_include_atlas_compute_provision(self) -> None:
        config = load_public_reference_cluster_config(ROOT)
        assert config.playbooks is not None
        self.assertIn("atlas-compute-provision", config.playbooks.repos)
        templates = config.playbooks.repos["atlas-compute-provision"].entries["templates"]
        provision = config.playbooks.repos["atlas-compute-provision"].entries["provision"]
        self.assertEqual(templates.file, "playbooks/build_templates.yaml")
        self.assertEqual(provision.file, "playbooks/provision_nodes.yaml")
        self.assertEqual([inv.tags for inv in templates.invocations], list(EXPECTED_TEMPLATES_TAGS))
        self.assertEqual([inv.tags for inv in provision.invocations], list(EXPECTED_PROVISION_TAGS))
        self.assertLess(
            [inv.tags for inv in provision.invocations].index("00_validate_provision"),
            [inv.tags for inv in provision.invocations].index("08_generate_tf_vars"),
        )
        self.assertLess(
            [inv.tags for inv in provision.invocations].index("10_tf_apply"),
            [inv.tags for inv in provision.invocations].index("provision_wait_ssh"),
        )
        self.assertLess(
            [inv.tags for inv in provision.invocations].index("provision_wait_ssh"),
            [inv.tags for inv in provision.invocations].index("11_tf_state_push"),
        )

    def test_provision_yml_contract(self) -> None:
        text = (TEMPLATE / "group_vars" / "all" / "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/compute-provision.md", text)
        self.assertIn("provision_stack: k8s", text)
        self.assertNotIn("provision_pve_templates:", text)
        self.assertNotIn("image_url:", text)
        hosts = (TEMPLATE / "hosts").read_text(encoding="utf-8")
        self.assertIn("ubuntu-base", hosts)
        self.assertIn("oracle-base", hosts)
        self.assertIn("debian-base", hosts)
        self.assertIn("provision_inventory_group_map_k8s:", text)
        self.assertIn("provision_tf_module_map_k8s:", text)
        self.assertNotIn("provision_inventory_group_map_infra:", text)
        self.assertIn("k8s_lbs", text)
        self.assertNotIn("infra_platform", text)

    @skip_unless_stack(STACK)
    def test_lab_provision_yml_matches_k8s_without_infra(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: k8s", text)
        self.assertIn("provision_inventory_group_map_k8s:", text)
        self.assertNotIn("provision_inventory_group_map_infra:", text)
        self.assertNotIn("infra_platform", text)

    def test_inventory_has_k8s_groups_without_infra(self) -> None:
        groups = extract_inventory_groups(TEMPLATE / "hosts")
        for group in ("k8s_lbs", "k8s_masters", "k8s_workers"):
            self.assertIn(group, groups)
        self.assertNotIn("infra_platform", groups)

    @skip_unless_stack(STACK)
    def test_lab_inventory_has_k8s_groups_without_infra(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        groups = extract_inventory_groups(path / "hosts")
        for group in ("k8s_lbs", "k8s_masters", "k8s_workers"):
            self.assertIn(group, groups)
        self.assertNotIn("infra_platform", groups)

    def test_template_invocations_aligned(self) -> None:
        path = TEMPLATE / "cluster.yaml"
        templates_inv, provision_inv = _compute_entries(path)
        self.assertEqual(_tag_list(templates_inv), list(EXPECTED_TEMPLATES_TAGS), path)
        self.assertEqual(_tag_list(provision_inv), list(EXPECTED_PROVISION_TAGS), path)
        for inv in templates_inv + provision_inv:
            self.assertIsNone(inv.get("limit"), f"{path}: unexpected limit on {inv['tags']}")
        wait = next(item for item in provision_inv if item["tags"] == "provision_wait_ssh")
        self.assertTrue(wait.get("root_ssh"), f"{path}: provision_wait_ssh needs root_ssh")
        provision_entry = yaml.safe_load(path.read_text(encoding="utf-8"))["playbooks"][
            "atlas-compute-provision"
        ]["entries"]["provision"]
        self.assertTrue(provision_entry.get("git_ssh"), f"{path}: provision git_ssh")
        self.assertIn("docs/stacks/compute-provision.md", path.read_text(encoding="utf-8"))

    @skip_unless_stack(STACK)
    def test_lab_invocations_match_template(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        for path in (path / "cluster.yaml", TEMPLATE / "cluster.yaml"):
            templates_inv, provision_inv = _compute_entries(path)
            self.assertEqual(_tag_list(templates_inv), list(EXPECTED_TEMPLATES_TAGS), path)
            self.assertEqual(_tag_list(provision_inv), list(EXPECTED_PROVISION_TAGS), path)

    def test_stack_templates_share_same_invocation_tags(self) -> None:
        for leaf in STACK_TEMPLATE_LEAVES:
            _assert_compute_invocation_contract(self, leaf)

    def test_dev_labs_share_same_invocation_tags(self) -> None:
        present = [leaf for leaf in _discovered_stack_lab_leaves() if (leaf / "cluster.yaml").is_file()]
        if not present:
            self.skipTest("no local dev/* stack labs present (see docs/local-labs.md)")
        for leaf in present:
            _assert_compute_invocation_contract(self, leaf)

    def test_k8s_full_template_exists(self) -> None:
        self.assertTrue(TEMPLATE.is_dir())
        content = (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas-compute-provision", content)
        self.assertIn("provision: atlas-compute-provision/provision", content)
        self.assertNotIn("- templates: atlas-compute-provision/templates", content)
        self.assertIn("playbooks/build_templates.yaml", content)  # emergency entry kept
        self.assertIn("playbooks/provision_nodes.yaml", content)
        self.assertIn("docs/stacks/compute-provision.md", content)

    def test_orchestration_docs_and_readme_links(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        docs = (ROOT / "docs" / "stacks" / "compute-provision.md").read_text(encoding="utf-8")
        self.assertIn("00_ensure_workspace", docs)
        self.assertIn("00_validate_provision", docs)
        self.assertIn("provision_wait_ssh", docs)
        self.assertIn("01_validate_vars", docs)  # documented absence / contrast
        self.assertIn("provision_stack", docs)
        self.assertIn("atlas-compute-provision", docs)
        self.assertIn("playbooks/build_templates.yaml", docs)
        self.assertIn("playbooks/provision_nodes.yaml", docs)
        self.assertIn("infra-edge.md", docs)
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("compute-provision.md", index)
        for rel in (
            "docs/clusters.md",
            "docs/playbooks.md",
            "docs/clusterctl.md",
            "docs/validate.md",
            "docs/ansible.md",
            "docs/cluster-config-v2.md",
            "docs/stacks/k8s-core.md",
            "docs/stacks/k8s-addons.md",
            "docs/stacks/infra-edge.md",
            "docs/stacks/jenkins-agent.md",
            "docs/stacks/gitlab-runner.md",
            "docs/stacks/postgresql.md",
            "docs/stacks/redis.md",
            "docs/stacks/kafka.md",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("compute-provision.md", text, rel)
        template_readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/compute-provision.md", template_readme)
        leaf = path
        readme = None if leaf is None else leaf / "README.md"
        if readme is not None and readme.is_file():
            ref_readme = (readme).read_text(encoding="utf-8")
            self.assertIn("docs/stacks/compute-provision.md", ref_readme)

    @skip_unless_stack(STACK)
    def test_context_loads_reference(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import clusters_root

        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)
        ctx = ClusterContext.load(cluster_id=lab)
        self.assertEqual(ctx.cluster_id, lab)
        self.assertTrue(group_vars_all_file(ctx.config_dir, "atlas-compute-provision.yml").is_file())
        provision = group_vars_all_file(ctx.config_dir, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: k8s", provision)
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.phases is not None
        self.assertEqual(config.phases.phase_aliases.get("provision"), "atlas-compute-provision/provision")


    def test_pve_templates_factory_scaffold(self) -> None:
        leaf = ROOT / "clusters" / "_template" / "pve_templates"
        self.assertTrue((leaf / "cluster.yaml").is_file())
        data = yaml.safe_load((leaf / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertEqual(
            [next(iter(item.values())) if isinstance(item, dict) else item for item in data["phases"]],
            ["atlas-compute-provision/templates"],
        )
        self.assertNotIn("provision", data["playbooks"]["atlas-compute-provision"]["entries"])
        catalog = (leaf / "group_vars" / "all" / "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("ubuntu-base:", catalog)
        self.assertIn("image_url:", catalog)
        self.assertIn("400100", catalog)

    def test_stack_scaffolds_omit_pve_templates_catalog(self) -> None:
        stacks = ("k8s_full", "infra_edge", "jenkins_agent", "gitlab_runner", "postgresql", "redis", "kafka")
        for name in stacks:
            path = ROOT / "clusters" / "_template" / name / "group_vars" / "all" / "atlas-compute-provision.yml"
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "provision_pve_templates:",
                text,
                f"{name} must omit provision_pve_templates (factory-only catalog)",
            )


if __name__ == "__main__":
    unittest.main()
