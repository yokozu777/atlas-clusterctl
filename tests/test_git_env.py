"""Tests for git_env SSH identity resolution (repo sync)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clusterctl.playbooks_config import PlaybookRepoSpec
from clusterctl.playbooks_sync import (
    playbooks_ssh_key_env_name,
    ssh_key_for_playbook_repo,
)
from clusterctl.repo_sync_git import git_env


class GitEnvTest(unittest.TestCase):
    _ENV_KEYS = ("GIT_SSH_COMMAND", "SSH_KEY", "ATLAS_CLUSTERCTL_CONFIG")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {key: os.environ.get(key) for key in self._ENV_KEYS}
        for key in self._ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTERCTL_CONFIG"] = str(self.root / "missing.yaml")

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_fallback_without_key(self) -> None:
        env = git_env({})
        self.assertEqual(env["GIT_SSH_COMMAND"], "ssh -o StrictHostKeyChecking=no")

    def test_pins_ssh_key_env(self) -> None:
        env = git_env({"SSH_KEY": "/home/u/.ssh/id_ed25519"})
        self.assertIn("-i /home/u/.ssh/id_ed25519", env["GIT_SSH_COMMAND"])
        self.assertIn("IdentitiesOnly=yes", env["GIT_SSH_COMMAND"])

    def test_keeps_existing_identity(self) -> None:
        existing = (
            "ssh -i /tmp/atlas-ssh/id_rsa -o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=no"
        )
        env = git_env(
            {"GIT_SSH_COMMAND": existing, "SSH_KEY": "/should/not/replace"}
        )
        self.assertEqual(env["GIT_SSH_COMMAND"], existing)

    def test_explicit_ssh_key_overrides_existing_identity(self) -> None:
        existing = "ssh -i /default/key -o IdentitiesOnly=yes"
        env = git_env(
            {"GIT_SSH_COMMAND": existing},
            ssh_key="/repo/key",
        )
        self.assertIn("-i /repo/key", env["GIT_SSH_COMMAND"])
        self.assertNotIn("/default/key", env["GIT_SSH_COMMAND"])

    def test_config_git_ssh_key_before_env_ssh_key(self) -> None:
        key = self.root / "config.key"
        key.write_text("dummy\n", encoding="utf-8")
        with mock.patch(
            "clusterctl.repo_sync_git.git_ssh_key_from_user_config",
            return_value=key,
        ):
            env = git_env({"SSH_KEY": "/env/key"})
        self.assertIn(str(key), env["GIT_SSH_COMMAND"])
        self.assertNotIn("/env/key", env["GIT_SSH_COMMAND"])


class PlaybooksSshKeyEnvTest(unittest.TestCase):
    def test_suffix_matches_ref_pattern(self) -> None:
        self.assertEqual(
            playbooks_ssh_key_env_name("atlas-k8s-addons"),
            "PLAYBOOKS_ATLAS_K8S_ADDONS_SSH_KEY",
        )

    def test_reads_overlay_over_os_environ(self) -> None:
        spec = PlaybookRepoSpec(
            name="atlas-k8s-core",
            source="git",
            url="git@example.com:org/repo.git",
            ref="main",
        )
        key = "PLAYBOOKS_ATLAS_K8S_CORE_SSH_KEY"
        saved = os.environ.get(key)
        try:
            os.environ[key] = "/from/os"
            found = ssh_key_for_playbook_repo(spec, {key: "/from/overlay"})
            self.assertEqual(found, "/from/overlay")
        finally:
            if saved is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = saved


if __name__ == "__main__":
    unittest.main()
