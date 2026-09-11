"""Run ./cluster mutating commands inside a Docker executor image."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from clusterctl.cli_args import SUBCOMMANDS as CLUSTER_SUBCOMMANDS
from clusterctl.cli_args import strip_global_flags_from_argv
from clusterctl.context import ClusterContext
from clusterctl.execution import (
    ENV_FORCE_LOCAL,
    check_ssh_key,
    docker_cli_available,
    is_inside_docker_container,
    resolve_docker_image_ref,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.logging_util import ENV_RUN_LOG_DIR
from clusterctl.paths import clusters_root, workspace_parent
from clusterctl.playbooks_paths import collect_local_playbook_docker_mounts
from clusterctl.playbooks_resolve import effective_playbooks_config, require_phase_runner
from clusterctl.user_config import ENV_CLUSTERS_ROOT, ENV_WORKSPACE_ROOT
from clusterctl.workspace_paths import (
    WORKSPACE_ANSIBLE_ENV_KEYS,
    assert_no_legacy_repo_root_ansible,
    configure_workspace_ansible_env,
    container_controller_ansible_tmp_dir,
    ensure_workspace_ansible_dirs,
    validate_workspace_ansible_env,
)

PASSTHROUGH_ENV_KEYS = (
    # Do not pass host GIT_SSH_COMMAND — it usually points at a host-only key
    # path (e.g. GitLab runner ~/.ssh/id_deploy). Container uses the mounted
    # CONTAINER_SSH_KEY instead (see build_container_env).
    "LIMIT",
    "OUTPUT_FILE",
    ENV_RUN_LOG_DIR,
)

# Container path for the mounted SSH private key. Host staging is a per-run
# dir under ``workspace/<cluster_id>/.atlas-ssh/atlas-ssh-*`` (see
# ``prepare_container_ssh_key``); only this container path is stable across runs.
CONTAINER_SSH_KEY = "/tmp/atlas-ssh/id_rsa"

# Host parent (under cluster workspace) for per-run SSH staging. Must sit on a
# Docker-shareable bind-mount — not host ``/tmp`` (Desktop/snap) and not
# controller ``.cache/`` (kept free of identity files).
DOCKER_SSH_STAGING_DIRNAME = ".atlas-ssh"

# Re-export for docker_validate and tests.
DOCKER_WORKSPACE_ANSIBLE_ENV_KEYS = WORKSPACE_ANSIBLE_ENV_KEYS


def docker_ssh_staging_parent(workspace_root: Path) -> Path:
    """Return ``<workspace_root>/.atlas-ssh`` for per-run ``atlas-ssh-*`` dirs."""
    return workspace_root.expanduser().resolve() / DOCKER_SSH_STAGING_DIRNAME

_DETACH_FORBIDDEN_MSG = (
    "docker: execution.extra_args must not include -d/--detach "
    "— per-run SSH staging is removed when docker run returns; "
    "detached containers would lose the mounted key while still running"
)

_USER_FORBIDDEN_MSG = (
    "docker: execution.extra_args must not include --user/-u "
    "— clusterctl sets --user to the host uid:gid automatically"
)

# Writable home inside the container (image often has /root only for UID 0).
CONTAINER_HOME = "/tmp/clusterctl-home"
# Fake NSS for arbitrary --user uid:gid (krang ≥336 ships this package).
CONTAINER_NSS_WRAPPER_SO = "/usr/lib/libnss_wrapper.so"
CONTAINER_NSS_USER = "clusterctl"
ENV_EXECUTION_ID = "ATLAS_EXECUTION_ID"


def docker_run_container_name(execution_id: str | None = None) -> str | None:
    """Stable docker --name so the hub worker can `docker stop` a canceled run."""
    raw = (execution_id or os.environ.get(ENV_EXECUTION_ID) or "").strip()
    if not raw:
        return None
    safe = "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in raw)
    if not safe or not safe[0].isalnum():
        return None
    return f"atlas-exec-{safe}"[:63]


# Single-letter docker run flags that may combine (e.g. -itu, -itd).
_DOCKER_COMBINED_SHORT_LETTERS = frozenset("itdu")


def extra_args_detach_flag(extra_args: tuple[str, ...] | list[str]) -> str | None:
    """Return the ``-d`` / ``--detach`` token from ``extra_args``, if any.

    Detects exact ``-d`` / ``--detach``, ``--detach=…``, and combined short
    clusters whose letters are only from ``itdu`` and include ``d``
    (e.g. ``-itd`` / ``-td``). Does not treat arbitrary alpha shorts with ``d``
    (e.g. ``-dns``) as detach.
    """
    for arg in extra_args:
        if arg == "--detach" or arg.startswith("--detach="):
            return arg
        if arg == "-d":
            return arg
        if arg.startswith("-") and not arg.startswith("--") and "=" not in arg:
            letters = arg[1:]
            if (
                letters.isalpha()
                and "d" in letters
                and set(letters) <= _DOCKER_COMBINED_SHORT_LETTERS
            ):
                return arg
    return None


def reject_docker_detach_extra_args(
    extra_args: tuple[str, ...] | list[str],
) -> None:
    """Fail fast: detach is incompatible with per-run SSH staging cleanup."""
    hit = extra_args_detach_flag(extra_args)
    if hit is not None:
        raise ClusterctlError(f"{_DETACH_FORBIDDEN_MSG} (got {hit!r})")


def extra_args_user_flag(extra_args: tuple[str, ...] | list[str]) -> str | None:
    """Return the ``--user`` / ``-u`` token from ``extra_args``, if any.

    Detects ``--user`` / ``--user=…``, any short ``-u…`` (``-u``, ``-u=…``,
    ``-u1000``, ``-uroot``), and combined short clusters whose letters are only
    from ``itdu`` and include ``u`` (e.g. ``-itu``). Does not treat long bogus
    shorts like ``-volume`` as user flags.
    """
    for arg in extra_args:
        if arg == "--user" or arg.startswith("--user="):
            return arg
        # All short -u forms: -u, -u=, -u1000, -uroot, -unobody, …
        if arg.startswith("-u") and not arg.startswith("--"):
            return arg
        if arg.startswith("-") and not arg.startswith("--") and "=" not in arg:
            letters = arg[1:]
            if (
                letters.isalpha()
                and "u" in letters
                and set(letters) <= _DOCKER_COMBINED_SHORT_LETTERS
            ):
                return arg
    return None


def reject_docker_user_extra_args(
    extra_args: tuple[str, ...] | list[str],
) -> None:
    """Fail fast: container user is owned by clusterctl (host uid:gid)."""
    hit = extra_args_user_flag(extra_args)
    if hit is not None:
        raise ClusterctlError(f"{_USER_FORBIDDEN_MSG} (got {hit!r})")


def reject_docker_extra_args(extra_args: tuple[str, ...] | list[str]) -> None:
    """Reject detach and user overrides in ``execution.extra_args``."""
    reject_docker_detach_extra_args(extra_args)
    reject_docker_user_extra_args(extra_args)


def host_docker_user_spec() -> str | None:
    """Return ``uid:gid`` for ``docker run --user``, or ``None`` if unavailable."""
    try:
        return f"{os.getuid()}:{os.getgid()}"
    except AttributeError:
        return None


def container_nonroot_nss_preamble() -> str:
    """Bash snippet: fake passwd/group via nss_wrapper for non-root ``--user``.

    Runs inside the container after ``HOME`` exists. No-op for uid 0. Exits with
    a clear error if ``libnss_wrapper.so`` is missing (required for git/ssh).
    """
    so = shlex.quote(CONTAINER_NSS_WRAPPER_SO)
    user = shlex.quote(CONTAINER_NSS_USER)
    home = shlex.quote(CONTAINER_HOME)
    return (
        f'if [ "$(id -u)" -ne 0 ]; then '
        f"if [ ! -f {so} ]; then "
        f'echo "docker: nss_wrapper required for non-root --user '
        f'(missing {CONTAINER_NSS_WRAPPER_SO}; use krang >=336 or install '
        f'nss_wrapper)" >&2; '
        f"exit 1; "
        f"fi; "
        f'printf "%s:x:%s:%s:%s:%s:/bin/bash\\n" {user} "$(id -u)" "$(id -g)" '
        f"{user} {home} > \"$HOME/passwd\"; "
        f'printf "%s:x:%s:\\n" {user} "$(id -g)" > "$HOME/group"; '
        f'export NSS_WRAPPER_PASSWD="$HOME/passwd"; '
        f'export NSS_WRAPPER_GROUP="$HOME/group"; '
        f"export LD_PRELOAD={so}${{LD_PRELOAD:+:$LD_PRELOAD}}; "
        f"export USER={user} LOGNAME={user}; "
        f"fi"
    )


@dataclass(frozen=True)
class PreparedContainerSshKey:
    """Per-run host staging for the container SSH bind-mount.

    ``key_path`` is mounted read-only at ``CONTAINER_SSH_KEY``. Entry points
    (``run_docker_container`` / ``run_docker_smoke``) call ``preflight_docker``
    before prepare, then ``cleanup()`` in ``finally`` after the run so concurrent
    jobs never share one file.
    """

    key_path: Path
    staging_dir: Path

    def cleanup(self) -> None:
        shutil.rmtree(self.staging_dir, ignore_errors=True)


def prepare_container_ssh_key(
    ssh_key: Path,
    *,
    staging_parent: Path,
) -> PreparedContainerSshKey:
    """Copy SSH key into a unique temp dir (mode 0700/0600) for the container mount.

    GitLab File variables (and some CI temp paths) are often 0644/0664; OpenSSH
    refuses them with ``UNPROTECTED PRIVATE KEY FILE`` / ``bad permissions``.

    Staging is ``tempfile.mkdtemp(prefix="atlas-ssh-", dir=staging_parent)``.
    Callers must pass ``docker_ssh_staging_parent(workspace_root)``
    (``workspace/<cluster_id>/.atlas-ssh``) so the bind-mount source lies under
    the already-shared workspace tree — Docker Desktop / snap frequently deny
    mounts from host ``/tmp``, and we do **not** write identity under controller
    ``.cache/``. Unique ``atlas-ssh-*`` dirs keep parallel runs from sharing one
    key file (unlike the legacy single ``.cache/docker-identity/id_rsa``).
    Container mount target remains ``CONTAINER_SSH_KEY`` (``/tmp/atlas-ssh/id_rsa``).

    Entry points call ``preflight_docker`` first; this still re-checks the source
    key and raises ``ClusterctlError`` (never a bare ``FileNotFoundError`` /
    ``OSError`` from ``mkdtemp`` or copy) so direct callers get the same UX and
    no temp dir is left behind on failure.
    """
    source = ssh_key.expanduser().resolve()
    ssh_error = check_ssh_key(source)
    if ssh_error:
        raise ClusterctlError(f"docker: {ssh_error}")

    staging: Path | None = None
    try:
        parent = staging_parent.expanduser().resolve()
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="atlas-ssh-", dir=str(parent)))
        staging.chmod(0o700)
        dest = staging / "id_rsa"
        dest.write_bytes(source.read_bytes())
        dest.chmod(0o600)
    except OSError as exc:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        raise ClusterctlError(f"docker: failed to stage SSH key: {exc}") from exc
    except Exception:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return PreparedContainerSshKey(key_path=dest, staging_dir=staging)


def clusterctl_inner_argv(stripped_argv: list[str]) -> list[str]:
    """Build ``python3 -m clusterctl …`` argv for execution inside the container."""
    tokens = list(stripped_argv)
    if (
        tokens
        and not tokens[0].startswith("-")
        and tokens[0] not in CLUSTER_SUBCOMMANDS
    ):
        tokens = tokens[1:]
    return ["python3", "-m", "clusterctl", *tokens]


def _docker_local_playbook_mounts(ctx: ClusterContext) -> list[tuple[Path, Path]]:
    """Resolve extra bind-mounts for local playbook repos (schema v2 phase runner only)."""
    require_phase_runner(ctx)
    playbooks = effective_playbooks_config(ctx)
    return collect_local_playbook_docker_mounts(
        playbooks,
        repo_root_path=ctx.repo_root.resolve(),
    )


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def external_config_bind_mount_roots(ctx: ClusterContext) -> list[Path]:
    """Host paths from ``.config`` / env that sit outside ``ATLAS_CLUSTER_ROOT``.

    Sibling inventory layouts (``clusters.path`` + ``workspace.path`` under one parent)
    collapse to a single parent bind-mount when possible.
    """
    repo = ctx.repo_root.resolve()
    clusters = clusters_root(repo).resolve()
    ws_parent = workspace_parent(repo).resolve()
    ws_cluster = ctx.workspace_root.resolve()

    external: list[Path] = []
    for path in (clusters, ws_parent, ws_cluster):
        if _is_under(path, repo) or path == repo:
            continue
        external.append(path)
    if not external:
        return []

    try:
        common = Path(os.path.commonpath([str(p) for p in external])).resolve()
    except ValueError:
        common = None

    if (
        common is not None
        and common != Path("/")
        and not _is_under(common, repo)
        and len(common.parts) >= 3
        and all(_is_under(p, common) or p == common for p in external)
        and all(len(p.parts) - len(common.parts) <= 4 for p in external)
    ):
        return [common]

    roots: list[Path] = []
    for path in sorted(set(external), key=lambda p: len(p.parts)):
        if any(path == root or _is_under(path, root) for root in roots):
            continue
        roots = [root for root in roots if not _is_under(root, path)]
        roots.append(path)
    return roots


def _ownership_fix_paths(ctx: ClusterContext) -> list[Path]:
    """Host paths for the emergency ownership helper / unit tests.

    Not used by the normal docker executor path (container runs as host
    ``uid:gid``). Scope stays narrow — never an entire inventory checkout
    (``.git`` + ``clusters/`` + unrelated trees):

    - **per-cluster** workspace only (``ctx.workspace_root`` /
      ``workspace/<cluster_id>/``) — never the shared workspace parent that
      holds sibling cluster trees
    - controller leftovers (``.cache/``, legacy ``tfstate-repo/``, …)
    - inventory ``tfstate/`` and ``.git/`` only (mode B durable writes + git meta)

    SSH identity staging is per-run under
    ``workspace/<cluster_id>/.atlas-ssh/atlas-ssh-*`` (removed in ``finally``).
    Controller ``.cache/`` may still appear here for pip / stale leftovers only.
    """
    from clusterctl.paths import atlas_inventory_root

    repo = ctx.repo_root.resolve()
    clusters = clusters_root(repo).resolve()
    ws_cluster = ctx.workspace_root.resolve()
    inv_root = atlas_inventory_root(repo).resolve()

    candidates: list[Path] = [
        # This run's runtime only — not workspace/ siblings (ci/jenkins, …).
        ws_cluster,
        repo / "tfstate-repo",  # legacy mode A — keep reclaiming when present
        # Leftover CI pip cache / old docker-identity; identity no longer written here.
        repo / ".cache",
        repo / ".cluster-active",
        repo / ".config",
        repo / "plan.json",
        *sorted(repo.glob("tfstate-repo.local.bak-*")),
        *sorted(repo.glob("tfstate-repo.legacy.bak*")),
    ]

    # Mode B: durable TF + git metadata under inventory — never clusters/.
    if not _is_under(inv_root, repo) and inv_root != repo:
        candidates.append(inv_root / "tfstate")
        candidates.append(inv_root / ".git")
    elif _is_under(clusters, repo) or clusters == repo / "clusters":
        # Inventory is the product clusters/ tree under the controller — rare.
        pass

    # Preserve order, drop missing / duplicates / paths covered by a parent.
    out: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if not resolved.exists():
            continue
        if any(resolved == parent or _is_under(resolved, parent) for parent in out):
            continue
        out = [parent for parent in out if not _is_under(parent, resolved)]
        out.append(resolved)
    return out


def fix_bind_mount_ownership(ctx: ClusterContext) -> None:
    """Emergency ``chown`` of bind mounts back to the host uid.

    ``run_docker_container`` does **not** call this (container already runs as
    host ``uid:gid``). There is no CLI entrypoint. Kept for unit tests and
    manual Python invocation. For legacy root-owned trees, operators should
    ``sudo chown`` on the host instead. Paths come from
    ``_ownership_fix_paths`` (per-cluster workspace, inventory ``tfstate/`` /
    ``.git``, controller leftovers — never the shared workspace parent or
    whole inventory ``clusters/``).
    """
    try:
        uid = os.getuid()
        gid = os.getgid()
    except AttributeError:
        return
    if uid == 0:
        return
    if not docker_cli_available():
        return

    paths = _ownership_fix_paths(ctx)
    if not paths:
        return

    image_ref = resolve_docker_image_ref(ctx.execution.docker)
    cmd: list[str] = ["docker", "run", "--rm"]
    for path in paths:
        cmd.extend(["-v", f"{path}:{path}"])
    cmd.append(image_ref)
    cmd.extend(["chown", "-R", f"{uid}:{gid}", *[str(p) for p in paths]])

    print(
        f"docker: chown -R {uid}:{gid} → {', '.join(str(p) for p in paths)}",
        file=sys.stderr,
    )
    subprocess.run(cmd, check=False)


def build_docker_mounts(ctx: ClusterContext, *, ssh_key_host: Path) -> list[str]:
    """Bind-mount controller checkout, external inventory/workspace, local playbook repos.

    ``ssh_key_host`` must be a mode-0600 file from ``prepare_container_ssh_key``
    (or equivalent); it is mounted read-only at ``CONTAINER_SSH_KEY``.
    """
    repo_root = ctx.repo_root.resolve()
    ssh_key = ssh_key_host.expanduser().resolve()
    clusters = clusters_root(repo_root).resolve()
    if not clusters.is_dir():
        raise ClusterctlError(
            f"docker: clusters path missing for bind-mount: {clusters} "
            f"(set clusters.path in .config/config.yaml or {ENV_CLUSTERS_ROOT})"
        )

    mounts = [
        "-v",
        f"{repo_root}:{repo_root}:rw",
        "-v",
        f"{ssh_key}:{CONTAINER_SSH_KEY}:ro",
    ]

    for mount_root in external_config_bind_mount_roots(ctx):
        if not mount_root.exists():
            mount_root.mkdir(parents=True, exist_ok=True)
        if _is_under(mount_root, repo_root) or mount_root == repo_root:
            continue
        mounts.extend(["-v", f"{mount_root}:{mount_root}:rw"])

    for host_path, container_path in _docker_local_playbook_mounts(ctx):
        mounts.extend(["-v", f"{host_path}:{container_path}:ro"])

    return mounts


def preflight_docker_workspace(ctx: ClusterContext) -> None:
    """Ensure host workspace ansible dirs exist before container start (bind-mounted rw)."""
    assert_no_legacy_repo_root_ansible(ctx.repo_root)
    ensure_workspace_ansible_dirs(ctx.workspace_root)


def build_container_env(ctx: ClusterContext) -> dict[str, str]:
    ws = ctx.workspace_root.resolve()
    preflight_docker_workspace(ctx)

    repo = ctx.repo_root.resolve()
    env: dict[str, str] = {
        "ATLAS_CLUSTER_ROOT": str(repo),
        ENV_CLUSTERS_ROOT: str(clusters_root(repo).resolve()),
        ENV_WORKSPACE_ROOT: str(workspace_parent(repo).resolve()),
        "CLUSTER_ID": ctx.cluster_id,
        "CLUSTER_WORKSPACE_ID": ctx.workspace_id,
        "CLUSTER_WORKSPACE_ROOT": str(ws),
        ENV_FORCE_LOCAL: "1",
        "HOME": CONTAINER_HOME,
        "SSH_KEY": CONTAINER_SSH_KEY,
        "ANSIBLE_PRIVATE_KEY_FILE": CONTAINER_SSH_KEY,
    }

    configure_workspace_ansible_env(
        env,
        ws,
        workspace_id=ctx.workspace_id,
        controller_temp="container",
        ensure_dirs=False,
    )
    validate_workspace_ansible_env(
        env,
        ws,
        workspace_id=ctx.workspace_id,
        controller_temp="container",
    )

    for key in PASSTHROUGH_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            env[key] = value

    # Mounted SSH key (build_docker_mounts); ignore any host GIT_SSH_COMMAND.
    env["GIT_SSH_COMMAND"] = (
        f"ssh -i {CONTAINER_SSH_KEY} -o IdentitiesOnly=yes "
        "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    )
    # Mounted .git may not match container identity in /etc/passwd; keep
    # safe.directory=* so git fetch works under host uid:gid.
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "safe.directory"
    env["GIT_CONFIG_VALUE_0"] = "*"
    return env


def build_docker_run_command(
    ctx: ClusterContext,
    inner_argv: list[str],
    *,
    ssh_key_host: Path,
) -> list[str]:
    """Assemble full ``docker run … python3 -m clusterctl …`` command.

    Caller must run ``preflight_docker(ctx)`` before prepare/mount, then pass
    ``ssh_key_host`` from ``prepare_container_ssh_key`` (caller owns cleanup).
    This helper does **not** re-run preflight — avoids staging the key when CLI
    or SSH checks would fail. It still rejects ``-d``/``--detach`` and
    ``--user``/``-u`` in ``execution.extra_args`` (defense in depth for direct
    callers). Appends ``--user`` host uid:gid after ``extra_args`` so clusterctl
    always owns the container user.
    """
    extra_args = ctx.execution.docker.extra_args
    reject_docker_extra_args(extra_args)

    image_ref = resolve_docker_image_ref(ctx.execution.docker)
    mounts = build_docker_mounts(ctx, ssh_key_host=ssh_key_host)
    container_env = build_container_env(ctx)

    cmd = ["docker", "run", "--rm"]
    container_name = docker_run_container_name()
    if container_name:
        cmd.extend(["--name", container_name])
        execution_id = os.environ.get(ENV_EXECUTION_ID, "").strip()
        if execution_id:
            cmd.extend(["--label", f"atlas.execution_id={execution_id}"])
    if sys.stdin.isatty() and sys.stdout.isatty():
        cmd.append("-it")
    else:
        cmd.append("-i")

    cmd.extend(mounts)
    cmd.extend(["-w", str(ctx.repo_root.resolve())])

    for key, value in container_env.items():
        cmd.extend(["-e", f"{key}={value}"])

    cmd.extend(extra_args)
    user_spec = host_docker_user_spec()
    if user_spec is not None:
        cmd.extend(["--user", user_spec])
    cmd.append(image_ref)

    inner_cmd_str = shlex.join(inner_argv)
    workdir = shlex.quote(str(ctx.repo_root.resolve()))
    # Hot Ansible tmp must live on container-local FS (not bind-mounted workspace).
    controller_tmp = shlex.quote(
        str(container_controller_ansible_tmp_dir(ctx.workspace_id))
    )
    home_dir = shlex.quote(CONTAINER_HOME)
    nss_setup = container_nonroot_nss_preamble()
    cmd.extend(
        [
            "bash",
            "-lc",
            (
                f"mkdir -p {controller_tmp} {home_dir} && "
                f"{nss_setup} && "
                f"cd {workdir} && exec {inner_cmd_str}"
            ),
        ]
    )
    return cmd


def format_docker_command(cmd: list[str]) -> str:
    return shlex.join(cmd)


def preflight_docker(ctx: ClusterContext) -> None:
    if not docker_cli_available():
        raise ClusterctlError(
            "docker execution requires docker CLI on PATH — "
            "install docker or use --executor local / execution.mode: local"
        )
    # Before prepare: detach would return from docker run immediately while
    # finally deletes the staged key the still-running container needs.
    # Also reject --user overrides (clusterctl sets host uid:gid).
    reject_docker_extra_args(ctx.execution.docker.extra_args)
    ssh_error = check_ssh_key(ctx.ssh_key.expanduser())
    if ssh_error:
        raise ClusterctlError(f"docker: {ssh_error}")

    _docker_local_playbook_mounts(ctx)


def run_docker_container(ctx: ClusterContext, argv: list[str]) -> int:
    """Re-exec clusterctl inside Docker image; returns process exit code."""
    stripped = strip_global_flags_from_argv(argv)
    inner = clusterctl_inner_argv(stripped)
    # Preflight before staging: missing docker/SSH must raise ClusterctlError
    # without writing a temp key copy.
    preflight_docker(ctx)
    prepared: PreparedContainerSshKey | None = None
    try:
        prepared = prepare_container_ssh_key(
            ctx.ssh_key,
            staging_parent=docker_ssh_staging_parent(ctx.workspace_root),
        )
        cmd = build_docker_run_command(ctx, inner, ssh_key_host=prepared.key_path)

        print(
            f"docker: {resolve_docker_image_ref(ctx.execution.docker)} → {' '.join(inner[3:])}",
            file=sys.stderr,
        )
        print(f"docker: {format_docker_command(cmd)}", file=sys.stderr)

        result = subprocess.run(cmd, check=False)
        return int(result.returncode)
    finally:
        if prepared is not None:
            prepared.cleanup()
        # Host --user owns new bind-mount writes; no post-run chown.


def dispatch_docker_if_needed(ctx: ClusterContext, argv: list[str]) -> int | None:
    """
    Run mutating command in Docker when execution.mode is docker.

    Returns exit code if dispatched, ``None`` to continue with local execution.
    """
    if not ctx.execution.is_docker:
        return None
    if is_inside_docker_container():
        return None
    return run_docker_container(ctx, argv)


def should_delegate_to_docker(ctx: ClusterContext) -> bool:
    return ctx.execution.is_docker and not is_inside_docker_container()
