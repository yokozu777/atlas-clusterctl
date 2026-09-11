"""Jenkins seed Phase 1: seed scripts + list_deployable_clusters helper."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_DIR = ROOT / "examples" / "internal" / "seed"
SEED_JF = SEED_DIR / "Jenkinsfile"
SEED_DSL = SEED_DIR / "seed_deploy_jobs.groovy"
SEED_README = SEED_DIR / "README.md"
HELPER = ROOT / "clusterctl" / "tools" / "list_deployable_clusters.py"
GATE = ROOT / "tests" / "test_jenkins_seed_phase1.py"


class JenkinsSeedPhase1Test(unittest.TestCase):
    def test_artifacts_present(self) -> None:
        self.assertTrue(SEED_JF.is_file(), SEED_JF)
        self.assertTrue(SEED_DSL.is_file(), SEED_DSL)
        self.assertTrue(HELPER.is_file(), HELPER)
        self.assertTrue(SEED_README.is_file(), SEED_README)
        self.assertTrue(GATE.is_file(), GATE)

    def test_contract_phase1_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Phase 1", text)
        self.assertIn("[x] Seed sample scripts (Phase 1)", text)
        self.assertIn("list_deployable_clusters", text)
        self.assertIn("seed_deploy_jobs.groovy", text)
        self.assertIn("test_jenkins_seed_phase1.py", text)

    def test_changelog_phase1(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — Phase 1", text)
        self.assertIn("test_jenkins_seed_phase1.py", text)
        self.assertIn("list_deployable_clusters", text)
        self.assertIn("seed_deploy_jobs.groovy", text)

    def test_jenkinsfile_manual_seed_flow(self) -> None:
        text = SEED_JF.read_text(encoding="utf-8")
        self.assertNotIn("triggers {", text)
        self.assertNotIn("cron(", text)
        self.assertNotIn("pollSCM", text)
        self.assertIn("list_deployable_clusters", text)
        self.assertIn("jobDsl(", text)
        self.assertIn("seed_deploy_jobs.groovy", text)
        self.assertIn("CLUSTER_IDS", text)
        self.assertIn("DEPLOY_SPECS", text)
        self.assertIn("empty deployable id list", text)
        self.assertIn("bash -euo pipefail", text)
        self.assertIn("atlas-clusterctl-local|examples/internal/Jenkinsfile.local", text)
        self.assertIn("atlas-clusterctl|examples/internal/Jenkinsfile", text)

    def test_dsl_full_params_template(self) -> None:
        text = SEED_DSL.read_text(encoding="utf-8")
        self.assertIn("choiceParam(", text)
        self.assertIn("'CLUSTER_ID'", text)
        self.assertIn("TAGS", text)
        self.assertIn("LIMIT", text)
        self.assertIn("EXTRA_VARS", text)
        self.assertIn("INVENTORY_GIT_URL", text)
        self.assertIn("PHASES", text)
        self.assertIn("pipelineJob(", text)
        self.assertIn("cpsScm", text)
        self.assertIn("CLUSTER_IDS is empty", text)
        self.assertIn("DEPLOY_SPECS", text)

    def test_seed_readme(self) -> None:
        text = SEED_README.read_text(encoding="utf-8")
        self.assertIn("Phase 1", text)
        self.assertIn("Jenkinsfile", text)
        self.assertIn("seed_deploy_jobs.groovy", text)
        self.assertIn("atlas-clusterctl-seed", text)
        self.assertIn("Phase 2", text)


if __name__ == "__main__":
    unittest.main()
