"""List deployable cluster IDs under an inventory ``clusters/`` root (Jenkins seed)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clusterctl.cluster_layout import list_deployable_cluster_ids


def collect_deployable_cluster_ids(
    clusters_root: Path | str,
    *,
    prefer: str = "",
) -> list[str]:
    """Return deployable ``env/name`` ids under *clusters_root*.

    Uses :func:`clusterctl.cluster_layout.list_deployable_cluster_ids` (same notion
    as ``./cluster list`` without ``[policy]`` / org baseline).

    When *prefer* is a non-empty id present in the scan result, it is moved to
    index 0 (stable UI default for Jenkins ``choice``). Unknown prefer is ignored.

    Raises:
        FileNotFoundError: *clusters_root* is missing or not a directory.
    """
    root = Path(clusters_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"clusters root not a directory: {root}")

    ids = list(list_deployable_cluster_ids(root))
    prefer_id = (prefer or "").strip()
    if prefer_id and prefer_id in ids:
        return [prefer_id] + [i for i in ids if i != prefer_id]
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print deployable cluster IDs (env/name) under a clusters/ tree. "
            "Used by examples/internal/seed (Jenkins seed job). "
            "Excludes org/env policy dirs — same notion as ./cluster list without [policy]."
        )
    )
    parser.add_argument(
        "--clusters-root",
        type=Path,
        required=True,
        help="Path to inventory clusters/ directory (contains env/name/cluster.yaml leaves)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON array instead of one id per line",
    )
    parser.add_argument(
        "--prefer",
        default="",
        help="If this id is in the list, print it first (stable UI default)",
    )
    args = parser.parse_args(argv)

    try:
        ids = collect_deployable_cluster_ids(
            args.clusters_root,
            prefer=args.prefer,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not ids:
        root = Path(args.clusters_root).expanduser().resolve()
        print(
            f"error: no deployable cluster IDs under {root}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps(ids, ensure_ascii=False))
    else:
        for cluster_id in ids:
            print(cluster_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
