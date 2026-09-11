"""Additive --json for list / stages / repos status / workspace show."""

from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from clusterctl.__main__ import main
from clusterctl.list_cmd import collect_cluster_list
from clusterctl.stages_cmd import format_org_baseline_stages_json


ROOT = Path(__file__).resolve().parents[1]


class CliJsonListTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            k: os.environ.get(k) for k in ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")
        }
        os.environ.pop("CLUSTER_ID", None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_list_json_is_array_of_objects(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["list", "--json"])
        self.assertEqual(code, 0, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertIsInstance(payload, list)
        for row in payload:
            self.assertIn("id", row)
            self.assertIn("kind", row)
            self.assertIn(row["kind"], ("deployable", "policy", "broken"))
        collected = collect_cluster_list(ROOT)
        self.assertEqual([r["id"] for r in payload], [r["id"] for r in collected])

    def test_stages_baseline_json(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["stages", "--baseline", "--json"])
        self.assertEqual(code, 0, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["baseline"])
        self.assertGreater(len(payload["stages"]), 0)
        self.assertIn("alias", payload["stages"][0])
        expected = json.loads(format_org_baseline_stages_json())
        self.assertEqual(payload["stages"][0]["alias"], expected["stages"][0]["alias"])

    def test_list_text_unchanged_empty_message_prefix(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["list"])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertNotIn("{", stdout.getvalue().lstrip()[:1] or "x")


if __name__ == "__main__":
    unittest.main()
