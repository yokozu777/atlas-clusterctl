"""Phase 0 gate: ADR 007 — inline phase aliases (contract only)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "007-phases-inline-aliases.md"
ADR_005 = ROOT / "docs" / "adr" / "005-remove-cluster-stacks.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CONTRACT_TESTS = ROOT / "tests" / "test_phases_inline_aliases_contract.py"


class Adr007PhasesInlineAliasesPhase0Test(unittest.TestCase):
    def test_adr_exists_and_accepted_phase0(self) -> None:
        self.assertTrue(ADR.is_file(), ADR)
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("no YAML deletion", text)
        self.assertIn("phase_aliases", text)
        self.assertIn("Out of scope", text)
        self.assertIn("no dual-read", text.lower())
        self.assertIn("bare", text.lower())
        for phase in (
            "Phase 0",
            "Phase 1",
            "Phase 2",
            "Phase 3",
            "Phase 4",
            "Phase 5",
        ):
            self.assertIn(phase, text, phase)
        # Target syntax needles.
        self.assertIn("templates: atlas-compute-provision/templates", text)
        self.assertIn("hard-reject", text.lower())

    def test_breaking_checklist_phase0_contract_done(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Breaking changes checklist", text)
        self.assertIn(
            "[x] Target YAML + semantics table locked (Phase 0)",
            text,
        )
        self.assertIn(
            "[x] Bare-ref + hard-reject `phase_aliases:` + no dual-read decided (Phase 0)",
            text,
        )
        self.assertIn(
            "[x] Contract matrix tests exist (Phase 0)",
            text,
        )

    def test_adr_index_and_docs_index(self) -> None:
        adr_index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("007-phases-inline-aliases.md", adr_index)
        self.assertIn("Accepted (Phase", adr_index)
        docs_index = DOCS_INDEX.read_text(encoding="utf-8")
        self.assertIn("007", docs_index)
        self.assertIn("inline phase aliases", docs_index.lower())

    def test_schema_doc_phase0_callout(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("hard-rejected", text.lower())
        # Phase 0 callout language may evolve; keep stable needles.
        self.assertIn("templates: atlas-compute-provision/templates", text)

    def test_adr_005_sot_row_notes_supersede(self) -> None:
        text = ADR_005.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("inline in `phases:`", text)

    def test_changelog_mentions_adr007_phase0(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("Phase 0", text)
        self.assertIn("phase_aliases", text)
        self.assertIn("no YAML deletion", text)

    def test_contract_matrix_tests_exist(self) -> None:
        self.assertTrue(CONTRACT_TESTS.is_file(), CONTRACT_TESTS)
        text = CONTRACT_TESTS.read_text(encoding="utf-8")
        for needle in (
            "test_inline_single_key_map_registers_alias",
            "test_bare_repo_entry_allowed_without_alias",
            "test_top_level_phase_aliases_hard_rejected",
            "test_duplicate_alias_errors",
            "test_duplicate_ref_errors_at_parse",
            "test_duplicate_bare_ref_errors_at_parse",
            "test_alias_with_slash_errors",
            "test_multi_key_map_errors",
            "test_dump_rejects_duplicate_refs",
            "test_dump_rejects_drifted_alias_target",
            "test_dump_rejects_two_aliases_for_one_ref",
        ):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
