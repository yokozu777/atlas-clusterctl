"""Jenkins seed LIMIT follow-up Phase 2: seed writes / archives limits map."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
CHANGELOG = ROOT / "CHANGELOG.md"
ADR011 = ROOT / "docs" / "adr" / "011-jenkins-limits-active-choices.md"
SEED_JF = ROOT / "examples" / "internal" / "seed" / "Jenkinsfile"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
HELPER = ROOT / "clusterctl" / "tools" / "list_cluster_limits.py"
GITIGNORE = ROOT / ".gitignore"
GATE = ROOT / "tests" / "test_jenkins_seed_limits_param_phase2.py"


class JenkinsSeedLimitsParamPhase2Test(unittest.TestCase):
    def test_contract_phase2_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertTrue(
            "Phase 0–2 done" in text
            or "LIMIT follow-up Phase 0–2 done" in text
            or "LIMIT follow-up Phase 0–3 done" in text
            or "LIMIT follow-up Phase 0–4 done" in text
            or "LIMIT follow-up Phase 0–5 done" in text
            or "Phase 0–3 done" in text
            or "Phase 0–4 done" in text
            or "Phase 0–5 done" in text
            or "Artifact on successful seed Build — **done**" in text,
            "contract banner / plan must mark Phase 2 complete",
        )
        self.assertIn(
            "Artifact on successful seed Build — **done**",
            text,
        )
        self.assertIn("cluster-limits.json", text)
        self.assertIn("CLUSTER_LIMITS_JSON", text)
        self.assertIn("--allow-empty", text)
        self.assertIn(
            "[x] Phase 2 — seed writes / archives `cluster-limits.json` "
            "(`tests/test_jenkins_seed_limits_param_phase2.py`)",
            text,
        )
        self.assertIn("test_jenkins_seed_limits_param_phase2.py", text)
        self.assertIn("### Phase 2 artifacts (`LIMIT` follow-up)", text)
        self.assertIn("Phase 3", text)

    def test_adr_phase2_done(self) -> None:
        text = ADR011.read_text(encoding="utf-8")
        self.assertIn("cluster-limits.json", text)
        self.assertIn("CLUSTER_LIMITS_JSON", text)
        self.assertIn("test_jenkins_seed_limits_param_phase2.py", text)
        self.assertIn("[x] Phase 2 seed map", text)
        self.assertTrue(
            "[ ] Phases 3–5 implementation" in text
            or "[ ] Phases 4–5 implementation" in text
            or "[ ] Phase 5 acceptance" in text
            or "[x] Phase 5 acceptance" in text,
            "ADR must leave later phases unchecked or mark Phase 5 done",
        )
        self.assertIn("**Done**", text)

    def test_changelog_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — LIMIT follow-up Phase 2", text)
        self.assertIn("test_jenkins_seed_limits_param_phase2.py", text)
        self.assertIn("cluster-limits.json", text)
        self.assertIn("CLUSTER_LIMITS_JSON", text)
        self.assertIn("--allow-empty", text)

    def test_seed_pipeline_writes_and_archives_map(self) -> None:
        text = SEED_JF.read_text(encoding="utf-8")
        self.assertIn("list_cluster_limits.py", text)
        self.assertIn("List cluster limits map", text)
        self.assertIn("list_cluster_limits", text)
        self.assertIn("--all", text)
        self.assertIn("--allow-empty", text)
        self.assertIn("--ui", text)
        self.assertIn("cluster-limits.json", text)
        self.assertIn("ids_missing_from_limits_map", text)
        self.assertIn("without limits catalog", text)
        self.assertIn("CLUSTER_LIMITS_JSON", text)
        self.assertIn("no --product-clusters-root", text)
        self.assertIn("allowEmptyArchive", text)
        self.assertIn("failed before writing", text)
        self.assertIn(
            "examples/internal/seed/cluster-ids.txt,"
            "examples/internal/seed/cluster-phases.json,"
            "examples/internal/seed/cluster-limits.json",
            text,
        )

    def test_dsl_binds_limits_map(self) -> None:
        """Phase 2 delivered map binding; Phase 3 wires Active Choices on top."""
        dsl = SEED_DSL.read_text(encoding="utf-8")
        self.assertIn("CLUSTER_LIMITS_JSON", dsl)
        self.assertIn("cluster-limits.json", dsl)
        self.assertIn("limitsReactiveScript", dsl)
        self.assertIn("limitsSwitchBody", dsl)
        # UI map value→label (or legacy flat→paired labels).
        self.assertTrue(
            "return [:]" in dsl or "return []" in dsl,
            "LIMIT reactive script must return empty map/list for unknown CLUSTER_ID",
        )
        # Seed-time parse only — form-render must stay switch-only (ADR 010 lesson).
        self.assertIn("JsonSlurper", dsl)
        self.assertIn("switch", dsl)
        has_string = bool(re.search(r"stringParam\(\s*'LIMIT'\s*,\s*''\s*,", dsl))
        has_reactive = bool(
            re.search(r"activeChoiceReactiveParam\(\s*'LIMIT'\s*\)\s*\{", dsl)
        )
        self.assertTrue(
            has_string or has_reactive,
            "LIMIT must be stringParam (Phase 2) or Active Choices (Phase 3+)",
        )

    def test_helper_allow_empty_and_missing(self) -> None:
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn("--allow-empty", helper)
        self.assertIn("allow_empty", helper)
        self.assertIn("def ids_missing_from_limits_map", helper)

    def test_gitignore_and_docs(self) -> None:
        gi = GITIGNORE.read_text(encoding="utf-8")
        self.assertIn("/examples/internal/seed/cluster-limits.json", gi)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("LIMIT` follow-up Phase 2", seed)
        self.assertIn("cluster-limits.json", seed)
        self.assertIn("CLUSTER_LIMITS_JSON", seed)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
