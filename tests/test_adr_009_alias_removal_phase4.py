"""ADR 009 alias-removal Phase 4: external callers migrated to ``run --phases``."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"

SIBLING_INVENTORY = ROOT.parent / "atlas-inventory"
SIBLING_COMPUTE = ROOT.parent / "atlas-compute-provision"

_INVENTORY_PATHS = (
    "clusters/ci/infra/README.md",
    "clusters/ci/jenkins/README.md",
    "clusters/ci/kafka/README.md",
    "clusters/ci/postgresql/README.md",
    "clusters/ci/redis/README.md",
    "clusters/lab/pve-templates/README.md",
)
_COMPUTE_PATH = "docs/adr/001-tfstate-repo-prefix.md"

_TEACH_PLAY = re.compile(r"\./cluster play\b")
_TEACH_STAGE = re.compile(r"\./cluster stage\b")  # not ``stages``

# Broader hygiene: markdown / ADR under sibling roots (skip huge binary trees).
_SCAN_GLOBS = ("**/*.md", "**/*.rst", "**/*.txt")


def _hits(text: str) -> list[str]:
    out: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _TEACH_PLAY.search(line):
            out.append(f"{lineno}:play:{line.strip()}")
        if _TEACH_STAGE.search(line):
            out.append(f"{lineno}:stage:{line.strip()}")
    return out


class Adr009AliasRemovalPhase4Test(unittest.TestCase):
    def test_adr_phase4_checklist(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("[x] External READMEs / sibling ADR migrated (Phase 4)", text)
        self.assertIn("test_adr_009_alias_removal_phase4.py", text)
        self.assertIn("alias removal phase 4", text.lower())
        self.assertIn("Phase 1–5 done", text)
        self.assertIn("scan clean", text.lower())
        # Inventory table records migration.
        self.assertIn("**migrated**", text.lower())
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("alias hard-removal Phase 1–5 done", index)

    def test_changelog_phase4(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("alias removal Phase 4", text)
        self.assertIn("test_adr_009_alias_removal_phase4.py", text)
        self.assertIn("atlas-inventory", text)
        self.assertIn("atlas-compute-provision", text)

    def test_inventoried_paths_migrated(self) -> None:
        if not SIBLING_INVENTORY.is_dir():
            self.skipTest(f"sibling atlas-inventory not at {SIBLING_INVENTORY}")
        if not SIBLING_COMPUTE.is_dir():
            self.skipTest(f"sibling atlas-compute-provision not at {SIBLING_COMPUTE}")

        for rel in _INVENTORY_PATHS:
            path = SIBLING_INVENTORY / rel
            self.assertTrue(path.is_file(), path)
            hits = _hits(path.read_text(encoding="utf-8"))
            self.assertEqual(hits, [], f"{rel} still teaches stage/play:\n" + "\n".join(hits))
            body = path.read_text(encoding="utf-8")
            self.assertIn("./cluster run", body, rel)

        compute = SIBLING_COMPUTE / _COMPUTE_PATH
        self.assertTrue(compute.is_file(), compute)
        hits = _hits(compute.read_text(encoding="utf-8"))
        self.assertEqual(
            hits,
            [],
            f"{_COMPUTE_PATH} still teaches stage/play:\n" + "\n".join(hits),
        )
        self.assertIn("./cluster run --phases provision", compute.read_text(encoding="utf-8"))

    def test_sibling_trees_scan_clean(self) -> None:
        """Full sibling markdown scan (Phase 4 done-when: scan clean)."""
        missing: list[str] = []
        if not SIBLING_INVENTORY.is_dir():
            missing.append("atlas-inventory")
        if not SIBLING_COMPUTE.is_dir():
            missing.append("atlas-compute-provision")
        if missing:
            self.skipTest(f"sibling repos not present: {missing}")

        bad: list[str] = []
        for root, label in (
            (SIBLING_INVENTORY, "atlas-inventory"),
            (SIBLING_COMPUTE, "atlas-compute-provision"),
        ):
            seen: set[Path] = set()
            for pattern in _SCAN_GLOBS:
                for path in root.glob(pattern):
                    if not path.is_file() or path in seen:
                        continue
                    seen.add(path)
                    # Skip vendored / runtime trees (materialized playbook clones).
                    parts = set(path.parts)
                    if parts & {".git", "node_modules", ".terraform", "workspace"}:
                        continue
                    try:
                        text = path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        continue
                    for hit in _hits(text):
                        bad.append(f"{label}/{path.relative_to(root)}:{hit}")
        self.assertEqual(bad, [], "sibling docs still teach ./cluster stage|play:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
