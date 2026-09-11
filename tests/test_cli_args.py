"""Tests for clusterctl.cli_args."""

from __future__ import annotations

import unittest

from clusterctl.cli_args import normalize_global_argv, strip_global_flags_from_argv
from clusterctl.exceptions import ClusterctlError


class CliArgsTest(unittest.TestCase):
    def test_cluster_before_subcommand(self) -> None:
        argv = normalize_global_argv(["cluster", "--cluster", "lab", "validate"])
        self.assertEqual(argv, ["cluster", "--cluster", "lab", "validate"])

    def test_cluster_after_subcommand(self) -> None:
        argv = normalize_global_argv(["cluster", "validate", "--cluster", "lab"])
        self.assertEqual(argv, ["cluster", "--cluster", "lab", "validate"])

    def test_executor_after_subcommand(self) -> None:
        argv = normalize_global_argv(["cluster", "run", "--dry-run", "--executor", "local"])
        self.assertEqual(argv, ["cluster", "--executor", "local", "run", "--dry-run"])

    def test_both_flags_any_order(self) -> None:
        argv = normalize_global_argv(
            ["cluster", "plan", "--executor", "docker", "--cluster", "lab"]
        )
        self.assertEqual(
            argv,
            ["cluster", "--executor", "docker", "--cluster", "lab", "plan"],
        )

    def test_inline_form(self) -> None:
        argv = normalize_global_argv(["validate", "--cluster=lab"])
        self.assertEqual(argv, ["cluster", "--cluster", "lab", "validate"])

    def test_conflicting_cluster_raises(self) -> None:
        with self.assertRaises(ClusterctlError):
            normalize_global_argv(["cluster", "--cluster", "a", "validate", "--cluster", "b"])

    def test_same_cluster_twice_deduped(self) -> None:
        argv = normalize_global_argv(["cluster", "--cluster", "lab", "validate", "--cluster", "lab"])
        self.assertEqual(argv, ["cluster", "--cluster", "lab", "validate"])

    def test_strip_global_flags(self) -> None:
        stripped = strip_global_flags_from_argv(
            ["cluster", "--cluster", "lab", "run", "--executor", "docker", "--dry-run"]
        )
        self.assertEqual(stripped, ["cluster", "run", "--dry-run"])


    def test_main_validate_repo_only(self) -> None:
        import os
        import tempfile
        from pathlib import Path

        from clusterctl.__main__ import main
        from clusterctl.pipeline_fixture import seed_org_baseline_fixture

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
            seed_org_baseline_fixture(root)
            old = os.environ.get("ATLAS_CLUSTER_ROOT")
            old_ws = os.environ.get("CLUSTER_WORKSPACE_ID")
            os.environ["ATLAS_CLUSTER_ROOT"] = str(root)
            os.environ["CLUSTER_WORKSPACE_ID"] = "test-ws"
            try:
                code = main(["validate", "--repo", "--skip-docker-smoke"])
                self.assertEqual(code, 0)
            finally:
                if old is None:
                    os.environ.pop("ATLAS_CLUSTER_ROOT", None)
                else:
                    os.environ["ATLAS_CLUSTER_ROOT"] = old
                if old_ws is None:
                    os.environ.pop("CLUSTER_WORKSPACE_ID", None)
                else:
                    os.environ["CLUSTER_WORKSPACE_ID"] = old_ws


if __name__ == "__main__":
    unittest.main()
