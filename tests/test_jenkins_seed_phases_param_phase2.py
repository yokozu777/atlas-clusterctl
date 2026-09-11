"""Jenkins seed PHASES follow-up Phase 2: shared phases-list helper + fixture."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
CHANGELOG = ROOT / "CHANGELOG.md"
HELPER = ROOT / "clusterctl" / "tools" / "list_cluster_phases.py"
UNIT = ROOT / "tests" / "test_list_cluster_phases.py"
FIXTURE = ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "clusters"
FIXTURE_README = ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "README.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
GATE = ROOT / "tests" / "test_jenkins_seed_phases_param_phase2.py"


class JenkinsSeedPhasesParamPhase2Test(unittest.TestCase):
    def test_contract_phase2_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertTrue(
            "Phase 1–2 done" in text
            or "Phase 1–3 done" in text
            or "Phase 4 deferred (locked)" in text
            or "Phase 4 deferred/locked" in text
            or "Phase 0–5 done" in text,
            "contract banner must mark Phase 2 complete",
        )
        self.assertIn(
            "Offline id → phase names — **done**",
            text,
        )
        self.assertIn("collect_phases_for_cluster", text)
        self.assertIn("list_cluster_phases", text)
        self.assertIn("test_list_cluster_phases.py", text)
        self.assertIn("test_jenkins_seed_phases_param_phase2.py", text)
        self.assertIn(
            "[x] Phase 2 — phases-list helper + fixture",
            text,
        )

    def test_changelog_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — PHASES follow-up Phase 2", text)
        self.assertIn("test_jenkins_seed_phases_param_phase2.py", text)
        self.assertIn("list_cluster_phases", text)
        self.assertIn("collect_phases_for_cluster", text)

    def test_artifacts_present(self) -> None:
        self.assertTrue(HELPER.is_file(), HELPER)
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn("def collect_phases_for_cluster", helper)
        self.assertIn("def collect_phases_map", helper)
        self.assertIn("PhasesUnavailableError", helper)
        self.assertIn("load_merged_cluster_config_v2", helper)
        self.assertIn("stage_name_for_phase_ref", helper)

        self.assertTrue(UNIT.is_file(), UNIT)
        self.assertTrue((FIXTURE / "fixture" / "postgresql" / "cluster.yaml").is_file())
        pg = (FIXTURE / "fixture" / "postgresql" / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("phases:", pg)
        self.assertIn("postgresql:", pg)

        readme = FIXTURE_README.read_text(encoding="utf-8")
        self.assertIn("list_cluster_phases", readme)
        self.assertIn("hosts_only", readme)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("follow-up Phase 2", seed)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
