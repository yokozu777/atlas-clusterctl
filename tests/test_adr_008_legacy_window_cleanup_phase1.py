"""Cleanup Phase 1 gate: ADR 008 — Variant B purge Python docs scanner (clusterctl)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
LOCAL_LABS = ROOT / "docs" / "local-labs.md"
PHASE4 = ROOT / "tests" / "test_adr_008_phases_cli_selector_phase4.py"
PHASE2 = ROOT / "tests" / "test_adr_008_phases_cli_selector_phase2.py"


class Adr008LegacyWindowCleanupPhase1Test(unittest.TestCase):
    def test_adr_cleanup_phase1_done(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Cleanup Phase 1 (done)", text)
        self.assertIn("Cleanup Phase 1 acceptance", text)
        self.assertIn("test_adr_008_legacy_window_cleanup_phase1.py", text)
        self.assertIn(
            "[x] Cleanup Phase 1 — remove Python docs scanner / script deps (clusterctl)",
            text,
        )
        self.assertIn("Current runtime (Phase 5)", text)
        self.assertIn("Cleanup Phase 1", text)
        self.assertIn("Cleanup Phase 2", text)
        self.assertIn("full `run_ci` not required", text)
        self.assertNotIn("adr_008_legacy_cli`; CI green", text)
        self.assertIn("superseded by Cleanup Phase 2/3 Done", text)

    def test_scanner_modules_deleted(self) -> None:
        self.assertFalse((ROOT / "tests" / "adr_008_legacy_cli.py").is_file())
        self.assertFalse((ROOT / "tests" / "test_adr_008_legacy_cli.py").is_file())
        self.assertIsNone(
            importlib.util.find_spec("tests.adr_008_legacy_cli"),
            "tests.adr_008_legacy_cli must not be importable",
        )

    def test_phase_gates_do_not_import_scanner_or_run_script(self) -> None:
        for path in (PHASE2, PHASE4):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("from tests.adr_008_legacy_cli", text, path.name)
            self.assertNotIn("import tests.adr_008_legacy_cli", text, path.name)
            self.assertNotIn("find_legacy_phase_window_hits", text, path.name)
            self.assertNotIn("check-no-legacy-phase-window", text, path.name)
            self.assertNotIn("SIBLING_INVENTORY", text, path.name)

    def test_phase4_keeps_permanent_hygiene(self) -> None:
        text = PHASE4.read_text(encoding="utf-8")
        self.assertIn("test_argparse_plan_run_reject_from_to_keep_init_from", text)
        self.assertIn("test_grep_retired_dests_allowlist", text)
        self.assertIn("from_stage", text)
        self.assertIn("to_stage", text)
        self.assertIn("test_no_legacy_docs_scanner_module", text)

    def test_operator_docs_no_longer_require_inventory_script(self) -> None:
        labs = LOCAL_LABS.read_text(encoding="utf-8")
        ctl = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertNotIn("./scripts/check-no-legacy-phase-window.sh", labs)
        self.assertNotIn("./scripts/check-no-legacy-phase-window.sh", ctl)
        self.assertIn("argparse", ctl.lower())
        self.assertTrue(
            ("Cleanup Phase 1" in labs)
            or ("Cleanup Phases 1–2" in labs)
            or ("Cleanup Phases 0–3" in labs)
            or ("Cleanup Variant B:** complete" in labs)
            or ("Cleanup Variant B:**complete" in labs.replace(" ", "")),
            "local-labs.md must mention cleanup Variant B progress/complete",
        )
        self.assertTrue(
            ("Cleanup Phase 1" in ctl)
            or ("Cleanup Phases 1–2" in ctl)
            or ("Cleanup Phases 0–3" in ctl)
            or ("Cleanup **Variant B** complete" in ctl)
            or ("Variant B** complete" in ctl),
            "clusterctl.md must mention cleanup Variant B progress/complete",
        )

    def test_adr_index_and_changelog(self) -> None:
        index = ADR_INDEX.read_text(encoding="utf-8")
        # Index advances with cleanup; Phase 1+ status strings remain acceptable.
        self.assertTrue(
            ("cleanup B Phase 1" in index)
            or ("cleanup B Phase 2" in index)
            or ("cleanup B complete" in index),
            index,
        )
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008 cleanup Variant B — Phase 1", changelog)
        self.assertIn("adr_008_legacy_cli.py", changelog)
        self.assertIn("test_adr_008_legacy_window_cleanup_phase1.py", changelog)


if __name__ == "__main__":
    unittest.main()
