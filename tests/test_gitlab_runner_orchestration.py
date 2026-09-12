"""Orchestration contract for atlas-gitlab-runner via clusterctl.

SoT: ``_template/gitlab_runner``. Optional local lab: discovered via ``lab_id_for('gitlab')`` (see docs/local-labs.md).
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
    PUBLIC_GITLAB_RUNNER_TEMPLATE,
    ROOT,
)

STACK = "gitlab"
TEMPLATE = PUBLIC_GITLAB_RUNNER_TEMPLATE

EXPECTED_RUNNER_TAGS = (
    "00_ensure_workspace",
    "01_validate_vars",
    "02_ensure_runner_token",
    "03_install_runner",
)


def _load_template_config():
    raw = yaml.safe_load((TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")) or {}
    return parse_cluster_config_v2_fragment(raw)


class GitLabRunnerOrchestrationTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import list_deployable_cluster_ids, repo_root

        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    def test_phases_include_gitlab_runner(self) -> None:
        config = _load_template_config()
        assert config.phases is not None
        phases = list(config.phases.phases)
        self.assertEqual(
            phases,
            [
                "atlas-compute-provision/provision",
                "atlas-node-foundation/init",
                "atlas-gitlab-runner/runner",
            ],
        )
        for ref in phases:
            self.assertNotIn("k8s", ref)
            self.assertNotIn("infra-edge", ref)
        aliases = config.phases.phase_aliases
        self.assertEqual(aliases.get("gitlab-runner"), "atlas-gitlab-runner/runner")
        self.assertEqual(aliases.get("init"), "atlas-node-foundation/init")

    def test_playbooks_include_atlas_gitlab_runner(self) -> None:
        config = _load_template_config()
        assert config.playbooks is not None
        self.assertIn("atlas-gitlab-runner", config.playbooks.repos)
        entry = config.playbooks.repos["atlas-gitlab-runner"].entries["runner"]
        self.assertEqual(entry.file, "playbooks/gitlab_runner.yaml")
        tags = [inv.tags for inv in entry.invocations]
        self.assertEqual(tags, list(EXPECTED_RUNNER_TAGS))
        self.assertLess(tags.index("01_validate_vars"), tags.index("02_ensure_runner_token"))
        self.assertLess(tags.index("02_ensure_runner_token"), tags.index("03_install_runner"))

    def test_gitlab_runner_yml_targeting(self) -> None:
        text = (TEMPLATE / "group_vars" / "all" / "atlas-gitlab-runner.yml").read_text(encoding="utf-8")
        secrets = (TEMPLATE / "group_vars" / "all" / "atlas-gitlab-runner.secrets.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("gitlab_runner_hosts: gitlab_runners", text)
        self.assertIn("gitlab_runner_executor: shell", text)
        self.assertIn("docs/stacks/gitlab-runner.md", text)
        self.assertNotIn("gitlab_runner_authentication_token:", text)
        self.assertIn("gitlab_runner_authentication_token:", secrets)
        self.assertRegex(
            secrets,
            r"(?m)^gitlab_runner_authentication_token:\s*(''|\"\"|CHANGEME)\s*$",
        )

    @skip_unless_stack(STACK)
    def test_lab_gitlab_runner_yml_targeting(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = (path / "group_vars" / "all" / "atlas-gitlab-runner.yml").read_text(encoding="utf-8")
        self.assertIn("gitlab_runner_hosts: gitlab_runners", text)
        self.assertIn("docs/stacks/gitlab-runner.md", text)

    def test_prepare_hosts_targets_gitlab_runners(self) -> None:
        text = (TEMPLATE / "group_vars" / "all" / "atlas-node-foundation.yml").read_text(encoding="utf-8")
        self.assertIn("node_foundation_init_hosts: gitlab_runners", text)
        self.assertIn("docs/stacks/gitlab-runner.md", text)

    @skip_unless_stack(STACK)
    def test_lab_prepare_hosts_targets_gitlab_runners(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-node-foundation.yml").read_text(encoding="utf-8")
        self.assertIn("node_foundation_init_hosts: gitlab_runners", text)

    def test_inventory_has_gitlab_runners_group(self) -> None:
        groups = extract_inventory_groups(TEMPLATE / "hosts")
        self.assertIn("gitlab_runners", groups)

    @skip_unless_stack(STACK)
    def test_lab_inventory_has_gitlab_runners_group(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        groups = extract_inventory_groups(path / "hosts")
        self.assertIn("gitlab_runners", groups)

    def test_template_invocation_limits_aligned(self) -> None:
        path = TEMPLATE / "cluster.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        inv = data["playbooks"]["atlas-gitlab-runner"]["entries"]["runner"]["invocations"]
        tags = [item["tags"] for item in inv]
        self.assertEqual(tags, list(EXPECTED_RUNNER_TAGS), path)
        limits = {item["tags"]: item.get("limit") for item in inv}
        self.assertIsNone(limits.get("01_validate_vars"), f"{path}: validate must not set limit")
        self.assertIsNone(limits.get("02_ensure_runner_token"), f"{path}: ensure token must not set limit")
        self.assertEqual(limits["03_install_runner"], "gitlab_runners", f"{path}: install limit")
        when = data["playbooks"]["atlas-gitlab-runner"]["entries"]["runner"]["when"]
        self.assertIn("gitlab_runners", when["inventory_groups_any"])

    def test_gitlab_runner_template_exists(self) -> None:
        self.assertTrue(TEMPLATE.is_dir())
        content = (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas-gitlab-runner", content)
        self.assertIn("gitlab-runner: atlas-gitlab-runner/runner", content)
        self.assertIn("playbooks/gitlab_runner.yaml", content)
        self.assertIn("docs/stacks/gitlab-runner.md", content)

    def test_secrets_examples_point_to_overlay(self) -> None:
        secrets_path = TEMPLATE / "group_vars" / "all" / "atlas-gitlab-runner.secrets.yml"
        text = secrets_path.read_text(encoding="utf-8")
        self.assertIn("gitlab_runner_authentication_token", text)
        self.assertIn("gitlab_runner_api_private_token", text)
        self.assertIn("docs/stacks/gitlab-runner.md", text)

    def test_orchestration_docs_and_readme_links(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        docs = (ROOT / "docs" / "stacks" / "gitlab-runner.md").read_text(encoding="utf-8")
        self.assertIn("gitlab_runner_hosts", docs)
        self.assertIn("00_ensure_workspace", docs)
        self.assertIn("01_validate_vars", docs)
        self.assertIn("02_ensure_runner_token", docs)
        self.assertIn("03_install_runner", docs)
        self.assertIn("atlas-gitlab-runner", docs)
        self.assertIn("gitlab-ci.md", docs)
        self.assertIn("config.toml", docs)
        self.assertIn("PAT preflight", docs)
        self.assertNotIn("gitlab_runner_authentication_token` — not in git", docs)
        self.assertNotIn("{{ cluster_workspace_root }}/secrets/gitlab_runner_authentication_token", docs)
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("gitlab-runner.md", index)
        clusters_doc = (ROOT / "docs" / "clusters.md").read_text(encoding="utf-8")
        self.assertIn("gitlab-runner.md", clusters_doc)
        playbooks_doc = (ROOT / "docs" / "playbooks.md").read_text(encoding="utf-8")
        self.assertIn("gitlab-runner.md", playbooks_doc)
        clusterctl_doc = (ROOT / "docs" / "clusterctl.md").read_text(encoding="utf-8")
        self.assertIn("gitlab-runner.md", clusterctl_doc)
        validate_doc = (ROOT / "docs" / "validate.md").read_text(encoding="utf-8")
        self.assertIn("gitlab-runner.md", validate_doc)
        template_readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/gitlab-runner.md", template_readme)
        leaf = path
        readme = None if leaf is None else leaf / "README.md"
        if readme is not None and readme.is_file():
            ref_readme = (readme).read_text(encoding="utf-8")
            self.assertIn("docs/stacks/gitlab-runner.md", ref_readme)

    @skip_unless_stack(STACK)
    def test_context_loads_reference(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import clusters_root

        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)
        ctx = ClusterContext.load(cluster_id=lab)
        self.assertEqual(ctx.cluster_id, lab)
        self.assertTrue((ctx.config_dir / "group_vars" / "all" / "atlas-gitlab-runner.yml").is_file())
        provision = group_vars_all_file(ctx.config_dir, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: gitlab_runner", provision)
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.phases is not None
        self.assertEqual(config.phases.phase_aliases.get("gitlab-runner"), "atlas-gitlab-runner/runner")


if __name__ == "__main__":
    unittest.main()
