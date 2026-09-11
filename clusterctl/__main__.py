"""Entry point: python3 -m clusterctl  (./cluster)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from clusterctl import __version__
from clusterctl.cli_args import normalize_global_argv
from clusterctl.ansible_runner import AnsibleRunner
from clusterctl.context import ClusterContext
from clusterctl.config_cmd import cmd_config_effective, cmd_config_show
from clusterctl.exceptions import (
    ClusterctlError,
    ClusterNotFoundError,
    PhaseAliasesRemovedError,
    StacksRemovedError,
)
from clusterctl.logging_util import run_log_session, tee_log_file
from clusterctl.execution import EXECUTION_MODES
from clusterctl.docker_executor import dispatch_docker_if_needed
from clusterctl.paths import (
    repo_root,
    resolve_cluster_id,
    write_active_cluster_id,
)
from clusterctl.workspace_paths import report_purged_legacy_repo_root_ansible
from clusterctl.phase_plan import (
    ensure_run_plan_nonempty,
    format_phase_plan_json,
    format_phase_plan_text,
    resolve_phase_execution_plan,
)
from clusterctl.run_overrides import apply_run_cli_overrides, resolve_run_limit
from clusterctl.playbooks_resolve import require_phase_runner
from clusterctl.smoke import format_smoke_json, format_smoke_text, run_smoke
from clusterctl.validate import (
    format_report_text,
    format_reports_json,
    report_cluster_load_failure,
    validate_all_clusters,
    validate_cluster,
    validate_repo,
)
from clusterctl.workspace_cmd import cmd_workspace_reset, cmd_workspace_show


def _add_executor_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--executor",
        choices=sorted(EXECUTION_MODES),
        metavar="MODE",
        help="runtime override: local (ansible on host) or docker (container)",
    )


def _executor_from_args(args: argparse.Namespace) -> str | None:
    return getattr(args, "executor", None)


def _add_cluster_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cluster",
        metavar="ID",
        help="cluster config id (default: CLUSTER_ID → .cluster-active → default)",
    )


def _add_phases_selector_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--phases",
        "-p",
        dest="phases_selector",
        metavar="SELECTOR",
        help=(
            "phase window: NAME | start..end | a,b,c "
            "(CSV needs ≥2 names; ADR 008)"
        ),
    )


def _add_run_override_flags(parser: argparse.ArgumentParser) -> None:
    """ADR 009 Phase 1 — execute overrides on ``run`` (see run_overrides.py)."""
    parser.add_argument(
        "--tags",
        default="all",
        help="ansible --tags (default: all); selective → single-phase collapse",
    )
    parser.add_argument(
        "--limit",
        help="ansible --limit; selective → single-phase collapse",
    )
    parser.add_argument(
        "-e",
        "--extra-vars",
        action="append",
        default=[],
        metavar="VAR",
        help=(
            "extra ansible -e (repeatable). Alone: merge into every catalog "
            "invocation (no collapse). With --tags/--limit/--root-ssh: rides on "
            "collapsed invocation (ADR 009)"
        ),
    )
    parser.add_argument(
        "--root-ssh",
        action="store_true",
        help="pass root SSH extra-vars (init); selective → single-phase collapse",
    )
    parser.add_argument(
        "--git-ssh",
        action="store_true",
        help="set GIT_SSH_COMMAND for git-over-ssh roles (does not collapse)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cluster",
        description="Atlas cluster controller CLI (schema v2 playbooks + phases)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_cluster_flag(parser)
    _add_executor_flag(parser)

    sub = parser.add_subparsers(dest="command", required=True)

    use_p = sub.add_parser("use", help="select active cluster (writes .cluster-active)")
    use_p.add_argument(
        "cluster_id",
        help="cluster id (env/name, legacy id, or 'default')",
    )

    run_p = sub.add_parser("run", help="run schema v2 phases from cluster cascade")
    _add_phases_selector_flag(run_p)
    _add_run_override_flags(run_p)
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="print plan summary and ansible invocations without executing",
    )

    plan_p = sub.add_parser("plan", help="show execution plan (dry-run summary)")
    _add_phases_selector_flag(plan_p)
    plan_p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="list every invocation in the plan",
    )
    plan_p.add_argument(
        "--json",
        action="store_true",
        help="emit plan as JSON",
    )

    stages_p = sub.add_parser(
        "stages",
        help="list effective phases for cluster (or org baseline with --baseline)",
    )
    stages_p.add_argument(
        "--baseline",
        action="store_true",
        help="list org baseline phases only (ignore active cluster)",
    )
    stages_p.add_argument(
        "--json",
        action="store_true",
        help="emit stages as JSON",
    )

    list_p = sub.add_parser("list", help="list clusters under clusters/")
    list_p.add_argument(
        "--json",
        action="store_true",
        help="emit cluster list as JSON",
    )

    limits_p = sub.add_parser(
        "limits",
        help="list ansible --limit groups and hosts for the current cluster",
    )
    limits_p.add_argument(
        "--json",
        action="store_true",
        help="emit groups and hosts as JSON",
    )

    vars_p = sub.add_parser(
        "vars",
        help="list connected cluster.yaml / group_vars / host_vars (paths only)",
    )
    vars_p.add_argument(
        "--json",
        action="store_true",
        help="emit vars catalog as JSON (no file bodies)",
    )

    init_p = sub.add_parser("init", help="scaffold clusters/<id>/ from an existing cluster or _template")
    init_p.add_argument("cluster_id", metavar="ID")
    init_p.add_argument(
        "--from",
        dest="from_cluster",
        default="default",
        help="copy clusters/<id>/ as base (default: default; ignored with --template)",
    )
    init_p.add_argument(
        "--template",
        nargs="?",
        const="",
        default=None,
        metavar="NAME",
        help="copy clusters/_template/ (optional NAME, e.g. k8s_full → _template/k8s_full/)",
    )
    init_p.add_argument(
        "--display-name",
        metavar="NAME",
        help="cluster.yaml display_name (default: cluster id)",
    )
    init_p.add_argument(
        "--dns-suffix",
        metavar="DOMAIN",
        help="Leaf DNS identity dns_domain_suffix in atlas-*.yml overlays "
        "(e.g. lab.example.com); cluster_domain stack prefix stays template-owned",
    )
    init_p.add_argument(
        "--no-validate",
        action="store_true",
        help="skip post-init validate (not recommended)",
    )
    init_p.add_argument(
        "--force",
        action="store_true",
        help="replace existing clusters/<id>/ directory",
    )

    cfg_p = sub.add_parser("config", help="unified ansible.cfg resolution")
    cfg_sub = cfg_p.add_subparsers(dest="config_command", required=True)
    cfg_show = cfg_sub.add_parser("show", help="show ansible env for a phase alias or repo/entry")
    cfg_show.add_argument(
        "boundary",
        nargs="?",
        default="k8s-addons",
        metavar="PHASE",
        help="phase alias or repo/entry ref (default: k8s-addons)",
    )
    cfg_show.add_argument(
        "--json",
        action="store_true",
        help="emit config report as JSON",
    )
    cfg_effective = cfg_sub.add_parser(
        "effective",
        help="show merged schema v2 cluster.yaml (cascade)",
    )
    cfg_effective.add_argument(
        "--json",
        action="store_true",
        help="emit effective config as JSON",
    )

    ws_p = sub.add_parser("workspace", help="workspace runtime paths")
    ws_sub = ws_p.add_subparsers(dest="workspace_command", required=True)
    ws_show = ws_sub.add_parser("show", help="show resolved cluster + workspace paths")
    ws_show.add_argument(
        "--json",
        action="store_true",
        help="emit workspace paths as JSON",
    )
    ws_sub.add_parser("id", help="print resolved workspace id (for shell scripts)")
    reset_p = ws_sub.add_parser("reset", help="delete workspace/<id>/ runtime tree")
    reset_p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="skip interactive confirmation",
    )

    pb_p = sub.add_parser("playbooks", help="playbook repository sync (schema v2)")
    pb_sub = pb_p.add_subparsers(dest="playbooks_command", required=True)
    pb_sync = pb_sub.add_parser("sync", help="clone/update git playbook repos into workspace")
    pb_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="show planned sync actions without running git",
    )
    pb_sync.add_argument(
        "--repo",
        metavar="NAME",
        help="sync one playbook repo only (any name from cluster.yaml playbooks)",
    )
    pb_sync.add_argument(
        "--phase-ref",
        metavar="REPO/ENTRY",
        help="sync repo for one phase ref (e.g. my-stack/install)",
    )
    pb_sync.add_argument(
        "--phase",
        metavar="ALIAS",
        help="sync repo for a phase alias (e.g. install → my-stack/install)",
    )
    pb_status = pb_sub.add_parser("status", help="show materialized playbook repo readiness")
    pb_status.add_argument(
        "--json",
        action="store_true",
        help="emit repo status as JSON",
    )
    pb_sub.add_parser("show", help="show resolved playbooks config and readiness")

    repos_p = sub.add_parser(
        "repos",
        help="sync playbook repos into workspace (schema v2)",
    )
    repos_sub = repos_p.add_subparsers(dest="repos_command", required=True)
    repos_sync = repos_sub.add_parser("sync", help="clone/update repos into workspace")
    repos_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="show planned sync actions without running git",
    )
    repos_sync.add_argument(
        "--repo",
        metavar="NAME",
        help="sync one repo only",
    )
    repos_sync.add_argument(
        "--phase-ref",
        metavar="REPO/ENTRY",
        help="sync repo for one v2 phase ref",
    )
    repos_sync.add_argument(
        "--phase",
        metavar="ALIAS",
        help="sync playbooks repo for a phase alias or repo/entry ref",
    )
    repos_status = repos_sub.add_parser("status", help="show materialized repo readiness")
    repos_status.add_argument(
        "--json",
        action="store_true",
        help="emit repo status as JSON",
    )
    repos_sub.add_parser("show", help="show resolved repo config and readiness")

    val_p = sub.add_parser("validate", help="validate cluster config and repo artifacts")
    val_p.add_argument(
        "--repo",
        action="store_true",
        help="validate repository only (org baseline, layout conventions)",
    )
    val_p.add_argument(
        "--all",
        action="store_true",
        help="validate all clusters under clusters/ (+ repo)",
    )
    val_p.add_argument(
        "--json",
        action="store_true",
        help="emit JSON report",
    )
    val_p.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors (exit 1)",
    )
    val_p.add_argument(
        "--skip-docker-smoke",
        action="store_true",
        help="skip docker pull + in-container smoke (mounts + run --dry-run)",
    )

    smoke_p = sub.add_parser("smoke", help="multi-cluster validate + execution plan smoke test")
    smoke_p.add_argument(
        "--all",
        action="store_true",
        help="smoke all clusters (default when --cluster omitted)",
    )
    smoke_p.add_argument(
        "--json",
        action="store_true",
        help="emit JSON report",
    )
    smoke_p.add_argument(
        "--no-repo",
        action="store_true",
        help="skip repository-level checks",
    )

    return parser


def _resolve_plan(ctx: ClusterContext, args: argparse.Namespace):
    from clusterctl.phase_selector import resolve_cli_phase_window

    require_phase_runner(ctx)
    window = resolve_cli_phase_window(
        phases_selector=getattr(args, "phases_selector", None),
    )
    return resolve_phase_execution_plan(
        ctx,
        from_phase=window.from_phase,
        to_phase=window.to_phase,
        only_phases=window.only_phases,
    )


def _cmd_run_execute(
    ctx: ClusterContext,
    args: argparse.Namespace,
    raw_argv: list[str],
    *,
    command: str = "run",
    header: str | None = None,
    extra_metadata: dict | None = None,
) -> int:
    """Execute path for ``run`` (ADR 009)."""
    plan = ensure_run_plan_nonempty(_resolve_plan(ctx, args))
    # CLI --limit wins; else env LIMIT (resolve_run_limit).
    limit = resolve_run_limit(getattr(args, "limit", None))
    plan = apply_run_cli_overrides(
        plan,
        tags=getattr(args, "tags", None),
        limit=limit,
        extra_vars=tuple(getattr(args, "extra_vars", None) or ()),
        root_ssh=bool(getattr(args, "root_ssh", False)),
        git_ssh=bool(getattr(args, "git_ssh", False)),
    )
    if header is None:
        header = f"cluster run phases ({', '.join(plan.summary.phases)})"
    metadata = {
        "cluster_id": ctx.cluster_id,
        "schema_version": ctx.schema_version,
        "phases": list(plan.summary.phases),
        "invocation_count": plan.summary.invocation_count,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    extra = tuple(getattr(args, "extra_vars", None) or ())
    if extra:
        metadata["extra_vars"] = list(extra)
    tags = getattr(args, "tags", None)
    if tags and str(tags).strip() and str(tags).strip() != "all":
        metadata["tags"] = str(tags).strip()
    if limit:
        metadata["limit"] = limit

    def _execute(runner: AnsibleRunner) -> None:
        if args.dry_run:
            print(format_phase_plan_text(plan), end="")
            print("--- dry-run invocations ---")
        runner.run_phase_execution_plan(plan, dry_run=args.dry_run)

    return _run_mutating_logged(
        ctx,
        raw_argv,
        command=command,
        header=header,
        metadata=metadata,
        dry_run=args.dry_run,
        execute=_execute,
    )


def _validation_exit_code(reports, *, strict: bool = False) -> int:
    if any(not report.ok for report in reports):
        return 1
    if strict and any(report.warnings for report in reports):
        return 1
    return 0


def _cmd_validate(args: argparse.Namespace, root: Path) -> int:
    os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))
    docker_smoke = not args.skip_docker_smoke

    if args.repo and not args.all and not getattr(args, "cluster", None):
        reports = [validate_repo(root)]
    elif args.all:
        reports = validate_all_clusters(
            root,
            executor=_executor_from_args(args),
            docker_smoke=docker_smoke,
            strict=args.strict,
        )
    else:
        cluster_id = getattr(args, "cluster", None)
        try:
            ctx = ClusterContext.load(
                cluster_id=cluster_id,
                executor=_executor_from_args(args),
            )
            reports = [
                validate_cluster(
                    ctx, root=root, docker_smoke=docker_smoke, strict=args.strict
                )
            ]
        except (StacksRemovedError, PhaseAliasesRemovedError) as exc:
            # Structured report (same code as --all), not only stderr print.
            reports = [
                report_cluster_load_failure(
                    cluster_id or exc.source or "(cluster)",
                    exc,
                )
            ]

    if args.json:
        print(format_reports_json(reports), end="")
    else:
        for index, report in enumerate(reports):
            if index:
                print("")
            print(format_report_text(report), end="")
            if not report.issues or index < len(reports) - 1:
                print("")

    return _validation_exit_code(reports, strict=args.strict)


def _cmd_smoke(args: argparse.Namespace, root: Path) -> int:
    os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))
    cluster_id = getattr(args, "cluster", None)
    if cluster_id is None and not args.all:
        args_all = True
    else:
        args_all = args.all or cluster_id is None

    results = run_smoke(
        root,
        cluster_id=cluster_id if not args_all else None,
        include_repo=not args.no_repo,
    )

    if args.json:
        print(format_smoke_json(results), end="")
    else:
        print(format_smoke_text(results), end="")

    ok = all(report.ok for report, _ in results)
    ok = ok and all(smoke is None or smoke.plan_ok for _, smoke in results)
    return 0 if ok else 1


def _output_file_override() -> Path | None:
    raw = os.environ.get("OUTPUT_FILE", "").strip()
    return Path(raw) if raw else None


def _run_mutating_logged(
    ctx: ClusterContext,
    raw_argv: list[str],
    *,
    command: str,
    header: str,
    metadata: dict[str, object],
    dry_run: bool,
    execute,
) -> int:
    """Create run log dir, optionally delegate to docker, then execute ansible."""
    override = _output_file_override()
    if override is not None:
        with tee_log_file(override, header=header):
            dispatched = _dispatch_mutating(ctx, raw_argv)
            if dispatched is not None:
                return dispatched
            execute(AnsibleRunner(ctx))
        if not dry_run:
            print(f"log: {override}")
        return 0

    if dry_run:
        dispatched = _dispatch_mutating(ctx, raw_argv)
        if dispatched is not None:
            return dispatched
        execute(AnsibleRunner(ctx))
        return 0

    with run_log_session(
        ctx.workspace_logs,
        command=command,
        header=header,
        metadata=metadata,
    ) as session:
        dispatched = _dispatch_mutating(ctx, raw_argv)
        if dispatched is not None:
            session.set_exit_code(dispatched)
            print(f"log: {session.summary_path()}")
            return dispatched
        execute(AnsibleRunner(ctx, log_session=session))
        session.set_exit_code(0)
        print(f"log: {session.summary_path()}")
    return 0


def _load_context(args: argparse.Namespace) -> ClusterContext:
    root = Path(__file__).resolve().parent.parent
    os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))
    return ClusterContext.load(
        cluster_id=getattr(args, "cluster", None),
        executor=_executor_from_args(args),
    )


def _dispatch_mutating(ctx: ClusterContext, argv: list[str]) -> int | None:
    """Delegate run/stage/play to Docker when execution.mode is docker."""
    return dispatch_docker_if_needed(ctx, argv)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        incoming = list(sys.argv) if argv is None else list(argv)
        normalized = normalize_global_argv(incoming)
    except ClusterctlError as exc:
        print(f"cluster: {exc}", file=sys.stderr)
        return 1
    raw_argv = normalized
    args = parser.parse_args(normalized[1:])

    try:
        report_purged_legacy_repo_root_ansible(repo_root())
    except ClusterctlError as exc:
        print(f"cluster: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == "use":
            path = write_active_cluster_id(args.cluster_id)
            print(f"active cluster: {args.cluster_id} ({path})")
            return 0

        if args.command == "stages":
            from clusterctl.stages_cmd import cmd_stages

            as_json = bool(getattr(args, "json", False))
            if getattr(args, "baseline", False):
                return cmd_stages(None, baseline=True, as_json=as_json)

            root = Path(__file__).resolve().parent.parent
            os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))
            try:
                ctx = ClusterContext.load(cluster_id=getattr(args, "cluster", None))
            except ClusterNotFoundError as exc:
                print(f"cluster: {exc}", file=sys.stderr)
                return 1

            if ctx.deployable:
                return cmd_stages(ctx, as_json=as_json)
            return cmd_stages(None, baseline=True, as_json=as_json)

        if args.command == "list":
            from clusterctl.list_cmd import cmd_list

            root = Path(__file__).resolve().parent.parent
            os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))
            return cmd_list(root, as_json=bool(getattr(args, "json", False)))

        if args.command == "limits":
            from clusterctl.limits_cmd import cmd_limits

            root = repo_root()
            os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))
            cluster_id = resolve_cluster_id(getattr(args, "cluster", None), root)
            return cmd_limits(
                root,
                cluster_id,
                as_json=bool(getattr(args, "json", False)),
            )

        if args.command == "vars":
            from clusterctl.vars_cmd import cmd_vars

            root = repo_root()
            os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))
            cluster_id = resolve_cluster_id(getattr(args, "cluster", None), root)
            return cmd_vars(
                root,
                cluster_id,
                as_json=bool(getattr(args, "json", False)),
            )

        if args.command == "init":
            from clusterctl.cluster_init import InitOptions, init_cluster

            root = Path(__file__).resolve().parent.parent
            options = InitOptions(
                from_id=args.from_cluster,
                template_name=args.template,
                display_name=getattr(args, "display_name", None),
                dns_domain_suffix=getattr(args, "dns_suffix", None),
                validate=not args.no_validate,
                force=args.force,
            )
            target = init_cluster(root, args.cluster_id, options=options)
            print(f"created {target}")
            print(
                f"  edit Leaf DNS in {target}/group_vars/all/atlas-*.yml "
                f"(and hosts); fill atlas-*.secrets.yml"
            )
            print(f"  ./cluster use {args.cluster_id}")
            return 0

        if args.command == "config":
            root = repo_root()
            cluster_id = resolve_cluster_id(getattr(args, "cluster", None), root)
            if args.config_command == "effective":
                try:
                    ctx = _load_context(args)
                except ClusterNotFoundError:
                    ctx = None
                return cmd_config_effective(
                    ctx,
                    cluster_id=cluster_id,
                    repo_root_path=root,
                    as_json=args.json,
                )
            ctx = _load_context(args)
            return cmd_config_show(ctx, args.boundary, as_json=args.json)

        if args.command == "validate":
            root = repo_root()
            return _cmd_validate(args, root)

        if args.command == "smoke":
            root = repo_root()
            return _cmd_smoke(args, root)

        if args.command == "workspace" and args.workspace_command == "id":
            root = Path(__file__).resolve().parent.parent
            os.environ.setdefault("ATLAS_CLUSTER_ROOT", str(root))
            from clusterctl.workspace_cmd import cmd_workspace_id

            return cmd_workspace_id(getattr(args, "cluster", None))

        if args.command == "playbooks":
            ctx = _load_context(args)
            from clusterctl.playbooks_cmd import (
                cmd_playbooks_show,
                cmd_playbooks_status,
                cmd_playbooks_sync,
            )

            if args.playbooks_command == "sync":
                return cmd_playbooks_sync(
                    ctx,
                    dry_run=args.dry_run,
                    repo=getattr(args, "repo", None),
                    phase_ref=getattr(args, "phase_ref", None),
                    phase=getattr(args, "phase", None),
                )
            if args.playbooks_command == "status":
                return cmd_playbooks_status(ctx, as_json=bool(getattr(args, "json", False)))
            if args.playbooks_command == "show":
                return cmd_playbooks_show(ctx)

        if args.command == "repos":
            ctx = _load_context(args)
            from clusterctl.repos_cmd import (
                cmd_repos_show,
                cmd_repos_status,
                cmd_repos_sync,
            )

            if args.repos_command == "sync":
                return cmd_repos_sync(
                    ctx,
                    dry_run=args.dry_run,
                    repo=getattr(args, "repo", None),
                    phase_ref=getattr(args, "phase_ref", None),
                    phase=getattr(args, "phase", None),
                )
            if args.repos_command == "status":
                return cmd_repos_status(ctx, as_json=bool(getattr(args, "json", False)))
            if args.repos_command == "show":
                return cmd_repos_show(ctx)

        ctx = _load_context(args)

        if args.command == "plan":
            plan = _resolve_plan(ctx, args)
            if args.json:
                print(format_phase_plan_json(plan), end="")
            else:
                print(format_phase_plan_text(plan, verbose=args.verbose), end="")
            return 0

        if args.command == "workspace":
            if args.workspace_command == "show":
                return cmd_workspace_show(ctx, as_json=bool(getattr(args, "json", False)))
            if args.workspace_command == "reset":
                return cmd_workspace_reset(ctx, assume_yes=args.yes)

        if args.command == "run":
            return _cmd_run_execute(ctx, args, raw_argv, command="run")

    except ClusterctlError as exc:
        print(f"cluster: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ncluster: interrupted", file=sys.stderr)
        return 130

    parser.error(f"unhandled command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
