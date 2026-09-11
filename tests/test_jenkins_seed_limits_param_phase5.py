"""Jenkins seed LIMIT follow-up Phase 5: offline acceptance (empty LIMIT + cascade)."""

from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from clusterctl.tools.list_cluster_limits import (
    collect_limits_for_cluster,
    collect_limits_map,
    main as limits_main,
)
from clusterctl.tools.list_deployable_clusters import collect_deployable_cluster_ids

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
ADR011 = ROOT / "docs" / "adr" / "011-jenkins-limits-active-choices.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
SEED_JF = ROOT / "examples" / "internal" / "seed" / "Jenkinsfile"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
DOCKER_JF = ROOT / "examples" / "internal" / "Jenkinsfile"
LOCAL_JF = ROOT / "examples" / "internal" / "Jenkinsfile.local"
FIXTURE = ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "clusters"
GATE = ROOT / "tests" / "test_jenkins_seed_limits_param_phase5.py"

_PHASE_GATES = tuple(
    ROOT / "tests" / f"test_jenkins_seed_limits_param_phase{n}.py"
    for n in range(0, 6)
)
_PARAMS_BLOCK = re.compile(r"(?m)^\s*parameters\s*\{")
_NEW_LEAF = "lab/acceptance_limits"
_NEW_GROUPS = ["acceptance_group"]
_NEW_HOSTS = ["10.99.0.1", "10.99.0.2"]
_NEW_FLAT = [*_NEW_GROUPS, *_NEW_HOSTS]

_FIXTURE_FLAT = {
    "fixture/postgresql": [
        "pgsql_cluster",
        "pgsql_lbs",
        "10.20.0.1",
        "10.20.0.10",
        "10.20.0.2",
    ],
    "fixture/redis": [
        "redis_cluster_masters",
        "redis_proxies",
        "10.30.0.1",
        "10.30.0.5",
    ],
    "lab/alpha": ["alpha", "10.40.0.1", "10.40.0.2"],
}


def _write_leaf_with_hosts(clusters: Path, cluster_id: str) -> None:
    env, name = cluster_id.split("/", 1)
    leaf = clusters / env / name
    leaf.mkdir(parents=True, exist_ok=True)
    (leaf / "cluster.yaml").write_text(
        "schema_version: 2\n"
        "execution:\n"
        "  mode: local\n"
        "phases:\n"
        "- provision: atlas-compute-provision/provision\n",
        encoding="utf-8",
    )
    (leaf / "hosts").write_text(
        "all:\n"
        "  children:\n"
        "    acceptance_group:\n"
        "      hosts:\n"
        "        10.99.0.1: {}\n"
        "        10.99.0.2: {}\n",
        encoding="utf-8",
    )


class JenkinsSeedLimitsParamPhase5Test(unittest.TestCase):
    def test_contract_phase5_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("Phase 0–5 done", text)
        self.assertIn("LIMIT follow-up Phase 0–5 done", text)
        self.assertIn("Checklist complete — **done**", text)
        self.assertIn("### Phase 5 acceptance (`LIMIT` follow-up)", text)
        self.assertIn('id="phase-5-acceptance-limits-follow-up"', text)
        self.assertIn("| **Offline** | **Done**", text)
        self.assertIn("Offline proof", text)
        self.assertIn("Live controller", text)
        self.assertIn("org-local", text)
        self.assertIn("test_jenkins_seed_limits_param_phase5.py", text)
        self.assertIn(
            "[x] Phase 5 — acceptance (`tests/test_jenkins_seed_limits_param_phase5.py`)",
            text,
        )
        self.assertIn("ADR 011", text)
        self.assertIn("### Map vs empty `LIMIT`", text)
        self.assertIn("omit `--limit`", text)
        self.assertIn("### Seed map root (inventory-only)", text)
        self.assertIn("inventory-only", text)
        self.assertIn("examples/internal/seed/cluster-limits.json", text)
        self.assertIn("activeChoiceReactiveParam('LIMIT')", text)
        self.assertIn("host keys", text.lower())
        self.assertNotIn("Phase 5 acceptance (`LIMIT` follow-up) — stub", text)

    def test_adr_phase5_done(self) -> None:
        text = ADR011.read_text(encoding="utf-8")
        self.assertIn("Phase 0–5", text)
        self.assertIn("Accepted", text)
        self.assertIn("test_jenkins_seed_limits_param_phase5.py", text)
        self.assertIn("[x] Phase 5 acceptance", text)
        # No unchecked remaining implementation checklist items.
        self.assertNotIn("[ ] Phase 5", text)
        self.assertNotIn("[ ] Phases", text)
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("011-jenkins-limits-active-choices.md", index)
        self.assertIn("Phase 0–5", index)

    def test_changelog_phase5(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — LIMIT follow-up Phase 5", text)
        self.assertIn("test_jenkins_seed_limits_param_phase5.py", text)
        self.assertIn("acceptance", text.lower())
        self.assertIn("omit", text.lower())

    def test_all_limits_param_gates_present(self) -> None:
        for path in _PHASE_GATES:
            self.assertTrue(path.is_file(), path)

    def test_offline_fixture_map_matches_leaf_catalog(self) -> None:
        """Seed map artifact shape matches helper / leaf YAML groups+hosts."""
        self.assertTrue(FIXTURE.is_dir(), FIXTURE)
        mapping = collect_limits_map(FIXTURE)
        self.assertEqual(mapping, _FIXTURE_FLAT)
        self.assertNotIn("fixture/hosts_only", mapping)
        # Membership (ids) still includes hosts_only — map is catalog-only.
        ids = collect_deployable_cluster_ids(FIXTURE)
        self.assertIn("fixture/hosts_only", ids)

        out = io.StringIO()
        with redirect_stdout(out):
            rc = limits_main(["--clusters-root", str(FIXTURE), "--all"])
        self.assertEqual(rc, 0)
        artifact = json.loads(out.getvalue())
        self.assertEqual(artifact, mapping)
        for cid, names in mapping.items():
            self.assertEqual(collect_limits_for_cluster(FIXTURE, cid), names)
            # Groups precede hosts: first entries are non-IP-like group names for fixtures.
            groups_end = next(
                (i for i, n in enumerate(names) if n[0].isdigit()),
                len(names),
            )
            self.assertGreater(groups_end, 0, cid)

    def test_offline_acceptance_add_leaf_map_and_deploy_contract(self) -> None:
        """Simulate: add leaf with YAML hosts → map artifact → cascade + empty LIMIT."""
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            shutil.copytree(FIXTURE, clusters)

            before = collect_limits_map(clusters)
            self.assertNotIn(_NEW_LEAF, before)

            _write_leaf_with_hosts(clusters, _NEW_LEAF)
            after = collect_limits_map(clusters)
            self.assertIn(_NEW_LEAF, after)
            self.assertEqual(after[_NEW_LEAF], _NEW_FLAT)

            artifact = Path(tmp) / "cluster-limits.json"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = limits_main(
                    ["--clusters-root", str(clusters), "--all", "--allow-empty"]
                )
            self.assertEqual(rc, 0)
            artifact.write_text(buf.getvalue(), encoding="utf-8")
            seeded = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(seeded, after)
            self.assertEqual(seeded[_NEW_LEAF], _NEW_FLAT)

            # UI: Active Choices cascade (ADR 011); empty selection = omit --limit.
            dsl = SEED_DSL.read_text(encoding="utf-8")
            self.assertRegex(
                dsl,
                r"activeChoiceReactiveParam\(\s*'LIMIT'\s*\)\s*\{",
            )
            self.assertGreaterEqual(
                len(re.findall(r"referencedParameter\(\s*'CLUSTER_ID'\s*\)", dsl)),
                2,
            )
            self.assertIn("CLUSTER_LIMITS_JSON", dsl)
            self.assertIn("choiceType('CHECKBOX')", dsl)
            self.assertNotIn("PT_CHECKBOX", dsl)
            self.assertIn("return [:]", dsl)
            self.assertIn("value", dsl)
            self.assertIn("label", dsl)
            self.assertNotRegex(
                dsl,
                r"stringParam\(\s*'LIMIT'\s*,\s*''\s*,",
            )

            seed_jf = SEED_JF.read_text(encoding="utf-8")
            self.assertIn("cluster-limits.json", seed_jf)
            self.assertIn("list_cluster_limits", seed_jf)
            self.assertIn("--allow-empty", seed_jf)
            self.assertIn("--ui", seed_jf)
            self.assertIn("CLUSTER_LIMITS_JSON", seed_jf)

            # Seed UI path: ordered value→label entries (hierarchy for Active Choices).
            ui_map = collect_limits_map(clusters, ui=True)
            self.assertEqual(
                [e["value"] for e in ui_map[_NEW_LEAF]],
                _NEW_FLAT,
            )
            self.assertTrue(
                ui_map[_NEW_LEAF][0]["label"].startswith("▸ "),
            )
            self.assertIn("└", ui_map[_NEW_LEAF][1]["label"])

            for path in (DOCKER_JF, LOCAL_JF):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(
                    _PARAMS_BLOCK.search(text),
                    f"{path.name}: parameters {{}} would reset seed UI",
                )
                self.assertIn("params.LIMIT", text, path.name)
                self.assertIn('LIMIT = "${envParam(params.LIMIT)}"', text, path.name)
                self.assertIn("instanceof Collection", text, path.name)
                # Empty LIMIT → Run without --limit.
                self.assertIn('if [ -n "${LIMIT:-}" ]; then', text, path.name)
                self.assertIn('--limit "${LIMIT}"', text, path.name)

    def test_docs_acceptance_surfaces(self) -> None:
        seed = SEED_README.read_text(encoding="utf-8")
        self.assertIn("LIMIT` follow-up Phase 5", seed)
        self.assertIn("acceptance", seed.lower())
        self.assertIn("follow-up-limits-parameter-contract", seed)
        self.assertIn("phase-5-acceptance-limits-follow-up", seed)
        self.assertIn("ADR 011", seed)

        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 011", jenkins)
        self.assertIn(
            "jenkins-seed.md#follow-up-limits-parameter-contract",
            jenkins,
        )
        self.assertIn(
            "jenkins-seed.md#phase-5-acceptance-limits-follow-up",
            jenkins,
        )
        self.assertIn("Phase 0–5", jenkins)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
