"""Compat tests for dev/jenkins.

Full orchestration contract: tests/test_jenkins_agent_orchestration.py

SoT for public CI: ``_template/jenkins_agent``. Optional lab: discovered jenkins lab (``lab_id_for('jenkins')``).
"""

from __future__ import annotations

import unittest
from pathlib import Path

from clusterctl.cluster_config_loader import load_merged_cluster_config_v2
from clusterctl.context import ClusterContext
from clusterctl.paths import clusters_root, list_deployable_cluster_ids, repo_root
from tests.lab_support import lab_id_for, lab_path_for, skip_unless_stack, group_vars_all_file

ROOT = Path(__file__).resolve().parents[1]
STACK = "jenkins"


class CiJenkinsClusterTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    @skip_unless_stack(STACK)
    def test_phases_exclude_k8s_and_infra(self) -> None:
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
        self.assertIn("atlas-jenkins-agent/agent", phases)
        for ref in phases:
            self.assertNotIn("k8s", ref)
            self.assertNotIn("infra-edge", ref)

    @skip_unless_stack(STACK)
    def test_playbooks_include_jenkins_agent(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.playbooks is not None
        self.assertIn("atlas-jenkins-agent", config.playbooks.repos)
        entry = config.playbooks.repos["atlas-jenkins-agent"].entries["agent"]
        self.assertEqual(entry.file, "playbooks/jenkins_agent.yaml")
        tags = [inv.tags for inv in entry.invocations]
        self.assertIn("01_validate_vars", tags)
        self.assertIn("03_install_jslave", tags)

    @skip_unless_stack(STACK)
    def test_provision_stack_jenkins_in_group_vars(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        ctx = ClusterContext.load(cluster_id=lab)
        text = group_vars_all_file(ctx.config_dir, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: jenkins", text)
        self.assertIn("provision_inventory_group_map_jenkins", text)

    @skip_unless_stack(STACK)
    def test_init_targets_jslave_hosts(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-node-foundation.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("node_foundation_init_hosts: jslave", text)

    def test_jenkins_agent_template_exists(self) -> None:
        template = ROOT / "clusters" / "_template" / "jenkins_agent" / "cluster.yaml"
        self.assertTrue(template.is_file())
        content = template.read_text(encoding="utf-8")
        self.assertIn("atlas-jenkins-agent", content)
        self.assertIn(
            "provision_stack: jenkins",
            (template.parent / "group_vars" / "all" / "atlas-compute-provision.yml").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
