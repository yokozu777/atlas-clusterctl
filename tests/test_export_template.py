"""Universal export_template: inventory leaf → product _template/<name> (ADR 004)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
import yaml

from clusterctl.exceptions import ClusterctlError
from clusterctl.tools.export_template import (
    KNOWN_TEMPLATE_NAMES,
    export_template,
    main,
    scrub_secrets_overlay_file,
    scrub_secrets_overlays_for_public_template,
    validate_template_name,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_leaf(
    lab: Path,
    *,
    overlay_name: str,
    domain_prefix: str,
    literal_domain: bool = False,
) -> None:
    _write(
        lab / "cluster.yaml",
        "schema_version: 2\nid: lab\nplaybooks: {}\nphases:\n  phases: []\n",
    )
    _write(lab / "hosts", "[all]\nnode1 ansible_host=10.0.0.1\n")
    if literal_domain:
        domain_line = f"cluster_domain: {domain_prefix}.live.com\n"
    else:
        domain_line = f'cluster_domain: "{domain_prefix}.{{{{ dns_domain_suffix }}}}"\n'
    _write(
        lab / "group_vars" / "all" / overlay_name,
        f"# Leaf DNS identity\ndns_domain_suffix: live.lab\n{domain_line}",
    )
    _write(
        lab / "group_vars" / "all" / "cluster.yml",
        "dns_domain_suffix: live.lab\n",
    )
    _write(lab / "group_vars" / "all" / "secrets.yml", "password: live\n")
    product = overlay_name.removesuffix(".yml")
    _write(
        lab / "group_vars" / "all" / f"{product}.secrets.yml",
        "vip_auth_pass: LIVE_SECRET\nnested:\n  token: ALSO_LIVE\n",
    )
    _write(lab / "pub_keys" / "localuser.pub", "ssh-ed25519 AAAA test\n")


# (source_id, template_name, atlas overlay, stack DNS prefix)
_STACK_CASES: tuple[tuple[str, str, str, str], ...] = (
    ("fixture/redis", "redis", "atlas-redis.yml", "redis"),
    ("fixture/kafka", "kafka", "atlas-kafka.yml", "kafka"),
    ("fixture/postgresql", "postgresql", "atlas-postgresql.yml", "pgsql"),
    ("fixture/infra", "infra_edge", "atlas-infra-edge.yml", "infra"),
    ("fixture/jenkins", "jenkins_agent", "atlas-jenkins-agent.yml", "jenkins"),
    ("fixture/k8s", "k8s_full", "atlas-k8s-core.yml", "k8s"),
)


class ExportTemplateValidateTest(unittest.TestCase):
    def test_validate_template_name_ok(self) -> None:
        for name in KNOWN_TEMPLATE_NAMES:
            self.assertEqual(validate_template_name(name), name)

    def test_validate_template_name_rejects(self) -> None:
        for bad in ("", "_template", "a/b", "../x", "Redis", "has space"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    validate_template_name(bad)


class ExportTemplateMultiStackTest(unittest.TestCase):
    def test_export_all_known_stacks_preserves_prefix_and_scrubs(self) -> None:
        for source_id, template_name, overlay, prefix in _STACK_CASES:
            with self.subTest(source_id=source_id, template=template_name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    source_root = root / "inventory"
                    target_root = root / "product"
                    lab = source_root.joinpath(*source_id.split("/"))
                    _seed_leaf(lab, overlay_name=overlay, domain_prefix=prefix)

                    target = export_template(
                        source_id=source_id,
                        template_name=template_name,
                        source_root=source_root,
                        target_root=target_root,
                    )
                    self.assertEqual(
                        target,
                        (target_root / "_template" / template_name).resolve(),
                    )
                    cfg = (target / "cluster.yaml").read_text(encoding="utf-8")
                    self.assertIn("id: ''", cfg)
                    self.assertIn(
                        f"export_template --from {source_id} --template {template_name}",
                        cfg,
                    )
                    self.assertTrue((target / "hosts").is_file())
                    self.assertTrue((target / "pub_keys" / "localuser.pub").is_file())
                    self.assertFalse(
                        (target / "group_vars" / "all" / "cluster.yml").exists()
                    )
                    legacy_secrets = yaml.safe_load(
                        (target / "group_vars" / "all" / "secrets.yml").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(legacy_secrets, {"password": ""})
                    product = overlay.removesuffix(".yml")
                    product_secrets = yaml.safe_load(
                        (
                            target
                            / "group_vars"
                            / "all"
                            / f"{product}.secrets.yml"
                        ).read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        product_secrets,
                        {"vip_auth_pass": "", "nested": {"token": ""}},
                    )
                    data = yaml.safe_load(
                        (target / "group_vars" / "all" / overlay).read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(data["dns_domain_suffix"], "example.com")
                    self.assertEqual(
                        data["cluster_domain"],
                        f"{prefix}.{{{{ dns_domain_suffix }}}}",
                    )

    def test_export_scrubs_literal_cluster_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "inventory"
            target_root = root / "product"
            lab = source_root / "fixture" / "redis"
            _seed_leaf(
                lab,
                overlay_name="atlas-redis.yml",
                domain_prefix="redis",
                literal_domain=True,
            )
            target = export_template(
                source_id="fixture/redis",
                template_name="redis",
                source_root=source_root,
                target_root=target_root,
            )
            text = (target / "group_vars" / "all" / "atlas-redis.yml").read_text(
                encoding="utf-8"
            )
            self.assertIn("dns_domain_suffix: example.com", text)
            self.assertIn('cluster_domain: "redis.{{ dns_domain_suffix }}"', text)
            self.assertNotIn("redis.live.com", text)

    def test_missing_source_mentions_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FileNotFoundError) as ctx:
                export_template(
                    source_id="fixture/redis",
                    template_name="redis",
                    source_root=root / "empty",
                    target_root=root / "product",
                )
            self.assertIn("source_root=", str(ctx.exception))

    def test_invalid_source_id_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ClusterctlError):
                export_template(
                    source_id="not a id",
                    template_name="redis",
                    source_root=root,
                    target_root=root,
                )

    def test_does_not_copy_or_rewrite_readme(self) -> None:
        """Runtime copy is hosts/group_vars/pub_keys only — README stays template-owned."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "inventory"
            target_root = root / "product"
            lab = source_root / "fixture" / "redis"
            _seed_leaf(lab, overlay_name="atlas-redis.yml", domain_prefix="redis")
            marker = "effective merge: `default/default` + `fixture/k8s` LIVE"
            _write(lab / "README.md", marker + "\n")
            # Pre-existing public README must not be overwritten by lab text.
            pre = target_root / "_template" / "redis" / "README.md"
            _write(pre, "public scaffold readme\n")
            target = export_template(
                source_id="fixture/redis",
                template_name="redis",
                source_root=source_root,
                target_root=target_root,
            )
            self.assertEqual(
                (target / "README.md").read_text(encoding="utf-8").strip(),
                "public scaffold readme",
            )
            self.assertNotIn("LIVE", (target / "README.md").read_text(encoding="utf-8"))


class ExportTemplateSecretsScrubTest(unittest.TestCase):
    def test_empties_product_and_legacy_secrets_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "leaf"
            _write(
                config / "group_vars" / "all" / "atlas-redis.secrets.yml",
                "vip_auth_pass: LIVE\nnested:\n  token: ALSO\n",
            )
            _write(config / "group_vars" / "all" / "secrets.yml", "password: LIVE\n")
            written = scrub_secrets_overlays_for_public_template(config)
            self.assertEqual(len(written), 2)
            product = yaml.safe_load(
                (config / "group_vars" / "all" / "atlas-redis.secrets.yml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(product, {"vip_auth_pass": "", "nested": {"token": ""}})
            legacy = yaml.safe_load(
                (config / "group_vars" / "all" / "secrets.yml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(legacy, {"password": ""})

    def test_vault_payload_replaced_with_stub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "atlas-x.secrets.yml"
            path.write_text(
                "$ANSIBLE_VAULT;1.1;AES256\n6666666666666666\n",
                encoding="utf-8",
            )
            self.assertTrue(scrub_secrets_overlay_file(path))
            text = path.read_text(encoding="utf-8")
            self.assertIn("Vault payload removed", text)
            self.assertNotIn("6666666666666666", text)
            self.assertFalse(scrub_secrets_overlay_file(path))


class ExportTemplateFlattenCascadeTest(unittest.TestCase):
    def test_flatten_merges_env_default_and_scrubs_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "inventory"
            target_root = root / "product"
            env_default = source_root / "fixture" / "default"
            lab = source_root / "fixture" / "redis"
            _write(
                env_default / "group_vars" / "all" / "atlas-node-foundation.yml",
                "dns_domain_suffix: live.lab\n"
                "admin_user: localuser\n"
                'pki_ca_url:\n  - "https://ca.dev-mxhash.com:8443/roots.pem"\n',
            )
            _write(
                env_default / "group_vars" / "all" / "atlas-node-foundation.secrets.yml",
                "admin_password: LIVE\n",
            )
            _seed_leaf(lab, overlay_name="atlas-redis.yml", domain_prefix="redis")
            _write(
                lab / "hosts",
                "all:\n  children:\n    redis:\n      hosts:\n"
                "        10.1.2.3:\n"
                "          hostname: redis01.dev-mxhash.com\n",
            )
            _write(
                lab / "group_vars" / "all" / "atlas-node-foundation.yml",
                "dns_domain_suffix: live.lab\n"
                'cluster_domain: "redis.{{ dns_domain_suffix }}"\n'
                "node_foundation_init_hosts: redis\n",
            )
            _write(lab / "group_vars" / "proxmox.yml", "ansible_host: pve\n")

            target = export_template(
                source_id="fixture/redis",
                template_name="redis",
                source_root=source_root,
                target_root=target_root,
                flatten_cascade=True,
            )
            foundation = yaml.safe_load(
                (
                    target / "group_vars" / "all" / "atlas-node-foundation.yml"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(foundation["admin_user"], "localuser")
            self.assertEqual(foundation["node_foundation_init_hosts"], "redis")
            self.assertEqual(foundation["dns_domain_suffix"], "example.com")
            self.assertEqual(
                foundation["pki_ca_url"],
                ["https://ca.example.com:8443/roots.pem"],
            )
            secrets = yaml.safe_load(
                (
                    target
                    / "group_vars"
                    / "all"
                    / "atlas-node-foundation.secrets.yml"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(secrets, {"admin_password": ""})
            hosts = (target / "hosts").read_text(encoding="utf-8")
            self.assertIn("192.168.1.240:", hosts)
            self.assertIn("hostname: redis01.example.com", hosts)
            self.assertNotIn("10.1.2.3", hosts)
            self.assertNotIn("mxhash", hosts)
            self.assertTrue((target / "group_vars" / "proxmox.yml").is_file())
            header = (target / "cluster.yaml").read_text(encoding="utf-8")
            self.assertIn("--flatten-cascade", header)


class ExportTemplateCliTest(unittest.TestCase):
    def test_cli_requires_from_and_template(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            main([])
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "inv"
            target_root = root / "prod"
            lab = source_root / "fixture" / "kafka"
            _seed_leaf(lab, overlay_name="atlas-kafka.yml", domain_prefix="kafka")
            rc = main(
                [
                    "--from",
                    "fixture/kafka",
                    "--template",
                    "kafka",
                    "--source-root",
                    str(source_root),
                    "--target-root",
                    str(target_root),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(
                (target_root / "_template" / "kafka" / "cluster.yaml").is_file()
            )

    def test_cli_same_root_via_source_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lab = root / "fixture" / "redis"
            _seed_leaf(lab, overlay_name="atlas-redis.yml", domain_prefix="redis")
            rc = main(
                [
                    "--from",
                    "fixture/redis",
                    "--template",
                    "redis",
                    "--source-root",
                    str(root),
                    "--target-root",
                    str(root),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue((root / "_template" / "redis" / "cluster.yaml").is_file())

    def test_cli_bad_template_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rc = main(
                [
                    "--from",
                    "fixture/redis",
                    "--template",
                    "_bad",
                    "--source-root",
                    str(root),
                    "--target-root",
                    str(root),
                ]
            )
            self.assertEqual(rc, 1)

    def test_defaults_use_inventory_and_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = root / "controller"
            inventory = root / "inventory" / "clusters"
            (product / "clusters").mkdir(parents=True)
            lab = inventory / "fixture" / "redis"
            _seed_leaf(lab, overlay_name="atlas-redis.yml", domain_prefix="redis")

            prev_root = os.environ.get("ATLAS_CLUSTER_ROOT")
            prev_clusters = os.environ.get("ATLAS_CLUSTERS_ROOT")
            prev_cfg = os.environ.get("ATLAS_CLUSTERCTL_CONFIG")
            try:
                os.environ["ATLAS_CLUSTER_ROOT"] = str(product)
                os.environ["ATLAS_CLUSTERS_ROOT"] = str(inventory)
                os.environ["ATLAS_CLUSTERCTL_CONFIG"] = str(root / "empty-config.yaml")
                (root / "empty-config.yaml").write_text("{}\n", encoding="utf-8")
                target = export_template(source_id="fixture/redis", template_name="redis")
                self.assertEqual(
                    target,
                    (product / "clusters" / "_template" / "redis").resolve(),
                )
            finally:
                for key, prev in (
                    ("ATLAS_CLUSTER_ROOT", prev_root),
                    ("ATLAS_CLUSTERS_ROOT", prev_clusters),
                    ("ATLAS_CLUSTERCTL_CONFIG", prev_cfg),
                ):
                    if prev is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = prev


if __name__ == "__main__":
    unittest.main()
