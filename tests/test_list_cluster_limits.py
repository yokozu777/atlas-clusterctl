"""Unit tests for ``clusterctl.tools.list_cluster_limits`` (Jenkins seed LIMIT Phase 1)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from clusterctl.tools.list_cluster_limits import (
    LimitsUnavailableError,
    collect_limits_for_cluster,
    collect_limits_map,
    collect_limits_parts_for_cluster,
    collect_limits_ui_entries_for_cluster,
    collect_limits_ui_for_cluster,
    format_host_limit_label,
    ids_missing_from_limits_map,
    main,
)
from clusterctl.tools.list_deployable_clusters import collect_deployable_cluster_ids

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CLUSTERS = (
    ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "clusters"
)

_FIXTURE_PARTS = {
    "fixture/postgresql": (
        ["pgsql_cluster", "pgsql_lbs"],
        ["10.20.0.1", "10.20.0.10", "10.20.0.2"],
    ),
    "fixture/redis": (
        ["redis_cluster_masters", "redis_proxies"],
        ["10.30.0.1", "10.30.0.5"],
    ),
    "lab/alpha": (
        ["alpha"],
        ["10.40.0.1", "10.40.0.2"],
    ),
}
_FIXTURE_FLAT = {
    cid: [*groups, *hosts] for cid, (groups, hosts) in _FIXTURE_PARTS.items()
}


class CollectLimitsForClusterTest(unittest.TestCase):
    def test_fixture_parts_and_flat(self) -> None:
        for cid, (groups, hosts) in _FIXTURE_PARTS.items():
            with self.subTest(cid):
                self.assertEqual(
                    collect_limits_parts_for_cluster(FIXTURE_CLUSTERS, cid),
                    (groups, hosts),
                )
                self.assertEqual(
                    collect_limits_for_cluster(FIXTURE_CLUSTERS, cid),
                    [*groups, *hosts],
                )
                # Groups precede hosts in the flat catalog.
                flat = collect_limits_for_cluster(FIXTURE_CLUSTERS, cid)
                self.assertEqual(flat[: len(groups)], groups)
                self.assertEqual(flat[len(groups) :], hosts)

    def test_ini_hosts_only_unavailable(self) -> None:
        # Deployable scanner leaf; INI hosts is not a YAML mapping → unavailable.
        with self.assertRaises(LimitsUnavailableError):
            collect_limits_for_cluster(FIXTURE_CLUSTERS, "fixture/hosts_only")

    def test_missing_leaf_unavailable(self) -> None:
        with self.assertRaises(LimitsUnavailableError):
            collect_limits_for_cluster(FIXTURE_CLUSTERS, "missing/leaf")

    def test_missing_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            with self.assertRaises(FileNotFoundError):
                collect_limits_for_cluster(missing, "fixture/postgresql")

    def test_blank_cluster_id(self) -> None:
        with self.assertRaises(ValueError):
            collect_limits_for_cluster(FIXTURE_CLUSTERS, "  ")

    def test_host_key_collision_listed_once_under_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            leaf = clusters / "lab" / "collide"
            leaf.mkdir(parents=True)
            (leaf / "cluster.yaml").write_text(
                "schema_version: 2\nexecution:\n  mode: local\n",
                encoding="utf-8",
            )
            # Group name equals a host key under another group — host list drops dup.
            (leaf / "hosts").write_text(
                "all:\n"
                "  children:\n"
                "    shared:\n"
                "      hosts:\n"
                "        shared: {}\n"
                "        10.0.0.9: {}\n",
                encoding="utf-8",
            )
            groups, hosts = collect_limits_parts_for_cluster(clusters, "lab/collide")
            self.assertEqual(groups, ["shared"])
            self.assertEqual(hosts, ["10.0.0.9"])
            self.assertEqual(
                collect_limits_for_cluster(clusters, "lab/collide"),
                ["shared", "10.0.0.9"],
            )


class CollectLimitsMapTest(unittest.TestCase):
    def test_fixture_map_omits_hosts_only(self) -> None:
        mapping = collect_limits_map(FIXTURE_CLUSTERS)
        self.assertEqual(mapping, _FIXTURE_FLAT)
        self.assertNotIn("fixture/hosts_only", mapping)

    def test_structured_map(self) -> None:
        mapping = collect_limits_map(FIXTURE_CLUSTERS, structured=True)
        self.assertEqual(
            mapping["fixture/postgresql"],
            {
                "groups": _FIXTURE_PARTS["fixture/postgresql"][0],
                "hosts": _FIXTURE_PARTS["fixture/postgresql"][1],
            },
        )

    def test_explicit_ids(self) -> None:
        mapping = collect_limits_map(
            FIXTURE_CLUSTERS,
            cluster_ids=["fixture/postgresql", "fixture/hosts_only"],
        )
        self.assertEqual(list(mapping.keys()), ["fixture/postgresql"])
        self.assertEqual(mapping["fixture/postgresql"], _FIXTURE_FLAT["fixture/postgresql"])

    def test_ids_missing_from_limits_map_preserves_order(self) -> None:
        mapping = collect_limits_map(FIXTURE_CLUSTERS)
        ids = collect_deployable_cluster_ids(FIXTURE_CLUSTERS)
        missing = ids_missing_from_limits_map(ids, mapping)
        self.assertEqual(missing, ["fixture/hosts_only"])
        self.assertEqual(
            ids_missing_from_limits_map(
                ["fixture/postgresql", "fixture/hosts_only", "lab/alpha"],
                mapping,
            ),
            ["fixture/hosts_only"],
        )

    def test_ui_hierarchy_hosts_nested_under_groups(self) -> None:
        ui = collect_limits_ui_for_cluster(FIXTURE_CLUSTERS, "fixture/postgresql")
        keys = list(ui.keys())
        # Group then its hosts, then next group…
        self.assertEqual(keys[0], "pgsql_cluster")
        self.assertTrue(ui["pgsql_cluster"].startswith("▸ "))
        self.assertEqual(keys[1], "10.20.0.1")
        self.assertIn("hostname: pg01.test.example", ui["10.20.0.1"])
        self.assertTrue(ui["10.20.0.1"].startswith("   └ "))
        self.assertEqual(keys[2], "10.20.0.2")
        self.assertEqual(keys[3], "pgsql_lbs")
        self.assertEqual(keys[4], "10.20.0.10")
        entries = collect_limits_ui_entries_for_cluster(
            FIXTURE_CLUSTERS, "fixture/postgresql"
        )
        self.assertEqual(
            [e["value"] for e in entries],
            keys,
        )
        self.assertEqual(
            entries[1]["label"],
            format_host_limit_label("10.20.0.1", "pg01.test.example"),
        )

    def test_ui_map_all(self) -> None:
        mapping = collect_limits_map(FIXTURE_CLUSTERS, ui=True)
        self.assertIn("fixture/postgresql", mapping)
        self.assertIsInstance(mapping["fixture/postgresql"], list)
        self.assertIsInstance(mapping["fixture/postgresql"][0], dict)
        self.assertNotIn("fixture/hosts_only", mapping)

    def test_ui_includes_all_hosts_orphans(self) -> None:
        """Hosts under all.hosts must appear in UI (same keys as flat)."""
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            leaf = clusters / "lab" / "orphans"
            leaf.mkdir(parents=True)
            (leaf / "cluster.yaml").write_text(
                "schema_version: 2\nexecution:\n  mode: local\n",
                encoding="utf-8",
            )
            (leaf / "hosts").write_text(
                "all:\n"
                "  hosts:\n"
                "    10.50.0.1:\n"
                "      hostname: orphan01.test\n"
                "  children:\n"
                "    edge:\n"
                "      hosts:\n"
                "        10.50.0.2: {}\n",
                encoding="utf-8",
            )
            flat = collect_limits_for_cluster(clusters, "lab/orphans")
            ui = collect_limits_ui_for_cluster(clusters, "lab/orphans")
            self.assertEqual(set(flat), set(ui.keys()))
            self.assertIn("10.50.0.1", ui)
            self.assertIn("hostname: orphan01.test", ui["10.50.0.1"])
            # Named group comes before orphans.
            keys = list(ui.keys())
            self.assertEqual(keys[0], "edge")
            self.assertEqual(keys[1], "10.50.0.2")
            self.assertEqual(keys[2], "10.50.0.1")

    def test_ui_all_hosts_only_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            leaf = clusters / "lab" / "bare_hosts"
            leaf.mkdir(parents=True)
            (leaf / "cluster.yaml").write_text(
                "schema_version: 2\nexecution:\n  mode: local\n",
                encoding="utf-8",
            )
            (leaf / "hosts").write_text(
                "all:\n"
                "  hosts:\n"
                "    10.60.0.1: {}\n",
                encoding="utf-8",
            )
            ui = collect_limits_ui_for_cluster(clusters, "lab/bare_hosts")
            self.assertEqual(list(ui.keys()), ["10.60.0.1"])
            self.assertEqual(
                collect_limits_for_cluster(clusters, "lab/bare_hosts"),
                ["10.60.0.1"],
            )

    def test_ui_group_wins_over_host_key_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            leaf = clusters / "lab" / "collide_parent"
            leaf.mkdir(parents=True)
            (leaf / "cluster.yaml").write_text(
                "schema_version: 2\nexecution:\n  mode: local\n",
                encoding="utf-8",
            )
            (leaf / "hosts").write_text(
                "all:\n"
                "  children:\n"
                "    parent:\n"
                "      children:\n"
                "        child:\n"
                "          hosts:\n"
                "            parent:\n"
                "              hostname: not-a-group.example\n"
                "            10.70.0.1: {}\n",
                encoding="utf-8",
            )
            flat = collect_limits_for_cluster(clusters, "lab/collide_parent")
            ui = collect_limits_ui_for_cluster(clusters, "lab/collide_parent")
            groups, hosts = collect_limits_parts_for_cluster(
                clusters, "lab/collide_parent"
            )
            self.assertEqual(groups, ["child", "parent"])
            self.assertEqual(hosts, ["10.70.0.1"])
            self.assertEqual(flat, ["child", "parent", "10.70.0.1"])
            self.assertTrue(ui["parent"].startswith("▸ "))
            self.assertNotIn("not-a-group.example", ui["parent"])
            self.assertIn("10.70.0.1", ui)
            self.assertEqual(set(flat), set(ui.keys()))


class ListClusterLimitsCliTest(unittest.TestCase):
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
        self.assertEqual(
            out.getvalue().splitlines(),
            _FIXTURE_FLAT["lab/alpha"],
        )

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
        self.assertEqual(json.loads(out.getvalue()), _FIXTURE_FLAT["lab/alpha"])

    def test_cli_structured(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--cluster-id",
                    "fixture/redis",
                    "--structured",
                ]
            )
        self.assertEqual(rc, 0)
        self.assertEqual(
            json.loads(out.getvalue()),
            {
                "groups": _FIXTURE_PARTS["fixture/redis"][0],
                "hosts": _FIXTURE_PARTS["fixture/redis"][1],
            },
        )

    def test_cli_all_and_allow_empty(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["--clusters-root", str(FIXTURE_CLUSTERS), "--all"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue()), _FIXTURE_FLAT)

        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            clusters.mkdir()
            # Deployable leaf without hosts → empty map.
            leaf = clusters / "lab" / "bare"
            leaf.mkdir(parents=True)
            (leaf / "cluster.yaml").write_text(
                "schema_version: 2\nexecution:\n  mode: local\n",
                encoding="utf-8",
            )

            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                rc = main(["--clusters-root", str(clusters), "--all"])
            self.assertEqual(rc, 1)
            self.assertIn("no deployable leaves with usable inventory", err.getvalue())

            out = io.StringIO()
            with redirect_stdout(out):
                rc = main(
                    [
                        "--clusters-root",
                        str(clusters),
                        "--all",
                        "--allow-empty",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertEqual(out.getvalue().strip(), "{}")

    def test_cli_allow_empty_requires_all(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
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

    def test_cli_unavailable_exit_1(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--cluster-id",
                    "fixture/hosts_only",
                ]
            )
        self.assertEqual(rc, 1)
        self.assertIn("error:", err.getvalue())

    def test_cli_ui_single_and_all(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--cluster-id",
                    "fixture/postgresql",
                    "--ui",
                ]
            )
        self.assertEqual(rc, 0)
        entries = json.loads(out.getvalue())
        self.assertEqual(
            [e["value"] for e in entries],
            [
                "pgsql_cluster",
                "10.20.0.1",
                "10.20.0.2",
                "pgsql_lbs",
                "10.20.0.10",
            ],
        )
        self.assertIn("hostname: pg01.test.example", entries[1]["label"])

        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--all",
                    "--ui",
                ]
            )
        self.assertEqual(rc, 0)
        mapping = json.loads(out.getvalue())
        self.assertIn("fixture/postgresql", mapping)
        self.assertEqual(mapping["fixture/postgresql"][0]["value"], "pgsql_cluster")

    def test_cli_ui_structured_mutex(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = main(
                [
                    "--clusters-root",
                    str(FIXTURE_CLUSTERS),
                    "--all",
                    "--ui",
                    "--structured",
                ]
            )
        self.assertEqual(rc, 2)
        self.assertIn("mutually exclusive", err.getvalue())

    def test_module_entrypoint(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "clusterctl.tools.list_cluster_limits",
                "--clusters-root",
                str(FIXTURE_CLUSTERS),
                "--cluster-id",
                "lab/alpha",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            proc.stdout.splitlines(),
            _FIXTURE_FLAT["lab/alpha"],
        )


class ClusterLimitsCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in ("ATLAS_CLUSTER_ROOT", "ATLAS_CLUSTERS_ROOT", "CLUSTER_ID")
        }
        os.environ.pop("CLUSTER_ID", None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)
        os.environ["ATLAS_CLUSTERS_ROOT"] = str(FIXTURE_CLUSTERS)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_collect_payload_includes_hostname_and_group(self) -> None:
        from clusterctl.limits_cmd import collect_cluster_limits

        payload = collect_cluster_limits(FIXTURE_CLUSTERS, "fixture/postgresql")
        self.assertEqual(payload["cluster_id"], "fixture/postgresql")
        self.assertEqual(
            payload["groups"],
            _FIXTURE_PARTS["fixture/postgresql"][0],
        )
        hosts = {row["key"]: row for row in payload["hosts"]}
        self.assertEqual(
            sorted(hosts),
            _FIXTURE_PARTS["fixture/postgresql"][1],
        )
        self.assertEqual(hosts["10.20.0.1"]["hostname"], "pg01.test.example")
        self.assertEqual(hosts["10.20.0.1"]["group"], "pgsql_cluster")
        self.assertEqual(hosts["10.20.0.10"]["hostname"], "lb01.test.example")
        self.assertEqual(hosts["10.20.0.10"]["group"], "pgsql_lbs")

    def test_cli_json(self) -> None:
        from clusterctl.__main__ import main

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--cluster", "fixture/postgresql", "limits", "--json"])
        self.assertEqual(code, 0, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["cluster_id"], "fixture/postgresql")
        self.assertEqual(
            payload["groups"],
            _FIXTURE_PARTS["fixture/postgresql"][0],
        )
        self.assertEqual(payload["hosts"][0]["key"], "10.20.0.1")
        self.assertEqual(payload["hosts"][0]["hostname"], "pg01.test.example")

    def test_cli_unusable_inventory_is_empty_json(self) -> None:
        from clusterctl.__main__ import main

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--cluster", "fixture/hosts_only", "limits", "--json"])
        self.assertEqual(code, 0, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["groups"], [])
        self.assertEqual(payload["hosts"], [])

    def test_cli_missing_cluster(self) -> None:
        from clusterctl.__main__ import main

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--cluster", "missing/leaf", "limits", "--json"])
        self.assertEqual(code, 1, stdout.getvalue())
        self.assertIn("not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
