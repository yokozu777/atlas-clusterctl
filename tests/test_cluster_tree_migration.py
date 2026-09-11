"""Live hierarchical cluster tree: discovered k8s lab (optional local inventory)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from clusterctl.cluster_config import load_cluster_config
from clusterctl.cluster_layout import discover_config_dir
from clusterctl.context import ClusterContext
from clusterctl.paths import cluster_dir, list_cluster_ids, list_deployable_cluster_ids
from clusterctl.playbooks_resolve import effective_playbooks_config, uses_phase_runner
from tests.lab_support import lab_id_for, lab_path_for, skip_unless_stack


class ClusterTreeMigrationTest(unittest.TestCase):
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

    def test_legacy_flat_dir_absent(self) -> None:
        legacy = self.root / "clusters" / "dev-mxhash.com"
        self.assertFalse(legacy.exists())
        self.assertFalse((legacy / "cluster.yaml").is_file())

    @skip_unless_stack("k8s")
    def test_canonical_tree_exists(self) -> None:
        from clusterctl.paths import clusters_root

        leaf = lab_path_for("k8s")
        assert leaf is not None
        lab_id = lab_id_for("k8s")
        assert lab_id is not None
        env = lab_id.split("/", 1)[0]
        policy = clusters_root(self.root) / env / "default"
        self.assertTrue((leaf / "cluster.yaml").is_file())
        self.assertTrue((leaf / "hosts").is_file())
        self.assertTrue((policy / "cluster.yaml").is_file())

    @skip_unless_stack("k8s")
    def test_discover_config_dir_prefers_hierarchical_leaf(self) -> None:
        from clusterctl.paths import clusters_root

        lab_id = lab_id_for("k8s")
        leaf = lab_path_for("k8s")
        assert lab_id and leaf
        path = discover_config_dir(clusters_root(self.root), lab_id)
        self.assertEqual(path, leaf.resolve())

    @skip_unless_stack("k8s")
    def test_context_load_discovered_k8s_lab(self) -> None:
        lab_id = lab_id_for("k8s")
        leaf = lab_path_for("k8s")
        assert lab_id and leaf
        ctx = ClusterContext.load(cluster_id=lab_id)
        self.assertEqual(ctx.cluster_id, lab_id)
        self.assertEqual(ctx.config_dir.resolve(), leaf.resolve())
        self.assertTrue(uses_phase_runner(ctx))
        playbooks = effective_playbooks_config(ctx)
        for name in (
            "atlas-node-foundation",
            "atlas-compute-provision",
            "atlas-k8s-core",
            "atlas-k8s-addons",
        ):
            self.assertIn(name, playbooks.repos)

    @skip_unless_stack("k8s")
    def test_leaf_cluster_yaml_minimal(self) -> None:
        lab_id = lab_id_for("k8s")
        assert lab_id
        cfg = load_cluster_config(
            cluster_dir(self.root, lab_id),
            lab_id,
            repo_root=self.root,
        )
        self.assertEqual(cfg.schema_version, 2)
        self.assertIsNone(cfg.legacy_profile)
        self.assertFalse(hasattr(cfg, "stacks"))
        cascade = tuple(p.as_posix() for p in cfg.cascade_paths)
        self.assertTrue(any(p.endswith("default/default/cluster.yaml") for p in cascade))
        env = lab_id.split("/", 1)[0]
        self.assertTrue(any(p.endswith(f"{env}/default/cluster.yaml") for p in cascade))
        self.assertTrue(any(p.endswith(f"{lab_id}/cluster.yaml") for p in cascade))

    @skip_unless_stack("k8s")
    def test_list_includes_discovered_lab_not_legacy_dir(self) -> None:
        lab_id = lab_id_for("k8s")
        assert lab_id
        ids = list_cluster_ids(self.root)
        self.assertIn(lab_id, ids)
        self.assertNotIn("dev-mxhash.com", ids)

    @skip_unless_stack("k8s")
    def test_list_deployable_excludes_policy_dirs(self) -> None:
        lab_id = lab_id_for("k8s")
        assert lab_id
        deployable = list_deployable_cluster_ids(self.root)
        all_ids = list_cluster_ids(self.root)
        self.assertIn(lab_id, deployable)
        self.assertNotIn("default/default", deployable)
        env = lab_id.split("/", 1)[0]
        self.assertNotIn(f"{env}/default", deployable)
        self.assertIn("default/default", all_ids)

    @skip_unless_stack("k8s")
    def test_group_vars_cluster_identity_without_injected_paths(self) -> None:
        leaf = lab_path_for("k8s")
        assert leaf
        self.assertFalse(
            (leaf / "group_vars" / "all" / "cluster.yml").exists(),
            "ADR 003 Phase 3: inventory labs omit cluster.yml",
        )
        core = leaf / "group_vars" / "all" / "atlas-k8s-core.yml"
        text = core.read_text(encoding="utf-8")
        self.assertIn("dns_domain_suffix:", text)
        self.assertIn("cluster_domain:", text)
        self.assertNotIn("cluster_id:", text)
        self.assertNotIn("atlas_cluster_root:", text)
        self.assertNotIn("cluster_workspace_root:", text)


if __name__ == "__main__":
    unittest.main()
