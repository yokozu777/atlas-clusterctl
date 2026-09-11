"""Phase 3 gate: ADR 006 — inventory labs omit redundant playbooks_enabled: true."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import yaml

from clusterctl.paths import clusters_root
from clusterctl.playbooks_config import load_cluster_config_v2_yaml
from tests.lab_support import STACK_MARKERS, lab_id_for, present_deployable_ids

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "006-redundant-playbooks-enabled.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"

_INVENTORY_ROOT = Path(
    os.environ.get(
        "ATLAS_INVENTORY_ROOT",
        str(ROOT.parent / "atlas-inventory"),
    )
)


def _infer_sample_ids() -> list[str]:
    """One deployable leaf per known stack marker (skip missing stacks)."""
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


class Adr006RedundantPlaybooksEnabledPhase3Test(unittest.TestCase):
    def test_adr_status_phase3(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn("[x] Inventory labs omit redundant `true`", text)
        self.assertIn(
            "[x] Public templates omit redundant `playbooks_enabled: true`",
            text,
        )

    def test_adr_index_phase3(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 006", text)
        self.assertIn("Phase 3", text)
        self.assertIn("atlas-inventory", text)

    def test_inventory_labs_omit_playbooks_enabled_true(self) -> None:
        if not _INVENTORY_ROOT.is_dir():
            self.skipTest(f"atlas-inventory not at {_INVENTORY_ROOT}")
        paths = _cluster_yaml_paths(_INVENTORY_ROOT)
        self.assertGreater(len(paths), 0, _INVENTORY_ROOT)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("playbooks_enabled: true", text, path)
            self.assertNotIn("# playbooks_enabled: true", text, path)
            data = yaml.safe_load(text) or {}
            if isinstance(data, dict):
                # Key may be absent; if present must not be redundant true-only noise.
                # Explicit false would still be allowed — none expected in labs today.
                if "playbooks_enabled" in data:
                    self.assertIs(data["playbooks_enabled"], False, path)

    def test_inventory_deployable_samples_infer_enabled(self) -> None:
        samples = _infer_sample_ids()
        if not samples:
            self.skipTest("no deployable labs discovered")
        croot = clusters_root()
        for leaf in samples:
            path = croot.joinpath(*leaf.split("/")) / "cluster.yaml"
            if not path.is_file():
                self.skipTest(f"missing sample leaf {path}")
            cfg = load_cluster_config_v2_yaml(path)
            self.assertIsNone(cfg.playbooks_enabled, leaf)
            self.assertTrue(cfg.effective_playbooks_enabled(), leaf)
            self.assertTrue(cfg.playbooks and cfg.playbooks.repos, leaf)


if __name__ == "__main__":
    unittest.main()
