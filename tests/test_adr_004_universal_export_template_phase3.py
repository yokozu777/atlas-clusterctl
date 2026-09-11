"""Phase 3 gate: ADR 004 — docs/inventory SoT is export_template only."""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.lab_support import lab_path_for

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "004-universal-export-template.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
LOCAL_LABS = ROOT / "docs" / "local-labs.md"
TEMPLATE_README = ROOT / "clusters" / "_template" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"

_SOT_DOCS = (
    LOCAL_LABS,
    TEMPLATE_README,
    ROOT / "clusters" / "_template" / "k8s_full" / "README.md",
    ROOT / "clusters" / "_template" / "redis" / "README.md",
    ROOT / "clusters" / "_template" / "kafka" / "README.md",
    ROOT / "clusters" / "_template" / "postgresql" / "README.md",
    ROOT / "clusters" / "_template" / "infra_edge" / "README.md",
    ROOT / "clusters" / "_template" / "jenkins_agent" / "README.md",
    ROOT / "docs" / "stacks" / "k8s-core.md",
    ROOT / "docs" / "stacks" / "k8s-addons.md",
    ROOT / "docs" / "stacks" / "compute-provision.md",
)

_TEMPLATE_NAMES = (
    "k8s_full",
    "redis",
    "kafka",
    "postgresql",
    "infra_edge",
    "jenkins_agent",
)

_RETIRED = "export_k8s_full_template"


class Adr004UniversalExportTemplatePhase3Test(unittest.TestCase):
    def test_adr_docs_checklist_complete(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 3", text)
        self.assertIn("Status:** Accepted", text)
        self.assertIn("[x] Docs/local-labs + inventory READMEs updated", text)

    def test_adr_index_lists_004(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("004-universal-export-template.md", text)
        self.assertIn("Universal `export_template`", text)

    def test_sot_docs_recommend_export_template_only(self) -> None:
        for path in _SOT_DOCS:
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "export_template",
                text,
                f"{path.relative_to(ROOT)} must mention export_template",
            )
            self.assertNotIn(
                _RETIRED,
                text,
                f"{path.relative_to(ROOT)} must not recommend retired module",
            )

    def test_template_readmes_have_regenerate_commands(self) -> None:
        for name in _TEMPLATE_NAMES:
            path = ROOT / "clusters" / "_template" / name / "README.md"
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                f"export_template --from <lab-id> --template {name}",
                text,
                name,
            )

    def test_local_labs_is_phase3_sot(self) -> None:
        text = LOCAL_LABS.read_text(encoding="utf-8")
        self.assertIn("export_template --from <lab-id> --template redis", text)
        self.assertIn("export_template --from <lab-id> --template k8s_full", text)
        self.assertNotIn(_RETIRED, text)

    def test_inventory_k8s_readme_uses_universal_export_when_present(self) -> None:
        leaf = lab_path_for("k8s")
        if leaf is None:
            self.skipTest("no discovered k8s lab")
        readme = leaf / "README.md"
        if not readme.is_file():
            self.skipTest(f"inventory lab README absent: {readme}")
        text = readme.read_text(encoding="utf-8")
        self.assertIn("export_template", text)
        self.assertNotIn(_RETIRED, text)

    def test_changelog_mentions_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 004", text)
        self.assertIn("Phase 3", text)
        self.assertIn("export_template", text)


if __name__ == "__main__":
    unittest.main()
