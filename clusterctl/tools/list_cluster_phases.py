"""List ordered phase names for a leaf under an inventory ``clusters/`` root.

Used by Jenkins seed path B (offline ``CLUSTER_ID → phases`` reference map /
``cluster-phases.json``).

**Map / helper SoT:** YAML ``phases:`` catalog after cascade merge only.
Does **not** apply inventory ``when:`` filters (or other plan-time skips).
Jenkins seed samples pass inventory ``clusters/`` only (no
``--product-clusters-root``).

**Deploy empty ``PHASES`` (separate):** ``./cluster plan|run`` **without**
``--phases`` → **plan SoT** (effective stages). That list may be a **subset**
of this map when ``when:`` (or runtime) drops phases. Do not treat the map as
a promise of what an empty-``PHASES`` deploy will execute.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clusterctl.cluster_config_loader import load_merged_cluster_config_v2
from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import stage_name_for_phase_ref
from clusterctl.tools.list_deployable_clusters import collect_deployable_cluster_ids


class PhasesUnavailableError(LookupError):
    """Leaf has no usable ``phases:`` catalog after cascade merge."""


def collect_phases_for_cluster(
    clusters_root: Path | str,
    cluster_id: str,
    *,
    short_names: bool = True,
    product_clusters_root: Path | str | None = None,
) -> list[str]:
    """Return ordered phase names (or refs) for *cluster_id*.

    Uses :func:`load_merged_cluster_config_v2` then ``config.phases.phases``.
    Short names match the deploy ``PHASES`` selector / CLI (alias or entry id).
    YAML catalog only — no inventory ``when:`` (see module docstring).

    Raises:
        FileNotFoundError: *clusters_root* missing or not a directory.
        ClusterctlError: cascade / config load failure.
        PhasesUnavailableError: merged config has no non-empty ``phases:``.
    """
    root = Path(clusters_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"clusters root not a directory: {root}")

    cid = (cluster_id or "").strip()
    if not cid:
        raise ValueError("cluster_id is required")

    product: Path | None = None
    if product_clusters_root is not None:
        product = Path(product_clusters_root).expanduser().resolve()

    config = load_merged_cluster_config_v2(
        root,
        cid,
        product_clusters_root=product,
    )
    if config.phases is None or not config.phases.phases:
        raise PhasesUnavailableError(
            f"no phases: catalog for {cid!r} under {root}"
        )

    refs = list(config.phases.phases)
    if not short_names:
        return refs
    aliases = config.phases.phase_aliases
    return [stage_name_for_phase_ref(ref, aliases) for ref in refs]


def collect_phases_map(
    clusters_root: Path | str,
    *,
    short_names: bool = True,
    product_clusters_root: Path | str | None = None,
    cluster_ids: list[str] | None = None,
) -> dict[str, list[str]]:
    """Map deployable ids → phase lists; omit leaves without ``phases:``.

    Default *cluster_ids* = :func:`collect_deployable_cluster_ids`. Leaves that
    raise :class:`PhasesUnavailableError` are skipped (still deployable layout
    for ``CLUSTER_ID`` choice — e.g. ``hosts``-only). Other errors propagate.
    """
    root = Path(clusters_root).expanduser().resolve()
    ids = (
        list(cluster_ids)
        if cluster_ids is not None
        else collect_deployable_cluster_ids(root)
    )
    out: dict[str, list[str]] = {}
    for cid in ids:
        try:
            out[cid] = collect_phases_for_cluster(
                root,
                cid,
                short_names=short_names,
                product_clusters_root=product_clusters_root,
            )
        except PhasesUnavailableError:
            continue
    return out


def ids_missing_from_phases_map(
    cluster_ids: list[str],
    phases_map: dict[str, list[str]],
) -> list[str]:
    """Return *cluster_ids* (order preserved) absent from *phases_map* keys.

    Used by seed to warn when ``CLUSTER_ID`` choices include leaves without
    ``phases:`` (map is catalog-only; Job DSL still seeds those ids).
    """
    mapped = set(phases_map)
    return [cid for cid in cluster_ids if cid not in mapped]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print ordered phase names for a leaf (or JSON map for all deployable "
            "leaves with phases:). Jenkins seed path B reference helper. "
            "Output = YAML phases: catalog only (no inventory when:). "
            "Deploy empty PHASES is separate: plan/run without --phases (plan SoT; "
            "may omit catalog entries skipped at plan time)."
        )
    )
    parser.add_argument(
        "--clusters-root",
        type=Path,
        required=True,
        help="Path to inventory clusters/ directory",
    )
    parser.add_argument(
        "--cluster-id",
        default="",
        help="Single leaf env/name (required unless --all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Emit map for all deployable leaves that have phases: (JSON object)",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help=(
            "With --all only: print {} and exit 0 when no leaf has phases: "
            "(seed artifact). Error if used without --all."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON array (single id) or object (--all); default lines for single id",
    )
    parser.add_argument(
        "--refs",
        action="store_true",
        help="Print phase_ref (repo/entry) instead of short PHASES selector names",
    )
    parser.add_argument(
        "--product-clusters-root",
        type=Path,
        default=None,
        help=(
            "Optional product clusters/ for org-baseline cascade fallback "
            "(offline/manual). Seed Pipeline samples do not pass this — "
            "inventory clusters/ only."
        ),
    )
    args = parser.parse_args(argv)
    short_names = not args.refs

    if args.allow_empty and not args.all:
        print(
            "error: --allow-empty requires --all",
            file=sys.stderr,
        )
        return 2

    try:
        if args.all:
            mapping = collect_phases_map(
                args.clusters_root,
                short_names=short_names,
                product_clusters_root=args.product_clusters_root,
            )
            if not mapping:
                root = Path(args.clusters_root).expanduser().resolve()
                if args.allow_empty:
                    print("{}")
                    return 0
                print(
                    f"error: no deployable leaves with phases: under {root}",
                    file=sys.stderr,
                )
                return 1
            # --all always JSON object (lines would be ambiguous).
            print(json.dumps(mapping, ensure_ascii=False, sort_keys=True))
            return 0

        cid = (args.cluster_id or "").strip()
        if not cid:
            print("error: --cluster-id is required (or pass --all)", file=sys.stderr)
            return 2

        phases = collect_phases_for_cluster(
            args.clusters_root,
            cid,
            short_names=short_names,
            product_clusters_root=args.product_clusters_root,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except PhasesUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ClusterctlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # YAML parse / unexpected load failures — no traceback in seed logs.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(phases, ensure_ascii=False))
    else:
        for name in phases:
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
