"""Git/local sync for schema v2 playbook repositories into workspace/<id>/repos/."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TextIO

from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import (
    PhasesConfig,
    PlaybookRepoSpec,
    PlaybooksConfig,
    parse_phase_ref,
    resolve_phase_alias,
)
from clusterctl.playbooks_paths import (
    layout_subpath,
    normalize_layout,
    playbook_repo_layout_ready,
    resolve_layout_dir,
    resolve_local_playbook_repo_path,
    resolve_repo_base,
    workspace_materialized_playbook_repo_root,
)
from clusterctl.repo_sync_git import (
    GitSyncTarget,
    git_clone_fresh,
    git_env,
    git_fetch_and_checkout,
    is_git_repo,
)
from clusterctl.playbooks_paths import workspace_repos_root

_ENV_REF_PATTERN = re.compile(r"^PLAYBOOKS_(?P<name>[A-Z0-9_]+)_REF$")
_ENV_PATH_PATTERN = re.compile(r"^PLAYBOOKS_(?P<name>[A-Z0-9_]+)_PATH$")
_ENV_SOURCE_PATTERN = re.compile(r"^PLAYBOOKS_(?P<name>[A-Z0-9_]+)_SOURCE$")


@dataclass(frozen=True)
class PlaybookSyncResult:
    name: str
    action: str
    path: Path
    ref: str | None = None
    detail: str = ""


def _repo_name_to_env_suffix(repo_name: str) -> str:
    return repo_name.upper().replace("-", "_").replace(".", "_")


def playbooks_ssh_key_env_name(repo_name: str) -> str:
    return f"PLAYBOOKS_{_repo_name_to_env_suffix(repo_name)}_SSH_KEY"


def ssh_key_for_playbook_repo(
    spec: PlaybookRepoSpec,
    env: dict[str, str] | None = None,
) -> str | None:
    """Per-repo SSH key path from ``PLAYBOOKS_<NAME>_SSH_KEY`` (env overlay wins)."""
    merged = dict(os.environ)
    if env:
        merged.update(env)
    key = (merged.get(playbooks_ssh_key_env_name(spec.name)) or "").strip()
    return key or None


def _env_suffix_to_repo_name(suffix: str, known_names: set[str]) -> str:
    upper = suffix.upper()
    for name in known_names:
        if _repo_name_to_env_suffix(name) == upper:
            return name
    raise ClusterctlError(
        f"unknown PLAYBOOKS env key suffix {suffix!r} — "
        f"expected one of: {', '.join(sorted(_repo_name_to_env_suffix(n) for n in known_names))}"
    )


def _collect_playbooks_env_patches(known: set[str]) -> dict[str, dict[str, str]]:
    patches: dict[str, dict[str, str]] = {}

    for key, value in os.environ.items():
        raw_value = value.strip()
        if not raw_value:
            continue

        ref_match = _ENV_REF_PATTERN.match(key)
        if ref_match:
            name = _env_suffix_to_repo_name(ref_match.group("name"), known)
            patches.setdefault(name, {})["ref"] = raw_value
            continue

        path_match = _ENV_PATH_PATTERN.match(key)
        if path_match:
            name = _env_suffix_to_repo_name(path_match.group("name"), known)
            repo_patch = patches.setdefault(name, {})
            repo_patch["path"] = raw_value
            repo_patch["source"] = "local"
            continue

        source_match = _ENV_SOURCE_PATTERN.match(key)
        if source_match:
            name = _env_suffix_to_repo_name(source_match.group("name"), known)
            patches.setdefault(name, {})["source"] = raw_value.lower()

    return patches


def apply_playbooks_env_overrides(playbooks: PlaybooksConfig) -> PlaybooksConfig:
    """Apply PLAYBOOKS_* env overrides to a playbooks config."""
    if not playbooks.repos:
        return playbooks

    known = set(playbooks.repos)
    patches = _collect_playbooks_env_patches(known)

    if not patches:
        return playbooks

    merged_repos = dict(playbooks.repos)
    for name, patch in patches.items():
        base = merged_repos[name]
        # PATH / explicit SOURCE=local → local. REF alone (or SOURCE=git) → git.
        if "path" in patch or patch.get("source", "").strip().lower() == "local":
            source = "local"
        elif "ref" in patch or patch.get("source", "").strip().lower() == "git":
            source = "git"
        else:
            source = base.source.strip().lower()

        if source == "local":
            merged_repos[name] = replace(
                base,
                source="local",
                url=None,
                ref=None,
                path=patch.get("path", base.path),
            )
        else:
            url = base.url
            if not (url and str(url).strip()):
                # Local sibling/repo_root specs have no git url; REF cannot switch source.
                # Keep source=local but record the requested ref for operators/tests.
                merged_repos[name] = replace(
                    base,
                    source="local",
                    ref=patch.get("ref", base.ref),
                    path=patch.get("path", base.path),
                )
            else:
                merged_repos[name] = replace(
                    base,
                    source="git",
                    url=url,
                    ref=patch.get("ref", base.ref),
                    path=None,
                )
        merged_repos[name].validate()

    return PlaybooksConfig(repos=merged_repos)


def playbooks_env_overrides_active(repo_names: set[str] | frozenset[str]) -> bool:
    return bool(_collect_playbooks_env_patches(set(repo_names)))


_apply_playbooks_env_overrides = apply_playbooks_env_overrides


def uses_playbooks_sync(
    playbooks_enabled: bool,
    playbooks: PlaybooksConfig | None,
) -> bool:
    return bool(playbooks_enabled and playbooks and playbooks.repos)


def require_playbooks_sync(
    playbooks_enabled: bool,
    playbooks: PlaybooksConfig | None,
) -> PlaybooksConfig:
    if not uses_playbooks_sync(playbooks_enabled, playbooks):
        raise ClusterctlError(
            "playbooks sync requires an effective playbooks catalog "
            "(define playbooks: in cluster.yaml; omit playbooks_enabled or set true; "
            "use playbooks_enabled: false to disable — see docs/cluster-config-v2.md / ADR 006)"
        )
    assert playbooks is not None
    return playbooks


def _git_target(spec: PlaybookRepoSpec) -> GitSyncTarget:
    if not spec.url or not spec.ref:
        raise ClusterctlError(f"playbooks sync {spec.name}: git source requires url and ref")
    return GitSyncTarget(
        name=spec.name,
        url=spec.url,
        ref=spec.ref,
        shallow=spec.shallow,
    )


def _materialized_ready(
    spec: PlaybookRepoSpec,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> bool:
    layout_dir = resolve_layout_dir(
        spec,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    )
    return playbook_repo_layout_ready(spec, layout_dir)


def sync_playbook_repo_spec(
    spec: PlaybookRepoSpec,
    *,
    workspace_root: Path,
    repo_root_path: Path,
    env: dict[str, str] | None = None,
    dry_run: bool = False,
    log_streams: tuple[TextIO, TextIO] | None = None,
) -> PlaybookSyncResult:
    """Sync one playbook repo according to its spec."""
    git_environment = git_env(env, ssh_key=ssh_key_for_playbook_repo(spec, env))

    if spec.source == "local":
        local_root = resolve_local_playbook_repo_path(spec, repo_root_path=repo_root_path)
        layout_dir = resolve_layout_dir(
            spec,
            workspace_root=workspace_root,
            repo_root_path=repo_root_path,
        )
        if not _materialized_ready(
            spec,
            workspace_root=workspace_root,
            repo_root_path=repo_root_path,
        ):
            raise ClusterctlError(
                f"playbooks sync {spec.name}: local path not ready at {layout_dir} "
                f"(root={local_root})"
            )
        return PlaybookSyncResult(
            name=spec.name,
            action="local",
            path=local_root,
            detail="direct path (no sync)",
        )

    dest = workspace_materialized_playbook_repo_root(workspace_root, spec.name)
    sync_mode = spec.effective_sync

    if sync_mode == "never":
        layout_dir = resolve_layout_dir(
            spec,
            workspace_root=workspace_root,
            repo_root_path=repo_root_path,
        )
        return PlaybookSyncResult(
            name=spec.name,
            action="never",
            path=dest,
            ref=spec.ref,
            detail=f"sync=never — materialized copy must exist at {layout_dir}",
        )

    if sync_mode == "if_missing" and _materialized_ready(
        spec,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    ):
        return PlaybookSyncResult(
            name=spec.name,
            action="skipped",
            path=dest,
            ref=spec.ref,
            detail="sync=if_missing and repo already ready",
        )

    if dry_run:
        action = "clone" if not is_git_repo(dest) else "update"
        return PlaybookSyncResult(
            name=spec.name,
            action=f"dry-run-{action}",
            path=dest,
            ref=spec.ref,
            detail=f"would {action} {spec.url} @ {spec.ref}",
        )

    target = _git_target(spec)
    if not is_git_repo(dest):
        git_clone_fresh(target, dest, git_environment, log_streams=log_streams)
        action = "cloned"
    else:
        git_fetch_and_checkout(target, dest, git_environment, log_streams=log_streams)
        action = "updated"

    layout_dir = resolve_layout_dir(
        spec,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    )
    if not playbook_repo_layout_ready(spec, layout_dir):
        layout_hint = normalize_layout(spec.layout) or "(repo root)"
        raise ClusterctlError(
            f"playbooks sync {spec.name}: checkout at {dest} @ {spec.ref} "
            f"did not produce a usable layout at {layout_dir} (layout={layout_hint!r})"
        )

    return PlaybookSyncResult(
        name=spec.name,
        action=action,
        path=dest,
        ref=spec.ref,
        detail=f"{spec.url} @ {spec.ref}",
    )


def sync_playbooks(
    playbooks: PlaybooksConfig,
    *,
    workspace_root: Path,
    repo_root_path: Path,
    repo_names: tuple[str, ...] | list[str] | None = None,
    env: dict[str, str] | None = None,
    dry_run: bool = False,
    log_streams: tuple[TextIO, TextIO] | None = None,
) -> list[PlaybookSyncResult]:
    playbooks = _apply_playbooks_env_overrides(playbooks)
    workspace_repos_root(workspace_root).mkdir(parents=True, exist_ok=True)
    names = tuple(repo_names or sorted(playbooks.repos))
    results: list[PlaybookSyncResult] = []
    for name in names:
        if name not in playbooks.repos:
            raise ClusterctlError(f"playbooks sync: repo not configured: {name!r}")
        results.append(
            sync_playbook_repo_spec(
                playbooks.repos[name],
                workspace_root=workspace_root,
                repo_root_path=repo_root_path,
                env=env,
                dry_run=dry_run,
                log_streams=log_streams,
            )
        )
    return results


def repo_names_for_phase_refs(phase_refs: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for phase_ref in phase_refs:
        repo_name, _ = parse_phase_ref(phase_ref)
        if repo_name not in seen:
            seen.append(repo_name)
    return tuple(seen)


def repo_names_for_phase_alias(
    phase_name: str,
    *,
    phases: PhasesConfig,
) -> tuple[str, ...]:
    phase_ref = resolve_phase_alias(phase_name, phases.phase_aliases)
    return repo_names_for_phase_refs((phase_ref,))


def repo_names_for_all_phases(phases: PhasesConfig) -> tuple[str, ...]:
    return repo_names_for_phase_refs(phases.phases)


def ensure_playbooks_synced(
    *,
    playbooks_enabled: bool,
    playbooks: PlaybooksConfig | None,
    workspace_root: Path,
    repo_root_path: Path,
    phases: PhasesConfig | None = None,
    repo_names: tuple[str, ...] | list[str] | None = None,
    env: dict[str, str] | None = None,
    dry_run: bool = False,
    log_streams: tuple[TextIO, TextIO] | None = None,
) -> list[PlaybookSyncResult]:
    """Sync playbook repos before ansible execution (no-op when playbooks inactive)."""
    if not uses_playbooks_sync(playbooks_enabled, playbooks):
        return []

    assert playbooks is not None
    names = repo_names
    if names is None and phases is not None:
        names = repo_names_for_all_phases(phases)

    return sync_playbooks(
        playbooks,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
        repo_names=names,
        env=env,
        dry_run=dry_run,
        log_streams=log_streams,
    )


def playbook_repo_status_records(
    playbooks: PlaybooksConfig,
    *,
    workspace_root: Path,
    repo_root_path: Path,
    repo_names: tuple[str, ...] | None = None,
) -> list[dict]:
    playbooks = _apply_playbooks_env_overrides(playbooks)
    names = repo_names or tuple(sorted(playbooks.repos))
    records: list[dict] = []
    for name in names:
        spec = playbooks.repos[name]
        layout_dir = resolve_layout_dir(
            spec,
            workspace_root=workspace_root,
            repo_root_path=repo_root_path,
        )
        ready = playbook_repo_layout_ready(spec, layout_dir)
        layout_label = normalize_layout(spec.layout) or "(repo root)"
        record: dict = {
            "name": name,
            "state": "ready" if ready else "missing",
            "source": spec.source,
            "layout": layout_label,
            "layout_dir": str(layout_dir),
        }
        if spec.source == "git":
            dest = workspace_materialized_playbook_repo_root(workspace_root, spec.name)
            head = None
            if is_git_repo(dest):
                try:
                    completed = subprocess.run(
                        ["git", "-C", str(dest), "rev-parse", "--short", "HEAD"],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    if completed.returncode == 0:
                        head = completed.stdout.strip() or None
                except OSError:
                    pass
            record.update(
                {
                    "url": spec.url,
                    "ref": spec.ref,
                    "sync": spec.effective_sync,
                    "path": str(dest),
                    "head": head,
                }
            )
        else:
            local_root = resolve_local_playbook_repo_path(spec, repo_root_path=repo_root_path)
            record.update(
                {
                    "path": str(local_root),
                    "sync": "never",
                }
            )
        records.append(record)
    return records


def playbook_repo_status_lines(
    playbooks: PlaybooksConfig,
    *,
    workspace_root: Path,
    repo_root_path: Path,
    repo_names: tuple[str, ...] | None = None,
) -> list[str]:
    records = playbook_repo_status_records(
        playbooks,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
        repo_names=repo_names,
    )
    lines = ["Playbook repo sync status:"]
    for rec in records:
        name = rec["name"]
        state = rec["state"]
        layout_label = rec["layout"]
        if rec["source"] == "git":
            head = f" HEAD={rec['head']}" if rec.get("head") else ""
            dest = rec["path"]
            lines.append(
                f"  {name}: {state} git {rec['url']} @ {rec['ref']} "
                f"(sync={rec['sync']}, layout={layout_label}, path={dest}{head})"
            )
        else:
            layout_dir = rec["layout_dir"]
            local_root = rec["path"]
            lines.append(
                f"  {name}: {state} local {local_root} → {layout_dir} "
                f"(layout={layout_label}, sync=never)"
            )
    return lines


def playbooks_summary_lines(
    playbooks: PlaybooksConfig,
    *,
    workspace_root: Path,
    repo_root_path: Path,
    repo_names: tuple[str, ...] | None = None,
) -> list[str]:
    playbooks = _apply_playbooks_env_overrides(playbooks)
    names = repo_names or tuple(sorted(playbooks.repos))
    lines = [f"Playbook repos: {len(names)} configured"]
    for name in names:
        spec = playbooks.repos[name]
        layout_dir = resolve_layout_dir(
            spec,
            workspace_root=workspace_root,
            repo_root_path=repo_root_path,
        )
        if spec.source == "git":
            material = resolve_repo_base(
                spec,
                workspace_root=workspace_root,
                repo_root_path=repo_root_path,
            )
            lines.append(
                f"  {name}: git {spec.url} @ {spec.ref} "
                f"(sync={spec.effective_sync}, layout={normalize_layout(spec.layout) or '/'}, "
                f"material={material}, roles={layout_dir})"
            )
        else:
            local_root = resolve_local_playbook_repo_path(spec, repo_root_path=repo_root_path)
            lines.append(
                f"  {name}: local {local_root} → {layout_dir} "
                f"(layout={normalize_layout(spec.layout) or '/'})"
            )
    return lines
