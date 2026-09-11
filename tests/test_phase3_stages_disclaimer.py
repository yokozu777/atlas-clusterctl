"""Phase 3: ./cluster stages org-baseline disclaimer."""

from __future__ import annotations

import io
import contextlib
import unittest

from clusterctl.__main__ import main


class StagesCommandDisclaimerTest(unittest.TestCase):
    def test_stages_prints_org_baseline_disclaimer(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(["stages", "--baseline"])
        self.assertEqual(code, 0)
        self.assertIn("org baseline", stderr.getvalue().lower())
        self.assertIn("stages --cluster", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
