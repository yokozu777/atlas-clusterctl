"""Jenkins seed PHASES follow-up Phase 0: empty = plan SoT; cascade via ADR 010."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
HELPER = ROOT / "clusterctl" / "tools" / "list_cluster_phases.py"
ADR010 = ROOT / "docs" / "adr" / "010-jenkins-phases-active-choices.md"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
GATE = ROOT / "tests" / "test_jenkins_seed_phases_param_phase0.py"


class JenkinsSeedPhasesParamPhase0Test(unittest.TestCase):
    def test_contract_locked(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("## Follow-up: `PHASES` parameter (contract)", text)
        self.assertTrue(
            "**Phase 0 locked" in text
            or "CLUSTER_ID Phase 0–5 done" in text
            or "PHASES follow-up Phase 0–5 done" in text
            or "Phase 0–5 done" in text,
            "contract banner must mark Phase 0 semantics locked / complete",
        )
        self.assertIn("CLUSTER_ID Phase 0–5 done", text)
        self.assertIn("PHASES follow-up Phase 0–5 done", text)
        self.assertIn("Empty `PHASES`", text)
        self.assertIn("plan SoT", text)
        self.assertIn("### Map vs empty `PHASES`", text)
        self.assertIn("when:", text)
        self.assertIn("Cascade / Active Choices", text)
        self.assertIn("Out of scope", text)
        self.assertIn("Seed phases map (path B + C)", text)
        self.assertIn("TAGS` / `LIMIT`", text)
        self.assertIn("Unchanged", text)
        self.assertIn("UI SoT", text)
        self.assertIn("test_jenkins_seed_phases_param_phase0.py", text)
        self.assertIn(
            "[x] Empty `PHASES` ⇒ plan/run without `--phases` (plan SoT; may differ from YAML map)",
            text,
        )
        self.assertIn("ADR 010", text)
        self.assertIn(
            "[x] Path C initially deferred; **unlocked** by [ADR 010]",
            text,
        )
        self.assertIn("ADR 008", text)
        self.assertIn("ADR 009", text)
        self.assertIn("Phase 1", text)
        self.assertIn("Phase 2", text)
        self.assertIn("Phase 3", text)
        self.assertIn("Phase 5", text)
        # Must not require map ≡ plan in live checklist.
        self.assertNotIn("same phase count / names as a local", text)
        self.assertIn("### Seed map root (inventory-only)", text)
        self.assertIn("inventory-only", text.lower())
        self.assertIn("--product-clusters-root", text)
        self.assertIn("PRODUCT_CLUSTERS_ROOT", text)
        self.assertIn("path c unlocked", text.lower())

    def test_docs_linked(self) -> None:
        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("plan SoT", jenkins)
        self.assertIn("jenkins-seed.md#follow-up-phases-parameter-contract", jenkins)
        self.assertIn("when:", jenkins)
        self.assertIn("uno-choice", jenkins)
        self.assertIn("ADR 010", jenkins)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("follow-up-phases-parameter-contract", seed)
        self.assertIn("plan SoT", seed)
        self.assertIn("when:", seed)
        self.assertIn("Active Choices", seed)
        self.assertIn("ADR 010", seed)
        self.assertIn("Artifacts", seed)
        self.assertIn("inventory", seed.lower())
        self.assertIn("Remediation Phase D", seed)
        self.assertIn("Remediation Phase E", seed)

        self.assertTrue(ADR010.is_file(), ADR010)

    def test_helper_separates_map_from_empty_phases(self) -> None:
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn("plan SoT", helper)
        self.assertIn("when:", helper)
        self.assertNotIn(
            "Empty PHASES in deploy = this full catalog",
            helper,
        )

    def test_changelog_phase0(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — PHASES follow-up Phase 0", text)
        self.assertIn("test_jenkins_seed_phases_param_phase0.py", text)
        self.assertIn("empty deploy ``PHASES``", text)

    def test_deploy_runtime_empty_phases_omits_flag(self) -> None:
        """Phase 0 locks semantics already implemented in deploy samples."""
        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn('if [ -n "${PHASES:-}" ]; then', text, path.name)
            self.assertIn('plan --phases "${PHASES}"', text, path.name)
            # Empty branch: plan without --phases (plan SoT).
            self.assertIn('./cluster --cluster "${CLUSTER_ID}" plan\n', text, path.name)
            self.assertIn("params.PHASES", text, path.name)
            self.assertIn("plan SoT", text, path.name)
            self.assertIn("instanceof Collection", text, path.name)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
