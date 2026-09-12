"""Reference cluster + org baseline stub helpers (schema v2)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from clusterctl.cluster_config_loader import load_merged_cluster_config_v2
from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import (
    ClusterConfigV2,
    parse_cluster_config_v2_fragment,
    parse_phase_ref,
    stage_name_for_phase_ref,
)

# Optional local lab (gitignored). Prefer when present for maintainer workstation tests.
REFERENCE_CLUSTER_ID = "dev/mxhash"
REFERENCE_CLUSTER_REL = Path("clusters") / "dev" / "mxhash" / "cluster.yaml"

# Public SoT for fixtures / CI when local labs are absent.
PUBLIC_REFERENCE_REL = Path("clusters") / "_template" / "k8s_full" / "cluster.yaml"

ORG_BASELINE_REL = Path("clusters") / "default" / "default" / "cluster.yaml"

# Full k8s cascade invocation count — public ``_template/k8s_full`` and lab
# ``dev/mxhash`` (provision + init + core + addons; golden templates are a
# separate ``pve_templates`` leaf). Infra is a separate leaf
# (``ci/infra`` / ``_template/infra_edge``).
FULL_K8S_INVOCATION_COUNT = 105
MXHASH_INVOCATION_COUNT = 105


def public_reference_cluster_yaml(root: Path | None = None) -> Path:
    base = (root or Path(__file__).resolve().parents[1]).resolve()
    return base / PUBLIC_REFERENCE_REL


def reference_cluster_yaml(root: Path | None = None) -> Path:
    """Prefer local lab leaf; fall back to public scrubbed template."""
    base = (root or Path(__file__).resolve().parents[1]).resolve()
    lab = base / REFERENCE_CLUSTER_REL
    if lab.is_file():
        return lab
    return base / PUBLIC_REFERENCE_REL


def org_baseline_cluster_yaml(root: Path | None = None) -> Path:
    base = (root or Path(__file__).resolve().parents[1]).resolve()
    return base / ORG_BASELINE_REL


def _cluster_yaml_has_playbooks(path: Path) -> bool:
    """True when YAML has a non-empty playbooks mapping (stub scaffolds do not)."""
    if not path.is_file():
        return False
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    playbooks = raw.get("playbooks")
    return isinstance(playbooks, dict) and bool(playbooks)


def _rewrite_playbooks_sibling_to_repo_root(raw: dict[str, Any]) -> dict[str, Any]:
    """Isolated fixtures live under a tempfile; sibling paths would escape the tree."""
    playbooks = raw.get("playbooks")
    if not isinstance(playbooks, dict):
        return raw
    for spec in playbooks.values():
        if isinstance(spec, dict) and spec.get("path_relative_to") == "sibling":
            spec["path_relative_to"] = "repo_root"
    return raw


def _load_fragment_cluster_yaml(path: Path, *, default_id: str) -> ClusterConfigV2:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ClusterctlError(f"invalid cluster.yaml (expected mapping): {path}")
    config = parse_cluster_config_v2_fragment(raw)
    if config.cluster_id is None:
        config = replace(config, cluster_id=default_id)
    return config


def seed_org_baseline_fixture(target_root: Path) -> Path:
    """Copy public full-k8s cluster.yaml into isolated test repo at default/default.

    Rewrites ``path_relative_to: sibling`` → ``repo_root`` so stubs under the tempfile
    resolve correctly. Skips rewrite when dest already has a real playbooks block
    (tests may mutate the seeded baseline in place).
    """
    dest = org_baseline_cluster_yaml(target_root)
    if _cluster_yaml_has_playbooks(dest):
        return dest
    source_repo = Path(__file__).resolve().parents[1]
    src = public_reference_cluster_yaml(source_repo)
    if not src.is_file():
        src = reference_cluster_yaml(source_repo)
    if not src.is_file():
        raise FileNotFoundError(f"missing reference cluster template: {src}")
    raw = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ClusterctlError(f"invalid reference cluster.yaml: {src}")
    raw = _rewrite_playbooks_sibling_to_repo_root(dict(raw))
    # Fixture leaf id for cascade layer 1
    raw["id"] = "default/default"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return dest


def load_public_reference_cluster_config(repo_root: Path | None = None) -> ClusterConfigV2:
    """Load scrubbed ``_template/k8s_full`` playbooks/phases (always available in public tree)."""
    source = Path(__file__).resolve().parents[1].resolve()
    base = (repo_root or source).resolve()
    path = public_reference_cluster_yaml(base)
    if not path.is_file():
        path = public_reference_cluster_yaml(source)
    if not path.is_file():
        raise FileNotFoundError(f"missing public reference template: {path}")
    return _load_fragment_cluster_yaml(path, default_id="template/k8s_full")


def load_reference_cluster_config(repo_root: Path | None = None) -> ClusterConfigV2:
    """Full-k8s SoT: local ``dev/mxhash`` when present, else public ``_template/k8s_full``."""
    source = Path(__file__).resolve().parents[1].resolve()
    base = (repo_root or source).resolve()
    lab = base / REFERENCE_CLUSTER_REL
    if lab.is_file():
        return load_merged_cluster_config_v2(base / "clusters", REFERENCE_CLUSTER_ID)
    # Prefer template in the given root; fall back to package tree (isolated temp roots).
    if public_reference_cluster_yaml(base).is_file():
        return load_public_reference_cluster_config(base)
    return load_public_reference_cluster_config(source)


def load_org_baseline_cluster_config(repo_root: Path | None = None) -> ClusterConfigV2:
    """Full playbooks/phases SoT for tests.

    Prefer seeded ``clusters/default/default`` when it carries real playbooks
    (after ``seed_org_baseline_fixture``). Otherwise use public ``_template/k8s_full``
    (not a private lab that may still embed infra).
    """
    source = Path(__file__).resolve().parents[1].resolve()
    base = (repo_root or source).resolve()
    seeded = org_baseline_cluster_yaml(base)
    if _cluster_yaml_has_playbooks(seeded):
        return _load_fragment_cluster_yaml(seeded, default_id="default/default")
    if public_reference_cluster_yaml(base).is_file():
        return load_public_reference_cluster_config(base)
    return load_public_reference_cluster_config(source)


def build_org_baseline_cluster_config(
    repo_root: Path | None = None,
    *,
    execution: dict[str, Any] | None = None,
) -> ClusterConfigV2:
    """Return org baseline config (optionally override execution for tests)."""
    config = load_org_baseline_cluster_config(repo_root)
    if execution is not None:
        config = replace(config, execution=execution)
    return config


def build_org_baseline_playbooks(repo_root: Path | None = None):
    config = load_org_baseline_cluster_config(repo_root)
    if config.playbooks is None:
        raise ClusterctlError("org baseline missing playbooks")
    return config.playbooks


def build_org_baseline_phases(repo_root: Path | None = None):
    config = load_org_baseline_cluster_config(repo_root)
    if config.phases is None:
        raise ClusterctlError("org baseline missing phases")
    return config.phases


def default_git_repos_from_yaml(path: Path) -> dict[str, dict[str, Any]]:
    """Extract git repo sync fields from a v2 cluster.yaml playbooks section."""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    playbooks = data.get("playbooks") or {}
    if not isinstance(playbooks, dict):
        raise ValueError(f"invalid playbooks in {path}")
    repos: dict[str, dict[str, Any]] = {}
    for name, raw in playbooks.items():
        if not isinstance(raw, dict):
            continue
        repos[str(name)] = {
            key: raw[key]
            for key in ("source", "url", "ref", "path", "path_relative_to", "shallow", "sync", "layout")
            if key in raw
        }
    return repos


def org_baseline_required_repo_names(repo_root: Path | None = None) -> frozenset[str]:
    """Repo names referenced by org baseline ``phases`` (schema-driven registry)."""
    from clusterctl.playbooks_registry import required_playbook_repo_names

    config = load_org_baseline_cluster_config(repo_root)
    return required_playbook_repo_names(config.playbooks, config.phases)


LOCAL_PLAYBOOK_REPO_NAMES: tuple[str, ...] = (
    "atlas-node-foundation",
    "atlas-infra-edge",
    "atlas-compute-provision",
    "atlas-k8s-core",
    "atlas-k8s-addons",
    "atlas-jenkins-agent",
    "atlas-gitlab-runner",
)

K8S_PLAYBOOK_REPO_NAMES: tuple[str, ...] = (
    "atlas-k8s-core",
    "atlas-k8s-addons",
)

_PLAYBOOK_REQUIREMENTS_STUBS: dict[str, tuple[str, ...]] = {
    "atlas-node-foundation": ("ansible.posix",),
    "atlas-infra-edge": ("ansible.posix",),
    "atlas-k8s-core": ("ansible.posix",),
    "atlas-k8s-addons": ("kubernetes.core",),
    "atlas-jenkins-agent": ("ansible.posix",),
    "atlas-gitlab-runner": ("ansible.posix",),
}


def _write_playbook_requirements_stub(repo_path: Path, collections: tuple[str, ...]) -> None:
    lines = ["---", "collections:"]
    for name in collections:
        version = ">=2.2.0" if name == "ansible.posix" else ">=6.4.0"
        lines.append(f"  - name: {name}")
        lines.append(f'    version: "{version}"')
    (repo_path / "requirements.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def seed_local_playbook_repo_stubs(root: Path) -> None:
    """Minimal on-disk stubs for isolated tests (roles/ layout for atlas-* repos)."""
    playbook_files = {
        "atlas-node-foundation": "init_nodes.yaml",
        "atlas-infra-edge": "infra_hosts.yaml",
        "atlas-compute-provision": "provision_nodes.yaml",
    }
    for repo in LOCAL_PLAYBOOK_REPO_NAMES:
        path = root / repo
        path.mkdir(parents=True, exist_ok=True)
        if repo == "atlas-k8s-core":
            (path / "roles" / "00_controller_tooling").mkdir(parents=True, exist_ok=True)
            (path / "roles" / "29_fetch_kubeconfig").mkdir(parents=True, exist_ok=True)
            playbooks = path / "playbooks"
            playbooks.mkdir(exist_ok=True)
            (playbooks / "cluster_core.yaml").write_text("---\n", encoding="utf-8")
        elif repo == "atlas-k8s-addons":
            (path / "roles" / "120_controller_tooling").mkdir(parents=True, exist_ok=True)
            (path / "roles" / "140_fetch_kubeconfig").mkdir(parents=True, exist_ok=True)
            (path / "roles" / "210_helm_bootstrap").mkdir(parents=True, exist_ok=True)
            (path / "roles" / "220_calico").mkdir(parents=True, exist_ok=True)
            (path / "roles" / "310_prometheus").mkdir(parents=True, exist_ok=True)
            (path / "roles" / "520_envoy_gateway").mkdir(parents=True, exist_ok=True)
            playbooks = path / "playbooks"
            playbooks.mkdir(exist_ok=True)
            (playbooks / "cluster_addons.yaml").write_text("---\n", encoding="utf-8")
        elif repo == "atlas-jenkins-agent":
            (path / "roles" / "03_install_jslave").mkdir(parents=True, exist_ok=True)
            playbooks = path / "playbooks"
            playbooks.mkdir(exist_ok=True)
            (playbooks / "jenkins_agent.yaml").write_text("---\n", encoding="utf-8")
        elif repo == "atlas-gitlab-runner":
            (path / "roles" / "03_install_runner").mkdir(parents=True, exist_ok=True)
            playbooks = path / "playbooks"
            playbooks.mkdir(exist_ok=True)
            (playbooks / "gitlab_runner.yaml").write_text("---\n", encoding="utf-8")
        else:
            (path / "roles" / "dummy").mkdir(parents=True, exist_ok=True)
            playbooks = path / "playbooks"
            playbooks.mkdir(exist_ok=True)
            playbook_name = playbook_files.get(repo, "playbook.yaml")
            (playbooks / playbook_name).write_text("---\n", encoding="utf-8")
            if repo == "atlas-compute-provision":
                (playbooks / "build_templates.yaml").write_text("---\n", encoding="utf-8")
        stub_reqs = _PLAYBOOK_REQUIREMENTS_STUBS.get(repo)
        if stub_reqs is not None:
            _write_playbook_requirements_stub(path, stub_reqs)


def local_playbooks_override_block(*repos: str) -> dict[str, dict[str, str]]:
    """Local playbooks cascade overrides (repo_root paths) for isolated tests."""
    catalog = {
        "atlas-node-foundation": {
            "source": "local",
            "path": "atlas-node-foundation",
            "path_relative_to": "repo_root",
        },
        "atlas-infra-edge": {
            "source": "local",
            "path": "atlas-infra-edge",
            "path_relative_to": "repo_root",
        },
        "atlas-compute-provision": {
            "source": "local",
            "path": "atlas-compute-provision",
            "path_relative_to": "repo_root",
        },
        "atlas-k8s-core": {
            "source": "local",
            "path": "atlas-k8s-core",
            "path_relative_to": "repo_root",
            "layout": "roles/",
        },
        "atlas-k8s-addons": {
            "source": "local",
            "path": "atlas-k8s-addons",
            "path_relative_to": "repo_root",
            "layout": "roles/",
        },
        "atlas-jenkins-agent": {
            "source": "local",
            "path": "atlas-jenkins-agent",
            "path_relative_to": "repo_root",
            "layout": "roles/",
        },
        "atlas-gitlab-runner": {
            "source": "local",
            "path": "atlas-gitlab-runner",
            "path_relative_to": "repo_root",
            "layout": "roles/",
        },
    }
    if repos:
        return {name: catalog[name] for name in repos}
    return dict(catalog)


def migration_table(repo_root: Path | None = None) -> list[dict[str, str]]:
    """Parity table: org baseline phases vs legacy stage/ansible naming."""
    config = load_org_baseline_cluster_config(repo_root)
    assert config.playbooks is not None and config.phases is not None
    aliases = config.phases.phase_aliases
    rows: list[dict[str, str]] = []
    for phase_ref in config.phases.phases:
        stage_name = stage_name_for_phase_ref(phase_ref, aliases)
        repo_name, entry_id = parse_phase_ref(phase_ref)
        entry = config.playbooks.repos[repo_name].entries[entry_id]
        rows.append(
            {
                "legacy_stage": stage_name,
                "legacy_playbook": entry.file,
                "legacy_ansible_phase": phase_ref,
                "v2_phase_ref": phase_ref,
                "v2_repo": repo_name,
                "v2_entry": entry_id,
                "v2_playbook_file": entry.file,
                "invocations": str(len(entry.invocations)),
            }
        )
    return rows
