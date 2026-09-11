"""Unit tests for ``clusterctl.tools.list_deployable_clusters`` (Jenkins seed scanner)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from clusterctl.tools.list_deployable_clusters import (
    collect_deployable_cluster_ids,
    main,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CLUSTERS = (
    ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "clusters"
)

# Committed fixture expectations (policy / _template / empty omitted).
_FIXTURE_DEPLOYABLE = (
    "fixture/hosts_only",
    "fixture/postgresql",
    "fixture/redis",
    "lab/alpha",
)
_FIXTURE_EXCLUDED = (
    "fixture/default",
    "default/default",
    "_template/ignored",
    "fixture/broken_empty",
)


class CollectDeployableClusterIdsTest(unittest.TestCase):
    def test_fixture_inventory_membership(self) -> None:
        self.assertTrue(FIXTURE_CLUSTERS.is_dir(), FIXTURE_CLUSTERS)
        ids = collect_deployable_cluster_ids(FIXTURE_CLUSTERS)
        self.assertEqual(ids, list(_FIXTURE_DEPLOYABLE))
        for excluded in _FIXTURE_EXCLUDED:
            self.assertNotIn(excluded, ids, excluded)

    def test_prefer_moves_known_id_first(self) -> None:
        ids = collect_deployable_cluster_ids(
            FIXTURE_CLUSTERS,
            prefer="lab/alpha",
        )
        self.assertEqual(ids[0], "lab/alpha")
        self.assertEqual(sorted(ids), sorted(_FIXTURE_DEPLOYABLE))

    def test_prefer_unknown_ignored(self) -> None:
        ids = collect_deployable_cluster_ids(
            FIXTURE_CLUSTERS,
            prefer="missing/leaf",
        )
        self.assertEqual(ids, list(_FIXTURE_DEPLOYABLE))

    def test_prefer_blank_noop(self) -> None:
        ids = collect_deployable_cluster_ids(FIXTURE_CLUSTERS, prefer="  ")
        self.assertEqual(ids, list(_FIXTURE_DEPLOYABLE))

    def test_missing_root_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            with self.assertRaises(FileNotFoundError) as ctx:
                collect_deployable_cluster_ids(missing)
            self.assertIn("not a directory", str(ctx.exception))

    def test_empty_clusters_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            clusters.mkdir()
            self.assertEqual(collect_deployable_cluster_ids(clusters), [])


class ListDeployableClustersCliTest(unittest.TestCase):
    def test_cli_lines_and_json(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--clusters-root", str(FIXTURE_CLUSTERS)])
        self.assertEqual(rc, 0)
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        self.assertEqual(lines, list(_FIXTURE_DEPLOYABLE))

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--prefer",
                    "fixture/redis",
                    "--json",
                ]
            )
        self.assertEqual(rc, 0)
        ids = json.loads(buf.getvalue())
        self.assertEqual(ids[0], "fixture/redis")
        self.assertEqual(sorted(ids), sorted(_FIXTURE_DEPLOYABLE))

    def test_cli_empty_exit_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            clusters.mkdir()
            err = io.StringIO()
            with redirect_stderr(err):
                rc = main(["--clusters-root", str(clusters)])
            self.assertEqual(rc, 1)
            self.assertIn("no deployable", err.getvalue())

    def test_cli_missing_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            err = io.StringIO()
            with redirect_stderr(err):
                rc = main(["--clusters-root", str(missing)])
            self.assertEqual(rc, 2)
            self.assertIn("not a directory", err.getvalue())

    def test_module_entrypoint_subprocess(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "clusterctl.tools.list_deployable_clusters",
                "--clusters-root",
                str(FIXTURE_CLUSTERS),
                "--json",
            ],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), list(_FIXTURE_DEPLOYABLE))


if __name__ == "__main__":
    unittest.main()
