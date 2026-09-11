"""Scaffold a new cluster under clusters/<id>/ or clusters/<env>/<name>/."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML required") from exc

from clusterctl.cluster_layout import (
    CLUSTER_CONFIG_NAME,
    canonical_cluster_id,
    cluster_config_dir,
    config_dir_is_usable,
    discover_config_dir,
    is_org_baseline_cluster_id,
    normalize_cluster_id,
    validate_cluster_id,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.leaf_dns import (
    discover_leaf_dns_overlays,
    overlays_with_dns_suffix_value,
    patch_leaf_dns_identity,
)

_SINGLE_CLUSTER_ID = re.compile(r"^[a-z][a-z0-9._-]+$")
_HIERARCHICAL_CLUSTER_ID = re.compile(r"^[a-z][a-z0-9._-]+/[a-z][a-z0-9._-]+$")
# secrets.yml: never copy live credentials.
# cluster.yml: legacy only (ADR 003); templates omit it; validate warns if present.
_COPY_IGNORE = shutil.ignore_patterns("secrets.yml")


@dataclass(frozen=True)
class InitOptions:
    """Options for ``init_cluster`` (``./cluster init``)."""

    from_id: str = "default"
    template_name: str | None = None
    display_name: str | None = None
    dns_domain_suffix: str | None = None
    validate: bool = True
    force: bool = False


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ClusterctlError(f"expected YAML mapping: {path}")
    return data


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def validate_init_cluster_id(cluster_id: str) -> str:
    text = normalize_cluster_id(cluster_id)
    if is_org_baseline_cluster_id(text):
        raise ClusterctlError("cannot init org baseline id 'default/default'")
    if text in {"default", "default/default"}:
        raise ClusterctlError("cannot init cluster id 'default'; pick another id")
    if text.startswith("_") or "/_" in text:
        raise ClusterctlError(f"cluster id must not contain '_': {cluster_id!r}")
    if _HIERARCHICAL_CLUSTER_ID.fullmatch(text):
        env, name = text.split("/", 1)
        if name == "default" and env != "default":
            raise ClusterctlError(
                f"cannot init env policy path {text!r}; use a deployable name "
                f"(e.g. {env}/mycluster)"
            )
        return text
    if _SINGLE_CLUSTER_ID.match(text):
        return text
    raise ClusterctlError(
        f"invalid cluster id {cluster_id!r} — use env/name (e.g. dev/mxhash) "
        "or a single-segment id (e.g. lab)"
    )


def init_cluster_target_dir(root: Path, cluster_id: str) -> Path:
    from clusterctl.paths import clusters_root as resolve_clusters_root

    text = validate_init_cluster_id(cluster_id)
    inventory_root = resolve_clusters_root(root)
    if "/" in text:
        return cluster_config_dir(inventory_root, text)
    return inventory_root / text


def _resolve_source_dir(root: Path, from_id: str) -> Path:
    from clusterctl.paths import clusters_root as resolve_clusters_root
    from clusterctl.paths import product_clusters_root

    text = normalize_cluster_id(from_id)
    search_roots = [resolve_clusters_root(root)]
    product = product_clusters_root(root)
    if product.resolve() not in {path.resolve() for path in search_roots}:
        search_roots.append(product)

    for base in search_roots:
        if "/" in text:
            candidate = cluster_config_dir(base, text)
        else:
            candidate = base / text
        if candidate.is_dir():
            return candidate
    raise ClusterctlError(f"source cluster not found: clusters/{text}/")


def _resolve_copy_source(root: Path, options: InitOptions) -> Path:
    from clusterctl.paths import product_clusters_root

    if options.template_name is not None:
        # Templates always ship with the controller checkout, not the inventory tree.
        base = product_clusters_root(root) / "_template"
        source = base / options.template_name if options.template_name else base
        if not source.is_dir():
            label = options.template_name or "root"
            raise ClusterctlError(f"clusters/_template/{label} not found")
        return source

    from_id = options.from_id.strip()
    if not from_id or from_id.startswith("_"):
        raise ClusterctlError(
            f"invalid --from cluster id {from_id!r} — pick an existing clusters/<id>/"
        )
    return _resolve_source_dir(root, from_id)


def _fallback_runtime_source(root: Path, source: Path) -> Path | None:
    """When --from is policy-only (cluster.yaml fragment), borrow hosts/vars."""
    from clusterctl.paths import clusters_root as resolve_clusters_root
    from clusterctl.paths import product_clusters_root

    if (source / "hosts").is_file() or (source / "group_vars").is_dir():
        return None
    product = product_clusters_root(root)
    inventory = resolve_clusters_root(root)
    for candidate in (
        inventory / "default" / "default",
        product / "default" / "default",
        inventory / "default",
        product / "default",
        product / "_template",
    ):
        if candidate.is_dir() and candidate != source and config_dir_is_usable(candidate):
            return candidate
    return None


def _ensure_group_vars_from_org_baseline(root: Path, target: Path) -> None:
    """If the copy lacks group_vars, borrow org baseline overlays (default/default)."""
    if (target / "group_vars").is_dir():
        return
    from clusterctl.paths import clusters_root as resolve_clusters_root
    from clusterctl.paths import product_clusters_root

    for base in (resolve_clusters_root(root), product_clusters_root(root)):
        baseline = base / "default" / "default" / "group_vars"
        if baseline.is_dir():
            shutil.copytree(baseline, target / "group_vars", ignore=_COPY_IGNORE)
            return


def _effective_display_name(cluster_id: str, explicit: str | None) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    return cluster_id


def _patch_cluster_yaml(
    path: Path,
    cluster_id: str,
    *,
    display_name: str | None,
) -> None:
    if not path.is_file():
        return
    data = _load_yaml(path)
    data["id"] = canonical_cluster_id(cluster_id)
    data["display_name"] = _effective_display_name(cluster_id, display_name)
    _write_yaml(path, data)


def _copy_runtime_files(source: Path, target: Path) -> None:
    for name in ("hosts", "group_vars", "pub_keys"):
        src = source / name
        if not src.exists():
            continue
        dest = target / name
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=_COPY_IGNORE)
        else:
            shutil.copy2(src, dest)


def _run_post_init_validate(root: Path, cluster_id: str) -> None:
    from clusterctl.context import ClusterContext
    from clusterctl.validate import format_report_text, validate_cluster

    ctx = ClusterContext.load(cluster_id=cluster_id)
    report = validate_cluster(ctx, root=root)
    if report.ok:
        return
    message = format_report_text(report).strip()
    raise ClusterctlError(f"init validation failed for {cluster_id!r}:\n{message}")


def init_cluster(root: Path, cluster_id: str, *, options: InitOptions | None = None) -> Path:
    """
    Create clusters/<id>/ or clusters/<env>/<name>/ by copying a source cluster.

    Default: ``--from default`` (copy ``clusters/default/``, not ``_template``).
    Use ``--from default/default`` for org baseline fragment + runtime from ``default/``.

    When ``dns_domain_suffix`` is set, rewrites that key in every Leaf DNS overlay
    (ADR 003 Phase 2 — typically ``atlas-*.yml``). ``cluster_domain`` stack prefixes
    are template-owned and are never rewritten here.
    """
    opts = options or InitOptions()
    validate_init_cluster_id(cluster_id)
    target = init_cluster_target_dir(root, cluster_id)

    if target.exists():
        if not opts.force:
            raise ClusterctlError(
                f"cluster already exists: {target} (use --force to replace)"
            )
        shutil.rmtree(target)

    source = _resolve_copy_source(root, opts)
    target.parent.mkdir(parents=True, exist_ok=True)

    if config_dir_is_usable(source):
        shutil.copytree(source, target, ignore=_COPY_IGNORE)
    else:
        target.mkdir(parents=True)
        src_cfg = source / CLUSTER_CONFIG_NAME
        if src_cfg.is_file():
            shutil.copy2(src_cfg, target / CLUSTER_CONFIG_NAME)
        runtime_source = _fallback_runtime_source(root, source)
        if runtime_source is None:
            raise ClusterctlError(
                f"source clusters/{opts.from_id}/ has no cluster.yaml scaffold and "
                "no runtime files — use --from default or --template"
            )
        _copy_runtime_files(runtime_source, target)

    _ensure_group_vars_from_org_baseline(root, target)

    _patch_cluster_yaml(
        target / CLUSTER_CONFIG_NAME,
        cluster_id,
        display_name=opts.display_name,
    )
    # ADR 003 Phase 2: patch product overlays (and legacy cluster.yml only if it
    # still declares DNS keys). Never create cluster.yml here.
    suffix = (opts.dns_domain_suffix or "").strip() or None
    try:
        patch_leaf_dns_identity(
            target,
            cluster_id,
            dns_domain_suffix=suffix,
        )
        if suffix is not None:
            _require_dns_suffix_applied(target, suffix)
        if opts.validate:
            _run_post_init_validate(root, canonical_cluster_id(cluster_id))
    except ClusterctlError:
        if target.exists():
            shutil.rmtree(target)
        raise

    return target


def _require_dns_suffix_applied(config_dir: Path, suffix: str) -> None:
    """Fail hard when ``--dns-suffix`` could not land in any Leaf DNS overlay."""
    matched = overlays_with_dns_suffix_value(config_dir, suffix)
    if matched:
        return
    overlays = discover_leaf_dns_overlays(config_dir)
    if not overlays:
        raise ClusterctlError(
            f"--dns-suffix {suffix!r}: no Leaf DNS overlays under "
            f"{config_dir}/group_vars/all "
            "(need atlas-*.yml with dns_domain_suffix / # Leaf DNS identity)"
        )
    names = ", ".join(path.name for path in overlays)
    raise ClusterctlError(
        f"--dns-suffix {suffix!r}: no overlay declares dns_domain_suffix "
        f"(Leaf DNS files without that key: {names})"
    )


def resolve_existing_cluster_dir(root: Path, cluster_id: str) -> Path:
    """Public helper: resolve config dir for init/validate tooling."""
    from clusterctl.paths import clusters_root as resolve_clusters_root

    return discover_config_dir(resolve_clusters_root(root), cluster_id)
