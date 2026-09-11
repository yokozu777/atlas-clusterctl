"""`./cluster limits` — ansible --limit catalog for the current cluster."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from clusterctl.cluster_layout import discover_config_dir
from clusterctl.exceptions import ClusterctlError
from clusterctl.inventory import extract_inventory_limit_sections
from clusterctl.paths import clusters_root, inventory_path
from clusterctl.tools.list_cluster_limits import (
    LimitsUnavailableError,
    collect_limits_parts_for_cluster,
)


def collect_cluster_limits(
    clusters: Path | str,
    cluster_id: str,
) -> dict[str, Any]:
    """JSON payload for ``./cluster limits --json``.

    ``hosts`` entries are inventory keys plus optional ``hostname:`` DNS and
    the first named group that lists the host.
    """
    groups, host_keys = collect_limits_parts_for_cluster(clusters, cluster_id)
    hostname_by_key: dict[str, str | None] = dict.fromkeys(host_keys)
    group_by_key: dict[str, str | None] = dict.fromkeys(host_keys)
    try:
        inv = inventory_path(discover_config_dir(Path(clusters), cluster_id))
        for group_name, hosts in extract_inventory_limit_sections(inv):
            for host_key, hostname_var in hosts:
                if host_key not in hostname_by_key:
                    continue
                if hostname_var and not hostname_by_key[host_key]:
                    hostname_by_key[host_key] = hostname_var
                if group_name and not group_by_key[host_key]:
                    group_by_key[host_key] = group_name
    except ClusterctlError:
        pass
    return {
        "cluster_id": cluster_id,
        "groups": groups,
        "hosts": [
            {
                "key": key,
                "hostname": hostname_by_key.get(key),
                "group": group_by_key.get(key),
            }
            for key in host_keys
        ],
    }


def cmd_limits(root: Path, cluster_id: str, *, as_json: bool = False) -> int:
    clusters = clusters_root(root)
    try:
        payload = collect_cluster_limits(clusters, cluster_id)
    except FileNotFoundError as exc:
        print(f"cluster: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"cluster: {exc}", file=sys.stderr)
        return 1
    except LimitsUnavailableError as exc:
        message = str(exc)
        if "not found" in message:
            print(f"cluster: {exc}", file=sys.stderr)
            return 1
        payload = {"cluster_id": cluster_id, "groups": [], "hosts": []}

    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", end="")
        return 0

    groups = payload["groups"]
    hosts = payload["hosts"]
    if not groups and not hosts:
        print("(no inventory groups or hosts for --limit)")
        return 0
    print("groups:")
    for name in groups:
        print(f"  {name}")
    print("hosts:")
    for row in hosts:
        hostname = row.get("hostname")
        extra = f"  {hostname}" if hostname else ""
        print(f"  {row['key']}{extra}")
    return 0
