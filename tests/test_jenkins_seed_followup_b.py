"""Jenkins seed follow-up Phase B: null-safe env, membership docs, DSL split."""

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
FIXTURE_README = ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "README.md"
GATE = ROOT / "tests" / "test_jenkins_seed_followup_b.py"

_RAW_ENV_CLUSTER = re.compile(
    r'CLUSTER_ID\s*=\s*"\$\{params\.CLUSTER_ID\}"'
)
_EXECUTION_PARAM = re.compile(
    r"stringParam\(\s*'EXECUTION_DOCKER_TAG'",
    re.MULTILINE,
)


class JenkinsSeedFollowupBTest(unittest.TestCase):
    def test_changelog_phase_b(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — follow-up Phase B", text)
        self.assertIn("test_jenkins_seed_followup_b.py", text)
        self.assertIn("envParam", text)
        self.assertIn("requireSeedManagedParams", text)
        self.assertIn("EXECUTION_DOCKER_TAG", text)

    def test_deploy_jf_null_safe_env_and_guard(self) -> None:
        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn("def envParam(", text, path.name)
            self.assertIn("equalsIgnoreCase('null')", text, path.name)
            self.assertIn("instanceof Collection", text, path.name)
            self.assertIn("instanceof Object[]", text, path.name)
            self.assertNotIn("getClass().isArray()", text, path.name)
            self.assertIn("def requireSeedManagedParams(", text, path.name)
            self.assertIn("requireSeedManagedParams()", text, path.name)
            self.assertIn("Seed-managed boolean params missing", text, path.name)
            self.assertIn("CLUSTER_ID missing", text, path.name)
            self.assertIsNone(
                _RAW_ENV_CLUSTER.search(text),
                f"{path.name}: CLUSTER_ID env must use envParam, not raw params",
            )
            self.assertIn(
                'CLUSTER_ID = "${envParam(params.CLUSTER_ID)}"',
                text,
                path.name,
            )
            self.assertIn("params.RUN_CI_PREFLIGHT == true", text, path.name)
            self.assertIn("params.RUN_SMOKE == true", text, path.name)
            self.assertIn("params.SKIP_DEPLOY != true", text, path.name)
            self.assertIn("expression { envParam(params.INVENTORY_GIT_URL) }", text, path.name)

        docker = DOCKER_JF.read_text(encoding="utf-8")
        self.assertIn(
            'EXECUTION_DOCKER_TAG = "${envParam(params.EXECUTION_DOCKER_TAG)}"',
            docker,
        )
        local = LOCAL_JF.read_text(encoding="utf-8")
        self.assertNotIn("EXECUTION_DOCKER_TAG", local)

    def test_dsl_omits_execution_tag_for_local(self) -> None:
        text = SEED_DSL.read_text(encoding="utf-8")
        self.assertIn("dockerSample", text)
        self.assertIn("Jenkinsfile.local", text)
        self.assertIn("if (dockerSample)", text)
        self.assertIsNotNone(_EXECUTION_PARAM.search(text))
        matches = list(_EXECUTION_PARAM.finditer(text))
        self.assertEqual(len(matches), 1)
        before = text[: matches[0].start()]
        self.assertIn("if (dockerSample)", before)
        self.assertIn("bare-agent", text)
        # Local var must not be named scriptPath — shadows Job DSL method scriptPath(…).
        self.assertIn("jfScript", text)
        self.assertIn("scriptPath(jfScript)", text)
        self.assertNotIn("def scriptPath =", text)
        self.assertIn("AGENT", text)
        self.assertIn("AGENT_CHOICES", text)
        self.assertIn("choiceParam(", text)

    def test_docs_membership_not_health_guarantee(self) -> None:
        contract = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("deployable layout", contract)
        self.assertIn("Choice membership ≠ health guarantee", contract)
        self.assertIn("validate", contract.lower())
        self.assertIn("smoke", contract.lower())
        self.assertNotIn("/ broken overlays", contract)

        fixture = FIXTURE_README.read_text(encoding="utf-8")
        self.assertIn("hosts_only", fixture)
        self.assertIn("scanner", fixture.lower())
        self.assertIn("not a validate/smoke", fixture.lower())

        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("omitted from `.local`", jenkins)
        self.assertIn("Active Choices", jenkins)
        self.assertIn("AGENT", jenkins)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("EXECUTION_DOCKER_TAG", seed)
        self.assertIn("Jenkinsfile.local", seed)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
