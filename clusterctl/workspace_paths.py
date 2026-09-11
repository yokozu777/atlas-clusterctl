"""Per-cluster Ansible controller runtime paths under workspace/<workspace_id>/."""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from typing import Literal, TextIO

from clusterctl.exceptions import ClusterctlError

ControllerTempLocation = Literal["workspace", "container"]

WORKSPACE_ANSIBLE_ENV_KEYS = (
    "ANSIBLE_CACHE_PLUGIN_CONNECTION",
    "ANSIBLE_LOCAL_TEMP",
    "ANSIBLE_COLLECTIONS_PATHS",
    "TMPDIR",
    "ANSIBLE_FORCE_COLOR",
)

CONTAINER_CONTROLLER_TMP_ROOT = Path("/tmp/clusterctl")
_UNSAFE_WORKSPACE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


def workspace_facts_cache_dir(workspace_root: Path) -> Path:
    return workspace_root / ".ansible_facts_cache"


def workspace_ansible_tmp_dir(workspace_root: Path) -> Path:
    return workspace_root / ".ansible" / "tmp"


def workspace_collections_dir(workspace_root: Path) -> Path:
    """Ansible Galaxy collections root (contains ``ansible_collections/`` after install)."""
    return workspace_root / ".ansible" / "collections"


def container_controller_ansible_tmp_dir(workspace_id: str) -> Path:
    """Ephemeral controller temp on container FS (ansible 2.21+ RPC — not bind-mount)."""
    safe_id = _UNSAFE_WORKSPACE_ID.sub("-", workspace_id.strip()).strip("-")
    if not safe_id:
        raise ClusterctlError(
            f"invalid workspace id for container controller temp: {workspace_id!r}"
        )
    return CONTAINER_CONTROLLER_TMP_ROOT / safe_id


def resolve_controller_temp_location(*, inside_docker_container: bool) -> ControllerTempLocation:
    """Where ANSIBLE_LOCAL_TEMP / TMPDIR live for the current process."""
    return "container" if inside_docker_container else "workspace"


def effective_controller_temp_location(
    *,
    inside_docker_container: bool,
    configured_docker: bool,
) -> ControllerTempLocation:
    """Resolved controller temp for display / host-side preflight."""
    if inside_docker_container or configured_docker:
        return "container"
    return "workspace"


def controller_ansible_tmp_dir(
    workspace_root: Path,
    *,
    workspace_id: str,
    controller_temp: ControllerTempLocation,
) -> Path:
    if controller_temp == "container":
        return container_controller_ansible_tmp_dir(workspace_id)
    return workspace_ansible_tmp_dir(workspace_root)


def ensure_workspace_ansible_dirs(workspace_root: Path) -> None:
    """Create workspace-local Ansible runtime directories (idempotent)."""
    for path in (
        workspace_ansible_tmp_dir(workspace_root),
        workspace_facts_cache_dir(workspace_root),
        workspace_collections_dir(workspace_root),
    ):
        path.mkdir(parents=True, exist_ok=True)


def ensure_container_controller_tmp_dir(workspace_id: str) -> Path:
    """Create controller temp on container FS (docker executor / in-container runs)."""
    path = container_controller_ansible_tmp_dir(workspace_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_workspace_ansible_env(
    env: dict[str, str],
    workspace_root: Path,
    *,
    workspace_id: str | None = None,
    controller_temp: ControllerTempLocation = "workspace",
    ensure_dirs: bool = True,
) -> None:
    """Set Ansible controller env vars scoped to workspace (no repo-root fallback)."""
    ws = workspace_root.resolve()
    wid = (workspace_id or env.get("CLUSTER_WORKSPACE_ID", "")).strip()
    if controller_temp == "container" and not wid:
        raise ClusterctlError(
            "CLUSTER_WORKSPACE_ID required for container controller temp (docker executor)"
        )

    cache_dir = workspace_facts_cache_dir(ws)
    collections_dir = workspace_collections_dir(ws)
    tmp_dir = controller_ansible_tmp_dir(
        ws,
        workspace_id=wid or "unknown",
        controller_temp=controller_temp,
    )

    if ensure_dirs:
        cache_dir.mkdir(parents=True, exist_ok=True)
        collections_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)

    env["ANSIBLE_CACHE_PLUGIN_CONNECTION"] = str(cache_dir)
    env["ANSIBLE_COLLECTIONS_PATHS"] = str(collections_dir)
    env["ANSIBLE_LOCAL_TEMP"] = str(tmp_dir)
    env["TMPDIR"] = str(tmp_dir)
    # clusterctl runs ansible-playbook via subprocess PIPE (not a TTY); force ANSI colors.
    env["ANSIBLE_FORCE_COLOR"] = "true"


def validate_workspace_ansible_env(
    env: dict[str, str],
    workspace_root: Path,
    *,
    workspace_id: str | None = None,
    controller_temp: ControllerTempLocation = "workspace",
) -> None:
    """Fail fast when ansible runtime paths are missing or inconsistent."""
    ws = workspace_root.resolve()
    wid = (workspace_id or env.get("CLUSTER_WORKSPACE_ID", "")).strip()
    if controller_temp == "container" and not wid:
        raise ClusterctlError(
            "CLUSTER_WORKSPACE_ID required to validate container controller temp"
        )

    cache_expected = workspace_facts_cache_dir(ws).resolve()
    tmp_expected = controller_ansible_tmp_dir(
        ws,
        workspace_id=wid or "unknown",
        controller_temp=controller_temp,
    ).resolve()

    cache_raw = env.get("ANSIBLE_CACHE_PLUGIN_CONNECTION", "").strip()
    if not cache_raw:
        raise ClusterctlError(
            f"missing ANSIBLE_CACHE_PLUGIN_CONNECTION — ansible runtime must run via ./cluster "
            f"(paths belong under {ws})"
        )
    cache_actual = Path(cache_raw).resolve()
    try:
        cache_actual.relative_to(ws)
    except ValueError as exc:
        raise ClusterctlError(
            f"ANSIBLE_CACHE_PLUGIN_CONNECTION must be under workspace {ws}, got {cache_actual} "
            f"(legacy repo-root .ansible paths are not supported)"
        ) from exc
    if cache_actual != cache_expected:
        raise ClusterctlError(
            f"ANSIBLE_CACHE_PLUGIN_CONNECTION must be {cache_expected}, got {cache_actual}"
        )

    tmp_raw = env.get("ANSIBLE_LOCAL_TEMP", "").strip()
    if not tmp_raw:
        raise ClusterctlError(
            f"missing ANSIBLE_LOCAL_TEMP — ansible runtime must run via ./cluster "
            f"(expected {tmp_expected})"
        )
    tmp_actual = Path(tmp_raw).resolve()

    if controller_temp == "container":
        try:
            tmp_actual.relative_to(ws)
        except ValueError:
            pass
        else:
            raise ClusterctlError(
                f"ANSIBLE_LOCAL_TEMP must be on container FS ({CONTAINER_CONTROLLER_TMP_ROOT}/…), "
                f"not under workspace bind-mount {ws} — "
                f"ansible-core 2.21+ RPC requires local temp in docker executor"
            )

    if tmp_actual != tmp_expected:
        raise ClusterctlError(
            f"ANSIBLE_LOCAL_TEMP must be {tmp_expected}, got {tmp_actual}"
        )

    tmpdir = env.get("TMPDIR", "").strip()
    if tmpdir and Path(tmpdir).resolve() != tmp_expected:
        raise ClusterctlError(
            "TMPDIR must match ANSIBLE_LOCAL_TEMP "
            f"({tmp_expected}), got {Path(tmpdir).resolve()}"
        )


def workspace_ansible_summary_lines(
    workspace_root: Path,
    *,
    workspace_id: str | None = None,
    controller_temp: ControllerTempLocation = "workspace",
) -> list[str]:
    ws = workspace_root.resolve()
    lines = [
        f"Fact cache:  {workspace_facts_cache_dir(ws)}",
        f"Collections: {workspace_collections_dir(ws)}",
    ]
    if controller_temp == "container":
        if not workspace_id:
            lines.append("Ansible tmp:  (container FS — set CLUSTER_WORKSPACE_ID)")
            return lines
        tmp = container_controller_ansible_tmp_dir(workspace_id)
        lines.append(f"Ansible tmp: {tmp} (container FS, docker executor)")
    else:
        lines.append(f"Ansible tmp: {workspace_ansible_tmp_dir(ws)}")
    return lines


def legacy_repo_root_ansible_entries(repo_root: Path) -> list[Path]:
    """Return legacy ansible artifact paths that must not exist at repo root."""
    root = repo_root.resolve()
    return [root / name for name in (".ansible", ".ansible_facts_cache")]


def purge_legacy_repo_root_ansible(repo_root: Path) -> tuple[Path, ...]:
    """Remove legacy ansible paths at *repo_root* (not under workspace/<id>/).

    Deletes both empty and non-empty ``.ansible`` / ``.ansible_facts_cache``
    (unlike :func:`assert_no_legacy_repo_root_ansible`, which ignores empty dirs).

    Returns paths that were deleted. Safe no-op when nothing exists.
    Raises :class:`ClusterctlError` when removal fails (permissions, etc.).
    """
    removed: list[Path] = []
    for path in legacy_repo_root_ansible_entries(repo_root):
        if not path.exists() and not path.is_symlink():
            continue
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as exc:
            raise ClusterctlError(
                f"cannot remove legacy repo-root {path.name}: {exc} — "
                f"fix permissions or run `rm -rf {path.name}` and use "
                f"workspace/<id>/ instead"
            ) from exc
        removed.append(path)
    return tuple(removed)


def report_purged_legacy_repo_root_ansible(
    repo_root: Path,
    *,
    stream: TextIO | None = None,
) -> tuple[Path, ...]:
    """Purge legacy repo-root ansible paths and print a short notice to *stream*.

    Message prefix is ``cluster:`` for both ``./cluster`` and
    ``python3 -m clusterctl.ansible_env``. Names are printed without a forced
    trailing slash.
    """
    out = sys.stderr if stream is None else stream
    removed = purge_legacy_repo_root_ansible(repo_root)
    if removed:
        names = ", ".join(path.name for path in removed)
        print(
            f"cluster: removed legacy repo-root {names}"
            " (use workspace/<id>/ instead)",
            file=out,
        )
    return removed


def assert_no_legacy_repo_root_ansible(repo_root: Path) -> None:
    """Fail when a non-empty legacy ansible path exists at *repo_root*.

    Empty directories are ignored (CLI purge removes them at startup; this assert
    is defense-in-depth for mid-flight / non-CLI callers).
    """
    for path in legacy_repo_root_ansible_entries(repo_root):
        if not path.exists():
            continue
        if path.is_dir():
            try:
                if not any(path.iterdir()):
                    continue
            except OSError:
                pass
        raise ClusterctlError(
            f"legacy ansible path at repo root: {path.name}/ — "
            f"expected auto-purge at CLI start; remove with "
            f"`rm -rf {path.name}` and use workspace/<id>/ instead"
        )
