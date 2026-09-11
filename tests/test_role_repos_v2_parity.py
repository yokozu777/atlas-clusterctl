"""Tests for PR-10: v2 playbook_repos derived from effective playbooks cascade."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.ansible_config import configure_boundary_env, summary_lines_for_boundary
from clusterctl.ansible_env import export_phase
from clusterctl.context import ClusterContext
from clusterctl.playbooks_resolve import effective_playbooks_config
from clusterctl.cluster_config import load_cluster_config
from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import (
    org_baseline_required_repo_names,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_resolve import effective_playbooks_config
from clusterctl.playbooks_repos import resolved_playbook_repos_from_config
from clusterctl.validate import Severity, validate_cluster
from tests.lab_support import lab_id_for, skip_unless_stack

class RoleReposV2ParityTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        self._saved_playbooks = {k: v for k, v in os.environ.items() if k.startswith("PLAYBOOKS_")}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        for key in self._saved_playbooks:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._seed_tree()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for key in list(os.environ):
            if key.startswith("PLAYBOOKS_") and key not in self._saved_playbooks:
                os.environ.pop(key, None)
        for key, value in self._saved_playbooks.items():
            os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_tree(self) -> None:
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        (self.root / "workspace").mkdir(exist_ok=True)
        seed_org_baseline_fixture(self.root)
        seed_local_playbook_repo_stubs(self.root)

        env_policy = self.root / "clusters" / "dev" / "default"
        env_policy.mkdir(parents=True, exist_ok=True)
        (env_policy / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "dev/default",
                    "playbooks": {
                        "atlas-node-foundation": {
                            "source": "local",
                            "path": "atlas-node-foundation",
                            "path_relative_to": "repo_root",
                            "layout": "roles/",
                            "sync": "never",
                        },
                        "atlas-infra-edge": {
                            "source": "local",
                            "path": "atlas-infra-edge",
                            "path_relative_to": "repo_root",
                            "layout": "roles/",
                            "sync": "never",
                        },
                        "atlas-compute-provision": {
                            "source": "local",
                            "path": "atlas-compute-provision",
                            "path_relative_to": "repo_root",
                            "layout": "roles/",
                            "sync": "never",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        for repo in ("atlas-infra-edge", "atlas-compute-provision", "atlas-node-foundation"):
            path = self.root / repo
            (path / "roles" / "demo" / "tasks").mkdir(parents=True, exist_ok=True)
            (path / "roles" / "demo" / "tasks" / "main.yaml").write_text("---\n", encoding="utf-8")
            (path / "playbooks").mkdir(exist_ok=True)
            (path / "playbooks" / "init_nodes.yaml").write_text("---\n", encoding="utf-8")

        leaf = self.root / "clusters" / "dev" / "leaf"
        leaf.mkdir(parents=True, exist_ok=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "dev/leaf",
                    "inventory": "hosts",
                    "execution": {"mode": "local"},
                }
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text(
            "all:\n  children:\n    k8s_masters:\n      hosts:\n        localhost:\n",
            encoding="utf-8",
        )
        (leaf / "pub_keys").mkdir()
        (leaf / "pub_keys" / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True, exist_ok=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "dev/leaf",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                    "provision_stack": "k8s",
                }
            ),
            encoding="utf-8",
        )

    def test_v2_leaf_without_yaml_role_repos_derives_specs(self) -> None:
        cfg = load_cluster_config(
            self.root / "clusters" / "dev" / "leaf",
            "dev/leaf",
            repo_root=self.root,
        )
        self.assertTrue(cfg.playbooks_enabled)
        self.assertTrue(cfg.playbook_repos.is_configured())
        required = org_baseline_required_repo_names(self.root)
        self.assertEqual(set(cfg.playbook_repos.specs), required)
        self.assertFalse(cfg.playbook_repos.cluster_overrides)
        self.assertEqual(cfg.playbook_repos.specs["atlas-node-foundation"].source, "local")
        self.assertEqual(cfg.playbook_repos.specs["atlas-k8s-core"].source, "local")

    def test_resolved_specs_match_playbooks_cascade(self) -> None:
        ctx = ClusterContext.load(cluster_id="dev/leaf")
        playbooks = effective_playbooks_config(ctx)
        derived = resolved_playbook_repos_from_config(playbooks)
        required = org_baseline_required_repo_names(self.root)
        for name in required:
            self.assertEqual(
                ctx.playbook_repos.specs[name].source,
                derived[name].source,
            )

    def test_ansible_env_export_uses_derived_playbook_repos(self) -> None:
        text = export_phase("init", cluster_id="dev/leaf")
        expected = str((self.root / "atlas-node-foundation" / "roles").resolve())
        self.assertIn(f"ANSIBLE_ROLES_PATH={expected}", text)

    def test_configure_boundary_env_local_repo_root(self) -> None:
        ctx = ClusterContext.load(cluster_id="dev/leaf")
        playbooks = effective_playbooks_config(ctx)
        assert ctx.config_v2 is not None and ctx.config_v2.phases is not None
        env: dict[str, str] = {}
        configure_boundary_env(
            env,
            ctx.repo_root,
            "k8s-core",
            playbooks=playbooks,
            phases=ctx.config_v2.phases,
            workspace_root=ctx.workspace_root,
        )
        self.assertEqual(
            env["ANSIBLE_ROLES_PATH"],
            str((self.root / "atlas-k8s-core" / "roles").resolve()),
        )

    def test_summary_lines_work_without_leaf_yaml_role_repos(self) -> None:
        ctx = ClusterContext.load(cluster_id="dev/leaf")
        playbooks = effective_playbooks_config(ctx)
        assert ctx.config_v2 is not None and ctx.config_v2.phases is not None
        lines = summary_lines_for_boundary(
            ctx.repo_root,
            "init",
            playbooks=playbooks,
            phases=ctx.config_v2.phases,
            workspace_root=ctx.workspace_root,
        )
        self.assertTrue(any("schema v2" in line for line in lines))

    def test_local_playbooks_override_clears_git_url(self) -> None:
        ctx = ClusterContext.load(cluster_id="dev/leaf")
        foundation_spec = ctx.playbook_repos.specs["atlas-node-foundation"]
        self.assertEqual(foundation_spec.source, "local")
        self.assertIsNone(foundation_spec.url)
        self.assertIsNone(foundation_spec.ref)

    def test_leaf_playbooks_override_in_cascade(self) -> None:
        leaf_cfg = self.root / "clusters" / "dev" / "leaf" / "cluster.yaml"
        data = yaml.safe_load(leaf_cfg.read_text(encoding="utf-8"))
        data["playbooks"] = {
            "atlas-k8s-core": {
                "source": "local",
                "path": "atlas-k8s-core",
                "path_relative_to": "repo_root",
            }
        }
        leaf_cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
        platform = self.root / "atlas-k8s-core"
        (platform / "00_controller_tooling").mkdir(parents=True)

        ctx = ClusterContext.load(cluster_id="dev/leaf")
        self.assertFalse(ctx.playbook_repos.cluster_overrides)
        self.assertEqual(ctx.playbook_repos.specs["atlas-k8s-core"].source, "local")
        playbooks = effective_playbooks_config(ctx)
        self.assertEqual(playbooks.repos["atlas-k8s-core"].source, "local")

class RoleReposV2ParityRealRepoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self._saved_root = os.environ.get("ATLAS_CLUSTER_ROOT")
        self._saved_playbooks = {k: v for k, v in os.environ.items() if k.startswith("PLAYBOOKS_")}
        for key in self._saved_playbooks:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)

    def tearDown(self) -> None:
        if self._saved_root is None:
            os.environ.pop("ATLAS_CLUSTER_ROOT", None)
        else:
            os.environ["ATLAS_CLUSTER_ROOT"] = self._saved_root
        for key in list(os.environ):
            if key.startswith("PLAYBOOKS_") and key not in self._saved_playbooks:
                os.environ.pop(key, None)
        for key, value in self._saved_playbooks.items():
            os.environ[key] = value

    @skip_unless_stack("k8s")
    def test_k8s_lab_derives_playbook_repos_from_cascade(self) -> None:
        lab = lab_id_for("k8s")
        assert lab is not None
        ctx = ClusterContext.load(cluster_id=lab)
        self.assertTrue(ctx.playbook_repos.is_configured())
        self.assertEqual(set(ctx.playbook_repos.specs), org_baseline_required_repo_names(self.root))
        self.assertNotIn("atlas-infra-edge", ctx.playbook_repos.specs)
        self.assertFalse(ctx.playbook_repos.cluster_overrides)

        # Inventory lab uses git-sourced playbooks (workspace sync); public templates use local.
        for name in ("atlas-node-foundation", "atlas-k8s-core", "atlas-k8s-addons", "atlas-compute-provision"):
            spec = ctx.playbook_repos.specs[name]
            self.assertEqual(spec.source, "git", name)
            self.assertTrue(spec.url, name)

    @skip_unless_stack("k8s")
    def test_k8s_lab_validate_reports_role_repos_from_playbooks(self) -> None:
        lab = lab_id_for("k8s")
        assert lab is not None
        ctx = ClusterContext.load(cluster_id=lab)
        with (
            patch("clusterctl.validate.playbook_repo_layout_ready", return_value=True),
            patch("clusterctl.validate.validate_docker_deep", return_value=[]),
        ):
            report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        codes = {issue.code for issue in report.issues}
        self.assertIn("playbooks_from_cascade", codes)
        self.assertNotIn("playbooks_specs_incomplete", codes)

    @skip_unless_stack("k8s")
    def test_k8s_lab_playbooks_exclude_infra_edge(self) -> None:
        lab = lab_id_for("k8s")
        assert lab is not None
        ctx = ClusterContext.load(cluster_id=lab)
        self.assertNotIn("atlas-infra-edge", ctx.playbook_repos.specs)
        aliases = ctx.config_v2.phases.phase_aliases if ctx.config_v2.phases else {}
        self.assertNotIn("infra", aliases)
        self.assertNotIn("init-infra", aliases)
        self.assertIn("k8s-core", aliases)

if __name__ == "__main__":
    unittest.main()
