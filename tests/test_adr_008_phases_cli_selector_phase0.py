"""Phase 0 gate: ADR 008 — ``--phases`` CLI selector (contract only)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CONTRACT_TESTS = ROOT / "tests" / "test_phases_selector_contract.py"
SELECTOR_MOD = ROOT / "clusterctl" / "phase_selector.py"


class Adr008PhasesCliSelectorPhase0Test(unittest.TestCase):
    def test_adr_exists_and_accepted_phase0(self) -> None:
        self.assertTrue(ADR.is_file(), ADR)
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Out of scope", text)
        self.assertIn("provision..k8s-addons", text)
        self.assertIn("comma", text.lower())
        for phase in (
            "Phase 0",
            "Phase 1",
            "Phase 2",
            "Phase 3",
            "Phase 4",
            "Phase 5",
        ):
            self.assertIn(phase, text, phase)

    def test_breaking_checklist_phase0_contract_done(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Breaking changes checklist", text)
        self.assertIn("[x] Target selector grammar locked (Phase 0)", text)
        self.assertIn(
            "[x] Single + `start..end` decided; CSV deferred with hard ERROR **at Phase 0** (lifted in Phase 3)",
            text,
        )
        self.assertIn("[x] Contract matrix tests exist (Phase 0)", text)
        self.assertIn("[x] **No argparse wiring** yet (Phase 0)", text)

    def test_adr_index_and_docs_index(self) -> None:
        adr_index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("008-phases-cli-selector.md", adr_index)
        self.assertIn("Accepted (Phase", adr_index)
        docs_index = DOCS_INDEX.read_text(encoding="utf-8")
        self.assertIn("008", docs_index)
        self.assertIn("--phases", docs_index)

    def test_clusterctl_doc_phase0_callout(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 008", text)
        self.assertIn("--phases", text)
        self.assertIn("provision..k8s-addons", text)

    def test_changelog_mentions_adr008_phase0(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008", text)
        self.assertIn("Phase 0", text)

    def test_selector_module_exists(self) -> None:
        self.assertTrue(SELECTOR_MOD.is_file(), SELECTOR_MOD)
        text = SELECTOR_MOD.read_text(encoding="utf-8")
        self.assertIn("def parse_phases_selector", text)
        self.assertIn("PhaseRangeSelector", text)

    def test_contract_matrix_tests_exist(self) -> None:
        self.assertTrue(CONTRACT_TESTS.is_file(), CONTRACT_TESTS)
        text = CONTRACT_TESTS.read_text(encoding="utf-8")
        for needle in (
            "test_single_phase",
            "test_range_aliases",
            "test_range_full_refs",
            "test_range_allows_spaces_around_separator",
            "test_empty_errors",
            "test_bare_separator_errors",
            "test_open_range_errors",
            "test_multiple_separators_error",
            "test_comma_list_accepted",
            "test_mix_range_and_comma_errors",
        ):
            self.assertIn(needle, text, needle)


if __name__ == "__main__":
    unittest.main()
