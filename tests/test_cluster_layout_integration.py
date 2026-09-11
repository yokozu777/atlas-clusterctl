"""Integration tests for PR-1 layout + cascade wiring."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config import load_cluster_config
from clusterctl.cluster_layout import canonical_cluster_id, discover_config_dir
from clusterctl.config_cmd import cmd_config_effective
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterNotFoundError
from clusterctl.paths import cluster_dir, list_cluster_ids, resolve_cluster_id, write_active_cluster_id
from clusterctl.pipeline_fixture import build_org_baseline_cluster_config, seed_org_baseline_fixture
from clusterctl.cluster_config_loader import dump_cluster_config_v2


class ClusterLayoutIntegrationTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "ATLAS_CLUSTERS_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._seed_repo()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_repo(self) -> None:
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        seed_org_baseline_fixture(self.root)
        build_org_baseline_cluster_config(self.root)

        env_policy = self.root / "clusters" / "fixture" / "default"
        env_policy.mkdir(parents=True)
        (env_policy / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "fixture/default",
                    "playbooks": {
                        "atlas-node-foundation": {
                            "source": "local",
                            "path": "atlas-node-foundation",
                            "path_relative_to": "sibling",
                            "layout": "roles/",
                            "sync": "never",
                        }
                    },
                    "execution": {"mode": "local"},
                }
            ),
            encoding="utf-8",
        )

        leaf = self.root / "clusters" / "fixture" / "k8s"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "fixture/k8s",
                    "display_name": "Dev test",
                    "inventory": "hosts",
                    "cluster_id_aliases": {"fixture-k8s.example": "fixture/k8s"},
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
                    "cluster_id": "fixture/k8s",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                }
            ),
            encoding="utf-8",
        )
        (leaf / "pub_keys").mkdir()
        (leaf / "pub_keys" / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")

    def test_legacy_alias_resolves_to_hierarchical_leaf(self) -> None:
        path = discover_config_dir(self.root / "clusters", "fixture/k8s")
        self.assertEqual(path.name, "k8s")
        self.assertEqual(path.parent.name, "fixture")

    def test_canonical_cluster_id_alias(self) -> None:
        # Alias is cascade-declared on the leaf (soft-compat Phase 4: no builtin map).
        ClusterContext.load(cluster_id="fixture/k8s")
        self.assertEqual(canonical_cluster_id("fixture-k8s.example"), "fixture/k8s")

    def test_cluster_dir_via_paths(self) -> None:
        path = cluster_dir(self.root, "fixture/k8s")
        self.assertTrue((path / "hosts").is_file())

    def test_load_config_merges_v2_cascade(self) -> None:
        cfg = load_cluster_config(
            cluster_dir(self.root, "fixture/k8s"),
            "fixture/k8s",
            repo_root=self.root,
        )
        self.assertEqual(cfg.schema_version, 2)
        self.assertIsNotNone(cfg.config_v2)
        assert cfg.config_v2 is not None
        self.assertTrue(cfg.config_v2.effective_playbooks_enabled())
        self.assertEqual(cfg.config_v2.execution.get("mode"), "local")
        self.assertEqual(cfg.config_v2.playbooks.repos["atlas-node-foundation"].source, "local")
        self.assertGreaterEqual(len(cfg.cascade_paths), 3)

    def test_context_load_canonical_id(self) -> None:
        ctx = ClusterContext.load(cluster_id="fixture/k8s")
        self.assertEqual(ctx.cluster_id, "fixture/k8s")
        self.assertEqual(ctx.schema_version, 2)
        self.assertTrue(ctx.deployable)
        self.assertIsNotNone(ctx.config_v2)

    def test_list_cluster_ids_canonical(self) -> None:
        ids = list_cluster_ids(self.root)
        self.assertIn("fixture/k8s", ids)
        self.assertIn("default/default", ids)

    def test_use_writes_canonical_id(self) -> None:
        ClusterContext.load(cluster_id="fixture/k8s")
        path = write_active_cluster_id("fixture-k8s.example", self.root)
        self.assertEqual(path.read_text(encoding="utf-8").strip(), "fixture/k8s")
        self.assertEqual(resolve_cluster_id(root=self.root), "fixture/k8s")

    def test_config_effective_org_baseline(self) -> None:
        code = cmd_config_effective(
            None,
            cluster_id="default/default",
            repo_root_path=self.root,
            as_json=False,
        )
        self.assertEqual(code, 0)

    def test_config_effective_deployable_cluster(self) -> None:
        ctx = ClusterContext.load(cluster_id="fixture/k8s")
        code = cmd_config_effective(
            ctx,
            cluster_id="fixture/k8s",
            repo_root_path=self.root,
            as_json=False,
        )
        self.assertEqual(code, 0)

    def test_org_baseline_not_loadable_as_context(self) -> None:
        with self.assertRaises(ClusterNotFoundError):
            ClusterContext.load(cluster_id="default/default")


if __name__ == "__main__":
    unittest.main()
