"""Jenkins seed LIMIT follow-up Phase 3: Active Choices cascade for LIMIT."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
CHANGELOG = ROOT / "CHANGELOG.md"
ADR011 = ROOT / "docs" / "adr" / "011-jenkins-limits-active-choices.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
SEED_JF = ROOT / "examples" / "internal" / "seed" / "Jenkinsfile"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
GATE = ROOT / "tests" / "test_jenkins_seed_limits_param_phase3.py"


class JenkinsSeedLimitsParamPhase3Test(unittest.TestCase):
    def test_contract_phase3_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertTrue(
            "Phase 0–3 done" in text
            or "LIMIT follow-up Phase 0–3 done" in text
            or "LIMIT follow-up Phase 0–4 done" in text
            or "LIMIT follow-up Phase 0–5 done" in text
            or "Phase 0–4 done" in text
            or "Phase 0–5 done" in text
            or "Checkboxes refresh with `CLUSTER_ID` — **done**" in text,
            "contract banner / plan must mark Phase 3 complete",
        )
        self.assertIn(
            "Checkboxes refresh with `CLUSTER_ID` — **done**",
            text,
        )
        self.assertIn("activeChoiceReactiveParam('LIMIT')", text)
        self.assertIn("### Phase 3 artifacts (`LIMIT` follow-up)", text)
        self.assertIn(
            "[x] Phase 3 — reactive `LIMIT` checkboxes "
            "(`tests/test_jenkins_seed_limits_param_phase3.py`)",
            text,
        )
        self.assertIn("test_jenkins_seed_limits_param_phase3.py", text)
        self.assertIn("CHECKBOX", text)
        self.assertIn("referencedParameter", text)
        # Normative UI is Active Choices, not free-form string.
        self.assertIn("**UI shape (Phase 3+)**", text)
        self.assertIn("**In scope / delivered**", text)

    def test_adr_phase3_done(self) -> None:
        text = ADR011.read_text(encoding="utf-8")
        self.assertIn("Accepted", text)
        self.assertIn("activeChoiceReactiveParam('LIMIT')", text)
        self.assertIn("CHECKBOX", text)
        self.assertNotIn("PT_CHECKBOX", text)
        self.assertIn("test_jenkins_seed_limits_param_phase3.py", text)
        self.assertIn("[x] Phase 3 DSL UI", text)
        self.assertTrue(
            "[ ] Phases 4–5 implementation" in text
            or "[ ] Phases 3–5 implementation" in text
            or "[ ] Phase 5 acceptance" in text
            or "[x] Phase 5 acceptance" in text,
            "ADR must leave later phases unchecked or mark Phase 5 done",
        )
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("011-jenkins-limits-active-choices.md", index)
        self.assertTrue(
            "Phase 0–3" in index
            or "Phase 0–4" in index
            or "Phase 0–5" in index,
            "ADR index must mark LIMIT cascade progress through Phase 3+",
        )

    def test_changelog_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — LIMIT follow-up Phase 3", text)
        self.assertIn("test_jenkins_seed_limits_param_phase3.py", text)
        self.assertIn("activeChoiceReactiveParam", text)
        self.assertIn("CHECKBOX", text)
        self.assertIn("CLUSTER_LIMITS_JSON", text)

    def test_dsl_active_choices_cascade(self) -> None:
        dsl = SEED_DSL.read_text(encoding="utf-8")
        self.assertRegex(
            dsl,
            r"activeChoiceReactiveParam\(\s*'LIMIT'\s*\)\s*\{",
        )
        # Both PHASES and LIMIT reference CLUSTER_ID.
        self.assertGreaterEqual(
            len(re.findall(r"referencedParameter\(\s*'CLUSTER_ID'\s*\)", dsl)),
            2,
        )
        self.assertIn("choiceType('CHECKBOX')", dsl)
        self.assertNotIn("PT_CHECKBOX", dsl)
        self.assertIn("CLUSTER_LIMITS_JSON", dsl)
        self.assertIn("limitsReactiveScript", dsl)
        self.assertIn("JsonSlurper", dsl)
        self.assertIn("switch", dsl)
        self.assertIn("ADR 011", dsl)
        self.assertIn("omit --limit", dsl)
        self.assertNotRegex(
            dsl,
            r"stringParam\(\s*'LIMIT'\s*,\s*''\s*,",
            "LIMIT must not remain stringParam after Phase 3",
        )
        # Form-render script must not embed JsonSlurper (seed-time only).
        # Heuristic: reactive script bodies use switch/case, not parseText.
        self.assertIn("limitsSwitchBody", dsl)
        reactive_assign = dsl.split("def limitsReactiveScript", 1)[1]
        reactive_body = reactive_assign.split("if (!clusterctlUrl", 1)[0]
        self.assertNotIn("JsonSlurper", reactive_body)
        self.assertNotIn("parseText", reactive_body)
        self.assertIn("switch", reactive_body)

    def test_seed_passes_limits_json(self) -> None:
        jf = SEED_JF.read_text(encoding="utf-8")
        self.assertIn("CLUSTER_LIMITS_JSON", jf)
        self.assertIn("cluster-limits.json", jf)
        self.assertIn("ADR 011", jf)
        self.assertIn("LIMIT Active Choices", jf)

    def test_deploy_envparam_joins_collection(self) -> None:
        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn("instanceof Collection", text, path.name)
            self.assertIn("join(',')", text, path.name)
            self.assertIn("params.LIMIT", text, path.name)
            self.assertIn("ADR 010 / 011", text, path.name)
            self.assertIn('if [ -n "${LIMIT:-}" ]; then', text, path.name)
            self.assertIn('--limit "${LIMIT}"', text, path.name)

    def test_operator_docs_spell_cascade(self) -> None:
        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("uno-choice", jenkins)
        self.assertIn("ADR 011", jenkins)
        self.assertIn("checkboxes", jenkins.lower())
        self.assertIn("groups with nested host keys", jenkins.lower())
        # Keep hostname: display guidance in operator docs.
        self.assertIn("hostname:", jenkins.lower())

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("LIMIT` follow-up Phase 3", seed)
        self.assertIn("Active Choices", seed)
        self.assertIn("ADR 011", seed)
        self.assertIn("uno-choice", seed)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
