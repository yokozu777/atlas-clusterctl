"""Leaf DNS identity helpers for init / export (ADR 003 Phase 2).

Deployable leaves declare DNS in product ``atlas-*.yml`` overlays under a
``# Leaf DNS identity`` block (duplicated per consumer). ``cluster.yml`` is
optional legacy and must not be the SoT for these keys.

``./cluster init --dns-suffix`` rewrites only ``dns_domain_suffix``. Stack
prefixes in ``cluster_domain`` (e.g. ``redis.{{ dns_domain_suffix }}``) stay
template-owned — edit the overlay YAML to change them.
"""

from __future__ import annotations

from pathlib import Path

from clusterctl.cluster_layout import canonical_cluster_id
from clusterctl.cluster_vars_loader import (
    PRIMARY_CLUSTER_VAR,
    discover_group_vars_all,
    group_vars_all_dir,
    is_secrets_overlay,
)

# Marker used in public templates / inventory overlays.
LEAF_DNS_MARKER = "# Leaf DNS identity"

# Top-level keys that mark a file as Leaf DNS identity (discovery).
# Only ``dns_domain_suffix`` is rewritten by ``./cluster init --dns-suffix``.
# ``k8s_cluster_domain`` is left alone (normally ``"{{ cluster_domain }}"``).
_LEAF_DNS_IDENTITY_KEYS = frozenset({"dns_domain_suffix", "cluster_domain"})

# Public-template placeholder written by export scrub.
PUBLIC_DNS_DOMAIN_SUFFIX = "example.com"


def _top_level_key(line: str) -> str | None:
    """Return mapping key when *line* is a top-level (indent 0) YAML key line."""
    if not line or line[0] in " \t#":
        return None
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if ":" not in stripped:
        return None
    key = stripped.split(":", 1)[0].strip()
    return key or None


def _top_level_scalar_value(line: str) -> str | None:
    """Return unquoted scalar for a top-level ``key: value`` line, else None."""
    if _top_level_key(line) is None:
        return None
    _, _, rest = line.partition(":")
    value = rest.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def file_has_leaf_dns_identity(path: Path) -> bool:
    """True when *path* carries a Leaf DNS identity block or top-level DNS keys."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if LEAF_DNS_MARKER in text:
        return True
    for line in text.splitlines():
        if _top_level_key(line) in _LEAF_DNS_IDENTITY_KEYS:
            return True
    return False


def discover_leaf_dns_overlays(config_dir: Path) -> tuple[Path, ...]:
    """Return ``group_vars/all`` files that declare Leaf DNS identity.

    Includes product ``atlas-*.yml`` (marker / keys) and legacy ``cluster.yml``
    when it still holds top-level DNS keys (fixtures / pre-Phase-3 sources).
    Secrets overlays are never patched.
    """
    found: list[Path] = []
    for path in discover_group_vars_all(config_dir):
        if is_secrets_overlay(path.name):
            continue
        if file_has_leaf_dns_identity(path):
            found.append(path)
    return tuple(found)


def overlays_with_dns_suffix_value(
    config_dir: Path,
    suffix: str,
) -> tuple[Path, ...]:
    """Leaf DNS overlays whose top-level ``dns_domain_suffix`` equals *suffix*."""
    want = (suffix or "").strip()
    if not want:
        return ()
    matched: list[Path] = []
    for path in discover_leaf_dns_overlays(config_dir):
        for line in path.read_text(encoding="utf-8").splitlines():
            if _top_level_key(line) != "dns_domain_suffix":
                continue
            if (_top_level_scalar_value(line) or "").strip() == want:
                matched.append(path)
            break
    return tuple(matched)


def _public_cluster_domain_replacement(raw_value: str) -> str | None:
    """Return replacement line for a literal ``cluster_domain``, or None to keep.

    Jinja values (contain ``{{``) are left intact. Literals become
    ``"<first-label>.{{ dns_domain_suffix }}"`` so live FQDNs do not land in
    public templates.
    """
    value = (raw_value or "").strip()
    if not value or "{{" in value:
        return None
    prefix = value.split(".", 1)[0].strip() or "k8s"
    return f'cluster_domain: "{prefix}.{{{{ dns_domain_suffix }}}}"\n'


def patch_group_vars_identity_lines(
    path: Path,
    *,
    cluster_id: str | None = None,
    dns_domain_suffix: str | None = None,
    scrub_literal_cluster_domain: bool = False,
) -> bool:
    """Rewrite top-level identity keys in *path*. Returns True if content changed.

    - ``cluster_id`` (legacy) → canonical id when *cluster_id* is provided
    - ``dns_domain_suffix`` → when *dns_domain_suffix* is a non-empty string
    - ``cluster_domain`` → Jinja form when *scrub_literal_cluster_domain* and value
      is a literal FQDN (export hygiene only; init never sets this flag)
    """
    if not path.is_file():
        return False

    canonical = canonical_cluster_id(cluster_id) if cluster_id else None
    suffix = (dns_domain_suffix or "").strip() or None
    if canonical is None and suffix is None and not scrub_literal_cluster_domain:
        return False

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    patched: list[str] = []
    changed = False
    for line in lines:
        key = _top_level_key(line.rstrip("\n"))
        if key == "cluster_id" and canonical is not None:
            replacement = f"cluster_id: {canonical}\n"
            patched.append(replacement)
            changed = changed or line != replacement
        elif key == "dns_domain_suffix" and suffix is not None:
            replacement = f"dns_domain_suffix: {suffix}\n"
            patched.append(replacement)
            changed = changed or line != replacement
        elif key == "cluster_domain" and scrub_literal_cluster_domain:
            raw = _top_level_scalar_value(line.rstrip("\n"))
            replacement = _public_cluster_domain_replacement(raw or "")
            if replacement is None:
                patched.append(line if line.endswith("\n") else f"{line}\n")
            else:
                patched.append(replacement)
                changed = changed or line != replacement
        else:
            patched.append(line if line.endswith("\n") else f"{line}\n")

    if changed:
        path.write_text("".join(patched), encoding="utf-8")
    return changed


def patch_leaf_dns_identity(
    config_dir: Path,
    cluster_id: str,
    *,
    dns_domain_suffix: str | None = None,
) -> tuple[Path, ...]:
    """Patch every Leaf DNS overlay under *config_dir*. Returns written paths."""
    written: list[Path] = []
    for path in discover_leaf_dns_overlays(config_dir):
        if patch_group_vars_identity_lines(
            path,
            cluster_id=cluster_id,
            dns_domain_suffix=dns_domain_suffix,
        ):
            written.append(path)
    return tuple(written)


def scrub_leaf_dns_suffix_for_public_template(
    config_dir: Path,
    *,
    public_suffix: str = PUBLIC_DNS_DOMAIN_SUFFIX,
) -> tuple[Path, ...]:
    """Normalize Leaf DNS for public templates.

    - ``dns_domain_suffix`` → *public_suffix* (default ``example.com``)
    - literal ``cluster_domain`` FQDNs → ``"<prefix>.{{ dns_domain_suffix }}"``
    - Jinja ``cluster_domain`` values are left intact
    """
    written: list[Path] = []
    for path in discover_leaf_dns_overlays(config_dir):
        if patch_group_vars_identity_lines(
            path,
            dns_domain_suffix=public_suffix,
            scrub_literal_cluster_domain=True,
        ):
            written.append(path)
    return tuple(written)


def remove_legacy_cluster_yml(config_dir: Path) -> bool:
    """Delete ``group_vars/all/cluster.yml`` when present (ADR 003 Phase 3+).

    Public templates and inventory labs omit this file. Export uses this after
    scrubbing Leaf DNS into ``atlas-*.yml``. Returns True when a file was removed.
    """
    path = group_vars_all_dir(config_dir) / PRIMARY_CLUSTER_VAR
    if not path.is_file():
        return False
    path.unlink()
    return True
