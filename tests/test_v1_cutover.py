"""Tests for PR-11: v1 profiles/pipeline runtime removed."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.__main__ import main
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import seed_org_baseline_fixture

class V1CutoverTest(unittest.TestCase):
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
        self._seed_v1_like_cluster()

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
                }
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        (leaf / "pub_keys").mkdir()
        (leaf / "pub_keys" / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/legacy",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                }
            ),
            encoding="utf-8",
        )
        for repo in ("atlas-infra-edge", "atlas-compute-provision", "atlas-node-foundation", "atlas-k8s-core"):
            path = self.root / repo
            path.mkdir()
            if repo == "atlas-k8s-core":
                (path / "00_controller_tooling").mkdir()
            else:
                (path / "roles" / "demo").mkdir(parents=True)

    def test_plan_rejects_v1_cluster(self) -> None:
        code = main(["plan", "--cluster", "lab/legacy"])
        self.assertEqual(code, 1)

    def test_run_rejects_v1_cluster(self) -> None:
        code = main(["run", "--cluster", "lab/legacy", "--dry-run"])
        self.assertEqual(code, 1)

    def test_stage_alias_removed_unknown_command(self) -> None:
        """``stage`` is hard-removed; argparse rejects before cluster load."""
        import contextlib
        import io

        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with contextlib.redirect_stderr(buf):
                main(["stage", "init", "--cluster", "lab/legacy", "--dry-run"])
        self.assertEqual(cm.exception.code, 2)

    def test_run_phases_rejects_v1_cluster(self) -> None:
        code = main(
            ["run", "--phases", "init", "--cluster", "lab/legacy", "--dry-run"]
        )
        self.assertEqual(code, 1)

    def test_repos_sync_rejects_v1_cluster(self) -> None:
        from clusterctl.repos_cmd import cmd_repos_sync

        ctx = ClusterContext.load(cluster_id="lab/legacy")
        with self.assertRaises(ClusterctlError) as exc:
            cmd_repos_sync(ctx, dry_run=True)
        self.assertIn("schema v2", str(exc.exception).lower())

    def test_v2_cluster_plan_ok(self) -> None:
        seed_org_baseline_fixture(self.root)
        leaf = self.root / "clusters" / "lab" / "v2"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab/v2",
                    "inventory": "hosts",
                    "execution": {"mode": "local"},
                }
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text(
            "all:\n  children:\n    k8s_masters:\n      hosts:\n        localhost:\n",
            encoding="utf-8",
        )
        (leaf / "pub_keys").mkdir()
        (leaf / "pub_keys" / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/v2",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                    "provision_stack": "k8s",
                }
            ),
            encoding="utf-8",
        )
        code = main(["plan", "--cluster", "lab/v2"])
        self.assertEqual(code, 0)

if __name__ == "__main__":
    unittest.main()
