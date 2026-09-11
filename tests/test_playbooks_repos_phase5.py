"""Phase 5 gate: role_repos facade → playbooks_repos API."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
import warnings
from pathlib import Path

import yaml

from clusterctl.cluster_config import load_cluster_config
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import seed_org_baseline_fixture
from clusterctl.playbooks_repos import (
    ResolvedPlaybookRepo,
    ResolvedPlaybooksRepos,
    empty_resolved_playbooks_repos,
)
from clusterctl.playbooks_resolve import (
    build_resolved_playbooks_repos,
    validate_org_baseline_playbooks,
)

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
PLAYBOOKS_DOC = ROOT / "docs" / "playbooks.md"
REPOS_MOD = ROOT / "clusterctl" / "playbooks_repos.py"
SHIM_MOD = ROOT / "clusterctl" / "role_repos.py"


class PlaybooksReposRenamePhase5Test(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def test_canonical_module_exists_and_shim_is_thin(self) -> None:
        self.assertTrue(REPOS_MOD.is_file())
        shim_text = SHIM_MOD.read_text(encoding="utf-8")
        self.assertIn("deprecated", shim_text.lower())
        self.assertIn("playbooks_repos", shim_text)
        self.assertLess(len(shim_text.splitlines()), 120)

    def test_changelog_and_docs_mention_rename(self) -> None:
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("playbooks_repos", changelog)
        self.assertIn("role_repos", changelog)
        docs = PLAYBOOKS_DOC.read_text(encoding="utf-8")
        self.assertIn("playbooks:", docs)

    def test_shim_import_emits_deprecation_warning(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            # Force a fresh import path for the warning side-effect.
            sys_modules_key = "clusterctl.role_repos"
            import sys

            sys.modules.pop(sys_modules_key, None)
            importlib.import_module(sys_modules_key)
        messages = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            any("playbooks_repos" in msg for msg in messages),
            messages,
        )

    def test_shim_aliases_point_at_canonical_types(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from clusterctl import role_repos as shim
            from clusterctl import playbooks_repos as canon

        self.assertIs(shim.RoleRepoSpec, canon.ResolvedPlaybookRepo)
        self.assertIs(shim.RoleReposConfig, canon.ResolvedPlaybooksRepos)
        self.assertIs(shim.empty_role_repos_config, canon.empty_resolved_playbooks_repos)
        self.assertIs(shim.role_repos_specs_from_playbooks, canon.resolved_playbook_repos_from_config)
        self.assertIs(shim.require_playbooks_resolver, canon.require_playbook_repos)

    def test_context_exposes_playbook_repos_with_role_repos_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
            try:
                for key in self._ISOLATED_ENV_KEYS:
                    os.environ.pop(key, None)
                os.environ["ATLAS_CLUSTER_ROOT"] = str(root)
                seed_org_baseline_fixture(root)
                leaf = root / "clusters" / "lab" / "test"
                leaf.mkdir(parents=True)
                (leaf / "hosts").write_text(
                    "all:\n  hosts:\n    localhost:\n", encoding="utf-8"
                )
                (leaf / "pub_keys").mkdir()
                (leaf / "pub_keys" / "localuser.pub").write_text("ssh-rsa t\n", encoding="utf-8")
                gv = leaf / "group_vars" / "all"
                gv.mkdir(parents=True)
                (gv / "atlas-node-foundation.yml").write_text(
                    yaml.safe_dump(
                        {
                            "dns_domain_suffix": "example.com",
                            "cluster_domain": "k8s.example.com",
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                (leaf / "cluster.yaml").write_text(
                    yaml.safe_dump(
                        {
                            "schema_version": 2,
                            "id": "lab/test",
                            "inventory": "hosts",
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                ctx = ClusterContext.load(cluster_id="lab/test")
                self.assertIsInstance(ctx.playbook_repos, ResolvedPlaybooksRepos)
                self.assertIs(ctx.role_repos, ctx.playbook_repos)
                self.assertTrue(ctx.playbooks_enabled)
                self.assertTrue(ctx.playbook_repos.is_configured())
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_leaf_yaml_role_repos_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed_org_baseline_fixture(root)
            cluster_dir = root / "clusters" / "fixture" / "k8s"
            cluster_dir.mkdir(parents=True)
            (cluster_dir / "group_vars" / "all").mkdir(parents=True)
            (cluster_dir / "group_vars" / "all" / "atlas-node-foundation.yml").write_text(
                "dns_domain_suffix: example.com\ncluster_domain: k8s.example.com\n",
                encoding="utf-8",
            )
            (cluster_dir / "hosts").write_text("[all]\nlocalhost\n", encoding="utf-8")
            (cluster_dir / "cluster.yaml").write_text(
                yaml.safe_dump(
                    {
                        "id": "fixture/k8s",
                        "inventory": "hosts",
                        "role_repos": {"atlas-k8s-core": {"ref": "dev"}},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ClusterctlError):
                load_cluster_config(cluster_dir, "fixture/k8s", repo_root=root)

    def test_build_resolved_playbooks_repos_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed_org_baseline_fixture(root)
            os.environ["ATLAS_CLUSTER_ROOT"] = str(root)
            os.environ["PLAYBOOKS_ATLAS_K8S_CORE_REF"] = "phase5-branch"
            try:
                config = validate_org_baseline_playbooks(root)
                self.assertIsInstance(next(iter(config.specs.values())), ResolvedPlaybookRepo)
                from clusterctl.pipeline_fixture import load_org_baseline_cluster_config

                baseline = load_org_baseline_cluster_config(root)
                assert baseline.playbooks is not None
                resolved = build_resolved_playbooks_repos(baseline.playbooks)
                self.assertEqual(resolved.specs["atlas-k8s-core"].ref, "phase5-branch")
                self.assertIsInstance(empty_resolved_playbooks_repos().specs, dict)
            finally:
                os.environ.pop("PLAYBOOKS_ATLAS_K8S_CORE_REF", None)
                os.environ.pop("ATLAS_CLUSTER_ROOT", None)


if __name__ == "__main__":
    unittest.main()
