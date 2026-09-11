"""CI gate: no retired playbook repo names in atlas-clusterctl SoT paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN = re.compile(
    r"init_roles|atlas-phase-0|atlas-phase-1|k8s-platform|k8s_cluster\.git"
)

SCAN_ROOTS = (
    "clusters",
    "clusterctl",
    "tests",
    "docs",
)

SCAN_FILES = (
    "README.md",
    "Jenkinsfile",
    "playbooks/README.md",
    "profiles/README.md",
)

EXEMPT = frozenset(
    {
        "clusterctl/legacy_guard.py",
        "clusterctl/tools/check_no_legacy_repos.py",
    }
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def find_legacy_repo_references(root: Path | None = None) -> list[tuple[str, int, str]]:
    base = (root or _repo_root()).resolve()
    hits: list[tuple[str, int, str]] = []

    def scan_file(path: Path) -> None:
        rel = path.relative_to(base).as_posix()
        if rel in EXEMPT:
            return
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        for line_no, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN.search(line):
                hits.append((rel, line_no, line.strip()))

    for name in SCAN_ROOTS:
        root_dir = base / name
        if not root_dir.is_dir():
            continue
        for path in sorted(root_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix in {".py", ".yml", ".yaml", ".md", ".sh", ""} or path.name == "Jenkinsfile":
                scan_file(path)

    for name in SCAN_FILES:
        path = base / name
        if path.is_file():
            scan_file(path)

    return hits


def main(argv: list[str] | None = None) -> int:
    _ = argv
    hits = find_legacy_repo_references()
    if hits:
        for rel, line_no, line in hits:
            print(f"{rel}:{line_no}:{line}")
        print("FAIL: legacy repo references found (use atlas-* family only)", file=sys.stderr)
        return 1
    print("OK: zero legacy repo references in atlas-clusterctl SoT paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
