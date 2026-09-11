"""Tests for PR-G6: org-baseline stub names and playbooks_enabled."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config import load_cluster_config
from clusterctl.context import ClusterContext
from clusterctl.playbooks_config import playbooks_feature_enabled, resolve_playbooks_enabled
from clusterctl.playbooks_registry import org_baseline_playbook_repo_names
from clusterctl.pipeline_fixture import seed_org_baseline_fixture
from clusterctl.repo_conventions import _legacy_in_repo_role_repo_findings


class GenericEngineG6Test(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "CLUSTER_WORKSPACE_ID")

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
                    "playbooks_enabled": True,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / ".cluster-active").write_text("lab/test\n", encoding="utf-8")

    def test_org_baseline_stub_names_include_known_repos(self) -> None:
        names = org_baseline_playbook_repo_names(self.root)
        self.assertIn("atlas-node-foundation", names)
        self.assertIn("atlas-k8s-core", names)
        self.assertGreaterEqual(len(names), 4)

    def test_fifth_repo_in_org_baseline_triggers_stub_guard(self) -> None:
        baseline = self.root / "clusters" / "default" / "default" / "cluster.yaml"
        data = yaml.safe_load(baseline.read_text(encoding="utf-8"))
        data.setdefault("playbooks", {})["rare-stack"] = {
            "source": "git",
            "url": "git@example.com/org/rare-stack.git",
            "ref": "main",
            "layout": "roles/",
            "entries": {
                "install": {
                    "file": "playbooks/install.yaml",
                    "invocations": [{"tags": "all"}],
                }
            },
        }
        baseline.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

        names = org_baseline_playbook_repo_names(self.root)
        self.assertIn("rare-stack", names)

        (self.root / "rare-stack").mkdir()
        codes = {f.code for f in _legacy_in_repo_role_repo_findings(self.root)}
        self.assertIn("legacy_role_repo_stub_empty", codes)

    def test_playbooks_enabled_explicit(self) -> None:
        self.assertTrue(playbooks_feature_enabled({"playbooks_enabled": True}))
        self.assertFalse(playbooks_feature_enabled({}))
        self.assertTrue(
            playbooks_feature_enabled(
                {
                    "playbooks": {
                        "rare": {
                            "source": "local",
                            "path": "rare",
                            "entries": {
                                "install": {
                                    "file": "playbooks/install.yaml",
                                    "invocations": [{"tags": "all"}],
                                }
                            },
                        }
                    }
                }
            )
        )

    def test_cluster_config_playbooks_enabled(self) -> None:
        cfg = load_cluster_config(
            self.root / "clusters" / "lab" / "test",
            "lab/test",
            repo_root=self.root,
        )
        self.assertTrue(cfg.playbooks_enabled)

    def test_context_playbooks_enabled_property(self) -> None:
        ctx = ClusterContext.load("lab/test")
        self.assertTrue(ctx.playbooks_enabled)

    def test_resolve_playbooks_enabled_from_merged_v2(self) -> None:
        from clusterctl.cluster_config_loader import load_merged_cluster_config_v2

        v2 = load_merged_cluster_config_v2(self.root / "clusters", "lab/test")
        enabled = resolve_playbooks_enabled({"id": "lab/test"}, config_v2=v2)
        self.assertTrue(enabled)


if __name__ == "__main__":
    unittest.main()
