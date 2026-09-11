"""Phase 4 gate: ADR 006 — docs polish + fixture hygiene."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "006-redundant-playbooks-enabled.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"

# Intentional remaining ``"playbooks_enabled": True`` (and related) fixtures.
_FIXTURE_TRUE_ALLOWLIST = frozenset(
    {
        "test_playbooks_enabled_infer.py",
        "test_phase5_schema_cleanup.py",
        "test_generic_engine_g6.py",
        "test_playbooks_config.py",
        "test_docker_validate.py",
        # Enable-without-catalog / stub leaves (no playbooks: in same file).
        "test_cluster_init.py",
        "test_phase3_leaf_overlay_deprecation.py",
        "test_phase4_context_summary.py",
        "test_phase4_thin_facade.py",
        "test_playbooks_cmd_gates.py",
        "test_playbooks_resolve_errors.py",
        "test_repo_conventions.py",
        "test_repos_cmd.py",
        "test_v1_cutover.py",
        # Sync API kwarg playbooks_enabled=True is not a YAML fixture.
        "test_phase3_sync_unification.py",
        # ADR phase gates may quote the string.
        "test_adr_006_redundant_playbooks_enabled_phase0.py",
        "test_adr_006_redundant_playbooks_enabled_phase1.py",
        "test_adr_006_redundant_playbooks_enabled_phase2.py",
        "test_adr_006_redundant_playbooks_enabled_phase3.py",
        "test_adr_006_redundant_playbooks_enabled_phase4.py",
        "test_adr_006_redundant_playbooks_enabled_phase5.py",
    }
)

_TRUE_LINE = re.compile(
    r"""^[ \t]*["']playbooks_enabled["']\s*:\s*True,?[ \t]*$""",
    re.M,
)


class Adr006RedundantPlaybooksEnabledPhase4Test(unittest.TestCase):
    def test_adr_status_phase4(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn(
            "[x] Docs controller contract + unittest fixture hygiene (Phase 4)",
            text,
        )
        self.assertIn("fixture hygiene", text.lower())

    def test_adr_index_phase4(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase4(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 006", text)
        self.assertIn("Phase 4", text)
        self.assertIn("fixture hygiene", text.lower())

    def test_controller_contract_omits_mandatory_true(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("## Controller contract", text)
        # Primary signal is playbooks:; do not require "or playbooks_enabled: true".
        contract = text.split("## Controller contract", 1)[1].split("## ", 1)[0]
        self.assertIn("when `playbooks:` is present", contract)
        self.assertNotIn("or `playbooks_enabled: true`", contract)
        self.assertIn("ADR 006", contract)

    def test_no_redundant_true_in_fixtures_with_playbooks(self) -> None:
        """Fixtures that already define playbooks: must not also set True."""
        offenders: list[str] = []
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            if path.name in _FIXTURE_TRUE_ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8")
            if '"playbooks"' not in text and "'playbooks'" not in text:
                continue
            if _TRUE_LINE.search(text):
                offenders.append(path.name)
        self.assertEqual(
            offenders,
            [],
            "omit redundant playbooks_enabled: True when fixture has playbooks: "
            f"(or add to Phase 4 allowlist): {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
