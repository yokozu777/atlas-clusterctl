"""Phase 8 CI gate — offline checks before Jenkins repos sync / deploy."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clusterctl.legacy_guard import find_legacy_artifacts
from clusterctl.tools.check_no_legacy_repos import find_legacy_repo_references
from clusterctl.tools.generate_org_cluster_fixture import main as validate_org_fixture
from clusterctl.validate import validate_repo


def _run_unittest() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=ROOT,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def _run_legacy_reference_scan() -> None:
    hits = find_legacy_repo_references(ROOT)
    if hits:
        for rel, line_no, line in hits:
            print(f"{rel}:{line_no}:{line}")
        print("FAIL: legacy repo references found (use atlas-* family only)", file=sys.stderr)
        raise SystemExit(1)
    print("OK: zero legacy repo references in atlas-clusterctl SoT paths")


def _run_legacy_artifacts_scan() -> None:
    artifacts = find_legacy_artifacts(ROOT)
    if artifacts:
        for artifact in artifacts:
            print(f"{artifact.path.relative_to(ROOT)}: {artifact.hint}", file=sys.stderr)
        print("FAIL: legacy artifacts present in repository layout", file=sys.stderr)
        raise SystemExit(1)
    print("OK: zero legacy artifacts at repo root / workspace/repos")


def _run_org_fixture() -> None:
    code = validate_org_fixture()
    if code != 0:
        raise SystemExit(code)


def _run_validate_repo() -> None:
    report = validate_repo(ROOT)
    errors = [issue for issue in report.issues if issue.is_error]
    if errors:
        for issue in errors:
            print(f"ERROR {issue.code}: {issue.message}", file=sys.stderr)
            if issue.hint:
                print(f"  hint: {issue.hint}", file=sys.stderr)
        raise SystemExit(1)
    print("OK: validate --repo (zero errors)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="atlas-clusterctl offline CI preflight gate")
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="skip unittest discover (faster local iteration)",
    )
    args = parser.parse_args(argv)

    if not args.skip_tests:
        print("== unittest discover ==")
        _run_unittest()

    print("== legacy repo reference scan ==")
    _run_legacy_reference_scan()

    print("== legacy artifact scan ==")
    _run_legacy_artifacts_scan()

    print("== org baseline fixture ==")
    _run_org_fixture()

    print("== validate --repo ==")
    _run_validate_repo()

    print("CI preflight: all gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
