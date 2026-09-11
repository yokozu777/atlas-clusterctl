"""Tests for phase-3 unified playbooks sync (role_repos_sync removed)."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from clusterctl.ansible_runner import AnsibleRunner
from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import seed_local_playbook_repo_stubs, seed_org_baseline_fixture
from clusterctl.playbooks_sync import ensure_playbooks_synced


class Phase3SyncUnificationTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "CLUSTER_WORKSPACE_ID")

    def test_role_repos_sync_module_removed(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("clusterctl.role_repos_sync")

    def test_ansible_runner_uses_playbooks_sync_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
            try:
                for key in self._ISOLATED_ENV_KEYS:
                    os.environ.pop(key, None)
                os.environ["ATLAS_CLUSTER_ROOT"] = str(root)
                seed_org_baseline_fixture(root)
                seed_local_playbook_repo_stubs(root)
                leaf = root / "clusters" / "lab" / "test"
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

                ctx = ClusterContext.load("lab/test")
                runner = AnsibleRunner(ctx)
                with mock.patch(
                    "clusterctl.ansible_runner.ensure_playbooks_synced",
                    return_value=[],
                ) as mocked:
                    runner._sync_repos(dry_run=True)
                mocked.assert_called_once()
                kwargs = mocked.call_args.kwargs
                self.assertTrue(kwargs["playbooks_enabled"])
                self.assertIsNotNone(kwargs["playbooks"])
                self.assertIn("atlas-k8s-core", kwargs["playbooks"].repos)
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_leaf_playbooks_override_syncs_via_playbooks_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
            try:
                for key in self._ISOLATED_ENV_KEYS:
                    os.environ.pop(key, None)
                os.environ["ATLAS_CLUSTER_ROOT"] = str(root)
                seed_org_baseline_fixture(root)
                seed_local_playbook_repo_stubs(root)
                leaf = root / "clusters" / "lab" / "test"
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
                            "playbooks": {
                                "atlas-k8s-core": {
                                    "source": "git",
                                    "url": "git@example.com/org/atlas-k8s-core.git",
                                    "ref": "feature/overlay",
                                    "sync": "always",
                                }
                            },
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )

                ctx = ClusterContext.load("lab/test")
                results = ensure_playbooks_synced(
                    playbooks_enabled=True,
                    playbooks=__import__(
                        "clusterctl.playbooks_resolve",
                        fromlist=["effective_playbooks_config"],
                    ).effective_playbooks_config(ctx),
                    workspace_root=ctx.workspace_root,
                    repo_root_path=ctx.repo_root,
                    dry_run=True,
                )
                platform = next(result for result in results if result.name == "atlas-k8s-core")
                self.assertTrue(platform.action.startswith("dry-run-"))
                self.assertIn("feature/overlay", platform.detail)
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
