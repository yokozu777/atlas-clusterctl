"""ADR 009 alias-removal Phase 3: in-repo docs/notes no live teach of aliases."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
REPORT = ROOT / "notes" / "report_clusterctl.md"

_TEACH_PLAY = re.compile(r"(?m)^(?!\s*#).*?\./cluster play\b")
_TEACH_STAGE = re.compile(r"(?m)^(?!\s*#).*?\./cluster stage\b")  # not stages
_COMMENTED_ALIAS = re.compile(
    r"(?m)^\s*#\s*\./cluster (?:stage|play)\b"
)

_STAGE_SECTION = re.compile(
    r"### 4\.9\. `stage`\n(?P<body>.*?)(?=\n### 4\.10\.|\Z)",
    re.DOTALL,
)
_PLAY_SECTION = re.compile(
    r"### 4\.10\. `play`\n(?P<body>.*?)(?=\n### 4\.11\.|\Z)",
    re.DOTALL,
)


class Adr009AliasRemovalPhase3Test(unittest.TestCase):
    def test_notes_stage_play_are_removed_cards(self) -> None:
        text = REPORT.read_text(encoding="utf-8")
        stage = _STAGE_SECTION.search(text)
        play = _PLAY_SECTION.search(text)
        self.assertIsNotNone(stage, "§4.9 stage missing")
        self.assertIsNotNone(play, "§4.10 play missing")
        assert stage is not None and play is not None
        for label, body in (("stage", stage.group("body")), ("play", play.group("body"))):
            body = body.strip().removesuffix("---").strip()
            self.assertIn("**Removed** (ADR 009 alias-removal)", body, label)
            self.assertIn("./cluster run --phases", body, label)
            self.assertIn("docs/clusterctl.md", body, label)
            self.assertIn("009-unify-run-stage-play.md", body, label)
            self.assertNotIn("**Deprecated**", body, label)
            self.assertNotIn("stderr", body.lower(), label)
            self.assertNotIn("```text", body, label)
            self.assertNotIn("| Аргумент", body, label)
            self.assertLessEqual(
                len([ln for ln in body.splitlines() if ln.strip()]),
                12,
                f"{label} section too long:\n{body}",
            )
        self.assertIn("apply_run_cli_overrides", stage.group("body"))
        self.assertIn("_cmd_run_execute", stage.group("body"))
        self.assertIn("merge_e", play.group("body"))
        self.assertIn("apply_play_cli_overrides", play.group("body"))
        self.assertIn("tests only", play.group("body"))

    def test_notes_no_live_or_commented_alias_teach(self) -> None:
        text = REPORT.read_text(encoding="utf-8")
        self.assertEqual(
            _TEACH_PLAY.findall(text),
            [],
            "notes still teach ./cluster play",
        )
        self.assertEqual(
            _TEACH_STAGE.findall(text),
            [],
            "notes still teach ./cluster stage",
        )
        self.assertEqual(
            _COMMENTED_ALIAS.findall(text),
            [],
            "notes cheatsheet still comments ./cluster stage|play",
        )
        self.assertNotIn("deprecated aliases", text.lower())
        self.assertIn("`run`", text)
        self.assertIn("./cluster run --phases", text)
        # Summary / LIMIT / ADR row aligned with removal.
        self.assertIn("| Исполнение | `run` |", text)
        self.assertRegex(text, r"`LIMIT`.*для `run`")
        self.assertNotRegex(text, r"`LIMIT`.*`stage`.*`play`")

    def test_clusterctl_doc_removed_banner(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("### `stage` / `play` (removed)", text)
        self.assertIn("**Removed** (ADR 009 alias-removal Phase 1–5)", text)
        self.assertIn("alias-removal Phase 1–5", text)
        self.assertNotIn("Deprecated** (ADR 009 Phase 2)", text)

    def test_changelog_breaking_and_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("alias removal Phase 3", text)
        self.assertIn("test_adr_009_alias_removal_phase3.py", text)
        self.assertIn("no live teach", text.lower())
        # Polished Breaking migration table.
        breaking = text.split("### Breaking (ADR 009 — alias removal Phase 1)", 1)[1]
        breaking = breaking.split("### ", 1)[0]
        self.assertIn("./cluster stage NAME", breaking)
        self.assertIn("./cluster run --phases NAME", breaking)
        self.assertIn("./cluster play NAME", breaking)
        self.assertIn("invalid choice", breaking.lower())
        self.assertIn("stages", breaking)

    def test_adr_phase3_checklist(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("[x] Docs / notes / Breaking changelog (Phase 3)", text)
        self.assertIn("test_adr_009_alias_removal_phase3.py", text)
        self.assertIn("alias removal phase 3", text.lower())
        self.assertIn("Phase 1–5 done", text)
        runtime = text.split("## Current runtime", 1)[1].split("## Target end state", 1)[0]
        self.assertIn("**Removed**", runtime)
        self.assertIn("no live teach", runtime.lower())
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("alias hard-removal Phase 1–5 done", index)


if __name__ == "__main__":
    unittest.main()
