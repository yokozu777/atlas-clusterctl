"""Shared git clone/update helpers for repository sync (role_repos + playbooks)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from clusterctl.exceptions import ClusterctlError
from clusterctl.git_ssh import git_ssh_command_has_identity, resolve_git_ssh_command
from clusterctl.logging_util import run_subprocess_logged
from clusterctl.user_config import git_ssh_key_from_user_config

_COMMIT_REF_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


@dataclass(frozen=True)
class GitSyncTarget:
    """Minimal git source descriptor for clone/fetch operations."""

    name: str
    url: str
    ref: str
    shallow: bool = True


def looks_like_commit(ref: str | None) -> bool:
    return bool(ref and _COMMIT_REF_RE.fullmatch(ref))


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def git_env(
    base: dict[str, str] | None = None,
    *,
    ssh_key: str | None = None,
) -> dict[str, str]:
    """Environment for git clone/fetch.

    Per-repo ``ssh_key`` (from ``PLAYBOOKS_*_SSH_KEY``) always pins ``-i``.
    Otherwise keep an existing ``GIT_SSH_COMMAND`` that already has ``-i``,
    then ``git.ssh_key`` in local config, then ``SSH_KEY``.
    """
    env = dict(os.environ if base is None else base)
    explicit = (ssh_key or "").strip()
    if explicit:
        env["GIT_SSH_COMMAND"] = resolve_git_ssh_command(
            existing=None,
            ssh_key=explicit,
        )
        return env

    existing = (env.get("GIT_SSH_COMMAND") or os.environ.get("GIT_SSH_COMMAND") or "").strip()
    if existing and git_ssh_command_has_identity(existing):
        env["GIT_SSH_COMMAND"] = existing
        return env

    configured = git_ssh_key_from_user_config()
    fallback = (
        str(configured)
        if configured is not None
        else ""
    ) or (env.get("SSH_KEY") or os.environ.get("SSH_KEY") or "").strip()
    env["GIT_SSH_COMMAND"] = resolve_git_ssh_command(
        existing=existing or None,
        ssh_key=fallback or None,
    )
    return env


def run_git(
    args: list[str],
    env: dict[str, str],
    *,
    check: bool = True,
    cwd: Path | None = None,
    log_streams: tuple[TextIO, TextIO] | None = None,
) -> int:
    cmd = ["git", *args]
    if log_streams is not None:
        result = run_subprocess_logged(
            cmd,
            cwd=cwd,
            env=env,
            log_streams=log_streams,
        )
    else:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        result = int(completed.returncode)
        if check and result != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise ClusterctlError(
                f"git {' '.join(args)} failed (exit {result})"
                + (f": {detail}" if detail else "")
            )
    if check and result != 0:
        raise ClusterctlError(f"git {' '.join(args)} failed (exit {result})")
    return result


def git_rev_parse(dest: Path, ref: str = "HEAD") -> str | None:
    if not is_git_repo(dest):
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", ref],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
    except OSError:
        return None
    return None


def git_clone_fresh(
    target: GitSyncTarget,
    dest: Path,
    env: dict[str, str],
    *,
    log_streams: tuple[TextIO, TextIO] | None = None,
) -> None:
    if not target.url or not target.ref:
        raise ClusterctlError(f"sync {target.name}: git source requires url and ref")

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if not dest.is_dir():
            raise ClusterctlError(f"sync {target.name}: {dest} is not a directory")
        if any(dest.iterdir()) and not is_git_repo(dest):
            raise ClusterctlError(
                f"sync {target.name}: {dest} exists but is not a git repository"
            )
        if is_git_repo(dest):
            shutil.rmtree(dest)

    ref = target.ref
    if looks_like_commit(ref):
        clone_cmd = ["clone"]
        if target.shallow:
            clone_cmd.extend(["--depth", "1"])
        clone_cmd.extend([target.url, str(dest)])
        run_git(clone_cmd, env, log_streams=log_streams)
        run_git(["-C", str(dest), "checkout", ref], env, log_streams=log_streams)
        return

    clone_cmd = ["clone"]
    if target.shallow:
        clone_cmd.extend(["--depth", "1", "--branch", ref, "--single-branch"])
    else:
        clone_cmd.extend(["--branch", ref])
    clone_cmd.extend([target.url, str(dest)])
    run_git(clone_cmd, env, log_streams=log_streams)


def git_fetch_and_checkout(
    target: GitSyncTarget,
    dest: Path,
    env: dict[str, str],
    *,
    log_streams: tuple[TextIO, TextIO] | None = None,
) -> None:
    if not target.ref:
        raise ClusterctlError(f"sync {target.name}: git source requires ref")

    ref = target.ref
    if target.shallow:
        run_git(
            ["-C", str(dest), "fetch", "--depth", "1", "origin", ref],
            env,
            log_streams=log_streams,
        )
    else:
        run_git(["-C", str(dest), "fetch", "origin", ref], env, log_streams=log_streams)

    checkout_rc = run_git(
        ["-C", str(dest), "checkout", "--force", ref],
        env,
        check=False,
        log_streams=log_streams,
    )
    if checkout_rc != 0:
        run_git(
            ["-C", str(dest), "checkout", "--force", "FETCH_HEAD"],
            env,
            log_streams=log_streams,
        )
    if target.shallow:
        run_git(
            ["-C", str(dest), "reset", "--hard", "FETCH_HEAD"],
            env,
            log_streams=log_streams,
        )
