"""Unit tests for ``clusterctl.tools.list_cluster_phases`` (Jenkins seed path B)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from clusterctl.tools.list_cluster_phases import (
    PhasesUnavailableError,
    collect_phases_for_cluster,
    collect_phases_map,
    ids_missing_from_phases_map,
    main,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CLUSTERS = (
    ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "clusters"
)

_FIXTURE_PHASES = {
    "fixture/postgresql": ["provision", "init", "postgresql"],
    "fixture/redis": ["provision", "init", "redis"],
    "lab/alpha": ["provision", "init"],
}
_FIXTURE_REFS_PG = [
    "atlas-compute-provision/provision",
    "atlas-node-foundation/init",
    "atlas-postgresql/cluster",
]


class CollectPhasesForClusterTest(unittest.TestCase):
    def test_fixture_short_names(self) -> None:
        for cid, expected in _FIXTURE_PHASES.items():
            with self.subTest(cid):
                self.assertEqual(
                    collect_phases_for_cluster(FIXTURE_CLUSTERS, cid),
                    expected,
                )

    def test_fixture_refs(self) -> None:
        self.assertEqual(
            collect_phases_for_cluster(
                FIXTURE_CLUSTERS,
                "fixture/postgresql",
                short_names=False,
            ),
            _FIXTURE_REFS_PG,
        )

    def test_unknown_or_phaseless_unavailable(self) -> None:
        # Unknown id still cascades org/env policy stubs → phases None.
        with self.assertRaises(PhasesUnavailableError):
            collect_phases_for_cluster(FIXTURE_CLUSTERS, "missing/leaf")
        with self.assertRaises(PhasesUnavailableError):
            collect_phases_for_cluster(FIXTURE_CLUSTERS, "fixture/hosts_only")

    def test_missing_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            with self.assertRaises(FileNotFoundError):
                collect_phases_for_cluster(missing, "fixture/postgresql")

    def test_blank_cluster_id(self) -> None:
        with self.assertRaises(ValueError):
            collect_phases_for_cluster(FIXTURE_CLUSTERS, "  ")


class CollectPhasesMapTest(unittest.TestCase):
    def test_fixture_map_omits_hosts_only(self) -> None:
        mapping = collect_phases_map(FIXTURE_CLUSTERS)
        self.assertEqual(mapping, _FIXTURE_PHASES)
        self.assertNotIn("fixture/hosts_only", mapping)

    def test_explicit_ids(self) -> None:
        mapping = collect_phases_map(
            FIXTURE_CLUSTERS,
            cluster_ids=["fixture/postgresql", "fixture/hosts_only"],
        )
        self.assertEqual(list(mapping.keys()), ["fixture/postgresql"])
        self.assertEqual(mapping["fixture/postgresql"], _FIXTURE_PHASES["fixture/postgresql"])

    def test_ids_missing_from_phases_map_preserves_order(self) -> None:
        mapping = collect_phases_map(FIXTURE_CLUSTERS)
        from clusterctl.tools.list_deployable_clusters import (
            collect_deployable_cluster_ids,
        )

        ids = collect_deployable_cluster_ids(FIXTURE_CLUSTERS)
        missing = ids_missing_from_phases_map(ids, mapping)
        self.assertEqual(missing, ["fixture/hosts_only"])
        self.assertEqual(
            ids_missing_from_phases_map(
                ["fixture/postgresql", "fixture/hosts_only", "lab/alpha"],
                mapping,
            ),
            ["fixture/hosts_only"],
        )


class ListClusterPhasesCliTest(unittest.TestCase):
    def test_cli_lines_and_json(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--cluster-id",
                    "lab/alpha",
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().splitlines(), ["provision", "init"])

        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--cluster-id",
                    "lab/alpha",
                    "--json",
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue()), ["provision", "init"])

    def test_cli_refs(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--cluster-id",
                    "fixture/postgresql",
                    "--refs",
                    "--json",
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue()), _FIXTURE_REFS_PG)

    def test_cli_all_map(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["--clusters-root", str(FIXTURE_CLUSTERS), "--all"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue()), _FIXTURE_PHASES)

    def test_cli_all_empty_map_exit_1_without_allow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "clusters"
            # Deployable leaf without phases: → empty collect_phases_map.
            leaf = root / "fixture" / "hosts_only"
            leaf.mkdir(parents=True)
            (leaf / "hosts").write_text("localhost\n", encoding="utf-8")
            (leaf / "cluster.yaml").write_text("{}\n", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                rc = main(["--clusters-root", str(root), "--all"])
            self.assertEqual(rc, 1)
            self.assertIn("no deployable leaves with phases:", err.getvalue())

            out = io.StringIO()
            with redirect_stdout(out):
                rc = main(
                    ["--clusters-root", str(root), "--all", "--allow-empty"]
                )
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out.getvalue()), {})

    def test_cli_hosts_only_exit_1(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--cluster-id",
                    "fixture/hosts_only",
                ]
            )
        self.assertEqual(rc, 1)
        self.assertIn("no phases:", err.getvalue())

    def test_cli_missing_id_exit_2(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(["--clusters-root", str(FIXTURE_CLUSTERS)])
        self.assertEqual(rc, 2)
        self.assertIn("--cluster-id", err.getvalue())

    def test_cli_missing_root_exit_2(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS / "nope"),
                    "--cluster-id",
                    "fixture/postgresql",
                ]
            )
        self.assertEqual(rc, 2)

    def test_cli_allow_empty_requires_all(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--cluster-id",
                    "lab/alpha",
                    "--allow-empty",
                ]
            )
        self.assertEqual(rc, 2)
        self.assertIn("--allow-empty requires --all", err.getvalue())

    def test_module_entrypoint_subprocess(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "clusterctl.tools.list_cluster_phases",
                "--clusters-root",
                str(FIXTURE_CLUSTERS),
                "--cluster-id",
                "lab/alpha",
                "--json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), ["provision", "init"])

    def test_cli_corrupt_yaml_clean_error_no_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "clusters"
            leaf = root / "fixture" / "bad"
            leaf.mkdir(parents=True)
            (leaf / "hosts").write_text("localhost\n", encoding="utf-8")
            (leaf / "cluster.yaml").write_text(":\n  bad\n", encoding="utf-8")
            err = io.StringIO()
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = main(["--clusters-root", str(root), "--all", "--allow-empty"])
            self.assertEqual(rc, 2)
            self.assertEqual(out.getvalue(), "")
            err_text = err.getvalue()
            self.assertTrue(err_text.startswith("error:"), err_text)
            self.assertNotIn("Traceback", err_text)
            self.assertNotIn("yaml.parser.ParserError", err_text)


if __name__ == "__main__":
    unittest.main()
