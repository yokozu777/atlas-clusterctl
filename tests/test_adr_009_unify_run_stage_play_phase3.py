"""Phase 3 gate: ADR 009 — Jenkins EXTRA_VARS + run --phases in Pipeline samples."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"


class Adr009UnifyRunStagePlayPhase3Test(unittest.TestCase):
    def test_adr_status_phase3(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("[x] Jenkins `EXTRA_VARS` + docs (Phase 3)", text)

    def test_adr_index_phase3(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("009-unify-run-stage-play.md", text)
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("Phase 3", text)
        self.assertIn("EXTRA_VARS", text)

    def test_jenkins_docs_extra_vars(self) -> None:
        text = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("EXTRA_VARS", text)
        self.assertIn("TAGS", text)
        self.assertIn("LIMIT", text)
        self.assertIn("provision_mode=destroy", text)
        self.assertIn("run --phases", text)
        self.assertIn("ADR 009", text)
        self.assertIn("no `eval`", text)  # jenkins.md EXTRA_VARS section
        self.assertIn("[1/4] atlas-compute-provision/provision", text)
        self.assertNotIn("[1/4] atlas-compute-provision/templates", text)

    def test_jenkinsfiles_extra_vars_and_run_phases(self) -> None:
        seed_dsl = (
            ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
        ).read_text(encoding="utf-8")
        self.assertIn("EXTRA_VARS", seed_dsl)
        self.assertIn("TAGS", seed_dsl)
        self.assertIn("LIMIT", seed_dsl)

        for path in (DOCKER_JF, LOCAL_JF):
            text = path.read_text(encoding="utf-8")
            self.assertIn("params.EXTRA_VARS", text, path.name)
            self.assertIn("params.TAGS", text, path.name)
            self.assertIn("params.LIMIT", text, path.name)
            self.assertIn("runClusterPhase", text, path.name)
            self.assertIn('run --phases "${PHASE_REF}"', text, path.name)
            self.assertIn('extra+=(--tags "${TAGS}")', text, path.name)
            self.assertIn('extra+=(--limit "${LIMIT}")', text, path.name)
            self.assertIn("bash -euo pipefail", text, path.name)
            self.assertIn('extra+=(-e "${tok}")', text, path.name)
            self.assertIn("do not eval EXTRA_VARS", text, path.name)
            self.assertIn("provision_mode=destroy", text, path.name)
            self.assertNotIn('stage "${PHASE_REF}"', text, path.name)
            self.assertNotIn("./cluster --cluster \"${CLUSTER_ID}\" stage", text, path.name)
            self.assertNotIn(
                "[1/4] atlas-compute-provision/templates",
                text,
                path.name,
            )
            self.assertIn(
                "atlas-compute-provision/provision",
                text,
                path.name,
            )


if __name__ == "__main__":
    unittest.main()
