"""Phase 7 gate: working-tree publish readiness (pre-publish checklist)."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "pre-publish.md"
CHANGELOG = ROOT / "CHANGELOG.md"
REPORT = ROOT / "notes" / "report_clusterctl.md"
AUDIT = ROOT / "tests" / "check_pre_publish_audit.py"
HYGIENE = ROOT / "tests" / "check_publish_hygiene.sh"

_PUBLISH_SURFACE = (
    "LICENSE",
    "SECURITY.md",
    ".github/workflows/ci.yml",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "docs/local-labs.md",
    "docs/pre-publish.md",
    "tests/check_pre_publish_audit.py",
    "tests/check_publish_hygiene.sh",
    "tests/run_ci.sh",
)

_CHECKED = re.compile(r"^- \[x\] ", re.MULTILINE)
_UNCHECKED_OPERATOR = (
    "When the public remote URL is known, add `[project.urls]`",
    "Rotate any passwords / tokens that appeared in historical labs",
)


class PrePublishPhase7Test(unittest.TestCase):
    def test_phase7_status_banner(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("Phase 7 status — working-tree publish readiness", text)
        self.assertIn("**Ready**", text)
        self.assertIn("**Operator-owned**", text)
        self.assertIn("History rewrite / orphan publish", text)
        # Working-tree items checked; operator items remain open.
        self.assertGreaterEqual(len(_CHECKED.findall(text)), 7)
        for needle in _UNCHECKED_OPERATOR:
            self.assertIn(f"- [ ] {needle}", text, needle)

    def test_changelog_and_report_phase7(self) -> None:
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("publish readiness", changelog.lower())
        self.assertIn("Phase 7", changelog)
        report = REPORT.read_text(encoding="utf-8")
        self.assertIn("Фаза 7", report)
        self.assertIn("pre-publish", report.lower())

    def test_publish_surface_tracked(self) -> None:
        indexed = set(
            subprocess.check_output(
                ["git", "ls-files", "--", *_PUBLISH_SURFACE],
                cwd=ROOT,
                text=True,
            ).splitlines()
        )
        for rel in _PUBLISH_SURFACE:
            self.assertIn(rel, indexed, rel)
        self.assertFalse((ROOT / "scripts").exists())
        self.assertFalse((ROOT / "Jenkinsfile").is_file())

    def test_labs_absent_from_index_and_ignored(self) -> None:
        labs = subprocess.check_output(
            ["git", "ls-files", "clusters/ci", "clusters/dev"],
            cwd=ROOT,
            text=True,
        ).splitlines()
        self.assertEqual(labs, [])
        lab = ROOT / "clusters" / "dev" / "k8s" / "cluster.yaml"
        if not lab.is_file():
            return
        proc = subprocess.run(
            ["git", "check-ignore", "-v", str(lab.relative_to(ROOT))],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("clusters/dev", proc.stdout)

    def test_no_legacy_secrets_tracked(self) -> None:
        secrets = [
            line
            for line in subprocess.check_output(
                ["git", "ls-files"],
                cwd=ROOT,
                text=True,
            ).splitlines()
            if Path(line).name in ("secrets.yml", "secrets.yaml")
        ]
        self.assertEqual(secrets, [])

    def test_automated_gates_exit_zero(self) -> None:
        audit = subprocess.run(
            ["python3", str(AUDIT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(audit.returncode, 0, audit.stderr + audit.stdout)
        self.assertIn("OK: pre-publish audit", audit.stdout)
        hygiene = subprocess.run(
            ["bash", str(HYGIENE)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(hygiene.returncode, 0, hygiene.stderr + hygiene.stdout)
        self.assertIn("OK: publish hygiene", hygiene.stdout)


if __name__ == "__main__":
    unittest.main()
