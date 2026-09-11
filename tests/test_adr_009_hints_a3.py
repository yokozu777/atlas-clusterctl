"""Post–ADR 009 cleanup A3: runtime hints teach ``run --phases``, not ``play``/``stage``."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLUSTERCTL = ROOT / "clusterctl"
REPO_CONVENTIONS = CLUSTERCTL / "repo_conventions.py"
CHANGELOG = ROOT / "CHANGELOG.md"
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"

_TEACH_PLAY_OR_STAGE = re.compile(r"\./cluster (?:play|stage)\b")


class Adr009HintsA3Test(unittest.TestCase):
    def test_repo_conventions_hints_use_run(self) -> None:
        text = REPO_CONVENTIONS.read_text(encoding="utf-8")
        self.assertNotRegex(text, _TEACH_PLAY_OR_STAGE)
        self.assertIn("./cluster run --dry-run", text)
        self.assertIn("./cluster run --phases", text)
        self.assertNotIn("stage templates", text)
        self.assertNotIn("play infra", text)

    def test_clusterctl_py_no_teach_play_or_stage(self) -> None:
        hits: list[str] = []
        for path in sorted(CLUSTERCTL.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if line.lstrip().startswith("#"):
                    continue
                if _TEACH_PLAY_OR_STAGE.search(line):
                    hits.append(f"{rel}:{lineno}:{line.strip()}")
        self.assertEqual(
            hits,
            [],
            "clusterctl/*.py still teaches ./cluster play|stage:\n"
            + "\n".join(hits),
        )

    def test_main_has_no_alias_implementation(self) -> None:
        text = (CLUSTERCTL / "__main__.py").read_text(encoding="utf-8")
        self.assertNotRegex(text, _TEACH_PLAY_OR_STAGE)
        self.assertNotIn("_warn_deprecated_execute_alias", text)
        self.assertIn("def _cmd_run_execute", text)

    def test_changelog_and_adr_a3(self) -> None:
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("post-cleanup A3", changelog)
        self.assertIn("repo_conventions", changelog)
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("post-cleanup A3", adr)


if __name__ == "__main__":
    unittest.main()
