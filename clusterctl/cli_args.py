"""Global CLI flags (--cluster, --executor) usable before or after subcommand."""

from __future__ import annotations

from clusterctl.exceptions import ClusterctlError

SUBCOMMANDS = frozenset(
    {
        "use",
        "run",
        "plan",
        "stages",
        "list",
        "init",
        "config",
        "workspace",
        "validate",
        "smoke",
        "playbooks",
        "repos",
        "docker",
        "limits",
        "vars",
    }
)

# flag -> argparse dest (value-consuming options)
GLOBAL_VALUE_FLAGS: dict[str, str] = {
    "--cluster": "cluster",
    "--executor": "executor",
}


def _split_prog(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        return "cluster", []
    first = argv[0]
    if first in SUBCOMMANDS or first.startswith("-"):
        return "cluster", list(argv)
    return first, list(argv[1:])


def _parse_value_flag(token: str) -> tuple[str, str] | None:
    for flag in GLOBAL_VALUE_FLAGS:
        if token == flag:
            return flag, ""
        prefix = f"{flag}="
        if token.startswith(prefix):
            return flag, token[len(prefix) :]
    return None


def normalize_global_argv(argv: list[str] | None) -> list[str]:
    """
    Hoist ``--cluster`` / ``--executor`` to immediately after the program name.

    Both of these are equivalent after normalization::

        ./cluster --cluster lab validate
        ./cluster validate --cluster lab
    """
    prog, rest = _split_prog(list(argv or []))
    extracted: list[str] = []
    remaining: list[str] = []
    seen: dict[str, str] = {}

    index = 0
    while index < len(rest):
        token = rest[index]
        parsed = _parse_value_flag(token)
        if parsed is None:
            remaining.append(token)
            index += 1
            continue

        flag, inline_value = parsed
        dest = GLOBAL_VALUE_FLAGS[flag]
        if inline_value:
            value = inline_value
            index += 1
        elif index + 1 < len(rest) and not rest[index + 1].startswith("-"):
            value = rest[index + 1]
            index += 2
        else:
            remaining.extend(rest[index:])
            break

        if dest in seen:
            if seen[dest] != value:
                raise ClusterctlError(
                    f"conflicting {flag} values: {seen[dest]!r} and {value!r}"
                )
            continue
        seen[dest] = value
        extracted.extend([flag, value])

    return [prog, *extracted, *remaining]


def strip_global_flags_from_argv(argv: list[str]) -> list[str]:
    """Remove global flags from argv (e.g. before docker re-exec)."""
    stripped: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        parsed = _parse_value_flag(token)
        if parsed is None:
            stripped.append(token)
            index += 1
            continue

        flag, inline_value = parsed
        if inline_value:
            index += 1
        else:
            index += 2
    return stripped
