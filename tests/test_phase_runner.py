"""Tests for schema v2 phase runner command building (PR-3)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from clusterctl.controller_extra_vars import build_controller_extra_vars, materialize_controller_extra_vars
from clusterctl.phase_runner import build_phase_invocation_command, resolve_phase_playbook_path
from clusterctl.playbooks_config import InvocationSpec, PlaybookEntrySpec


class PhaseRunnerTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)

        self.repo_base = self.root / "atlas-compute-provision"
        self.repo_base.mkdir()
        playbook = self.repo_base / "playbooks" / "provision_nodes.yaml"
        playbook.parent.mkdir(parents=True)
        playbook.write_text("---\n", encoding="utf-8")

        self.inventory = self.root / "clusters" / "lab" / "hosts"
        self.inventory.parent.mkdir(parents=True)
        self.inventory.write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")

        self.workspace = self.root / "workspace" / "k8s.lab"
        self.workspace.mkdir(parents=True)
        (self.workspace / ".ansible").mkdir()
        cluster_vars = self.workspace / ".ansible" / "cluster_playbook_vars.yaml"
        cluster_vars.write_text("cluster_id: lab\n", encoding="utf-8")

        self.config_dir = self.root / "clusters" / "lab"
        (self.config_dir / "group_vars" / "all").mkdir(parents=True)

        self.ctx = MagicMock()
        self.ctx.repo_root = self.root
        self.ctx.config_dir = self.config_dir
        self.ctx.inventory = self.inventory
        self.ctx.cluster_id = "lab/test"
        self.ctx.workspace_id = "k8s.lab"
        self.ctx.workspace_root = self.workspace
        self.ctx.ssh_key = Path("/tmp/test_key")

        self.runner = MagicMock()
        self.runner.ctx = self.ctx
        self.runner._ensure_playbook_extra_vars.return_value = cluster_vars

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_resolve_phase_playbook_path(self) -> None:
        entry = PlaybookEntrySpec(file="playbooks/provision_nodes.yaml", invocations=())
        path = resolve_phase_playbook_path(self.repo_base, entry)
        self.assertEqual(path, (self.repo_base / "playbooks" / "provision_nodes.yaml").resolve())

    def test_build_phase_invocation_command_injects_controller_vars(self) -> None:
        controller_vars = materialize_controller_extra_vars(self.ctx)
        cluster_vars = self.workspace / ".ansible" / "cluster_playbook_vars.yaml"
        entry = PlaybookEntrySpec(file="playbooks/provision_nodes.yaml", invocations=())
        invocation = InvocationSpec(tags="10_foo", limit="localhost")
        cmd = build_phase_invocation_command(
            self.runner,
            repo_base=self.repo_base,
            entry=entry,
            invocation=invocation,
            cluster_extra_vars=cluster_vars,
            controller_extra_vars=controller_vars,
        )
        self.assertIn("ansible-playbook", cmd[0])
        self.assertIn(str(self.repo_base / "playbooks" / "provision_nodes.yaml"), cmd)
        self.assertIn(f"@{controller_vars}", " ".join(cmd))
        cluster_idx = cmd.index(f"@{cluster_vars}")
        controller_idx = cmd.index(f"@{controller_vars}")
        self.assertLess(cluster_idx, controller_idx)
        self.assertIn("--tags", cmd)
        self.assertIn("10_foo", cmd)
        self.assertIn("--limit", cmd)
        self.assertIn("localhost", cmd)

    def test_invocation_limit_wins_over_env_limit(self) -> None:
        saved = os.environ.get("LIMIT")
        try:
            os.environ["LIMIT"] = "from_env"
            controller_vars = materialize_controller_extra_vars(self.ctx)
            cluster_vars = self.workspace / ".ansible" / "cluster_playbook_vars.yaml"
            entry = PlaybookEntrySpec(file="playbooks/provision_nodes.yaml", invocations=())
            invocation = InvocationSpec(tags="all", limit="from_plan")
            cmd = build_phase_invocation_command(
                self.runner,
                repo_base=self.repo_base,
                entry=entry,
                invocation=invocation,
                cluster_extra_vars=cluster_vars,
                controller_extra_vars=controller_vars,
            )
            self.assertIn("--limit", cmd)
            self.assertIn("from_plan", cmd)
            self.assertNotIn("from_env", cmd)
        finally:
            if saved is None:
                os.environ.pop("LIMIT", None)
            else:
                os.environ["LIMIT"] = saved

    def test_env_limit_last_mile_when_invocation_has_none(self) -> None:
        saved = os.environ.get("LIMIT")
        try:
            os.environ["LIMIT"] = "from_env_only"
            controller_vars = materialize_controller_extra_vars(self.ctx)
            cluster_vars = self.workspace / ".ansible" / "cluster_playbook_vars.yaml"
            entry = PlaybookEntrySpec(file="playbooks/provision_nodes.yaml", invocations=())
            invocation = InvocationSpec(tags="all", limit=None)
            cmd = build_phase_invocation_command(
                self.runner,
                repo_base=self.repo_base,
                entry=entry,
                invocation=invocation,
                cluster_extra_vars=cluster_vars,
                controller_extra_vars=controller_vars,
            )
            self.assertIn("--limit", cmd)
            self.assertIn("from_env_only", cmd)
        finally:
            if saved is None:
                os.environ.pop("LIMIT", None)
            else:
                os.environ["LIMIT"] = saved

    def test_controller_extra_vars_payload(self) -> None:
        data = build_controller_extra_vars(self.ctx)
        self.assertEqual(data["cluster_id"], "lab/test")
        self.assertEqual(data["atlas_cluster_root"], str(self.root.resolve()))
        self.assertEqual(data["cluster_inventory"], str(self.inventory.resolve()))


if __name__ == "__main__":
    unittest.main()
