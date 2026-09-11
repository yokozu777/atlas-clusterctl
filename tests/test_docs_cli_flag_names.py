"""Regression: operator docs/samples teach real CLI flag names (Phase 1)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Operator surfaces (not ADR history / CHANGELOG / report scratchpads).
OPERATOR_DOC_GLOBS: tuple[str, ...] = (
    "docs/*.md",
    "docs/stacks/*.md",
    "README.md",
    "clusters/_template/*/README.md",
)

# Wrong short alias for validate --skip-docker-smoke.
_SKIP_DOCKER_SHORT = re.compile(r"--skip-docker(?!-smoke)\b")
# Wrong name for play --root-ssh.
_SSH_ROOT = re.compile(r"--ssh-root\b")
# plan has no --list (list is a top-level subcommand).
_PLAN_LIST = re.compile(r"(?:^|[^\w./])(?:\./)?cluster\b[^\n]*\bplan\b[^\n]*--list\b")


def _scan(globs: tuple[str, ...], pattern: re.Pattern[str]) -> list[str]:
    offenders: list[str] = []
    for glob in globs:
        for path in sorted(ROOT.glob(glob)):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if "/adr/" in rel:
                continue
            text = path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                line = text[line_start : line_end if line_end != -1 else None].strip()
                offenders.append(f"{rel}: {line}")
    return offenders


class DocsCliFlagNamesTest(unittest.TestCase):
    def test_no_skip_docker_short_alias(self) -> None:
        bad = _scan(OPERATOR_DOC_GLOBS, _SKIP_DOCKER_SHORT)
        self.assertEqual(
            bad,
            [],
            "use --skip-docker-smoke (not --skip-docker)",
        )

    def test_no_ssh_root_alias(self) -> None:
        bad = _scan(OPERATOR_DOC_GLOBS, _SSH_ROOT)
        self.assertEqual(bad, [], "use --root-ssh (not --ssh-root)")

    def test_no_plan_list_flag(self) -> None:
        bad = _scan(OPERATOR_DOC_GLOBS, _PLAN_LIST)
        self.assertEqual(
            bad,
            [],
            "plan has no --list; use ./cluster list for clusters",
        )

    def test_jenkins_docs_phases_param(self) -> None:
        text = (ROOT / "docs" / "jenkins.md").read_text(encoding="utf-8")
        self.assertIn("`PHASES`", text)
        self.assertIn("--phases", text)
        self.assertNotIn("FROM_PHASE", text)
        self.assertNotIn("TO_PHASE", text)

    def test_jenkinsfiles_use_phases_selector(self) -> None:
        seed_dsl = (
            ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
        ).read_text(encoding="utf-8")
        self.assertIn("PHASES", seed_dsl)

        for name in ("Jenkinsfile", "Jenkinsfile.local"):
            path = ROOT / "examples" / "internal" / name
            text = path.read_text(encoding="utf-8")
            self.assertIn("params.PHASES", text, name)
            self.assertIn('plan --phases "${PHASES}"', text, name)
            self.assertNotIn("FROM_PHASE", text, name)
            self.assertNotIn("TO_PHASE", text, name)
            self.assertNotIn("--from", text, name)
            self.assertNotIn("--to", text, name)


if __name__ == "__main__":
    unittest.main()
