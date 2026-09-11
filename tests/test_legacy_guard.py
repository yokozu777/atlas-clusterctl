"""Tests for PR-8 legacy artifact guard."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clusterctl.legacy_guard import find_legacy_artifacts
from clusterctl.validate import Severity, validate_repo


class LegacyGuardTest(unittest.TestCase):
    def test_clean_repo_has_no_legacy_artifacts(self) -> None:
        root = Path(__file__).resolve().parents[1]
        artifacts = find_legacy_artifacts(root)
        self.assertEqual(artifacts, [], [str(a.path) for a in artifacts])

    def test_detects_legacy_pipeline_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
            (root / "clusterctl").mkdir()
            (root / "clusterctl" / "pipeline.yaml").write_text("stages: []\n", encoding="utf-8")
            artifacts = find_legacy_artifacts(root)
            self.assertTrue(any("pipeline.yaml" in str(a.path) for a in artifacts))

    def test_validate_repo_flags_legacy_profile_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
            profiles = root / "profiles"
            profiles.mkdir()
            (profiles / "full.yaml").write_text("name: full\n", encoding="utf-8")
            report = validate_repo(root)
            codes = {issue.code for issue in report.issues if issue.severity == Severity.ERROR}
            self.assertIn("legacy_artifact_present", codes)


if __name__ == "__main__":
    unittest.main()
