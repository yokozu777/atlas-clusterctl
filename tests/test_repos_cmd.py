"""Tests for unified repos sync command (PR-4)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.cluster_config_loader import dump_cluster_config_v2
from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import build_org_baseline_cluster_config, seed_org_baseline_fixture
from clusterctl.repos_cmd import cmd_repos_status, cmd_repos_sync


class ReposCmdTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._seed_v2_cluster()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_v2_cluster(self) -> None:
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        seed_org_baseline_fixture(self.root)
        build_org_baseline_cluster_config(self.root)

        leaf = self.root / "clusters" / "lab" / "test"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab/test",
                    "inventory": "hosts",
                    "playbooks_enabled": True,
                }
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/test",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                }
            ),
            encoding="utf-8",
        )

    def test_repos_sync_delegates_to_playbooks_for_v2(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab/test")
        with patch("clusterctl.repos_cmd.cmd_playbooks_sync", return_value=0) as mocked:
            code = cmd_repos_sync(ctx, dry_run=True)
        self.assertEqual(code, 0)
        mocked.assert_called_once()

    def test_repos_status_delegates_to_playbooks_for_v2(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab/test")
        with patch("clusterctl.repos_cmd.cmd_playbooks_status", return_value=0) as mocked:
            code = cmd_repos_status(ctx)
        self.assertEqual(code, 0)
        mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
