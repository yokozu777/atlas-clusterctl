"""Cleanup Phase 3 gate: ADR 008 — Variant B verify + close."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from tests.lab_support import lab_id_for

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
LOCAL_LABS = ROOT / "docs" / "local-labs.md"
RUN_CI = ROOT / "tests" / "run_ci.sh"
SIBLING_INVENTORY = ROOT.parent / "atlas-inventory"
SCRIPT_BASENAME = "check-no-legacy-phase-window"

_ALLOW_EXACT = {
    "CHANGELOG.md",
    "docs/adr/008-phases-cli-selector.md",
}
_ALLOW_PREFIXES = (
    "tests/test_adr_008_legacy_window_cleanup_",
    "docs/adr/",
)
_SKIP_DIR_PARTS = {
    ".git",
    "__pycache__",
    "tfstate-repo",
    "workspace",
    ".pytest_cache",
}


def _skip_controller_junk(part: str) -> bool:
    """Ignore durable-checkout clones and local bak trees under the controller root."""
    return (
        part in _SKIP_DIR_PARTS
        or part.startswith("tfstate.legacy-bak")
        or part.startswith("tfstate.local.bak")
    )


def _basename_offenders(root: Path) -> list[str]:
    offenders: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(_skip_controller_junk(part) for part in path.parts):
            continue
        if path.suffix not in {".py", ".md", ".sh", ".yml", ".yaml", ".txt"} and path.name != "CHANGELOG.md":
            continue
        rel = path.relative_to(root).as_posix()
        if rel in _ALLOW_EXACT or any(rel.startswith(p) for p in _ALLOW_PREFIXES):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if SCRIPT_BASENAME in text:
            offenders.append(rel)
    return sorted(offenders)


class Adr008LegacyWindowCleanupPhase3Test(unittest.TestCase):
    def test_adr_cleanup_phase3_done(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Cleanup Phase 3 (done)", text)
        self.assertIn("Cleanup Phase 3 acceptance", text)
        self.assertIn("test_adr_008_legacy_window_cleanup_phase3.py", text)
        self.assertIn(
            "[x] Cleanup Phase 3 — verify + close (Variant B complete)",
            text,
        )
        self.assertIn("**Done** — cleanup complete", text)
        self.assertIn("Variant B** complete", text)
        self.assertIn("0–3 complete", text)

    def test_script_basename_only_in_history_surfaces(self) -> None:
        offenders = _basename_offenders(ROOT)
        self.assertEqual(
            offenders,
            [],
            "script basename leaked outside ADR/CHANGELOG/cleanup gates:\n"
            + "\n".join(offenders),
        )
        for path in (CLUSTERCTL_DOC, LOCAL_LABS):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(SCRIPT_BASENAME, text, path.name)
            self.assertNotIn("./scripts/check-no-legacy-phase-window.sh", text, path.name)

    def test_inventory_script_gone_and_tfstate_intact(self) -> None:
        if not (SIBLING_INVENTORY / "clusters").is_dir():
            self.skipTest("sibling atlas-inventory not present")
        script = SIBLING_INVENTORY / "scripts" / "check-no-legacy-phase-window.sh"
        self.assertFalse(script.is_file(), script)
        proc = subprocess.run(
            ["git", "ls-files", "--", "scripts/check-no-legacy-phase-window.sh"],
            cwd=SIBLING_INVENTORY,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")
        tfstate_root = SIBLING_INVENTORY / "tfstate"
        if not tfstate_root.is_dir():
            self.skipTest(f"no tfstate tree at {tfstate_root}")
        for stack in ("infra", "k8s"):
            leaf = lab_id_for(stack)
            if leaf is None:
                self.skipTest(f"no local lab for stack {stack!r}")
            state = tfstate_root / leaf / "terraform.tfstate"
            self.assertTrue(state.is_file(), state)

    def test_permanent_hygiene_still_present(self) -> None:
        phase4 = (ROOT / "tests" / "test_adr_008_phases_cli_selector_phase4.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("test_argparse_plan_run_reject_from_to_keep_init_from", phase4)
        self.assertIn("test_grep_retired_dests_allowlist", phase4)
        self.assertFalse((ROOT / "tests" / "adr_008_legacy_cli.py").is_file())

    def test_run_ci_script_exists(self) -> None:
        self.assertTrue(RUN_CI.is_file(), RUN_CI)
        self.assertTrue(RUN_CI.stat().st_mode & 0o111, "run_ci.sh must be executable")

    def test_adr008_suite_is_the_phase3_offline_gate(self) -> None:
        """Phase 3 offline proof is the ADR 008 suite + hygiene, not full run_ci debt."""
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("test_adr_008*.py", text)
        self.assertIn("66 OK", text)
        self.assertNotIn("| `test_adr_008*.py` | 65 OK |", text)
        self.assertIn("acceptance-time proof", text)
        self.assertIn("full `run_ci` not required", text)
        self.assertIn("out of scope** for Variant B", text)
        self.assertIn("pre-existing", text.lower())
        self.assertIn("superseded by Cleanup Phase 2/3 Done", text)
        self.assertIn("Superseded by Variant B Cleanup Phases 0–3", CHANGELOG.read_text(encoding="utf-8"))

    def test_adr_index_and_changelog(self) -> None:
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("cleanup B complete", index)
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008 cleanup Variant B — Phase 3", changelog)
        self.assertIn("test_adr_008_legacy_window_cleanup_phase3.py", changelog)
        self.assertIn("pre-existing", changelog.lower())


if __name__ == "__main__":
    unittest.main()
