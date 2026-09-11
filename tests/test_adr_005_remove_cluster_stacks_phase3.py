"""Phase 3 gate: ADR 005 — stacks: removed from templates/docs (historical)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "005-remove-cluster-stacks.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"
CLUSTERS_DOC = ROOT / "docs" / "clusters.md"
VALIDATE_DOC = ROOT / "docs" / "validate.md"
CHANGELOG = ROOT / "CHANGELOG.md"
BASELINE = ROOT / "clusters" / "default" / "default" / "cluster.yaml"
PARENT_SCAFFOLD = ROOT / "clusters" / "_template" / "cluster.yaml"

_TEMPLATES = (
    "k8s_full",
    "infra_edge",
    "jenkins_agent",
    "postgresql",
    "redis",
    "kafka",
)

_PRODUCT_STACK_DOCS = (
    "jenkins-agent.md",
    "redis.md",
    "kafka.md",
    "postgresql.md",
    "infra-edge.md",
    "k8s-core.md",
    "k8s-addons.md",
)

_INVENTORY_ROOT = Path(
    os.environ.get(
        "ATLAS_INVENTORY_ROOT",
        str(ROOT.parent / "atlas-inventory"),
    )
)


def _cluster_yaml_paths(root: Path) -> list[Path]:
    clusters = root / "clusters"
    if not clusters.is_dir():
        return []
    return sorted(clusters.rglob("cluster.yaml"))


class Adr005RemoveClusterStacksPhase3Test(unittest.TestCase):
    def test_adr_documents_phase3_outcomes(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted", text)
        self.assertIn("Phase 3", text)
        self.assertIn("[x] Public `_template/*/cluster.yaml` omit `stacks:`", text)
        self.assertIn("[x] Org baseline omits `stacks:`", text)
        self.assertIn("[x] Inventory labs omit `stacks:`", text)
        self.assertIn(
            "[x] Docs (`cluster-config-v2`, validate, product stacks prose) updated",
            text,
        )

    def test_public_templates_omit_stacks(self) -> None:
        for name in _TEMPLATES:
            path = ROOT / "clusters" / "_template" / name / "cluster.yaml"
            self.assertTrue(path.is_file(), path)
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict, path)
            self.assertNotIn("stacks", data, path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\nstacks:\n", text, path)
            self.assertNotIn("skip_phase_refs", text, path)

        for path in (BASELINE, PARENT_SCAFFOLD):
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\nstacks:\n", text, path)
            self.assertNotIn("# stacks:", text, path)
            self.assertNotIn("skip_phase_refs", text, path)

    def test_product_clusters_tree_has_no_stacks_key(self) -> None:
        for path in _cluster_yaml_paths(ROOT):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\nstacks:\n", text, path)
            data = yaml.safe_load(text) or {}
            if isinstance(data, dict):
                self.assertNotIn("stacks", data, path)

    def test_inventory_labs_omit_stacks_when_present(self) -> None:
        if not _INVENTORY_ROOT.is_dir():
            self.skipTest(f"atlas-inventory not at {_INVENTORY_ROOT}")
        paths = _cluster_yaml_paths(_INVENTORY_ROOT)
        self.assertGreater(len(paths), 0, _INVENTORY_ROOT)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\nstacks:\n", text, path)
            data = yaml.safe_load(text) or {}
            if isinstance(data, dict):
                self.assertNotIn("stacks", data, path)

    def test_schema_and_ops_docs_reworded(self) -> None:
        schema = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("adr/005-remove-cluster-stacks.md", schema)
        self.assertNotIn("## `stacks`", schema)
        self.assertNotIn("| `stacks` |", schema)
        self.assertIn("plan sot", schema.lower())

        clusters = CLUSTERS_DOC.read_text(encoding="utf-8")
        self.assertIn("phases:", clusters)
        self.assertNotIn("stacks.*", clusters)

        validate = VALIDATE_DOC.read_text(encoding="utf-8")
        self.assertIn("phases:", validate)
        self.assertNotIn("or `stacks`", validate)

    def test_product_stack_docs_drop_yaml_stacks_prose(self) -> None:
        for name in _PRODUCT_STACK_DOCS:
            path = ROOT / "docs" / "stacks" / name
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("stacks.infra", text, name)
            self.assertNotIn("stacks.k8s", text, name)
            self.assertNotIn("skip_phase_refs", text, name)

    def test_changelog_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 005", text)
        self.assertIn("Phase 3", text)
        # Phase 3 work is folded into the Phases 0–4 complete summary.
        self.assertIn("templates", text.lower())


if __name__ == "__main__":
    unittest.main()
