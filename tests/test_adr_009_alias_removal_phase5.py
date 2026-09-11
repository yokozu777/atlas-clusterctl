"""ADR 009 alias-removal Phase 5: ``./tests/run_ci.sh`` acceptance after hard remove."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
RUN_CI = ROOT / "tests" / "run_ci.sh"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RUN_OVERRIDES = ROOT / "clusterctl" / "run_overrides.py"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"


class Adr009AliasRemovalPhase5Test(unittest.TestCase):
    def test_run_ci_script_present(self) -> None:
        self.assertTrue(RUN_CI.is_file(), RUN_CI)
        self.assertTrue(os.access(RUN_CI, os.X_OK), f"{RUN_CI} not executable")
        text = RUN_CI.read_text(encoding="utf-8")
        self.assertIn("unittest", text.lower())
        self.assertTrue(CI_WORKFLOW.is_file(), CI_WORKFLOW)
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("./tests/run_ci.sh", workflow)

    def test_adr_phase5_complete(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("[x] Offline ``run_ci`` green after removal (Phase 5)", text)
        self.assertIn("test_adr_009_alias_removal_phase5.py", text)
        self.assertIn("alias removal phase 5", text.lower())
        self.assertIn("Phase 1–5 done", text)
        # Alias-removal follow-up fully closed.
        self.assertIn("alias hard-removal Phase 1–5 done", text)
        self.assertRegex(
            text,
            r"Phase 5.*\./tests/run_ci\.sh.*\*\*done\*\*",
        )
        runtime = text.split("## Current runtime", 1)[1].split("## Target end state", 1)[0]
        self.assertIn("run_ci.sh", runtime)
        self.assertIn("alias-removal Phase 1–5", runtime)
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("alias hard-removal Phase 1–5 done", index)

    def test_changelog_phase5(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("alias removal Phase 5", text)
        self.assertIn("test_adr_009_alias_removal_phase5.py", text)
        self.assertIn("run_ci.sh", text)
        # Hygiene fix that unblocked acceptance.
        self.assertIn("_merge_extra_into_phase_plan", text)

    def test_run_overrides_no_retired_dest_substring(self) -> None:
        """ADR 008 retired-dest grep must not trip on merge helper names."""
        text = RUN_OVERRIDES.read_text(encoding="utf-8")
        self.assertIn("def _merge_extra_into_phase_plan", text)
        # Build needles at runtime so this gate file is not itself a hit.
        retired = ("from" + "_stage", "to" + "_stage")
        for needle in retired:
            self.assertNotIn(needle, text)
        self.assertNotIn("_merge_extra_into_" + "stage", text)

    def test_clusterctl_doc_phase5(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("alias-removal Phase 1–5", text)
        self.assertIn("**Removed** (ADR 009 alias-removal Phase 1–5)", text)


if __name__ == "__main__":
    unittest.main()
