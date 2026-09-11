"""Phase 0 gate: ADR 003 (optional cluster.yml) is accepted and cross-linked."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "003-optional-cluster-yml.md"
CLUSTERS_DOC = ROOT / "docs" / "clusters.md"
LOADER = ROOT / "clusterctl" / "cluster_vars_loader.py"


class Adr003OptionalClusterYmlPhase0Test(unittest.TestCase):
    def test_adr_exists_and_accepted(self) -> None:
        self.assertTrue(ADR.is_file(), ADR)
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted", text)
        self.assertIn("Phase 0", text)
        # Target contract must be explicit
        self.assertIn("group_vars/all/cluster.yml", text)
        self.assertIn("MUST NOT", text)
        self.assertIn("atlas-*.yml", text)
        self.assertIn("provision_stack", text)
        self.assertIn("controller_extra_vars", text)
        # Implementation roadmap bound
        for phase in ("Phase 1", "Phase 2", "Phase 3", "Phase 4"):
            self.assertIn(phase, text, phase)

    def test_breaking_changes_checklist_present(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Breaking changes checklist", text)
        self.assertIn("ClusterContext.cluster_var_file", text)
        self.assertIn("primary_cluster_var_file", text)
        self.assertIn("./cluster init", text)

    def test_clusters_md_links_contract_and_adr(self) -> None:
        text = CLUSTERS_DOC.read_text(encoding="utf-8")
        self.assertIn("Leaf filesystem contract", text)
        self.assertIn("adr/003-optional-cluster-yml.md", text)
        self.assertIn("cluster_yml_legacy", text)

    def test_loader_points_at_adr(self) -> None:
        text = LOADER.read_text(encoding="utf-8")
        self.assertIn("docs/adr/003-optional-cluster-yml.md", text)
        self.assertIn("PRIMARY_CLUSTER_VAR", text)
        self.assertIn("optional_cluster_var_file", text)


if __name__ == "__main__":
    unittest.main()
