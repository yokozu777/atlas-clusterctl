"""Tests for controller extra-vars contract (PR-5 group_vars controller contract)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from clusterctl.cluster_vars_loader import materialize_playbook_extra_vars
from clusterctl.controller_extra_vars import (
    CONTROLLER_CONTRACT_KEYS,
    build_controller_extra_vars,
    materialize_controller_extra_vars,
    strip_controller_contract_keys,
    validate_controller_contract,
)
from clusterctl.phase_runner import build_phase_invocation_command
from clusterctl.playbooks_config import InvocationSpec, PlaybookEntrySpec


class ControllerContractTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)

        self.config_dir = self.root / "clusters" / "lab" / "test"
        all_dir = self.config_dir / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        (self.config_dir / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        (self.config_dir / "pub_keys").mkdir()
        (self.config_dir / "pub_keys" / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")

        (all_dir / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "atlas_cluster_root": "{{ playbook_dir | regex_replace('/playbooks/?$', '') }}",
                    "cluster_id": "lab/test",
                    "cluster_config_dir": "{{ atlas_cluster_root }}/clusters/{{ cluster_id }}",
                    "cluster_pub_keys_dir": "{{ cluster_config_dir }}/pub_keys",
                    "cluster_domain": "k8s.example.com",
                    "dns_domain_suffix": "example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (all_dir / "atlas-compute-provision.yml").write_text(
            yaml.safe_dump(
                {
                    "provision_hosts_file": "{{ cluster_config_dir }}/hosts",
                    "provision_pve_inventory_group": "proxmox",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        self.workspace = self.root / "workspace" / "k8s.example.com"
        self.workspace.mkdir(parents=True)
        (self.root / "workspace").mkdir(exist_ok=True)

        self.inventory = self.config_dir / "hosts"
        self.ctx = MagicMock()
        self.ctx.repo_root = self.root
        self.ctx.config_dir = self.config_dir
        self.ctx.inventory = self.inventory
        self.ctx.cluster_id = "lab/test"
        self.ctx.workspace_id = "k8s.example.com"
        self.ctx.workspace_root = self.workspace
        self.ctx.ssh_key = Path("/tmp/test_key")

        self.repo_base = self.root / "atlas-compute-provision"
        self.repo_base.mkdir()
        playbook = self.repo_base / "playbooks" / "provision_nodes.yaml"
        playbook.parent.mkdir(parents=True)
        playbook.write_text("---\n", encoding="utf-8")

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_strip_controller_contract_keys(self) -> None:
        merged = {
            "atlas_cluster_root": "jinja",
            "cluster_id": "lab/test",
            "provision_pve_inventory_group": "proxmox",
            "cluster_domain": "k8s.example.com",
        }
        stripped = strip_controller_contract_keys(merged)
        self.assertNotIn("atlas_cluster_root", stripped)
        self.assertNotIn("cluster_id", stripped)
        self.assertEqual(stripped["provision_pve_inventory_group"], "proxmox")

    def test_materialize_excludes_controller_keys(self) -> None:
        path = materialize_playbook_extra_vars(self.config_dir, self.workspace)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key in CONTROLLER_CONTRACT_KEYS:
            self.assertNotIn(key, data)
        self.assertEqual(data["cluster_domain"], "k8s.example.com")
        self.assertEqual(data["provision_pve_inventory_group"], "proxmox")

    def test_build_controller_extra_vars_absolute_paths(self) -> None:
        data = build_controller_extra_vars(self.ctx)
        self.assertEqual(data["atlas_cluster_root"], str(self.root.resolve()))
        self.assertEqual(data["atlas_clusters_root"], str((self.root / "clusters").resolve()))
        self.assertEqual(data["atlas_inventory_root"], str(self.root.resolve()))
        self.assertEqual(data["cluster_config_dir"], str(self.config_dir.resolve()))
        self.assertEqual(data["cluster_inventory"], str(self.inventory.resolve()))
        self.assertEqual(data["provision_hosts_file"], str(self.inventory.resolve()))
        self.assertEqual(
            data["provision_ssh_public_key_file"],
            str((self.config_dir / "pub_keys" / "localuser.pub").resolve()),
        )
        self.assertEqual(data["cluster_workspace_root"], str(self.workspace.resolve()))

    def test_materialize_controller_extra_vars_file(self) -> None:
        path = materialize_controller_extra_vars(self.ctx)
        self.assertTrue(path.is_file())
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data["cluster_id"], "lab/test")

    def test_validate_controller_contract_ok(self) -> None:
        self.assertEqual(validate_controller_contract(self.ctx), [])

    def test_validate_controller_contract_missing_pub_key(self) -> None:
        (self.config_dir / "pub_keys" / "localuser.pub").unlink()
        errors = validate_controller_contract(self.ctx)
        self.assertTrue(any("provision_ssh_public_key_file" in item for item in errors))

    def test_phase_command_controller_vars_after_cluster_vars(self) -> None:
        cluster_vars = materialize_playbook_extra_vars(self.config_dir, self.workspace)
        controller_vars = materialize_controller_extra_vars(self.ctx)
        runner = MagicMock()
        runner.ctx = self.ctx
        entry = PlaybookEntrySpec(file="playbooks/provision_nodes.yaml", invocations=())
        invocation = InvocationSpec(tags="all")
        cmd = build_phase_invocation_command(
            runner,
            repo_base=self.repo_base,
            entry=entry,
            invocation=invocation,
            cluster_extra_vars=cluster_vars,
            controller_extra_vars=controller_vars,
        )
        cluster_idx = cmd.index(f"@{cluster_vars}")
        controller_idx = cmd.index(f"@{controller_vars}")
        self.assertLess(cluster_idx, controller_idx)


if __name__ == "__main__":
    unittest.main()
