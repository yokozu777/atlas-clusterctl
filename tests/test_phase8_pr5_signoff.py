"""Phase 8 PR-5: CI preflight, workspace purge, retired materialized repos."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clusterctl.legacy_guard import RETIRED_PLAYBOOK_REPO_DIRS, find_legacy_artifacts
from clusterctl.tools.ci_preflight import main as ci_preflight_main
from clusterctl.tools.purge_legacy_materialized_repos import (
    find_retired_workspace_materialized_paths,
    purge_retired_workspace_materialized,
)

_K8S_RETIRED = RETIRED_PLAYBOOK_REPO_DIRS[3][0]
_FOUNDATION_RETIRED = RETIRED_PLAYBOOK_REPO_DIRS[0][0]


class Phase8PR5SignoffTest(unittest.TestCase):
    def test_retired_workspace_repo_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "workspace" / "k8s.example.com" / "repos" / _K8S_RETIRED
            legacy.mkdir(parents=True)
            (legacy / "README").write_text("legacy", encoding="utf-8")

            artifacts = find_legacy_artifacts(root)
            kinds = {artifact.kind for artifact in artifacts}
            self.assertIn("retired_workspace_repo", kinds)
            self.assertTrue(any(_K8S_RETIRED in str(a.path) for a in artifacts))

    def test_purge_removes_retired_workspace_materialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "workspace" / "k8s.example.com" / "repos" / _FOUNDATION_RETIRED
            legacy.mkdir(parents=True)
            (legacy / "marker").write_text("x", encoding="utf-8")

            found = find_retired_workspace_materialized_paths(root)
            self.assertEqual(len(found), 1)

            removed = purge_retired_workspace_materialized(root, dry_run=False)
            self.assertEqual(len(removed), 1)
            self.assertFalse(legacy.exists())
            self.assertEqual(find_retired_workspace_materialized_paths(root), [])

    def test_ci_preflight_skip_tests_passes_on_real_repo(self) -> None:
        code = ci_preflight_main(["--skip-tests"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
