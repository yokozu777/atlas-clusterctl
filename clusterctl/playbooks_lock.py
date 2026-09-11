"""Pinned playbook repo SHAs in workspace/<id>/playbooks.lock after sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import PlaybookRepoSpec, PlaybooksConfig
from clusterctl.playbooks_paths import (
    resolve_layout_dir,
    resolve_local_playbook_repo_path,
    workspace_materialized_playbook_repo_root,
)
from clusterctl.playbooks_sync import PlaybookSyncResult
from clusterctl.repo_sync_git import git_rev_parse, is_git_repo

PLAYBOOKS_LOCK_SCHEMA_VERSION = 1
PLAYBOOKS_LOCK_FILENAME = "playbooks.lock"


@dataclass(frozen=True)
class PlaybookLockEntry:
    source: str
    url: str | None = None
    requested_ref: str | None = None
    resolved_sha: str | None = None
    path: str | None = None
    materialized_path: str | None = None
    sync_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"source": self.source}
        if self.url is not None:
            payload["url"] = self.url
        if self.requested_ref is not None:
            payload["requested_ref"] = self.requested_ref
        if self.resolved_sha is not None:
            payload["resolved_sha"] = self.resolved_sha
        if self.path is not None:
            payload["path"] = self.path
        if self.materialized_path is not None:
            payload["materialized_path"] = self.materialized_path
        if self.sync_action is not None:
            payload["sync_action"] = self.sync_action
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlaybookLockEntry:
        return cls(
            source=str(data.get("source", "")).strip().lower(),
            url=data.get("url"),
            requested_ref=data.get("requested_ref"),
            resolved_sha=data.get("resolved_sha"),
            path=data.get("path"),
            materialized_path=data.get("materialized_path"),
            sync_action=data.get("sync_action"),
        )


@dataclass(frozen=True)
class PlaybooksLock:
    schema_version: int
    cluster_id: str
    workspace_id: str
    updated_at: str
    repos: dict[str, PlaybookLockEntry]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "cluster_id": self.cluster_id,
            "workspace_id": self.workspace_id,
            "updated_at": self.updated_at,
            "repos": {name: entry.to_dict() for name, entry in sorted(self.repos.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlaybooksLock:
        if not isinstance(data, dict):
            raise ClusterctlError("playbooks.lock: root must be a mapping")
        repos_raw = data.get("repos")
        if not isinstance(repos_raw, dict):
            raise ClusterctlError("playbooks.lock: repos must be a mapping")
        repos = {
            str(name): PlaybookLockEntry.from_dict(entry)
            for name, entry in repos_raw.items()
            if isinstance(entry, dict)
        }
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            cluster_id=str(data.get("cluster_id", "")),
            workspace_id=str(data.get("workspace_id", "")),
            updated_at=str(data.get("updated_at", "")),
            repos=repos,
        )


def playbooks_lock_path(workspace_root: Path) -> Path:
    return workspace_root.resolve() / PLAYBOOKS_LOCK_FILENAME


def read_playbooks_lock(workspace_root: Path) -> PlaybooksLock | None:
    path = playbooks_lock_path(workspace_root)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ClusterctlError(f"playbooks.lock: cannot read {path}: {exc}") from exc
    if not data:
        return None
    return PlaybooksLock.from_dict(data)


def write_playbooks_lock(workspace_root: Path, lock: PlaybooksLock) -> Path:
    path = playbooks_lock_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        lock.to_dict(),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    path.write_text(text, encoding="utf-8")
    return path


def _lock_entry_for_spec(
    spec: PlaybookRepoSpec,
    result: PlaybookSyncResult | None,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> PlaybookLockEntry:
    layout_dir = resolve_layout_dir(
        spec,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    )
    materialized = str(layout_dir.resolve())
    sync_action = result.action if result is not None else None

    if spec.source == "local":
        local_root = resolve_local_playbook_repo_path(spec, repo_root_path=repo_root_path)
        return PlaybookLockEntry(
            source="local",
            path=str(local_root.resolve()),
            materialized_path=materialized,
            sync_action=sync_action or "local",
        )

    dest = workspace_materialized_playbook_repo_root(workspace_root, spec.name)
    resolved_sha = git_rev_parse(dest) if is_git_repo(dest) else None
    return PlaybookLockEntry(
        source="git",
        url=spec.url,
        requested_ref=spec.ref,
        resolved_sha=resolved_sha,
        materialized_path=materialized,
        sync_action=sync_action,
    )


def build_playbooks_lock_entry(
    spec: PlaybookRepoSpec,
    *,
    workspace_root: Path,
    repo_root_path: Path,
    result: PlaybookSyncResult | None = None,
) -> PlaybookLockEntry:
    return _lock_entry_for_spec(
        spec,
        result,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    )


def update_playbooks_lock(
    *,
    cluster_id: str,
    workspace_id: str,
    workspace_root: Path,
    playbooks: PlaybooksConfig,
    results: list[PlaybookSyncResult],
    repo_root_path: Path,
    repo_names: tuple[str, ...] | None = None,
) -> Path:
    """Merge lock entries for synced repos; refresh metadata for the workspace."""
    existing = read_playbooks_lock(workspace_root)
    merged_repos: dict[str, PlaybookLockEntry] = dict(existing.repos) if existing else {}

    result_by_name = {result.name: result for result in results}
    names = repo_names or tuple(sorted(playbooks.repos))
    for name in names:
        if name not in playbooks.repos:
            raise ClusterctlError(f"playbooks.lock: repo not configured: {name!r}")
        merged_repos[name] = _lock_entry_for_spec(
            playbooks.repos[name],
            result_by_name.get(name),
            workspace_root=workspace_root,
            repo_root_path=repo_root_path,
        )

    lock = PlaybooksLock(
        schema_version=PLAYBOOKS_LOCK_SCHEMA_VERSION,
        cluster_id=cluster_id,
        workspace_id=workspace_id,
        updated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        repos=merged_repos,
    )
    return write_playbooks_lock(workspace_root, lock)


def current_git_sha_for_spec(
    spec: PlaybookRepoSpec,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> str | None:
    if spec.source != "git":
        return None
    dest = workspace_materialized_playbook_repo_root(workspace_root, spec.name)
    if not is_git_repo(dest):
        return None
    return git_rev_parse(dest)


def playbooks_lock_status_lines(
    lock: PlaybooksLock | None,
    *,
    workspace_root: Path,
) -> list[str]:
    if lock is None:
        return [f"Playbooks lock: (missing) expected at {playbooks_lock_path(workspace_root)}"]
    lines = [
        f"Playbooks lock: {playbooks_lock_path(workspace_root)} "
        f"(updated {lock.updated_at}, cluster={lock.cluster_id})"
    ]
    for name, entry in sorted(lock.repos.items()):
        if entry.source == "git":
            sha = entry.resolved_sha or "?"
            lines.append(
                f"  {name}: git {entry.requested_ref} @ {sha}"
            )
        else:
            lines.append(f"  {name}: local {entry.path}")
    return lines


def validate_playbooks_lock(
    *,
    cluster_id: str,
    workspace_id: str,
    playbooks: PlaybooksConfig,
    workspace_root: Path,
    repo_root_path: Path,
    phase_repo_names: set[str],
    strict: bool = False,
) -> list[tuple[str, str, str | None]]:
    """
    Return validation tuples: (severity, code, message[, hint]).
    severity is 'error' or 'warning'.
    """
    lock = read_playbooks_lock(workspace_root)
    path = playbooks_lock_path(workspace_root)
    if lock is None:
        return [
            (
                "error" if strict else "warning",
                "playbooks_lock_missing",
                f"playbooks.lock not found at {path}",
                "./cluster repos sync",
            )
        ]

    issues: list[tuple[str, str, str | None]] = []
    if lock.schema_version != PLAYBOOKS_LOCK_SCHEMA_VERSION:
        issues.append(
            (
                "warning",
                "playbooks_lock_schema",
                f"playbooks.lock schema_version={lock.schema_version} "
                f"(expected {PLAYBOOKS_LOCK_SCHEMA_VERSION})",
                None,
            )
        )
    if lock.cluster_id and lock.cluster_id != cluster_id:
        issues.append(
            (
                "warning",
                "playbooks_lock_cluster_mismatch",
                f"playbooks.lock cluster_id={lock.cluster_id!r} "
                f"does not match active cluster {cluster_id!r}",
                "./cluster repos sync",
            )
        )
    if lock.workspace_id and lock.workspace_id != workspace_id:
        issues.append(
            (
                "warning",
                "playbooks_lock_workspace_mismatch",
                f"playbooks.lock workspace_id={lock.workspace_id!r} "
                f"does not match resolved {workspace_id!r}",
                "./cluster repos sync",
            )
        )

    for repo_name in sorted(phase_repo_names):
        if repo_name not in playbooks.repos:
            continue
        spec = playbooks.repos[repo_name]
        entry = lock.repos.get(repo_name)
        if entry is None:
            issues.append(
                (
                    "error" if strict else "warning",
                    f"playbooks_lock_repo_missing_{repo_name}",
                    f"playbooks.lock has no entry for {repo_name!r}",
                    "./cluster repos sync",
                )
            )
            continue

        if spec.source == "git":
            current_sha = current_git_sha_for_spec(
                spec,
                workspace_root=workspace_root,
                repo_root_path=repo_root_path,
            )
            if current_sha and entry.resolved_sha and current_sha != entry.resolved_sha:
                issues.append(
                    (
                        "error" if strict else "warning",
                        f"playbooks_lock_drift_{repo_name}",
                        (
                            f"{repo_name}: materialized HEAD {current_sha[:12]} "
                            f"differs from lock {entry.resolved_sha[:12]}"
                        ),
                        "./cluster repos sync",
                    )
                )
        elif spec.source == "local":
            local_root = resolve_local_playbook_repo_path(spec, repo_root_path=repo_root_path)
            locked_path = entry.path or ""
            if locked_path and str(local_root.resolve()) != str(Path(locked_path).resolve()):
                issues.append(
                    (
                        "warning",
                        f"playbooks_lock_local_path_{repo_name}",
                        (
                            f"{repo_name}: local path changed "
                            f"(lock={locked_path}, current={local_root})"
                        ),
                        None,
                    )
                )

    return issues
