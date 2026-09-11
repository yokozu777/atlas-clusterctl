"""Tests for clusterctl.ansible_env."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.ansible_env import export_phase, export_workspace
from clusterctl.pipeline_fixture import local_playbooks_override_block, seed_org_baseline_fixture


class AnsibleEnvTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = (
        "TMPDIR",
        "ANSIBLE_LOCAL_TEMP",
        "ANSIBLE_CACHE_PLUGIN_CONNECTION",
        "ANSIBLE_COLLECTIONS_PATHS",
        "CLUSTER_WORKSPACE_ROOT",
        "CLUSTER_WORKSPACE_ID",
        "CLUSTER_ID",
    )

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._env_root = os.environ.get("ATLAS_CLUSTER_ROOT")
        self._saved_env = {key: os.environ.get(key) for key in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._seed_cluster()

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self._env_root is None:
            os.environ.pop("ATLAS_CLUSTER_ROOT", None)
        else:
            os.environ["ATLAS_CLUSTER_ROOT"] = self._env_root
        self._tmpdir.cleanup()

    def _seed_cluster(self) -> None:
        cluster = self.root / "clusters" / "lab"
        all_dir = cluster / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        seed_org_baseline_fixture(self.root)
        (cluster / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab",
                    "inventory": "hosts",
                    "playbooks": local_playbooks_override_block(),
                    "execution": {"mode": "local"},
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
        for repo in ("atlas-infra-edge", "atlas-compute-provision", "atlas-node-foundation", "atlas-k8s-core"):
            path = self.root / repo
            path.mkdir()
            if repo == "atlas-k8s-core":
                (path / "00_controller_tooling").mkdir()
            elif repo == "atlas-node-foundation":
                (path / "roles" / "dummy").mkdir(parents=True)
            else:
                (path / "roles" / "dummy").mkdir(parents=True)

    def test_export_workspace_sets_ansible_runtime_paths(self) -> None:
        text = export_workspace(cluster_id="lab")
        ws = self.root / "workspace" / "lab"
        self.assertIn(f"ANSIBLE_CACHE_PLUGIN_CONNECTION={ws / '.ansible_facts_cache'}", text)
        self.assertIn(f"ANSIBLE_COLLECTIONS_PATHS={ws / '.ansible' / 'collections'}", text)
        self.assertIn(f"ANSIBLE_LOCAL_TEMP={ws / '.ansible' / 'tmp'}", text)
        self.assertIn(f"TMPDIR={ws / '.ansible' / 'tmp'}", text)
        self.assertIn(f"CLUSTER_WORKSPACE_ROOT={ws}", text)

    def test_export_phase_includes_roles_path(self) -> None:
        text = export_phase("k8s-core", cluster_id="lab")
        self.assertIn("ANSIBLE_ROLES_PATH=", text)
        self.assertIn("atlas-k8s-core/roles", text)
        self.assertIn("ANSIBLE_LOCAL_TEMP=", text)


if __name__ == "__main__":
    unittest.main()
