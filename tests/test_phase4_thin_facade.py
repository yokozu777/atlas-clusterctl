"""Phase 4/5: playbooks_repos is canonical; role_repos is a deprecated shim."""

from __future__ import annotations

import os
import tempfile
import unittest
import warnings
from pathlib import Path

import yaml

from clusterctl.cluster_config import load_cluster_config
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import load_org_baseline_cluster_config, seed_org_baseline_fixture
from clusterctl.playbooks_resolve import build_resolved_playbooks_repos, validate_org_baseline_playbooks
from clusterctl.playbooks_repos import ORG_BASELINE_CLUSTER_YAML


class Phase4ThinFacadeTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT",)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved_env = {key: os.environ.get(key) for key in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_role_repos_module_is_deprecated_shim(self) -> None:
        role_repos_path = Path(__file__).resolve().parents[1] / "clusterctl" / "role_repos.py"
        text = role_repos_path.read_text(encoding="utf-8")
        line_count = len(text.splitlines())
        self.assertLess(
            line_count,
            120,
            f"role_repos.py should stay a thin shim (got {line_count} lines)",
        )
        self.assertIn("playbooks_repos", text)
        self.assertIn("DeprecationWarning", text)

    def test_validate_alias_points_to_playbooks_validate(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from clusterctl.role_repos import validate_role_repos_defaults_file

        self.assertIs(validate_role_repos_defaults_file, validate_org_baseline_playbooks)

    def test_build_resolved_playbooks_repos_applies_playbooks_env(self) -> None:
        os.environ["PLAYBOOKS_ATLAS_K8S_CORE_REF"] = "phase4-branch"
        try:
            config = load_org_baseline_cluster_config(self.root)
            assert config.playbooks is not None
            resolved = build_resolved_playbooks_repos(config.playbooks)
            self.assertEqual(resolved.specs["atlas-k8s-core"].ref, "phase4-branch")
        finally:
            os.environ.pop("PLAYBOOKS_ATLAS_K8S_CORE_REF", None)

    def test_leaf_role_repos_in_cluster_yaml_rejected(self) -> None:
        cluster_dir = self.root / "clusters" / "fixture" / "k8s"
        cluster_dir.mkdir(parents=True)
        (cluster_dir / "group_vars" / "all").mkdir(parents=True)
        (cluster_dir / "group_vars" / "all" / "atlas-node-foundation.yml").write_text(
            "dns_domain_suffix: example.com\ncluster_domain: k8s.example.com\n",
            encoding="utf-8",
        )
        (cluster_dir / "hosts").write_text("[all]\nlocalhost\n")
        (cluster_dir / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "fixture/k8s",
                    "inventory": "hosts",
                    "playbooks_enabled": True,
                    "role_repos": {"atlas-k8s-core": {"ref": "dev"}},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ClusterctlError):
            load_cluster_config(cluster_dir, "fixture/k8s", repo_root=self.root)

    def test_context_playbook_repos(self) -> None:
        leaf = self.root / "clusters" / "lab" / "test"
        leaf.mkdir(parents=True)
        (leaf / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        (leaf / "group_vars" / "all").mkdir(parents=True)
        (leaf / "group_vars" / "all" / "atlas-node-foundation.yml").write_text(
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
        self.assertTrue(ctx.playbooks_enabled)
        self.assertIs(ctx.role_repos, ctx.playbook_repos)

    def test_org_baseline_path_constant(self) -> None:
        self.assertEqual(ORG_BASELINE_CLUSTER_YAML, "clusters/default/default/cluster.yaml")


if __name__ == "__main__":
    unittest.main()
