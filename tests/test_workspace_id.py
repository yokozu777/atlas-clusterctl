"""Tests for clusterctl.workspace_id."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.workspace_id import (
    WorkspaceIdSource,
    resolve_cluster_domain_from_vars,
    resolve_k8s_cluster_domain_from_vars,
    resolve_workspace_id,
    resolve_workspace_id_details,
)


class WorkspaceIdTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._env_backup = os.environ.get("CLUSTER_WORKSPACE_ID")
        os.environ.pop("CLUSTER_WORKSPACE_ID", None)

    def tearDown(self) -> None:
        if self._env_backup is None:
            os.environ.pop("CLUSTER_WORKSPACE_ID", None)
        else:
            os.environ["CLUSTER_WORKSPACE_ID"] = self._env_backup
        self._tmpdir.cleanup()

    def _write_vars(self, data: dict) -> list[Path]:
        path = self.root / "cluster.yml"
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return [path]

    def test_cluster_domain_resolves_dns_suffix(self) -> None:
        vars_data = {
            "dns_domain_suffix": "lab.example.com",
            "cluster_domain": "k8s.{{ dns_domain_suffix }}",
            "k8s_cluster_domain": "{{ cluster_domain }}",
        }
        self.assertEqual(resolve_cluster_domain_from_vars(vars_data), "k8s.lab.example.com")
        self.assertEqual(resolve_k8s_cluster_domain_from_vars(vars_data), "k8s.lab.example.com")

        paths = self._write_vars(vars_data)
        resolution = resolve_workspace_id_details(self.root, group_var_files=paths)
        self.assertEqual(resolution.workspace_id, "k8s.lab.example.com")
        self.assertEqual(resolution.source, WorkspaceIdSource.CLUSTER_DOMAIN)

    def test_legacy_k8s_cluster_domain_not_workspace_fallback(self) -> None:
        vars_data = {
            "dns_domain_suffix": "example.com",
            "k8s_cluster_domain": "k8s.{{ dns_domain_suffix }}",
        }
        paths = self._write_vars(vars_data)
        with self.assertRaises(ValueError) as ctx:
            resolve_workspace_id_details(self.root, group_var_files=paths)
        self.assertIn("cluster workspace id is empty", str(ctx.exception))
        # Helper still resolves k8s_cluster_domain for validate / alias checks.
        self.assertEqual(
            resolve_k8s_cluster_domain_from_vars(vars_data),
            "k8s.example.com",
        )

    def test_ceph_only_cluster_domain(self) -> None:
        vars_data = {
            "dns_domain_suffix": "example.com",
            "cluster_domain": "ceph.{{ dns_domain_suffix }}",
        }
        paths = self._write_vars(vars_data)
        resolution = resolve_workspace_id_details(self.root, group_var_files=paths)
        self.assertEqual(resolution.workspace_id, "ceph.example.com")
        self.assertEqual(resolution.source, WorkspaceIdSource.CLUSTER_DOMAIN)

    def test_env_override_wins(self) -> None:
        vars_data = {
            "dns_domain_suffix": "example.com",
            "cluster_domain": "k8s.{{ dns_domain_suffix }}",
        }
        os.environ["CLUSTER_WORKSPACE_ID"] = "override.example.com"
        paths = self._write_vars(vars_data)
        resolution = resolve_workspace_id_details(self.root, group_var_files=paths)
        self.assertEqual(resolution.workspace_id, "override.example.com")
        self.assertEqual(resolution.source, WorkspaceIdSource.ENV)

    def test_cluster_yaml_override(self) -> None:
        vars_data = {
            "dns_domain_suffix": "example.com",
            "cluster_domain": "k8s.{{ dns_domain_suffix }}",
        }
        paths = self._write_vars(vars_data)
        resolution = resolve_workspace_id_details(
            self.root,
            group_var_files=paths,
            override="yaml.override.com",
        )
        self.assertEqual(resolution.workspace_id, "yaml.override.com")
        self.assertEqual(resolution.source, WorkspaceIdSource.CLUSTER_YAML)

    def test_literal_cluster_workspace_id(self) -> None:
        vars_data = {
            "cluster_workspace_id": "fixed.workspace.example.com",
            "cluster_domain": "ignored.{{ dns_domain_suffix }}",
            "dns_domain_suffix": "example.com",
        }
        paths = self._write_vars(vars_data)
        resolution = resolve_workspace_id_details(self.root, group_var_files=paths)
        self.assertEqual(resolution.workspace_id, "fixed.workspace.example.com")
        self.assertEqual(resolution.source, WorkspaceIdSource.VARS_LITERAL)

    def test_unresolved_jinja_raises(self) -> None:
        vars_data = {"cluster_domain": "{{ unknown_var }}"}
        paths = self._write_vars(vars_data)
        with self.assertRaises(ValueError):
            resolve_workspace_id(self.root, group_var_files=paths)

    def test_invalid_charset_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_workspace_id_details(override="bad id/with/slash")


if __name__ == "__main__":
    unittest.main()
