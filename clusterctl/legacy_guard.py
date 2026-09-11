"""Detect removed v1 artifacts that must not reappear in the repo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LEGACY_REPO_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("clusterctl/pipeline.yaml", "invocations live in clusters/default/default/cluster.yaml (schema v2)"),
    ("role_repos.defaults.yaml", "git defaults live in clusters/default/default/cluster.yaml playbooks"),
    ("playbooks/run_cluster.yaml", "use ./cluster run with schema v2 phases"),
)

LEGACY_REPO_DIRS: tuple[tuple[str, str], ...] = (
    ("profiles", "execution presets replaced by phases in cluster.yaml"),
)

RETIRED_PLAYBOOK_REPO_DIRS: tuple[tuple[str, str], ...] = (
    ("init_roles", "retired playbook repo — use atlas-node-foundation"),
    ("atlas-phase-0", "retired playbook repo — use atlas-infra-edge"),
    ("atlas-phase-1", "retired playbook repo — use atlas-compute-provision"),
    ("k8s-platform", "retired playbook repo — use atlas-k8s-core / atlas-k8s-addons"),
    ("TBD", "removed legacy archive tree (phase 8)"),
)

RETIRED_PLAYBOOK_REPO_NAMES: frozenset[str] = frozenset(name for name, _ in RETIRED_PLAYBOOK_REPO_DIRS)


@dataclass(frozen=True)
class LegacyArtifact:
    path: Path
    kind: str
    hint: str


def find_legacy_artifacts(root: Path) -> list[LegacyArtifact]:
    base = root.resolve()
    found: list[LegacyArtifact] = []

    for rel, hint in LEGACY_REPO_ARTIFACTS:
        path = base / rel
        if path.is_file():
            found.append(LegacyArtifact(path=path, kind="file", hint=hint))

    for rel, hint in LEGACY_REPO_DIRS:
        path = base / rel
        if path.is_dir() and any(path.glob("*.yaml")):
            found.append(LegacyArtifact(path=path, kind="dir", hint=hint))

    for rel, hint in RETIRED_PLAYBOOK_REPO_DIRS:
        path = base / rel
        if path.exists():
            found.append(LegacyArtifact(path=path, kind="retired_repo", hint=hint))

    workspace = base / "workspace"
    if workspace.is_dir():
        for repos_dir in sorted(workspace.glob("**/repos")):
            if not repos_dir.is_dir():
                continue
            for rel, hint in RETIRED_PLAYBOOK_REPO_DIRS:
                path = repos_dir / rel
                if path.exists():
                    found.append(
                        LegacyArtifact(
                            path=path,
                            kind="retired_workspace_repo",
                            hint=f"{hint} — rm -rf {path.relative_to(base)}",
                        )
                    )

    playbooks_dir = base / "playbooks"
    if playbooks_dir.is_dir():
        for playbook in sorted(playbooks_dir.glob("*.yaml")):
            if playbook.name == "run_cluster.yaml":
                continue
            found.append(
                LegacyArtifact(
                    path=playbook,
                    kind="shim",
                    hint="canonical playbooks live in sibling repos (see docs/cluster-config-v2.md)",
                )
            )

    return found
