"""Phase 7: removed deprecated shims (role-repos CLI, ROLE_REPOS_*, STAGE_BY_NAME)."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import playbooks_feature_enabled
from clusterctl.playbooks_sync import apply_playbooks_env_overrides
from clusterctl.playbooks_config import PlaybookRepoSpec, PlaybooksConfig


ROOT = Path(__file__).resolve().parents[1]


class Phase7ShimRemovalTest(unittest.TestCase):
    def test_role_repos_cli_removed(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "clusterctl", "role-repos", "status"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("invalid choice", proc.stderr.lower() + proc.stdout.lower())

    def test_stage_by_name_removed(self) -> None:
        import clusterctl.stages as stages_module

        with self.assertRaises(AttributeError):
            _ = stages_module.STAGE_BY_NAME

    def test_role_repos_env_ignored(self) -> None:
        import os

        key = "ROLE_REPOS_K8S_PLATFORM_REF"
        old = os.environ.get(key)
        os.environ[key] = "legacy-branch"
        try:
            playbooks = PlaybooksConfig(
                repos={
                    "atlas-k8s-core": PlaybookRepoSpec(
                        name="atlas-k8s-core",
                        source="git",
                        url="git@example.com/atlas-k8s-core.git",
                        ref="main",
                    )
                }
            )
            merged = apply_playbooks_env_overrides(playbooks)
            self.assertEqual(merged.repos["atlas-k8s-core"].ref, "main")
        finally:
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old

    def test_role_repos_enabled_yaml_rejected(self) -> None:
        with self.assertRaises(ClusterctlError):
            playbooks_feature_enabled({"role_repos_enabled": True})

    def test_check_docker_role_repos_host_alias_removed(self) -> None:
        import clusterctl.docker_validate as docker_validate

        with self.assertRaises(AttributeError):
            _ = docker_validate.check_docker_role_repos_host

    def test_role_repos_yaml_flag_rejected(self) -> None:
        with self.assertRaises(ClusterctlError):
            playbooks_feature_enabled(
                {"role_repos": {"atlas-k8s-core": {"ref": "dev"}}}
            )


if __name__ == "__main__":
    unittest.main()
