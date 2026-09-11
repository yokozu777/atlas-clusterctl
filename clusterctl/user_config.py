"""Controller-local clusterctl config (``.config/`` under the checkout).

Runtime file (gitignored)::

    $ATLAS_CLUSTER_ROOT/.config/config.yaml

Template (tracked)::

    .config/config.yaml.example

Copy once::

    cp .config/config.yaml.example .config/config.yaml

Optional override for the config file path: ``ATLAS_CLUSTERCTL_CONFIG``.

Live clusters tree (inventory) resolution:

1. ``ATLAS_CLUSTERS_ROOT``
2. ``clusters.path`` in ``.config/config.yaml``
3. ``$ATLAS_CLUSTER_ROOT/clusters``

Workspace parent directory resolution:

1. ``ATLAS_WORKSPACE_ROOT``
2. ``workspace.path`` in ``.config/config.yaml``
3. ``$ATLAS_CLUSTER_ROOT/workspace``
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from clusterctl.exceptions import ClusterctlError

CONFIG_DIRNAME = ".config"
CONFIG_FILENAME = "config.yaml"
CONFIG_EXAMPLE_FILENAME = "config.yaml.example"
ENV_CLUSTERS_ROOT = "ATLAS_CLUSTERS_ROOT"
ENV_WORKSPACE_ROOT = "ATLAS_WORKSPACE_ROOT"
ENV_CONFIG_PATH = "ATLAS_CLUSTERCTL_CONFIG"


def local_config_dir(repo_root: Path | None = None) -> Path:
    """``$ATLAS_CLUSTER_ROOT/.config`` directory."""
    if repo_root is None:
        from clusterctl.paths import repo_root as _repo_root

        repo_root = _repo_root()
    return repo_root / CONFIG_DIRNAME


def local_config_path(repo_root: Path | None = None) -> Path:
    """Path to ``.config/config.yaml`` (or ``ATLAS_CLUSTERCTL_CONFIG``)."""
    override = os.environ.get(ENV_CONFIG_PATH, "").strip()
    if override:
        return Path(override).expanduser()
    return local_config_dir(repo_root) / CONFIG_FILENAME


def local_config_example_path(repo_root: Path | None = None) -> Path:
    return local_config_dir(repo_root) / CONFIG_EXAMPLE_FILENAME


# Back-compat alias used by older call sites / tests.
user_config_path = local_config_path


def load_user_config(
    path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Load YAML local config; missing file → empty dict."""
    cfg_path = path or local_config_path(repo_root)
    if not cfg_path.is_file():
        return {}
    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ClusterctlError(f"cannot read config {cfg_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ClusterctlError(f"invalid YAML in config {cfg_path}: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ClusterctlError(f"config {cfg_path} must be a mapping at the top level")
    return raw


def resolve_configured_path(raw_path: str, *, repo_root: Path) -> Path:
    """Resolve absolute or repo-relative path from local config.

    Relative paths are resolved against ``ATLAS_CLUSTER_ROOT`` (not ``.config/``).
    """
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        return (repo_root / path).resolve()
    return path.resolve()


def _section_path(
    config: dict[str, Any],
    section: str,
    *,
    repo_root: Path | None,
) -> Path | None:
    block = config.get(section)
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ClusterctlError(f"config {section}: must be a mapping")
    raw_path = block.get("path")
    if raw_path is None or raw_path == "":
        return None
    if not isinstance(raw_path, str):
        raise ClusterctlError(f"config {section}.path must be a string")
    base = repo_root
    if base is None:
        from clusterctl.paths import repo_root as _repo_root

        base = _repo_root()
    return resolve_configured_path(raw_path, repo_root=base)


def clusters_path_from_user_config(
    config: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> Path | None:
    """Return resolved ``clusters.path`` from local config, or None if unset."""
    data = config if config is not None else load_user_config(repo_root=repo_root)
    return _section_path(data, "clusters", repo_root=repo_root)


def workspace_path_from_user_config(
    config: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> Path | None:
    """Return resolved ``workspace.path`` from local config, or None if unset."""
    data = config if config is not None else load_user_config(repo_root=repo_root)
    return _section_path(data, "workspace", repo_root=repo_root)


def git_ssh_key_from_user_config(
    config: dict[str, Any] | None = None,
    *,
    repo_root: Path | None = None,
) -> Path | None:
    """Return resolved ``git.ssh_key`` from local config, or None if unset.

    Lowest-priority default for playbook repo pull (CLI). UI bindings live in hub.
    """
    data = config if config is not None else load_user_config(repo_root=repo_root)
    block = data.get("git")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ClusterctlError("config git: must be a mapping")
    raw_path = block.get("ssh_key")
    if raw_path is None or raw_path == "":
        return None
    if not isinstance(raw_path, str):
        raise ClusterctlError("config git.ssh_key must be a string")
    base = repo_root
    if base is None:
        from clusterctl.paths import repo_root as _repo_root

        base = _repo_root()
    return resolve_configured_path(raw_path, repo_root=base)
