"""Phase 3 gate: ADR 003 — templates/inventory omit group_vars/all/cluster.yml."""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.lab_support import (
    PUBLIC_INFRA_TEMPLATE,
    PUBLIC_JENKINS_TEMPLATE,
    PUBLIC_K8S_TEMPLATE,
    PUBLIC_KAFKA_TEMPLATE,
    PUBLIC_POSTGRESQL_TEMPLATE,
    PUBLIC_REDIS_TEMPLATE,
    present_deployable_ids,
)

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "003-optional-cluster-yml.md"
CLUSTERS_DOC = ROOT / "docs" / "clusters.md"
CLUSTERS = ROOT / "clusters"

_PUBLIC_LEAVES = (
    CLUSTERS / "_template",
    PUBLIC_K8S_TEMPLATE,
    PUBLIC_INFRA_TEMPLATE,
    PUBLIC_JENKINS_TEMPLATE,
    PUBLIC_REDIS_TEMPLATE,
    PUBLIC_POSTGRESQL_TEMPLATE,
    PUBLIC_KAFKA_TEMPLATE,
    CLUSTERS / "default",
)


class Adr003OptionalClusterYmlPhase3Test(unittest.TestCase):
    def test_adr_status_phase3(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 3", text)
        self.assertIn("[x] Templates/inventory may omit `cluster.yml`", text)

    def test_clusters_md_phase3_runtime(self) -> None:
        text = CLUSTERS_DOC.read_text(encoding="utf-8")
        self.assertIn("omit", text.lower())
        self.assertIn("atlas-*.yml", text)
        self.assertIn("adr/003-optional-cluster-yml.md", text)

    def test_public_templates_omit_cluster_yml(self) -> None:
        missing: list[str] = []
        present: list[str] = []
        for leaf in _PUBLIC_LEAVES:
            stub = leaf / "group_vars" / "all" / "cluster.yml"
            rel = stub.relative_to(ROOT)
            if not (leaf / "group_vars" / "all").is_dir():
                continue
            if stub.exists():
                present.append(str(rel))
            else:
                missing.append(str(rel))
        self.assertEqual(present, [], f"Phase 3 stubs must be deleted: {present}")
        self.assertTrue(missing, "expected at least one public group_vars/all without stub")

    def test_inventory_labs_omit_cluster_yml_when_present(self) -> None:
        from clusterctl.paths import clusters_root

        croot = clusters_root(ROOT)
        for cluster_id in present_deployable_ids():
            parts = tuple(p for p in cluster_id.split("/") if p)
            stub = croot.joinpath(*parts) / "group_vars" / "all" / "cluster.yml"
            self.assertFalse(
                stub.exists(),
                f"ADR 003 Phase 3: inventory lab still has stub: {stub}",
            )

    def test_conventional_list_omits_cluster_yml(self) -> None:
        from clusterctl.cluster_vars_loader import CONVENTIONAL_GROUP_VARS_ALL

        self.assertNotIn("cluster.yml", CONVENTIONAL_GROUP_VARS_ALL)


if __name__ == "__main__":
    unittest.main()
