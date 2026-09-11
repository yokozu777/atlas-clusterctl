"""Jenkins seed Phase 4: shared list helper + fixture inventory hardening."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
CHANGELOG = ROOT / "CHANGELOG.md"
HELPER = ROOT / "clusterctl" / "tools" / "list_deployable_clusters.py"
UNIT = ROOT / "tests" / "test_list_deployable_clusters.py"
FIXTURE = ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "clusters"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
GATE = ROOT / "tests" / "test_jenkins_seed_phase4.py"


class JenkinsSeedPhase4Test(unittest.TestCase):
    def test_contract_phase4_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Phase 4", text)
        self.assertIn("[x] List helper + tests (Phase 4)", text)
        self.assertIn("Scanner gate green — **done**", text)
        self.assertIn("collect_deployable_cluster_ids", text)
        self.assertIn("jenkins_seed_inventory", text)
        self.assertIn("test_list_deployable_clusters.py", text)
        self.assertIn("test_jenkins_seed_phase4.py", text)

    def test_changelog_phase4(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — Phase 4", text)
        self.assertIn("test_jenkins_seed_phase4.py", text)
        self.assertIn("collect_deployable_cluster_ids", text)
        self.assertIn("jenkins_seed_inventory", text)

    def test_artifacts_present(self) -> None:
        self.assertTrue(HELPER.is_file(), HELPER)
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn("def collect_deployable_cluster_ids", helper)
        self.assertIn("list_deployable_cluster_ids", helper)

        self.assertTrue(UNIT.is_file(), UNIT)
        self.assertTrue(FIXTURE.is_dir(), FIXTURE)
        # Fixture must include policy + deployable leaves for scanner coverage.
        self.assertTrue((FIXTURE / "fixture" / "redis" / "cluster.yaml").is_file())
        self.assertTrue((FIXTURE / "fixture" / "default" / "cluster.yaml").is_file())
        self.assertTrue((FIXTURE / "default" / "default" / "cluster.yaml").is_file())
        self.assertTrue((FIXTURE / "fixture" / "hosts_only" / "hosts").is_file())
        self.assertTrue((FIXTURE / "_template" / "ignored" / "cluster.yaml").is_file())
        self.assertTrue((FIXTURE / "fixture" / "broken_empty").is_dir())

    def test_seed_readme_phase4(self) -> None:
        text = SEED_README.read_text(encoding="utf-8")
        self.assertIn("[x] Phase 4", text)
        self.assertIn("list_deployable_clusters", text)
        self.assertIn("jenkins_seed_inventory", text)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
