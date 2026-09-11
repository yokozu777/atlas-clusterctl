"""Phase 4: workspace_id canonical default vars fallback (flat default removed)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.workspace_id import (
    WorkspaceIdSource,
    reset_workspace_id_warnings_for_tests,
    resolve_workspace_id_details,
)


class WorkspaceIdFallbackTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_WORKSPACE_ID", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        reset_workspace_id_warnings_for_tests()

    def tearDown(self) -> None:
        reset_workspace_id_warnings_for_tests()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _write_canonical_default(self, data: dict) -> Path:
        path = (
            self.root
            / "clusters"
            / "default"
            / "default"
            / "group_vars"
            / "all"
            / "atlas-node-foundation.yml"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return path

    def _write_legacy_flat_default(self, data: dict) -> Path:
        path = self.root / "clusters" / "default" / "group_vars" / "all" / "cluster.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return path

    def test_prefers_canonical_default_default_vars(self) -> None:
        self._write_canonical_default(
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "canonical.{{ dns_domain_suffix }}",
            }
        )
        self._write_legacy_flat_default(
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "legacy.{{ dns_domain_suffix }}",
            }
        )
        resolution = resolve_workspace_id_details(self.root)
        self.assertEqual(resolution.workspace_id, "canonical.example.com")

    def test_canonical_fallback_merges_atlas_overlay_without_cluster_yml(self) -> None:
        self._write_canonical_default(
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "atlas-only.{{ dns_domain_suffix }}",
            }
        )
        resolution = resolve_workspace_id_details(self.root)
        self.assertEqual(resolution.workspace_id, "atlas-only.example.com")
        self.assertEqual(resolution.source, WorkspaceIdSource.CLUSTER_DOMAIN)

    def test_flat_default_vars_are_ignored(self) -> None:
        """Soft-compat Phase 4: only clusters/default/default is a vars fallback."""
        self._write_legacy_flat_default(
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "legacy.{{ dns_domain_suffix }}",
            }
        )
        with self.assertRaises(ValueError) as ctx:
            resolve_workspace_id_details(self.root)
        self.assertIn("cluster workspace id is empty", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
