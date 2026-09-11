"""Jenkins seed Phase 3: operator docs polish (workflow crisp)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
INTERNAL_README = ROOT / "examples" / "internal" / "README.md"
ROOT_README = ROOT / "README.md"
GATE = ROOT / "tests" / "test_jenkins_seed_phase3.py"


class JenkinsSeedPhase3Test(unittest.TestCase):
    def test_contract_phase3_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Phase 3", text)
        self.assertIn("[x] Operator docs polish (Phase 3)", text)
        self.assertIn("workflow crisp — **done**", text)
        self.assertIn("test_jenkins_seed_phase3.py", text)
        self.assertIn("Manual Build only", text)
        self.assertIn("no cron", text.lower())
        self.assertIn("Bootstrap", text)
        self.assertIn("Day-to-day", text)
        self.assertIn("Inventory leaf change", text)

    def test_changelog_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — Phase 3", text)
        self.assertIn("test_jenkins_seed_phase3.py", text)
        self.assertIn("Operator docs polish", text)

    def test_jenkins_md_operator_workflow(self) -> None:
        text = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("## Operator workflow", text)
        self.assertIn("### First time (bootstrap)", text)
        self.assertIn("### Day-to-day deploy", text)
        self.assertIn("### When to re-run seed", text)
        self.assertIn("manual only", text.lower())
        self.assertIn("no cron", text.lower())
        self.assertIn("no inventory webhook", text.lower())
        self.assertIn("atlas-clusterctl-seed", text)
        self.assertIn("Phase 0–5 done", text)
        self.assertIn("CLUSTER_ID missing", text)
        # Seed row in samples table
        self.assertIn("examples/internal/seed/Jenkinsfile", text)

    def test_seed_readme_operator_facing(self) -> None:
        text = SEED_README.read_text(encoding="utf-8")
        self.assertIn("no cron", text.lower())
        self.assertIn("no inventory webhook", text.lower())
        self.assertIn("## Setup (once)", text)
        self.assertIn("## When to re-run", text)
        self.assertIn("## Seed parameters", text)
        self.assertIn("## Troubleshooting", text)
        self.assertIn("CLUSTER_ID missing", text)
        self.assertIn("DEPLOY_SPECS", text)
        self.assertIn("[x] Phase 3 — operator docs polish", text)
        self.assertIn("docs/jenkins.md", text)

    def test_internal_and_root_readme(self) -> None:
        internal = INTERNAL_README.read_text(encoding="utf-8")
        self.assertIn("Operator workflow", internal)
        self.assertIn("**Bootstrap**", internal)
        self.assertIn("**Deploy (day-to-day)**", internal)
        self.assertIn("Manual Build only", internal)
        self.assertIn("seed/Jenkinsfile", internal)

        root = ROOT_README.read_text(encoding="utf-8")
        self.assertIn("jenkins-seed.md", root)
        self.assertIn("atlas-clusterctl-seed", root)
        self.assertIn("omit `parameters {}`", root)
        # Stale Deps/venv guidance removed in Phase 3 polish.
        self.assertNotIn("Deps", root.split("## Jenkins Pipeline")[1].split("## Documentation")[0])
        self.assertNotIn("python3-venv", root)
        self.assertNotIn("requirements.txt", root.split("## Jenkins Pipeline")[1].split("## Documentation")[0])

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
