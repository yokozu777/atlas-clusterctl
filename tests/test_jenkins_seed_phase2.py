"""Jenkins seed Phase 2: deploy JF omits parameters{}; UI SoT = seed."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
GATE = ROOT / "tests" / "test_jenkins_seed_phase2.py"

_PARAMS_BLOCK = re.compile(r"(?m)^\s*parameters\s*\{")
_STRING_CLUSTER_ID = re.compile(
    r"string\s*\(\s*name:\s*'CLUSTER_ID'",
    re.MULTILINE,
)


class JenkinsSeedPhase2Test(unittest.TestCase):
    def test_contract_phase2_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Phase 2", text)
        self.assertIn("[x] Deploy JF `CLUSTER_ID` alignment (Phase 2)", text)
        self.assertIn("omit declarative", text.lower())
        self.assertIn("test_jenkins_seed_phase2.py", text)
        self.assertIn("**done**", text)

    def test_changelog_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — Phase 2", text)
        self.assertIn("test_jenkins_seed_phase2.py", text)
        self.assertIn("parameters {}", text)

    def test_deploy_jenkinsfiles_omit_parameters(self) -> None:
        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                _PARAMS_BLOCK.search(text),
                f"{path.name} must not declare parameters {{}} (UI SoT = seed)",
            )
            self.assertIsNone(
                _STRING_CLUSTER_ID.search(text),
                f"{path.name} must not declare string CLUSTER_ID",
            )
            self.assertNotIn("getJenkinsAgents", text, path.name)
            self.assertIn("UI parameters SoT = seed", text, path.name)
            self.assertIn("docs/jenkins-seed.md", text, path.name)
            self.assertIn("atlas-clusterctl-seed", text, path.name)
            self.assertIn("CLUSTER_ID missing", text, path.name)
            self.assertIn("params.CLUSTER_ID", text, path.name)
            self.assertIn('CLUSTER_ID = "${envParam(params.CLUSTER_ID)}"', text, path.name)
            self.assertIn("requireSeedManagedParams", text, path.name)
            self.assertIn("params.TAGS", text, path.name)
            self.assertIn("params.LIMIT", text, path.name)
            self.assertIn("params.EXTRA_VARS", text, path.name)
            self.assertIn("params.PHASES", text, path.name)
            self.assertIn("params.AGENT", text, path.name)

    def test_seed_dsl_owns_full_template(self) -> None:
        text = SEED_DSL.read_text(encoding="utf-8")
        self.assertIn("choiceParam(", text)
        self.assertIn("'CLUSTER_ID'", text)
        self.assertIn("'AGENT'", text)
        self.assertIn("AGENT_CHOICES", text)
        self.assertIn("new ArrayList(agents)", text)
        for needle in ("TAGS", "LIMIT", "EXTRA_VARS", "PHASES", "INVENTORY_GIT_URL"):
            self.assertIn(needle, text, needle)
        self.assertIn("rewrites params", text)
        self.assertNotIn("Until Phase 2", text)
        self.assertIn("lightweight(false)", text)

    def test_docs_ui_sot(self) -> None:
        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("UI SoT", jenkins)
        self.assertIn("omit", jenkins.lower())
        self.assertIn("seed Job DSL", jenkins)
        self.assertIn("parameters { }", jenkins)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("[x] Phase 2", seed)
        self.assertNotIn("still declare `string(name: 'CLUSTER_ID')`", seed)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
