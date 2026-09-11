"""Tests for Kafka KRaft HA cluster.

SoT for public CI: ``_template/kafka``. Optional lab: discovered kafka lab (``lab_id_for('kafka')``).
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config_loader import load_merged_cluster_config_v2
from clusterctl.context import ClusterContext
from clusterctl.inventory import KAFKA_GROUPS, extract_inventory_groups
from clusterctl.paths import clusters_root, list_deployable_cluster_ids, repo_root
from tests.lab_support import (
    lab_id_for,
    lab_path_for,
    PUBLIC_KAFKA_TEMPLATE,
    skip_unless_stack,
    group_vars_all_file,
)

ROOT = Path(__file__).resolve().parents[1]
STACK = "kafka"
TEMPLATE = PUBLIC_KAFKA_TEMPLATE


class CiKafkaClusterTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    @skip_unless_stack(STACK)
    def test_phases_include_kafka_cluster(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.phases is not None
        phases = config.phases.phases
        self.assertEqual(len(phases), 3)
        self.assertNotIn("atlas-compute-provision/templates", phases)
        self.assertIn("atlas-compute-provision/provision", phases)
        self.assertIn("atlas-node-foundation/init", phases)
        self.assertIn("atlas-kafka/cluster", phases)

    @skip_unless_stack(STACK)
    def test_playbooks_include_atlas_kafka(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.playbooks is not None
        self.assertIn("atlas-kafka", config.playbooks.repos)
        entry = config.playbooks.repos["atlas-kafka"].entries["cluster"]
        self.assertEqual(entry.file, "playbooks/kafka_cluster.yaml")
        tags = [inv.tags for inv in entry.invocations]
        self.assertIn("01_validate_vars", tags)
        self.assertIn("200_kafka_node", tags)
        self.assertIn("201_kafka_controllers", tags)
        self.assertIn("202_kafka_brokers", tags)
        self.assertIn("203_kafka_verify", tags)

    @skip_unless_stack(STACK)
    def test_provision_stack_kafka_in_group_vars(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        ctx = ClusterContext.load(cluster_id=lab)
        text = group_vars_all_file(ctx.config_dir, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: kafka", text)
        self.assertIn("provision_inventory_group_map_kafka", text)
        self.assertIn("kafka_controllers", text)

    @skip_unless_stack(STACK)
    def test_kafka_yml_version_and_targeting(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-kafka.yml").read_text(encoding="utf-8")
        self.assertIn('kafka_version: "4.3.1"', text)
        self.assertIn("kafka_security_mode: plaintext", text)
        self.assertIn("kafka_controller_hosts: kafka_controllers", text)
        self.assertIn("kafka_broker_hosts: kafka_brokers", text)

    def test_init_targets_kafka_groups(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        leaves = [TEMPLATE]
        if lab:
            leaves.append(path)
        for leaf in leaves:
            text = group_vars_all_file(leaf, "atlas-node-foundation.yml").read_text(encoding="utf-8")
            self.assertIn(
                'node_foundation_init_hosts: "kafka_controllers:kafka_brokers"',
                text,
                leaf,
            )
            self.assertIn("docs/stacks/kafka.md", text, leaf)

    @skip_unless_stack(STACK)
    def test_inventory_has_kafka_groups_and_parent(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        groups = extract_inventory_groups(path / "hosts")
        self.assertIn("kafka", groups)
        self.assertTrue(KAFKA_GROUPS <= groups)

    @skip_unless_stack(STACK)
    def test_inventory_defines_stable_kafka_node_id(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = (path / "hosts").read_text(encoding="utf-8")
        for node_id in (
            "kafka_node_id: 1",
            "kafka_node_id: 2",
            "kafka_node_id: 3",
            "kafka_node_id: 101",
            "kafka_node_id: 102",
            "kafka_node_id: 103",
        ):
            self.assertIn(node_id, text)

    def test_init_kafka_template_from_repo(self) -> None:
        self.assertTrue(TEMPLATE.is_dir())
        self.assertTrue((TEMPLATE / "group_vars" / "all" / "atlas-kafka.yml").is_file())
        content = (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas-kafka", content)
        self.assertIn("kafka: atlas-kafka/cluster", content)

    def test_ci_and_template_invocation_limits_aligned(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        expected_tags = (
            "01_validate_vars",
            "200_kafka_node",
            "201_kafka_controllers",
            "202_kafka_brokers",
            "203_kafka_verify",
        )
        paths = [TEMPLATE / "cluster.yaml"]
        if lab:
            paths.append(path / "cluster.yaml")
        for path in paths:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            inv = data["playbooks"]["atlas-kafka"]["entries"]["cluster"]["invocations"]
            tags = [item["tags"] for item in inv]
            for tag in expected_tags:
                self.assertIn(tag, tags, path)
            limits = {item["tags"]: item.get("limit") for item in inv}
            self.assertEqual(limits["200_kafka_node"], "kafka_controllers:kafka_brokers")
            self.assertEqual(limits["201_kafka_controllers"], "kafka_controllers")
            self.assertEqual(limits["202_kafka_brokers"], "kafka_brokers")
            self.assertEqual(limits["203_kafka_verify"], "kafka_brokers")

    def test_orchestration_docs_and_readme_links(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        docs = (ROOT / "docs" / "stacks" / "kafka.md").read_text(encoding="utf-8")
        self.assertIn("kafka_controller_hosts", docs)
        self.assertIn("kafka_broker_hosts", docs)
        self.assertIn("203_kafka_verify", docs)
        self.assertIn("00_ensure_workspace", docs)
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("kafka.md", index)
        template_readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/kafka.md", template_readme)
        if lab and (path / "README.md").is_file():
            ci_readme = (path / "README.md").read_text(encoding="utf-8")
            self.assertIn("docs/stacks/kafka.md", ci_readme)
        leaves = [TEMPLATE]
        if lab:
            leaves.append(path)
        for leaf in leaves:
            kafka_yml = group_vars_all_file(leaf, "atlas-kafka.yml").read_text(encoding="utf-8")
            for key in (
                "kafka_controller_hosts: kafka_controllers",
                "kafka_broker_hosts: kafka_brokers",
            ):
                self.assertIn(key, kafka_yml, f"{leaf}: {key}")

    @skip_unless_stack(STACK)
    def test_lab_hosts_nest_under_kafka_parent(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        hosts = yaml.safe_load((path / "hosts").read_text(encoding="utf-8"))
        children = hosts["all"]["children"]["kafka"]["children"]
        self.assertIn("kafka_controllers", children)
        self.assertIn("kafka_brokers", children)


if __name__ == "__main__":
    unittest.main()
