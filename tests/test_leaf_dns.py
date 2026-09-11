"""Unit tests for clusterctl.leaf_dns (suffix-only patch; template-owned prefixes)."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.leaf_dns import (
    LEAF_DNS_MARKER,
    discover_leaf_dns_overlays,
    file_has_leaf_dns_identity,
    patch_group_vars_identity_lines,
    patch_leaf_dns_identity,
    scrub_leaf_dns_suffix_for_public_template,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class LeafDnsApiSurfaceTest(unittest.TestCase):
    def test_patch_helpers_reject_removed_domain_prefix_kwarg(self) -> None:
        for fn in (patch_group_vars_identity_lines, patch_leaf_dns_identity):
            params = inspect.signature(fn).parameters
            self.assertNotIn("domain_prefix", params, fn.__name__)


class LeafDnsPatchContractTest(unittest.TestCase):
    def test_suffix_patch_preserves_quoted_stack_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "group_vars" / "all" / "atlas-redis.yml"
            _write(
                path,
                f"{LEAF_DNS_MARKER}\n"
                "dns_domain_suffix: example.com\n"
                'cluster_domain: "redis.{{ dns_domain_suffix }}"\n'
                'k8s_cluster_domain: "{{ cluster_domain }}"\n',
            )
            self.assertTrue(
                patch_group_vars_identity_lines(
                    path,
                    cluster_id="lab/redis",
                    dns_domain_suffix="lab.example.com",
                )
            )
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            self.assertEqual(data["dns_domain_suffix"], "lab.example.com")
            self.assertEqual(data["cluster_domain"], "redis.{{ dns_domain_suffix }}")
            self.assertEqual(data["k8s_cluster_domain"], "{{ cluster_domain }}")
            self.assertIn('cluster_domain: "redis.{{ dns_domain_suffix }}"', text)

    def test_suffix_patch_preserves_unquoted_and_divergent_prefixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            all_dir = config / "group_vars" / "all"
            _write(
                all_dir / "atlas-a.yml",
                f"{LEAF_DNS_MARKER}\n"
                "dns_domain_suffix: example.com\n"
                "cluster_domain: kafka.{{ dns_domain_suffix }}\n",
            )
            _write(
                all_dir / "atlas-b.yml",
                f"{LEAF_DNS_MARKER}\n"
                "dns_domain_suffix: example.com\n"
                'cluster_domain: "pgsql.{{ dns_domain_suffix }}"\n',
            )
            written = patch_leaf_dns_identity(
                config,
                "lab/x",
                dns_domain_suffix="ci.example.com",
            )
            self.assertEqual(len(written), 2)
            a = yaml.safe_load((all_dir / "atlas-a.yml").read_text(encoding="utf-8"))
            b = yaml.safe_load((all_dir / "atlas-b.yml").read_text(encoding="utf-8"))
            self.assertEqual(a["dns_domain_suffix"], "ci.example.com")
            self.assertEqual(b["dns_domain_suffix"], "ci.example.com")
            self.assertEqual(a["cluster_domain"], "kafka.{{ dns_domain_suffix }}")
            self.assertEqual(b["cluster_domain"], "pgsql.{{ dns_domain_suffix }}")

    def test_blank_suffix_is_noop_for_dns_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "group_vars" / "all" / "atlas-x.yml"
            original = (
                f"{LEAF_DNS_MARKER}\n"
                "dns_domain_suffix: example.com\n"
                'cluster_domain: "k8s.{{ dns_domain_suffix }}"\n'
            )
            _write(path, original)
            self.assertFalse(
                patch_group_vars_identity_lines(path, dns_domain_suffix="  ")
            )
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_secrets_overlay_never_discovered_or_patched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            all_dir = config / "group_vars" / "all"
            _write(
                all_dir / "atlas-redis.yml",
                f"{LEAF_DNS_MARKER}\ndns_domain_suffix: example.com\n",
            )
            secrets = all_dir / "atlas-redis.secrets.yml"
            _write(
                secrets,
                f"{LEAF_DNS_MARKER}\ndns_domain_suffix: secret.example.com\n",
            )
            names = [p.name for p in discover_leaf_dns_overlays(config)]
            self.assertEqual(names, ["atlas-redis.yml"])
            patch_leaf_dns_identity(
                config, "lab/x", dns_domain_suffix="lab.example.com"
            )
            secrets_data = yaml.safe_load(secrets.read_text(encoding="utf-8"))
            self.assertEqual(secrets_data["dns_domain_suffix"], "secret.example.com")

    def test_scrub_preserves_cluster_domain_jinja(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            path = config / "group_vars" / "all" / "atlas-core.yml"
            _write(
                path,
                f"{LEAF_DNS_MARKER}\n"
                "dns_domain_suffix: live.lab\n"
                'cluster_domain: "k8s.{{ dns_domain_suffix }}"\n',
            )
            scrub_leaf_dns_suffix_for_public_template(config)
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(data["dns_domain_suffix"], "example.com")
            self.assertEqual(data["cluster_domain"], "k8s.{{ dns_domain_suffix }}")

    def test_scrub_rewrites_literal_cluster_domain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            path = config / "group_vars" / "all" / "atlas-core.yml"
            _write(
                path,
                f"{LEAF_DNS_MARKER}\n"
                "dns_domain_suffix: live.com\n"
                "cluster_domain: k8s.live.com\n",
            )
            scrub_leaf_dns_suffix_for_public_template(config)
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            self.assertEqual(data["dns_domain_suffix"], "example.com")
            self.assertEqual(data["cluster_domain"], "k8s.{{ dns_domain_suffix }}")
            self.assertIn('cluster_domain: "k8s.{{ dns_domain_suffix }}"', text)

    def test_file_has_leaf_dns_identity_by_keys_or_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            by_marker = Path(tmp) / "m.yml"
            by_key = Path(tmp) / "k.yml"
            plain = Path(tmp) / "p.yml"
            _write(by_marker, f"{LEAF_DNS_MARKER}\nfoo: 1\n")
            _write(by_key, 'cluster_domain: "x.{{ dns_domain_suffix }}"\n')
            _write(plain, "redis_port: 6379\n")
            self.assertTrue(file_has_leaf_dns_identity(by_marker))
            self.assertTrue(file_has_leaf_dns_identity(by_key))
            self.assertFalse(file_has_leaf_dns_identity(plain))


if __name__ == "__main__":
    unittest.main()
