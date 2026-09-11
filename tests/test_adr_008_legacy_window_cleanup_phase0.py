"""Cleanup Phase 0 gate: ADR 008 — Variant B legacy anti-regression purge (decision only)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"


class Adr008LegacyWindowCleanupPhase0Test(unittest.TestCase):
    def test_adr_locks_variant_b_cleanup_phase0(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Post-complete cleanup — Variant B", text)
        self.assertIn("Variant B — full purge", text)
        self.assertIn("Rejected — Variant A", text)
        self.assertIn("Cleanup Phase 0 (done)", text)
        self.assertIn("test_adr_008_legacy_window_cleanup_phase0.py", text)
        self.assertIn(
            "[x] Cleanup Variant B Phase 0 locked (decision + gate; no code purge yet)",
            text,
        )
        for phase in ("Cleanup Phase 1", "Cleanup Phase 2", "Cleanup Phase 3"):
            self.assertIn(phase, text, phase)

    def test_out_of_scope_preserves_other_from_flags(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("init --from", text)
        self.assertIn("export_template --from", text)
        self.assertIn("Out of scope (unchanged)", text)
        self.assertIn("argparse", text.lower())
        self.assertIn("from_stage", text)
        self.assertIn("to_stage", text)

    def test_phase0_decision_recorded_no_code_purge_in_phase0(self) -> None:
        """Phase 0 text forbids code purge in that phase (historical acceptance)."""
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("No** deletion of `.sh` / `adr_008_legacy_cli.py` in Phase 0", text)
        self.assertIn("code purge = 1–2", text)

    def test_delete_table_names_targets(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("adr_008_legacy_cli.py", text)
        self.assertIn("check-no-legacy-phase-window.sh", text)
        self.assertIn("PLAN_RUN_LEGACY_PHASE_WINDOW_PATTERN", text)

    def test_adr_index_and_changelog(self) -> None:
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("008-phases-cli-selector.md", index)
        self.assertIn("cleanup B", index)
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008 cleanup Variant B", changelog)
        self.assertIn("Phase 0", changelog)
        self.assertIn("test_adr_008_legacy_window_cleanup_phase0.py", changelog)


if __name__ == "__main__":
    unittest.main()
