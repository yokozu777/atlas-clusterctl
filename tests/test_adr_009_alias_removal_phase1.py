"""ADR 009 alias-removal Phase 1: CLI ``stage`` / ``play`` hard-removed."""

from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

import clusterctl.__main__ as main_mod
from clusterctl.cli_args import SUBCOMMANDS

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
CHANGELOG = ROOT / "CHANGELOG.md"
MAIN = ROOT / "clusterctl" / "__main__.py"
CLI_ARGS = ROOT / "clusterctl" / "cli_args.py"


class Adr009AliasRemovalPhase1Test(unittest.TestCase):
    def test_subcommands_drop_stage_play_keep_stages(self) -> None:
        self.assertNotIn("stage", SUBCOMMANDS)
        self.assertNotIn("play", SUBCOMMANDS)
        self.assertIn("stages", SUBCOMMANDS)
        self.assertIn("run", SUBCOMMANDS)

    def test_main_has_no_alias_wiring(self) -> None:
        text = MAIN.read_text(encoding="utf-8")
        self.assertNotIn('command="stage"', text)
        self.assertNotIn('command="play"', text)
        self.assertNotIn("_warn_deprecated_execute_alias", text)
        self.assertNotIn('add_parser(\n        "stage"', text)
        self.assertNotIn('add_parser(\n        "play"', text)
        cli = CLI_ARGS.read_text(encoding="utf-8")
        self.assertNotIn('"stage"', cli)
        self.assertNotIn('"play"', cli)
        self.assertIn('"stages"', cli)

    def test_argparse_rejects_stage_and_play(self) -> None:
        parser = main_mod._build_parser()
        for argv in (
            ["stage", "provision"],
            ["play", "provision", "-e", "a=1"],
        ):
            buf = io.StringIO()
            with self.assertRaises(SystemExit) as cm:
                with contextlib.redirect_stderr(buf):
                    parser.parse_args(argv)
            self.assertEqual(cm.exception.code, 2)

    def test_run_still_parses(self) -> None:
        parser = main_mod._build_parser()
        args = parser.parse_args(
            ["run", "--phases", "provision", "-e", "provision_mode=destroy"]
        )
        self.assertEqual(args.command, "run")
        self.assertEqual(args.phases_selector, "provision")
        self.assertEqual(args.extra_vars, ["provision_mode=destroy"])

    def test_adr_and_changelog_phase1(self) -> None:
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("alias hard-removal Phase 1", adr)
        self.assertIn("[x] Argparse / ``cli_args`` remove (Phase 1)", adr)
        self.assertIn("test_adr_009_alias_removal_phase1.py", adr)
        self.assertIn("**removed**", adr.lower())
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("alias removal Phase 1", changelog)
        self.assertIn("Breaking", changelog)


if __name__ == "__main__":
    unittest.main()
