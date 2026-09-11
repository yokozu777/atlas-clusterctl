"""Phase 0 gate: ADR 009 — unify run / stage / play (contract only)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_008 = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
CHANGELOG = ROOT / "CHANGELOG.md"
POLICY_MOD = ROOT / "clusterctl" / "run_overrides.py"
CONTRACT_TESTS = ROOT / "tests" / "test_run_overrides_contract.py"


class Adr009UnifyRunStagePlayPhase0Test(unittest.TestCase):
    def test_adr_exists_and_accepted_phase0(self) -> None:
        self.assertTrue(ADR.is_file(), ADR)
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Out of scope", text)
        self.assertIn("merge_e", text)
        self.assertIn("collapse", text)
        self.assertIn("EXTRA_VARS", text)
        self.assertIn("provision_mode=destroy", text)
        self.assertIn("Phase 0–4 deliverables", text)
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
        self.assertIn(
            "[x] Target CLI + override policy table locked (Phase 0)",
            text,
        )
        self.assertIn(
            "[x] `merge_e` vs `collapse` vs multi-phase selective ERROR decided (Phase 0)",
            text,
        )
        self.assertIn(
            "[x] Legacy `stage` / `play` mapping + Jenkins `EXTRA_VARS` shape decided (Phase 0)",
            text,
        )
        self.assertIn("[x] Contract matrix tests exist (Phase 0)", text)
        self.assertIn("[x] **No argparse wiring** yet (Phase 0)", text)

    def test_adr_index_and_docs_index(self) -> None:
        adr_index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("009-unify-run-stage-play.md", adr_index)
        self.assertIn("Accepted (Phase", adr_index)
        docs_index = DOCS_INDEX.read_text(encoding="utf-8")
        self.assertIn("009", docs_index)
        self.assertIn("unify", docs_index.lower())

    def test_clusterctl_doc_phase0_callout(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("009-unify-run-stage-play.md", text)
        self.assertIn("merge_e", text)

    def test_adr_008_points_forward(self) -> None:
        text = ADR_008.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("unify", text.lower())

    def test_changelog_mentions_adr009_phase0(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("Phase 0", text)
        self.assertIn("no argparse wiring", text.lower())

    def test_policy_module_exists(self) -> None:
        self.assertTrue(POLICY_MOD.is_file(), POLICY_MOD)
        text = POLICY_MOD.read_text(encoding="utf-8")
        self.assertIn("def classify_run_overrides", text)
        self.assertIn("RunOverrideMode", text)
        self.assertIn("MERGE_EXTRA", text)
        self.assertIn("ERROR_MULTI_PHASE_SELECTIVE", text)

    def test_contract_matrix_tests_exist(self) -> None:
        self.assertTrue(CONTRACT_TESTS.is_file(), CONTRACT_TESTS)
        text = CONTRACT_TESTS.read_text(encoding="utf-8")
        for needle in (
            "test_catalog_no_overrides",
            "test_merge_e_single_and_multi_phase",
            "test_collapse_tags_or_limit_or_root_ssh_single_phase",
            "test_error_multi_phase_selective",
            "test_git_ssh_not_in_classifier",
            "test_blank_extra_vars_ignored",
            "test_phase_count_zero_raises",
        ):
            self.assertIn(needle, text, needle)

    def test_main_not_wired_in_phase0_text(self) -> None:
        """Phase 0 checklist remains historical; wiring is Phase 1 (see phase1 gate)."""
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("[x] **No argparse wiring** yet (Phase 0)", text)
        self.assertIn("[x] `run` override flags + policy wiring (Phase 1)", text)


if __name__ == "__main__":
    unittest.main()
