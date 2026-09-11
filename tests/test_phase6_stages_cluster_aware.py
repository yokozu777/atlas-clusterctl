"""Phase 6: cluster-aware ./cluster stages."""

from __future__ import annotations

from tests.lab_support import lab_id_for, skip_unless_stack, FULL_K8S_INVOCATION_COUNT

import io
import contextlib
import os
import unittest
from pathlib import Path

from clusterctl.__main__ import main
from clusterctl.context import ClusterContext
from clusterctl.stages_cmd import cmd_stages, format_org_baseline_stages_text


ROOT = Path(__file__).resolve().parents[1]


class StagesClusterAwareTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_baseline_flag_prints_org_disclaimer(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["stages", "--baseline"])
        self.assertEqual(code, 0)
        self.assertIn("org baseline", stderr.getvalue().lower())
        self.assertIn("provision", format_org_baseline_stages_text())

    @skip_unless_stack("k8s")
    def test_cluster_stages_dev_k8s(self) -> None:
        stderr = io.StringIO()
        stdout = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            code = main(["stages", "--cluster", lab_id_for("k8s")])
        self.assertEqual(code, 0, stderr.getvalue())
        out = stdout.getvalue()
        self.assertIn("Cluster:", out)
        self.assertIn(lab_id_for("k8s"), out)
        self.assertIn("provision", out)

    @skip_unless_stack("k8s")
    def test_cmd_stages_cluster_matches_plan_phase_count(self) -> None:
        ctx = ClusterContext.load(lab_id_for("k8s"))
        stderr = io.StringIO()
        stdout = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            code = cmd_stages(ctx)
        self.assertEqual(code, 0)
        out = stdout.getvalue()
        self.assertIn(f"{FULL_K8S_INVOCATION_COUNT} invocations", out)


if __name__ == "__main__":
    unittest.main()
