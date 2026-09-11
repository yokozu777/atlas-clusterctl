"""List ansible ``--limit`` catalog names for a leaf under inventory ``clusters/``.

Used by Jenkins seed LIMIT follow-up (ADR 011): offline ``CLUSTER_ID →`` checkbox
catalog.

**Map / helper SoT:** YAML Ansible inventory file ``hosts`` under the leaf.

* **Flat** (CLI default): **groups** (sorted) then **hosts** (sorted). Host keys
  that collide with a group name appear only under groups.
* **UI** (``--ui`` / seed): hierarchical Active Choices map — for each group with
  direct hosts, group value then nested host labels; host label may include
  inventory ``hostname:`` as ``(hostname: dns)``. Submitted values remain group
  names / host **keys** (not DNS).
* Inventory-only — no product baseline, no live ``ansible-inventory``.

**Deploy empty ``LIMIT`` (separate):** Run omits ``--limit``. Non-empty values
are ansible host patterns (ADR 009 single-phase rule unchanged).

Leaves without a usable YAML ``hosts`` file (missing, INI-only, empty catalog)
raise :class:`LimitsUnavailableError` and are omitted from ``--all`` maps.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clusterctl.cluster_layout import discover_config_dir
from clusterctl.exceptions import ClusterctlError
from clusterctl.inventory import (
    extract_inventory_groups,
    extract_inventory_hostnames,
    extract_inventory_limit_sections,
)
from clusterctl.paths import inventory_path
from clusterctl.tools.list_deployable_clusters import collect_deployable_cluster_ids

# Visual hierarchy for Active Choices checkbox labels (values stay clean keys).
_GROUP_LABEL_PREFIX = "▸ "
_HOST_LABEL_PREFIX = "   └ "


class LimitsUnavailableError(LookupError):
    """Leaf has no usable YAML inventory catalog for LIMIT checkboxes."""


def _leaf_inventory_path(clusters_root: Path, cluster_id: str) -> Path:
    """Resolve ``clusters/<env>/<name>/hosts`` for *cluster_id*."""
    try:
        config_dir = discover_config_dir(clusters_root, cluster_id)
    except FileNotFoundError as exc:
        raise LimitsUnavailableError(
            f"cluster leaf not found for {cluster_id!r} under {clusters_root}"
        ) from exc
    return inventory_path(config_dir)


def format_host_limit_label(host_key: str, hostname_var: str | None = None) -> str:
    """Checkbox label for a host key; optional ``hostname:`` DNS in parentheses."""
    base = f"{_HOST_LABEL_PREFIX}{host_key}"
    if hostname_var:
        return f"{base} (hostname: {hostname_var})"
    return base


def format_group_limit_label(group_name: str) -> str:
    """Checkbox label for an inventory group."""
    return f"{_GROUP_LABEL_PREFIX}{group_name}"


def collect_limits_parts_for_cluster(
    clusters_root: Path | str,
    cluster_id: str,
) -> tuple[list[str], list[str]]:
    """Return ``(groups, hosts)`` for *cluster_id* (both sorted).

    Hosts that also appear as group names are dropped from the hosts list
    (flat checkbox catalog lists them once, under groups).

    Raises:
        FileNotFoundError: *clusters_root* missing or not a directory.
        ValueError: blank *cluster_id*.
        LimitsUnavailableError: missing / unusable / empty YAML inventory.
    """
    root = Path(clusters_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"clusters root not a directory: {root}")

    cid = (cluster_id or "").strip()
    if not cid:
        raise ValueError("cluster_id is required")

    inv = _leaf_inventory_path(root, cid)
    if not inv.is_file():
        raise LimitsUnavailableError(
            f"no hosts inventory for {cid!r} under {root}"
        )

    try:
        groups = sorted(extract_inventory_groups(inv))
        hosts = sorted(extract_inventory_hostnames(inv))
    except ClusterctlError as exc:
        raise LimitsUnavailableError(
            f"unusable inventory for {cid!r}: {exc}"
        ) from exc

    group_set = set(groups)
    hosts_only = [h for h in hosts if h not in group_set]
    if not groups and not hosts_only:
        raise LimitsUnavailableError(
            f"empty inventory catalog for {cid!r} under {root}"
        )
    return groups, hosts_only


def collect_limits_for_cluster(
    clusters_root: Path | str,
    cluster_id: str,
) -> list[str]:
    """Return flat LIMIT catalog: groups (sorted) then hosts (sorted).

    Same raises as :func:`collect_limits_parts_for_cluster`.
    """
    groups, hosts = collect_limits_parts_for_cluster(clusters_root, cluster_id)
    return [*groups, *hosts]


def collect_limits_ui_for_cluster(
    clusters_root: Path | str,
    cluster_id: str,
) -> OrderedDict[str, str]:
    """Return Active Choices map: ``--limit`` value → checkbox label.

    Order: each group with direct hosts (sorted), then its hosts (sorted);
    orphan ``all.hosts`` keys; then parent-only groups. Host keys that collide
    with a group name are omitted (flat SoT: group wins). Labels nest hosts
    under groups; may include ``(hostname: …)`` from inventory.
    """
    root = Path(clusters_root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"clusters root not a directory: {root}")

    cid = (cluster_id or "").strip()
    if not cid:
        raise ValueError("cluster_id is required")

    inv = _leaf_inventory_path(root, cid)
    if not inv.is_file():
        raise LimitsUnavailableError(
            f"no hosts inventory for {cid!r} under {root}"
        )

    try:
        sections = extract_inventory_limit_sections(inv)
    except ClusterctlError as exc:
        raise LimitsUnavailableError(
            f"unusable inventory for {cid!r}: {exc}"
        ) from exc

    # Flat SoT: when a host key collides with a group name, keep the group only.
    all_group_names = {name for name, _ in sections if name}
    out: OrderedDict[str, str] = OrderedDict()
    seen_hosts: set[str] = set()
    for group_name, hosts in sections:
        if group_name:
            out[group_name] = format_group_limit_label(group_name)
        for host_key, hostname_var in hosts:
            if host_key in seen_hosts:
                continue
            if host_key in all_group_names:
                continue
            seen_hosts.add(host_key)
            out[host_key] = format_host_limit_label(host_key, hostname_var)

    if not out:
        raise LimitsUnavailableError(
            f"empty inventory catalog for {cid!r} under {root}"
        )
    return out


def collect_limits_ui_entries_for_cluster(
    clusters_root: Path | str,
    cluster_id: str,
) -> list[dict[str, str]]:
    """Ordered Active Choices entries: ``{\"value\", \"label\"}`` (JSON-safe order)."""
    ui = collect_limits_ui_for_cluster(clusters_root, cluster_id)
    return [{"value": value, "label": label} for value, label in ui.items()]


def collect_limits_map(
    clusters_root: Path | str,
    *,
    cluster_ids: list[str] | None = None,
    structured: bool = False,
    ui: bool = False,
) -> dict[str, list[str] | dict[str, list[str]] | list[dict[str, str]]]:
    """Map deployable ids → LIMIT catalogs; omit leaves without usable inventory.

    Default *cluster_ids* = :func:`collect_deployable_cluster_ids`.
    *ui* True → ordered ``[{\"value\", \"label\"}, …]`` for Active Choices
    (list preserves hierarchy through JSON / Job DSL ``JsonSlurper``).
    *structured* True → ``{"groups": [...], "hosts": [...]}`` (ignored if *ui*).
    Else flat ``list[str]``.
    """
    root = Path(clusters_root).expanduser().resolve()
    ids = (
        list(cluster_ids)
        if cluster_ids is not None
        else collect_deployable_cluster_ids(root)
    )
    out: dict[
        str, list[str] | dict[str, list[str]] | list[dict[str, str]]
    ] = {}
    for cid in ids:
        try:
            if ui:
                out[cid] = collect_limits_ui_entries_for_cluster(root, cid)
                continue
            groups, hosts = collect_limits_parts_for_cluster(root, cid)
        except LimitsUnavailableError:
            continue
        if structured:
            out[cid] = {"groups": groups, "hosts": hosts}
        else:
            out[cid] = [*groups, *hosts]
    return out


def ids_missing_from_limits_map(
    cluster_ids: list[str],
    limits_map: dict[str, object],
) -> list[str]:
    """Return *cluster_ids* (order preserved) absent from *limits_map* keys.

    Used by seed (Phase 2+) to warn when ``CLUSTER_ID`` choices include leaves
    without a usable YAML inventory catalog.
    """
    mapped = set(limits_map)
    return [cid for cid in cluster_ids if cid not in mapped]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print ansible --limit catalog names for a leaf (or JSON map for all "
            "deployable leaves with usable YAML hosts). Jenkins seed LIMIT "
            "follow-up helper (ADR 011). Flat default = groups then hosts "
            "(inventory keys). --ui = hierarchical Active Choices value→label. "
            "Deploy empty LIMIT omits --limit (separate)."
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
        help="Emit map for all deployable leaves with usable inventory (JSON object)",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help=(
            "With --all only: print {} and exit 0 when no leaf has a usable "
            "catalog (seed artifact). Error if used without --all."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON array (single id flat) or object (--all); default lines for single id",
    )
    parser.add_argument(
        "--structured",
        action="store_true",
        help=(
            "Emit {\"groups\": [...], \"hosts\": [...]} per leaf "
            "(implies JSON for single id; --all values become objects)"
        ),
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help=(
            "Emit Active Choices value→label map (group then nested hosts; "
            "hostname: in labels). Implies JSON. Seed uses this with --all."
        ),
    )
    args = parser.parse_args(argv)

    if args.allow_empty and not args.all:
        print(
            "error: --allow-empty requires --all",
            file=sys.stderr,
        )
        return 2
    if args.ui and args.structured:
        print(
            "error: --ui and --structured are mutually exclusive",
            file=sys.stderr,
        )
        return 2

    try:
        if args.all:
            mapping = collect_limits_map(
                args.clusters_root,
                structured=args.structured,
                ui=args.ui,
            )
            if not mapping:
                root = Path(args.clusters_root).expanduser().resolve()
                if args.allow_empty:
                    print("{}")
                    return 0
                print(
                    f"error: no deployable leaves with usable inventory under {root}",
                    file=sys.stderr,
                )
                return 1
            # --ui values are ordered entry lists; sort_keys only reorders leaf ids.
            print(
                json.dumps(
                    mapping,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0

        cid = (args.cluster_id or "").strip()
        if not cid:
            print("error: --cluster-id is required (or pass --all)", file=sys.stderr)
            return 2

        if args.ui:
            entries = collect_limits_ui_entries_for_cluster(args.clusters_root, cid)
            print(json.dumps(entries, ensure_ascii=False))
            return 0

        groups, hosts = collect_limits_parts_for_cluster(args.clusters_root, cid)
        flat = [*groups, *hosts]
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except LimitsUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ClusterctlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.structured or args.json:
        if args.structured:
            print(
                json.dumps(
                    {"groups": groups, "hosts": hosts},
                    ensure_ascii=False,
                )
            )
        else:
            print(json.dumps(flat, ensure_ascii=False))
    else:
        for name in flat:
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
