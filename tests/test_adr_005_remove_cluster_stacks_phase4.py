"""Phase 4 gate: ADR 005 — stacks.py deleted; stacks: hard-rejected; grep-gate.

Phase D extends the grep-gate so legacy validate codes and retired stack APIs
cannot re-enter ``clusterctl/`` (hard ban) or the wider tree outside history
allowlists (CHANGELOG + ADR + phase gates + intentional negative tests).
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "005-remove-cluster-stacks.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"
CHANGELOG = ROOT / "CHANGELOG.md"
STACKS_MODULE = ROOT / "clusterctl" / "stacks.py"
PHASE_INTENT = ROOT / "clusterctl" / "phase_intent.py"
INTENT_TESTS = ROOT / "tests" / "test_phase_intent.py"
LEGACY_STACKS_TESTS = ROOT / "tests" / "test_stacks_g5.py"

# YAML key / retired module API may appear only in history + ADR phase gates.
_STACKS_MODULE_IMPORT = "clusterctl.stacks"
_SKIP_PHASE_REFS = "skip_phase_refs"
_STACKS_LEGACY = "stacks_legacy"

# Legacy validate issue codes (renamed in post-Phase-4 cleanup B).
_LEGACY_VALIDATE_CODES = (
    "stacks_k8s_no_inventory",
    "stacks_infra_no_inventory",
    "stacks_postgresql_no_inventory",
    "stacks_mysql_no_inventory",
    "stacks_redis_no_inventory",
    "stacks_kafka_no_inventory",
    "inventory_k8s_stack_disabled",
    "inventory_infra_stack_disabled",
    "inventory_postgresql_stack_disabled",
    "inventory_redis_stack_disabled",
    "inventory_kafka_stack_disabled",
    "data_stack_no_inventory",
)

# Retired engine symbols (must not return to runtime).
_RETIRED_STACK_APIS = (
    "apply_stacks_filter",
    "resolve_stack_flags",
    "StackFlags",
    "load_phase_intent",
    "stacks_skipped",
)

# Tombstone / current contract — must remain (not banned).
_KEPT_CONTRACT = (
    "stacks_removed",
    "StacksRemovedError",
    "provision_stack",
)


def _is_history_allowlisted(rel: str) -> bool:
    if rel == "CHANGELOG.md":
        return True
    if rel == "docs/adr/005-remove-cluster-stacks.md":
        return True
    if rel.startswith("tests/test_adr_005_remove_cluster_stacks_"):
        return True
    # Intentional negative tests that assert rejection / absence.
    if rel in ("tests/test_phase_intent.py", "tests/test_phase_plan.py"):
        return True
    return False


def _git_grep_lines(needle: str, *paths: str) -> list[str]:
    cmd = [
        "git",
        "grep",
        "-n",
        "-I",
        "--full-name",
        "-F",
        needle,
        "--",
        *paths,
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in (0, 1):
        raise AssertionError(f"git grep failed for {needle!r}: {proc.stderr}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _offenders_outside_allowlist(needle: str) -> list[str]:
    offenders: list[str] = []
    for line in _git_grep_lines(needle, "."):
        rel = line.split(":", 1)[0]
        if not _is_history_allowlisted(rel):
            offenders.append(line)
    return offenders


def _clusterctl_py_files() -> list[Path]:
    return sorted((ROOT / "clusterctl").rglob("*.py"))


class Adr005RemoveClusterStacksPhase4Test(unittest.TestCase):
    def test_adr_status_phase4_complete(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase 4", text)
        self.assertIn("Phase 4 complete", text)
        self.assertIn("Current runtime (Phase 4", text)
        self.assertIn("[x] `clusterctl/stacks.py` removed / non-SoT", text)
        self.assertIn("[x] Present `stacks:` → hard error", text)
        self.assertIn("Grep-gate: retired YAML key / skip API", text)
        self.assertIn("legacy validate codes only in", text)
        # Phase C: docs match runtime (no soft-delete / live resolve_stack_flags).
        self.assertIn("Post-Phase-4 cleanup", text)
        self.assertIn("phase_intent.py", text)
        self.assertIn("PhaseIntent", text)
        self.assertNotIn("resolve_stack_flags", text)
        self.assertNotIn("or reduced to a migration helper", text)
        self.assertNotIn("Validate must be retargeted", text)
        self.assertNotIn("StackFlags", text)
        # Phase D: grep-gate strengthened and marked done.
        self.assertIn("| D |", text)
        self.assertIn("strengthened grep-gate", text.lower())
        self.assertNotIn("(follow-up) strengthen grep-gate", text)
        # Phase E: offline full verification recorded.
        self.assertIn("| E |", text)
        self.assertIn("run_ci.sh", text)
        self.assertIn("no live labs", text.lower())

    def test_adr_index_phase4(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase 4)", text)

    def test_stacks_module_deleted_intent_module_present(self) -> None:
        self.assertFalse(STACKS_MODULE.exists(), STACKS_MODULE)
        self.assertFalse(LEGACY_STACKS_TESTS.exists(), LEGACY_STACKS_TESTS)
        self.assertTrue(PHASE_INTENT.is_file(), PHASE_INTENT)
        self.assertTrue(INTENT_TESTS.is_file(), INTENT_TESTS)
        intent = PHASE_INTENT.read_text(encoding="utf-8")
        self.assertIn("def infer_phase_intent", intent)
        self.assertIn("PHASE_INTENT_REFS", intent)
        self.assertIn("class PhaseIntent", intent)

    def test_legacy_stacks_validate_codes_removed(self) -> None:
        validate = (ROOT / "clusterctl" / "validate.py").read_text(encoding="utf-8")
        for needle in _LEGACY_VALIDATE_CODES:
            self.assertNotIn(needle, validate, needle)
        for needle in (
            "phase_intent_k8s_no_inventory",
            "phase_intent_postgresql_no_inventory",
            "inventory_k8s_phases_omitted",
            "inventory_postgresql_phases_omitted",
            "provision_stack_no_inventory",
        ):
            self.assertIn(needle, validate, needle)
        intent = PHASE_INTENT.read_text(encoding="utf-8")
        self.assertNotIn("def load_phase_intent", intent)

    def test_stacks_removed_error_is_typed_contract(self) -> None:
        """Post-Phase-4: live reject uses StacksRemovedError / stacks_removed."""
        from clusterctl.exceptions import StacksRemovedError

        self.assertEqual(StacksRemovedError.code, "stacks_removed")
        exc_text = (ROOT / "clusterctl" / "exceptions.py").read_text(encoding="utf-8")
        self.assertIn("class StacksRemovedError", exc_text)
        validate = (ROOT / "clusterctl" / "validate.py").read_text(encoding="utf-8")
        self.assertIn("report_cluster_load_failure", validate)
        self.assertIn("StacksRemovedError", validate)
        intent_tests = INTENT_TESTS.read_text(encoding="utf-8")
        self.assertIn("stacks_removed", intent_tests)
        self.assertIn("StacksRemovedError", intent_tests)
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("StacksRemovedError", adr)
        self.assertIn("`stacks_removed`", adr)

    def test_schema_doc_phase4(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("Phase 4", text)
        self.assertIn("hard-reject", text.lower())
        self.assertIn("stacks_removed", text)
        self.assertIn("adr/005-remove-cluster-stacks.md", text)
        self.assertNotIn("## `stacks`", text)

    def test_changelog_phase4(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 005", text)
        self.assertIn("Phase 4", text)
        self.assertIn("stacks.py", text)
        self.assertIn("(D) grep-gate strengthened", text)
        self.assertIn("hard-banned under", text)
        self.assertIn("(E) offline full verification", text)
        self.assertIn("run_ci.sh", text)

    def test_clusterctl_hard_ban_legacy_symbols(self) -> None:
        """Phase D: no legacy codes / retired APIs anywhere under clusterctl/."""
        banned = (
            *_LEGACY_VALIDATE_CODES,
            *_RETIRED_STACK_APIS,
            _STACKS_MODULE_IMPORT,
            _SKIP_PHASE_REFS,
            _STACKS_LEGACY,
        )
        hits: list[str] = []
        for path in _clusterctl_py_files():
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(ROOT).as_posix()
            for needle in banned:
                if needle in text:
                    hits.append(f"{rel}: contains {needle!r}")
        self.assertEqual(
            hits,
            [],
            "legacy stack symbols leaked into clusterctl/:\n" + "\n".join(hits),
        )
        # Kept contract must still be present in runtime.
        joined = "\n".join(p.read_text(encoding="utf-8") for p in _clusterctl_py_files())
        for needle in _KEPT_CONTRACT:
            self.assertIn(needle, joined, needle)

    def test_grep_clusterctl_stacks_import_allowlist(self) -> None:
        offenders = _offenders_outside_allowlist(_STACKS_MODULE_IMPORT)
        self.assertEqual(
            offenders,
            [],
            "clusterctl.stacks leaked outside allowlist:\n" + "\n".join(offenders),
        )

    def test_grep_skip_phase_refs_allowlist(self) -> None:
        offenders = _offenders_outside_allowlist(_SKIP_PHASE_REFS)
        self.assertEqual(
            offenders,
            [],
            "skip_phase_refs leaked outside allowlist:\n" + "\n".join(offenders),
        )

    def test_grep_stacks_legacy_allowlist(self) -> None:
        offenders = _offenders_outside_allowlist(_STACKS_LEGACY)
        self.assertEqual(
            offenders,
            [],
            "stacks_legacy leaked outside allowlist:\n" + "\n".join(offenders),
        )

    def test_grep_legacy_validate_codes_allowlist(self) -> None:
        """Phase D: renamed validate codes only in history allowlist."""
        all_offenders: list[str] = []
        for needle in _LEGACY_VALIDATE_CODES:
            for line in _offenders_outside_allowlist(needle):
                all_offenders.append(line)
        self.assertEqual(
            all_offenders,
            [],
            "legacy validate codes leaked outside allowlist:\n"
            + "\n".join(all_offenders),
        )

    def test_grep_retired_stack_apis_allowlist(self) -> None:
        """Phase D: retired stack filter / intent APIs only in history allowlist."""
        all_offenders: list[str] = []
        for needle in _RETIRED_STACK_APIS:
            for line in _offenders_outside_allowlist(needle):
                all_offenders.append(line)
        self.assertEqual(
            all_offenders,
            [],
            "retired stack APIs leaked outside allowlist:\n"
            + "\n".join(all_offenders),
        )

    def test_grep_yaml_stacks_key_in_clusters(self) -> None:
        """No live ``stacks:`` key under clusters/."""
        proc = subprocess.run(
            [
                "git",
                "grep",
                "-n",
                "-I",
                "--full-name",
                "-E",
                "^stacks:",
                "--",
                "clusters",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)


if __name__ == "__main__":
    unittest.main()
