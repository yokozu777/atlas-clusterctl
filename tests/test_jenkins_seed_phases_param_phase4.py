"""Jenkins seed PHASES follow-up Phase 4: path C unlocked — Active Choices."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
CHANGELOG = ROOT / "CHANGELOG.md"
ADR010 = ROOT / "docs" / "adr" / "010-jenkins-phases-active-choices.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
SEED_JF = ROOT / "examples" / "internal" / "seed" / "Jenkinsfile"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
GATE = ROOT / "tests" / "test_jenkins_seed_phases_param_phase4.py"


class JenkinsSeedPhasesParamPhase4Test(unittest.TestCase):
    def test_adr_010_accepted(self) -> None:
        self.assertTrue(ADR010.is_file(), ADR010)
        text = ADR010.read_text(encoding="utf-8")
        self.assertIn("ADR 010", text)
        self.assertIn("Accepted", text)
        self.assertIn("activeChoiceReactiveParam", text)
        self.assertIn("uno-choice", text)
        self.assertIn("CHECKBOX", text)
        self.assertNotIn("PT_CHECKBOX", text)
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("010-jenkins-phases-active-choices.md", index)

    def test_contract_phase4_unlocked(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("path c unlocked", text.lower())
        self.assertIn("ADR 010", text)
        self.assertIn("### Phase 4 artifacts", text)
        self.assertIn(
            "[x] Phase 4 — path C unlocked / ADR 010",
            text,
        )
        self.assertIn("test_jenkins_seed_phases_param_phase4.py", text)
        self.assertIn("Cascade / Active Choices", text)
        self.assertIn("**In scope**", text)
        self.assertIn("uno-choice", text)
        # Historical deferral must not remain the normative Phase 4 status.
        self.assertNotIn("**Deferred (locked)**", text)
        self.assertNotIn("Unlock later", text)

    def test_changelog_phase4_adr010(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("PHASES path C / ADR 010", text)
        self.assertIn("test_jenkins_seed_phases_param_phase4.py", text)
        self.assertIn("Active Choices", text)
        self.assertIn("uno-choice", text)

    def test_dsl_active_choices_cascade(self) -> None:
        dsl = SEED_DSL.read_text(encoding="utf-8")
        self.assertIn("activeChoiceReactiveParam('PHASES')", dsl)
        self.assertIn("referencedParameter('CLUSTER_ID')", dsl)
        self.assertIn("choiceType('CHECKBOX')", dsl)
        self.assertNotIn("PT_CHECKBOX", dsl)
        self.assertIn("CLUSTER_PHASES_JSON", dsl)
        self.assertIn("JsonSlurper", dsl)
        self.assertIn("ADR 010", dsl)
        self.assertIn("plan SoT", dsl)
        self.assertNotRegex(
            dsl,
            r"stringParam\(\s*'PHASES'\s*,\s*''\s*,",
            "PHASES must not remain stringParam after ADR 010",
        )
        self.assertNotRegex(
            dsl,
            r"choiceParam\(\s*'PHASES'",
            "PHASES must not be static choiceParam",
        )

    def test_seed_passes_phases_json(self) -> None:
        jf = SEED_JF.read_text(encoding="utf-8")
        self.assertIn("CLUSTER_PHASES_JSON", jf)
        self.assertIn("cluster-phases.json", jf)
        self.assertIn("ADR 010", jf)

    def test_deploy_envparam_joins_collection(self) -> None:
        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn("instanceof Collection", text, path.name)
            self.assertIn("join(',')", text, path.name)
            self.assertIn("ADR 010", text, path.name)

    def test_operator_docs_spell_cascade(self) -> None:
        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("uno-choice", jenkins)
        self.assertIn("ADR 010", jenkins)
        self.assertIn("checkboxes", jenkins.lower())

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("follow-up Phase 4", seed)
        self.assertIn("Active Choices", seed)
        self.assertIn("ADR 010", seed)
        self.assertIn("uno-choice", seed)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
