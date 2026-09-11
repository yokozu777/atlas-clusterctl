"""Phase 4 gate: ADR 008 — remove plan/run ``--from``/``--to``; dest-name hygiene."""

from __future__ import annotations

import contextlib
import inspect
import io
import subprocess
import unittest
from pathlib import Path

from clusterctl import __main__ as main_mod
from clusterctl.phase_selector import resolve_cli_phase_window

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
MAIN = ROOT / "clusterctl" / "__main__.py"
SELECTOR = ROOT / "clusterctl" / "phase_selector.py"

_RETIRED_DESTS = ("from_stage", "to_stage")

# Retired plan/run dest names may appear only in CHANGELOG / ADR / phase gates.
_ALLOWLIST_PREFIXES = (
    "CHANGELOG.md",
    "docs/adr/008-phases-cli-selector.md",
    "tests/test_adr_008_phases_cli_selector_",
    "tests/test_adr_008_legacy_window_cleanup_",
    "notes/report_clusterctl.md",
)


def _is_allowed(rel: str) -> bool:
    return any(rel == p or rel.startswith(p) for p in _ALLOWLIST_PREFIXES)


class Adr008PhasesCliSelectorPhase4Test(unittest.TestCase):
    def test_adr_status_phase4(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        # Status may advance past Phase 4; Phase 4 deliverables stay checked.
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("[x] Remove `--from`/`--to` (Phase 4)", text)
        self.assertIn("removed", text.lower())
        self.assertIn("Current runtime (Phase", text)
        # Permanent hygiene after Variant B Cleanup Phase 1.
        self.assertIn("from_stage", text)
        self.assertIn("to_stage", text)

    def test_adr_index_phase4(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)
        self.assertIn("008-phases-cli-selector.md", text)

    def test_changelog_phase4(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008", text)
        self.assertIn("Phase 4", text)
        self.assertIn("from_stage", text)
        self.assertIn("to_stage", text)

    def test_clusterctl_doc_no_plan_run_from_to(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertRegex(text, r"ADR 008 Phase [45]")
        self.assertIn("removed", text.lower())
        plan_section = text.split("### `plan`", 1)[1].split("### `run`", 1)[0]
        run_section = text.split("### `run`", 1)[1].split("### `stages`", 1)[0]
        for section in (plan_section, run_section):
            self.assertNotIn("--from", section)
            self.assertNotIn("--to", section)

    def test_main_has_no_plan_run_legacy_dests(self) -> None:
        text = MAIN.read_text(encoding="utf-8")
        self.assertNotIn('dest="from_stage"', text)
        self.assertNotIn('dest="to_stage"', text)
        self.assertIn('"--phases"', text)
        # init --from remains (different meaning).
        self.assertIn('dest="from_cluster"', text)

    def test_selector_is_phases_only(self) -> None:
        params = list(inspect.signature(resolve_cli_phase_window).parameters)
        self.assertEqual(params, ["phases_selector"])
        text = SELECTOR.read_text(encoding="utf-8")
        self.assertNotIn("do not combine --phases with --from/--to", text)

    def test_argparse_plan_run_reject_from_to_keep_init_from(self) -> None:
        parser = main_mod._build_parser()
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            with self.assertRaises(SystemExit):
                parser.parse_args(["plan", "--from", "init", "--to", "provision"])
            with self.assertRaises(SystemExit):
                parser.parse_args(["run", "--to", "k8s-addons"])
        args = parser.parse_args(["init", "lab/x", "--from", "default"])
        self.assertEqual(args.from_cluster, "default")
        args = parser.parse_args(["plan", "--phases", "provision..init"])
        self.assertEqual(args.phases_selector, "provision..init")

    def test_grep_retired_dests_allowlist(self) -> None:
        offenders: list[str] = []
        for needle in _RETIRED_DESTS:
            proc = subprocess.run(
                [
                    "git",
                    "grep",
                    "-n",
                    "-I",
                    "--full-name",
                    needle,
                    "--",
                    ".",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                rel = line.split(":", 1)[0]
                if not _is_allowed(rel):
                    offenders.append(line)
        self.assertEqual(
            offenders,
            [],
            "retired plan/run dest leaked outside allowlist:\n"
            + "\n".join(offenders),
        )

    def test_no_legacy_docs_scanner_module(self) -> None:
        """Cleanup Variant B Phase 1: Python docs twin SoT removed."""
        self.assertFalse(
            (ROOT / "tests" / "adr_008_legacy_cli.py").is_file(),
            "adr_008_legacy_cli.py must be deleted (Cleanup Phase 1)",
        )
        self.assertFalse(
            (ROOT / "tests" / "test_adr_008_legacy_cli.py").is_file(),
            "test_adr_008_legacy_cli.py must be deleted (Cleanup Phase 1)",
        )


if __name__ == "__main__":
    unittest.main()
