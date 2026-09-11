"""Declarative phase filtering via playbook ``when`` (inventory predicates).

ADR 005: YAML ``stacks:`` is rejected at load — not applied to the plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from clusterctl.inventory import extract_inventory_groups
from clusterctl.playbooks_config import PhaseWhen, PlaybookEntrySpec, PlaybooksConfig


@dataclass(frozen=True)
class PhaseFilterContext:
    inventory_groups: frozenset[str]
    merged_vars: Mapping[str, Any]

    @classmethod
    def from_inventory(
        cls,
        inventory_path: str | Any,
        merged_vars: Mapping[str, Any],
    ) -> PhaseFilterContext:
        from pathlib import Path

        groups = extract_inventory_groups(Path(inventory_path))
        return cls(inventory_groups=frozenset(groups), merged_vars=merged_vars)


@dataclass(frozen=True)
class PhaseFilterResult:
    included: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]  # (phase_ref, reason)


def _var_matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool):
        return bool(actual) is expected
    return actual == expected


def evaluate_phase_when(
    when: PhaseWhen,
    ctx: PhaseFilterContext,
) -> str | None:
    """Return skip reason when the entry should be skipped, else None."""
    if when.inventory_groups_all:
        missing = [group for group in when.inventory_groups_all if group not in ctx.inventory_groups]
        if missing:
            return f"missing inventory groups (all): {', '.join(missing)}"

    if when.inventory_groups_any:
        if not any(group in ctx.inventory_groups for group in when.inventory_groups_any):
            return (
                "missing inventory groups (any): "
                + ", ".join(when.inventory_groups_any)
            )

    for key, expected in when.vars.items():
        actual = ctx.merged_vars.get(key)
        if not _var_matches(expected, actual):
            return f"var {key} expected {expected!r}, got {actual!r}"

    return None


def should_run_entry(
    entry: PlaybookEntrySpec,
    ctx: PhaseFilterContext,
) -> str | None:
    if entry.when.is_empty:
        return None
    return evaluate_phase_when(entry.when, ctx)


def filter_phases(
    phases: tuple[str, ...],
    playbooks: PlaybooksConfig,
    ctx: PhaseFilterContext,
) -> PhaseFilterResult:
    included: list[str] = []
    skipped: list[tuple[str, str]] = []
    for phase_ref in phases:
        _, entry = playbooks.resolve_entry(phase_ref)
        reason = should_run_entry(entry, ctx)
        if reason:
            skipped.append((phase_ref, reason))
            continue
        included.append(phase_ref)
    return PhaseFilterResult(included=tuple(included), skipped=tuple(skipped))
