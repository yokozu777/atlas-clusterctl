"""Tests for ANSIBLE_ROLES_PATH resolution (schema v2 playbooks entries)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.ansible_config import (
    configure_boundary_env,
    resolve_ansible_roles_path_for_boundary,
    summary_lines_for_boundary,
)
from clusterctl.ansible_env import export_phase
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import local_playbooks_override_block, seed_local_playbook_repo_stubs, seed_org_baseline_fixture
from clusterctl.playbooks_resolve import effective_playbooks_config
from clusterctl.playbooks_repos import require_playbook_repos


class AnsibleRolesPathTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = (
        "TMPDIR",
        "ANSIBLE_LOCAL_TEMP",
        "ANSIBLE_CACHE_PLUGIN_CONNECTION",
        "CLUSTER_WORKSPACE_ROOT",
        "CLUSTER_WORKSPACE_ID",
        "CLUSTER_ID",
        "ATLAS_CLUSTER_ROOT",
    )

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
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
        seed_local_playbook_repo_stubs(self.root)

    def _playbooks_and_phases(self, ctx: ClusterContext):
        assert ctx.config_v2 is not None
        assert ctx.config_v2.phases is not None
        return effective_playbooks_config(ctx), ctx.config_v2.phases

    def test_legacy_layout_rejected(self) -> None:
        org_baseline = self.root / "clusters" / "default" / "default" / "cluster.yaml"
        if org_baseline.is_file():
            org_baseline.unlink()
        cluster_yaml = self.root / "clusters" / "lab" / "cluster.yaml"
        cluster_yaml.write_text(
            yaml.safe_dump({"id": "lab", "inventory": "hosts"}, sort_keys=False),
            encoding="utf-8",
        )
        ctx = ClusterContext.load(cluster_id="lab")
        with self.assertRaises(ClusterctlError) as exc:
            require_playbook_repos(ctx.playbooks_enabled, ctx.playbook_repos)
        self.assertIn("required", str(exc.exception).lower())

    def test_boundary_alias_resolves_roles_path(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab")
        playbooks, phases = self._playbooks_and_phases(ctx)
        path = resolve_ansible_roles_path_for_boundary(
            "k8s-core",
            playbooks=playbooks,
            phases=phases,
            workspace_root=ctx.workspace_root,
            repo_root_path=self.root,
        )
        self.assertEqual(
            Path(path),
            (self.root / "atlas-k8s-core" / "roles").resolve(),
        )

    def test_boundary_phase_ref_resolves_roles_path(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab")
        playbooks, phases = self._playbooks_and_phases(ctx)
        path = resolve_ansible_roles_path_for_boundary(
            "atlas-k8s-core/cluster",
            playbooks=playbooks,
            phases=phases,
            workspace_root=ctx.workspace_root,
            repo_root_path=self.root,
        )
        self.assertEqual(
            Path(path),
            (self.root / "atlas-k8s-core" / "roles").resolve(),
        )

    def test_configure_boundary_env_uses_entry_ansible(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab")
        playbooks, phases = self._playbooks_and_phases(ctx)
        env: dict[str, str] = {}
        phase_ref = configure_boundary_env(
            env,
            ctx.repo_root,
            "k8s-addons",
            playbooks=playbooks,
            phases=phases,
            workspace_root=ctx.workspace_root,
        )
        self.assertEqual(phase_ref, "atlas-k8s-addons/addons")
        self.assertEqual(
            env["ANSIBLE_ROLES_PATH"],
            str((self.root / "atlas-k8s-addons" / "roles").resolve()),
        )
        self.assertEqual(env["ANSIBLE_FORKS"], "100")

    def test_export_phase_role_repos_local(self) -> None:
        text = export_phase("k8s-core", cluster_id="lab")
        self.assertIn(f"ANSIBLE_ROLES_PATH={self.root / 'atlas-k8s-core' / 'roles'}", text)

    def test_summary_lines_shows_schema_v2_layout(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab")
        playbooks, phases = self._playbooks_and_phases(ctx)
        lines = summary_lines_for_boundary(
            ctx.repo_root,
            "k8s-core",
            playbooks=playbooks,
            phases=phases,
            workspace_root=ctx.workspace_root,
        )
        self.assertTrue(any("schema v2" in line for line in lines))
        self.assertTrue(any("atlas-k8s-core/cluster" in line for line in lines))

    def test_git_materialized_path_required(self) -> None:
        cluster_yaml = self.root / "clusters" / "lab" / "cluster.yaml"
        cluster_yaml.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab",
                    "inventory": "hosts",
                    "execution": {"mode": "local"},
                    "playbooks": {
                        "atlas-infra-edge": {
                            "source": "git",
                            "url": "git@example.com/org/atlas-infra-edge.git",
                            "ref": "main",
                            "layout": "roles/",
                            "entries": {
                                "infra": {
                                    "file": "playbooks/infra_hosts.yaml",
                                    "invocations": [{"tags": "all"}],
                                }
                            },
                        }
                    },
                    "phases": [{"infra": "atlas-infra-edge/infra"}],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        ctx = ClusterContext.load(cluster_id="lab")
        playbooks, phases = self._playbooks_and_phases(ctx)
        with self.assertRaises(ClusterctlError) as exc:
            resolve_ansible_roles_path_for_boundary(
                "infra",
                playbooks=playbooks,
                phases=phases,
                workspace_root=ctx.workspace_root,
                repo_root_path=self.root,
            )
        self.assertIn("not ready", str(exc.exception).lower())


if __name__ == "__main__":
    unittest.main()
