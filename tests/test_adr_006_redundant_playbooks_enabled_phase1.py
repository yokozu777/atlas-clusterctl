"""Phase 1 gate: ADR 006 — playbooks_enabled hints/helpers aligned (no mandatory true)."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "006-redundant-playbooks-enabled.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
PLAYBOOKS_CONFIG = ROOT / "clusterctl" / "playbooks_config.py"

_SET_TRUE_NEEDLE = "set playbooks_enabled: true"
_ENGINE_HINT_PATHS = (
    "clusterctl/validate.py",
    "clusterctl/playbooks_sync.py",
    "clusterctl/playbooks_repos.py",
    "clusterctl/role_repos.py",
    "clusterctl/docker_validate.py",
    "clusterctl/repo_conventions.py",
    "clusterctl/playbooks_config.py",
)


def _is_history_allowlisted(rel: str) -> bool:
    if rel == "CHANGELOG.md":
        return True
    if rel.startswith("docs/adr/"):
        return True
    if rel.startswith("tests/test_adr_006_"):
        return True
    return False


class Adr006RedundantPlaybooksEnabledPhase1Test(unittest.TestCase):
    def test_adr_status_phase1(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn("[x] User-facing errors do not require setting `true`", text)
        self.assertIn(
            "[x] `playbooks_feature_enabled` omit→infer aligned (Phase 1)",
            text,
        )
        self.assertIn("no yaml deletion", text.lower())  # historical Phase 0/1 plan text
        # Phase 2 checklist may be checked; gate only cares Phase 1 items stay.
        self.assertIn(
            "User-facing errors do not require setting `true`",
            text,
        )

    def test_adr_index_phase1(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase1(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 006", text)
        self.assertIn("Phase 1", text)
        self.assertIn("playbooks_feature_enabled", text)

    def test_playbooks_feature_enabled_infers_in_source(self) -> None:
        text = PLAYBOOKS_CONFIG.read_text(encoding="utf-8")
        self.assertIn("def playbooks_feature_enabled", text)
        self.assertIn("infer", text.lower())
        self.assertIn('raw.get("playbooks")', text)
        # Must not hard-return False on omit without checking playbooks.
        self.assertNotIn(
            "if explicit is not None:\n        return explicit\n    return False",
            text.replace("\r\n", "\n"),
        )

    def test_engine_has_no_set_playbooks_enabled_true(self) -> None:
        offenders: list[str] = []
        for rel in _ENGINE_HINT_PATHS:
            path = ROOT / rel
            text = path.read_text(encoding="utf-8")
            if _SET_TRUE_NEEDLE in text:
                offenders.append(rel)
        self.assertEqual(
            offenders,
            [],
            "engine still tells operators to set playbooks_enabled: true:\n"
            + "\n".join(offenders),
        )

    def test_grep_set_true_allowlist(self) -> None:
        """``set playbooks_enabled: true`` only in history / ADR / phase gates."""
        proc = subprocess.run(
            [
                "git",
                "grep",
                "-n",
                "-I",
                "--full-name",
                "-F",
                _SET_TRUE_NEEDLE,
                "--",
                ".",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        offenders: list[str] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            rel = line.split(":", 1)[0]
            if not _is_history_allowlisted(rel):
                offenders.append(line)
        self.assertEqual(
            offenders,
            [],
            "set playbooks_enabled: true leaked outside allowlist:\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
