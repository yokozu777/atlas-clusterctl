"""Cleanup Phase 2 gate: ADR 008 — Variant B delete inventory legacy-window script."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
LOCAL_LABS = ROOT / "docs" / "local-labs.md"
SIBLING_INVENTORY = ROOT.parent / "atlas-inventory"
SCRIPT = SIBLING_INVENTORY / "scripts" / "check-no-legacy-phase-window.sh"


class Adr008LegacyWindowCleanupPhase2Test(unittest.TestCase):
    def test_adr_cleanup_phase2_done(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Cleanup Phase 2 (done)", text)
        self.assertIn("Cleanup Phase 2 acceptance", text)
        self.assertIn("test_adr_008_legacy_window_cleanup_phase2.py", text)
        self.assertIn(
            "[x] Cleanup Phase 2 — delete inventory `check-no-legacy-phase-window.sh`",
            text,
        )
        self.assertIn("**Done** — file gone from HEAD", text)
        self.assertIn("Cleanup Phase 2 (done)", text)
        # Forward-compatible: Phase 3 may already be closed.
        self.assertTrue(
            ("Cleanup Phase 3 pending" in text)
            or ("Cleanup Phase 3 (done)" in text)
            or ("Variant B complete" in text)
            or ("Phases 0–3 complete" in text),
            "ADR must record Phase 3 pending or complete",
        )

    def test_inventory_script_deleted_when_sibling_present(self) -> None:
        if not (SIBLING_INVENTORY / ".git").is_dir() and not (
            SIBLING_INVENTORY / "clusters"
        ).is_dir():
            self.skipTest("sibling atlas-inventory not present")
        self.assertFalse(
            SCRIPT.is_file(),
            f"{SCRIPT} must be deleted (Cleanup Phase 2)",
        )
        # Empty scripts/ dir is fine; tracked path must be gone from git index.
        import subprocess

        proc = subprocess.run(
            ["git", "ls-files", "--", "scripts/check-no-legacy-phase-window.sh"],
            cwd=SIBLING_INVENTORY,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.strip(),
            "",
            "script still tracked in atlas-inventory git index",
        )

    def test_operator_docs_do_not_instruct_running_script(self) -> None:
        labs = LOCAL_LABS.read_text(encoding="utf-8")
        ctl = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        for text, name in ((labs, "local-labs.md"), (ctl, "clusterctl.md")):
            self.assertNotIn("./scripts/check-no-legacy-phase-window.sh", text, name)
            self.assertIn("Cleanup", text, name)
            self.assertIn("Variant B", text, name)

    def test_adr_index_and_changelog(self) -> None:
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertTrue(
            ("cleanup B Phase 2" in index) or ("cleanup B complete" in index),
            index,
        )
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008 cleanup Variant B — Phase 2", changelog)
        self.assertIn("check-no-legacy-phase-window.sh", changelog)
        self.assertIn("test_adr_008_legacy_window_cleanup_phase2.py", changelog)


if __name__ == "__main__":
    unittest.main()
