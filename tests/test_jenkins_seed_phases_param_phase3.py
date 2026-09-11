"""Jenkins seed PHASES follow-up Phase 3: seed writes / archives phases map."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_JF = ROOT / "examples" / "internal" / "seed" / "Jenkinsfile"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
HELPER = ROOT / "clusterctl" / "tools" / "list_cluster_phases.py"
GITIGNORE = ROOT / ".gitignore"
GATE = ROOT / "tests" / "test_jenkins_seed_phases_param_phase3.py"


class JenkinsSeedPhasesParamPhase3Test(unittest.TestCase):
    def test_contract_phase3_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertTrue(
            "Phase 1–3 done" in text
            or "Phase 4 deferred (locked)" in text
            or "Phase 4 deferred/locked" in text
            or "Phase 0–5 done" in text,
            "contract banner must mark Phase 3 complete",
        )
        self.assertIn(
            "Artifact on successful seed Build — **done**",
            text,
        )
        self.assertIn("cluster-phases.json", text)
        self.assertIn("--allow-empty", text)
        self.assertIn(
            "[x] Phase 3 — seed writes / archives `cluster-phases.json`",
            text,
        )
        self.assertIn("test_jenkins_seed_phases_param_phase3.py", text)
        self.assertIn("### Phase 3 artifacts", text)

    def test_changelog_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — PHASES follow-up Phase 3", text)
        self.assertIn("test_jenkins_seed_phases_param_phase3.py", text)
        self.assertIn("cluster-phases.json", text)
        self.assertIn("--allow-empty", text)

    def test_seed_pipeline_writes_and_archives_map(self) -> None:
        text = SEED_JF.read_text(encoding="utf-8")
        self.assertIn("list_cluster_phases.py", text)
        self.assertIn("List cluster phases map", text)
        self.assertIn("list_cluster_phases", text)
        self.assertIn("--all", text)
        self.assertIn("--allow-empty", text)
        self.assertIn("cluster-phases.json", text)
        self.assertIn("ids_missing_from_phases_map", text)
        self.assertIn("without phases:", text)
        self.assertIn("no --product-clusters-root", text)
        self.assertIn("allowEmptyArchive", text)
        self.assertIn("failed before writing", text)
        self.assertIn(
            "examples/internal/seed/cluster-ids.txt,examples/internal/seed/cluster-phases.json",
            text,
        )

    def test_helper_allow_empty_and_missing_helper(self) -> None:
        helper = HELPER.read_text(encoding="utf-8")
        self.assertIn("--allow-empty", helper)
        self.assertIn("allow_empty", helper)
        self.assertIn("def ids_missing_from_phases_map", helper)
        self.assertIn("except Exception as exc:", helper)
        self.assertIn("Seed Pipeline samples do not pass this", helper)
        self.assertIn("Error if used without --all", helper)

    def test_gitignore_and_docs(self) -> None:
        gi = GITIGNORE.read_text(encoding="utf-8")
        self.assertIn("/examples/internal/seed/cluster-phases.json", gi)

        dsl = SEED_DSL.read_text(encoding="utf-8")
        self.assertIn("cluster-phases.json", dsl)

        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("follow-up Phase 3", seed)
        self.assertIn("cluster-phases.json", seed)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
