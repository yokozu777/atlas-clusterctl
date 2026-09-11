"""Phase 4 gate: ADR 009 — operator docs teach ``run`` as canonical execute."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
DOCS_README = ROOT / "docs" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
STACKS_DIR = ROOT / "docs" / "stacks"
TEMPLATE_INFRA_README = ROOT / "clusters" / "_template" / "infra_edge" / "README.md"

# Operator-facing docs that must not teach ``./cluster play`` / ``./cluster stage``
# as primary examples. ADR mapping table and ``./cluster stages`` list helper are OK.
OPERATOR_DOC_PATHS = (
    CLUSTERCTL_DOC,
    DOCS_README,
    ROOT / "docs" / "clusters.md",
    ROOT / "docs" / "cluster-config-v2.md",
    ROOT / "docs" / "local-labs.md",
    ROOT / "docs" / "ansible.md",
    TEMPLATE_INFRA_README,
    *sorted(STACKS_DIR.glob("*.md")),
)

_TEACH_PLAY = re.compile(r"\./cluster play\b")
_TEACH_STAGE = re.compile(r"\./cluster stage\b")  # not ``stages``


class Adr009UnifyRunStagePlayPhase4Test(unittest.TestCase):
    def test_adr_status_phase4(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("[x] Operator docs canonical `run` (Phase 4)", text)
        self.assertIn("**done**", text.split("**Phase 4**", 1)[1].split("\n", 1)[0])
        self.assertTrue(
            "[x] Offline `./tests/run_ci.sh` green (Phase 5)" in text
            or "[ ] Offline `./tests/run_ci.sh` green (Phase 5)" in text,
            "Phase 5 checklist row missing",
        )
        self.assertNotIn(
            "Temporary dual docs (`stage`/`play` still in examples until Phase 4)",
            text,
        )

    def test_adr_index_phase4(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("009-unify-run-stage-play.md", text)
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase4(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 009 — Phase 4", text)
        self.assertIn("canonical", text.lower())
        self.assertIn("test_adr_009_unify_run_stage_play_phase4.py", text)

    def test_clusterctl_banner_and_quick_start_teach_run(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("./cluster run --phases", text)
        qs = text.split("## Quick start", 1)[1].split("## Global flags", 1)[0]
        self.assertIn("./cluster run --phases", qs)
        self.assertNotRegex(qs, _TEACH_PLAY)
        self.assertNotRegex(qs, _TEACH_STAGE)
        self.assertIn("### `stage` / `play` (removed)", text)
        self.assertIn("**Removed** (ADR 009 alias-removal Phase 1–5)", text)

    def test_operator_docs_do_not_teach_play_or_stage(self) -> None:
        for path in OPERATOR_DOC_PATHS:
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            play_hits = _TEACH_PLAY.findall(text)
            stage_hits = _TEACH_STAGE.findall(text)
            self.assertEqual(
                play_hits,
                [],
                f"{path.relative_to(ROOT)} still teaches ./cluster play: {play_hits}",
            )
            self.assertEqual(
                stage_hits,
                [],
                f"{path.relative_to(ROOT)} still teaches ./cluster stage: {stage_hits}",
            )

    def test_docs_readme_scaffold_examples_use_run(self) -> None:
        text = DOCS_README.read_text(encoding="utf-8")
        self.assertIn("./cluster run --phases", text)
        self.assertNotRegex(text, _TEACH_PLAY)
        self.assertNotRegex(text, _TEACH_STAGE)


if __name__ == "__main__":
    unittest.main()
