"""ADR 009 alias-removal Phase 0: hard-remove contract (historical lock)."""

from __future__ import annotations

import unittest
from pathlib import Path

from clusterctl.cli_args import SUBCOMMANDS

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
GATE = ROOT / "tests" / "test_adr_009_alias_removal_phase0.py"

_EXTERNAL_INVENTORY_PATHS = (
    "clusters/ci/infra/README.md",
    "clusters/ci/jenkins/README.md",
    "clusters/ci/kafka/README.md",
    "clusters/ci/postgresql/README.md",
    "clusters/ci/redis/README.md",
    "clusters/lab/pve-templates/README.md",
)
_EXTERNAL_COMPUTE_PATH = "docs/adr/001-tfstate-repo-prefix.md"


class Adr009AliasRemovalPhase0Test(unittest.TestCase):
    def test_adr_alias_removal_phase0_locked(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("## Alias removal (follow-up)", text)
        self.assertIn("Phase 0 locked", text)
        self.assertIn("**Hard remove**", text)
        self.assertIn("**No** silent shim", text)
        self.assertIn("**no** Variant S", text)
        self.assertIn("test_adr_009_alias_removal_phase0.py", text)
        self.assertIn("[x] Hard remove vs Variant S decided (Phase 0)", text)
        self.assertIn("[x] External caller inventory recorded (Phase 0)", text)
        self.assertIn("``./cluster stages``", text)
        self.assertIn("apply_play_cli_overrides", text)

    def test_external_inventory_listed(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("External callers inventory", text)
        self.assertIn("atlas-inventory", text)
        self.assertIn("atlas-compute-provision", text)
        for path in _EXTERNAL_INVENTORY_PATHS:
            self.assertIn(path, text, path)
        self.assertIn(_EXTERNAL_COMPUTE_PATH, text)
        self.assertIn("run --phases NAME --tags T", text)
        self.assertIn("./cluster stage NAME", text)
        self.assertIn("./cluster run --phases NAME", text)

    def test_phase1_supersedes_not_wired(self) -> None:
        """After Phase 1, aliases are gone; Phase 0 inventory/contract remains."""
        self.assertNotIn("stage", SUBCOMMANDS)
        self.assertNotIn("play", SUBCOMMANDS)
        self.assertIn("stages", SUBCOMMANDS)
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 1–5 done", adr)
        self.assertIn("[x] Argparse / ``cli_args`` remove (Phase 1)", adr)

    def test_changelog_and_index(self) -> None:
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("alias removal Phase 0", changelog)
        self.assertIn("hard remove", changelog.lower())
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("alias hard-removal Phase 1–5 done", index)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
