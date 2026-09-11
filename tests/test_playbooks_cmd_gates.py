"""Phase 2: unified playbooks/repos CLI gates."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import seed_local_playbook_repo_stubs, seed_org_baseline_fixture
from clusterctl.playbooks_cmd import cmd_playbooks_show, cmd_playbooks_status, cmd_playbooks_sync
from clusterctl.playbooks_resolve import require_effective_playbooks_context
from clusterctl.repos_cmd import cmd_repos_sync


class PlaybooksCmdGatesTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        (self.root / "workspace").mkdir(exist_ok=True)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_v1_like_cluster(self) -> None:
        leaf = self.root / "clusters" / "lab" / "legacy"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "lab/legacy",
                    "inventory": "hosts",
                    "playbooks_enabled": True,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/legacy",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / "atlas-node-foundation" / "roles" / "demo").mkdir(parents=True)

    def _seed_v2_cluster(self) -> None:
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
                    "playbooks_enabled": True,
                },
                sort_keys=False,
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
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def test_playbooks_sync_rejects_v1_cluster(self) -> None:
        self._seed_v1_like_cluster()
        ctx = ClusterContext.load(cluster_id="lab/legacy")
        with self.assertRaises(ClusterctlError) as raised:
            cmd_playbooks_sync(ctx, dry_run=True)
        self.assertIn("schema v2 playbooks + phases", str(raised.exception))

    def test_repos_sync_rejects_v1_cluster_with_same_gate(self) -> None:
        self._seed_v1_like_cluster()
        ctx = ClusterContext.load(cluster_id="lab/legacy")
        with self.assertRaises(ClusterctlError) as raised:
            cmd_repos_sync(ctx, dry_run=True)
        self.assertIn("schema v2 playbooks + phases", str(raised.exception))

    def test_playbooks_status_rejects_v1_cluster(self) -> None:
        self._seed_v1_like_cluster()
        ctx = ClusterContext.load(cluster_id="lab/legacy")
        with self.assertRaises(ClusterctlError):
            cmd_playbooks_status(ctx)

    def test_playbooks_show_rejects_v1_cluster(self) -> None:
        self._seed_v1_like_cluster()
        ctx = ClusterContext.load(cluster_id="lab/legacy")
        with self.assertRaises(ClusterctlError):
            cmd_playbooks_show(ctx)

    def test_playbooks_and_repos_share_require_effective_playbooks_context(self) -> None:
        self._seed_v2_cluster()
        ctx = ClusterContext.load(cluster_id="lab/test")
        playbooks, phases = require_effective_playbooks_context(ctx)
        self.assertIsNotNone(playbooks.repos)
        self.assertGreater(len(phases.phases), 0)

        with patch(
            "clusterctl.playbooks_cmd.require_effective_playbooks_context",
            return_value=(playbooks, phases),
        ) as mocked:
            cmd_playbooks_sync(ctx, dry_run=True)
            cmd_repos_sync(ctx, dry_run=True)
        self.assertEqual(mocked.call_count, 2)

    def test_playbooks_sync_ok_for_v2_cascade_cluster(self) -> None:
        self._seed_v2_cluster()
        ctx = ClusterContext.load(cluster_id="lab/test")
        code = cmd_playbooks_sync(ctx, dry_run=True)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
