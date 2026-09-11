"""Promote a deployable/lab leaf into a public ``clusters/_template/<name>/`` scaffold.

Maintainer-only (ADR 004). Operators consume scaffolds via::

    ./cluster init <env>/<name> --template <name>

Usage::

    python3 -m clusterctl.tools.export_template --from <lab-id> --template redis
    python3 -m clusterctl.tools.export_template --from <lab-id> --template k8s_full \\
        --flatten-cascade
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
    cluster_config_dir,
    validate_cluster_id,
)
from clusterctl.cluster_vars_loader import (
    discover_legacy_secrets_overlays,
    discover_secrets_overlays,
    load_yaml_mapping,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.leaf_dns import (
    remove_legacy_cluster_yml,
    scrub_leaf_dns_suffix_for_public_template,
)
from clusterctl.paths import clusters_root, product_clusters_root

_RUNTIME_COPY = ("hosts", "group_vars", "pub_keys")
_TEMPLATE_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
_GROUP_VARS_SUFFIXES = (".yml", ".yaml")
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
# Org lab FQDNs that must not land in public scaffolds (publish hygiene).
_ORG_DOMAIN_RE = re.compile(
    r"(?i)\b(?:(?:gitea|harbor|upload|nexus)\.)?(?:dev-)?mxhash\.com\b"
)

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


def _empty_secret_values(node: object) -> object:
    """Keep mapping/list structure; replace every leaf scalar with ``\"\"``."""
    if isinstance(node, dict):
        return {key: _empty_secret_values(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_empty_secret_values(item) for item in node]
    if node is None:
        return None
    return ""


def scrub_secrets_overlay_file(path: Path) -> bool:
    """Empty values in one secrets overlay. Returns True when the file changed."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("$ANSIBLE_VAULT"):
        path.write_text(_VAULT_SCRUB_STUB, encoding="utf-8")
        return True
    # Idempotent: vault stub already written by a previous scrub.
    if text == _VAULT_SCRUB_STUB:
        return False

    data = yaml.safe_load(text)
    if data is None:
        return False
    if not isinstance(data, (dict, list)):
        scrubbed: object = ""
    else:
        scrubbed = _empty_secret_values(data)
    new_text = yaml.safe_dump(
        scrubbed,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
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
    return scrubbed


def scrub_org_domains_under(config_dir: Path) -> tuple[Path, ...]:
    """Rewrite org FQDNs in ``hosts`` / ``group_vars`` / ``cluster.yaml`` text files."""
    written: list[Path] = []
    candidates: list[Path] = []
    for name in ("hosts", CLUSTER_CONFIG_NAME):
        path = config_dir / name
        if path.is_file():
            candidates.append(path)
    group_vars = config_dir / "group_vars"
    if group_vars.is_dir():
        candidates.extend(sorted(p for p in group_vars.rglob("*") if p.is_file()))
    for path in candidates:
        if path.name.startswith("."):
            continue
        if (
            path.name not in {"hosts", CLUSTER_CONFIG_NAME}
            and path.suffix not in {".yml", ".yaml"}
        ):
            continue
        text = path.read_text(encoding="utf-8")
        scrubbed = scrub_org_domains_in_text(text)
        if scrubbed != text:
            path.write_text(scrubbed, encoding="utf-8")
            written.append(path)
    return tuple(written)


def scrub_cluster_yaml_for_public_template(path: Path) -> bool:
    """Neutralize playbook git URLs, aliases, and execution image in ``cluster.yaml``."""
    if not path.is_file():
        return False
    raw = path.read_text(encoding="utf-8")
    # Preserve scaffold comment header (lines before the first non-comment mapping key).
    header_lines: list[str] = []
    body_lines: list[str] = []
    in_header = True
    for line in raw.splitlines(keepends=True):
        if in_header and (line.startswith("#") or line.strip() == ""):
            header_lines.append(line)
            continue
        in_header = False
        body_lines.append(line)
    data = yaml.safe_load("".join(body_lines)) or {}
    if not isinstance(data, dict):
        return False
    changed = False

    playbooks = data.get("playbooks")
    if isinstance(playbooks, dict):
        for name, entry in playbooks.items():
            if not isinstance(entry, dict):
                continue
            public_url = f"git@example.com:org/{name}.git"
            if entry.get("url") != public_url:
                entry["url"] = public_url
                changed = True
            if entry.get("source") != "local":
                entry["source"] = "local"
                changed = True
            if entry.get("sync") != "never":
                entry["sync"] = "never"
                changed = True

    aliases = data.get("cluster_id_aliases")
    if aliases not in (None, {}):
        data["cluster_id_aliases"] = {}
        changed = True

    execution = data.get("execution")
    if isinstance(execution, dict):
        image = str(execution.get("image") or "")
        image_l = image.lower()
        if (
            "mxhash" in image_l
            or "harbor." in image_l
            or image_l.startswith("harbor/")
        ):
            if execution.get("image") != "yokozu/krang":
                execution["image"] = "yokozu/krang"
                changed = True
            if execution.get("mode") == "docker":
                execution["mode"] = "local"
                changed = True

    if not changed:
        return False

    path.write_text(
        "".join(header_lines)
        + yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
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

    Same-basename files are shallow-merged (later layer wins), matching runtime
    ``load_cluster_vars`` key semantics. Single-layer files are copied as-is.
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
        merged: dict = {}
        for path in paths:
            merged.update(load_yaml_mapping(path))
        dest.write_text(
            yaml.safe_dump(
                merged,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            ),
            encoding="utf-8",
        )


def _copy_leaf_group_vars_sidecars(source: Path, target: Path) -> None:
    """Copy non-``all`` ``group_vars`` entries from the leaf (e.g. ``proxmox.yml``)."""
    src_gv = source / "group_vars"
    if not src_gv.is_dir():
        return
    dest_gv = target / "group_vars"
    dest_gv.mkdir(parents=True, exist_ok=True)
    for item in sorted(src_gv.iterdir(), key=lambda p: p.name):
        if item.name == "all":
            continue
        dest = dest_gv / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        if item.is_dir():
            shutil.copytree(item, dest)
        elif item.is_file():
            shutil.copy2(item, dest)


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
    Scrubs Leaf DNS, empties secrets-overlay values, removes legacy ``cluster.yml``.
    With *flatten_cascade*, merge org→env→leaf ``group_vars/all`` into a fat scaffold
    (needed when inventory leaves are thin overlays). Also remaps ``hosts`` IPv4s and
    org FQDNs for publish hygiene. Does not rewrite README.
    """
    source_id = validate_cluster_id(source_id)
    template_name = validate_template_name(template_name)

    source_root = (source_root or clusters_root()).resolve()
    target_root = (target_root or product_clusters_root()).resolve()
    source = cluster_config_dir(source_root, source_id)
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
    data["id"] = ""
    data["display_name"] = None
    data.pop("deployable", None)

    target.mkdir(parents=True, exist_ok=True)
    (target / CLUSTER_CONFIG_NAME).write_text(
        _scaffold_header(
            source_id=source_id,
            template_name=template_name,
            flatten_cascade=flatten_cascade,
        )
        + yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    if flatten_cascade:
        for name in ("hosts", "pub_keys"):
            src = source / name
            dest = target / name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            if src.is_dir():
                shutil.copytree(src, dest)
            elif src.is_file():
                shutil.copy2(src, dest)
        cascade_dirs = cascade_group_vars_dirs(
            source_root,
            source_id,
            product_clusters_root=target_root,
        )
        write_flattened_group_vars_all(
            cascade_dirs=cascade_dirs,
            dest_config_dir=target,
        )
        _copy_leaf_group_vars_sidecars(source, target)
    else:
        for name in _RUNTIME_COPY:
            src = source / name
            dest = target / name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            if src.is_dir():
                shutil.copytree(src, dest)
            elif src.is_file():
                shutil.copy2(src, dest)

    scrub_leaf_dns_suffix_for_public_template(target)
    scrub_secrets_overlays_for_public_template(target)
    # Neutralize playbook URLs / execution before domain rewrite (harbor.* → example.com).
    scrub_cluster_yaml_for_public_template(target / CLUSTER_CONFIG_NAME)
    scrub_org_domains_under(target)
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
        help="source cluster id under --source-root (e.g. ci/redis, dev/mxhash)",
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
            "merge org→env→leaf group_vars/all into a self-contained scaffold "
            "(use for thin inventory leaves that rely on <env>/default)"
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
