"""Phase 0 gate: ADR 006 — redundant playbooks_enabled: true (contract only)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "006-redundant-playbooks-enabled.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"
CHANGELOG = ROOT / "CHANGELOG.md"
INFER_TESTS = ROOT / "tests" / "test_playbooks_enabled_infer.py"


class Adr006RedundantPlaybooksEnabledPhase0Test(unittest.TestCase):
    def test_adr_exists_and_accepted_phase0(self) -> None:
        self.assertTrue(ADR.is_file(), ADR)
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("no YAML deletion", text)
        self.assertIn("playbooks_enabled: true", text)
        self.assertIn("playbooks_enabled: false", text)
        self.assertIn("effective_playbooks_enabled", text)
        self.assertIn("Out of scope", text)
        for phase in (
            "Phase 0",
            "Phase 1",
            "Phase 2",
            "Phase 3",
            "Phase 4",
            "Phase 5",
        ):
            self.assertIn(phase, text, phase)
        # Semantics table needles.
        self.assertIn("omit `playbooks_enabled`", text)
        self.assertIn("infer", text.lower())

    def test_breaking_checklist_phase0_infer_done(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Breaking changes checklist", text)
        self.assertIn(
            "[x] Infer / cascade / `false` override covered by tests (Phase 0)",
            text,
        )
        # YAML deletion not done yet.
        self.assertIn(
            "[x] Public templates omit redundant `playbooks_enabled: true`",
            text,
        )

    def test_adr_index_and_docs_index(self) -> None:
        adr_index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("006-redundant-playbooks-enabled.md", adr_index)
        self.assertIn("Accepted (Phase", adr_index)
        docs_index = DOCS_INDEX.read_text(encoding="utf-8")
        self.assertIn("006", docs_index)

    def test_schema_doc_phase0_callout(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 006", text)
        self.assertIn("playbooks_enabled", text)
        self.assertIn("infer", text.lower())
        self.assertIn("false", text)
        # Minimal example must not require redundant true (Phase 0 docs).
        self.assertNotIn(
            "playbooks_enabled: true\n\nplaybooks:",
            text.replace("\r\n", "\n"),
        )

    def test_changelog_mentions_adr006_phase0(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 006", text)
        self.assertIn("Phase 0", text)
        self.assertIn("playbooks_enabled", text)

    def test_infer_matrix_tests_exist(self) -> None:
        self.assertTrue(INFER_TESTS.is_file(), INFER_TESTS)
        text = INFER_TESTS.read_text(encoding="utf-8")
        for needle in (
            "test_omit_flag_with_playbooks_infers_enabled",
            "test_explicit_false_disables_even_with_playbooks",
            "test_cascade_both_omit_infers_from_merged_playbooks",
            "test_cascade_parent_true_child_omit_stays_enabled",
            "test_cascade_parent_omit_child_false_disables",
            "test_context_omitted_flag_with_playbooks_is_enabled",
            "test_context_explicit_false_is_disabled",
        ):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
