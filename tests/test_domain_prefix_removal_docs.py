"""Docs gate: --domain-prefix removal (operator contract Phase 3)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Operator-facing docs must not recommend the removed flag.
_OPERATOR_DOCS = (
    ROOT / "docs" / "clusters.md",
    ROOT / "docs" / "clusterctl.md",
    ROOT / "docs" / "adr" / "003-optional-cluster-yml.md",
    ROOT / "docs" / "stacks" / "README.md",
    ROOT / "clusters" / "_template" / "README.md",
    ROOT / "clusters" / "_template" / "cluster.yaml",
    ROOT / "clusters" / "_template" / "redis" / "README.md",
    ROOT / "clusters" / "_template" / "kafka" / "README.md",
    ROOT / "clusters" / "_template" / "postgresql" / "README.md",
    ROOT / "clusters" / "_template" / "k8s_full" / "README.md",
    ROOT / "clusters" / "_template" / "jenkins_agent" / "README.md",
    ROOT / "clusters" / "_template" / "infra_edge" / "README.md",
)


class DomainPrefixRemovalDocsTest(unittest.TestCase):
    def test_operator_docs_omit_domain_prefix_flag(self) -> None:
        for path in _OPERATOR_DOCS:
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("--domain-prefix", text, path)
            self.assertNotIn("domain_prefix", text, path)

    def test_clusters_md_leaf_dns_ownership_table(self) -> None:
        text = (ROOT / "docs" / "clusters.md").read_text(encoding="utf-8")
        self.assertIn("### Leaf DNS identity", text)
        self.assertIn("template/stack prefix", text)
        self.assertIn("--dns-suffix", text)
        self.assertIn("never rewrites `cluster_domain` prefixes", text)

    def test_adr_init_table_suffix_only(self) -> None:
        text = (ROOT / "docs" / "adr" / "003-optional-cluster-yml.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Patches **`dns_domain_suffix`**", text)
        self.assertIn("Does **not** rewrite `cluster_domain` stack prefixes", text)
        self.assertNotIn("Patches the same keys", text)

    def test_changelog_records_removal(self) -> None:
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("### Removed", text)
        self.assertIn("--domain-prefix", text)
        self.assertIn("template-owned", text)
        self.assertIn("fails hard", text)
        self.assertIn("literal `cluster_domain`", text)
        self.assertNotIn("removal verified", text.lower())

    def test_template_readmes_document_prefix_ownership(self) -> None:
        for rel in (
            "clusters/_template/jenkins_agent/README.md",
            "clusters/_template/infra_edge/README.md",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("--dns-suffix", text, rel)
            self.assertIn("template prefix", text, rel)


if __name__ == "__main__":
    unittest.main()
