"""Tests for resolved playbook-repos view (playbooks_repos)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import (
    load_org_baseline_cluster_config,
    org_baseline_required_repo_names,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_repos import (
    empty_resolved_playbooks_repos,
    resolve_local_repo_path,
    resolved_playbook_repos_from_config,
)
from clusterctl.playbooks_resolve import build_resolved_playbooks_repos
from clusterctl.playbooks_sync import apply_playbooks_env_overrides
from clusterctl.playbooks_validate import validate_org_baseline_playbooks


class RoleReposSpecTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT",)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved_env = {key: os.environ.get(key) for key in self._ISOLATED_ENV_KEYS}
        self._saved_playbooks_env = {
            key: value
            for key, value in os.environ.items()
            if key.startswith("PLAYBOOKS_")
        }
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        for key in self._saved_playbooks_env:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for key in list(os.environ):
            if key.startswith("PLAYBOOKS_") and key not in self._saved_playbooks_env:
                os.environ.pop(key, None)
        for key, value in self._saved_playbooks_env.items():
            os.environ[key] = value
        self._tmpdir.cleanup()

    def test_org_baseline_specs_all_required_repos(self) -> None:
        config = load_org_baseline_cluster_config(self.root)
        assert config.playbooks is not None
        specs = resolved_playbook_repos_from_config(config.playbooks)
        required = org_baseline_required_repo_names(self.root)
        self.assertEqual(set(specs), required)
        self.assertEqual(specs["atlas-k8s-core"].source, "local")
        self.assertIsNone(specs["atlas-k8s-core"].ref)

    def test_validate_defaults_file(self) -> None:
        config = validate_org_baseline_playbooks(self.root)
        self.assertTrue(config.defaults_loaded)
        self.assertEqual(len(config.specs), len(org_baseline_required_repo_names(self.root)))

    def test_validate_defaults_incomplete(self) -> None:
        partial_path = self.root / "clusters" / "default" / "default" / "cluster.yaml"
        partial_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "playbooks": {
                        "atlas-node-foundation": {
                            "source": "git",
                            "url": "git@example.com/init.git",
                            "ref": "main",
                            "entries": {
                                "init": {
                                    "file": "playbooks/init_nodes.yaml",
                                    "invocations": [{"tags": "all"}],
                                }
                            },
                        }
                    },
                    "phases": [
                        "atlas-node-foundation/init",
                        "atlas-compute-provision/provision",
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ClusterctlError) as ctx:
            validate_org_baseline_playbooks(self.root)
        self.assertIn("atlas-compute-provision", str(ctx.exception))

    def test_build_resolved_playbooks_repos_from_playbooks(self) -> None:
        config = load_org_baseline_cluster_config(self.root)
        assert config.playbooks is not None
        resolved = build_resolved_playbooks_repos(config.playbooks)
        self.assertIn("atlas-k8s-core", resolved.specs)
        self.assertFalse(resolved.cluster_overrides)

    def test_env_ref_override(self) -> None:
        os.environ["PLAYBOOKS_ATLAS_K8S_CORE_REF"] = "env-branch"
        config = load_org_baseline_cluster_config(self.root)
        assert config.playbooks is not None
        resolved = build_resolved_playbooks_repos(config.playbooks)
        self.assertEqual(resolved.specs["atlas-k8s-core"].ref, "env-branch")
        self.assertTrue(resolved.env_overrides)

    def test_env_path_sets_local(self) -> None:
        local_repo = self.root / "dev-atlas-node-foundation"
        local_repo.mkdir()
        os.environ["PLAYBOOKS_ATLAS_NODE_FOUNDATION_PATH"] = str(local_repo)
        os.environ["PLAYBOOKS_ATLAS_NODE_FOUNDATION_SOURCE"] = "local"
        config = load_org_baseline_cluster_config(self.root)
        assert config.playbooks is not None
        resolved = build_resolved_playbooks_repos(config.playbooks)
        spec = resolved.specs["atlas-node-foundation"]
        self.assertEqual(spec.source, "local")
        self.assertEqual(spec.path, str(local_repo))

    def test_resolve_local_sibling_path(self) -> None:
        monorepo = self.root / "monorepo"
        repo = monorepo / "atlas-clusterctl"
        sibling = monorepo / "atlas-node-foundation"
        repo.mkdir(parents=True)
        sibling.mkdir()
        seed_org_baseline_fixture(repo)
        config = load_org_baseline_cluster_config(repo)
        assert config.playbooks is not None
        playbooks = apply_playbooks_env_overrides(config.playbooks)
        from clusterctl.playbooks_config import PlaybooksConfig, PlaybookRepoSpec

        merged = PlaybooksConfig(
            repos={
                **playbooks.repos,
                "atlas-node-foundation": PlaybookRepoSpec(
                    name="atlas-node-foundation",
                    source="local",
                    path="atlas-node-foundation",
                    path_relative_to="sibling",
                    layout="roles/",
                ),
            }
        )
        resolved = build_resolved_playbooks_repos(merged)
        local_spec = resolve_local_repo_path(
            resolved.specs["atlas-node-foundation"],
            repo_root_path=repo,
        )
        self.assertEqual(local_spec, sibling.resolve())

    def test_resolve_local_repo_root_path(self) -> None:
        local_dir = self.root / "vendor" / "atlas-k8s-core"
        local_dir.mkdir(parents=True)
        from clusterctl.playbooks_config import PlaybooksConfig, PlaybookRepoSpec

        playbooks = PlaybooksConfig(
            repos={
                "atlas-k8s-core": PlaybookRepoSpec(
                    name="atlas-k8s-core",
                    source="local",
                    path="vendor/atlas-k8s-core",
                    path_relative_to="repo_root",
                    layout="",
                )
            }
        )
        resolved = build_resolved_playbooks_repos(playbooks)
        local = resolve_local_repo_path(
            resolved.specs["atlas-k8s-core"],
            repo_root_path=self.root,
        )
        self.assertEqual(local, local_dir.resolve())

    def test_empty_resolved_playbooks_repos(self) -> None:
        config = empty_resolved_playbooks_repos()
        self.assertFalse(config.is_configured())


if __name__ == "__main__":
    unittest.main()
