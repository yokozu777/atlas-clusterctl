"""Phase 1 gate: ADR 004 — universal export_template shipped."""

from __future__ import annotations

import unittest
from pathlib import Path

from clusterctl.tools.export_template import KNOWN_TEMPLATE_NAMES

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "004-universal-export-template.md"
UNIVERSAL = ROOT / "clusterctl" / "tools" / "export_template.py"
RETIRED_SHIM = ROOT / "clusterctl" / "tools" / "export_k8s_full_template.py"


class Adr004UniversalExportTemplatePhase1Test(unittest.TestCase):
    def test_adr_status_phase1(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 1", text)
        self.assertIn("[x] `python3 -m clusterctl.tools.export_template", text)

    def test_universal_module_exists(self) -> None:
        self.assertTrue(UNIVERSAL.is_file(), UNIVERSAL)
        text = UNIVERSAL.read_text(encoding="utf-8")
        self.assertIn("def export_template", text)
        self.assertIn("--from", text)
        self.assertIn("--template", text)
        for name in KNOWN_TEMPLATE_NAMES:
            self.assertIn(name, text, name)

    def test_retired_shim_absent(self) -> None:
        """Phase 4 deleted the Phase 1 shim; Phase 1 gate stays green."""
        self.assertFalse(RETIRED_SHIM.exists(), RETIRED_SHIM)


if __name__ == "__main__":
    unittest.main()
