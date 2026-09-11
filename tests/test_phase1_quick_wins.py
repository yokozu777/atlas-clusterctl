"""Tests for phase-1 quick wins: readiness unify, PLAYBOOKS env, effective playbooks."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.context import ClusterContext
from clusterctl.playbooks_config import PlaybookRepoSpec, PlaybooksConfig
from clusterctl.playbooks_resolve import effective_playbooks_config
from clusterctl.playbooks_sync import apply_playbooks_env_overrides, sync_playbooks
from clusterctl.pipeline_fixture import seed_org_baseline_fixture


class Phase1ReadinessTest(unittest.TestCase):
    def test_k8s_platform_marker_dirs_ready_without_roles_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace" / "k8s.example.com"
            repo_root = workspace / "repos" / "atlas-k8s-core"
            (repo_root / "00_controller_tooling").mkdir(parents=True)
            spec = PlaybookRepoSpec(
                name="atlas-k8s-core",
                source="git",
                url="git@example.com/atlas-k8s-core.git",
                ref="main",
                layout="",
                sync="never",
            )
            playbooks = PlaybooksConfig(repos={"atlas-k8s-core": spec})
            results = sync_playbooks(
                playbooks,
                workspace_root=workspace,
                repo_root_path=root,
            )
            self.assertEqual(results[0].action, "never")


class Phase1EnvOverridesTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = (
        "ATLAS_CLUSTER_ROOT",
        "CLUSTER_ID",
        "CLUSTER_WORKSPACE_ID",
        "PLAYBOOKS_ATLAS_K8S_CORE_REF",
    )

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)
        self._seed_leaf()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_leaf(self) -> None:
        leaf = self.root / "clusters" / "lab" / "test"
        leaf.mkdir(parents=True)
        (leaf / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        (leaf / "group_vars" / "all").mkdir(parents=True)
        (leaf / "group_vars" / "all" / "cluster.yml").write_text(
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
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab/test",
                    "inventory": "hosts",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / ".cluster-active").write_text("lab/test\n", encoding="utf-8")

    def test_playbooks_ref_env_override(self) -> None:
        os.environ["PLAYBOOKS_ATLAS_K8S_CORE_REF"] = "feature/env-branch"
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
        self.assertEqual(merged.repos["atlas-k8s-core"].ref, "feature/env-branch")

    def test_effective_playbooks_config_applies_playbooks_env(self) -> None:
        os.environ["PLAYBOOKS_ATLAS_K8S_CORE_REF"] = "effective-branch"
        ctx = ClusterContext.load("lab/test")
        playbooks = effective_playbooks_config(ctx)
        self.assertEqual(playbooks.repos["atlas-k8s-core"].ref, "effective-branch")

    def test_effective_playbooks_config_uses_cascade_playbooks_override(self) -> None:
        leaf = self.root / "clusters" / "lab" / "test" / "cluster.yaml"
        data = yaml.safe_load(leaf.read_text(encoding="utf-8"))
        data["playbooks"] = {
            "atlas-k8s-core": {
                "ref": "leaf-override",
            }
        }
        leaf.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        ctx = ClusterContext.load("lab/test")
        playbooks = effective_playbooks_config(ctx)
        self.assertEqual(playbooks.repos["atlas-k8s-core"].ref, "leaf-override")


if __name__ == "__main__":
    unittest.main()
