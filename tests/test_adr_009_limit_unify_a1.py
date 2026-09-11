"""Post–ADR 009 cleanup A1: env ``LIMIT`` unified for ``run`` (was play-only)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import clusterctl.__main__ as main_mod
from clusterctl.run_overrides import resolve_run_limit

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "clusterctl" / "__main__.py"
POLICY = ROOT / "clusterctl" / "run_overrides.py"
PHASE_RUNNER = ROOT / "clusterctl" / "phase_runner.py"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
CHANGELOG = ROOT / "CHANGELOG.md"


class Adr009LimitUnifyA1Test(unittest.TestCase):
    def test_honor_limit_env_removed(self) -> None:
        text = MAIN.read_text(encoding="utf-8")
        self.assertNotIn("honor_limit_env", text)
        self.assertIn("resolve_run_limit", text)

    def test_resolve_run_limit_exported(self) -> None:
        text = POLICY.read_text(encoding="utf-8")
        self.assertIn("def resolve_run_limit", text)

    def test_phase_runner_prefers_invocation_limit(self) -> None:
        text = PHASE_RUNNER.read_text(encoding="utf-8")
        self.assertIn("invocation.limit", text)
        # Planned limit before env (CLI baked into invocation wins).
        self.assertRegex(
            text,
            r"\(invocation\.limit or \"\"\)\.strip\(\).*LIMIT",
        )

    def test_docs_and_changelog(self) -> None:
        doc = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("`LIMIT`", doc)
        self.assertIn("--limit", doc)
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("LIMIT", adr)
        self.assertIn("resolve_run_limit", adr)
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("LIMIT", changelog)
        self.assertIn("post-cleanup A1", changelog)

    def test_run_and_play_resolve_limit_identically(self) -> None:
        """Shared helper: no verb-specific LIMIT path remains."""
        env = {"LIMIT": "infra_platform"}
        self.assertEqual(resolve_run_limit(None, env=env), "infra_platform")
        self.assertEqual(resolve_run_limit("cli_hosts", env=env), "cli_hosts")

    def test_os_environ_limit_used_when_no_cli(self) -> None:
        saved = os.environ.get("LIMIT")
        try:
            os.environ["LIMIT"] = "from_environ"
            self.assertEqual(resolve_run_limit(None), "from_environ")
            self.assertEqual(resolve_run_limit("  "), "from_environ")
        finally:
            if saved is None:
                os.environ.pop("LIMIT", None)
            else:
                os.environ["LIMIT"] = saved

    def test_cmd_run_execute_signature_has_no_honor_flag(self) -> None:
        import inspect

        params = inspect.signature(main_mod._cmd_run_execute).parameters
        self.assertNotIn("honor_limit_env", params)


if __name__ == "__main__":
    unittest.main()
