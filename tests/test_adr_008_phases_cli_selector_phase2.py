"""Phase 2 gate: ADR 008 — docs happy-path on ``--phases``; from/to deprecated."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
MAIN = ROOT / "clusterctl" / "__main__.py"


class Adr008PhasesCliSelectorPhase2Test(unittest.TestCase):
    def test_adr_status_phase2(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn("[x] Docs happy-path (Phase 2)", text)
        self.assertIn("deprecated", text.lower())

    def test_adr_index_phase2(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008", text)
        self.assertIn("Phase 2", text)
        self.assertIn("deprecated", text.lower())

    def test_clusterctl_doc_happy_path(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 008", text)
        self.assertIn("--phases provision..k8s-addons", text)
        # No live plan/run legacy examples in the command sections.
        plan_section = text.split("### `plan`", 1)[1].split("### `run`", 1)[0]
        run_section = text.split("### `run`", 1)[1].split("### `stages`", 1)[0]
        self.assertNotIn("--from", plan_section)
        self.assertNotIn("--to", plan_section)
        for block in re.findall(r"```bash\n(.*?)```", run_section, flags=re.S):
            self.assertNotIn("--from", block)
            self.assertNotIn("--to", block)

    def test_argparse_help_phases_primary(self) -> None:
        text = MAIN.read_text(encoding="utf-8")
        self.assertIn('"--phases"', text)
        self.assertIn("phases_selector", text)
        # Phase 4 removes plan/run --from/--to; Phase 2 only required --phases SoT.
        self.assertNotIn('dest="from_stage"', text)
        self.assertNotIn('dest="to_stage"', text)

    def test_stacks_use_phases_selector(self) -> None:
        stacks = ROOT / "docs" / "stacks"
        hits = 0
        for path in sorted(stacks.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if "--phases" in text:
                hits += 1
        self.assertGreaterEqual(hits, 5, "expected stack runbooks to show --phases")


if __name__ == "__main__":
    unittest.main()
