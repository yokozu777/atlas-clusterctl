"""Cluster CLI errors."""

from __future__ import annotations


class ClusterctlError(Exception):
    """Base error with user-facing message."""


class ClusterNotFoundError(ClusterctlError):
    pass


class ClusterNotSelectedError(ClusterctlError):
    pass


class StageNotFoundError(ClusterctlError):
    pass


class PlaybookNotFoundError(ClusterctlError):
    pass


class WorkspaceResetAborted(ClusterctlError):
    pass


class StacksRemovedError(ClusterctlError):
    """YAML ``cluster.yaml`` key ``stacks:`` was removed (ADR 005).

    Validate reports this as issue code ``stacks_removed`` (not a generic load
    failure). Tombstone name matches the forbidden key on purpose.
    """

    code = "stacks_removed"
    hint = (
        "omit stacks:; edit phases: instead — "
        "see docs/adr/005-remove-cluster-stacks.md"
    )

    def __init__(self, source: str) -> None:
        self.source = str(source).strip() or "(unknown)"
        super().__init__(
            f"cluster.yaml key stacks: was removed ({self.source}) — "
            f"plan SoT is phases: — {self.hint}"
        )

    def with_source(self, source: str) -> StacksRemovedError:
        """Return the same error with a more specific source path."""
        return StacksRemovedError(source)


class PhaseAliasesRemovedError(ClusterctlError):
    """YAML ``cluster.yaml`` key ``phase_aliases:`` was removed (ADR 007).

    Validate reports this as issue code ``phase_aliases_removed``. Short CLI
    names live inline in ``phases:`` (``- alias: repo/entry``).
    """

    code = "phase_aliases_removed"
    hint = (
        "omit phase_aliases:; put aliases inline in phases: "
        "(- templates: atlas-compute-provision/templates) — "
        "see docs/adr/007-phases-inline-aliases.md"
    )

    def __init__(self, source: str) -> None:
        self.source = str(source).strip() or "(unknown)"
        super().__init__(
            f"cluster.yaml key phase_aliases: was removed ({self.source}) — "
            f"{self.hint}"
        )

    def with_source(self, source: str) -> PhaseAliasesRemovedError:
        return PhaseAliasesRemovedError(source)
