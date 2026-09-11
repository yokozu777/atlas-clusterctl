"""Phase 4: lazy pipeline load — no org baseline I/O at import time."""

from __future__ import annotations

import importlib
import sys
import unittest
from unittest import mock

import clusterctl.pipeline as pipeline_module


class PipelineLazyLoadTest(unittest.TestCase):
    def tearDown(self) -> None:
        pipeline_module.reset_pipeline_cache_for_tests()

    def test_import_pipeline_does_not_load_org_baseline(self) -> None:
        pipeline_module.reset_pipeline_cache_for_tests()
        with mock.patch.object(pipeline_module, "stages_from_org_baseline") as mocked:
            reloaded = importlib.reload(pipeline_module)
            mocked.assert_not_called()
            self.assertNotIn("STAGES", reloaded.__dict__)

    def test_phase_indexes_load_on_first_access(self) -> None:
        pipeline_module.reset_pipeline_cache_for_tests()
        with mock.patch.object(
            pipeline_module,
            "stages_from_org_baseline",
            wraps=pipeline_module.stages_from_org_baseline,
        ) as mocked:
            run_order = pipeline_module.RUN_ORDER
            self.assertGreater(len(run_order), 0)
            self.assertEqual(mocked.call_count, 1)
            alias = pipeline_module.PHASE_BY_ALIAS
            self.assertEqual(mocked.call_count, 1)
            self.assertIn(run_order[0], alias)

    def test_reset_pipeline_cache_for_tests_clears_indexes(self) -> None:
        _ = pipeline_module.RUN_ORDER
        pipeline_module.reset_pipeline_cache_for_tests()
        with mock.patch.object(pipeline_module, "stages_from_org_baseline") as mocked:
            mocked.return_value = ()
            run_order = pipeline_module.RUN_ORDER
            self.assertEqual(run_order, [])
            mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
