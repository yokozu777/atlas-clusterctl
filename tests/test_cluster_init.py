"""Tests for clusterctl.cluster_init."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_init import InitOptions, init_cluster
from clusterctl.exceptions import ClusterctlError


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
