"""Tests for clusterctl.repo_conventions."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.pipeline_fixture import seed_org_baseline_fixture
from clusterctl.repo_conventions import check_repo_conventions
from clusterctl.playbooks_repos import ORG_BASELINE_CLUSTER_YAML


class RepoConventionsTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "CLUSTER_WORKSPACE_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved_env = {key: os.environ.get(key) for key in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._write_active_cluster()
        self._seed_cluster()

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _write_active_cluster(self) -> None:
        (self.root / ".cluster-active").write_text("lab\n", encoding="utf-8")

    def _seed_cluster(self) -> None:
        cluster = self.root / "clusters" / "lab"
        all_dir = cluster / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        (cluster / "cluster.yaml").write_text(
            yaml.safe_dump({"id": "lab", "inventory": "hosts"}, sort_keys=False),
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
        (self.root / "ansible.cfg").write_text(
            "[defaults]\nfact_caching = jsonfile\n",
            encoding="utf-8",
        )
        seed_org_baseline_fixture(self.root)

    def _seed_legacy_in_repo_repos(self) -> None:
        from clusterctl.pipeline_fixture import seed_local_playbook_repo_stubs
        seed_local_playbook_repo_stubs(self.root)

    def _findings_by_code(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for finding in check_repo_conventions(self.root):
            grouped.setdefault(finding.code, []).append(finding.severity)
        return grouped

    def test_legacy_root_ansible_paths_are_errors(self) -> None:
        (self.root / ".ansible").mkdir()
        (self.root / ".ansible" / "tmp").mkdir()
        grouped = self._findings_by_code()
        self.assertIn("legacy_root_path", grouped)
        self.assertIn("error", grouped["legacy_root_path"])

    def test_empty_legacy_ansible_dirs_are_ignored(self) -> None:
        (self.root / ".ansible").mkdir()
        (self.root / ".ansible_facts_cache").mkdir()
        grouped = self._findings_by_code()
        self.assertNotIn("legacy_root_path", grouped)

    def test_ansible_cfg_fact_caching_connection_is_error(self) -> None:
        (self.root / "ansible.cfg").write_text(
            "[defaults]\nfact_caching_connection = .ansible_facts_cache\n",
            encoding="utf-8",
        )
        grouped = self._findings_by_code()
        self.assertIn("ansible_cfg_legacy_fact_cache", grouped)

    def test_workspace_ansible_runtime_ok_when_dirs_exist(self) -> None:
        ws = self.root / "workspace" / "lab"
        (ws / ".ansible" / "tmp").mkdir(parents=True)
        (ws / ".ansible_facts_cache").mkdir(parents=True)
        grouped = self._findings_by_code()
        self.assertIn("workspace_ansible_runtime_ok", grouped)

    def test_legacy_in_repo_role_repo_error(self) -> None:
        self._seed_legacy_in_repo_repos()
        grouped = self._findings_by_code()
        self.assertIn("legacy_role_repo_in_repo", grouped)
        self.assertIn("error", grouped["legacy_role_repo_in_repo"])

    def test_legacy_stub_empty_error(self) -> None:
        (self.root / "atlas-node-foundation").mkdir()
        grouped = self._findings_by_code()
        self.assertIn("legacy_role_repo_stub_empty", grouped)
        self.assertIn("error", grouped["legacy_role_repo_stub_empty"])

    def test_legacy_stub_error_when_playbooks_enabled(self) -> None:
        cluster_yaml = self.root / "clusters" / "lab" / "cluster.yaml"
        cluster_yaml.write_text(
            yaml.safe_dump(
                {"id": "lab", "inventory": "hosts", "playbooks_enabled": True},
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / "atlas-k8s-core").mkdir()
        grouped = self._findings_by_code()
        self.assertIn("legacy_role_repo_stub_empty", grouped)
        self.assertIn("error", grouped["legacy_role_repo_stub_empty"])


if __name__ == "__main__":
    unittest.main()
