"""Bootstrap galaxy install from playbook repo requirements.yml files."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import yaml

from clusterctl.ansible_runner import AnsibleRunner
from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import (
    load_org_baseline_cluster_config,
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_config import PlaybookRepoSpec, PlaybooksConfig
from clusterctl.playbooks_requirements import (
    PLAYBOOK_REQUIREMENTS_FILENAME,
    discover_playbook_requirements_files,
    playbook_requirements_env_value,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _local_playbooks_config(root: Path) -> PlaybooksConfig:
    baseline = load_org_baseline_cluster_config(root)
    assert baseline.playbooks is not None
    repos: dict[str, PlaybookRepoSpec] = {}
    overrides = local_playbooks_override_block()
    for name, raw in overrides.items():
        if name not in baseline.playbooks.repos:
            continue
        base_spec = baseline.playbooks.repos[name]
        repos[name] = PlaybookRepoSpec(
            name=name,
            source="local",
            path=raw["path"],
            path_relative_to=raw["path_relative_to"],
            layout=raw.get("layout"),
            sync="never",
            entries=base_spec.entries,
        )
    return PlaybooksConfig(repos=repos)


class BootstrapCollectionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        seed_org_baseline_fixture(self.root)
        shutil.copytree(_REPO_ROOT / "clusterctl" / "bootstrap", self.root / "clusterctl" / "bootstrap")
        cluster = self.root / "clusters" / "lab"
        all_dir = cluster / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        (cluster / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "execution": {"mode": "local"},
                    "playbooks": local_playbooks_override_block(),
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (cluster / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        (all_dir / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        seed_local_playbook_repo_stubs(self.root)
        self._env_patch = os.environ.copy()
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_patch)
        self._tmp.cleanup()

    def test_bootstrap_installs_collections_under_workspace_not_repo_root(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab")
        runner = AnsibleRunner(ctx)
        runner.bootstrap()

        self.assertFalse(
            (self.root / ".ansible").exists(),
            "bootstrap must not create repo-root .ansible (use workspace/.ansible/collections)",
        )
        collections = ctx.workspace_root / ".ansible" / "collections"
        self.assertTrue(
            collections.is_dir(),
            f"expected galaxy collections root under workspace: {collections}",
        )


class BootstrapRequirementsDiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        seed_org_baseline_fixture(self.root)
        seed_local_playbook_repo_stubs(self.root)
        self.workspace = self.root / "workspace" / "k8s.example.com"
        self.workspace.mkdir(parents=True)
        self._env_patch = os.environ.copy()
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self.baseline = load_org_baseline_cluster_config(self.root)
        self.playbooks = _local_playbooks_config(self.root)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_patch)
        self._tmp.cleanup()

    def test_discovery_follows_phase_order_and_skips_missing(self) -> None:
        files = discover_playbook_requirements_files(
            self.playbooks,
            self.baseline.phases,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(len(files), 3)
        self.assertFalse(any("atlas-compute-provision" in str(path) for path in files))
        foundation = self.root / "atlas-node-foundation" / PLAYBOOK_REQUIREMENTS_FILENAME
        self.assertEqual(files[0], foundation.resolve())

    def test_discovery_deduplicates_shared_paths(self) -> None:
        duplicate = self.root / "shared" / PLAYBOOK_REQUIREMENTS_FILENAME
        duplicate.parent.mkdir(parents=True)
        duplicate.write_text("---\ncollections: []\n", encoding="utf-8")
        repos = dict(self.playbooks.repos)
        for name in ("atlas-k8s-core", "atlas-k8s-addons"):
            repos[name] = replace(
                repos[name],
                source="local",
                path="shared",
                path_relative_to="repo_root",
            )
        playbooks = replace(self.playbooks, repos=repos)
        files = discover_playbook_requirements_files(
            playbooks,
            self.baseline.phases,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(files.count(duplicate.resolve()), 1)

    def test_env_value_roundtrip(self) -> None:
        paths = [
            self.root / "atlas-node-foundation" / PLAYBOOK_REQUIREMENTS_FILENAME,
            self.root / "atlas-k8s-core" / PLAYBOOK_REQUIREMENTS_FILENAME,
        ]
        value = playbook_requirements_env_value(paths)
        self.assertIn(":", value)
        self.assertEqual(len(value.split(":")), 2)


if __name__ == "__main__":
    unittest.main()
