"""Tests for v2 smoke + validate integration (PR-4)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.cluster_config_loader import dump_cluster_config_v2
from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.smoke import run_cluster_smoke
from clusterctl.validate import Severity, validate_cluster

class SmokeValidateV2Test(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._seed()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed(self) -> None:
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        (self.root / "workspace").mkdir(exist_ok=True)
        seed_org_baseline_fixture(self.root)
        seed_local_playbook_repo_stubs(self.root)

        leaf = self.root / "clusters" / "lab" / "test"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab/test",
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
        gv.mkdir(parents=True)
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

    def test_smoke_uses_v2_plan(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab/test")
        with (
            patch("clusterctl.validate.playbook_repo_layout_ready", return_value=True),
            patch("clusterctl.validate.validate_docker_deep", return_value=[]),
        ):
            report, smoke = run_cluster_smoke(ctx)
        self.assertTrue(smoke.plan_ok)
        self.assertGreater(smoke.invocations, 0)
        self.assertGreater(len(smoke.phases), 0)

    def test_validate_reports_playbooks_resolver(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab/test")
        with (
            patch("clusterctl.validate.playbook_repo_layout_ready", return_value=True),
            patch("clusterctl.validate.validate_docker_deep", return_value=[]),
        ):
            report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        codes = {issue.code for issue in report.issues}
        self.assertIn("playbooks_resolver_active", codes)
        self.assertIn("plan_resolved", codes)
        self.assertIn("playbooks_atlas-node-foundation", codes)
        self.assertNotIn("role_repos_provision_missing", codes)

    def test_validate_rejects_legacy_profile(self) -> None:
        leaf_cfg = self.root / "clusters" / "lab" / "test" / "cluster.yaml"
        data = yaml.safe_load(leaf_cfg.read_text(encoding="utf-8"))
        data["profile"] = "full"
        leaf_cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
        ctx = ClusterContext.load(cluster_id="lab/test")
        with (
            patch("clusterctl.validate.playbook_repo_layout_ready", return_value=True),
            patch("clusterctl.validate.validate_docker_deep", return_value=[]),
        ):
            report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        errors = [issue for issue in report.issues if issue.code == "profile_legacy_removed"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].severity, Severity.ERROR)

if __name__ == "__main__":
    unittest.main()
