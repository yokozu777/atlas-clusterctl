"""Jenkins seed LIMIT follow-up Phase 1: list_cluster_limits helper + fixture."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
CHANGELOG = ROOT / "CHANGELOG.md"
ADR011 = ROOT / "docs" / "adr" / "011-jenkins-limits-active-choices.md"
HELPER = ROOT / "clusterctl" / "tools" / "list_cluster_limits.py"
UNIT = ROOT / "tests" / "test_list_cluster_limits.py"
FIXTURE = ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "clusters"
FIXTURE_README = ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "README.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
GATE = ROOT / "tests" / "test_jenkins_seed_limits_param_phase1.py"


class JenkinsSeedLimitsParamPhase1Test(unittest.TestCase):
    def test_contract_phase1_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertTrue(
            "Phase 0–1 done" in text
            or "Phase 0–2 done" in text
            or "Phase 0–3 done" in text
            or "Phase 0–4 done" in text
            or "Phase 0–5 done" in text
            or "Phase 1 done" in text
            or "Offline id → groups/hosts catalog — **done**" in text,
            "contract banner / plan must mark Phase 1 complete",
        )
        self.assertIn(
            "Offline id → groups/hosts catalog — **done**",
            text,
        )
        self.assertIn("list_cluster_limits", text)
        self.assertIn("collect_limits_for_cluster", text)
        self.assertIn("collect_limits_parts_for_cluster", text)
        self.assertIn("test_list_cluster_limits.py", text)
        self.assertIn("test_jenkins_seed_limits_param_phase1.py", text)
        self.assertIn(
            "[x] Phase 1 — helper + fixture (`tests/test_jenkins_seed_limits_param_phase1.py`)",
            text,
        )
        self.assertIn("### Phase 1 artifacts (`LIMIT` follow-up)", text)
        self.assertIn("--structured", text)
        self.assertIn("INI", text)

    def test_adr_phase1_done(self) -> None:
        text = ADR011.read_text(encoding="utf-8")
        self.assertIn("list_cluster_limits", text)
        self.assertIn("**Done**", text)
        self.assertIn("test_jenkins_seed_limits_param_phase1.py", text)
        self.assertIn("[x] Phase 1 helper", text)
        self.assertTrue(
            "[ ] Phases 2–5 implementation" in text
            or "[ ] Phases 3–5 implementation" in text
            or "[ ] Phases 4–5 implementation" in text
            or "[ ] Phase 5 acceptance" in text
            or "[x] Phase 5 acceptance" in text,
            "ADR must leave later phases unchecked or mark Phase 5 done",
        )

    def test_changelog_phase1(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — LIMIT follow-up Phase 1", text)
        self.assertIn("test_jenkins_seed_limits_param_phase1.py", text)
        self.assertIn("list_cluster_limits", text)
        self.assertIn("collect_limits_for_cluster", text)

    def test_artifacts_present(self) -> None:
        self.assertTrue(HELPER.is_file(), HELPER)
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn("def collect_limits_for_cluster", helper)
        self.assertIn("def collect_limits_parts_for_cluster", helper)
        self.assertIn("def collect_limits_map", helper)
        self.assertIn("def ids_missing_from_limits_map", helper)
        self.assertIn("LimitsUnavailableError", helper)
        self.assertIn("extract_inventory_groups", helper)
        self.assertIn("extract_inventory_hostnames", helper)
        self.assertIn("--allow-empty", helper)
        self.assertIn("--structured", helper)

        self.assertTrue(UNIT.is_file(), UNIT)

        for rel in (
            "fixture/postgresql/hosts",
            "fixture/redis/hosts",
            "lab/alpha/hosts",
        ):
            path = FIXTURE / rel
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("all:", text)
            self.assertIn("children:", text)

        hosts_only = (FIXTURE / "fixture" / "hosts_only" / "hosts").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("all:", hosts_only)  # still INI for scanner coverage

        readme = FIXTURE_README.read_text(encoding="utf-8")
        self.assertIn("list_cluster_limits", readme)
        self.assertIn("hosts_only", readme)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("LIMIT` follow-up Phase 1", seed)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
