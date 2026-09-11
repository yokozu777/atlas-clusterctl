"""Discover and validate Ansible host_vars/ under clusters/<id>/."""

from __future__ import annotations

from pathlib import Path

from clusterctl.cluster_vars_loader import load_yaml_mapping
from clusterctl.exceptions import ClusterctlError

HOST_VAR_SUFFIXES: tuple[str, ...] = (".yml", ".yaml")


def host_vars_dir(config_dir: Path) -> Path:
    return config_dir / "host_vars"


def host_var_filename(hostname: str) -> str:
    """Return the canonical host_vars filename for an inventory hostname."""
    return f"{hostname}.yml"


def discover_host_vars(config_dir: Path) -> tuple[tuple[str, Path], ...]:
    """
    Return ``(inventory_hostname, path)`` for each ``host_vars/*.{yml,yaml}``.

    Hostname is the file stem (must match the inventory host key).
    """
    directory = host_vars_dir(config_dir)
    if not directory.is_dir():
        return ()

    by_host: dict[str, Path] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        if path.suffix not in HOST_VAR_SUFFIXES:
            continue
        hostname = path.stem
        if not hostname or hostname.startswith("."):
            continue
        resolved = path.resolve()
        prior = by_host.get(hostname)
        if prior is not None:
            raise ClusterctlError(
                f"duplicate host_vars for {hostname!r}: {prior.name} and {path.name}"
            )
        by_host[hostname] = resolved

    return tuple((host, by_host[host]) for host in sorted(by_host))


def validate_host_var_content(path: Path) -> str | None:
    """Return an error message when a host_vars file is not a YAML mapping."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return "host_vars file is empty"
    try:
        load_yaml_mapping(path)
    except ClusterctlError as exc:
        return str(exc)
    return None


def host_var_path_for(config_dir: Path, hostname: str) -> Path:
    return host_vars_dir(config_dir) / host_var_filename(hostname)
