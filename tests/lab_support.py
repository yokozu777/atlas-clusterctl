"""Helpers for optional local labs vs public templates — discover by product overlays."""

from __future__ import annotations

import functools
import re
import unittest
from pathlib import Path
from typing import Callable, TypeVar

from clusterctl.cluster_layout import cascade_group_vars_dirs
from clusterctl.cluster_vars_loader import load_cluster_vars
from clusterctl.paths import clusters_root, list_deployable_cluster_ids, repo_root
from tests.catalog_parity import PRODUCT_REPOS, leaf_product_overlays

# Controller checkout (public templates / product trees only — not live inventory SoT).
ROOT = Path(__file__).resolve().parents[1]

# Stack name → required atlas-*.yml product stems on the leaf (not secrets).
STACK_MARKERS: dict[str, frozenset[str]] = {
    "k8s": frozenset({"atlas-k8s-core"}),
    "jenkins": frozenset({"atlas-jenkins-agent"}),
    "gitlab": frozenset({"atlas-gitlab-runner"}),
    "postgresql": frozenset({"atlas-postgresql"}),
    "redis": frozenset({"atlas-redis"}),
    "kafka": frozenset({"atlas-kafka"}),
    "infra": frozenset({"atlas-infra-edge"}),
    "pve_templates": frozenset({"atlas-compute-provision"}),
}

PUBLIC_K8S_TEMPLATE = ROOT / "clusters" / "_template" / "k8s_full"
PUBLIC_JENKINS_TEMPLATE = ROOT / "clusters" / "_template" / "jenkins_agent"
PUBLIC_GITLAB_RUNNER_TEMPLATE = ROOT / "clusters" / "_template" / "gitlab_runner"
PUBLIC_INFRA_TEMPLATE = ROOT / "clusters" / "_template" / "infra_edge"
PUBLIC_REDIS_TEMPLATE = ROOT / "clusters" / "_template" / "redis"
PUBLIC_POSTGRESQL_TEMPLATE = ROOT / "clusters" / "_template" / "postgresql"
PUBLIC_KAFKA_TEMPLATE = ROOT / "clusters" / "_template" / "kafka"

# Full k8s playbooks/phases invocation count — public ``_template/k8s_full``
# and any discovered k8s lab (provision + init + core + addons).
FULL_K8S_INVOCATION_COUNT = 105

_PKG_REPOS_KEY_RE = re.compile(r"(?m)^pkg_repos(_extra)?:\s")
_CLUSTER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_-]*$")

F = TypeVar("F", bound=Callable[..., object])


def _discover_root(root: Path | None = None) -> Path:
    """Same SoT as CLI / ClusterContext.load (ATLAS_CLUSTER_ROOT → repo_root)."""
    return root if root is not None else repo_root()


def group_vars_all_file(leaf: Path, name: str) -> Path:
    """Path to ``group_vars/all/<name>`` under a cluster leaf or template."""
    return leaf / "group_vars" / "all" / name


def foundation_has_pkg_repos_key(text: str) -> bool:
    """True when overlay declares top-level ``pkg_repos`` and/or ``pkg_repos_extra``."""
    return bool(_PKG_REPOS_KEY_RE.search(text))


def foundation_merged_repo_names(cluster_id: str, *, root: Path | None = None) -> list[str]:
    """Enabled repo names from cascade-merged ``pkg_repos`` + ``pkg_repos_extra``."""
    merged = _merged_vars(cluster_id, root=root)
    names: list[str] = []
    for key in ("pkg_repos", "pkg_repos_extra"):
        entries = merged.get(key) or []
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            enabled = item.get("enabled", True)
            if enabled is False or enabled in ("false", "False", "no", "No"):
                continue
            names.append(str(name))
    return names


def lab_leaf(*parts: str) -> Path:
    """Path to a lab leaf under the live inventory tree (``.config`` / env / checkout)."""
    return clusters_root(_discover_root()) / Path(*parts)


def lab_exists(*parts: str) -> bool:
    """True when a local lab leaf has cluster.yaml on disk."""
    return (lab_leaf(*parts) / "cluster.yaml").is_file()


def lab_id_exists(cluster_id: str) -> bool:
    parts = tuple(p for p in cluster_id.split("/") if p)
    return lab_exists(*parts)


def present_deployable_ids(root: Path | None = None) -> list[str]:
    return list_deployable_cluster_ids(_discover_root(root))


def lab_products(cluster_id: str, *, root: Path | None = None) -> frozenset[str]:
    """Product overlay stems present on a deployable leaf."""
    repo = _discover_root(root)
    parts = tuple(p for p in cluster_id.split("/") if p)
    all_dir = clusters_root(repo).joinpath(*parts) / "group_vars" / "all"
    return frozenset(leaf_product_overlays(all_dir))


def _merged_vars(cluster_id: str, *, root: Path | None = None) -> dict:
    repo = _discover_root(root)
    croot = clusters_root(repo)
    parts = tuple(p for p in cluster_id.split("/") if p)
    leaf = croot.joinpath(*parts)
    cascade = cascade_group_vars_dirs(croot, cluster_id)
    return load_cluster_vars(leaf, cascade_dirs=cascade)


def _matches_stack(cluster_id: str, stack: str, *, root: Path | None = None) -> bool:
    markers = STACK_MARKERS.get(stack)
    if markers is None:
        raise KeyError(f"unknown stack marker: {stack!r}")
    products = lab_products(cluster_id, root=root)
    if not markers <= products:
        return False
    if stack == "infra":
        # Thin infra-edge bridge on k8s leaves is not a full infra lab.
        return "infra_platform_hosts" in _merged_vars(cluster_id, root=root)
    if stack == "pve_templates":
        # Golden PVE factory: compute overlay without guest provision_stack.
        return not _merged_vars(cluster_id, root=root).get("provision_stack")
    return True


def labs_for_stack(stack: str, *, root: Path | None = None) -> list[str]:
    """Deployable cluster ids matching *stack* markers (sorted for stability)."""
    if stack not in STACK_MARKERS:
        raise KeyError(f"unknown stack marker: {stack!r}")
    found = [
        cid
        for cid in present_deployable_ids(root)
        if _matches_stack(cid, stack, root=root)
    ]
    return sorted(found)


def lab_id_for(stack: str, *, root: Path | None = None) -> str | None:
    """First matching deployable lab for *stack*, or None."""
    labs = labs_for_stack(stack, root=root)
    return labs[0] if labs else None


def lab_path_for(stack: str, *, root: Path | None = None) -> Path | None:
    """Filesystem path to ``lab_id_for(stack)``, or None."""
    cluster_id = lab_id_for(stack, root=root)
    if cluster_id is None:
        return None
    parts = tuple(p for p in cluster_id.split("/") if p)
    return clusters_root(_discover_root(root)).joinpath(*parts)


def skip_unless_stack(stack: str) -> Callable[[F], F]:
    """Skip at test runtime when no deployable leaf matches *stack* markers."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> object:
            if lab_id_for(stack) is None:
                raise unittest.SkipTest(
                    f"no local lab for stack {stack!r} "
                    "(discover via lab_support; see docs/local-labs.md)"
                )
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def skip_unless_lab(*parts: str) -> Callable[[F], F]:
    """Skip at test runtime when a concrete inventory path is missing (prefer skip_unless_stack)."""
    rel = "/".join(parts)

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> object:
            if not lab_exists(*parts):
                raise unittest.SkipTest(
                    f"local lab not present: clusters/{rel} (see docs/local-labs.md)"
                )
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def skip_unless_lab_id(cluster_id: str) -> Callable[[F], F]:
    parts = tuple(p for p in cluster_id.split("/") if p)
    return skip_unless_lab(*parts)


def assert_known_labs_subset(test: unittest.TestCase, deployable: list[str]) -> None:
    """Deployable ids must be hierarchical env/name and exist under clusters_root."""
    croot = clusters_root(_discover_root())
    for cluster_id in deployable:
        test.assertRegex(
            cluster_id,
            _CLUSTER_ID_RE,
            f"unexpected deployable id shape: {cluster_id}",
        )
        parts = tuple(p for p in cluster_id.split("/") if p)
        test.assertTrue(
            (croot.joinpath(*parts) / "cluster.yaml").is_file(),
            f"deployable id missing on disk: {cluster_id}",
        )


# Re-export for callers that imported PRODUCT_REPOS via lab discovery docs.
__all__ = (
    "STACK_MARKERS",
    "FULL_K8S_INVOCATION_COUNT",
    "PRODUCT_REPOS",
    "PUBLIC_K8S_TEMPLATE",
    "PUBLIC_JENKINS_TEMPLATE",
    "PUBLIC_GITLAB_RUNNER_TEMPLATE",
    "PUBLIC_INFRA_TEMPLATE",
    "PUBLIC_REDIS_TEMPLATE",
    "PUBLIC_POSTGRESQL_TEMPLATE",
    "PUBLIC_KAFKA_TEMPLATE",
    "ROOT",
    "assert_known_labs_subset",
    "foundation_has_pkg_repos_key",
    "foundation_merged_repo_names",
    "group_vars_all_file",
    "lab_exists",
    "lab_id_exists",
    "lab_id_for",
    "lab_leaf",
    "lab_path_for",
    "lab_products",
    "labs_for_stack",
    "present_deployable_ids",
    "skip_unless_lab",
    "skip_unless_lab_id",
    "skip_unless_stack",
)
