"""Phase 1 gate: ADR 009 — ``run`` override flags + policy wiring."""

from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

import clusterctl.__main__ as main_mod

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
CHANGELOG = ROOT / "CHANGELOG.md"
MAIN = ROOT / "clusterctl" / "__main__.py"
POLICY = ROOT / "clusterctl" / "run_overrides.py"
CONTRACT = ROOT / "tests" / "test_run_overrides_contract.py"


class Adr009UnifyRunStagePlayPhase1Test(unittest.TestCase):
    def test_adr_status_phase1(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("[x] `run` override flags + policy wiring (Phase 1)", text)

    def test_adr_index_phase1(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("009-unify-run-stage-play.md", text)
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase1(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("Phase 1", text)
        self.assertIn("apply_run_cli_overrides", text)

    def test_clusterctl_doc_run_flags(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("--extra-vars", text)
        self.assertIn("merge_e", text)
        # run section documents -e
        self.assertIn("./cluster run --phases provision -e provision_mode=destroy", text)

    def test_main_wires_apply_run_cli_overrides(self) -> None:
        text = MAIN.read_text(encoding="utf-8")
        self.assertIn("from clusterctl.run_overrides import apply_run_cli_overrides", text)
        self.assertIn("resolve_run_limit", text)
        self.assertNotIn("honor_limit_env", text)
        self.assertIn("_add_run_override_flags", text)
        self.assertIn("apply_run_cli_overrides(", text)

    def test_policy_exports_apply(self) -> None:
        text = POLICY.read_text(encoding="utf-8")
        self.assertIn("def apply_run_cli_overrides", text)
        self.assertIn("def resolve_run_limit", text)
        self.assertIn("MERGE_EXTRA", text)

    def test_contract_covers_apply(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        for needle in (
            "test_merge_e_appends_without_collapse_multi_phase",
            "test_collapse_single_phase_with_tags_and_e",
            "test_multi_phase_tags_errors",
            "ResolveRunLimitTest",
            "test_env_limit_collapses_single_phase",
        ):
            self.assertIn(needle, text, needle)

    def test_argparse_run_accepts_override_flags(self) -> None:
        parser = main_mod._build_parser()
        args = parser.parse_args(
            [
                "run",
                "--phases",
                "provision",
                "--tags",
                "10_tf_apply",
                "--limit",
                "localhost",
                "-e",
                "provision_mode=destroy",
                "-e",
                "foo=bar",
                "--root-ssh",
                "--git-ssh",
                "--dry-run",
            ]
        )
        self.assertEqual(args.command, "run")
        self.assertEqual(args.phases_selector, "provision")
        self.assertEqual(args.tags, "10_tf_apply")
        self.assertEqual(args.limit, "localhost")
        self.assertEqual(args.extra_vars, ["provision_mode=destroy", "foo=bar"])
        self.assertTrue(args.root_ssh)
        self.assertTrue(args.git_ssh)
        self.assertTrue(args.dry_run)

    def test_argparse_plan_has_no_extra_vars(self) -> None:
        parser = main_mod._build_parser()
        args = parser.parse_args(["plan", "--phases", "init"])
        self.assertEqual(args.command, "plan")
        self.assertIsNone(getattr(args, "extra_vars", None))
        self.assertIsNone(getattr(args, "tags", None))

    def test_argparse_run_rejects_unknown_flag_still_ok(self) -> None:
        parser = main_mod._build_parser()
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            with self.assertRaises(SystemExit):
                parser.parse_args(["run", "--from", "init"])


if __name__ == "__main__":
    unittest.main()
