"""Phase 4 gate: ADR 007 — docs polish + fixture hygiene."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "007-phases-inline-aliases.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
VALIDATE_DOC = ROOT / "docs" / "validate.md"

# Intentional remaining ``"phase_aliases":`` YAML/dict literals (negative tests / gates).
_FIXTURE_PHASE_ALIASES_KEY_ALLOWLIST = frozenset(
    {
        "test_phases_inline_aliases_contract.py",
        "test_phase_aliases_g2.py",
        "test_adr_007_phases_inline_aliases_phase0.py",
        "test_adr_007_phases_inline_aliases_phase1.py",
        "test_adr_007_phases_inline_aliases_phase2.py",
        "test_adr_007_phases_inline_aliases_phase3.py",
        "test_adr_007_phases_inline_aliases_phase4.py",
        "test_adr_007_phases_inline_aliases_phase5.py",
    }
)

_YAML_KEY = re.compile(r"""["']phase_aliases["']\s*:""")


class Adr007PhasesInlineAliasesPhase4Test(unittest.TestCase):
    def test_adr_status_phase4(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn("[x] Docs examples use inline form only (Phase 4)", text)
        self.assertIn("fixture hygiene", text.lower())

    def test_adr_index_phase4(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase4(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("Phase 4", text)
        self.assertIn("fixture hygiene", text.lower())

    def test_schema_doc_phase4(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("operator docs use the inline form only", text.lower())
        self.assertIn("Public `_template/**`", text)
        self.assertIn("atlas-inventory", text)
        aliases_section = text.split("## Phase aliases", 1)[1].split("## `execution`", 1)[0]
        self.assertIn("- provision: atlas-compute-provision/provision", aliases_section)
        self.assertNotIn("\nphase_aliases:\n", aliases_section)

    def test_docs_index_mentions_inline_aliases(self) -> None:
        text = DOCS_INDEX.read_text(encoding="utf-8")
        self.assertIn("inline aliases", text.lower())
        self.assertIn("ADR 007", text)

    def test_validate_doc_no_legacy_sot_row(self) -> None:
        text = VALIDATE_DOC.read_text(encoding="utf-8")
        self.assertIn("phase_aliases_removed", text)
        self.assertIn("Inline phase alias", text)
        self.assertNotIn("ERROR (legacy)", text)

    def test_operator_docs_have_no_recommended_phase_aliases_block(self) -> None:
        """Outside ADR history, operator docs must not teach top-level phase_aliases:."""
        offenders: list[str] = []
        for path in sorted((ROOT / "docs").rglob("*.md")):
            if "docs/adr" in path.as_posix():
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"(?m)^phase_aliases:\s*$", text):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], offenders)

    def test_no_redundant_phase_aliases_yaml_key_in_fixtures(self) -> None:
        offenders: list[str] = []
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            if path.name in _FIXTURE_PHASE_ALIASES_KEY_ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8")
            if _YAML_KEY.search(text):
                offenders.append(path.name)
        self.assertEqual(
            offenders,
            [],
            "omit YAML phase_aliases: key in fixtures "
            f"(or add to Phase 4 allowlist): {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
