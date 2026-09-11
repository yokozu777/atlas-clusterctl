"""Jenkins seed Phase 0: manual seed job contract for ``CLUSTER_ID`` choice."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
INTERNAL_README = ROOT / "examples" / "internal" / "README.md"
GATE = ROOT / "tests" / "test_jenkins_seed_phase0.py"


class JenkinsSeedPhase0Test(unittest.TestCase):
    def test_contract_locked(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Phase 0", text)
        self.assertIn("**Seed job**", text)
        self.assertIn("**Job DSL**", text)
        self.assertIn("**Manual Build only**", text)
        self.assertIn("no cron", text.lower())
        self.assertIn("no inventory webhook", text.lower())
        self.assertIn("Active Choices", text)
        self.assertIn("atlas-clusterctl-seed", text)
        self.assertIn("atlas-clusterctl-local", text)
        self.assertIn("list_deployable_cluster_ids", text)
        self.assertIn("string(name: 'CLUSTER_ID')", text)
        self.assertIn("TAGS", text)
        self.assertIn("LIMIT", text)
        self.assertIn("EXTRA_VARS", text)
        self.assertIn("Empty scan", text)
        self.assertIn("job-dsl", text)
        self.assertIn("[x] Seed + Job DSL vs Active Choices decided — **seed + Job DSL**", text)
        self.assertIn("[x] Manual trigger only (no cron/webhook in scope)", text)
        self.assertIn("test_jenkins_seed_phase0.py", text)

    def test_phase_plan_and_checklist(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        for phase in ("Phase 0", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5"):
            self.assertIn(f"**{phase}**", text, phase)
        self.assertIn("[x] Acceptance (Phase 5)", text)

    def test_docs_linked(self) -> None:
        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("jenkins-seed.md", jenkins)
        self.assertIn("job-dsl", jenkins)
        self.assertIn("examples/internal/seed", jenkins)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("jenkins-seed.md", seed)
        self.assertIn("atlas-clusterctl-seed", seed)
        self.assertIn("Phase 1", seed)

        internal = INTERNAL_README.read_text(encoding="utf-8")
        self.assertIn("jenkins-seed.md", internal)
        self.assertIn("seed/", internal)
        self.assertIn("job-dsl", internal)

    def test_changelog_phase0(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — Phase 0", text)
        self.assertIn("test_jenkins_seed_phase0.py", text)
        self.assertIn("jenkins-seed.md", text)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
