"""Path resolution for schema v2 playbook repositories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import PlaybookRepoSpec, PlaybooksConfig

WORKSPACE_REPOS_DIRNAME = "repos"

__all__ = [
    "ResolvedPlaybookLocation",
    "WORKSPACE_REPOS_DIRNAME",
    "collect_local_playbook_docker_mounts",
    "layout_subpath",
    "layout_dir_ready",
    "normalize_layout",
    "playbook_repo_layout_ready",
    "repo_layout_ready",
    "resolve_ansible_roles_path_for_spec",
    "resolve_layout_dir",
    "resolve_local_playbook_repo_path",
    "resolve_playbook_entry_location",
    "resolve_playbooks_entry_location",
    "resolve_repo_base",
    "workspace_materialized_playbook_repo_root",
    "workspace_repos_root",
]


@dataclass(frozen=True)
class ResolvedPlaybookLocation:
    repo_name: str
    repo_base: Path
    playbook_path: Path


def workspace_repos_root(workspace_root: Path) -> Path:
    return workspace_root.resolve() / WORKSPACE_REPOS_DIRNAME


def resolve_playbook_entry_location(
    repo_spec: PlaybookRepoSpec,
    entry_file: str,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> ResolvedPlaybookLocation:
    """Resolve v2 ``entry.file`` under a playbook repo."""
    base = resolve_repo_base(
        repo_spec,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    )
    playbook = Path(entry_file)
    if playbook.is_absolute():
        path = playbook.resolve()
        return ResolvedPlaybookLocation(
            repo_name=repo_spec.name,
            repo_base=path.parent,
            playbook_path=path,
        )
    playbook_path = (base / playbook).resolve()
    return ResolvedPlaybookLocation(
        repo_name=repo_spec.name,
        repo_base=base.resolve(),
        playbook_path=playbook_path,
    )


def resolve_playbooks_entry_location(
    playbooks: PlaybooksConfig,
    repo_name: str,
    entry_file: str,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> ResolvedPlaybookLocation:
    spec = playbooks.repos.get(repo_name)
    if spec is None:
        raise ClusterctlError(f"playbooks repo not configured: {repo_name!r}")
    return resolve_playbook_entry_location(
        spec,
        entry_file,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    )


def workspace_materialized_playbook_repo_root(workspace_root: Path, repo_name: str) -> Path:
    return workspace_repos_root(workspace_root) / repo_name


def normalize_layout(layout: str) -> str:
    """Return layout subpath without leading/trailing slashes ('' = repo root)."""
    return str(layout or "").strip().strip("/")


def layout_subpath(spec: PlaybookRepoSpec) -> Path:
    normalized = normalize_layout(spec.layout)
    return Path(normalized) if normalized else Path(".")


def resolve_local_playbook_repo_path(
    spec: PlaybookRepoSpec,
    *,
    repo_root_path: Path,
) -> Path:
    if spec.source != "local" or not spec.path:
        raise ClusterctlError(
            f"resolve_local_playbook_repo_path requires source=local: {spec.name}"
        )

    raw = Path(spec.path)
    if spec.path_relative_to == "absolute":
        return raw.resolve()
    if spec.path_relative_to == "repo_root":
        return (repo_root_path / raw).resolve()
    if spec.path_relative_to == "sibling":
        return (repo_root_path.parent / raw).resolve()

    raise ClusterctlError(
        f"playbooks.{spec.name}: unsupported path_relative_to={spec.path_relative_to!r}"
    )


def resolve_repo_base(
    spec: PlaybookRepoSpec,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> Path:
    if spec.source == "git":
        return workspace_materialized_playbook_repo_root(workspace_root, spec.name)
    return resolve_local_playbook_repo_path(spec, repo_root_path=repo_root_path)


def resolve_layout_dir(
    spec: PlaybookRepoSpec,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> Path:
    """Resolved layout directory (ANSIBLE_ROLES_PATH target or repo root)."""
    base = resolve_repo_base(
        spec,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    )
    subpath = layout_subpath(spec)
    if subpath == Path("."):
        return base.resolve()
    return (base / subpath).resolve()


def repo_layout_ready(layout_dir: Path) -> bool:
    """Whether a resolved layout directory looks usable (non-empty)."""
    if not layout_dir.is_dir():
        return False
    try:
        next(layout_dir.iterdir())
    except StopIteration:
        return False
    return True


def layout_dir_ready(layout_dir: Path, *, markers: tuple[str, ...] = ()) -> bool:
    """Whether a layout directory is usable (non-empty or marker dirs present)."""
    if not layout_dir.is_dir():
        return False
    if markers:
        return any((layout_dir / marker).is_dir() for marker in markers)
    return repo_layout_ready(layout_dir)


def playbook_repo_layout_ready(spec: PlaybookRepoSpec, layout_dir: Path) -> bool:
    """Whether ANSIBLE_ROLES_PATH for a playbook repo looks usable."""
    return layout_dir_ready(layout_dir, markers=spec.readiness_markers)


def resolve_ansible_roles_path_for_spec(
    spec: PlaybookRepoSpec,
    *,
    workspace_root: Path,
    repo_root_path: Path,
) -> str:
    """Resolved ANSIBLE_ROLES_PATH for a playbook repo (layout dir)."""
    layout_dir = resolve_layout_dir(
        spec,
        workspace_root=workspace_root,
        repo_root_path=repo_root_path,
    )
    if not playbook_repo_layout_ready(spec, layout_dir):
        if spec.source == "git":
            dest = workspace_materialized_playbook_repo_root(workspace_root, spec.name)
            raise ClusterctlError(
                f"playbook repo {spec.name!r} not ready at {layout_dir} — "
                f"expected git checkout under {dest} "
                f"({spec.url} @ {spec.ref}). "
                f"Run: ./cluster playbooks sync --repo {spec.name}"
            )
        local_root = resolve_local_playbook_repo_path(spec, repo_root_path=repo_root_path)
        raise ClusterctlError(
            f"playbook repo {spec.name!r} not ready at {layout_dir} "
            f"(source=local, root={local_root})"
        )
    return str(layout_dir.resolve())


def collect_local_playbook_docker_mounts(
    playbooks,
    *,
    repo_root_path: Path,
) -> list[tuple[Path, Path]]:
    """Extra ro bind-mounts for source=local playbook repos outside repo_root."""
    from clusterctl.exceptions import ClusterctlError
    from clusterctl.playbooks_config import PlaybooksConfig

    if not isinstance(playbooks, PlaybooksConfig):
        raise ClusterctlError("collect_local_playbook_docker_mounts requires PlaybooksConfig")

    mounts: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    repo_resolved = repo_root_path.resolve()

    for spec in playbooks.repos.values():
        if spec.source != "local":
            continue
        local_root = resolve_local_playbook_repo_path(spec, repo_root_path=repo_root_path).resolve()
        if not local_root.is_dir():
            raise ClusterctlError(
                f"docker: local playbook repo {spec.name!r} not found: {local_root}"
            )
        try:
            local_root.relative_to(repo_resolved)
            continue
        except ValueError:
            pass
        if local_root not in seen:
            seen.add(local_root)
            mounts.append((local_root, local_root))

    return mounts
