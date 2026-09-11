"""Tests for local config.yaml and ATLAS_CLUSTERS_ROOT / workspace resolution."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from clusterctl.cluster_layout import cascade_fragment_paths
from clusterctl.paths import (
    cascade_paths_for_cluster,
    clusters_root,
    product_clusters_root,
    workspace_parent,
    workspace_root,
)
from clusterctl.user_config import (
    clusters_path_from_user_config,
    git_ssh_key_from_user_config,
    load_user_config,
    local_config_path,
    workspace_path_from_user_config,
)


class LocalConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._cfg_override = os.environ.pop("ATLAS_CLUSTERCTL_CONFIG", None)

    def tearDown(self) -> None:
        if self._cfg_override is None:
            os.environ.pop("ATLAS_CLUSTERCTL_CONFIG", None)
        else:
            os.environ["ATLAS_CLUSTERCTL_CONFIG"] = self._cfg_override

    def test_local_config_path_under_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(local_config_path(root), root / ".config" / "config.yaml")

    def test_config_path_override_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom.yaml"
            prev = os.environ.get("ATLAS_CLUSTERCTL_CONFIG")
            try:
                os.environ["ATLAS_CLUSTERCTL_CONFIG"] = str(custom)
                self.assertEqual(local_config_path(Path(tmp)), custom)
            finally:
                if prev is None:
                    os.environ.pop("ATLAS_CLUSTERCTL_CONFIG", None)
                else:
                    os.environ["ATLAS_CLUSTERCTL_CONFIG"] = prev

    def test_load_missing_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent.yaml"
            self.assertEqual(load_user_config(missing), {})

    def test_clusters_path_relative_to_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inv = root / "inventory" / "clusters"
            inv.mkdir(parents=True)
            cfg = {"clusters": {"path": "inventory/clusters"}}
            resolved = clusters_path_from_user_config(cfg, repo_root=root)
            self.assertEqual(resolved, inv.resolve())

    def test_workspace_path_relative_to_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "runtime" / "workspace"
            ws.mkdir(parents=True)
            cfg = {"workspace": {"path": "runtime/workspace"}}
            resolved = workspace_path_from_user_config(cfg, repo_root=root)
            self.assertEqual(resolved, ws.resolve())

    def test_git_ssh_key_relative_to_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = root / "keys" / "id_ed25519"
            key.parent.mkdir()
            key.write_text("dummy\n", encoding="utf-8")
            cfg = {"git": {"ssh_key": "keys/id_ed25519"}}
            resolved = git_ssh_key_from_user_config(cfg, repo_root=root)
            self.assertEqual(resolved, key.resolve())

    def test_git_ssh_key_unset(self) -> None:
        self.assertIsNone(git_ssh_key_from_user_config({}, repo_root=Path("/tmp")))


class ClustersRootResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = {
            key: os.environ.get(key)
            for key in (
                "ATLAS_CLUSTERS_ROOT",
                "ATLAS_WORKSPACE_ROOT",
                "ATLAS_CLUSTERCTL_CONFIG",
            )
        }

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_fallback_to_product_clusters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "clusters").mkdir()
            os.environ.pop("ATLAS_CLUSTERS_ROOT", None)
            os.environ["ATLAS_CLUSTERCTL_CONFIG"] = str(root / "missing.yaml")
            self.assertEqual(clusters_root(root), (root / "clusters").resolve())
            self.assertEqual(product_clusters_root(root), (root / "clusters").resolve())

    def test_env_overrides_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "clusters").mkdir()
            inventory = root / "inv" / "clusters"
            inventory.mkdir(parents=True)
            (root / ".config").mkdir()
            (root / ".config" / "config.yaml").write_text(
                "clusters:\n  path: inv/clusters\n",
                encoding="utf-8",
            )
            os.environ.pop("ATLAS_CLUSTERCTL_CONFIG", None)
            os.environ["ATLAS_CLUSTERS_ROOT"] = str(inventory)
            self.assertEqual(clusters_root(root), inventory.resolve())

    def test_local_config_clusters_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "clusters").mkdir()
            inventory = root / "inv" / "clusters"
            inventory.mkdir(parents=True)
            (root / ".config").mkdir()
            (root / ".config" / "config.yaml").write_text(
                "clusters:\n  path: inv/clusters\n",
                encoding="utf-8",
            )
            os.environ.pop("ATLAS_CLUSTERS_ROOT", None)
            os.environ.pop("ATLAS_CLUSTERCTL_CONFIG", None)
            self.assertEqual(clusters_root(root), inventory.resolve())

    def test_cascade_falls_back_to_product_org_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = root / "clusters"
            org = product / "default" / "default"
            org.mkdir(parents=True)
            (org / "cluster.yaml").write_text(
                "schema_version: 2\nid: default/default\n",
                encoding="utf-8",
            )
            inventory = root / "inv" / "clusters"
            leaf = inventory / "lab" / "demo"
            leaf.mkdir(parents=True)
            (leaf / "cluster.yaml").write_text(
                "schema_version: 2\nid: lab/demo\n",
                encoding="utf-8",
            )
            (root / ".config").mkdir()
            (root / ".config" / "config.yaml").write_text(
                f"clusters:\n  path: {inventory}\n",
                encoding="utf-8",
            )
            os.environ.pop("ATLAS_CLUSTERS_ROOT", None)
            os.environ.pop("ATLAS_CLUSTERCTL_CONFIG", None)
            paths = cascade_paths_for_cluster(root, "lab/demo")
            self.assertEqual(
                [p.resolve() for p in paths],
                [
                    (org / "cluster.yaml").resolve(),
                    (leaf / "cluster.yaml").resolve(),
                ],
            )

    def test_cascade_fragment_paths_product_kwarg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inventory = Path(tmp) / "inv"
            product = Path(tmp) / "product"
            org = product / "default" / "default"
            org.mkdir(parents=True)
            (org / "cluster.yaml").write_text("id: default/default\n", encoding="utf-8")
            leaf = inventory / "a" / "b"
            leaf.mkdir(parents=True)
            (leaf / "cluster.yaml").write_text("id: a/b\n", encoding="utf-8")
            paths = cascade_fragment_paths(
                inventory,
                "a/b",
                product_clusters_root=product,
            )
            self.assertEqual(paths[0], (org / "cluster.yaml").resolve())
            self.assertEqual(paths[-1], (leaf / "cluster.yaml").resolve())

    def test_local_config_workspace_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "clusters").mkdir()
            custom_ws = root / "runtime" / "ws"
            custom_ws.mkdir(parents=True)
            (root / ".config").mkdir()
            (root / ".config" / "config.yaml").write_text(
                "workspace:\n  path: runtime/ws\n",
                encoding="utf-8",
            )
            os.environ.pop("ATLAS_WORKSPACE_ROOT", None)
            os.environ.pop("ATLAS_CLUSTERS_ROOT", None)
            os.environ.pop("ATLAS_CLUSTERCTL_CONFIG", None)
            self.assertEqual(workspace_parent(root), custom_ws.resolve())
            self.assertEqual(
                workspace_root(root, "lab/demo"),
                custom_ws.resolve() / "lab" / "demo",
            )

    def test_env_workspace_overrides_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            via_env = root / "from-env"
            via_env.mkdir()
            (root / ".config").mkdir()
            (root / ".config" / "config.yaml").write_text(
                "workspace:\n  path: from-config\n",
                encoding="utf-8",
            )
            os.environ.pop("ATLAS_CLUSTERCTL_CONFIG", None)
            os.environ["ATLAS_WORKSPACE_ROOT"] = str(via_env)
            self.assertEqual(workspace_parent(root), via_env.resolve())


if __name__ == "__main__":
    unittest.main()
