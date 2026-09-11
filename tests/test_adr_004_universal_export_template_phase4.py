"""Phase 4 gate: ADR 004 — retired k8s-only exporter deleted; grep-gate."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "004-universal-export-template.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
UNIVERSAL = ROOT / "clusterctl" / "tools" / "export_template.py"
RETIRED_MODULE = ROOT / "clusterctl" / "tools" / "export_k8s_full_template.py"
RETIRED_TESTS = ROOT / "tests" / "test_export_k8s_full_template.py"

_RETIRED = "export_k8s_full_template"

# Retired name may appear only in CHANGELOG history and ADR/phase-gate files
# that assert absence or document the migration.


def _is_allowed(rel: str) -> bool:
    if rel == "CHANGELOG.md":
        return True
    if rel == "docs/adr/004-universal-export-template.md":
        return True
    if rel == "tests/test_local_labs_contract.py":
        return True
    return rel.startswith("tests/test_adr_004_universal_export_template_")


class Adr004UniversalExportTemplatePhase4Test(unittest.TestCase):
    def test_adr_status_phase4_complete(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 4 complete", text)
        self.assertIn("Status:** Accepted", text)
        self.assertIn("[x] Old k8s-only exporter removed", text)
        self.assertIn("[x] Tests no longer import the retired module as SoT API", text)
        self.assertIn("[x] `--clusters-root` alias removed", text)
        self.assertIn("shim deleted", text.lower())

    def test_adr_index_phase4(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase 4)", text)

    def test_shim_and_legacy_tests_deleted(self) -> None:
        self.assertFalse(RETIRED_MODULE.exists(), RETIRED_MODULE)
        self.assertFalse(RETIRED_TESTS.exists(), RETIRED_TESTS)

    def test_export_template_has_no_clusters_root_flag(self) -> None:
        text = UNIVERSAL.read_text(encoding="utf-8")
        self.assertNotIn("--clusters-root", text)
        self.assertNotIn('"--clusters-root"', text)
        self.assertNotIn("args.clusters_root", text)
        self.assertIn("--source-root", text)
        self.assertIn("--target-root", text)

    def test_changelog_records_phase4(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 004", text)
        self.assertIn("Phase 4", text)
        self.assertIn(_RETIRED, text)

    def test_grep_retired_name_allowlist(self) -> None:
        """Retired module name only in CHANGELOG / ADR / phase gates."""
        proc = subprocess.run(
            [
                "git",
                "grep",
                "-n",
                "-I",
                "--full-name",
                _RETIRED,
                "--",
                ".",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        # 0 = matches, 1 = no matches
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        offenders: list[str] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            rel = line.split(":", 1)[0]
            if not _is_allowed(rel):
                offenders.append(line)
        self.assertEqual(
            offenders,
            [],
            "retired name leaked outside allowlist:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
