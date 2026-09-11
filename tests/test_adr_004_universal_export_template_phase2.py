"""Phase 2 gate: ADR 004 — multi-stack export_template tests are the SoT."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "004-universal-export-template.md"
EXPORT_TESTS = ROOT / "tests" / "test_export_template.py"
RETIRED_LEGACY_TESTS = ROOT / "tests" / "test_export_k8s_full_template.py"
ADR003_PHASE2 = ROOT / "tests" / "test_adr_003_optional_cluster_yml_phase2.py"

_STACK_NEEDLES = (
    "fixture/redis",
    "fixture/kafka",
    "fixture/postgresql",
    "fixture/infra",
    "fixture/jenkins",
    "fixture/k8s",
    "redis",
    "kafka",
    "postgresql",
    "infra_edge",
    "jenkins_agent",
    "k8s_full",
)


class Adr004UniversalExportTemplatePhase2Test(unittest.TestCase):
    def test_adr_status_phase2(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 2", text)
        self.assertIn("test_export_template.py", text)
        self.assertIn("multi-stack", text.lower())

    def test_export_template_tests_cover_known_stacks(self) -> None:
        self.assertTrue(EXPORT_TESTS.is_file(), EXPORT_TESTS)
        text = EXPORT_TESTS.read_text(encoding="utf-8")
        for needle in _STACK_NEEDLES:
            self.assertIn(needle, text, needle)
        self.assertIn("literal_domain", text)
        self.assertIn("does_not_copy_or_rewrite_readme", text)
        self.assertIn("cli_requires_from_and_template", text)
        self.assertIn("defaults_use_inventory_and_product", text)
        self.assertNotIn("export_k8s_full_template", text)
        self.assertNotIn("shim_delegates_to_universal", text)

    def test_retired_legacy_tests_absent(self) -> None:
        self.assertFalse(RETIRED_LEGACY_TESTS.exists(), RETIRED_LEGACY_TESTS)

    def test_adr003_phase2_uses_universal_export(self) -> None:
        text = ADR003_PHASE2.read_text(encoding="utf-8")
        self.assertIn("from clusterctl.tools.export_template import export_template", text)
        self.assertNotIn(
            "from clusterctl.tools.export_k8s_full_template import",
            text,
        )


if __name__ == "__main__":
    unittest.main()
