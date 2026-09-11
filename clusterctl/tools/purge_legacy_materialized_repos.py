"""Remove retired playbook repo materialization under workspace/<id>/repos/."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clusterctl.legacy_guard import RETIRED_PLAYBOOK_REPO_DIRS


def _repo_root() -> Path:
    return ROOT


def find_retired_workspace_materialized_paths(repo_root: Path | None = None) -> list[Path]:
    base = (repo_root or _repo_root()).resolve()
    workspace = base / "workspace"
    if not workspace.is_dir():
        return []

    found: list[Path] = []
    retired_names = {name for name, _ in RETIRED_PLAYBOOK_REPO_DIRS if name != "TBD"}
    for repos_dir in sorted(workspace.glob("**/repos")):
        if not repos_dir.is_dir():
            continue
        for name in sorted(retired_names):
            path = repos_dir / name
            if path.exists():
                found.append(path)
    return found


def purge_retired_workspace_materialized(
    repo_root: Path | None = None,
    *,
    dry_run: bool = False,
) -> list[Path]:
    removed: list[Path] = []
    for path in find_retired_workspace_materialized_paths(repo_root):
        if dry_run:
            print(f"would remove: {path}")
        else:
            shutil.rmtree(path)
            print(f"removed: {path}")
        removed.append(path)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Purge retired playbook repos from workspace/<id>/repos/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print paths only, do not delete",
    )
    args = parser.parse_args(argv)

    removed = purge_retired_workspace_materialized(dry_run=args.dry_run)
    if not removed:
        print("OK: no retired materialized playbook repos under workspace/*/repos/")
        return 0
    verb = "would remove" if args.dry_run else "removed"
    print(f"OK: {verb} {len(removed)} retired path(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
