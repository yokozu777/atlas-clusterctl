"""Tests for clusterctl.cluster_vars_loader and group_vars layout."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config import load_cluster_config
from clusterctl.cluster_vars_loader import (
    CONVENTIONAL_GROUP_VARS_ALL,
    CONVENTIONAL_PRODUCT_REPOS,
    discover_group_vars_all,
    discover_legacy_secrets_overlays,
    discover_secrets_overlays,
    is_product_secrets_overlay,
    load_cluster_vars,
    materialize_playbook_extra_vars,
    secrets_file_configured,
    validate_secrets_content,
)
from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import local_playbooks_override_block, seed_org_baseline_fixture
from clusterctl.playbooks_repos import ORG_BASELINE_CLUSTER_YAML
from clusterctl.validate import Severity, format_report_text, validate_cluster

class GroupVarsLayoutTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        self.cluster = self.root / "clusters" / "lab"
        self._write_minimal_cluster()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _write_minimal_cluster(self) -> None:
        all_dir = self.cluster / "group_vars" / "all"
        all_dir.mkdir(parents=True)
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
        (self.cluster / "hosts").write_text(
            'all:\n  children:\n    k8s_masters:\n      hosts:\n        m1: {}\n',
            encoding="utf-8",
        )
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
        (all_dir / "atlas-node-foundation.yml").write_text(
            yaml.safe_dump({"admin_user": "localuser"}, sort_keys=False),
            encoding="utf-8",
        )
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        seed_org_baseline_fixture(self.root)
        for repo in ("atlas-infra-edge", "atlas-compute-provision", "atlas-node-foundation", "atlas-k8s-core"):
            path = self.root / repo
            path.mkdir()
            if repo == "atlas-k8s-core":
                (path / "00_controller_tooling").mkdir()
            elif repo == "atlas-node-foundation":
                (path / "roles" / "dummy").mkdir(parents=True)
            else:
                (path / "roles").mkdir()

    def test_discover_order(self) -> None:
        files = discover_group_vars_all(self.cluster)
        names = [path.name for path in files]
        # Alphabetical: atlas-* before cluster.yml
        self.assertEqual(names, ["atlas-node-foundation.yml", "cluster.yml"])

    def test_discover_any_yml_alphabetical_secrets_last(self) -> None:
        all_dir = self.cluster / "group_vars" / "all"
        (all_dir / "zzz_stack.yml").write_text("from_zzz: 1\n", encoding="utf-8")
        (all_dir / "aaa_early.yml").write_text("from_aaa: 1\n", encoding="utf-8")
        (all_dir / "atlas-kafka.yml").write_text("kafka_port: 9092\n", encoding="utf-8")
        (all_dir / "atlas-redis.secrets.yml").write_text(
            "from_secrets: win\nfrom_aaa: overridden\n", encoding="utf-8"
        )
        (all_dir / "secrets.yml.example").write_text("example_only: 1\n", encoding="utf-8")
        (all_dir / "notes.md").write_text("# ignore\n", encoding="utf-8")
        (all_dir / ".hidden.yml").write_text("hidden: 1\n", encoding="utf-8")
        (all_dir / "extra.yaml").write_text("from_yaml_ext: 1\n", encoding="utf-8")

        names = [path.name for path in discover_group_vars_all(self.cluster)]
        self.assertEqual(
            names,
            [
                "aaa_early.yml",
                "atlas-kafka.yml",
                "atlas-node-foundation.yml",
                "cluster.yml",
                "extra.yaml",
                "zzz_stack.yml",
                "atlas-redis.secrets.yml",
            ],
        )
        self.assertNotIn("secrets.yml.example", names)
        self.assertNotIn("notes.md", names)
        self.assertNotIn(".hidden.yml", names)

        merged = load_cluster_vars(self.cluster)
        self.assertEqual(merged["kafka_port"], 9092)
        self.assertEqual(merged["from_zzz"], 1)
        self.assertEqual(merged["from_yaml_ext"], 1)
        self.assertEqual(merged["from_secrets"], "win")
        self.assertEqual(merged["from_aaa"], "overridden")
        self.assertNotIn("example_only", merged)
        self.assertNotIn("hidden", merged)

    def test_conventional_names_discover_alphabetically_secrets_last(self) -> None:
        """Repo-named conventional set is sorted; legacy secrets.yml not listed."""
        self.assertIn("atlas-k8s-core.yml", CONVENTIONAL_GROUP_VARS_ALL)
        self.assertIn("atlas-k8s-core.secrets.yml", CONVENTIONAL_GROUP_VARS_ALL)
        self.assertIn("atlas-redis.secrets.yml", CONVENTIONAL_GROUP_VARS_ALL)
        self.assertIn("atlas-infra-edge.yml", CONVENTIONAL_GROUP_VARS_ALL)
        self.assertIn("atlas-node-foundation.yml", CONVENTIONAL_GROUP_VARS_ALL)
        self.assertIn("atlas-compute-provision.yml", CONVENTIONAL_GROUP_VARS_ALL)
        self.assertNotIn("repos.yml", CONVENTIONAL_GROUP_VARS_ALL)
        self.assertNotIn("init_nodes.yml", CONVENTIONAL_GROUP_VARS_ALL)
        self.assertNotIn("secrets.yml", CONVENTIONAL_GROUP_VARS_ALL)
        self.assertEqual(list(CONVENTIONAL_GROUP_VARS_ALL), sorted(CONVENTIONAL_GROUP_VARS_ALL))
        self.assertEqual(len(CONVENTIONAL_PRODUCT_REPOS) * 2, len(CONVENTIONAL_GROUP_VARS_ALL))
        self.assertNotIn("cluster.yml", CONVENTIONAL_GROUP_VARS_ALL)

        all_dir = self.cluster / "group_vars" / "all"
        sample = (
            "atlas-k8s-addons.yml",
            "atlas-k8s-core.yml",
            "atlas-infra-edge.yml",
            "atlas-compute-provision.yml",
            "atlas-redis.secrets.yml",
            "secrets.yml",
        )
        for name in sample:
            (all_dir / name).write_text(f"{name.replace('.', '_')}: true\n", encoding="utf-8")
        names = [path.name for path in discover_group_vars_all(self.cluster)]
        self.assertEqual(
            names,
            [
                "atlas-compute-provision.yml",
                "atlas-infra-edge.yml",
                "atlas-k8s-addons.yml",
                "atlas-k8s-core.yml",
                "atlas-node-foundation.yml",
                "cluster.yml",
                "atlas-redis.secrets.yml",
            ],
        )
        self.assertEqual(
            [p.name for p in discover_legacy_secrets_overlays(self.cluster)],
            ["secrets.yml"],
        )

    def test_legacy_monolith_not_merged(self) -> None:
        all_dir = self.cluster / "group_vars" / "all"
        (all_dir / "atlas-redis.yml").write_text("vip_auth_pass: catalog\n", encoding="utf-8")
        (all_dir / "atlas-redis.secrets.yml").write_text("vip_auth_pass: product\n", encoding="utf-8")
        (all_dir / "secrets.yml").write_text("vip_auth_pass: legacy\n", encoding="utf-8")
        names = [path.name for path in discover_group_vars_all(self.cluster)]
        self.assertLess(names.index("atlas-redis.yml"), names.index("atlas-redis.secrets.yml"))
        self.assertNotIn("secrets.yml", names)
        self.assertTrue(is_product_secrets_overlay("atlas-redis.secrets.yml"))
        overlays = [p.name for p in discover_secrets_overlays(self.cluster)]
        self.assertEqual(overlays, ["atlas-redis.secrets.yml"])
        self.assertEqual(
            [p.name for p in discover_legacy_secrets_overlays(self.cluster)],
            ["secrets.yml"],
        )
        merged = load_cluster_vars(self.cluster)
        self.assertEqual(merged["vip_auth_pass"], "product")

    def test_arbitrary_filenames_still_merge_without_legacy_warning(self) -> None:
        """Any *.yml merges; no special-case deprecation for old stem names."""
        all_dir = self.cluster / "group_vars" / "all"
        (all_dir / "prepare_hosts.yml").write_text("custom_prepare: true\n", encoding="utf-8")
        (all_dir / "infra.yml").write_text("custom_infra: true\n", encoding="utf-8")
        merged = load_cluster_vars(self.cluster)
        self.assertTrue(merged["custom_prepare"])
        self.assertTrue(merged["custom_infra"])
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        self.assertNotIn(
            "group_vars_legacy_names",
            {issue.code for issue in report.issues},
        )

    def test_legacy_secrets_not_merged_but_detectable(self) -> None:
        all_dir = self.cluster / "group_vars" / "all"
        (all_dir / "zzz.yml").write_text("from_zzz: 1\nfrom_secrets: lose\n", encoding="utf-8")
        (all_dir / "secrets.yaml").write_text("from_secrets: win_yaml\n", encoding="utf-8")
        names = [path.name for path in discover_group_vars_all(self.cluster)]
        self.assertNotIn("secrets.yaml", names)
        merged = load_cluster_vars(self.cluster)
        self.assertEqual(merged["from_secrets"], "lose")
        self.assertEqual(merged["from_zzz"], 1)
        legacy = [p.name for p in discover_legacy_secrets_overlays(self.cluster)]
        self.assertEqual(legacy, ["secrets.yaml"])

        (all_dir / "secrets.yml").write_text("from_secrets: win_yml\n", encoding="utf-8")
        names = [path.name for path in discover_group_vars_all(self.cluster)]
        self.assertNotIn("secrets.yml", names)
        self.assertNotIn("secrets.yaml", names)
        legacy = [p.name for p in discover_legacy_secrets_overlays(self.cluster)]
        self.assertEqual(legacy, ["secrets.yaml", "secrets.yml"])
        merged = load_cluster_vars(self.cluster)
        self.assertEqual(merged["from_secrets"], "lose")

    def test_load_cluster_vars_merge(self) -> None:
        merged = load_cluster_vars(self.cluster)
        self.assertEqual(merged["cluster_domain"], "k8s.example.com")
        self.assertEqual(merged["admin_user"], "localuser")

    def test_materialize_includes_non_whitelist_files(self) -> None:
        all_dir = self.cluster / "group_vars" / "all"
        (all_dir / "atlas-redis.yml").write_text("redis_port: 6379\n", encoding="utf-8")
        (all_dir / "atlas-redis.secrets.yml").write_text("redis_port: 6380\n", encoding="utf-8")
        workspace = self.root / "workspace" / "lab"
        workspace.mkdir(parents=True)
        path = materialize_playbook_extra_vars(self.cluster, workspace)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data["redis_port"], 6380)
        self.assertEqual(data["cluster_domain"], "k8s.example.com")

    def test_cluster_config_discovers_group_vars(self) -> None:
        cfg = load_cluster_config(self.cluster, "lab")
        self.assertEqual(len(cfg.group_var_files), 2)
        self.assertEqual(cfg.host_var_files, ())

    def test_discover_host_vars(self) -> None:
        from clusterctl.host_vars import discover_host_vars

        host_dir = self.cluster / "host_vars"
        host_dir.mkdir()
        (host_dir / "m1.yml").write_text("prepare_data_disk: true\n", encoding="utf-8")
        discovered = discover_host_vars(self.cluster)
        self.assertEqual(discovered, (("m1", (host_dir / "m1.yml").resolve()),))

    def test_validate_host_vars_ok(self) -> None:
        host_dir = self.cluster / "host_vars"
        host_dir.mkdir()
        (host_dir / "m1.yml").write_text("foo: bar\n", encoding="utf-8")
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        codes = {issue.code for issue in report.issues}
        self.assertIn("host_vars_present", codes)
        self.assertIn("host_var_file", codes)

    def test_validate_host_vars_orphan(self) -> None:
        host_dir = self.cluster / "host_vars"
        host_dir.mkdir()
        (host_dir / "unknown.yml").write_text("foo: bar\n", encoding="utf-8")
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        self.assertIn("host_vars_orphan", {issue.code for issue in report.issues})

    def test_context_loads_without_extra_e(self) -> None:
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        self.assertEqual(ctx.cluster_id, "lab")
        self.assertTrue(ctx.group_var_files)
        self.assertIsNotNone(ctx.cluster_var_file)
        assert ctx.cluster_var_file is not None
        self.assertEqual(ctx.cluster_var_file.name, "cluster.yml")

    def test_context_loads_when_cluster_yml_removed(self) -> None:
        (self.cluster / "group_vars" / "all" / "cluster.yml").unlink()
        # Move DNS identity into the product overlay (ADR 003 Phase 1 SoT).
        foundation = self.cluster / "group_vars" / "all" / "atlas-node-foundation.yml"
        data = yaml.safe_load(foundation.read_text(encoding="utf-8")) or {}
        data.update(
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "k8s.example.com",
            }
        )
        foundation.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        self.assertIsNone(ctx.cluster_var_file)
        self.assertEqual(ctx.workspace_id, "k8s.example.com")

    def test_validate_errors_on_legacy_cluster_yml(self) -> None:
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        codes = {issue.code for issue in report.issues}
        self.assertIn("cluster_yml_legacy", codes)
        issue = next(i for i in report.issues if i.code == "cluster_yml_legacy")
        self.assertEqual(issue.severity, Severity.ERROR)
        text = format_report_text(report)
        self.assertIn("FAIL [cluster_yml_legacy]", text)

    def test_validate_no_cluster_yml_legacy_when_omitted(self) -> None:
        (self.cluster / "group_vars" / "all" / "cluster.yml").unlink()
        foundation = self.cluster / "group_vars" / "all" / "atlas-node-foundation.yml"
        data = yaml.safe_load(foundation.read_text(encoding="utf-8")) or {}
        data.update(
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "k8s.example.com",
            }
        )
        foundation.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        self.assertNotIn("cluster_yml_legacy", {issue.code for issue in report.issues})

    def test_validate_product_secrets_ok(self) -> None:
        secrets = self.cluster / "group_vars" / "all" / "atlas-redis.secrets.yml"
        secrets.write_text("vip_auth_pass: secret\n", encoding="utf-8")
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        codes = {issue.code for issue in report.issues}
        self.assertIn("secrets_present", codes)
        self.assertNotIn("secrets_legacy_monolith", codes)
        self.assertNotIn("secrets_missing", codes)

    def test_validate_legacy_secrets_errors(self) -> None:
        secrets = self.cluster / "group_vars" / "all" / "secrets.yml"
        secrets.write_text("provision_pve_password: secret\n", encoding="utf-8")
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        codes = {issue.code for issue in report.issues}
        self.assertNotIn("secrets_present", codes)
        self.assertIn("secrets_legacy_monolith", codes)
        issue = next(i for i in report.issues if i.code == "secrets_legacy_monolith")
        self.assertEqual(issue.severity, Severity.ERROR)

    def test_validate_secrets_comment_only(self) -> None:
        secrets = self.cluster / "group_vars" / "all" / "atlas-redis.secrets.yml"
        secrets.write_text("# only a comment\n", encoding="utf-8")
        self.assertIsNone(validate_secrets_content(secrets))
        self.assertFalse(secrets_file_configured(secrets))

    def test_validate_product_secrets_ok_configured(self) -> None:
        secrets = self.cluster / "group_vars" / "all" / "atlas-redis.secrets.yml"
        secrets.write_text("provision_pve_password: secret\n", encoding="utf-8")
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        report = validate_cluster(ctx, root=self.root, docker_smoke=False)
        secrets_issues = [i for i in report.issues if i.code == "secrets_present"]
        self.assertTrue(secrets_issues)
        self.assertEqual(secrets_issues[0].severity, Severity.OK)


class GroupVarsCascadeTest(unittest.TestCase):
    """org → env → leaf group_vars merge (defaults lower priority; secrets last)."""

    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "ATLAS_CLUSTERS_ROOT")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._build_tree()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _write_yaml(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    def _build_tree(self) -> None:
        clusters = self.root / "clusters"
        org_all = clusters / "default" / "default" / "group_vars" / "all"
        env_all = clusters / "dev" / "default" / "group_vars" / "all"
        leaf = clusters / "dev" / "redis"
        leaf_all = leaf / "group_vars" / "all"

        self._write_yaml(
            clusters / "default" / "default" / "cluster.yaml",
            {"schema_version": 2, "id": "default/default", "execution": {"mode": "local"}},
        )
        self._write_yaml(
            clusters / "dev" / "default" / "cluster.yaml",
            {"schema_version": 2, "id": "dev/default", "execution": {"mode": "local"}},
        )
        self._write_yaml(
            leaf / "cluster.yaml",
            {
                "schema_version": 2,
                "id": "dev/redis",
                "inventory": "hosts",
                "playbooks": local_playbooks_override_block(),
                "execution": {"mode": "local"},
            },
        )
        (leaf / "hosts").write_text(
            "all:\n  children:\n    redis:\n      hosts:\n        r1: {}\n",
            encoding="utf-8",
        )
        (leaf / "pub_keys").mkdir(parents=True)
        (leaf / "pub_keys" / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")

        self._write_yaml(org_all / "atlas-node-foundation.yml", {"a": 1, "shared": "org"})
        self._write_yaml(env_all / "atlas-node-foundation.yml", {"a": 2, "b": 2})
        self._write_yaml(
            leaf_all / "atlas-node-foundation.yml",
            {
                "b": 3,
                "dns_domain_suffix": "example.com",
                "cluster_domain": "redis.example.com",
                "leaf_only": True,
            },
        )
        self._write_yaml(env_all / "atlas-redis.secrets.yml", {"x": "env", "y": "env"})
        self._write_yaml(leaf_all / "atlas-redis.secrets.yml", {"x": "leaf"})
        # leaf non-secret same key as env secret — secrets force-last wins
        self._write_yaml(leaf_all / "atlas-redis.yml", {"y": "leaf-nonssecret"})

        self.org_all = org_all
        self.env_all = env_all
        self.leaf_all = leaf_all
        self.leaf = leaf
        self.clusters = clusters

    def test_cascade_dirs_order(self) -> None:
        from clusterctl.cluster_layout import cascade_group_vars_dirs

        dirs = cascade_group_vars_dirs(self.clusters, "dev/redis")
        self.assertEqual(
            [d.resolve() for d in dirs],
            [self.org_all.resolve(), self.env_all.resolve(), self.leaf_all.resolve()],
        )

    def test_discover_cascade_priority(self) -> None:
        from clusterctl.cluster_layout import cascade_group_vars_dirs
        from clusterctl.cluster_vars_loader import discover_group_vars_cascade

        dirs = cascade_group_vars_dirs(self.clusters, "dev/redis")
        files = discover_group_vars_cascade(dirs)
        names = [p.name for p in files]
        # non-secrets first (org, env, leaf), then secrets (env, leaf)
        self.assertLess(
            names.index("atlas-node-foundation.yml"),
            names.index("atlas-redis.secrets.yml"),
        )
        # three foundation files before secrets (org/env/leaf may share basename)
        foundation = [p for p in files if p.name == "atlas-node-foundation.yml"]
        self.assertEqual(len(foundation), 3)
        secrets = [p for p in files if p.name.endswith(".secrets.yml")]
        self.assertEqual(len(secrets), 2)
        self.assertTrue(all(p.name.endswith(".secrets.yml") for p in files[-2:]))

    def test_load_cascade_values(self) -> None:
        from clusterctl.cluster_layout import cascade_group_vars_dirs

        dirs = cascade_group_vars_dirs(self.clusters, "dev/redis")
        merged = load_cluster_vars(self.leaf, cascade_dirs=dirs)
        self.assertEqual(merged["a"], 2)  # env over org
        self.assertEqual(merged["b"], 3)  # leaf over env
        self.assertEqual(merged["shared"], "org")
        self.assertTrue(merged["leaf_only"])
        self.assertEqual(merged["x"], "leaf")  # leaf secret over env secret
        # env secret y overrides leaf non-secret y (secrets force-last)
        self.assertEqual(merged["y"], "env")

    def test_load_cluster_config_includes_cascade_files(self) -> None:
        cfg = load_cluster_config(self.leaf, "dev/redis", repo_root=self.root)
        # org + env + leaf foundation, leaf redis.yml, env+leaf secrets
        self.assertGreaterEqual(len(cfg.group_var_files), 6)
        from clusterctl.cluster_vars_loader import load_cluster_vars_from_paths

        merged = load_cluster_vars_from_paths(cfg.group_var_files)
        self.assertEqual(merged["a"], 2)
        self.assertEqual(merged["b"], 3)
        self.assertEqual(merged["x"], "leaf")
        self.assertEqual(merged["y"], "env")

    def test_materialize_uses_cascade(self) -> None:
        cfg = load_cluster_config(self.leaf, "dev/redis", repo_root=self.root)
        workspace = self.root / "workspace" / "dev" / "redis"
        workspace.mkdir(parents=True)
        path = materialize_playbook_extra_vars(
            self.leaf,
            workspace,
            group_var_files=cfg.group_var_files,
        )
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(data["a"], 2)
        self.assertEqual(data["b"], 3)
        self.assertEqual(data["x"], "leaf")
        self.assertEqual(data["y"], "env")


if __name__ == "__main__":
    unittest.main()
