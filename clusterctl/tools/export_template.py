"""Promote a deployable/lab leaf into a public ``clusters/_template/<name>/`` scaffold.

Maintainer-only (ADR 004). Operators consume scaffolds via::

    ./cluster init <env>/<name> --template <name>

Usage::

    python3 -m clusterctl.tools.export_template --from <lab-id> --template redis
    python3 -m clusterctl.tools.export_template --from dev/default --template default
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML required") from exc

from clusterctl.cluster_layout import (
    CLUSTER_CONFIG_NAME,
    cascade_group_vars_dirs,
    validate_cluster_id,
)
from clusterctl.cluster_vars_loader import (
    discover_legacy_secrets_overlays,
    discover_secrets_overlays,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.leaf_dns import (
    remove_legacy_cluster_yml,
    scrub_leaf_dns_suffix_for_public_template,
)
from clusterctl.paths import clusters_root, product_clusters_root

_TEMPLATE_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
_GROUP_VARS_SUFFIXES = (".yml", ".yaml")
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
# Org lab FQDNs that must not land in public scaffolds (publish hygiene).
_ORG_DOMAIN_RE = re.compile(
    r"(?i)\b(?:(?:gitea|harbor|upload|nexus)\.)?(?:dev-)?mxhash\.com\b"
)
_TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z0-9_./-]+):(\s|$)")
_BLOCK_SCALAR_RE = re.compile(r"^[|>][+-]?(?:\s+#.*)?$")
_SECRET_KEY_RE = re.compile(r"^(\s*)([^:#\s][^:]*):\s*(.*)$")
_SECRET_LIST_RE = re.compile(r"^(\s*)-\s+(\S.*)$")
_COMMENTED_SECRET_ASSIGN_RE = re.compile(
    r"""^\s*#\s*[A-Za-z0-9_]+\s*:\s*["'].+["']\s*$"""
)
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_PLAYBOOK_NAME_RE = re.compile(r"^(\s{2})([a-zA-Z0-9._-]+):\s*$")
_INDENTED_KEY_RE = re.compile(r"^(\s+)([A-Za-z0-9_./-]+):\s*(.*)$")
# Leftover org token after FQDN rewrite (e.g. ``Mxhash Internal CA``).
_ORG_TOKEN_RE = re.compile(r"(?i)\bmxhash\b")

# Injected when a leaf overlay omits the public orchestration-doc pointer.
_OVERLAY_STACK_DOCS: dict[str, str] = {
    "atlas-k8s-addons.yml": "docs/stacks/k8s-addons.md",
    "atlas-k8s-core.yml": "docs/stacks/k8s-core.md",
    "atlas-compute-provision.yml": "docs/stacks/compute-provision.md",
    "atlas-infra-edge.yml": "docs/stacks/infra-edge.md",
    "atlas-jenkins-agent.yml": "docs/stacks/jenkins-agent.md",
    "atlas-gitlab-runner.yml": "docs/stacks/gitlab-runner.md",
    "atlas-postgresql.yml": "docs/stacks/postgresql.md",
    "atlas-redis.yml": "docs/stacks/redis.md",
    "atlas-kafka.yml": "docs/stacks/kafka.md",
}

_VAULT_SCRUB_STUB = (
    "# Ansible Vault payload removed by export_template (public scrub).\n"
    "# Re-declare keys with empty values, then Vault-encrypt if needed.\n"
    "{}\n"
)

# Documented public scaffolds (ADR 004). Not enforced — custom names allowed.
KNOWN_TEMPLATE_NAMES = (
    "k8s_full",
    "infra_edge",
    "jenkins_agent",
    "gitlab_runner",
    "postgresql",
    "redis",
    "kafka",
    "pve_templates",
    "default",
)

# Placeholder host IPs for public hosts inventory (RFC1918; hygiene allows examples).
_PUBLIC_HOST_IP_BASE = (192, 168, 1, 240)


def validate_template_name(template_name: str) -> str:
    """Return a sanitized template directory name under ``_template/``."""
    text = (template_name or "").strip()
    if not text:
        raise ValueError("template name must be non-empty")
    if "/" in text or text.startswith("_") or text in {".", ".."}:
        raise ValueError(
            f"invalid template name {template_name!r} — use a simple name "
            f"(e.g. redis, k8s_full), not a path"
        )
    if not _TEMPLATE_NAME.fullmatch(text):
        raise ValueError(
            f"invalid template name {template_name!r} — expected "
            r"^[a-z][a-z0-9_-]*$"
        )
    return text


def _ensure_newline(text: str) -> str:
    if not text or text.endswith("\n"):
        return text
    return text + "\n"


def _is_top_level_key_line(line: str) -> bool:
    if not line or line[0] in " \t#":
        return False
    stripped = line.strip()
    if stripped.startswith("---") or stripped.startswith("..."):
        return False
    match = _TOP_LEVEL_KEY_RE.match(stripped)
    return match is not None


def _top_level_key(line: str) -> str | None:
    if not _is_top_level_key_line(line):
        return None
    return line.strip().split(":", 1)[0]


def _next_significant_is_top_level_key(lines: Sequence[str], start: int) -> bool:
    for raw in lines[start:]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return _is_top_level_key_line(raw)
    return False


def split_top_level_yaml_blocks(text: str) -> tuple[str, list[str], dict[str, str]]:
    """Split mapping YAML into preamble + ordered top-level key blocks.

    Comment/blank lines immediately before a key travel with that key. Later
    layers can replace a key's entire block (including its comments).
    """
    lines = text.splitlines(keepends=True)
    preamble: list[str] = []
    order: list[str] = []
    blocks: dict[str, str] = {}
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped == "" or stripped.startswith("#") or not _is_top_level_key_line(raw):
            if _is_top_level_key_line(raw):
                break
            preamble.append(raw)
            i += 1
            continue
        break

    pending: list[str] = []
    current_key: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is None:
            return
        if current_key not in blocks:
            order.append(current_key)
        blocks[current_key] = "".join(current_lines)
        current_key = None
        current_lines = []

    while i < len(lines):
        raw = lines[i]
        if current_key is None:
            if _is_top_level_key_line(raw):
                current_key = _top_level_key(raw)
                assert current_key is not None
                current_lines = pending + [raw]
                pending = []
            else:
                pending.append(raw)
            i += 1
            continue
        if _is_top_level_key_line(raw):
            flush()
            current_key = _top_level_key(raw)
            assert current_key is not None
            current_lines = [raw]
            i += 1
            continue
        if not raw.strip() or raw.lstrip().startswith("#"):
            if _next_significant_is_top_level_key(lines, i + 1):
                flush()
                pending = [raw]
                current_key = None
                i += 1
                continue
        current_lines.append(raw)
        i += 1
    flush()
    if pending:
        if order:
            blocks[order[-1]] += "".join(pending)
        else:
            preamble.extend(pending)
    return "".join(preamble), order, blocks


def merge_top_level_yaml_layers(texts: Sequence[str]) -> str:
    """Shallow-merge mapping YAML layers (later wins per top-level key)."""
    preamble = ""
    order: list[str] = []
    blocks: dict[str, str] = {}
    for text in texts:
        pre, keys, mapping = split_top_level_yaml_blocks(text)
        if pre.strip():
            # Later layer (leaf) preamble wins so stack docs comments are kept.
            preamble = pre
        for key in keys:
            if key not in blocks:
                order.append(key)
            blocks[key] = mapping[key]
    parts: list[str] = []
    if preamble:
        parts.append(_ensure_newline(preamble) if preamble.strip() else preamble)
    for key in order:
        parts.append(_ensure_newline(blocks[key]))
    return "".join(parts)


def _empty_secret_scalar_line(line: str) -> tuple[str, int | None]:
    """Empty a scalar/list-item line. Second value is indent to skip in a block scalar."""
    ended = line.endswith("\n")
    raw = line.rstrip("\n")
    stripped = raw.strip()
    if stripped.startswith("#") and _COMMENTED_SECRET_ASSIGN_RE.match(raw):
        return "", None
    if not stripped or stripped.startswith("#"):
        return line, None

    list_match = _SECRET_LIST_RE.match(raw)
    if list_match:
        indent, rest = list_match.group(1), list_match.group(2).strip()
        if _BLOCK_SCALAR_RE.match(rest):
            return f"{indent}- ''\n", len(indent)
        if rest.startswith("{"):
            return f"{indent}- {{}}\n", None
        if rest.startswith("["):
            return f"{indent}- []\n", None
        return f"{indent}- ''\n", None

    key_match = _SECRET_KEY_RE.match(raw)
    if not key_match:
        return line, None
    indent, key, value = key_match.group(1), key_match.group(2), key_match.group(3)
    value = value.split(" #", 1)[0].strip()
    if not value:
        return (_ensure_newline(line) if ended else line), None
    if _BLOCK_SCALAR_RE.match(value):
        return f"{indent}{key}: ''\n", len(indent)
    if value.startswith("[") and value != "[]":
        return f"{indent}{key}: []\n", None
    if value.startswith("{") and value != "{}":
        return f"{indent}{key}: {{}}\n", None
    if value in {"{}", "[]"}:
        return (_ensure_newline(line) if ended else line), None
    return f"{indent}{key}: ''\n", None


def scrub_secrets_overlay_file(path: Path) -> bool:
    """Empty values in one secrets overlay. Returns True when the file changed."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("$ANSIBLE_VAULT"):
        path.write_text(_VAULT_SCRUB_STUB, encoding="utf-8")
        return True
    if text == _VAULT_SCRUB_STUB:
        return False

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skip_deeper_than: int | None = None
    for line in lines:
        if skip_deeper_than is not None:
            if not line.strip():
                out.append(line)
                continue
            leading = len(line) - len(line.lstrip(" "))
            if leading > skip_deeper_than and not line.lstrip().startswith("#"):
                continue
            skip_deeper_than = None
        rebuilt, skip_indent = _empty_secret_scalar_line(line)
        if skip_indent is not None:
            skip_deeper_than = skip_indent
        if rebuilt == "":
            continue
        out.append(rebuilt)
    new_text = "".join(out)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def scrub_secrets_overlays_for_public_template(config_dir: Path) -> tuple[Path, ...]:
    """Empty values in product + legacy secrets overlays (never ship live secrets).

    Legacy ``secrets.yml`` is not merged at runtime (soft-compat Phase 4) but may
    still exist on a lab leaf during export — scrub it so public scaffolds cannot
    leak credentials.
    """
    written: list[Path] = []
    for path in (
        *discover_secrets_overlays(config_dir),
        *discover_legacy_secrets_overlays(config_dir),
    ):
        if scrub_secrets_overlay_file(path):
            written.append(path)
    return tuple(written)


def scrub_org_domains_in_text(text: str) -> str:
    """Replace known org lab FQDNs / path fingerprints with public placeholders."""
    scrubbed = _ORG_DOMAIN_RE.sub("example.com", text)
    # Split path so this source file does not itself trip publish hygiene.
    scrubbed = scrubbed.replace("/var/lib/" + "mxhash", "/var/lib/atlas-infra")
    scrubbed = scrubbed.replace("ca-" + "mxhash" + "-com.crt", "ca-example-com.crt")
    scrubbed = scrubbed.replace(
        "k8s_ca_cert_filename: " + "mxhash" + ".crt",
        "k8s_ca_cert_filename: example.crt",
    )
    scrubbed = re.sub(
        r"(?m)^(keycloak_realm:\s*)" + "mxhash" + r"\s*$",
        r"\1example",
        scrubbed,
    )
    scrubbed = scrubbed.replace("dev/" + "mxhash", "dev/k8s")
    scrubbed = re.sub(
        r"(?i)\bmxhash internal ca\b",
        "Example Internal CA",
        scrubbed,
    )
    return _ORG_TOKEN_RE.sub("example", scrubbed)


def scrub_cyrillic_in_text(text: str) -> str:
    """Drop Cyrillic from public YAML (comment lines / trailing comments)."""
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        ended = line.endswith("\n")
        raw = line.rstrip("\n")
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            if _CYRILLIC_RE.search(raw):
                continue
            out.append(line)
            continue
        if _CYRILLIC_RE.search(raw):
            code, sep, comment = raw.partition(" #")
            if sep and _CYRILLIC_RE.search(comment):
                rebuilt = code.rstrip()
                out.append(rebuilt + ("\n" if ended else ""))
                continue
            if _CYRILLIC_RE.search(raw):
                continue
        out.append(line)
    return "".join(out)


def scrub_readme_for_public_template(text: str) -> str:
    """Drop local-only inventory banners from a copied leaf README."""
    scrubbed = scrub_org_domains_in_text(text)
    # Inventory READMEs often start with a gitignored lab callout (no DOTALL:
    # ``.`` must not swallow the rest of the file).
    scrubbed = re.sub(
        r"(?im)^>\s*\*\*Local-only lab\*\*[^\n]*\n(?:>[^\n]*\n)*\n*",
        "",
        scrubbed,
        count=1,
    )
    scrubbed = scrubbed.replace("gitignored", "private inventory")
    return scrubbed


def scrub_org_domains_under(config_dir: Path) -> tuple[Path, ...]:
    """Rewrite org FQDNs in ``hosts`` / ``group_vars`` / ``cluster.yaml`` / README."""
    written: list[Path] = []
    candidates: list[Path] = []
    if config_dir.is_dir():
        for path in sorted(config_dir.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.suffix in {".pub", ".key"}:
                continue
            if path.suffix in {".yml", ".yaml", ".md", ".txt"} or path.name in {
                "hosts",
                CLUSTER_CONFIG_NAME,
            }:
                candidates.append(path)
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if path.name.lower() == "readme.md" or path.suffix == ".md":
            scrubbed = scrub_readme_for_public_template(text)
        else:
            scrubbed = scrub_org_domains_in_text(text)
            if path.suffix in {".yml", ".yaml"}:
                scrubbed = scrub_cyrillic_in_text(scrubbed)
        if scrubbed != text:
            path.write_text(scrubbed, encoding="utf-8")
            written.append(path)
    return tuple(written)


def _patch_cluster_yaml_identity(text: str) -> str:
    """Set public ``id`` / ``display_name`` and drop ``deployable`` without dumping."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    seen_id = False
    seen_display = False
    i = 0
    while i < len(lines):
        line = lines[i]
        key = _top_level_key(line)
        if key == "id":
            out.append("id: ''\n")
            seen_id = True
            i += 1
            continue
        if key == "display_name":
            out.append("display_name: null\n")
            seen_display = True
            i += 1
            continue
        if key == "deployable":
            i = _skip_top_level_block(lines, i)
            continue
        out.append(line if line.endswith("\n") else f"{line}\n")
        i += 1
    patched = "".join(out)
    if not seen_id:
        patched = "id: ''\n" + patched
    if not seen_display:
        patched = patched.replace("id: ''\n", "id: ''\ndisplay_name: null\n", 1)
    return patched


def _skip_top_level_block(lines: list[str], start: int) -> int:
    """Index of the next top-level key after the block that starts at *start*."""
    i = start + 1
    while i < len(lines):
        if _is_top_level_key_line(lines[i]):
            return i
        i += 1
    return i


def scrub_cluster_yaml_for_public_template(path: Path) -> bool:
    """Neutralize playbook git URLs, aliases, and execution image in ``cluster.yaml``."""
    if not path.is_file():
        return False
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    out: list[str] = []
    in_playbooks = False
    in_execution = False
    playbook_name: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        key = _top_level_key(line)
        if key == "playbooks":
            in_playbooks = True
            in_execution = False
            playbook_name = None
            out.append(line if line.endswith("\n") else f"{line}\n")
            i += 1
            continue
        if key == "execution":
            in_playbooks = False
            in_execution = True
            playbook_name = None
            out.append(line if line.endswith("\n") else f"{line}\n")
            i += 1
            continue
        if key == "cluster_id_aliases":
            in_playbooks = False
            in_execution = False
            playbook_name = None
            rest = line.split(":", 1)[1].strip()
            if rest in {"{}", ""}:
                out.append("cluster_id_aliases: {}\n")
                if rest == "":
                    i = _skip_top_level_block(lines, i)
                    continue
                i += 1
                continue
            out.append("cluster_id_aliases: {}\n")
            i = _skip_top_level_block(lines, i)
            continue
        if key is not None:
            in_playbooks = False
            in_execution = False
            playbook_name = None

        if in_playbooks:
            name_match = _PLAYBOOK_NAME_RE.match(line.rstrip("\n"))
            if name_match:
                playbook_name = name_match.group(2)
                out.append(line if line.endswith("\n") else f"{line}\n")
                i += 1
                continue
            indented = _INDENTED_KEY_RE.match(line.rstrip("\n"))
            if indented and playbook_name:
                indent, field, _value = indented.group(1), indented.group(2), indented.group(3)
                if field == "url":
                    out.append(
                        f"{indent}url: git@github.com:yokozu777/{playbook_name}.git\n"
                    )
                    i += 1
                    continue

        if in_execution:
            indented = _INDENTED_KEY_RE.match(line.rstrip("\n"))
            if indented:
                indent, field, value = indented.group(1), indented.group(2), indented.group(3)
                image_l = value.lower()
                if field == "image" and (
                    "mxhash" in image_l
                    or "harbor." in image_l
                    or image_l.strip("\"'").startswith("harbor/")
                    or image_l.strip("\"'") != "yokozu/krang"
                ):
                    out.append(f"{indent}image: yokozu/krang\n")
                    i += 1
                    continue
                if field == "mode" and value.strip().strip("'\"") != "docker":
                    out.append(f"{indent}mode: docker\n")
                    i += 1
                    continue
                if field == "tag" and value.strip().strip("'\"") != "latest":
                    out.append(f"{indent}tag: latest\n")
                    i += 1
                    continue

        out.append(line if line.endswith("\n") else f"{line}\n")
        i += 1

    new_text = "".join(out)
    if new_text == raw:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def _placeholder_ipv4(index: int) -> str:
    a, b, c, d0 = _PUBLIC_HOST_IP_BASE
    d = d0 + index
    if d > 254:
        raise ValueError(
            f"too many host IPs to remap into {_PUBLIC_HOST_IP_BASE[:-1]}.*"
        )
    return f"{a}.{b}.{c}.{d}"


def scrub_public_literals_under_group_vars(config_dir: Path) -> tuple[Path, ...]:
    """Replace recurring lab literals in ``group_vars`` (org git paths, infra IP)."""
    group_vars = config_dir / "group_vars"
    if not group_vars.is_dir():
        return ()
    written: list[Path] = []
    for path in sorted(group_vars.rglob("*")):
        if not path.is_file() or path.suffix not in {".yml", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8")
        scrubbed = (
            text.replace(":root/", ":org/")
            .replace("192.168.1.219", "192.168.1.53")
        )
        scrubbed = re.sub(
            r'(?m)^(redis_download_github_proxy:\s*)(?!\'\'|"").+$',
            r"\1''",
            scrubbed,
        )
        scrubbed = re.sub(
            r'(?m)^(redis_download_mirror_url:\s*)"https?://example\.com/[^"]*"\s*$',
            r"\1''",
            scrubbed,
        )
        scrubbed = re.sub(
            r'(?m)^(vip_address:\s*)"192\.168\.1\.130"\s*$',
            r'\1"192.168.1.250"',
            scrubbed,
        )
        if scrubbed != text:
            path.write_text(scrubbed, encoding="utf-8")
            written.append(path)
    return tuple(written)


def scrub_hosts_inventory_ips(path: Path) -> bool:
    """Remap distinct IPv4 literals in ``hosts`` to sequential public placeholders."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    seen: list[str] = []
    for match in _IPV4_RE.findall(text):
        if match not in seen:
            seen.append(match)
    if not seen:
        return False
    mapping = {ip: _placeholder_ipv4(i) for i, ip in enumerate(seen)}

    def _replace(match: re.Match[str]) -> str:
        return mapping[match.group(0)]

    new_text = _IPV4_RE.sub(_replace, text)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def _is_group_vars_all_candidate(path: Path) -> bool:
    if not path.is_file() or path.name.startswith("."):
        return False
    if path.name.endswith(".example"):
        return False
    return path.name.endswith(_GROUP_VARS_SUFFIXES)


def write_flattened_group_vars_all(
    *,
    cascade_dirs: Sequence[Path],
    dest_config_dir: Path,
) -> None:
    """Merge org→env→leaf ``group_vars/all`` into one self-contained ``all/``.

    Same-basename files are shallow-merged by top-level YAML blocks (later layer
    wins), matching runtime ``load_cluster_vars`` key semantics. Single-layer
    files are copied as-is so comments stay intact.
    """
    by_name: dict[str, list[Path]] = {}
    for all_dir in cascade_dirs:
        layer = Path(all_dir)
        if not layer.is_dir():
            continue
        for path in sorted(layer.iterdir(), key=lambda p: p.name):
            if not _is_group_vars_all_candidate(path):
                continue
            by_name.setdefault(path.name, []).append(path.resolve())

    dest_all = dest_config_dir / "group_vars" / "all"
    if dest_all.exists():
        shutil.rmtree(dest_all)
    dest_all.mkdir(parents=True, exist_ok=True)

    for name, paths in sorted(by_name.items()):
        dest = dest_all / name
        if len(paths) == 1:
            shutil.copy2(paths[0], dest)
            continue
        texts = [path.read_text(encoding="utf-8") for path in paths]
        dest.write_text(merge_top_level_yaml_layers(texts), encoding="utf-8")


def _copy_leaf_tree(source: Path, target: Path) -> None:
    """Copy every leaf file except ``cluster.yaml``. Keep an existing README."""
    keep_readme: str | None = None
    dest_readme = target / "README.md"
    if dest_readme.is_file():
        existing = dest_readme.read_text(encoding="utf-8")
        if existing.strip():
            keep_readme = existing

    for item in sorted(source.iterdir(), key=lambda p: p.name):
        if item.name in {".", "..", ".git"}:
            continue
        if item.name == CLUSTER_CONFIG_NAME:
            continue
        dest = target / item.name
        if item.name == "README.md" and keep_readme is not None:
            continue
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        if item.is_dir():
            shutil.copytree(item, dest)
        elif item.is_file():
            shutil.copy2(item, dest)

    if keep_readme is not None:
        dest_readme.write_text(keep_readme, encoding="utf-8")


def ensure_overlay_stack_docs_comments(config_dir: Path) -> tuple[Path, ...]:
    """Add ``docs/stacks/*.md`` pointers when a product overlay has none."""
    all_dir = config_dir / "group_vars" / "all"
    if not all_dir.is_dir():
        return ()
    written: list[Path] = []
    for name, docs in _OVERLAY_STACK_DOCS.items():
        path = all_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if docs in text:
            continue
        comment = f"# Orchestration contract: {docs}\n"
        lines = text.splitlines(keepends=True)
        insert_at = 0
        while insert_at < len(lines) and (
            not lines[insert_at].strip() or lines[insert_at].lstrip().startswith("#")
        ):
            insert_at += 1
        new_text = "".join(lines[:insert_at]) + comment + "".join(lines[insert_at:])
        path.write_text(new_text, encoding="utf-8")
        written.append(path)
    return tuple(written)


def _scaffold_header(*, source_id: str, template_name: str, flatten_cascade: bool) -> str:
    flatten_note = " --flatten-cascade" if flatten_cascade else ""
    return (
        f"# Public scaffold ``_template/{template_name}`` "
        f"(exported from ``{source_id}``).\n"
        f"# Regenerate: python3 -m clusterctl.tools.export_template "
        f"--from {source_id} --template {template_name}{flatten_note}\n"
        f"# Init: ./cluster init <env>/<name> --template {template_name}\n"
        "#\n"
        "# Scrub live hostnames / secrets before committing the public template.\n"
        "\n"
    )


def export_template(
    *,
    source_id: str,
    template_name: str,
    source_root: Path | None = None,
    target_root: Path | None = None,
    flatten_cascade: bool = False,
) -> Path:
    """Copy *source_id* from *source_root* into ``_template/<template_name>``.

    Defaults: inventory ``clusters_root()`` → product ``product_clusters_root()``.
    Copies the full leaf tree (not only hosts/group_vars/pub_keys). Scrubs Leaf
    DNS, empties secrets-overlay values, removes legacy ``cluster.yml``.
    With *flatten_cascade*, merge org→env→leaf ``group_vars/all`` into a fat
    scaffold (needed when inventory leaves are thin overlays). Also remaps
    ``hosts`` IPv4s and org FQDNs for publish hygiene. Does not overwrite an
    existing public README.
    """
    source_id = validate_cluster_id(source_id, allow_policy_ids=True)
    template_name = validate_template_name(template_name)

    source_root = (source_root or clusters_root()).resolve()
    target_root = (target_root or product_clusters_root()).resolve()
    source = source_root.joinpath(*source_id.split("/"))
    target = target_root / "_template" / template_name
    source_cfg = source / CLUSTER_CONFIG_NAME

    if not source_cfg.is_file():
        raise FileNotFoundError(
            f"{source_cfg} (source_root={source_root}; "
            "set ATLAS_CLUSTERS_ROOT / clusters.path, or pass --source-root)"
        )

    data = yaml.safe_load(source_cfg.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {source_cfg}")

    target.mkdir(parents=True, exist_ok=True)
    body = _patch_cluster_yaml_identity(source_cfg.read_text(encoding="utf-8"))
    (target / CLUSTER_CONFIG_NAME).write_text(
        _scaffold_header(
            source_id=source_id,
            template_name=template_name,
            flatten_cascade=flatten_cascade,
        )
        + body,
        encoding="utf-8",
    )

    _copy_leaf_tree(source, target)
    if flatten_cascade:
        cascade_dirs = cascade_group_vars_dirs(
            source_root,
            source_id,
            product_clusters_root=target_root,
        )
        write_flattened_group_vars_all(
            cascade_dirs=cascade_dirs,
            dest_config_dir=target,
        )

    scrub_leaf_dns_suffix_for_public_template(target)
    scrub_secrets_overlays_for_public_template(target)
    # Neutralize playbook URLs / execution before domain rewrite (harbor.* → example.com).
    scrub_cluster_yaml_for_public_template(target / CLUSTER_CONFIG_NAME)
    scrub_org_domains_under(target)
    ensure_overlay_stack_docs_comments(target)
    if flatten_cascade:
        scrub_public_literals_under_group_vars(target)
        hosts_path = target / "hosts"
        if hosts_path.is_file():
            scrub_hosts_inventory_ips(hosts_path)
    remove_legacy_cluster_yml(target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Promote a lab/deployable leaf into clusters/_template/<name> "
            "(maintainer-only; ADR 004)."
        )
    )
    parser.add_argument(
        "--from",
        dest="source_id",
        required=True,
        metavar="ID",
        help="source cluster id under --source-root (e.g. ci/redis, dev/k8s)",
    )
    parser.add_argument(
        "--template",
        dest="template_name",
        required=True,
        metavar="NAME",
        help=(
            "destination scaffold under _template/ "
            f"(e.g. {', '.join(KNOWN_TEMPLATE_NAMES)})"
        ),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="inventory clusters/ containing the source leaf "
        "(default: ATLAS_CLUSTERS_ROOT / clusters.path / product clusters/)",
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=None,
        help="product clusters/ that receives _template/<name> "
        "(default: $ATLAS_CLUSTER_ROOT/clusters)",
    )
    parser.add_argument(
        "--flatten-cascade",
        action="store_true",
        help=(
            "merge org→env→leaf group_vars/all into a self-contained scaffold. "
            "Omit for public stack scaffolds: env knobs live on _template/default"
        ),
    )
    args = parser.parse_args(argv)

    try:
        target = export_template(
            source_id=args.source_id,
            template_name=args.template_name,
            source_root=args.source_root,
            target_root=args.target_root,
            flatten_cascade=args.flatten_cascade,
        )
    except (FileNotFoundError, ValueError, ClusterctlError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    resolved_target = (args.target_root or product_clusters_root()).resolve()
    try:
        print(f"OK: {target.relative_to(resolved_target)}")
    except ValueError:
        print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
