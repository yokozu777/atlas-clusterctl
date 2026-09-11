"""Post–ADR 009 cleanup B (+ audit / alias-removal Phase 3): helper + notes."""

from __future__ import annotations

import inspect
import re
import unittest
from pathlib import Path

from clusterctl.phase_plan import apply_play_cli_overrides

ROOT = Path(__file__).resolve().parents[1]
PHASE_PLAN = ROOT / "clusterctl" / "phase_plan.py"
REPORT = ROOT / "notes" / "report_clusterctl.md"
NOTES_README = ROOT / "notes" / "README.md"
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
CHANGELOG = ROOT / "CHANGELOG.md"

_STAGE_SECTION = re.compile(
    r"### 4\.9\. `stage`\n(?P<body>.*?)(?=\n### 4\.10\.|\Z)",
    re.DOTALL,
)
_PLAY_SECTION = re.compile(
    r"### 4\.10\. `play`\n(?P<body>.*?)(?=\n### 4\.11\.|\Z)",
    re.DOTALL,
)


class Adr009NotesHelperBTest(unittest.TestCase):
    def test_apply_play_cli_overrides_docstring(self) -> None:
        doc = inspect.getdoc(apply_play_cli_overrides) or ""
        self.assertIn("DO NOT use from CLI", doc)
        self.assertIn("apply_run_cli_overrides", doc)
        self.assertIn("merge_e", doc)
        self.assertIn("test_play_cli_phase2", doc)
        # Source still defines the historical helper (not deleted).
        text = PHASE_PLAN.read_text(encoding="utf-8")
        self.assertIn("def apply_play_cli_overrides", text)
        self.assertIn("DO NOT use from CLI", text)

    def test_report_teaches_run_primary(self) -> None:
        text = REPORT.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("apply_run_cli_overrides", text)
        self.assertIn("merge_e", text)
        self.assertIn("`run`", text)
        self.assertIn("**Removed** (ADR 009", text)
        self.assertIn("./cluster run --phases", text)
        # Stale primary teaching removed.
        self.assertNotIn("apply_play_cli_overrides` → `stage.git_ssh`", text)
        self.assertNotIn(
            "Если заданы `--tags`≠`all` / `--limit` / `-e` / `--root-ssh`",
            text,
        )
        # Default k8s_full plan example starts at provision (A2 alignment).
        self.assertIn("- provision: atlas-compute-provision/provision", text)
        self.assertNotIn(
            "- templates: atlas-compute-provision/templates",
            text,
        )
        # Cheatsheet: no live or commented stage/play teach (alias-removal Phase 3).
        self.assertNotIn("# ./cluster stage provision", text)
        self.assertNotIn("# ./cluster play k8s-addons", text)
        self.assertNotIn(
            "\n./cluster stage provision\n",
            text,
        )

    def test_report_stage_play_sections_are_short_cards(self) -> None:
        """§4.9 / §4.10 Removed cards point at SoT; no duplicate flag tables."""
        text = REPORT.read_text(encoding="utf-8")
        stage = _STAGE_SECTION.search(text)
        play = _PLAY_SECTION.search(text)
        self.assertIsNotNone(stage, "§4.9 stage missing")
        self.assertIsNotNone(play, "§4.10 play missing")
        assert stage is not None and play is not None
        stage_body = stage.group("body")
        play_body = play.group("body")

        for label, body in (("stage", stage_body), ("play", play_body)):
            body = body.strip().removesuffix("---").strip()
            self.assertIn("**Removed** (ADR 009 alias-removal)", body, label)
            self.assertIn("./cluster run --phases", body, label)
            self.assertIn("docs/clusterctl.md", body, label)
            self.assertIn("009-unify-run-stage-play.md", body, label)
            self.assertNotIn("**Deprecated**", body, label)
            # No argparse usage fences / option tables (those live in §4.7 / docs).
            self.assertNotIn("```text", body, label)
            self.assertNotIn("| Аргумент", body, label)
            self.assertNotIn("| Опция", body, label)
            self.assertLessEqual(
                len([ln for ln in body.splitlines() if ln.strip()]),
                12,
                f"{label} section too long ({len(body.splitlines())} lines):\n{body}",
            )

        stage_body = stage.group("body")
        play_body = play.group("body")
        self.assertIn("_cmd_run_execute", stage_body)
        self.assertIn("apply_run_cli_overrides", stage_body)
        self.assertIn("merge_e", play_body)
        self.assertIn("resolve_play_phase_target", play_body)
        self.assertIn("tests only", play_body)
        self.assertIn("apply_play_cli_overrides", play_body)

    def test_notes_readme_points_at_adr009(self) -> None:
        text = NOTES_README.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)

    def test_limit_env_run_verb(self) -> None:
        text = REPORT.read_text(encoding="utf-8")
        self.assertIn("resolve_run_limit", text)
        self.assertRegex(text, r"`LIMIT`.*для `run`")
        self.assertNotRegex(text, r"`LIMIT`.*`stage`.*`play`")

    def test_changelog_and_adr_b(self) -> None:
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("post-cleanup B", changelog)
        self.assertIn("test_adr_009_notes_helper_b.py", changelog)
        self.assertIn("audit Phase 3", changelog)
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("post-cleanup B", adr)
        self.assertIn("test_adr_009_notes_helper_b.py", adr)
        self.assertRegex(adr, r"[Aa]udit Phase 3")


if __name__ == "__main__":
    unittest.main()
