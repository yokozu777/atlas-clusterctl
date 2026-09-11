"""Phase 7: removed leaf role_repos overlay."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config import load_cluster_config
from clusterctl.exceptions import ClusterctlError
from clusterctl.paths import cluster_dir
from clusterctl.pipeline_fixture import seed_org_baseline_fixture


class LeafRoleReposRemovedTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        seed_org_baseline_fixture(self.root)
        self._saved_root = os.environ.get("ATLAS_CLUSTER_ROOT")
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        if self._saved_root is None:
            os.environ.pop("ATLAS_CLUSTER_ROOT", None)
        else:
            os.environ["ATLAS_CLUSTER_ROOT"] = self._saved_root
        self._tmpdir.cleanup()

    def test_leaf_role_repos_rejected(self) -> None:
        leaf = self.root / "clusters" / "dev" / "overlay"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "dev/overlay",
                    "inventory": "hosts",
                    "playbooks_enabled": True,
                    "role_repos": {
                        "atlas-k8s-core": {"ref": "feature-branch"},
                    },
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
                    "cluster_id": "dev/overlay",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.overlay.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        config_dir = cluster_dir(self.root, "dev/overlay")
        with self.assertRaises(ClusterctlError) as ctx:
            load_cluster_config(config_dir, "dev/overlay", repo_root=self.root)
        self.assertIn("role_repos removed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
