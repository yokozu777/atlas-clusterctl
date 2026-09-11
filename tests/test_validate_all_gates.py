"""Tests for PR-9: validate/smoke --all gates deployable clusters only."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.paths import list_cluster_ids, list_deployable_cluster_ids
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.smoke import run_smoke
from clusterctl.validate import validate_all_clusters
from tests.lab_support import assert_known_labs_subset

class ValidateAllGatesTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._seed_tree()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_tree(self) -> None:
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        (self.root / "workspace").mkdir(exist_ok=True)
        seed_org_baseline_fixture(self.root)
        seed_local_playbook_repo_stubs(self.root)

        env_policy = self.root / "clusters" / "dev" / "default"
        env_policy.mkdir(parents=True, exist_ok=True)
        (env_policy / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "dev/default",
                    "playbooks": {
                        "atlas-node-foundation": {
                            "source": "local",
                            "path": "atlas-node-foundation",
                            "path_relative_to": "repo_root",
                            "layout": "roles/",
                            "sync": "never",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        flat_scaffold = self.root / "clusters" / "default"
        (flat_scaffold / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")

        leaf = self.root / "clusters" / "dev" / "leaf"
        leaf.mkdir(parents=True, exist_ok=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "dev/leaf",
                    "inventory": "hosts",
                    "playbooks": local_playbooks_override_block(
                        "atlas-node-foundation",
                        "atlas-infra-edge",
                        "atlas-compute-provision",
                        "atlas-k8s-core",
                        "atlas-k8s-addons",
                    )
                }
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text(
            "all:\n  children:\n    k8s_masters:\n      hosts:\n        localhost:\n"
            "    infra_platform:\n      hosts:\n        localhost:\n",
            encoding="utf-8",
        )
        pub_keys = leaf / "pub_keys"
        pub_keys.mkdir()
        (pub_keys / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True, exist_ok=True)
        (gv / "atlas-node-foundation.yml").write_text(
            yaml.safe_dump(
                {
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                    "provision_stack": "k8s",
                }
            ),
            encoding="utf-8",
        )

    def test_list_deployable_cluster_ids(self) -> None:
        all_ids = list_cluster_ids(self.root)
        deployable = list_deployable_cluster_ids(self.root)
        self.assertIn("default/default", all_ids)
        self.assertIn("dev/default", all_ids)
        self.assertIn("default", all_ids)
        self.assertIn("dev/leaf", all_ids)
        self.assertEqual(deployable, ["dev/leaf"])

    def test_validate_all_skips_policy_dirs(self) -> None:
        with (
            patch("clusterctl.validate.playbook_repo_layout_ready", return_value=True),
            patch("clusterctl.validate.validate_docker_deep", return_value=[]),
        ):
            reports = validate_all_clusters(self.root, docker_smoke=False)

        by_id = {report.cluster_id: report for report in reports}
        self.assertIn("default/default", by_id)
        self.assertIn("dev/default", by_id)
        self.assertIn("default", by_id)
        self.assertIn("dev/leaf", by_id)

        for policy_id in ("default/default", "dev/default", "default"):
            codes = {issue.code for issue in by_id[policy_id].issues}
            self.assertIn("cluster_policy_skipped", codes)
            self.assertNotIn("cluster_load_failed", codes)

        leaf_codes = {issue.code for issue in by_id["dev/leaf"].issues}
        self.assertNotIn("cluster_policy_skipped", leaf_codes)
        self.assertNotIn("cluster_load_failed", leaf_codes)

    def test_smoke_all_targets_deployable_only(self) -> None:
        with (
            patch("clusterctl.validate.playbook_repo_layout_ready", return_value=True),
            patch("clusterctl.validate.validate_docker_deep", return_value=[]),
        ):
            results = run_smoke(self.root, include_repo=False)

        cluster_ids = [report.cluster_id for report, _ in results]
        self.assertEqual(cluster_ids, ["dev/leaf"])
        self.assertTrue(all(smoke is not None and smoke.plan_ok for _, smoke in results))

class ValidateAllGatesRealRepoTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_real_repo_deployable_are_known_labs_subset(self) -> None:
        deployable = list_deployable_cluster_ids(self.root)
        assert_known_labs_subset(self, deployable)

if __name__ == "__main__":
    unittest.main()
