"""Tests for PR-12: clusters tree cleanup (no legacy flat id, default scaffold)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from clusterctl.cluster_layout import discover_config_dir, is_deployable_config_dir
from clusterctl.paths import list_cluster_ids, list_deployable_cluster_ids
from clusterctl.workspace_id import resolve_workspace_id
from tests.lab_support import (
    assert_known_labs_subset,
    lab_id_for,
    lab_path_for,
    skip_unless_stack,
)


class ClustersCleanupTest(unittest.TestCase):
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

    def test_legacy_flat_dir_removed(self) -> None:
        legacy_dir = self.root / "clusters" / "dev-mxhash.com"
        self.assertFalse(legacy_dir.exists(), "legacy flat cluster dir must stay removed")

    @skip_unless_stack("k8s")
    def test_discover_resolves_discovered_k8s_lab(self) -> None:
        from clusterctl.context import ClusterContext
        from clusterctl.paths import clusters_root

        lab_id = lab_id_for("k8s")
        leaf = lab_path_for("k8s")
        assert lab_id and leaf
        ClusterContext.load(cluster_id=lab_id)
        path = discover_config_dir(clusters_root(self.root), lab_id)
        self.assertEqual(path, leaf.resolve())

    def test_dev_mxhash_com_not_listed_as_cluster_id(self) -> None:
        ids = list_cluster_ids(self.root)
        self.assertNotIn("dev-mxhash.com", ids)

    def test_default_scaffold_uses_example_dns(self) -> None:
        core = (
            self.root
            / "clusters"
            / "default"
            / "default"
            / "group_vars"
            / "all"
            / "atlas-k8s-core.yml"
        )
        text = core.read_text(encoding="utf-8")
        self.assertIn("dns_domain_suffix: example.com", text)
        self.assertNotIn("dns_domain_suffix: dev-mxhash.com", text)
        stub = (
            self.root
            / "clusters"
            / "default"
            / "default"
            / "group_vars"
            / "all"
            / "cluster.yml"
        )
        self.assertFalse(stub.exists(), "ADR 003 Phase 3: default scaffold omits cluster.yml")

    def test_default_hosts_are_empty_scaffold(self) -> None:
        hosts = (self.root / "clusters" / "default" / "hosts").read_text(encoding="utf-8")
        self.assertIn("k8s_masters:", hosts)
        self.assertIn("hosts: {}", hosts)
        self.assertNotIn("dev-mxhash.com", hosts)
        self.assertNotIn("lb1.example.com", hosts)

    def test_default_flat_scaffold_not_deployable(self) -> None:
        flat_default = self.root / "clusters" / "default"
        self.assertFalse(is_deployable_config_dir(flat_default))
        self.assertFalse((flat_default / "cluster.yaml").is_file())

    @skip_unless_stack("k8s")
    def test_default_and_lab_workspace_ids_differ(self) -> None:
        default_vars = (
            self.root / "clusters" / "default" / "default" / "group_vars" / "all"
        )
        leaf = lab_path_for("k8s")
        assert leaf
        lab_vars = leaf / "group_vars" / "all"

        default_ws = resolve_workspace_id(
            self.root,
            group_var_files=tuple(sorted(default_vars.glob("*.yml"))),
        )
        lab_ws = resolve_workspace_id(
            self.root,
            group_var_files=tuple(sorted(lab_vars.glob("*.yml"))),
        )
        self.assertEqual(default_ws, "k8s.example.com")
        self.assertNotEqual(default_ws, lab_ws)

    def test_deployable_clusters_are_known_labs_subset(self) -> None:
        deployable = list_deployable_cluster_ids(self.root)
        assert_known_labs_subset(self, deployable)


if __name__ == "__main__":
    unittest.main()
