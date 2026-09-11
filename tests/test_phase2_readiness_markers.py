"""Tests for phase-2 declarative readiness_markers (G1 completion)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import load_org_baseline_cluster_config, seed_org_baseline_fixture
from clusterctl.playbooks_config import (
    PlaybookRepoSpec,
    PlaybooksConfig,
    merge_playbooks_configs,
    parse_playbooks_config,
)
from clusterctl.playbooks_paths import layout_dir_ready, playbook_repo_layout_ready
from clusterctl.playbooks_registry import org_baseline_playbook_repo_names
from clusterctl.playbooks_resolve import effective_playbooks_config
from clusterctl.playbooks_repos import ansible_roles_dir_ready, resolved_playbook_repos_from_config


class Phase2ReadinessMarkersTest(unittest.TestCase):
    def test_parse_readiness_markers(self) -> None:
        config = parse_playbooks_config(
            {
                "custom": {
                    "source": "git",
                    "url": "git@example.com/custom.git",
                    "ref": "main",
                    "layout": "",
                    "readiness_markers": ["alpha", "beta"],
                    "entries": {
                        "install": {
                            "file": "playbooks/install.yaml",
                            "invocations": [{"tags": "all"}],
                        }
                    },
                }
            }
        )
        assert config is not None
        self.assertEqual(config.repos["custom"].readiness_markers, ("alpha", "beta"))

    def test_invalid_marker_rejected(self) -> None:
        with self.assertRaises(ClusterctlError):
            parse_playbooks_config(
                {
                    "custom": {
                        "source": "git",
                        "url": "git@example.com/custom.git",
                        "ref": "main",
                        "readiness_markers": ["roles/extra"],
                        "entries": {
                            "install": {
                                "file": "playbooks/install.yaml",
                                "invocations": [{"tags": "all"}],
                            }
                        },
                    }
                }
            )

    def test_merge_preserves_base_markers_when_override_omits(self) -> None:
        base = PlaybooksConfig(
            repos={
                "custom": PlaybookRepoSpec(
                    name="custom",
                    source="git",
                    url="git@example.com/a.git",
                    ref="main",
                    layout="",
                    readiness_markers=("alpha",),
                )
            }
        )
        override = PlaybooksConfig(
            repos={
                "custom": PlaybookRepoSpec(
                    name="custom",
                    source="local",
                    path="custom",
                    layout="",
                )
            }
        )
        merged = merge_playbooks_configs(base, override)
        assert merged is not None
        self.assertEqual(merged.repos["custom"].readiness_markers, ("alpha",))
        self.assertEqual(merged.repos["custom"].source, "local")

    def test_layout_dir_ready_uses_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "alpha").mkdir()
            self.assertTrue(layout_dir_ready(root, markers=("alpha",)))
            self.assertFalse(layout_dir_ready(root, markers=("missing",)))
            self.assertTrue(layout_dir_ready(root, markers=()))

    def test_playbook_repo_layout_ready_no_hardcoded_repo_names(self) -> None:
        paths_source = Path(__file__).resolve().parents[1] / "clusterctl" / "playbooks_paths.py"
        text = paths_source.read_text(encoding="utf-8")
        self.assertNotIn("atlas-k8s-core", text)

    def test_org_baseline_k8s_core_has_markers(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        config = load_org_baseline_cluster_config(repo_root)
        assert config.playbooks is not None
        core = config.playbooks.repos["atlas-k8s-core"]
        addons = config.playbooks.repos["atlas-k8s-addons"]
        self.assertEqual(
            core.readiness_markers,
            ("00_controller_tooling", "29_fetch_kubeconfig"),
        )
        self.assertEqual(
            addons.readiness_markers,
            (
                "120_controller_tooling",
                "210_helm_bootstrap",
                "220_calico",
                "310_prometheus",
                "520_envoy_gateway",
            ),
        )

    def test_fifth_repo_markers_without_python_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed_org_baseline_fixture(root)
            baseline = root / "clusters" / "default" / "default" / "cluster.yaml"
            data = yaml.safe_load(baseline.read_text(encoding="utf-8"))
            data.setdefault("playbooks", {})["rare-stack"] = {
                "source": "git",
                "url": "git@example.com/org/rare-stack.git",
                "ref": "main",
                "layout": "",
                "readiness_markers": ["install-root"],
                "entries": {
                    "install": {
                        "file": "playbooks/install.yaml",
                        "invocations": [{"tags": "all"}],
                    }
                },
            }
            baseline.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            names = org_baseline_playbook_repo_names(root)
            self.assertIn("rare-stack", names)

            config = parse_playbooks_config(data["playbooks"])
            assert config is not None
            spec = config.repos["rare-stack"]
            workspace = root / "workspace" / "ws"
            repo_dir = workspace / "repos" / "rare-stack"
            repo_dir.mkdir(parents=True)
            self.assertFalse(playbook_repo_layout_ready(spec, repo_dir))
            (repo_dir / "install-root").mkdir()
            self.assertTrue(playbook_repo_layout_ready(spec, repo_dir))

    def test_resolved_repos_inherit_markers_from_playbooks(self) -> None:
        playbooks = PlaybooksConfig(
            repos={
                "atlas-k8s-core": PlaybookRepoSpec(
                    name="atlas-k8s-core",
                    source="git",
                    url="git@example.com/k.git",
                    ref="main",
                    layout="",
                    readiness_markers=("00_controller_tooling",),
                )
            }
        )
        specs = resolved_playbook_repos_from_config(playbooks)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "00_controller_tooling").mkdir()
            self.assertTrue(ansible_roles_dir_ready(root, specs["atlas-k8s-core"]))


class Phase2OrgBaselineContextTest(unittest.TestCase):
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
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def test_effective_playbooks_exposes_k8s_split_markers(self) -> None:
        ctx = ClusterContext.load("lab/test")
        playbooks = effective_playbooks_config(ctx)
        self.assertEqual(
            playbooks.repos["atlas-k8s-core"].readiness_markers,
            ("00_controller_tooling", "29_fetch_kubeconfig"),
        )
        self.assertEqual(
            playbooks.repos["atlas-k8s-addons"].readiness_markers,
            (
                "120_controller_tooling",
                "210_helm_bootstrap",
                "220_calico",
                "310_prometheus",
                "520_envoy_gateway",
            ),
        )


if __name__ == "__main__":
    unittest.main()
