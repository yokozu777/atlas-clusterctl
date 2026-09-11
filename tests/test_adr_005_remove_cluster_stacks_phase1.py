"""Phase 1 gate: ADR 005 — phases SoT; skip_phase_refs no longer filter (historical)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "005-remove-cluster-stacks.md"
PHASE_INTENT = ROOT / "clusterctl" / "phase_intent.py"
PHASE_PLAN = ROOT / "clusterctl" / "phase_plan.py"
VALIDATE = ROOT / "clusterctl" / "validate.py"
CHANGELOG = ROOT / "CHANGELOG.md"


class Adr005RemoveClusterStacksPhase1Test(unittest.TestCase):
    def test_adr_documents_phase1_outcomes(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 1", text)
        self.assertIn("Status:** Accepted", text)
        self.assertIn("[x] Plan does not apply `skip_phase_refs`", text)
        self.assertIn(
            "[x] Validate intent inferred from `phases:`", text
        )
        self.assertIn("PHASE_INTENT_REFS", text)
        self.assertIn("stacks_legacy", text)

    def test_intent_lives_in_phase_intent_module(self) -> None:
        """Phase 4 moved inference out of deleted stacks.py."""
        intent = PHASE_INTENT.read_text(encoding="utf-8")
        self.assertIn("def infer_phase_intent", intent)
        self.assertIn("PHASE_INTENT_REFS", intent)
        plan = PHASE_PLAN.read_text(encoding="utf-8")
        self.assertIn("ADR 005", plan)
        validate = VALIDATE.read_text(encoding="utf-8")
        self.assertIn("infer_phase_intent", validate)
        self.assertIn("phase intent:", validate)

    def test_changelog_phase1(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 005", text)
        self.assertIn("Phase 1", text)
        self.assertIn("stacks_legacy", text)


if __name__ == "__main__":
    unittest.main()
