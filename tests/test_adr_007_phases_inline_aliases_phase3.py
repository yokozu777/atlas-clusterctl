"""Phase 3 gate: ADR 007 — inventory labs omit top-level phase_aliases:."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import yaml

from clusterctl.paths import clusters_root
from clusterctl.playbooks_config import load_cluster_config_v2_yaml
from tests.lab_support import STACK_MARKERS, lab_id_for, present_deployable_ids

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "007-phases-inline-aliases.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"

_INVENTORY_ROOT = Path(
    os.environ.get(
        "ATLAS_INVENTORY_ROOT",
        str(ROOT.parent / "atlas-inventory"),
    )
)


def _infer_sample_ids() -> list[str]:
    found: list[str] = []
    for stack in STACK_MARKERS:
        lab = lab_id_for(stack)
        if lab is not None:
            found.append(lab)
    if found:
        return found
    return present_deployable_ids()


def _cluster_yaml_paths(root: Path) -> list[Path]:
    clusters = root / "clusters"
    if not clusters.is_dir():
        return []
    return sorted(clusters.rglob("cluster.yaml"))


def _live_phase_aliases_lines(text: str) -> list[int]:
    hits: list[int] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped == "phase_aliases:" or stripped.startswith("phase_aliases:"):
            hits.append(index)
    return hits


class Adr007PhasesInlineAliasesPhase3Test(unittest.TestCase):
    def test_adr_status_phase3(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn("[x] Inventory labs omit `phase_aliases:` (Phase 3)", text)
        self.assertIn("atlas-inventory", text)

    def test_adr_index_phase3(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("Phase 3", text)
        self.assertIn("atlas-inventory", text)

    def test_schema_doc_phase3(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("atlas-inventory", text)

    def test_inventory_labs_omit_phase_aliases(self) -> None:
        if not _INVENTORY_ROOT.is_dir():
            self.skipTest(f"atlas-inventory not at {_INVENTORY_ROOT}")
        paths = _cluster_yaml_paths(_INVENTORY_ROOT)
        self.assertGreater(len(paths), 0, _INVENTORY_ROOT)
        offenders: list[str] = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for line_no in _live_phase_aliases_lines(text):
                offenders.append(f"{path}:{line_no}")
            data = yaml.safe_load(text) or {}
            if isinstance(data, dict) and "phase_aliases" in data:
                offenders.append(f"{path}:parsed-key")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_inventory_deployable_samples_load_inline(self) -> None:
        samples = _infer_sample_ids()
        if not samples:
            self.skipTest("no deployable labs discovered")
        croot = clusters_root()
        for leaf in samples:
            path = croot.joinpath(*leaf.split("/")) / "cluster.yaml"
            if not path.is_file():
                self.skipTest(f"missing sample leaf {path}")
            cfg = load_cluster_config_v2_yaml(path)
            assert cfg.phases is not None
            self.assertTrue(cfg.phases.phases, leaf)
            self.assertTrue(cfg.phases.phase_aliases, leaf)
            # Spot-check: every alias target is in the phases list.
            for alias, ref in cfg.phases.phase_aliases.items():
                self.assertIn(ref, cfg.phases.phases, f"{leaf}:{alias}")


if __name__ == "__main__":
    unittest.main()
