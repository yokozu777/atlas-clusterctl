"""Inventory group extraction (YAML/JSON Ansible inventory)."""

from __future__ import annotations

from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML required") from exc

from clusterctl.exceptions import ClusterctlError

K8S_GROUPS = frozenset({"k8s_lbs", "k8s_masters", "k8s_workers"})
INFRA_GROUPS = frozenset({"infra_platform"})
PGSQL_GROUPS = frozenset({"pgsql_etcd_cluster", "pgsql_cluster", "pgsql_lbs"})
MYSQL_GROUPS = frozenset({"mysql"})
REDIS_GROUPS = frozenset(
    {"redis_cluster_masters", "redis_cluster_replicas", "redis_proxies", "redis_lbs"}
)
KAFKA_GROUPS = frozenset({"kafka_controllers", "kafka_brokers"})
# Working inventory groups with VM hosts (parent ``postgresql``/``redis``/``kafka`` is not a data group).
DATA_GROUPS = PGSQL_GROUPS | MYSQL_GROUPS | REDIS_GROUPS | KAFKA_GROUPS


def _walk_hosts(node: object, found: set[str]) -> None:
    if not isinstance(node, dict):
        return
    hosts = node.get("hosts")
    if isinstance(hosts, dict):
        for name in hosts:
            found.add(str(name))
    children = node.get("children")
    if isinstance(children, dict):
        for child in children.values():
            _walk_hosts(child, found)


def _host_hostname_var(meta: object) -> str | None:
    """Optional inventory ``hostname:`` DNS var on a host entry (display only)."""
    if not isinstance(meta, dict):
        return None
    raw = meta.get("hostname")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


# Sentinel section key for hosts declared under ``all:`` / root without a named
# inventory group (still valid ``--limit`` host keys; no group checkbox in UI).
_LIMIT_ORPHAN_SECTION = ""


def _merge_limit_host_entries(
    sections: dict[str, list[tuple[str, str | None]]],
    section_key: str,
    hosts: dict,
) -> None:
    entries: list[tuple[str, str | None]] = []
    for name, meta in hosts.items():
        entries.append((str(name), _host_hostname_var(meta)))
    entries.sort(key=lambda item: item[0])
    existing = sections.setdefault(section_key, [])
    seen = {h for h, _ in existing}
    for host_key, hostname in entries:
        if host_key not in seen:
            existing.append((host_key, hostname))
            seen.add(host_key)
    existing.sort(key=lambda item: item[0])


def _walk_limit_sections(
    node: object,
    group_name: str | None,
    sections: dict[str, list[tuple[str, str | None]]],
) -> None:
    """Collect groups with direct hosts → ``(host_key, hostname_var?)`` lists.

    Hosts on a node with *group_name* ``None`` (typically ``all.hosts``) go into
    the orphan section (empty key) — they must not be dropped vs flat catalog.
    """
    if not isinstance(node, dict):
        return
    hosts = node.get("hosts")
    if isinstance(hosts, dict) and hosts:
        section_key = (
            group_name if group_name is not None else _LIMIT_ORPHAN_SECTION
        )
        _merge_limit_host_entries(sections, section_key, hosts)
    children = node.get("children")
    if isinstance(children, dict):
        for child_name, child in children.items():
            _walk_limit_sections(child, str(child_name), sections)


def extract_inventory_limit_sections(
    inventory_path: Path,
) -> list[tuple[str | None, list[tuple[str, str | None]]]]:
    """Return LIMIT UI sections: ``(group|None, [(host_key, hostname_var?), ...])``.

    * Groups that declare direct ``hosts:`` come first (sorted by group name),
      each with hosts sorted by inventory key.
    * Orphan hosts (``all.hosts`` / root hosts without a named group) follow as
      ``(None, [...])`` — host checkboxes only (no invented group name).
    * Remaining inventory groups (parents without direct hosts) follow with an
      empty host list — still valid ``--limit`` group targets.
    * ``hostname_var`` is optional inventory ``hostname:`` (label only; SoT for
      ansible ``--limit`` remains the host **key**).
    """
    if not inventory_path.is_file():
        raise ClusterctlError(f"inventory not found: {inventory_path}")

    text = inventory_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ClusterctlError(f"invalid inventory YAML: {inventory_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ClusterctlError(f"inventory must be a mapping: {inventory_path}")

    sections: dict[str, list[tuple[str, str | None]]] = {}
    if "all" in data:
        _walk_limit_sections(data["all"], None, sections)
        for key, value in data.items():
            if key != "all" and isinstance(value, dict):
                _walk_limit_sections(value, str(key), sections)
    else:
        for key, value in data.items():
            if isinstance(value, dict):
                _walk_limit_sections(value, str(key), sections)

    orphans = sections.pop(_LIMIT_ORPHAN_SECTION, [])
    with_hosts = [
        (name, hosts)
        for name, hosts in sorted(sections.items(), key=lambda item: item[0])
        if hosts
    ]
    present = {name for name, _ in with_hosts}
    parent_only = sorted(extract_inventory_groups(inventory_path) - present)
    out: list[tuple[str | None, list[tuple[str, str | None]]]] = [
        *with_hosts,
    ]
    if orphans:
        out.append((None, orphans))
    out.extend((name, []) for name in parent_only)
    return out


def extract_inventory_hostnames(inventory_path: Path) -> set[str]:
    """Return inventory host keys (names used for host_vars/<name>.yml)."""
    if not inventory_path.is_file():
        raise ClusterctlError(f"inventory not found: {inventory_path}")

    text = inventory_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ClusterctlError(f"invalid inventory YAML: {inventory_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ClusterctlError(f"inventory must be a mapping: {inventory_path}")

    hostnames: set[str] = set()
    if "all" in data:
        _walk_hosts(data["all"], hostnames)
        for key, value in data.items():
            if key != "all" and isinstance(value, dict):
                _walk_hosts(value, hostnames)
    else:
        for value in data.values():
            if isinstance(value, dict):
                _walk_hosts(value, hostnames)

    return hostnames


def _walk_groups(node: object, found: set[str]) -> None:
    if not isinstance(node, dict):
        return
    children = node.get("children")
    if isinstance(children, dict):
        for name, child in children.items():
            found.add(str(name))
            _walk_groups(child, found)
    hosts = node.get("hosts")
    if isinstance(hosts, dict) and hosts:
        return


def extract_inventory_groups(inventory_path: Path) -> set[str]:
    if not inventory_path.is_file():
        raise ClusterctlError(f"inventory not found: {inventory_path}")

    text = inventory_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ClusterctlError(f"invalid inventory YAML: {inventory_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ClusterctlError(f"inventory must be a mapping: {inventory_path}")

    groups: set[str] = set()
    if "all" in data:
        _walk_groups(data["all"], groups)
        for key in data:
            if key != "all" and isinstance(data[key], dict):
                groups.add(str(key))
                _walk_groups(data[key], groups)
    else:
        for key, value in data.items():
            if isinstance(value, dict):
                groups.add(str(key))
                _walk_groups(value, groups)

    return groups
