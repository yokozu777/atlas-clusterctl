"""Tests for clusterctl.cluster_init."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_init import (
    InitOptions,
    init_cluster,
    is_init_bootstrap_code,
    soften_init_bootstrap_issues,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.validate import Severity, ValidationIssue, ValidationReport


class ClusterInitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._seed_minimal_repo()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write_cluster_var(self, base: Path, data: dict) -> None:
        all_dir = base / "group_vars" / "all"
        all_dir.mkdir(parents=True, exist_ok=True)
        (all_dir / "cluster.yml").write_text(
            yaml.safe_dump(data, sort_keys=False),
            encoding="utf-8",
        )

    def _write_atlas_dns_overlay(self, base: Path, data: dict, *, name: str = "atlas-node-foundation.yml") -> None:
        all_dir = base / "group_vars" / "all"
        all_dir.mkdir(parents=True, exist_ok=True)
        body = (
            "# Leaf DNS identity\n"
            "# (duplicated into every atlas-*.yml that uses leaf DNS / workspace id)\n"
            + yaml.safe_dump(data, sort_keys=False)
        )
        (all_dir / name).write_text(body, encoding="utf-8")

    def _seed_minimal_repo(self) -> None:
        default = self.root / "clusters" / "default"
        default.mkdir(parents=True)
        (default / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "default",
                    "display_name": "Source Default",
                    "playbooks_enabled": True,
                    "execution": {"mode": "local"},
                    "inventory": "hosts",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (default / "hosts").write_text(
            'all:\n  children:\n    k8s_masters:\n      hosts:\n        m1: {}\n',
            encoding="utf-8",
        )
        # ADR 003 Phase 3: DNS SoT is atlas-*.yml; templates omit cluster.yml.
        (default / "group_vars" / "all").mkdir(parents=True)
        self._write_atlas_dns_overlay(
            default,
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "k8s.{{ dns_domain_suffix }}",
                "k8s_cluster_domain": "{{ cluster_domain }}",
            },
        )
        self._write_atlas_dns_overlay(
            default,
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "k8s.{{ dns_domain_suffix }}",
            },
            name="atlas-compute-provision.yml",
        )

        template = self.root / "clusters" / "_template"
        template.mkdir(parents=True)
        (template / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "",
                    "display_name": None,
                    "playbooks_enabled": True,
                    "execution": {"mode": "local"},
                    "inventory": "hosts",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (template / "hosts").write_text("all:\n  children:\n    k8s_masters:\n      hosts: {}\n", encoding="utf-8")
        (template / "group_vars" / "all").mkdir(parents=True)
        self._write_atlas_dns_overlay(
            template,
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "k8s.{{ dns_domain_suffix }}",
                "k8s_cluster_domain": "{{ cluster_domain }}",
            },
        )

        (self.root / "ansible.cfg").write_text("[defaults]\ninventory = ignored\n", encoding="utf-8")
        from clusterctl.pipeline_fixture import seed_org_baseline_fixture

        seed_org_baseline_fixture(self.root)

    def test_init_from_default_patches_identity_only(self) -> None:
        target = init_cluster(
            self.root,
            "lab",
            options=InitOptions(from_id="default", validate=False),
        )
        cfg = yaml.safe_load((target / "cluster.yaml").read_text(encoding="utf-8"))
        vars_data = yaml.safe_load(
            (target / "group_vars" / "all" / "atlas-node-foundation.yml").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(cfg["id"], "lab")
        self.assertEqual(cfg["display_name"], "lab")
        self.assertEqual(cfg["execution"], {"mode": "local"})
        self.assertNotIn("cluster_id", vars_data)
        self.assertEqual(vars_data["dns_domain_suffix"], "example.com")
        self.assertNotIn("CHANGEME", (target / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertFalse((target / "group_vars" / "all" / "cluster.yml").exists())

    def test_init_display_name_override(self) -> None:
        target = init_cluster(
            self.root,
            "lab",
            options=InitOptions(
                from_id="default",
                display_name="Lab Environment",
                validate=False,
            ),
        )
        cfg = yaml.safe_load((target / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["display_name"], "Lab Environment")

    def test_init_dns_suffix_override(self) -> None:
        target = init_cluster(
            self.root,
            "lab",
            options=InitOptions(
                from_id="default",
                dns_domain_suffix="lab.example.com",
                validate=False,
            ),
        )
        for name in ("atlas-node-foundation.yml", "atlas-compute-provision.yml"):
            vars_data = yaml.safe_load(
                (target / "group_vars" / "all" / name).read_text(encoding="utf-8")
            )
            self.assertEqual(vars_data["dns_domain_suffix"], "lab.example.com", name)
        self.assertFalse((target / "group_vars" / "all" / "cluster.yml").exists())

    def test_init_dns_suffix_already_matching_is_ok(self) -> None:
        """Idempotent --dns-suffix when overlays already have that value."""
        target = init_cluster(
            self.root,
            "lab",
            options=InitOptions(
                from_id="default",
                dns_domain_suffix="example.com",
                validate=False,
            ),
        )
        self.assertTrue(target.is_dir())

    def test_init_dns_suffix_errors_without_leaf_dns_overlays(self) -> None:
        empty = self.root / "clusters" / "_template"
        all_dir = empty / "group_vars" / "all"
        if all_dir.is_dir():
            shutil.rmtree(all_dir)
        all_dir.mkdir(parents=True)
        (all_dir / "misc.yml").write_text("foo: 1\n", encoding="utf-8")

        with self.assertRaises(ClusterctlError) as ctx:
            init_cluster(
                self.root,
                "lab/empty",
                options=InitOptions(
                    template_name="",
                    dns_domain_suffix="lab.example.com",
                    validate=False,
                ),
            )
        self.assertIn("--dns-suffix", str(ctx.exception))
        self.assertIn("no Leaf DNS overlays", str(ctx.exception))
        self.assertFalse((self.root / "clusters" / "lab" / "empty").exists())

    def test_init_dns_suffix_errors_when_overlays_lack_suffix_key(self) -> None:
        source = self.root / "clusters" / "broken-dns"
        source.mkdir(parents=True)
        shutil.copy2(
            self.root / "clusters" / "default" / "cluster.yaml",
            source / "cluster.yaml",
        )
        (source / "hosts").write_text("all: {}\n", encoding="utf-8")
        all_dir = source / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        (all_dir / "atlas-x.yml").write_text(
            "# Leaf DNS identity\n"
            'cluster_domain: "k8s.{{ dns_domain_suffix }}"\n',
            encoding="utf-8",
        )

        with self.assertRaises(ClusterctlError) as ctx:
            init_cluster(
                self.root,
                "lab/broken",
                options=InitOptions(
                    from_id="broken-dns",
                    dns_domain_suffix="lab.example.com",
                    validate=False,
                ),
            )
        self.assertIn("no overlay declares dns_domain_suffix", str(ctx.exception))
        self.assertFalse((self.root / "clusters" / "lab" / "broken").exists())

    def test_init_dns_suffix_preserves_cluster_domain_prefix(self) -> None:
        """--dns-suffix must not rewrite template-owned cluster_domain prefixes."""
        target = init_cluster(
            self.root,
            "lab",
            options=InitOptions(
                from_id="default",
                dns_domain_suffix="lab.example.com",
                validate=False,
            ),
        )
        for name in ("atlas-node-foundation.yml", "atlas-compute-provision.yml"):
            vars_data = yaml.safe_load(
                (target / "group_vars" / "all" / name).read_text(encoding="utf-8")
            )
            self.assertEqual(vars_data["dns_domain_suffix"], "lab.example.com", name)
            self.assertEqual(
                vars_data["cluster_domain"],
                "k8s.{{ dns_domain_suffix }}",
                name,
            )

    def test_init_without_cluster_yml_source(self) -> None:
        """Init must not invent cluster.yml (ADR 003 Phase 3)."""
        target = init_cluster(
            self.root,
            "lab",
            options=InitOptions(
                from_id="default",
                dns_domain_suffix="lab.example.com",
                validate=False,
            ),
        )
        self.assertFalse((target / "group_vars" / "all" / "cluster.yml").exists())
        vars_data = yaml.safe_load(
            (target / "group_vars" / "all" / "atlas-node-foundation.yml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(vars_data["dns_domain_suffix"], "lab.example.com")

    def test_init_legacy_cluster_yml_dns_still_patched(self) -> None:
        """Pre-Phase-2 sources with DNS only in cluster.yml keep working."""
        source = self.root / "clusters" / "legacy_src"
        source.mkdir(parents=True)
        shutil.copy2(
            self.root / "clusters" / "default" / "cluster.yaml",
            source / "cluster.yaml",
        )
        shutil.copy2(self.root / "clusters" / "default" / "hosts", source / "hosts")
        self._write_cluster_var(
            source,
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "k8s.{{ dns_domain_suffix }}",
            },
        )
        target = init_cluster(
            self.root,
            "from-legacy",
            options=InitOptions(
                from_id="legacy_src",
                dns_domain_suffix="legacy.example.com",
                validate=False,
            ),
        )
        vars_data = yaml.safe_load(
            (target / "group_vars" / "all" / "cluster.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(vars_data["dns_domain_suffix"], "legacy.example.com")

    def test_init_template_not_from_default(self) -> None:
        target = init_cluster(
            self.root,
            "empty",
            options=InitOptions(template_name="", validate=False),
        )
        cfg = yaml.safe_load((target / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["id"], "empty")
        self.assertEqual(cfg["display_name"], "empty")
        self.assertNotEqual(
            (target / "cluster.yaml").read_text(encoding="utf-8"),
            (self.root / "clusters" / "default" / "cluster.yaml").read_text(encoding="utf-8"),
        )

    def test_init_template_k8s_full_subdir(self) -> None:
        k8s_full = self.root / "clusters" / "_template" / "k8s_full"
        k8s_full.mkdir(parents=True)
        shutil.copy2(
            self.root / "clusters" / "_template" / "cluster.yaml",
            k8s_full / "cluster.yaml",
        )
        shutil.copy2(
            self.root / "clusters" / "_template" / "hosts",
            k8s_full / "hosts",
        )
        target = init_cluster(
            self.root,
            "prod/k8s",
            options=InitOptions(template_name="k8s_full", validate=False),
        )
        cfg = yaml.safe_load((target / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["id"], "prod/k8s")
        self.assertTrue((target / "hosts").is_file())

    def test_init_template_postgresql_subdir(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        source = repo_root / "clusters" / "_template" / "postgresql"
        if not source.is_dir():
            self.skipTest("postgresql template not in repo")

        target_root = self.root / "clusters" / "_template" / "postgresql"
        target_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target_root)

        target = init_cluster(
            self.root,
            "lab/pgsql",
            options=InitOptions(
                template_name="postgresql",
                dns_domain_suffix="lab.example.com",
                validate=False,
            ),
        )
        cfg = yaml.safe_load((target / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["id"], "lab/pgsql")
        provision = (target / "group_vars" / "all" / "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: postgresql", provision)
        hosts = (target / "hosts").read_text(encoding="utf-8")
        self.assertIn("pgsql_etcd_cluster", hosts)
        self._assert_leaf_dns_suffix_and_prefix(
            target,
            suffix="lab.example.com",
            prefix="pgsql",
            overlays=(
                "atlas-compute-provision.yml",
                "atlas-node-foundation.yml",
                "atlas-postgresql.yml",
            ),
        )

    def test_init_template_kafka_subdir(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        source = repo_root / "clusters" / "_template" / "kafka"
        if not source.is_dir():
            self.skipTest("kafka template not in repo")

        target_root = self.root / "clusters" / "_template" / "kafka"
        target_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target_root)

        target = init_cluster(
            self.root,
            "lab/kafka",
            options=InitOptions(
                template_name="kafka",
                dns_domain_suffix="lab.example.com",
                validate=False,
            ),
        )
        cfg = yaml.safe_load((target / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["id"], "lab/kafka")
        provision = (target / "group_vars" / "all" / "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: kafka", provision)
        hosts = (target / "hosts").read_text(encoding="utf-8")
        self.assertIn("kafka_controllers", hosts)
        self.assertIn("kafka_brokers", hosts)
        self._assert_leaf_dns_suffix_and_prefix(
            target,
            suffix="lab.example.com",
            prefix="kafka",
            overlays=(
                "atlas-compute-provision.yml",
                "atlas-node-foundation.yml",
                "atlas-kafka.yml",
            ),
        )

    def test_init_template_redis_preserves_stack_prefix(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        source = repo_root / "clusters" / "_template" / "redis"
        if not source.is_dir():
            self.skipTest("redis template not in repo")

        target_root = self.root / "clusters" / "_template" / "redis"
        target_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target_root)

        target = init_cluster(
            self.root,
            "lab/redis",
            options=InitOptions(
                template_name="redis",
                dns_domain_suffix="lab.example.com",
                validate=False,
            ),
        )
        self._assert_leaf_dns_suffix_and_prefix(
            target,
            suffix="lab.example.com",
            prefix="redis",
            overlays=(
                "atlas-compute-provision.yml",
                "atlas-node-foundation.yml",
                "atlas-redis.yml",
            ),
        )

    def _assert_leaf_dns_suffix_and_prefix(
        self,
        target: Path,
        *,
        suffix: str,
        prefix: str,
        overlays: tuple[str, ...],
    ) -> None:
        expected_domain = f"{prefix}.{{{{ dns_domain_suffix }}}}"
        for name in overlays:
            path = target / "group_vars" / "all" / name
            self.assertTrue(path.is_file(), name)
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(data["dns_domain_suffix"], suffix, name)
            self.assertEqual(data["cluster_domain"], expected_domain, name)

    def test_init_refuses_existing_without_force(self) -> None:
        init_cluster(self.root, "lab", options=InitOptions(validate=False))
        with self.assertRaises(ClusterctlError):
            init_cluster(self.root, "lab", options=InitOptions(validate=False))

    def test_init_force_replaces(self) -> None:
        init_cluster(self.root, "lab", options=InitOptions(validate=False))
        init_cluster(
            self.root,
            "lab",
            options=InitOptions(display_name="Second", force=True, validate=False),
        )
        cfg = yaml.safe_load((self.root / "clusters" / "lab" / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["display_name"], "Second")

    def test_cli_rejects_removed_domain_prefix(self) -> None:
        from clusterctl.__main__ import _build_parser

        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                ["init", "lab/x", "--template", "--domain-prefix", "staging"]
            )

    def test_init_bootstrap_codes(self) -> None:
        self.assertTrue(is_init_bootstrap_code("playbooks_atlas-compute-provision_missing"))
        self.assertTrue(is_init_bootstrap_code("execution_docker_repos_missing"))
        self.assertTrue(is_init_bootstrap_code("playbooks_lock_missing"))
        self.assertTrue(
            is_init_bootstrap_code("playbooks_lock_repo_missing_atlas-compute-provision")
        )
        self.assertFalse(is_init_bootstrap_code("playbooks_incomplete"))
        self.assertFalse(is_init_bootstrap_code("playbook_file_atlas-k8s-core_init_missing"))
        self.assertFalse(is_init_bootstrap_code("controller_contract"))
        self.assertFalse(is_init_bootstrap_code("secrets_invalid"))

    def test_soften_init_bootstrap_issues(self) -> None:
        report = ValidationReport(cluster_id="lab/x")
        report.issues.extend(
            [
                ValidationIssue(
                    Severity.ERROR,
                    "playbooks_atlas-compute-provision_missing",
                    "layout not ready",
                ),
                ValidationIssue(Severity.ERROR, "controller_contract", "no pub_keys"),
            ]
        )
        changed = soften_init_bootstrap_issues(report)
        self.assertEqual(changed, 1)
        self.assertEqual(report.issues[0].severity, Severity.WARNING)
        self.assertEqual(report.issues[1].severity, Severity.ERROR)
        self.assertFalse(report.ok)

    def _git_playbooks_block(self) -> dict:
        return {
            "atlas-compute-provision": {
                "source": "git",
                "layout": "roles/",
                "shallow": True,
                "sync": "always",
                "url": "git@example.com:atlas-compute-provision.git",
                "ref": "main",
                "entries": {
                    "templates": {
                        "file": "playbooks/build_templates.yaml",
                        "invocations": [{"tags": "all"}],
                    }
                },
                "path": "atlas-compute-provision",
                "path_relative_to": "repo_root",
            }
        }

    def _write_git_playbooks_source(self, *, pub_keys: bool) -> Path:
        org = self.root / "clusters" / "default" / "default" / "cluster.yaml"
        org.parent.mkdir(parents=True, exist_ok=True)
        org.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "default/default",
                    "playbooks": self._git_playbooks_block(),
                    "phases": [{"templates": "atlas-compute-provision/templates"}],
                    "execution": {"mode": "local"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        source = self.root / "clusters" / "_template" / "git_src"
        source.mkdir(parents=True, exist_ok=True)
        (source / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "",
                    "display_name": None,
                    "playbooks": self._git_playbooks_block(),
                    "phases": [{"templates": "atlas-compute-provision/templates"}],
                    "execution": {"mode": "local"},
                    "inventory": "hosts",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (source / "hosts").write_text(
            "all:\n  hosts: {}\n  vars:\n    ansible_python_interpreter: /usr/bin/python3\n",
            encoding="utf-8",
        )
        self._write_atlas_dns_overlay(
            source,
            {
                "dns_domain_suffix": "example.com",
                "cluster_domain": "k8s.{{ dns_domain_suffix }}",
            },
        )
        if pub_keys:
            pub = source / "pub_keys"
            pub.mkdir(parents=True, exist_ok=True)
            (pub / "localuser.pub").write_text(
                "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest localuser\n",
                encoding="utf-8",
            )
        return source

    def _isolated_init_env(self) -> dict[str, str | None]:
        keys = ("ATLAS_CLUSTER_ROOT", "ATLAS_CLUSTERS_ROOT", "ATLAS_WORKSPACE_ROOT")
        saved = {key: os.environ.get(key) for key in keys}
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        os.environ.pop("ATLAS_CLUSTERS_ROOT", None)
        os.environ["ATLAS_WORKSPACE_ROOT"] = str(self.root / "workspace")
        return saved

    def _restore_init_env(self, saved: dict[str, str | None]) -> None:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_init_git_playbooks_empty_workspace_keeps_leaf(self) -> None:
        self._write_git_playbooks_source(pub_keys=True)
        saved = self._isolated_init_env()
        try:
            target = init_cluster(
                self.root,
                "lab/git",
                options=InitOptions(template_name="git_src", validate=True),
            )
            self.assertTrue(target.is_dir())
            self.assertTrue((target / "cluster.yaml").is_file())
            self.assertFalse(
                (
                    self.root
                    / "workspace"
                    / "lab"
                    / "git"
                    / "repos"
                    / "atlas-compute-provision"
                    / "roles"
                ).is_dir()
            )
            from clusterctl.context import ClusterContext
            from clusterctl.validate import validate_cluster

            ctx = ClusterContext.load(cluster_id="lab/git")
            report = validate_cluster(ctx, root=self.root, docker_smoke=False)
            codes = {issue.code for issue in report.errors}
            self.assertIn("playbooks_atlas-compute-provision_missing", codes)
        finally:
            self._restore_init_env(saved)

    def test_init_validate_still_rolls_back_controller_contract(self) -> None:
        self._write_git_playbooks_source(pub_keys=False)
        saved = self._isolated_init_env()
        try:
            with self.assertRaises(ClusterctlError) as ctx:
                init_cluster(
                    self.root,
                    "lab/bad",
                    options=InitOptions(template_name="git_src", validate=True),
                )
            self.assertIn("init validation failed", str(ctx.exception))
            self.assertFalse((self.root / "clusters" / "lab" / "bad").exists())
        finally:
            self._restore_init_env(saved)

    def _seed_pve_and_env_templates(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        for name in ("default", "pve_templates"):
            source = repo / "clusters" / "_template" / name
            dest = self.root / "clusters" / "_template" / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(source, dest)

    def test_init_hierarchical_seeds_env_default_from_template(self) -> None:
        self._seed_pve_and_env_templates()
        leaf = init_cluster(
            self.root,
            "lab/foo",
            options=InitOptions(template_name="pve_templates", validate=False),
        )
        env_default = self.root / "clusters" / "lab" / "default"
        self.assertTrue(env_default.is_dir(), env_default)
        cfg = yaml.safe_load((env_default / "cluster.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["id"], "lab/default")
        self.assertTrue(
            (
                env_default
                / "group_vars"
                / "all"
                / "atlas-compute-provision.secrets.yml"
            ).is_file()
        )
        self.assertTrue(
            (env_default / "group_vars" / "all" / "atlas-node-foundation.yml").is_file()
        )
        self.assertEqual(leaf, self.root / "clusters" / "lab" / "foo")
        leaf_all = leaf / "group_vars" / "all"
        self.assertTrue((leaf_all / "atlas-compute-provision.yml").is_file())
        self.assertFalse((leaf_all / "atlas-node-foundation.yml").exists())
        self.assertFalse((leaf_all / "atlas-node-foundation.secrets.yml").exists())
        self.assertFalse((leaf_all / "atlas-compute-provision.secrets.yml").exists())

        marker = env_default / "group_vars" / "all" / "atlas-compute-provision.yml"
        original = marker.read_text(encoding="utf-8")
        marker.write_text(original + "\n# env-policy-marker\n", encoding="utf-8")

        second = init_cluster(
            self.root,
            "lab/bar",
            options=InitOptions(template_name="pve_templates", validate=False),
        )
        self.assertTrue(second.is_dir())
        self.assertIn("# env-policy-marker", marker.read_text(encoding="utf-8"))

    def test_init_force_leaf_does_not_clobber_env_default(self) -> None:
        self._seed_pve_and_env_templates()
        init_cluster(
            self.root,
            "lab/foo",
            options=InitOptions(template_name="pve_templates", validate=False),
        )
        marker = (
            self.root
            / "clusters"
            / "lab"
            / "default"
            / "group_vars"
            / "all"
            / "atlas-compute-provision.yml"
        )
        marker.write_text(
            marker.read_text(encoding="utf-8") + "\n# keep-me\n",
            encoding="utf-8",
        )
        init_cluster(
            self.root,
            "lab/foo",
            options=InitOptions(
                template_name="pve_templates",
                validate=False,
                force=True,
            ),
        )
        self.assertIn("# keep-me", marker.read_text(encoding="utf-8"))

    def test_init_flat_id_does_not_seed_env_default(self) -> None:
        self._seed_pve_and_env_templates()
        target = init_cluster(
            self.root,
            "mylab",
            options=InitOptions(template_name="pve_templates", validate=False),
        )
        self.assertEqual(target, self.root / "clusters" / "mylab")
        self.assertFalse((target / "default").exists())
        self.assertFalse((self.root / "clusters" / "mylab" / "default").exists())

    def test_init_options_and_cli_have_no_domain_prefix(self) -> None:
        from dataclasses import fields

        from clusterctl.__main__ import _build_parser

        self.assertNotIn("domain_prefix", {f.name for f in fields(InitOptions)})

        init_parser = next(
            action.choices["init"]
            for action in _build_parser()._actions
            if getattr(action, "choices", None) and "init" in action.choices
        )
        help_text = init_parser.format_help()
        self.assertNotIn("--domain-prefix", help_text)
        self.assertIn("--dns-suffix", help_text)
        dests = {action.dest for action in init_parser._actions}
        self.assertNotIn("domain_prefix", dests)


if __name__ == "__main__":
    unittest.main()
