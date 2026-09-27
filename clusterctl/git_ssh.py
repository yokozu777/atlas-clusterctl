"""Build ``GIT_SSH_COMMAND`` for git-over-ssh (repo sync and playbook phases)."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

# Source path → staged 0600 copy (process lifetime). Docker file binds and
# GitLab File variables are often 0644/0777; OpenSSH refuses them.
_STAGED_IDENTITIES: dict[str, str] = {}


def normalize_openssh_private_key_bytes(data: bytes) -> bytes:
    """Return UTF-8 LF private-key bytes (no BOM).

    Windows Docker file binds and Notepad/PowerShell saves often add UTF-16, a
    UTF-8 BOM, or CRLF. Alpine OpenSSH then fails with
    ``error in libcrypto: unsupported``.
    """
    if not data:
        return data
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16")
    elif data.startswith(b"\xef\xbb\xbf"):
        text = data[3:].decode("utf-8")
    elif data[:64].count(b"\x00") >= 8:
        text = data.decode("utf-16")
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-16")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    if text and not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _try_repair_openssh_identity(path: Path) -> None:
    """Best-effort PEM rewrite when ``ssh-keygen -y`` cannot load ``path``."""
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        return
    try:
        check = subprocess.run(
            [ssh_keygen, "-y", "-f", str(path)],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    if check.returncode == 0:
        return
    try:
        subprocess.run(
            [ssh_keygen, "-p", "-P", "", "-N", "", "-m", "PEM", "-f", str(path)],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    try:
        path.chmod(0o600)
    except OSError:
        pass


def git_ssh_command_has_identity(command: str) -> bool:
    """True when ``command`` already passes ``-i <key>`` to ssh."""
    tokens = command.split()
    for index, token in enumerate(tokens):
        if token == "-i" and index + 1 < len(tokens):
            return True
        if token.startswith("-i") and len(token) > 2:
            return True
    return False


def identity_file_from_git_ssh_command(command: str) -> str | None:
    """Return the first ``-i`` path in ``command``, if any."""
    tokens = command.split()
    for index, token in enumerate(tokens):
        if token == "-i" and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith("-i") and len(token) > 2:
            return token[2:]
    return None


def ensure_openssh_private_key(path: str) -> str:
    """Return ``path``, or a 0600 LF copy OpenSSH can load.

    Compose bind-mounts and CI File variables often show mode 0644/0777.
    OpenSSH then prints ``UNPROTECTED PRIVATE KEY FILE`` / ``bad permissions``.
    Windows binds keep those modes and often add CRLF/BOM; a raw copy still
    fails with ``error in libcrypto: unsupported``. Missing paths are returned
    unchanged so callers fail with a normal git error.
    """
    raw = (path or "").strip()
    if not raw:
        return raw
    src = Path(raw).expanduser()
    try:
        resolved = str(src.resolve())
    except OSError:
        return raw
    cached = _STAGED_IDENTITIES.get(resolved)
    if cached and Path(cached).is_file():
        return cached
    if not src.is_file():
        return raw
    try:
        mode = src.stat().st_mode & 0o777
        contents = src.read_bytes()
    except OSError:
        return raw
    normalized = normalize_openssh_private_key_bytes(contents)
    if (mode & 0o077) == 0 and normalized == contents:
        return raw
    dest_dir = Path(tempfile.mkdtemp(prefix="atlas-ssh-git-"))
    dest_dir.chmod(0o700)
    dest = dest_dir / src.name
    dest.write_bytes(normalized)
    dest.chmod(0o600)
    _try_repair_openssh_identity(dest)
    staged = str(dest)
    _STAGED_IDENTITIES[resolved] = staged
    return staged


def resolve_git_ssh_command(
    *,
    existing: str | None = None,
    ssh_key: str | None = None,
) -> str:
    """Build ``GIT_SSH_COMMAND``.

    Prefer an existing command that already pins ``-i`` (docker_executor sets
    this to ``/tmp/atlas-ssh/id_rsa``). Otherwise pin ``ssh_key`` explicitly.
    Never replace a keyed command with host-check-only ``ssh``.
    Identity files that OpenSSH would reject are copied to mode 0600 first.
    """
    existing_cmd = (existing or "").strip()
    if existing_cmd and git_ssh_command_has_identity(existing_cmd):
        ident = identity_file_from_git_ssh_command(existing_cmd)
        if ident:
            safe = ensure_openssh_private_key(ident)
            if safe != ident:
                return resolve_git_ssh_command(existing=None, ssh_key=safe)
        return existing_cmd

    key = (ssh_key or "").strip()
    if key:
        key = ensure_openssh_private_key(key)
        return (
            f"ssh -i {shlex.quote(key)} -o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
        )
    if existing_cmd:
        return existing_cmd
    return "ssh -o StrictHostKeyChecking=no"
