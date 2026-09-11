"""Regression: docs/README.md quick-start phase windows match template SoT."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "docs" / "README.md"

# Truncated infra_edge window (must be provision..init-infra-post).
_TRUNCATED_INFRA_WINDOW = re.compile(r"provision\.\.infra(?!-post)\b")


class DocsReadmeQuickstartTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = README.read_text(encoding="utf-8")

    def test_infra_edge_full_window_is_init_infra_post(self) -> None:
        self.assertIn("provision..init-infra-post", self.text)
        bad = _TRUNCATED_INFRA_WINDOW.findall(self.text)
        self.assertEqual(
            bad,
            [],
            "docs/README.md must not teach provision..infra "
            "(SoT full window is provision..init-infra-post)",
        )

    def test_k8s_full_does_not_teach_infra_phases(self) -> None:
        # k8s_full phases: provision → init → k8s-core → k8s-addons
        # (infra is a separate infra_edge leaf).
        marker = "# Full k8s"
        start = self.text.index(marker)
        fence_end = self.text.index("```", start)
        block = self.text[start:fence_end]
        self.assertIsNone(_TRUNCATED_INFRA_WINDOW.search(block))
        self.assertNotIn("play infra", block)
        self.assertIn("provision..k8s-core", block)
        self.assertIn("k8s-core..k8s-addons", block)
        self.assertIn("provision..k8s-addons", block)
        self.assertIn("infra_edge", block)

    def test_top_quickstart_full_k8s_window(self) -> None:
        top = self.text.split("Data-plane / agent scaffolds:", 1)[0]
        self.assertIn("provision..k8s-addons", top)


if __name__ == "__main__":
    unittest.main()
