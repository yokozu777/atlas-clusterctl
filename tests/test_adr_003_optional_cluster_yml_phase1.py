"""Phase 1 gate: ADR 003 soft-require — leaf loads without cluster.yml."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config import load_cluster_config
from clusterctl.cluster_layout import config_dir_is_usable
from clusterctl.cluster_vars_loader import (
    optional_cluster_var_file,
    primary_cluster_var_file,
    require_group_vars_all,
)
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import local_playbooks_override_block, seed_org_baseline_fixture
from clusterctl.paths import cluster_var_file_path


ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "003-optional-cluster-yml.md"
CLUSTERS_DOC = ROOT / "docs" / "clusters.md"


class Adr003OptionalClusterYmlPhase1Test(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "CLUSTER_WORKSPACE_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        self.cluster = self.root / "clusters" / "lab"
        self._write_leaf_without_cluster_yml()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _write_leaf_without_cluster_yml(self) -> None:
        all_dir = self.cluster / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        (self.cluster / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab",
                    "inventory": "hosts",
                    "playbooks": local_playbooks_override_block(),
                    "execution": {"mode": "local"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.cluster / "hosts").write_text(
            "all:\n  children:\n    k8s_masters:\n      hosts:\n        m1: {}\n",
            encoding="utf-8",
        )
        (all_dir / "atlas-node-foundation.yml").write_text(
            yaml.safe_dump(
                {
                    "admin_user": "localuser",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "lab.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        seed_org_baseline_fixture(self.root)
        for repo in (
            "atlas-infra-edge",
            "atlas-compute-provision",
            "atlas-node-foundation",
            "atlas-k8s-core",
        ):
            path = self.root / repo
            path.mkdir()
            if repo == "atlas-k8s-core":
                (path / "00_controller_tooling").mkdir()
            elif repo == "atlas-node-foundation":
                (path / "roles" / "dummy").mkdir(parents=True)
            else:
                (path / "roles").mkdir()

    def test_adr_status_phase1(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 1", text)
        lowered = text.lower()
        self.assertTrue(
            "does not require" in lowered or "no longer requires" in lowered,
            "ADR must state cluster.yml is not required",
        )
        self.assertNotIn("still requires", lowered)

    def test_clusters_md_soft_require(self) -> None:
        text = CLUSTERS_DOC.read_text(encoding="utf-8")
        self.assertIn("does not require", text)
        self.assertIn("atlas-*.yml", text)
        self.assertIn("adr/003-optional-cluster-yml.md", text)

    def test_optional_helpers_return_none(self) -> None:
        self.assertIsNone(optional_cluster_var_file(self.cluster))
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            self.assertIsNone(primary_cluster_var_file(self.cluster))

    def test_require_group_vars_all_ok_without_cluster_yml(self) -> None:
        files = require_group_vars_all(self.cluster)
        self.assertEqual([path.name for path in files], ["atlas-node-foundation.yml"])

    def test_require_group_vars_all_empty_raises(self) -> None:
        empty = self.root / "clusters" / "empty"
        (empty / "group_vars" / "all").mkdir(parents=True)
        (empty / "cluster.yaml").write_text("schema_version: 2\n", encoding="utf-8")
        with self.assertRaises(ClusterctlError) as ctx:
            require_group_vars_all(empty)
        self.assertIn("no group_vars found", str(ctx.exception))

    def test_config_dir_usable_without_cluster_yml(self) -> None:
        self.assertTrue(config_dir_is_usable(self.cluster))

    def test_load_cluster_config_without_cluster_yml(self) -> None:
        cfg = load_cluster_config(self.cluster, "lab", repo_root=self.root)
        self.assertEqual(
            [path.name for path in cfg.group_var_files],
            ["atlas-node-foundation.yml"],
        )

    def test_context_loads_without_cluster_yml(self) -> None:
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        self.assertEqual(ctx.cluster_id, "lab")
        self.assertIsNone(ctx.cluster_var_file)
        self.assertEqual(ctx.workspace_id, "lab.example.com")
        self.assertEqual(
            [path.name for path in ctx.group_var_files],
            ["atlas-node-foundation.yml"],
        )

    def test_cluster_var_file_path_none_without_stub(self) -> None:
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        path = cluster_var_file_path(self.cluster, self.root)
        self.assertIsNone(path)


if __name__ == "__main__":
    unittest.main()
