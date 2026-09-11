"""Post–ADR 009 cleanup A4: Jenkins plan examples start at ``provision``, not ``templates``."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
CHANGELOG = ROOT / "CHANGELOG.md"
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"

_STALE_PLAN_TEMPLATES = re.compile(
    r"\[1/4\]\s*atlas-compute-provision/templates"
)


class Adr009JenkinsPlanExampleA4Test(unittest.TestCase):
    def test_jenkins_doc_example_uses_provision(self) -> None:
        text = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn(
            "[1/4] atlas-compute-provision/provision",
            text,
        )
        self.assertIsNone(
            _STALE_PLAN_TEMPLATES.search(text),
            "jenkins.md still shows templates as the typical [1/4] plan phase",
        )

    def test_jenkinsfiles_comments_use_provision(self) -> None:
        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                'atlas-compute-provision/provision"',
                text,
                path.name,
            )
            self.assertIsNone(
                _STALE_PLAN_TEMPLATES.search(text),
                f"{path.name} comment still cites templates as [1/4]",
            )
            # Dynamic stage name still built from plan JSON phase_ref.
            self.assertIn('"[${n}/${total}] ${phaseRef}"', text, path.name)

    def test_changelog_and_adr_a4(self) -> None:
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("post-cleanup A4", changelog)
        self.assertIn("provision", changelog)
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("post-cleanup A4", adr)


if __name__ == "__main__":
    unittest.main()
