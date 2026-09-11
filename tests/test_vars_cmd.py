"""Tests for ``./cluster vars --json`` catalog (paths only)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from clusterctl.vars_cmd import collect_cluster_vars
from clusterctl.__main__ import main


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CLUSTERS = (
    ROOT / "tests" / "fixtures" / "jenkins_seed_inventory" / "clusters"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CollectClusterVarsTest(unittest.TestCase):
    def test_fixture_postgresql_lists_cluster_and_hosts(self) -> None:
        os.environ["ATLAS_CLUSTERS_ROOT"] = str(FIXTURE_CLUSTERS)
        self.addCleanup(os.environ.pop, "ATLAS_CLUSTERS_ROOT", None)
        payload = collect_cluster_vars(ROOT, "fixture/postgresql")
        rels = [row["rel"] for row in payload["files"]]
        self.assertIn("fixture/postgresql/cluster.yaml", rels)
        self.assertIn("fixture/postgresql/hosts", rels)
        self.assertEqual(payload["cluster_id"], "fixture/postgresql")
        self.assertTrue(Path(payload["clusters_root"]).is_dir())

    def test_cascade_layers_and_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clusters = Path(tmp) / "clusters"
            _write(
                clusters / "default" / "default" / "cluster.yaml",
                "schema_version: 2\n",
            )
            _write(
                clusters / "default" / "default" / "group_vars" / "all" / "org.yml",
                "org_flag: true\n",
            )
            _write(
                clusters / "lab" / "default" / "cluster.yaml",
                "schema_version: 2\n",
            )
            _write(
                clusters / "lab" / "default" / "group_vars" / "all" / "env.yml",
                "env_flag: true\n",
            )
            leaf = clusters / "lab" / "pg"
            _write(leaf / "cluster.yaml", "schema_version: 2\nexecution:\n  mode: local\n")
            _write(
                leaf / "hosts",
                "all:\n  children:\n    pg:\n      hosts:\n        10.0.0.1: {}\n",
            )
            _write(
                leaf / "group_vars" / "all" / "atlas-postgresql.yml",
                "pg_name: lab\n",
            )
            _write(
                leaf / "group_vars" / "all" / "atlas-postgresql.secrets.yml",
                "pg_password: s3cret\n",
            )
            _write(leaf / "host_vars" / "10.0.0.1.yml", "ansible_user: root\n")

            prev = os.environ.get("ATLAS_CLUSTERS_ROOT")
            os.environ["ATLAS_CLUSTERS_ROOT"] = str(clusters)
            try:
                payload = collect_cluster_vars(ROOT, "lab/pg")
            finally:
                if prev is None:
                    os.environ.pop("ATLAS_CLUSTERS_ROOT", None)
                else:
                    os.environ["ATLAS_CLUSTERS_ROOT"] = prev

            by_rel = {row["rel"]: row for row in payload["files"]}
            self.assertEqual(by_rel["default/default/group_vars/all/org.yml"]["layer"], "org")
            self.assertEqual(by_rel["lab/default/group_vars/all/env.yml"]["layer"], "env")
            self.assertEqual(
                by_rel["lab/pg/group_vars/all/atlas-postgresql.yml"]["layer"],
                "leaf",
            )
            secret = by_rel["lab/pg/group_vars/all/atlas-postgresql.secrets.yml"]
            self.assertTrue(secret["secret"])
            self.assertEqual(secret["kind"], "group_vars")
            self.assertEqual(by_rel["lab/pg/host_vars/10.0.0.1.yml"]["kind"], "host_vars")
            self.assertEqual(by_rel["lab/pg/hosts"]["kind"], "inventory")
            self.assertEqual(by_rel["lab/pg/cluster.yaml"]["kind"], "cluster")
            self.assertNotIn("s3cret", json.dumps(payload))


class ClusterVarsCliTest(unittest.TestCase):
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

    def test_cli_json_paths_only(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--cluster", "fixture/postgresql", "vars", "--json"])
        self.assertEqual(code, 0, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["cluster_id"], "fixture/postgresql")
        rels = [row["rel"] for row in payload["files"]]
        self.assertIn("fixture/postgresql/hosts", rels)
        self.assertNotIn("s3cret", stdout.getvalue())

    def test_cli_missing_cluster(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--cluster", "missing/leaf", "vars", "--json"])
        self.assertEqual(code, 1, stdout.getvalue())
        self.assertTrue(stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
