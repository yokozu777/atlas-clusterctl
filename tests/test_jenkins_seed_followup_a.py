"""Jenkins seed follow-up Phase A: remote URL, lightweight/wipe, rewrite docs."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
SEED_JF = ROOT / "examples" / "internal" / "seed" / "Jenkinsfile"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
GATE = ROOT / "tests" / "test_jenkins_seed_followup_a.py"

_SET_URL = re.compile(r"remote\s+set-url\s+origin")
_LIGHTWEIGHT_TRUE = re.compile(r"lightweight\s*\(\s*true\s*\)")


class JenkinsSeedFollowupATest(unittest.TestCase):
    def test_changelog_phase_a(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — follow-up Phase A", text)
        self.assertIn("test_jenkins_seed_followup_a.py", text)
        self.assertIn("set-url", text)
        self.assertIn("lightweight(false)", text)

    def test_inventory_checkout_updates_origin(self) -> None:
        for path in (SEED_JF, DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIsNotNone(
                _SET_URL.search(text),
                f"{path.name}: missing git remote set-url when origin mismatches",
            )
            self.assertIn("origin mismatch", text, path.name)
            self.assertIn('remote get-url origin', text, path.name)

    def test_dsl_lightweight_false_with_wipe(self) -> None:
        text = SEED_DSL.read_text(encoding="utf-8")
        self.assertIn("wipeOutWorkspace()", text)
        self.assertIn("lightweight(false)", text)
        self.assertIsNone(
            _LIGHTWEIGHT_TRUE.search(text),
            "deploy cpsScm must not use lightweight(true) with wipeOutWorkspace",
        )
        self.assertIn("rewrites this job", text)
        self.assertIn("DEPLOY_SPECS", text)

    def test_docs_side_effects(self) -> None:
        contract = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("### Seed side effects", contract)
        self.assertIn("rewrites", contract.lower())
        self.assertIn("parameter definitions", contract)
        self.assertIn("Do **not** rely on manual UI tweaks", contract)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("## Side effects", seed)
        self.assertIn("set-url", seed)
        self.assertIn("lightweight(false)", seed)

        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("Seed side effects", jenkins)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
