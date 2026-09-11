"""Shell-friendly ansible env export (eval "$(python3 -m clusterctl.ansible_env export provision)")."""

from __future__ import annotations

import argparse
import os
import shlex
import sys

from pathlib import Path

from clusterctl.ansible_config import (
    configure_boundary_env,
    entry_settings,
    resolve_boundary_entry,
    summary_lines_for_boundary,
)
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.paths import repo_root
from clusterctl.playbooks_resolve import effective_playbooks_config, require_phase_runner
from clusterctl.workspace_paths import (
    WORKSPACE_ANSIBLE_ENV_KEYS,
    assert_no_legacy_repo_root_ansible,
    report_purged_legacy_repo_root_ansible,
    validate_workspace_ansible_env,
    workspace_ansible_summary_lines,
)

WORKSPACE_EXPORT_KEYS = (
    "ATLAS_CLUSTER_ROOT",
    "CLUSTER_ID",
    "CLUSTER_WORKSPACE_ID",
    "CLUSTER_WORKSPACE_ROOT",
    *WORKSPACE_ANSIBLE_ENV_KEYS,
)

PHASE_EXPORT_KEYS = (
    *WORKSPACE_EXPORT_KEYS,
    "SSH_KEY",
    "ANSIBLE_PRIVATE_KEY_FILE",
    "ANSIBLE_CONFIG",
    "ANSIBLE_ROLES_PATH",
    "ANSIBLE_STRATEGY",
    "ANSIBLE_FORKS",
    "ANSIBLE_FORCE_COLOR",
)


def _shell_quote(value: str) -> str:
    return shlex.quote(value)


def _export_lines(env: dict[str, str], keys: tuple[str, ...]) -> str:
    lines: list[str] = []
    for key in keys:
        value = env.get(key, "")
        if value is None or str(value).strip() == "":
            continue
        lines.append(f"export {key}={_shell_quote(str(value))}")
    return "\n".join(lines)


def _require_playbooks_context(ctx: ClusterContext) -> tuple:
    require_phase_runner(ctx)
    assert ctx.config_v2 is not None
    assert ctx.config_v2.phases is not None
    return effective_playbooks_config(ctx), ctx.config_v2.phases


def _ensure_legacy_repo_root_ansible_cleared(repo_root_path: Path) -> None:
    """Purge legacy repo-root ansible paths, then assert none remain non-empty."""
    report_purged_legacy_repo_root_ansible(repo_root_path)
    assert_no_legacy_repo_root_ansible(repo_root_path)


def build_workspace_env(*, cluster_id: str | None = None) -> dict[str, str]:
    ctx = ClusterContext.load(cluster_id=cluster_id)
    _ensure_legacy_repo_root_ansible_cleared(ctx.repo_root)
    env = ctx.ansible_env(ensure_dirs=True)
    validate_workspace_ansible_env(
        env,
        ctx.workspace_root,
        workspace_id=ctx.workspace_id,
        controller_temp=ctx.controller_temp_location(),
    )
    return env


def build_phase_env(boundary: str, *, cluster_id: str | None = None) -> dict[str, str]:
    ctx = ClusterContext.load(cluster_id=cluster_id)
    _ensure_legacy_repo_root_ansible_cleared(ctx.repo_root)
    playbooks, phases = _require_playbooks_context(ctx)
    env = ctx.ansible_env(ensure_dirs=True)
    configure_boundary_env(
        env,
        ctx.repo_root,
        boundary,
        playbooks=playbooks,
        phases=phases,
        workspace_root=ctx.workspace_root,
    )
    validate_workspace_ansible_env(
        env,
        ctx.workspace_root,
        workspace_id=ctx.workspace_id,
        controller_temp=ctx.controller_temp_location(),
    )
    return env


def export_workspace(*, cluster_id: str | None = None) -> str:
    return _export_lines(build_workspace_env(cluster_id=cluster_id), WORKSPACE_EXPORT_KEYS)


def export_phase(boundary: str, *, cluster_id: str | None = None) -> str:
    return _export_lines(build_phase_env(boundary, cluster_id=cluster_id), PHASE_EXPORT_KEYS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export unified ansible + workspace env for shell scripts",
    )
    parser.add_argument(
        "--cluster",
        metavar="ID",
        help="clusters/<id>/ (default: CLUSTER_ID / .cluster-active / default)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export_p = sub.add_parser(
        "export",
        help="print bash export statements for ansible phase + workspace runtime",
    )
    export_p.add_argument(
        "boundary",
        metavar="PHASE",
        help="phase alias or repo/entry ref (e.g. provision, atlas-infra-edge/infra)",
    )

    sub.add_parser(
        "export-workspace",
        help="print bash export statements for workspace ansible runtime only",
    )

    show_p = sub.add_parser("show", help="human-readable resolved ansible env")
    show_p.add_argument(
        "boundary",
        metavar="PHASE",
        nargs="?",
        default="k8s-addons",
        help="phase alias or repo/entry ref",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(repo_root()))

    try:
        report_purged_legacy_repo_root_ansible(repo_root())
    except ClusterctlError as exc:
        print(f"cluster: {exc}", file=sys.stderr)
        return 1

    cluster_id = getattr(args, "cluster", None)

    try:
        if args.command == "export":
            print(export_phase(args.boundary, cluster_id=cluster_id))
            return 0
        if args.command == "export-workspace":
            print(export_workspace(cluster_id=cluster_id))
            return 0
        if args.command == "show":
            ctx = ClusterContext.load(cluster_id=cluster_id)
            _ensure_legacy_repo_root_ansible_cleared(ctx.repo_root)
            playbooks, phases = _require_playbooks_context(ctx)
            for line in ctx.summary_lines():
                print(line)
            print("")
            for line in workspace_ansible_summary_lines(
                ctx.workspace_root,
                workspace_id=ctx.workspace_id,
                controller_temp=ctx.controller_temp_location(),
            ):
                print(line)
            print("")
            _, _, entry = resolve_boundary_entry(args.boundary, playbooks, phases)
            for line in summary_lines_for_boundary(
                ctx.repo_root,
                args.boundary,
                playbooks=playbooks,
                phases=phases,
                workspace_root=ctx.workspace_root,
            ):
                print(line)
            settings = entry_settings(entry)
            print(f"(resolved strategy={settings.strategy}, forks={settings.forks})")
            return 0
    except ClusterctlError as exc:
        print(f"ansible_env: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
