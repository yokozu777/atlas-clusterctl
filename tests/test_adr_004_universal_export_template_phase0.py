"""Phase 0 gate: ADR 004 — universal export_template contract (historical)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "004-universal-export-template.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
LOCAL_LABS = ROOT / "docs" / "local-labs.md"
TEMPLATE_README = ROOT / "clusters" / "_template" / "README.md"

# Public named scaffolds (empty parent _template/ is out of scope for export).
KNOWN_TEMPLATES = (
    "k8s_full",
    "infra_edge",
    "jenkins_agent",
    "postgresql",
    "redis",
    "kafka",
)


class Adr004UniversalExportTemplatePhase0Test(unittest.TestCase):
    def test_adr_exists_and_accepted(self) -> None:
        self.assertTrue(ADR.is_file(), ADR)
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted", text)
        self.assertIn("export_template", text)
        self.assertIn("--from", text)
        self.assertIn("--template", text)
        self.assertIn("maintainer-only", text.lower().replace("`", "").replace("**", ""))
        self.assertIn("./cluster init", text)
        # Roadmap bound
        for phase in ("Phase 1", "Phase 2", "Phase 3", "Phase 4"):
            self.assertIn(phase, text, phase)
        self.assertIn("k8s_full", text)

    def test_known_templates_listed(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        for name in KNOWN_TEMPLATES:
            self.assertIn(f"`{name}`", text, name)
            scaffold = ROOT / "clusters" / "_template" / name / "cluster.yaml"
            self.assertTrue(scaffold.is_file(), scaffold)

    def test_breaking_changes_checklist_present(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Breaking changes checklist", text)
        self.assertIn("export_template --from", text)

    def test_adr_index_lists_004(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("004-universal-export-template.md", text)
        self.assertIn("Universal `export_template`", text)

    def test_local_labs_links_contract(self) -> None:
        text = LOCAL_LABS.read_text(encoding="utf-8")
        self.assertIn("adr/004-universal-export-template.md", text)
        self.assertIn("export_template", text)
        for name in KNOWN_TEMPLATES:
            self.assertIn(name, text, name)

    def test_template_readme_points_at_adr(self) -> None:
        text = TEMPLATE_README.read_text(encoding="utf-8")
        self.assertIn("004-universal-export-template.md", text)
        self.assertIn("export_template", text)


if __name__ == "__main__":
    unittest.main()
