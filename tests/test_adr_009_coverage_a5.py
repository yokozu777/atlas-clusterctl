"""Post–ADR 009 cleanup A5: coverage gaps — ``play -e`` E2E + ``run_ci`` gate scope."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
CHANGELOG = ROOT / "CHANGELOG.md"
PHASE5 = ROOT / "tests" / "test_adr_009_unify_run_stage_play_phase5.py"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"


class Adr009CoverageA5Test(unittest.TestCase):
    def test_adr_run_ci_gate_scope_wording(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("acceptance-time proof", text)
        self.assertIn("does not subprocess", text.lower())
        self.assertIn(".github/workflows/ci.yml", text)
        self.assertIn("post-cleanup A5", text)

    def test_adr_status_aligned_with_a5_scope(self) -> None:
        """Audit Phase 2: Status must not imply unittest subprocesses run_ci."""
        text = ADR.read_text(encoding="utf-8")
        status = text.split("## Context", 1)[0]
        self.assertIn("acceptance-time", status)
        self.assertIn("CI workflow", status)
        self.assertIn("does **not** subprocess", status)
        # Old Status phrasing that read as continuous gate green.
        self.assertNotIn("offline `./tests/run_ci.sh` + sample", status)

    def test_adr_context_marked_historical(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Historical problem statement (pre–Phase 1)", text)
        self.assertIn("Before Phase 1, operators and Jenkins faced", text)
        # Pre-Phase 1 collapse story stays in Context (Decision has current policy).
        context = text.split("## Decision", 1)[0]
        self.assertIn("**collapses**", context)

    def test_ci_workflow_runs_run_ci(self) -> None:
        text = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("./tests/run_ci.sh", text)

    def test_phase5_has_merge_e_e2e(self) -> None:
        text = PHASE5.read_text(encoding="utf-8")
        self.assertIn("test_sample_play_dry_run_merge_e", text)
        self.assertIn("provision_mode=destroy", text)
        self.assertIn("run", text)
        self.assertIn("--phases", text)
        self.assertIn("merge_e", text.lower())

    def test_limit_documented(self) -> None:
        """A1.6 / A5: LIMIT remains in operator env table."""
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("`LIMIT`", text)
        self.assertIn("resolve_run_limit", ADR.read_text(encoding="utf-8"))

    def test_changelog_a5_and_audit_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("post-cleanup A5", text)
        self.assertIn("play", text.lower())
        self.assertIn("test_adr_009_coverage_a5.py", text)
        self.assertIn("audit Phase 2", text)
        self.assertIn("Historical problem statement", ADR.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
