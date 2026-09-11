"""Phase 2 gate: ADR 003 — init/export patch Leaf DNS overlays, not cluster.yml."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.tools.export_template import export_template
from clusterctl.leaf_dns import (
    LEAF_DNS_MARKER,
    discover_leaf_dns_overlays,
    patch_leaf_dns_identity,
    remove_legacy_cluster_yml,
    scrub_leaf_dns_suffix_for_public_template,
)

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "003-optional-cluster-yml.md"
CLUSTERS_DOC = ROOT / "docs" / "clusters.md"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Adr003OptionalClusterYmlPhase2Test(unittest.TestCase):
    def test_adr_status_phase2(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 2", text)
        self.assertIn("init --dns-suffix", text.lower().replace("`", ""))
        # checklist item for init must be marked done
        self.assertIn(
            "[x] `./cluster init` no longer writes/requires `cluster.yml`",
            text,
        )

    def test_clusters_md_phase2_runtime(self) -> None:
        text = CLUSTERS_DOC.read_text(encoding="utf-8")
        self.assertIn("atlas-*.yml", text)
        self.assertIn("--dns-suffix", text)
        self.assertNotIn("--domain-prefix", text)

    def test_source_has_no_domain_prefix_api(self) -> None:
        """Removed init flag must not linger in Leaf DNS / init wiring."""
        root = ROOT / "clusterctl"
        for rel in ("leaf_dns.py", "cluster_init.py", "__main__.py"):
            text = (root / rel).read_text(encoding="utf-8")
            self.assertNotIn("domain_prefix", text, rel)
            self.assertNotIn("domain-prefix", text, rel)

    def test_discover_marker_and_legacy_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            all_dir = config / "group_vars" / "all"
            _write(
                all_dir / "atlas-redis.yml",
                f"{LEAF_DNS_MARKER}\ndns_domain_suffix: a.com\ncluster_domain: \"r.{{{{ dns_domain_suffix }}}}\"\n",
            )
            _write(all_dir / "atlas-other.yml", "redis_port: 6379\n")
            _write(
                all_dir / "cluster.yml",
                'dns_domain_suffix: legacy.com\ncluster_domain: "k8s.{{ dns_domain_suffix }}"\n',
            )
            _write(all_dir / "atlas-redis.secrets.yml", "vip_auth_pass: x\n")
            names = [path.name for path in discover_leaf_dns_overlays(config)]
            self.assertEqual(names, ["atlas-redis.yml", "cluster.yml"])

    def test_patch_updates_all_overlays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            all_dir = config / "group_vars" / "all"
            for name in ("atlas-a.yml", "atlas-b.yml"):
                _write(
                    all_dir / name,
                    f"{LEAF_DNS_MARKER}\ndns_domain_suffix: example.com\n"
                    'cluster_domain: "k8s.{{ dns_domain_suffix }}"\n',
                )
            written = patch_leaf_dns_identity(
                config,
                "lab/x",
                dns_domain_suffix="lab.example.com",
            )
            self.assertEqual(len(written), 2)
            for name in ("atlas-a.yml", "atlas-b.yml"):
                text = (all_dir / name).read_text(encoding="utf-8")
                data = yaml.safe_load(text)
                self.assertEqual(data["dns_domain_suffix"], "lab.example.com")
                self.assertEqual(
                    data["cluster_domain"],
                    "k8s.{{ dns_domain_suffix }}",
                )
                self.assertIn(
                    'cluster_domain: "k8s.{{ dns_domain_suffix }}"',
                    text,
                )

    def test_export_scrubs_overlays_and_stub_cluster_yml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "inventory"
            target_root = root / "product"
            lab = source_root / "fixture" / "k8s"
            _write(lab / "cluster.yaml", "schema_version: 2\nid: lab\n")
            _write(lab / "hosts", "[k8s_masters]\nm1\n")
            _write(
                lab / "group_vars" / "all" / "atlas-k8s-core.yml",
                f"{LEAF_DNS_MARKER}\ndns_domain_suffix: live.lab\n"
                'cluster_domain: "k8s.{{ dns_domain_suffix }}"\n',
            )
            _write(
                lab / "group_vars" / "all" / "cluster.yml",
                'dns_domain_suffix: live.lab\ncluster_domain: "k8s.{{ dns_domain_suffix }}"\n',
            )
            target = export_template(
                source_id="fixture/k8s",
                template_name="k8s_full",
                source_root=source_root,
                target_root=target_root,
            )
            core = yaml.safe_load(
                (target / "group_vars" / "all" / "atlas-k8s-core.yml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(core["dns_domain_suffix"], "example.com")
            self.assertFalse((target / "group_vars" / "all" / "cluster.yml").exists())

    def test_scrub_helpers_standalone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            _write(
                config / "group_vars" / "all" / "atlas-x.yml",
                f"{LEAF_DNS_MARKER}\ndns_domain_suffix: live.com\n",
            )
            scrub_leaf_dns_suffix_for_public_template(config)
            data = yaml.safe_load(
                (config / "group_vars" / "all" / "atlas-x.yml").read_text(encoding="utf-8")
            )
            self.assertEqual(data["dns_domain_suffix"], "example.com")
            _write(
                config / "group_vars" / "all" / "cluster.yml",
                "dns_domain_suffix: still.live\n",
            )
            self.assertTrue(remove_legacy_cluster_yml(config))
            self.assertFalse((config / "group_vars" / "all" / "cluster.yml").exists())


if __name__ == "__main__":
    unittest.main()
