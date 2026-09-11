"""Phase 0 gate: ADR 005 — remove cluster.yaml stacks (historical contract)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "005-remove-cluster-stacks.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"
CHANGELOG = ROOT / "CHANGELOG.md"

_TEMPLATE_NAMES = (
    "k8s_full",
    "infra_edge",
    "jenkins_agent",
    "postgresql",
    "redis",
    "kafka",
)


class Adr005RemoveClusterStacksPhase0Test(unittest.TestCase):
    def test_adr_exists_and_accepted_phase0(self) -> None:
        self.assertTrue(ADR.is_file(), ADR)
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted", text)
        self.assertIn("Phase 0", text)
        self.assertIn("no behavior change", text.lower())
        self.assertIn("phases:", text)
        self.assertIn("skip_phase_refs", text)
        self.assertIn("provision_stack", text)
        self.assertIn("docs/stacks/", text)
        self.assertIn("Out of scope", text)
        for phase in ("Phase 1", "Phase 2", "Phase 3", "Phase 4"):
            self.assertIn(phase, text, phase)

    def test_replacement_map_and_inference_matrix(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Replacement map", text)
        self.assertIn("Intent inference matrix", text)
        for needle in (
            "atlas-k8s-core/cluster",
            "atlas-k8s-addons/addons",
            "atlas-infra-edge/infra",
            "atlas-redis/cluster",
            "atlas-kafka/cluster",
            "atlas-jenkins-agent/agent",
        ):
            self.assertIn(needle, text, needle)

    def test_breaking_changes_checklist_present(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Breaking changes checklist", text)
        self.assertIn("Plan does not apply `skip_phase_refs`", text)
        self.assertIn("Present `stacks:` → hard error", text)

    def test_adr_index_and_docs_index(self) -> None:
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("005-remove-cluster-stacks.md", index)
        self.assertIn("Accepted (Phase", index)
        docs = DOCS_INDEX.read_text(encoding="utf-8")
        self.assertIn("005", docs)
        self.assertIn("stacks", docs)

    def test_schema_doc_points_at_adr005(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("adr/005-remove-cluster-stacks.md", text)
        self.assertIn("Phase ", text)

    def test_adr_inventories_template_paths(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        for name in _TEMPLATE_NAMES:
            self.assertIn(f"_template/{name}/cluster.yaml", text, name)

    def test_changelog_mentions_adr005_phase0(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 005", text)
        self.assertIn("Phase 0", text)
        self.assertIn("005-remove-cluster-stacks.md", text)


if __name__ == "__main__":
    unittest.main()
