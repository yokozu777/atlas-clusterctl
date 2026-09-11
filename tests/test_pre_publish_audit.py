"""Pre-publish audit surface (publish step 7)."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tests" / "check_pre_publish_audit.py"
DOC = ROOT / "docs" / "pre-publish.md"


class PrePublishAuditTest(unittest.TestCase):
    def test_audit_script_and_doc_exist(self) -> None:
        self.assertTrue(AUDIT.is_file(), str(AUDIT))
        self.assertTrue(DOC.is_file(), str(DOC))
        text = DOC.read_text(encoding="utf-8")
        for needle in (
            "git ls-files clusters/ci clusters/dev",
            "check_pre_publish_audit.py",
            "filter-repo",
            "Welcomeback",
            "./tests/run_ci.sh",
            "Phase 7 status",
            "Operator-owned",
        ):
            self.assertIn(needle, text, needle)

    def test_audit_passes_on_current_index(self) -> None:
        proc = subprocess.run(
            ["python3", str(AUDIT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}",
        )
        self.assertIn("OK: pre-publish audit", proc.stdout)

    def test_index_has_no_labs_or_secrets(self) -> None:
        labs = subprocess.check_output(
            ["git", "ls-files", "clusters/ci", "clusters/dev"],
            cwd=ROOT,
            text=True,
        ).splitlines()
        self.assertEqual(labs, [])
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


if __name__ == "__main__":
    unittest.main()
