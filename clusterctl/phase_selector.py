"""CLI phase window selector: ``--phases`` grammar (ADR 008)."""

from __future__ import annotations

from dataclasses import dataclass

from clusterctl.exceptions import ClusterctlError

_RANGE_SEP = ".."

# Lookalikes rejected early with distinct hints (ADR 008).
_RANGE_ELLIPSIS_LOOKALIKES = (
    "\u2026",  # … horizontal ellipsis
    "\u2025",  # ‥ two-dot leader
    "\u22ef",  # ⋯ midline horizontal ellipsis
)
_DASH_LOOKALIKES = (
    "\u2013",  # – en dash
    "\u2014",  # — em dash
)


@dataclass(frozen=True)
class PhaseRangeSelector:
    """Inclusive phase window as unresolved boundary names (alias or ``repo/entry``).

    Feeds ``resolve_phase_execution_plan(from_phase=..., to_phase=...)``.
    For a single phase, ``from_phase == to_phase``.
    """

    from_phase: str
    to_phase: str

    @property
    def is_single(self) -> bool:
        return self.from_phase == self.to_phase


@dataclass(frozen=True)
class PhaseListSelector:
    """Explicit phase set (ADR 008 Phase 3) — unresolved names from CSV.

    Plan order follows leaf ``phases:``, not CSV order.
    """

    names: tuple[str, ...]


@dataclass(frozen=True)
class CliPhaseWindow:
    """Resolved CLI window for ``plan``/``run`` (range **or** explicit set)."""

    from_phase: str | None = None
    to_phase: str | None = None
    only_phases: tuple[str, ...] | None = None


def parse_phases_selector(raw: str) -> PhaseRangeSelector | PhaseListSelector:
    """Parse ``--phases`` value into a range or explicit list.

    Accepted:
      - single token: ``init`` → range
      - range: ``provision..k8s-addons`` (whitespace around ``..`` trimmed)
      - CSV list (Phase 3): ``provision,init,k8s-core`` (2+ non-empty items)

    Rejected:
      - mixing ``..`` and ``,``
      - empty items / empty selector
      - Unicode ellipsis lookalikes for ``..``
      - Unicode en/em dash (use ASCII ``-`` in names or ``..`` for ranges)
    """
    if raw is None:
        raise ClusterctlError("phases selector is empty")
    text = str(raw).strip()
    if not text:
        raise ClusterctlError("phases selector is empty")

    for ch in _RANGE_ELLIPSIS_LOOKALIKES:
        if ch in text:
            raise ClusterctlError(
                f"phases selector must use ASCII '..' for ranges "
                f"(got lookalike {ch!r} in {text!r} — ADR 008)"
            )
    for ch in _DASH_LOOKALIKES:
        if ch in text:
            raise ClusterctlError(
                f"phases selector must use ASCII '-' in names "
                f"or ASCII '..' for ranges "
                f"(got lookalike {ch!r} in {text!r} — ADR 008)"
            )

    if "," in text:
        if _RANGE_SEP in text:
            raise ClusterctlError(
                "do not mix '..' range and comma list in --phases "
                "(use start..end or a,b,c — ADR 008)"
            )
        parts = [part.strip() for part in text.split(",")]
        if any(not part for part in parts):
            raise ClusterctlError(
                f"phases list entries must be non-empty (got {text!r})"
            )
        if len(parts) < 2:
            raise ClusterctlError(
                f"phases list requires at least two names separated by commas "
                f"(got {text!r}; for a single phase use --phases NAME without commas)"
            )
        seen: set[str] = set()
        for name in parts:
            if name in seen:
                raise ClusterctlError(f"duplicate phase name {name!r} in --phases list")
            seen.add(name)
        return PhaseListSelector(names=tuple(parts))

    if _RANGE_SEP in text:
        parts = text.split(_RANGE_SEP)
        if len(parts) != 2:
            raise ClusterctlError(
                f"phases selector must contain exactly one '{_RANGE_SEP}' "
                f"for a range, got {text!r}"
            )
        start = parts[0].strip()
        end = parts[1].strip()
        if not start or not end:
            raise ClusterctlError(
                f"phases range boundaries must be non-empty "
                f"(got {text!r} — use start{_RANGE_SEP}end)"
            )
        return PhaseRangeSelector(from_phase=start, to_phase=end)

    return PhaseRangeSelector(from_phase=text, to_phase=text)


def resolve_cli_phase_window(
    *,
    phases_selector: str | None = None,
) -> CliPhaseWindow:
    """Resolve CLI window for ``plan``/``run`` from ``--phases`` only (ADR 008 Phase 4).

    ``None`` / omitted selector → full effective phase list.
    """
    if phases_selector is None:
        return CliPhaseWindow()
    sel = parse_phases_selector(phases_selector)
    if isinstance(sel, PhaseListSelector):
        return CliPhaseWindow(only_phases=sel.names)
    return CliPhaseWindow(from_phase=sel.from_phase, to_phase=sel.to_phase)
