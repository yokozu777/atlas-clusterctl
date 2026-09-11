"""Phase 4: context.summary_lines playbooks section deduplication."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import seed_org_baseline_fixture


class ContextSummaryLinesTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)
        self._seed_cluster()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_cluster(self) -> None:
        leaf = self.root / "clusters" / "lab" / "test"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab/test",
                    "inventory": "hosts",
                    "playbooks_enabled": True,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/test",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def test_summary_lines_single_playbooks_block_when_resolver_active(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab/test")
        lines = ctx.summary_lines()
        playbooks_headers = [
            line
            for line in lines
            if line.startswith("Playbooks:")
            or line.startswith("Playbooks (workspace/local resolver):")
        ]
        self.assertEqual(len(playbooks_headers), 1)
        self.assertTrue(
            playbooks_headers[0].startswith("Playbooks (workspace/local resolver):")
        )

    def test_summary_lines_no_duplicate_effective_repo_count_line(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab/test")
        text = "\n".join(ctx.summary_lines())
        self.assertEqual(text.count("repo(s),"), 0)
        self.assertIn("Playbooks (workspace/local resolver):", text)


if __name__ == "__main__":
    unittest.main()
