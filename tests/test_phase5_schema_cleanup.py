"""Phase 5: profile cleanup, playbooks_enabled merge, cluster_id_aliases."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.cluster_config import load_cluster_config
from clusterctl.cluster_config_loader import load_cluster_config_v2_fragments
from clusterctl.cluster_layout import (
    canonical_cluster_id,
    effective_cluster_id_aliases,
    register_cluster_id_aliases,
    reset_cluster_id_aliases_for_tests,
)
from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import seed_org_baseline_fixture
from clusterctl.playbooks_config import (
    ClusterConfigV2,
    merge_cluster_config_v2,
    parse_cluster_config_v2_fragment,
    resolve_playbooks_enabled,
)
from clusterctl.validate import Severity, validate_cluster

class Phase5PlaybooksEnabledMergeTest(unittest.TestCase):
    def test_merge_inherits_base_when_child_omits_flag(self) -> None:
        base = parse_cluster_config_v2_fragment({"playbooks_enabled": True})
        child = parse_cluster_config_v2_fragment({"id": "fixture/k8s"})
        merged = merge_cluster_config_v2(base, child)
        self.assertIsNone(child.playbooks_enabled)
        self.assertTrue(merged.effective_playbooks_enabled())

    def test_merge_child_false_overrides_base_true(self) -> None:
        base = parse_cluster_config_v2_fragment({"playbooks_enabled": True})
        child = parse_cluster_config_v2_fragment({"playbooks_enabled": False})
        merged = merge_cluster_config_v2(base, child)
        self.assertFalse(merged.playbooks_enabled)
        self.assertFalse(merged.effective_playbooks_enabled())

    def test_resolve_prefers_leaf_explicit_false(self) -> None:
        base = parse_cluster_config_v2_fragment({"playbooks_enabled": True})
        enabled = resolve_playbooks_enabled(
            {"playbooks_enabled": False},
            config_v2=base,
        )
        self.assertFalse(enabled)

class Phase5ClusterIdAliasesTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        reset_cluster_id_aliases_for_tests()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)

    def tearDown(self) -> None:
        reset_cluster_id_aliases_for_tests()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_cascade_aliases_merge_from_env_policy(self) -> None:
        env_policy = self.root / "clusters" / "fixture" / "default"
        env_policy.mkdir(parents=True)
        (env_policy / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "fixture/default",
                    "cluster_id_aliases": {"legacy-lab": "fixture/k8s"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        leaf = self.root / "clusters" / "fixture" / "k8s"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump({"schema_version": 2, "id": "fixture/k8s", "inventory": "hosts"}),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        (leaf / "group_vars" / "all").mkdir(parents=True)
        (leaf / "group_vars" / "all" / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "fixture/k8s",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        paths = [
            self.root / "clusters" / "default" / "default" / "cluster.yaml",
            env_policy / "cluster.yaml",
            leaf / "cluster.yaml",
        ]
        merged = load_cluster_config_v2_fragments(paths)
        register_cluster_id_aliases(merged.cluster_id_aliases)
        aliases = effective_cluster_id_aliases()
        self.assertEqual(aliases["legacy-lab"], "fixture/k8s")
        self.assertEqual(canonical_cluster_id("legacy-lab", warn=False), "fixture/k8s")

    def test_alias_usage_emits_deprecation_warning(self) -> None:
        register_cluster_id_aliases({"legacy-lab": "fixture/k8s"})
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(canonical_cluster_id("legacy-lab"), "fixture/k8s")
            self.assertEqual(canonical_cluster_id("legacy-lab"), "fixture/k8s")
        output = stderr.getvalue()
        self.assertIn("deprecated cluster id alias", output.lower())
        self.assertEqual(output.count("legacy-lab"), 1)

class Phase5ProfileAndSchemaTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)
        self._seed_leaf()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_leaf(self) -> None:
        leaf = self.root / "clusters" / "lab" / "test"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab/test",
                    "inventory": "hosts",
                    "playbooks_enabled": True,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text(
            "all:\n  children:\n    k8s_masters:\n      hosts:\n        localhost:\n",
            encoding="utf-8",
        )
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/test",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                    "provision_stack": "k8s",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (leaf / "pub_keys").mkdir()
        (leaf / "pub_keys" / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")

    def test_validate_errors_on_legacy_profile_for_deployable(self) -> None:
        leaf_cfg = self.root / "clusters" / "lab" / "test" / "cluster.yaml"
        data = yaml.safe_load(leaf_cfg.read_text(encoding="utf-8"))
        data["profile"] = "full"
        leaf_cfg.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        ctx = ClusterContext.load(cluster_id="lab/test")
        with (
            patch("clusterctl.validate.playbook_repo_layout_ready", return_value=True),
            patch("clusterctl.validate.validate_docker_deep", return_value=[]),
        ):
            report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        codes = {issue.code for issue in report.issues}
        self.assertIn("profile_legacy_removed", codes)
        errors = [issue for issue in report.issues if issue.code == "profile_legacy_removed"]
        self.assertEqual(errors[0].severity, Severity.ERROR)

    def test_leaf_without_schema_version_warns(self) -> None:
        leaf = self.root / "clusters" / "lab" / "minimal"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "lab/minimal",
                    "inventory": "hosts",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text(
            "all:\n  children:\n    k8s_masters:\n      hosts:\n        localhost:\n",
            encoding="utf-8",
        )
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/minimal",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                    "provision_stack": "k8s",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (leaf / "pub_keys").mkdir()
        (leaf / "pub_keys" / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")
        ctx = ClusterContext.load(cluster_id="lab/minimal")
        with (
            patch("clusterctl.validate.playbook_repo_layout_ready", return_value=True),
            patch("clusterctl.validate.validate_docker_deep", return_value=[]),
        ):
            report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        codes = {issue.code for issue in report.issues}
        self.assertIn("schema_version_implicit", codes)

if __name__ == "__main__":
    unittest.main()
