"""ADR 009 alias-removal Phase 2: gates no longer require aliases retained."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
CHANGELOG = ROOT / "CHANGELOG.md"
MAIN = ROOT / "clusterctl" / "__main__.py"

# Files that may mention stage/play only to assert removal / rejection,
# or that lock historical product Phase 2 checklist wording.
_ALLOWLIST = frozenset(
    {
        "test_adr_009_alias_removal_phase0.py",
        "test_adr_009_alias_removal_phase1.py",
        "test_adr_009_alias_removal_phase2.py",
        # Historical product Phase 2 checklist row name (aliases were added then).
        "test_adr_009_unify_run_stage_play_phase2.py",
        "test_adr_009_alias_removal_phase3.py",
    }
)

_ASSERT_IN_WARN = re.compile(
    r'assertIn\(\s*[\'"]_warn_deprecated_execute_alias[\'"]'
)
_ASSERT_IN_CMD_STAGE = re.compile(
    r'assertIn\(\s*[\'"]command="stage"[\'"]'
)
_ASSERT_IN_CMD_PLAY = re.compile(
    r'assertIn\(\s*[\'"]command="play"[\'"]'
)


class Adr009AliasRemovalPhase2Test(unittest.TestCase):
    def test_no_gate_requires_alias_wiring(self) -> None:
        hits: list[str] = []
        for path in sorted(TESTS.glob("test_adr_009*.py")):
            if path.name in _ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if _ASSERT_IN_WARN.search(line) or _ASSERT_IN_CMD_STAGE.search(line) or _ASSERT_IN_CMD_PLAY.search(line):
                    hits.append(f"{path.name}:{lineno}:{stripped}")
                for needle in (
                    "deprecated aliases retained",
                    "aliases still in tree",
                ):
                    # Only fail when asserting presence (assertIn), not assertNotIn.
                    if needle in line and "assertIn" in line and "assertNotIn" not in line:
                        hits.append(f"{path.name}:{lineno}:{stripped}")
        self.assertEqual(
            hits,
            [],
            "ADR 009 gates still require aliases retained:\n" + "\n".join(hits),
        )

    def test_main_and_subcommands_removed(self) -> None:
        from clusterctl.cli_args import SUBCOMMANDS

        self.assertNotIn("stage", SUBCOMMANDS)
        self.assertNotIn("play", SUBCOMMANDS)
        self.assertIn("stages", SUBCOMMANDS)
        main = MAIN.read_text(encoding="utf-8")
        self.assertNotIn("_warn_deprecated_execute_alias", main)
        self.assertNotIn('command="stage"', main)
        self.assertNotIn('command="play"', main)

    def test_adr_phase2_checklist_and_runtime(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("[x] Gates no longer require aliases retained (Phase 2)", text)
        self.assertIn("test_adr_009_alias_removal_phase2.py", text)
        self.assertIn("alias removal phase 2", text.lower())
        # Current runtime must not claim aliases retained.
        runtime = text.split("## Current runtime", 1)[1].split("## Target end state", 1)[0]
        self.assertNotIn("deprecated aliases retained", runtime.lower())
        self.assertIn("**removed**", runtime.lower())
        # Product Phase 5 plan row notes follow-up removal.
        self.assertIn("alias-removal", text.lower())

    def test_changelog_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("alias removal Phase 2", text)
        self.assertIn("test_adr_009_alias_removal_phase2.py", text)


if __name__ == "__main__":
    unittest.main()
