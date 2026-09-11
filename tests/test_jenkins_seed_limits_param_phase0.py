"""Jenkins seed LIMIT follow-up Phase 0: empty omit --limit; cascade via ADR 011."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
ADR011 = ROOT / "docs" / "adr" / "011-jenkins-limits-active-choices.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
ADR010 = ROOT / "docs" / "adr" / "010-jenkins-phases-active-choices.md"
INVENTORY = ROOT / "clusterctl" / "inventory.py"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
GATE = ROOT / "tests" / "test_jenkins_seed_limits_param_phase0.py"


class JenkinsSeedLimitsParamPhase0Test(unittest.TestCase):
    def test_adr_011_phase0_accepted(self) -> None:
        self.assertTrue(ADR011.is_file(), ADR011)
        text = ADR011.read_text(encoding="utf-8")
        self.assertIn("ADR 011", text)
        self.assertIn("Accepted", text)
        self.assertIn("Phase 0", text)
        self.assertIn("activeChoiceReactiveParam('LIMIT')", text)
        self.assertIn("CHECKBOX", text)
        self.assertTrue(
            "groups first" in text.lower()
            or "group then its hosts" in text.lower()
            or "hierarchical" in text.lower(),
            "ADR must lock flat groups-first and/or hierarchical UI list shape",
        )
        self.assertIn("extract_inventory_hostnames", text)
        self.assertIn("extract_inventory_groups", text)
        self.assertIn("JsonSlurper", text)
        self.assertIn("switch", text.lower())
        self.assertIn("ADR 009", text)
        self.assertIn("ADR 010", text)
        # Remaining work was Phase 5; when complete, ADR has no unchecked phases.
        self.assertTrue(
            "[ ] Phases 1–5 implementation" in text
            or "[ ] Phases 2–5 implementation" in text
            or "[ ] Phases 3–5 implementation" in text
            or "[ ] Phases 4–5 implementation" in text
            or "[ ] Phase 5 acceptance" in text
            or "[x] Phase 5 acceptance" in text,
            "ADR must track remaining or completed Phase 5",
        )
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("011-jenkins-limits-active-choices.md", index)
        # Sibling ADR points at LIMIT exception.
        adr010 = ADR010.read_text(encoding="utf-8")
        self.assertIn("ADR 011", adr010)

    def test_contract_phase0_locked(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("## Follow-up: `LIMIT` parameter (contract)", text)
        self.assertTrue(
            "LIMIT follow-up Phase 0 locked" in text
            or "LIMIT follow-up Phase 0–1 done" in text
            or "LIMIT follow-up Phase 0–2 done" in text
            or "LIMIT follow-up Phase 0–3 done" in text
            or "LIMIT follow-up Phase 0–5 done" in text
            or "Phase 0–1 done" in text
            or "Phase 0–2 done" in text
            or "Phase 0–3 done" in text
            or "Phase 0–4 done" in text
            or "Phase 0–5 done" in text,
            "contract banner must mark LIMIT Phase 0 locked / Phase 0–N done",
        )
        self.assertIn('id="follow-up-limits-parameter-contract"', text)
        self.assertIn("ADR 011", text)
        self.assertIn("Empty `LIMIT`", text)
        self.assertIn("omit", text.lower())
        self.assertIn("### Map vs empty `LIMIT`", text)
        self.assertTrue(
            "groups first" in text.lower()
            or "group then its hosts" in text.lower()
            or "hierarchical" in text.lower(),
            "contract must lock flat groups-first and/or hierarchical UI list shape",
        )
        self.assertIn("host keys", text.lower())
        self.assertIn("extract_inventory_hostnames", text)
        self.assertIn("extract_inventory_groups", text)
        self.assertIn("Phase 3", text)
        self.assertIn("Out of scope", text)
        self.assertIn("JsonSlurper", text)
        self.assertIn("switch", text.lower())
        self.assertIn("ADR 009", text)
        self.assertIn("UI SoT", text)
        self.assertIn("test_jenkins_seed_limits_param_phase0.py", text)
        # Historical stringParam mention may remain in Phase 0 artifacts table.
        self.assertTrue(
            "stringParam('LIMIT'" in text
            or "activeChoiceReactiveParam('LIMIT')" in text,
            "contract must describe LIMIT UI shape (string historical or Active Choices)",
        )
        self.assertIn(
            "[x] Empty `LIMIT` ⇒ omit `--limit`",
            text,
        )
        self.assertIn(
            "[x] Phase 0 gate exists (`tests/test_jenkins_seed_limits_param_phase0.py`)",
            text,
        )
        self.assertIn("### Phase 0 artifacts (`LIMIT` follow-up)", text)
        self.assertIn('id="phase-5-acceptance-limits-follow-up"', text)
        # Header points at LIMIT track.
        self.assertIn("follow-up-limits-parameter-contract", text)

    def test_inventory_primitives_exist(self) -> None:
        """Phase 0 locks SoT on existing extractors (helper comes in Phase 1)."""
        inv = INVENTORY.read_text(encoding="utf-8")
        self.assertIn("def extract_inventory_hostnames", inv)
        self.assertIn("def extract_inventory_groups", inv)

    def test_dsl_limit_cascade_or_string_until_phase3(self) -> None:
        """Phase 0 locked string UI; Phase 3+ wires Active Choices."""
        dsl = SEED_DSL.read_text(encoding="utf-8")
        has_string = re.search(r"stringParam\(\s*'LIMIT'\s*,\s*''\s*,", dsl)
        has_reactive = re.search(
            r"activeChoiceReactiveParam\(\s*'LIMIT'\s*\)\s*\{", dsl
        )
        self.assertTrue(
            has_string or has_reactive,
            "LIMIT must be stringParam (pre-Phase 3) or Active Choices (Phase 3+)",
        )
        if has_reactive:
            self.assertIn("choiceType('CHECKBOX')", dsl)
            self.assertIn("referencedParameter('CLUSTER_ID')", dsl)
            self.assertNotIn("PT_CHECKBOX", dsl)
            self.assertIsNone(
                has_string,
                "LIMIT must not keep stringParam after Active Choices ships",
            )
        self.assertIn("ADR 011", dsl)
        self.assertIn("omit --limit", dsl)

    def test_deploy_runtime_empty_limit_omits_flag(self) -> None:
        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn("params.LIMIT", text, path.name)
            # Selective run path: only pass --limit when LIMIT non-empty.
            self.assertIn('if [ -n "${LIMIT:-}" ]; then', text, path.name)
            self.assertIn('--limit "${LIMIT}"', text, path.name)

    def test_docs_linked(self) -> None:
        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("follow-up-limits-parameter-contract", jenkins)
        self.assertIn("ADR 011", jenkins)
        self.assertIn("omit `--limit`", jenkins)
        self.assertIn("host key", jenkins.lower())

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("follow-up-limits-parameter-contract", seed)
        self.assertIn("ADR 011", seed)
        self.assertIn("LIMIT` follow-up Phase 0", seed)

    def test_changelog_phase0(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — LIMIT follow-up Phase 0", text)
        self.assertIn("test_jenkins_seed_limits_param_phase0.py", text)
        self.assertIn("ADR 011", text)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
