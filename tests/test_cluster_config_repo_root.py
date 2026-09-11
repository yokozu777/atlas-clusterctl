"""Regression tests for load_cluster_config repo_root inference (phase 1 / C-01)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config import load_cluster_config
from clusterctl.cluster_layout import (
    cluster_id_from_config_dir,
    infer_repo_root_from_config_dir,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.paths import cluster_dir, cluster_var_file_path, clusters_root
from clusterctl.pipeline_fixture import seed_org_baseline_fixture


class ClusterConfigRepoRootTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "ATLAS_CLUSTERS_ROOT")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        seed_org_baseline_fixture(self.root)
        self._seed_hierarchical_cluster()
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
        self._tmpdir.cleanup()

    def _seed_hierarchical_cluster(self) -> None:
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
                },
                sort_keys=False,
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
                    "inventory": "hosts",
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
                    "cluster_id": "fixture/k8s",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        flat = self.root / "clusters" / "lab"
        flat.mkdir(parents=True)
        (flat / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab",
                    "inventory": "hosts",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (flat / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        (flat / "group_vars" / "all").mkdir(parents=True)
        (flat / "group_vars" / "all" / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.lab.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def test_infer_repo_root_from_hierarchical_config_dir(self) -> None:
        config_dir = self.root / "clusters" / "fixture" / "k8s"
        self.assertEqual(infer_repo_root_from_config_dir(config_dir), self.root.resolve())

    def test_cluster_id_from_config_dir_hierarchical(self) -> None:
        config_dir = self.root / "clusters" / "fixture" / "k8s"
        self.assertEqual(
            cluster_id_from_config_dir(config_dir),
            "fixture/k8s",
        )

    def test_cluster_id_from_config_dir_flat_legacy(self) -> None:
        config_dir = self.root / "clusters" / "lab"
        self.assertEqual(cluster_id_from_config_dir(config_dir), "lab")

    def test_load_cluster_config_without_repo_root_hierarchical(self) -> None:
        config_dir = cluster_dir(self.root, "fixture/k8s")
        cfg = load_cluster_config(config_dir, "fixture/k8s")
        self.assertEqual(len(cfg.cascade_paths), 3)
        self.assertEqual(cfg.schema_version, 2)
        self.assertIsNotNone(cfg.config_v2)

    def test_load_cluster_config_without_repo_root_matches_explicit(self) -> None:
        config_dir = cluster_dir(self.root, "fixture/k8s")
        inferred = load_cluster_config(config_dir, "fixture/k8s")
        explicit = load_cluster_config(config_dir, "fixture/k8s", repo_root=self.root)
        self.assertEqual(inferred.cascade_paths, explicit.cascade_paths)
        self.assertEqual(inferred.schema_version, explicit.schema_version)

    def test_load_cluster_config_wrong_cluster_id_still_uses_explicit_id(self) -> None:
        """Cascade paths follow the cluster_id argument — callers must pass canonical id."""
        config_dir = cluster_dir(self.root, "fixture/k8s")
        wrong = load_cluster_config(config_dir, "k8s")
        right = load_cluster_config(config_dir, "fixture/k8s")
        self.assertLess(len(wrong.cascade_paths), len(right.cascade_paths))

    def test_cluster_var_file_path_uses_hierarchical_cluster_id(self) -> None:
        config_dir = cluster_dir(self.root, "fixture/k8s")
        path = cluster_var_file_path(config_dir, self.root)
        self.assertEqual(path, config_dir / "group_vars" / "all" / "cluster.yml")

    def test_cluster_var_file_path_none_when_stub_absent(self) -> None:
        config_dir = cluster_dir(self.root, "fixture/k8s")
        stub = config_dir / "group_vars" / "all" / "cluster.yml"
        product = config_dir / "group_vars" / "all" / "atlas-node-foundation.yml"
        product.write_text(
            yaml.safe_dump(
                {
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self.assertTrue(stub.is_file())
        stub.unlink()
        path = cluster_var_file_path(config_dir, self.root)
        self.assertIsNone(path)

    def test_infer_repo_root_raises_outside_clusters_tree(self) -> None:
        with self.assertRaises(ClusterctlError):
            infer_repo_root_from_config_dir(self.root / "workspace" / "foo")


if __name__ == "__main__":
    unittest.main()
