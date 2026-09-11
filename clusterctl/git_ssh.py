"""Build ``GIT_SSH_COMMAND`` for git-over-ssh (repo sync and playbook phases)."""

from __future__ import annotations

import shlex


def git_ssh_command_has_identity(command: str) -> bool:
    """True when ``command`` already passes ``-i <key>`` to ssh."""
    tokens = command.split()
    for index, token in enumerate(tokens):
        if token == "-i" and index + 1 < len(tokens):
            return True
        if token.startswith("-i") and len(token) > 2:
            return True
    return False


def resolve_git_ssh_command(
    *,
    existing: str | None = None,
    ssh_key: str | None = None,
) -> str:
    """Build ``GIT_SSH_COMMAND``.

    Prefer an existing command that already pins ``-i`` (docker_executor sets
    this to ``/tmp/atlas-ssh/id_rsa``). Otherwise pin ``ssh_key`` explicitly.
    Never replace a keyed command with host-check-only ``ssh``.
    """
    existing_cmd = (existing or "").strip()
    if existing_cmd and git_ssh_command_has_identity(existing_cmd):
        return existing_cmd

    key = (ssh_key or "").strip()
    if key:
        return (
            f"ssh -i {shlex.quote(key)} -o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
        )
    if existing_cmd:
        return existing_cmd
    return "ssh -o StrictHostKeyChecking=no"
