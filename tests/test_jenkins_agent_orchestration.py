"""Orchestration contract for atlas-jenkins-agent via clusterctl.

SoT: ``_template/jenkins_agent``. Optional local lab: discovered via ``lab_id_for('jenkins')`` (see docs/local-labs.md).
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
    PUBLIC_JENKINS_TEMPLATE,
    ROOT,
)

STACK = "jenkins"
TEMPLATE = PUBLIC_JENKINS_TEMPLATE

EXPECTED_AGENT_TAGS = (
    "00_ensure_workspace",
    "01_validate_vars",
    "03_install_jslave",
)


def _load_template_config():
    raw = yaml.safe_load((TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")) or {}
    return parse_cluster_config_v2_fragment(raw)


class JenkinsAgentOrchestrationTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import clusters_root, list_deployable_cluster_ids, repo_root

        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    def test_phases_include_jenkins_agent(self) -> None:
        config = _load_template_config()
        assert config.phases is not None
        phases = list(config.phases.phases)
        self.assertEqual(
            phases,
            [
                "atlas-compute-provision/provision",
                "atlas-node-foundation/init",
                "atlas-jenkins-agent/agent",
            ],
        )
        for ref in phases:
            self.assertNotIn("k8s", ref)
            self.assertNotIn("infra-edge", ref)
        aliases = config.phases.phase_aliases
        self.assertEqual(aliases.get("jenkins-agent"), "atlas-jenkins-agent/agent")
        self.assertEqual(aliases.get("init"), "atlas-node-foundation/init")

    def test_playbooks_include_atlas_jenkins_agent(self) -> None:
        config = _load_template_config()
        assert config.playbooks is not None
        self.assertIn("atlas-jenkins-agent", config.playbooks.repos)
        entry = config.playbooks.repos["atlas-jenkins-agent"].entries["agent"]
        self.assertEqual(entry.file, "playbooks/jenkins_agent.yaml")
        tags = [inv.tags for inv in entry.invocations]
        self.assertEqual(tags, list(EXPECTED_AGENT_TAGS))
        self.assertLess(tags.index("01_validate_vars"), tags.index("03_install_jslave"))

    def test_jenkins_agent_yml_targeting(self) -> None:
        text = (TEMPLATE / "group_vars" / "all" / "atlas-jenkins-agent.yml").read_text(encoding="utf-8")
        secrets = (TEMPLATE / "group_vars" / "all" / "atlas-jenkins-agent.secrets.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("jenkins_agent_hosts: jslave", text)
        self.assertIn("docs/stacks/jenkins-agent.md", text)
        self.assertNotIn("jenkins_admin_password:", text)
        self.assertIn("jenkins_admin_password:", secrets)
        self.assertRegex(
            secrets,
            r"(?m)^jenkins_admin_password:\s*(''|\"\"|CHANGEME)\s*$",
        )
        self.assertNotIn("Welcomeback", text)

    @skip_unless_stack(STACK)
    def test_lab_jenkins_agent_yml_targeting(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = (path / "group_vars" / "all" / "atlas-jenkins-agent.yml").read_text(encoding="utf-8")
        self.assertIn("jenkins_agent_hosts: jslave", text)
        self.assertIn("docs/stacks/jenkins-agent.md", text)

    def test_prepare_hosts_targets_jslave(self) -> None:
        text = (TEMPLATE / "group_vars" / "all" / "atlas-node-foundation.yml").read_text(encoding="utf-8")
        self.assertIn("node_foundation_init_hosts: jslave", text)
        self.assertIn("docs/stacks/jenkins-agent.md", text)

    @skip_unless_stack(STACK)
    def test_lab_prepare_hosts_targets_jslave(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-node-foundation.yml").read_text(encoding="utf-8")
        self.assertIn("node_foundation_init_hosts: jslave", text)
        self.assertIn("docs/stacks/jenkins-agent.md", text)

    def test_inventory_has_jslave_group(self) -> None:
        groups = extract_inventory_groups(TEMPLATE / "hosts")
        self.assertIn("jslave", groups)

    @skip_unless_stack(STACK)
    def test_lab_inventory_has_jslave_group(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        groups = extract_inventory_groups(path / "hosts")
        self.assertIn("jslave", groups)

    def test_template_invocation_limits_aligned(self) -> None:
        path = TEMPLATE / "cluster.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        inv = data["playbooks"]["atlas-jenkins-agent"]["entries"]["agent"]["invocations"]
        tags = [item["tags"] for item in inv]
        self.assertEqual(tags, list(EXPECTED_AGENT_TAGS), path)
        limits = {item["tags"]: item.get("limit") for item in inv}
        self.assertIsNone(limits.get("01_validate_vars"), f"{path}: validate must not set limit")
        self.assertEqual(limits["03_install_jslave"], "jslave", f"{path}: install limit")
        when = data["playbooks"]["atlas-jenkins-agent"]["entries"]["agent"]["when"]
        self.assertIn("jslave", when["inventory_groups_any"])

    @skip_unless_stack(STACK)
    def test_lab_invocations_match_template(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        for path in (path / "cluster.yaml", TEMPLATE / "cluster.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            inv = data["playbooks"]["atlas-jenkins-agent"]["entries"]["agent"]["invocations"]
            tags = [item["tags"] for item in inv]
            self.assertEqual(tags, list(EXPECTED_AGENT_TAGS), path)

    def test_jenkins_agent_template_exists(self) -> None:
        self.assertTrue(TEMPLATE.is_dir())
        content = (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas-jenkins-agent", content)
        self.assertIn("jenkins-agent: atlas-jenkins-agent/agent", content)
        self.assertIn("playbooks/jenkins_agent.yaml", content)
        self.assertIn("docs/stacks/jenkins-agent.md", content)

    def test_secrets_examples_point_to_overlay(self) -> None:
        secrets_path = TEMPLATE / "group_vars" / "all" / "atlas-jenkins-agent.secrets.yml"
        text = secrets_path.read_text(encoding="utf-8")
        self.assertIn("jenkins_admin_password", text)
        self.assertIn("docs/stacks/jenkins-agent.md", text)
        self.assertNotIn("Welcomeback", text)

    @skip_unless_stack(STACK)
    def test_lab_secrets_overlay_holds_admin_password(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        secrets_path = path / "group_vars" / "all" / "atlas-jenkins-agent.secrets.yml"
        self.assertTrue(secrets_path.is_file(), secrets_path)
        text = secrets_path.read_text(encoding="utf-8")
        self.assertIn("jenkins_admin_password", text)
        self.assertIn("docs/stacks/jenkins-agent.md", text)
        # Lab leaf may hold live credentials (private inventory); template stays CHANGEME.

    def test_orchestration_docs_and_readme_links(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        docs = (ROOT / "docs" / "stacks" / "jenkins-agent.md").read_text(encoding="utf-8")
        self.assertIn("jenkins_agent_hosts", docs)
        self.assertIn("00_ensure_workspace", docs)
        self.assertIn("01_validate_vars", docs)
        self.assertIn("03_install_jslave", docs)
        self.assertIn("atlas-jenkins-agent", docs)
        self.assertIn("jenkins.md", docs)
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("jenkins-agent.md", index)
        clusters_doc = (ROOT / "docs" / "clusters.md").read_text(encoding="utf-8")
        self.assertIn("jenkins-agent.md", clusters_doc)
        playbooks_doc = (ROOT / "docs" / "playbooks.md").read_text(encoding="utf-8")
        self.assertIn("jenkins-agent.md", playbooks_doc)
        clusterctl_doc = (ROOT / "docs" / "clusterctl.md").read_text(encoding="utf-8")
        self.assertIn("jenkins-agent.md", clusterctl_doc)
        validate_doc = (ROOT / "docs" / "validate.md").read_text(encoding="utf-8")
        self.assertIn("jenkins-agent.md", validate_doc)
        template_readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/jenkins-agent.md", template_readme)
        leaf = path
        readme = None if leaf is None else leaf / "README.md"
        if readme is not None and readme.is_file():
            ref_readme = (readme).read_text(encoding="utf-8")
            self.assertIn("docs/stacks/jenkins-agent.md", ref_readme)

    @skip_unless_stack(STACK)
    def test_context_loads_reference(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import clusters_root

        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)
        ctx = ClusterContext.load(cluster_id=lab)
        self.assertEqual(ctx.cluster_id, lab)
        self.assertTrue((ctx.config_dir / "group_vars" / "all" / "atlas-jenkins-agent.yml").is_file())
        provision = group_vars_all_file(ctx.config_dir, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: jenkins", provision)
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.phases is not None
        self.assertEqual(config.phases.phase_aliases.get("jenkins-agent"), "atlas-jenkins-agent/agent")


if __name__ == "__main__":
    unittest.main()
