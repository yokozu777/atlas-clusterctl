"""Phase 3/5: playbooks_validate module and import graph."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

from clusterctl.pipeline_fixture import seed_org_baseline_fixture
from clusterctl.playbooks_resolve import validate_org_baseline_playbooks


class PlaybooksValidateModuleTest(unittest.TestCase):
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

    def test_validate_org_baseline_single_implementation(self) -> None:
        from clusterctl.playbooks_validate import (
            validate_org_baseline_playbooks as validate_fresh,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from clusterctl.role_repos import validate_role_repos_defaults_file

        self.assertIs(validate_role_repos_defaults_file, validate_fresh)
        self.assertIs(validate_org_baseline_playbooks, validate_fresh)

    def test_validate_org_baseline_playbooks_ok(self) -> None:
        config = validate_org_baseline_playbooks(self.root)
        self.assertTrue(config.is_configured())
        self.assertIn("atlas-k8s-core", config.specs)

    def test_import_graph_without_circular_error(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            for name in (
                "clusterctl.playbooks_validate",
                "clusterctl.playbooks_repos",
                "clusterctl.role_repos",
                "clusterctl.playbooks_resolve",
            ):
                importlib.import_module(name)
        # Import only — avoid importlib.reload (rebinds aliases across modules).
        self.assertIn("clusterctl.playbooks_resolve", sys.modules)
        self.assertIn("clusterctl.playbooks_repos", sys.modules)


if __name__ == "__main__":
    unittest.main()
