"""Phase 6: automated E2E / Jenkins sign-off matrix (offline-safe checks)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from clusterctl.smoke import run_smoke
from clusterctl.validate import validate_all_clusters, validate_repo


ROOT = Path(__file__).resolve().parents[1]


class Phase6E2ESignoffTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "VALIDATE_SKIP_DOCKER_SMOKE")

    def setUp(self) -> None:
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)
        os.environ["VALIDATE_SKIP_DOCKER_SMOKE"] = "1"

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_validate_repo_zero_errors(self) -> None:
        report = validate_repo(ROOT)
        errors = [issue for issue in report.issues if issue.is_error]
        self.assertEqual(errors, [], [issue.message for issue in errors])

    def test_validate_all_skip_docker_zero_errors(self) -> None:
        reports = validate_all_clusters(ROOT, docker_smoke=False)
        errors = [
            issue
            for report in reports
            for issue in report.issues
            if issue.is_error
        ]
        self.assertEqual(errors, [], [issue.message for issue in errors])

    def test_smoke_all_plan_ok_offline(self) -> None:
        results = run_smoke(ROOT, include_repo=False)
        for report, smoke in results:
            self.assertTrue(report.ok, report.issues)
            if smoke is not None:
                self.assertTrue(smoke.plan_ok, smoke.error)
                self.assertGreater(smoke.invocations, 0)

    def test_jenkinsfile_cluster_cli_matrix(self) -> None:
        docker_jf = (ROOT / "examples" / "internal" / "Jenkinsfile").read_text(encoding="utf-8")
        local_jf = (ROOT / "examples" / "internal" / "Jenkinsfile.local").read_text(
            encoding="utf-8"
        )
        for text in (docker_jf, local_jf):
            self.assertIn("./cluster --cluster", text)
            self.assertIn("ci_preflight", text)
            self.assertIn("repos sync", text)
            self.assertIn("validate", text)
            self.assertIn("--strict", text)
            self.assertIn("VALIDATE_STRICT", text)
            self.assertIn("smoke", text)
            self.assertIn("readJSON", text)
            self.assertIn("plan.json", text)
            self.assertIn('run --phases "${PHASE_REF}"', text)
            self.assertIn("runClusterPhase", text)
            self.assertIn("EXTRA_VARS", text)
            self.assertIn("params.EXTRA_VARS", text)
            self.assertIn("params.TAGS", text)
            self.assertIn("params.LIMIT", text)
            self.assertIn('extra+=(--tags "${TAGS}")', text)
            self.assertIn('extra+=(--limit "${LIMIT}")', text)
            self.assertIn("bash -euo pipefail", text)
            self.assertIn("provision_mode=destroy", text)
            self.assertNotIn('stage "${PHASE_REF}"', text)
            self.assertIn("[${n}/${total}] ${phaseRef}", text)
            self.assertNotIn("ARGS=(play", text)
            self.assertNotIn("envStr(", text)
            self.assertIn("ansiColor(", text)
            self.assertIn("timestamps()", text)
            self.assertNotIn("JsonSlurperClassic", text)
            self.assertNotIn("./cluster --cluster \"${CLUSTER_ID}\" stage", text)
            self.assertIn("INVENTORY_GIT_URL", text)
            self.assertIn("Inventory checkout", text)
            self.assertIn(".config/config.yaml", text)
            self.assertIn("Prepare", text)
            self.assertIn("/tmp/clusterctl", text)
            self.assertNotIn("Bootstrap packages", text)
            self.assertNotIn("python3 -m venv", text)
            self.assertNotIn("requirements.txt", text)
            self.assertNotIn("prepare_workflow", text)
            self.assertNotIn("role-repos sync", text)
            # Phase 2: UI params from seed — deploy JF must not declare parameters {}.
            self.assertNotIn("name: 'CLUSTER_ID'", text)
            self.assertNotIn("name: 'PHASES'", text)
            self.assertIn("params.CLUSTER_ID", text)
            self.assertIn('CLUSTER_ID = "${envParam(params.CLUSTER_ID)}"', text)
            self.assertIn("PHASES", text)
            self.assertIn('plan --phases "${PHASES}"', text)
            self.assertNotIn("FROM_PHASE", text)
            self.assertNotIn("TO_PHASE", text)
            self.assertNotIn("--from", text)
            self.assertNotIn("--to", text)
            self.assertIn("params.AGENT", text)
            self.assertNotIn("getJenkinsAgents", text)
            self.assertIn("UI parameters SoT = seed", text)

        seed_dsl = (
            ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
        ).read_text(encoding="utf-8")
        self.assertIn("choiceParam(", seed_dsl)
        self.assertIn("'CLUSTER_ID'", seed_dsl)
        self.assertIn("TAGS", seed_dsl)
        self.assertIn("LIMIT", seed_dsl)
        self.assertIn("EXTRA_VARS", seed_dsl)
        self.assertIn("PHASES", seed_dsl)

        self.assertIn("harbor.mxhash.com/library/krang", docker_jf)
        self.assertIn("docker {", docker_jf)
        self.assertIn("envParam(params.AGENT, 'built-in')", docker_jf)
        self.assertNotIn("agent any", docker_jf)
        self.assertNotIn("AGENT_LABEL", docker_jf)

        self.assertIn("envParam(params.AGENT, 'built-in')", local_jf)
        self.assertNotIn("CLUSTER_EXECUTOR =", local_jf)
        self.assertNotIn("docker {", local_jf)
        self.assertNotIn("EXECUTION_DOCKER_TAG", local_jf)
        self.assertNotIn("agent any", local_jf)
        self.assertNotIn("AGENT_LABEL", local_jf)

    def test_jenkins_docs_list_plugins_and_agent_software(self) -> None:
        text = (ROOT / "docs" / "jenkins.md").read_text(encoding="utf-8")
        for needle in (
            "pipeline-utility-steps",
            "ansicolor",
            "timestamper",
            "ws-cleanup",
            "docker-workflow",
            "ssh-credentials",
            "credentials-binding",
            "PyYAML",
            "sshpass",
            "/tmp/clusterctl",
            "ansible-playbook",
            "EXTRA_VARS",
            "provision_mode=destroy",
            "run --phases",
            "ADR 009",
        ):
            self.assertIn(needle, text)
        readme = (ROOT / "examples" / "internal" / "README.md").read_text(encoding="utf-8")
        self.assertIn("pipeline-utility-steps", readme)
        self.assertIn("Docker Engine", readme)
        self.assertIn("ansible", readme)

    def test_cluster_help_documents_stages_baseline(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "clusterctl", "stages", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--baseline", proc.stdout)

    def test_changelog_documents_phase6(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertRegex(changelog, r"playbooks\.lock", re.IGNORECASE)

    def test_playbooks_doc_documents_lock(self) -> None:
        doc = (ROOT / "docs" / "playbooks.md").read_text(encoding="utf-8")
        self.assertIn("playbooks.lock", doc)


if __name__ == "__main__":
    unittest.main()
