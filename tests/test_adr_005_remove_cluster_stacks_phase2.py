"""Phase 2 gate: ADR 005 — plan filter / stacks_skipped UX removed (historical)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "005-remove-cluster-stacks.md"
PHASE_PLAN = ROOT / "clusterctl" / "phase_plan.py"
MAIN = ROOT / "clusterctl" / "__main__.py"
STAGES_CMD = ROOT / "clusterctl" / "stages_cmd.py"
SMOKE = ROOT / "clusterctl" / "smoke.py"
CHANGELOG = ROOT / "CHANGELOG.md"
INTENT_TESTS = ROOT / "tests" / "test_phase_intent.py"


class Adr005RemoveClusterStacksPhase2Test(unittest.TestCase):
    def test_adr_documents_phase2_outcomes(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted", text)
        self.assertIn("Phase 2", text)
        self.assertIn("[x] Plan filter / `stacks_skipped` UX removed", text)
        self.assertIn("apply_stacks_filter", text)
        self.assertIn("stacks_skipped", text)

    def test_plan_filter_api_removed(self) -> None:
        plan = PHASE_PLAN.read_text(encoding="utf-8")
        self.assertNotIn("apply_stacks_filter", plan)
        self.assertNotIn("stacks_skipped", plan)
        self.assertNotIn("stacks_skipped_phase_refs", plan)
        self.assertIn("ADR 005", plan)
        self.assertIn("filter_skipped", plan)
        self.assertIn("When filter skipped", plan)

        for path in (MAIN, STAGES_CMD, SMOKE):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("stacks_skipped", text, path.name)
            self.assertNotIn("apply_stacks_filter", text, path.name)
            self.assertNotIn("Stack filter skipped", text, path.name)

    def test_main_plan_path_does_not_load_stack_flags(self) -> None:
        text = MAIN.read_text(encoding="utf-8")
        self.assertNotIn("load_stack_flags", text)
        self.assertNotIn("stack_flags=", text)

    def test_intent_tests_cover_no_filter_api(self) -> None:
        self.assertTrue(INTENT_TESTS.is_file(), INTENT_TESTS)
        text = INTENT_TESTS.read_text(encoding="utf-8")
        self.assertIn("ADR 005", text)
        self.assertIn("test_execution_plan_is_phases_only", text)
        self.assertNotIn("apply_stacks_filter(", text)
        self.assertNotIn("stack_excluded_phase_refs(", text)

    def test_changelog_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 005", text)
        self.assertIn("Phase 2", text)
        self.assertIn("stacks_skipped", text)


if __name__ == "__main__":
    unittest.main()
