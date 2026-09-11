"""Regression tests for playbooks_resolve public API errors (phase 1 / C-02)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import seed_org_baseline_fixture
from clusterctl.playbooks_resolve import (
    effective_playbooks_config,
    require_phase_runner,
)


class PlaybooksResolveErrorsTest(unittest.TestCase):
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

    def _write_cluster(self, *, playbooks_enabled: bool = True) -> None:
        cluster = self.root / "clusters" / "lab"
        all_dir = cluster / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        data: dict = {
            "schema_version": 2,
            "id": "lab",
            "playbooks_enabled": playbooks_enabled,
            "inventory": "hosts",
            "execution": {"mode": "local"},
        }
        (cluster / "cluster.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        (cluster / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        (all_dir / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")

    def test_effective_playbooks_config_raises_clusterctl_error_without_playbooks(self) -> None:
        self._write_cluster()
        ctx = ClusterContext.load(cluster_id="lab")
        with mock.patch.object(type(ctx), "config_v2", new_callable=mock.PropertyMock) as mocked:
            mocked.return_value = None
            with self.assertRaises(ClusterctlError) as raised:
                effective_playbooks_config(ctx)
        self.assertIn("schema v2 playbooks", str(raised.exception))

    def test_require_phase_runner_raises_without_phases(self) -> None:
        self._write_cluster()
        ctx = ClusterContext.load(cluster_id="lab")
        with mock.patch("clusterctl.playbooks_resolve.uses_phase_runner", return_value=False):
            with self.assertRaises(ClusterctlError) as raised:
                require_phase_runner(ctx)
        self.assertIn("playbooks + phases", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
