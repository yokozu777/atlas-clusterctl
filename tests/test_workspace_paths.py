"""Tests for clusterctl.workspace_paths (controller temp policies)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clusterctl.exceptions import ClusterctlError
from clusterctl.workspace_paths import (
    assert_no_legacy_repo_root_ansible,
    configure_workspace_ansible_env,
    container_controller_ansible_tmp_dir,
    purge_legacy_repo_root_ansible,
    validate_workspace_ansible_env,
    workspace_ansible_tmp_dir,
    workspace_facts_cache_dir,
)


class WorkspacePathsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmpdir.name) / "workspace" / "k8s.example.com"
        self.ws.mkdir(parents=True)
        self.workspace_id = "k8s.example.com"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_workspace_controller_temp(self) -> None:
        env: dict[str, str] = {"CLUSTER_WORKSPACE_ID": self.workspace_id}
        configure_workspace_ansible_env(
            env,
            self.ws,
            workspace_id=self.workspace_id,
            controller_temp="workspace",
        )
        self.assertEqual(
            env["ANSIBLE_LOCAL_TEMP"],
            str(workspace_ansible_tmp_dir(self.ws)),
        )
        self.assertEqual(
            env["ANSIBLE_CACHE_PLUGIN_CONNECTION"],
            str(workspace_facts_cache_dir(self.ws)),
        )
        self.assertEqual(env["ANSIBLE_FORCE_COLOR"], "true")
        validate_workspace_ansible_env(
            env,
            self.ws,
            workspace_id=self.workspace_id,
            controller_temp="workspace",
        )

    def test_container_controller_temp(self) -> None:
        env: dict[str, str] = {"CLUSTER_WORKSPACE_ID": self.workspace_id}
        configure_workspace_ansible_env(
            env,
            self.ws,
            workspace_id=self.workspace_id,
            controller_temp="container",
            ensure_dirs=True,
        )
        expected_tmp = container_controller_ansible_tmp_dir(self.workspace_id)
        self.assertEqual(env["ANSIBLE_LOCAL_TEMP"], str(expected_tmp))
        self.assertEqual(env["TMPDIR"], str(expected_tmp))
        self.assertTrue(expected_tmp.is_dir())
        self.assertEqual(
            env["ANSIBLE_CACHE_PLUGIN_CONNECTION"],
            str(workspace_facts_cache_dir(self.ws)),
        )
        validate_workspace_ansible_env(
            env,
            self.ws,
            workspace_id=self.workspace_id,
            controller_temp="container",
        )

    def test_container_temp_rejects_workspace_bind_mount(self) -> None:
        env: dict[str, str] = {
            "CLUSTER_WORKSPACE_ID": self.workspace_id,
            "ANSIBLE_CACHE_PLUGIN_CONNECTION": str(workspace_facts_cache_dir(self.ws)),
            "ANSIBLE_LOCAL_TEMP": str(workspace_ansible_tmp_dir(self.ws)),
            "TMPDIR": str(workspace_ansible_tmp_dir(self.ws)),
        }
        with self.assertRaises(ClusterctlError) as exc:
            validate_workspace_ansible_env(
                env,
                self.ws,
                workspace_id=self.workspace_id,
                controller_temp="container",
            )
        self.assertIn("container FS", str(exc.exception))


class PurgeLegacyRepoRootAnsibleTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_purge_removes_nonempty_legacy_dirs(self) -> None:
        ansible = self.root / ".ansible"
        facts = self.root / ".ansible_facts_cache"
        (ansible / "tmp").mkdir(parents=True)
        (facts / "cache.json").parent.mkdir(parents=True)
        (facts / "cache.json").write_text("{}", encoding="utf-8")
        # Workspace copy must stay untouched.
        ws_ansible = self.root / "workspace" / "lab" / ".ansible" / "tmp"
        ws_ansible.mkdir(parents=True)

        removed = purge_legacy_repo_root_ansible(self.root)
        self.assertEqual(
            {path.name for path in removed},
            {".ansible", ".ansible_facts_cache"},
        )
        self.assertFalse(ansible.exists())
        self.assertFalse(facts.exists())
        self.assertTrue(ws_ansible.is_dir())
        assert_no_legacy_repo_root_ansible(self.root)

    def test_purge_is_idempotent(self) -> None:
        self.assertEqual(purge_legacy_repo_root_ansible(self.root), ())
        (self.root / ".ansible" / "tmp").mkdir(parents=True)
        first = purge_legacy_repo_root_ansible(self.root)
        self.assertEqual([p.name for p in first], [".ansible"])
        self.assertEqual(purge_legacy_repo_root_ansible(self.root), ())


if __name__ == "__main__":
    unittest.main()
