"""Post–ADR 009 cleanup A2: SoT docs phase counts match public templates."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from clusterctl.playbooks_config import load_cluster_config_v2_yaml
from tests.lab_support import FULL_K8S_INVOCATION_COUNT

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
TEMPLATE_ROOT = ROOT / "clusters" / "_template"
STACKS_DIR = ROOT / "docs" / "stacks"

# Default plan length for public scaffolds (golden templates are separate leaf).
EXPECTED_PHASE_COUNTS: dict[str, int] = {
    "k8s_full": 4,
    "infra_edge": 4,
    "redis": 3,
    "postgresql": 3,
    "kafka": 3,
    "jenkins_agent": 3,
    "gitlab_runner": 3,
    "pve_templates": 1,
}

# ASCII or Unicode arrows between phase tokens.
_ARROW = r"(?:-->|→|->)"

# Stale phrases that contradict golden-templates default plans.
_STALE_FIVE_PHASES = re.compile(
    r"(?:k8s_full|infra_edge|full k8s|Infra platform)[^\n]{0,80}\(5 phases\)|"
    r"Public SoT full k8s \(5 phases\)|"
    r"Infra platform only \(5 phases\)",
    re.IGNORECASE,
)
_STALE_K8S_FLOW_WITH_TEMPLATES = re.compile(
    rf"templates\s*{_ARROW}\s*provision\s*{_ARROW}\s*init\s*{_ARROW}\s*k8s-core"
)
_STALE_INFRA_FLOW_WITH_TEMPLATES = re.compile(
    rf"templates\s*{_ARROW}\s*provision\s*{_ARROW}\s*init-infra"
)
# Audit Phase 1: "Typical order: templates → …" (Unicode arrow missed by --> only).
_STALE_TYPICAL_ORDER_TEMPLATES = re.compile(
    r"Typical order:\s*`?templates`?",
    re.IGNORECASE,
)
_FACT_CACHE_REUSE = "Later init tags reuse `ansible_facts`"


class Adr009SotPhaseCountsA2Test(unittest.TestCase):
    def test_template_yaml_phase_counts(self) -> None:
        for name, expected in EXPECTED_PHASE_COUNTS.items():
            path = TEMPLATE_ROOT / name / "cluster.yaml"
            self.assertTrue(path.is_file(), path)
            cfg = load_cluster_config_v2_yaml(path)
            self.assertIsNotNone(cfg.phases, name)
            assert cfg.phases is not None
            self.assertEqual(
                len(cfg.phases.phases),
                expected,
                f"{name}: {list(cfg.phases.phases)}",
            )
            # Stack / k8s / infra default plans start at provision (not templates).
            if name != "pve_templates":
                self.assertEqual(
                    cfg.phases.phases[0],
                    "atlas-compute-provision/provision",
                    name,
                )
            else:
                self.assertEqual(
                    cfg.phases.phases[0],
                    "atlas-compute-provision/templates",
                )

    def test_k8s_full_invocation_count_matches_constant(self) -> None:
        cfg = load_cluster_config_v2_yaml(
            TEMPLATE_ROOT / "k8s_full" / "cluster.yaml"
        )
        assert cfg.phases is not None and cfg.playbooks is not None
        self.assertEqual(
            cfg.phases.invocation_count(cfg.playbooks),
            FULL_K8S_INVOCATION_COUNT,
        )

    def test_schema_doc_sot_table_four_phases(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("Public SoT full k8s (**4 phases**", text)
        self.assertIn("Infra platform only (**4 phases**", text)
        self.assertIn("pve_templates", text)
        self.assertIn("**4 phases**", text)
        self.assertRegex(text, r"on the order of \*\*95\*\*")
        self.assertIsNone(
            _STALE_FIVE_PHASES.search(text),
            "cluster-config-v2.md still claims 5 phases for SoT leaves",
        )
        # Detailed section already documents 4-phase flow without leading templates.
        self.assertIn("provision --> init --> k8s-core --> k8s-addons", text)
        self.assertNotRegex(text, _STALE_K8S_FLOW_WITH_TEMPLATES)
        self.assertIsNone(
            _STALE_TYPICAL_ORDER_TEMPLATES.search(text),
            "cluster-config-v2.md Typical order still leads with templates",
        )
        # Factory-only diagram remains allowed; stack typical starts at provision.
        self.assertIn("templates --> provision --> …           # pve_templates factory only", text)
        self.assertIn("provision --> init --> <stack>", text)
        self.assertIn("stack leaves start at `provision`", text)

    def test_readme_and_infra_stack_flows(self) -> None:
        readme = README.read_text(encoding="utf-8")
        self.assertIn("provision --> init --> k8s-core --> k8s-addons", readme)
        self.assertIn(
            "provision --> init-infra --> infra --> init-infra-post",
            readme,
        )
        self.assertNotRegex(readme, _STALE_K8S_FLOW_WITH_TEMPLATES)
        self.assertNotRegex(readme, _STALE_INFRA_FLOW_WITH_TEMPLATES)

        # Default phase tables must not list templates as a leaf alias row
        # (factory remains documented in compute-provision.md).
        stack_docs = sorted(STACKS_DIR.glob("*.md"))
        for path in stack_docs:
            if path.name == "compute-provision.md":
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(
                text,
                r"\|\s*`templates`\s*\|\s*`atlas-compute-provision/templates`",
                f"{path.name} still lists templates as a default leaf phase",
            )

    def test_stack_docs_no_duplicate_fact_cache_sentence(self) -> None:
        """Audit Phase 1.3: copy-paste doubled the fact_caching note."""
        for path in sorted(STACKS_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            count = text.count(_FACT_CACHE_REUSE)
            self.assertLessEqual(
                count,
                1,
                f"{path.name}: {_FACT_CACHE_REUSE!r} appears {count} times",
            )
            self.assertNotIn("\nyaml`.\n", text, f"{path.name}: corrupted fragment")

    def test_changelog_a2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("post-cleanup A2", text)
        self.assertIn("4 phases", text)
        self.assertIn("audit Phase 1", text)
        self.assertIn("Typical order", text)


if __name__ == "__main__":
    unittest.main()
