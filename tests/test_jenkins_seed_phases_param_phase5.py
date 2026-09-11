"""Jenkins seed PHASES follow-up Phase 5: offline acceptance (empty PHASES + cascade)."""

from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from clusterctl.tools.list_cluster_phases import (
    collect_phases_for_cluster,
    collect_phases_map,
    main as phases_main,
)
from clusterctl.tools.list_deployable_clusters import collect_deployable_cluster_ids

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
GATE = ROOT / "tests" / "test_jenkins_seed_phases_param_phase5.py"

_PHASE_GATES = tuple(
    ROOT / "tests" / f"test_jenkins_seed_phases_param_phase{n}.py"
    for n in range(0, 6)
)
_PARAMS_BLOCK = re.compile(r"(?m)^\s*parameters\s*\{")
_NEW_LEAF = "lab/acceptance_phases"
_NEW_PHASES = ["provision", "init", "acceptance"]

_FIXTURE_PHASES = {
    "fixture/postgresql": ["provision", "init", "postgresql"],
    "fixture/redis": ["provision", "init", "redis"],
    "lab/alpha": ["provision", "init"],
}


def _write_leaf_with_phases(clusters: Path, cluster_id: str) -> None:
    env, name = cluster_id.split("/", 1)
    leaf = clusters / env / name
    leaf.mkdir(parents=True, exist_ok=True)
    (leaf / "cluster.yaml").write_text(
        "schema_version: 2\n"
        "execution:\n"
        "  mode: local\n"
        "phases:\n"
        "- provision: atlas-compute-provision/provision\n"
        "- init: atlas-node-foundation/init\n"
        "- acceptance: atlas-postgresql/cluster\n",
        encoding="utf-8",
    )


class JenkinsSeedPhasesParamPhase5Test(unittest.TestCase):
    def test_contract_phase5_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Phase 0–5 done", text)
        self.assertIn("Checklist complete — **done**", text)
        self.assertIn("### Phase 5 acceptance (`PHASES` follow-up)", text)
        self.assertIn('id="phase-5-acceptance-phases-follow-up"', text)
        self.assertIn("| **Offline** | **Done**", text)
        self.assertIn("Offline proof", text)
        self.assertIn("Live controller", text)
        self.assertIn("org-local", text)
        self.assertIn("test_jenkins_seed_phases_param_phase5.py", text)
        self.assertIn(
            "[x] Phase 5 — acceptance (`tests/test_jenkins_seed_phases_param_phase5.py`)",
            text,
        )
        self.assertIn("path c unlocked", text.lower())
        self.assertIn("ADR 010", text)
        self.assertIn("### Map vs empty `PHASES`", text)
        self.assertIn("**not** require plan", text)
        self.assertIn("plan.json", text)
        self.assertNotIn("same phase count / names as a local", text)
        self.assertIn("### Seed map root (inventory-only)", text)
        self.assertIn("inventory-only", text)
        self.assertIn("examples/internal/seed/cluster-phases.json", text)
        self.assertIn("activeChoiceReactiveParam", text)

    def test_changelog_phase5(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — PHASES follow-up Phase 5", text)
        self.assertIn("test_jenkins_seed_phases_param_phase5.py", text)
        self.assertIn("acceptance", text.lower())

    def test_all_phases_param_gates_present(self) -> None:
        for path in _PHASE_GATES:
            self.assertTrue(path.is_file(), path)

    def test_offline_fixture_map_matches_leaf_catalog(self) -> None:
        """Seed map artifact shape matches helper / leaf YAML short names."""
        self.assertTrue(FIXTURE.is_dir(), FIXTURE)
        mapping = collect_phases_map(FIXTURE)
        self.assertEqual(mapping, _FIXTURE_PHASES)
        self.assertNotIn("fixture/hosts_only", mapping)
        # Membership (ids) still includes hosts_only — map is catalog-only.
        ids = collect_deployable_cluster_ids(FIXTURE)
        self.assertIn("fixture/hosts_only", ids)

        out = io.StringIO()
        with redirect_stdout(out):
            rc = phases_main(["--clusters-root", str(FIXTURE), "--all"])
        self.assertEqual(rc, 0)
        artifact = json.loads(out.getvalue())
        self.assertEqual(artifact, mapping)
        # Per-leaf helper agrees with map entries.
        for cid, phases in mapping.items():
            self.assertEqual(collect_phases_for_cluster(FIXTURE, cid), phases)

    def test_offline_acceptance_add_leaf_map_and_deploy_contract(self) -> None:
        """Simulate: add leaf with phases: → map artifact → cascade + empty PHASES."""
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            shutil.copytree(FIXTURE, clusters)

            before = collect_phases_map(clusters)
            self.assertNotIn(_NEW_LEAF, before)

            _write_leaf_with_phases(clusters, _NEW_LEAF)
            after = collect_phases_map(clusters)
            self.assertIn(_NEW_LEAF, after)
            self.assertEqual(after[_NEW_LEAF], _NEW_PHASES)

            # Seed Pipeline writes JSON object (tee → cluster-phases.json).
            artifact = Path(tmp) / "cluster-phases.json"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = phases_main(
                    ["--clusters-root", str(clusters), "--all", "--allow-empty"]
                )
            self.assertEqual(rc, 0)
            artifact.write_text(buf.getvalue(), encoding="utf-8")
            seeded = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(seeded, after)
            self.assertEqual(seeded[_NEW_LEAF], _NEW_PHASES)

            # UI: Active Choices cascade (ADR 010); empty selection = plan SoT.
            dsl = SEED_DSL.read_text(encoding="utf-8")
            self.assertIn("activeChoiceReactiveParam('PHASES')", dsl)
            self.assertIn("referencedParameter('CLUSTER_ID')", dsl)
            self.assertIn("CLUSTER_PHASES_JSON", dsl)
            self.assertNotRegex(dsl, r"choiceParam\(\s*'PHASES'")

            seed_jf = SEED_JF.read_text(encoding="utf-8")
            self.assertIn("cluster-phases.json", seed_jf)
            self.assertIn("list_cluster_phases", seed_jf)
            self.assertIn("--allow-empty", seed_jf)
            self.assertIn("CLUSTER_PHASES_JSON", seed_jf)

            for path in (DOCKER_JF, LOCAL_JF):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(
                    _PARAMS_BLOCK.search(text),
                    f"{path.name}: parameters {{}} would reset seed UI",
                )
                self.assertIn("params.PHASES", text, path.name)
                self.assertIn('PHASES = "${envParam(params.PHASES)}"', text, path.name)
                self.assertIn("instanceof Collection", text, path.name)
                # Empty PHASES → plan without --phases (full leaf catalog).
                self.assertIn('if [ -n "${PHASES:-}" ]; then', text, path.name)
                self.assertIn('plan --phases "${PHASES}"', text, path.name)
                self.assertIn(
                    './cluster --cluster "${CLUSTER_ID}" plan\n',
                    text,
                    path.name,
                )

    def test_docs_acceptance_surfaces(self) -> None:
        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("follow-up Phase 5", seed)
        self.assertIn("acceptance", seed.lower())
        self.assertIn("follow-up-phases-parameter-contract", seed)
        self.assertIn("ADR 010", seed)

        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("PHASES follow-up", jenkins)
        self.assertIn(
            "jenkins-seed.md#follow-up-phases-parameter-contract",
            jenkins,
        )
        self.assertIn(
            "jenkins-seed.md#phase-5-acceptance-phases-follow-up",
            jenkins,
        )

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
