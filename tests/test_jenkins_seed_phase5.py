"""Jenkins seed Phase 5: offline acceptance (add leaf → seed artifact → UI/deploy contract)."""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from clusterctl.tools.list_deployable_clusters import (
    collect_deployable_cluster_ids,
    main as list_main,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
SEED_JF = ROOT / "examples" / "internal" / "seed" / "Jenkinsfile"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
FIXTURE = ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "clusters"
GATE = ROOT / "tests" / "test_jenkins_seed_phase5.py"

_PHASE_GATES = tuple(
    ROOT / "tests" / f"test_jenkins_seed_phase{n}.py" for n in range(0, 6)
)
_PARAMS_BLOCK = re.compile(r"(?m)^\s*parameters\s*\{")
_NEW_LEAF = "lab/acceptance"


def _write_leaf(clusters: Path, cluster_id: str) -> None:
    env, name = cluster_id.split("/", 1)
    leaf = clusters / env / name
    leaf.mkdir(parents=True, exist_ok=True)
    (leaf / "cluster.yaml").write_text(
        "schema_version: 2\nexecution:\n  mode: local\n",
        encoding="utf-8",
    )


class JenkinsSeedPhase5Test(unittest.TestCase):
    def test_contract_phase5_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Phase 0–5 done", text)
        self.assertIn("[x] Acceptance (Phase 5)", text)
        self.assertIn("Checklist complete — **done**", text)
        self.assertIn("## Phase 5 acceptance", text)
        self.assertIn("Offline proof", text)
        self.assertIn("| **Offline** | **Done**", text)
        self.assertIn("test_jenkins_seed_phase5.py", text)
        self.assertIn("add leaf", text.lower())
        # Live UI steps documented for operators (org controller).
        self.assertIn("Live controller", text)
        self.assertIn("org-local", text)

    def test_changelog_phase5(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — Phase 5", text)
        self.assertIn("test_jenkins_seed_phase5.py", text)
        self.assertIn("acceptance", text.lower())

    def test_all_phase_gates_present(self) -> None:
        for path in _PHASE_GATES:
            self.assertTrue(path.is_file(), path)

    def test_offline_acceptance_add_leaf_seed_deploy_chain(self) -> None:
        """Simulate: add leaf → scan (seed list) → ids artifact → DSL/UI → deploy bind.

        Mirrors operator acceptance without a live Jenkins controller.
        """
        self.assertTrue(FIXTURE.is_dir(), FIXTURE)
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            shutil.copytree(FIXTURE, clusters)

            before = collect_deployable_cluster_ids(clusters)
            self.assertNotIn(_NEW_LEAF, before)

            _write_leaf(clusters, _NEW_LEAF)
            after = collect_deployable_cluster_ids(clusters, prefer=_NEW_LEAF)
            self.assertIn(_NEW_LEAF, after)
            self.assertEqual(after[0], _NEW_LEAF)

            # Seed Pipeline writes one id per line (tee cluster-ids.txt).
            artifact = Path(tmp) / "cluster-ids.txt"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = list_main(
                    [
                        "--clusters-root",
                        str(clusters),
                        "--prefer",
                        _NEW_LEAF,
                    ]
                )
            self.assertEqual(rc, 0)
            artifact.write_text(buf.getvalue(), encoding="utf-8")
            self.assertTrue(artifact.stat().st_size > 0)
            seeded_ids = [
                ln.strip()
                for ln in artifact.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            self.assertEqual(seeded_ids, after)
            self.assertEqual(seeded_ids[0], _NEW_LEAF)
            self.assertIn(_NEW_LEAF, seeded_ids)

            # Job DSL refuses empty CLUSTER_IDS (contract).
            self.assertTrue(seeded_ids)

            dsl = SEED_DSL.read_text(encoding="utf-8")
            self.assertIn("choiceParam(", dsl)
            self.assertIn("'CLUSTER_ID'", dsl)
            self.assertIn("CLUSTER_IDS", dsl)
            # Full template preserved for deploy UI.
            for needle in ("TAGS", "LIMIT", "EXTRA_VARS", "PHASES"):
                self.assertIn(needle, dsl, needle)

            seed_jf = SEED_JF.read_text(encoding="utf-8")
            self.assertIn("jobDsl(", seed_jf)
            self.assertIn("CLUSTER_IDS", seed_jf)
            self.assertIn("empty deployable id list", seed_jf)
            self.assertNotIn("triggers {", seed_jf)
            self.assertNotIn("cron(", seed_jf)

            for path in (DOCKER_JF, LOCAL_JF):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(
                    _PARAMS_BLOCK.search(text),
                    f"{path.name}: parameters {{}} would reset UI choice",
                )
                self.assertIn("params.CLUSTER_ID", text, path.name)
                self.assertIn('CLUSTER_ID = "${envParam(params.CLUSTER_ID)}"', text, path.name)
                self.assertIn("CLUSTER_ID missing", text, path.name)
                # Deploy would bind seeded choice value into env for ./cluster.
                self.assertIn('./cluster --cluster "${CLUSTER_ID}"', text, path.name)

    def test_offline_acceptance_empty_scan_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            clusters.mkdir()
            err = io.StringIO()
            with redirect_stderr(err):
                rc = list_main(["--clusters-root", str(clusters)])
            self.assertEqual(rc, 1)
            self.assertEqual(collect_deployable_cluster_ids(clusters), [])

    def test_docs_acceptance_surfaces(self) -> None:
        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("[x] Phase 5", seed)
        self.assertIn("acceptance", seed.lower())
        self.assertIn("jenkins-seed.md", seed)

        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("Phase 0–5 done", jenkins)
        self.assertIn("jenkins-seed.md", jenkins)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
