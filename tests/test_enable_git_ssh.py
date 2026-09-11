"""Tests for GIT_SSH_COMMAND resolution (git_ssh phases / tfstate git)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clusterctl.ansible_runner import (
    AnsibleRunner,
    git_ssh_command_has_identity,
    resolve_git_ssh_command,
)

class ResolveGitSshCommandTest(unittest.TestCase):
    def test_preserves_existing_command_with_identity(self) -> None:
        existing = (
            "ssh -i /tmp/atlas-ssh/id_rsa -o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
        )
        self.assertEqual(
            resolve_git_ssh_command(existing=existing, ssh_key="/other/key"),
            existing,
        )

    def test_builds_from_ssh_key_when_existing_lacks_identity(self) -> None:
        cmd = resolve_git_ssh_command(
            existing="ssh -o StrictHostKeyChecking=no",
            ssh_key="/tmp/atlas-ssh/id_rsa",
        )
        self.assertIn("-i /tmp/atlas-ssh/id_rsa", cmd)
        self.assertIn("IdentitiesOnly=yes", cmd)
        self.assertIn("StrictHostKeyChecking=no", cmd)

    def test_builds_from_ssh_key_when_unset(self) -> None:
        cmd = resolve_git_ssh_command(existing=None, ssh_key="/home/u/.ssh/id_ed25519")
        self.assertIn("-i /home/u/.ssh/id_ed25519", cmd)

    def test_quotes_key_path_with_spaces(self) -> None:
        cmd = resolve_git_ssh_command(existing="", ssh_key="/tmp/my key/id_rsa")
        self.assertIn("-i '/tmp/my key/id_rsa'", cmd)

    def test_fallback_without_key(self) -> None:
        self.assertEqual(
            resolve_git_ssh_command(existing=None, ssh_key=""),
            "ssh -o StrictHostKeyChecking=no",
        )

    def test_has_identity_helper(self) -> None:
        self.assertTrue(git_ssh_command_has_identity("ssh -i /k -o IdentitiesOnly=yes"))
        self.assertFalse(git_ssh_command_has_identity("ssh -o StrictHostKeyChecking=no"))


class EnableGitSshTest(unittest.TestCase):
    _ENV_KEYS = (
        "GIT_SSH_COMMAND",
        "SSH_KEY",
        "TFSTATE_SSH_KEY",
        "ANSIBLE_PRIVATE_KEY_FILE",
    )

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {key: os.environ.get(key) for key in self._ENV_KEYS}
        for key in self._ENV_KEYS:
            os.environ.pop(key, None)
        key = self.root / "id_rsa"
        key.write_text("dummy\n", encoding="utf-8")
        self.key = key

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _runner(self) -> AnsibleRunner:
        ctx = mock.Mock()
        ctx.ssh_key = self.key
        return AnsibleRunner(ctx)
    def test_preserves_docker_git_ssh_command(self) -> None:
        docker_cmd = (
            "ssh -i /tmp/atlas-ssh/id_rsa -o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
        )
        os.environ["GIT_SSH_COMMAND"] = docker_cmd
        os.environ["SSH_KEY"] = "/should/not/replace"
        runner = self._runner()
        runner._enable_git_ssh()
        self.assertEqual(os.environ["GIT_SSH_COMMAND"], docker_cmd)

    def test_rebuilds_when_command_lacks_identity(self) -> None:
        os.environ["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"
        os.environ["SSH_KEY"] = str(self.key)
        runner = self._runner()
        runner._enable_git_ssh()
        self.assertIn(f"-i {self.key}", os.environ["GIT_SSH_COMMAND"])

    def test_prefers_tfstate_ssh_key(self) -> None:
        tfstate = self.root / "tfstate_id_rsa"
        tfstate.write_text("tf\n", encoding="utf-8")
        os.environ.pop("GIT_SSH_COMMAND", None)
        os.environ["SSH_KEY"] = str(self.key)
        os.environ["TFSTATE_SSH_KEY"] = str(tfstate)
        runner = self._runner()
        runner._enable_git_ssh()
        self.assertIn(str(tfstate), os.environ["GIT_SSH_COMMAND"])
        self.assertNotIn(str(self.key), os.environ["GIT_SSH_COMMAND"])

    def test_idempotent(self) -> None:
        os.environ["SSH_KEY"] = str(self.key)
        runner = self._runner()
        runner._enable_git_ssh()
        first = os.environ["GIT_SSH_COMMAND"]
        runner._enable_git_ssh()
        self.assertEqual(os.environ["GIT_SSH_COMMAND"], first)

    def test_dry_run_prints_without_mutating_when_already_set(self) -> None:
        # dry-run still computes; when existing has -i, keep it and print
        docker_cmd = "ssh -i /tmp/atlas-ssh/id_rsa -o IdentitiesOnly=yes"
        os.environ["GIT_SSH_COMMAND"] = docker_cmd
        runner = self._runner()
        with mock.patch("builtins.print") as printed:
            runner._enable_git_ssh(dry_run=True)
        printed.assert_called()
        self.assertIn("GIT_SSH_COMMAND", printed.call_args[0][0])
        self.assertEqual(os.environ["GIT_SSH_COMMAND"], docker_cmd)


if __name__ == "__main__":
    unittest.main()
