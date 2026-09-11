"""Jenkins seed PHASES follow-up Phase 1: DSL + docs spell out empty = plan SoT."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
INTERNAL_README = ROOT / "examples" / "internal" / "README.md"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
GATE = ROOT / "tests" / "test_jenkins_seed_phases_param_phase1.py"


def _phases_description(dsl: str) -> str:
    """Return PHASES Active Choices description (Job DSL may concatenate strings)."""
    m = re.search(
        r"activeChoiceReactiveParam\(\s*'PHASES'\s*\)\s*\{(.*?)\n\s*filterable",
        dsl,
        re.DOTALL,
    )
    if not m:
        raise AssertionError("PHASES activeChoiceReactiveParam block not found")
    block = m.group(1)
    dm = re.search(
        r"description\(\s*((?:'[^']*'\s*\+\s*)*'[^']*')\s*\)",
        block,
        re.DOTALL,
    )
    if not dm:
        raise AssertionError("PHASES description() not found in Active Choices block")
    parts = re.findall(r"'([^']*)'", dm.group(1))
    return "".join(parts)


class JenkinsSeedPhasesParamPhase1Test(unittest.TestCase):
    def test_contract_phase1_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertTrue(
            "Phase 1 done" in text
            or "Phase 1–2 done" in text
            or "Phase 1–3 done" in text
            or "path c unlocked" in text.lower()
            or "Phase 0–5 done" in text,
            "contract banner must mark Phase 1 complete",
        )
        self.assertIn("Param description / jenkins.md crisp — **done**", text)
        self.assertIn(
            "[x] Phase 1 — DSL + operator docs empty = all",
            text,
        )
        self.assertIn("test_jenkins_seed_phases_param_phase1.py", text)
        self.assertIn("### Phase 1 artifacts", text)

    def test_changelog_phase1(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — PHASES follow-up Phase 1", text)
        self.assertIn("test_jenkins_seed_phases_param_phase1.py", text)
        self.assertIn("empty = all", text.lower())

    def test_dsl_phases_description_empty_means_plan_sot(self) -> None:
        dsl = SEED_DSL.read_text(encoding="utf-8")
        desc = _phases_description(dsl)
        self.assertIn("plan/run without --phases", desc)
        self.assertIn("plan SoT", desc)
        self.assertIn("when:", desc)
        self.assertIn("TAGS/LIMIT", desc)
        self.assertIn("single NAME", desc)
        self.assertIn("ADR 010", desc)
        self.assertIn("Active Choices", desc)
        self.assertIn("activeChoiceReactiveParam('PHASES')", dsl)

    def test_operator_docs_crisp(self) -> None:
        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("plan SoT", jenkins)
        self.assertIn("when:", jenkins)
        self.assertIn("follow-up-phases-parameter-contract", jenkins)

        internal = INTERNAL_README.read_text(encoding="utf-8")
        self.assertIn("plan SoT without `--phases`", internal)
        self.assertIn("follow-up-phases-parameter-contract", internal)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("follow-up Phase 1", seed)
        self.assertIn("plan sot", seed.lower())

    def test_deploy_plan_documents_empty_contract(self) -> None:
        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn("Empty PHASES", text, path.name)
            self.assertIn("plan SoT", text, path.name)
            self.assertIn("jenkins-seed.md", text, path.name)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
