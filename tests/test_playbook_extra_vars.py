"""Tests for materialized playbook extra-vars (group_vars/all → -e @)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.ansible_runner import AnsibleRunner
from clusterctl.cluster_vars_loader import (
    materialize_playbook_extra_vars,
    playbook_extra_vars_path,
)
from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import local_playbooks_override_block, seed_org_baseline_fixture


class PlaybookExtraVarsTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        self.cluster = self.root / "clusters" / "lab"
        self._seed_cluster()
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_cluster(self) -> None:
        all_dir = self.cluster / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        seed_org_baseline_fixture(self.root)
        (self.cluster / "cluster.yaml").write_text(
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
        (self.cluster / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
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
        (all_dir / "atlas-compute-provision.yml").write_text(
            yaml.safe_dump(
                {
                    "provision_pve_inventory_group": "proxmox",
                    "provision_pve_host": "192.168.1.20",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        from clusterctl.pipeline_fixture import seed_local_playbook_repo_stubs
        seed_local_playbook_repo_stubs(self.root)

    def test_materialize_writes_merged_group_vars(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        path = materialize_playbook_extra_vars(ctx.config_dir, ctx.workspace_root)
        self.assertEqual(path, playbook_extra_vars_path(ctx.workspace_root))
        self.assertTrue(path.is_file())
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data["provision_pve_inventory_group"], "proxmox")
        self.assertEqual(data["cluster_domain"], "k8s.example.com")
        self.assertNotIn("atlas_cluster_root", data)

    def test_ansible_runner_includes_extra_vars_file(self) -> None:
        from clusterctl.phase_runner import build_phase_invocation_command
        from clusterctl.playbooks_config import InvocationSpec, PlaybookEntrySpec

        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        runner = AnsibleRunner(ctx)
        cluster_vars = materialize_playbook_extra_vars(ctx.config_dir, ctx.workspace_root)
        controller_vars = runner._ensure_controller_extra_vars()
        repo_base = ctx.repo_root.parent / "atlas-compute-provision"
        if not (repo_base / "playbooks" / "build_templates.yaml").is_file():
            self.skipTest("atlas-compute-provision sibling playbooks not present")
        entry = PlaybookEntrySpec(file="playbooks/build_templates.yaml", invocations=())
        invocation = InvocationSpec(tags="00_check_pve_templates", extra_e=("override_key=1",))
        cmd = build_phase_invocation_command(
            runner,
            repo_base=repo_base,
            entry=entry,
            invocation=invocation,
            cluster_extra_vars=cluster_vars,
            controller_extra_vars=controller_vars,
        )
        self.assertEqual(cmd[cmd.index(f"@{cluster_vars}") - 1], "-e")
        self.assertLess(cmd.index(f"@{cluster_vars}"), cmd.index(f"@{controller_vars}"))
        self.assertLess(cmd.index(f"@{controller_vars}"), cmd.index("override_key=1"))


if __name__ == "__main__":
    unittest.main()
