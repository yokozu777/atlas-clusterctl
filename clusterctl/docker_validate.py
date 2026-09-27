"""Deep Docker execution checks for validate preflight."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.execution import (
    ExecutionCheck,
    check_ssh_key,
    docker_cli_available,
    is_inside_docker_container,
    resolve_docker_image_ref,
)
from clusterctl.docker_executor import (
    DOCKER_WORKSPACE_ANSIBLE_ENV_KEYS,
    build_container_env,
    build_docker_run_command,
    docker_ssh_staging_parent,
    preflight_docker,
    prepare_container_ssh_key,
)
from clusterctl.playbooks_paths import (
    playbook_repo_layout_ready,
    resolve_layout_dir,
)
from clusterctl.playbooks_registry import repo_names_from_phase_refs
from clusterctl.playbooks_resolve import effective_playbooks_config, uses_phase_runner
from clusterctl.playbooks_repos import require_playbook_repos
from clusterctl.workspace_paths import (
    container_controller_ansible_tmp_dir,
    validate_workspace_ansible_env,
    workspace_ansible_summary_lines,
    workspace_facts_cache_dir,
)

ENV_SKIP_DOCKER_SMOKE = "VALIDATE_SKIP_DOCKER_SMOKE"
DEFAULT_PULL_TIMEOUT_SEC = 600
DEFAULT_SMOKE_TIMEOUT_SEC = 180


@dataclass(frozen=True)
class DockerValidateOptions:
    pull: bool = True
    verify_mounts: bool = True
    run_dry_run: bool = True
    pull_timeout_sec: int = DEFAULT_PULL_TIMEOUT_SEC
    smoke_timeout_sec: int = DEFAULT_SMOKE_TIMEOUT_SEC


def skip_docker_smoke_from_env() -> bool:
    return os.environ.get(ENV_SKIP_DOCKER_SMOKE, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def verify_container_ansible_workspace(ctx: ClusterContext) -> str | None:
    """Return error message when workspace ansible env/dirs are wrong inside container."""
    try:
        validate_workspace_ansible_env(
            dict(os.environ),
            ctx.workspace_root,
            workspace_id=ctx.workspace_id,
            controller_temp="container",
        )
    except ClusterctlError as exc:
        return str(exc)

    ws = ctx.workspace_root.resolve()
    cache_dir = workspace_facts_cache_dir(ws)
    if not cache_dir.is_dir():
        return f"workspace fact cache missing in container: {cache_dir}"

    tmp_dir = container_controller_ansible_tmp_dir(ctx.workspace_id)
    if not tmp_dir.is_dir():
        return f"container controller tmp missing: {tmp_dir}"
    return None


def check_docker_workspace_ansible_host(ctx: ClusterContext) -> ExecutionCheck | None:
    try:
        env = build_container_env(ctx)
    except ClusterctlError as exc:
        return ExecutionCheck(
            severity="error",
            code="execution_docker_workspace_ansible",
            message=f"docker workspace ansible env: {exc}",
            hint="remove legacy .ansible paths from repo root; use workspace/<id>/",
        )

    summary = ", ".join(f"{key}={env[key]}" for key in DOCKER_WORKSPACE_ANSIBLE_ENV_KEYS)
    return ExecutionCheck(
        severity="ok",
        code="execution_docker_workspace_ansible",
        message=f"docker workspace ansible env ready: {summary}",
    )


def verify_container_mounts(ctx: ClusterContext) -> list[str]:
    """Return missing playbook repo names (empty = all layout dirs ready in container)."""
    if not uses_phase_runner(ctx):
        return []
    assert ctx.config_v2 is not None
    assert ctx.config_v2.phases is not None

    playbooks = effective_playbooks_config(ctx)
    phases = ctx.config_v2.phases
    missing: list[str] = []
    for repo_name in repo_names_from_phase_refs(phases.phases):
        spec = playbooks.repos.get(repo_name)
        if spec is None:
            missing.append(repo_name)
            continue
        layout_dir = resolve_layout_dir(
            spec,
            workspace_root=ctx.workspace_root,
            repo_root_path=ctx.repo_root,
        )
        if not playbook_repo_layout_ready(spec, layout_dir):
            missing.append(repo_name)
    return missing


def check_docker_playbooks_host(ctx: ClusterContext) -> ExecutionCheck | None:
    if not uses_phase_runner(ctx):
        return ExecutionCheck(
            severity="error",
            code="execution_docker_phases_missing",
            message="docker execution requires schema v2 playbooks + phases",
            hint="see docs/cluster-config-v2.md",
        )
    try:
        require_playbook_repos(ctx.playbooks_enabled, ctx.playbook_repos)
    except ClusterctlError as exc:
        return ExecutionCheck(
            severity="error",
            code="execution_docker_repos_missing",
            message=str(exc),
            hint="define playbooks: (+ phases:) then ./cluster repos sync "
            "(playbooks_enabled: false disables — ADR 006)",
        )

    missing = verify_container_mounts(ctx)
    if missing:
        return ExecutionCheck(
            severity="error",
            code="execution_docker_repos_missing",
            message="docker playbooks not ready: " + ", ".join(missing),
            hint="./cluster repos sync — git repos under workspace/<id>/repos/",
        )

    return ExecutionCheck(
        severity="ok",
        code="execution_docker_repos",
        message="docker playbooks ready (workspace/local resolver)",
    )


def _run_subprocess(
    cmd: list[str],
    *,
    timeout_sec: int,
    label: str,
) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return False, f"{label} timed out after {timeout_sec}s"
    except OSError as exc:
        return False, f"{label} failed: {exc}"

    if result.returncode == 0:
        detail = (result.stdout or result.stderr or "").strip()
        if detail:
            last_line = detail.splitlines()[-1]
            return True, last_line
        return True, "ok"

    detail = (result.stderr or result.stdout or "").strip()
    if len(detail) > 400:
        detail = detail[-400:]
    return False, detail or f"{label} exited {result.returncode}"


def docker_pull_image(image_ref: str, *, timeout_sec: int) -> tuple[bool, str]:
    return _run_subprocess(
        ["docker", "pull", image_ref],
        timeout_sec=timeout_sec,
        label=f"docker pull {image_ref}",
    )


def cmd_docker_pull(ctx: ClusterContext) -> int:
    """Pull ``execution.image:tag`` from cluster.yaml (worker / Apply)."""
    docker_cfg = (
        ctx.execution_configured
        if ctx.execution_configured.is_docker
        else ctx.execution
    )
    if not docker_cfg.is_docker:
        raise ClusterctlError(
            "execution.mode is not docker — set execution.image and execution.tag "
            "in cluster.yaml"
        )
    image_ref = resolve_docker_image_ref(docker_cfg.docker)
    ok, detail = docker_pull_image(image_ref, timeout_sec=DEFAULT_PULL_TIMEOUT_SEC)
    if not ok:
        raise ClusterctlError(f"docker pull {image_ref} failed: {detail}")
    print(f"pulled {image_ref}: {detail}")
    return 0


def build_docker_smoke_command(
    ctx: ClusterContext, *, ssh_key_host: Path
) -> list[str]:
    inner = ["python3", "-m", "clusterctl.docker_validate", "inner-smoke"]
    return build_docker_run_command(ctx, inner, ssh_key_host=ssh_key_host)


def run_docker_smoke(ctx: ClusterContext, *, timeout_sec: int) -> tuple[bool, str]:
    # Same order as run_docker_container: preflight → prepare → assemble cmd.
    preflight_docker(ctx)
    prepared = prepare_container_ssh_key(
        ctx.ssh_key,
        staging_parent=docker_ssh_staging_parent(ctx.workspace_root),
    )
    try:
        cmd = build_docker_smoke_command(ctx, ssh_key_host=prepared.key_path)
        return _run_subprocess(
            cmd,
            timeout_sec=timeout_sec,
            label="docker smoke (mounts + cluster run --dry-run)",
        )
    finally:
        prepared.cleanup()


def _basic_docker_ready(ctx: ClusterContext) -> str | None:
    if not ctx.execution.is_docker:
        return "not docker mode"
    if is_inside_docker_container():
        return "inside docker container"
    if not docker_cli_available():
        return "docker CLI missing"
    if not ctx.execution.docker.image or not ctx.execution.docker.tag:
        return "docker image/tag not configured"
    if check_ssh_key(ctx.ssh_key.expanduser()):
        return "ssh key not ready"
    return None


def validate_docker_deep(
    ctx: ClusterContext,
    *,
    options: DockerValidateOptions | None = None,
) -> list[ExecutionCheck]:
    """
    Pull executor image, verify role-repo mounts inside container, run ``run --dry-run``.

    Skipped when effective execution mode is not docker or basic prerequisites fail.
    """
    opts = options or DockerValidateOptions()
    checks: list[ExecutionCheck] = []

    skip_reason = _basic_docker_ready(ctx)
    if skip_reason:
        return checks

    repo_check = check_docker_playbooks_host(ctx)
    if repo_check is not None:
        checks.append(repo_check)
        if repo_check.severity == "error":
            return checks

    ws_check = check_docker_workspace_ansible_host(ctx)
    if ws_check is not None:
        checks.append(ws_check)
        if ws_check.severity == "error":
            return checks

    try:
        image_ref = resolve_docker_image_ref(ctx.execution.docker)
    except ClusterctlError as exc:
        checks.append(
            ExecutionCheck(
                severity="error",
                code="execution_docker_image_resolve",
                message=str(exc),
            )
        )
        return checks

    if opts.pull:
        ok, detail = docker_pull_image(image_ref, timeout_sec=opts.pull_timeout_sec)
        if ok:
            checks.append(
                ExecutionCheck(
                    severity="ok",
                    code="execution_docker_pull",
                    message=f"docker pull {image_ref}: {detail}",
                )
            )
        else:
            checks.append(
                ExecutionCheck(
                    severity="error",
                    code="execution_docker_pull",
                    message=f"docker pull {image_ref} failed: {detail}",
                    hint="check registry auth, network, image:tag in cluster.yaml",
                )
            )
            return checks

    if not opts.verify_mounts and not opts.run_dry_run:
        return checks

    ok, detail = run_docker_smoke(ctx, timeout_sec=opts.smoke_timeout_sec)
    if ok:
        checks.append(
            ExecutionCheck(
                severity="ok",
                code="execution_docker_smoke",
                message=f"docker smoke OK (mounts + run --dry-run): {detail}",
            )
        )
    else:
        checks.append(
            ExecutionCheck(
                severity="error",
                code="execution_docker_smoke",
                message=f"docker smoke failed: {detail}",
                hint=(
                    "verify workspace/repos/ playbooks, image entrypoint, and "
                    "./cluster run --dry-run inside container"
                ),
            )
        )

    return checks


def run_inner_smoke() -> int:
    """Execute inside Docker container during validate (mount check + run --dry-run)."""
    from clusterctl.context import ClusterContext

    ctx = ClusterContext.load(cluster_id=os.environ.get("CLUSTER_ID"))
    missing = verify_container_mounts(ctx)
    if missing:
        print(
            "docker inner-smoke: playbooks not ready in container: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    print(
        "docker inner-smoke: playbooks paths OK (workspace/local resolver)",
        file=sys.stderr,
    )

    ansible_err = verify_container_ansible_workspace(ctx)
    if ansible_err:
        print(f"docker inner-smoke: workspace ansible: {ansible_err}", file=sys.stderr)
        return 1

    for line in workspace_ansible_summary_lines(
        ctx.workspace_root.resolve(),
        workspace_id=ctx.workspace_id,
        controller_temp="container",
    ):
        print(f"docker inner-smoke: {line}", file=sys.stderr)

    dry_run_cmd = [sys.executable, "-m", "clusterctl", "run", "--dry-run"]
    result = subprocess.run(dry_run_cmd, check=False)
    return int(result.returncode)



def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "inner-smoke":
        return run_inner_smoke()
    print("usage: python3 -m clusterctl.docker_validate inner-smoke", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
