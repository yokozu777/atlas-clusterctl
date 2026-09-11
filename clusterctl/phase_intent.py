"""Phase intent inferred from ``phases:`` (ADR 005 SoT).

Used by validate to cross-check inventory groups. Not YAML ``stacks:`` —
that key is rejected at cluster.yaml load (Phase 4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# Keep in sync with public ``_template/*/cluster.yaml`` phase refs.
PHASE_INTENT_REFS: dict[str, frozenset[str]] = {
    "k8s": frozenset(
        {
            "atlas-k8s-core/cluster",
            "atlas-k8s-addons/addons",
        }
    ),
    "infra": frozenset(
        {
            "atlas-infra-edge/infra",
            "atlas-node-foundation/init-infra",
            "atlas-node-foundation/init-infra-post",
        }
    ),
    "postgresql": frozenset({"atlas-postgresql/cluster"}),
    "redis": frozenset({"atlas-redis/cluster"}),
    "kafka": frozenset({"atlas-kafka/cluster"}),
}


@dataclass(frozen=True)
class PhaseIntent:
    """Inventory-intent flags derived from ``phases:`` (+ ``provision_stack``)."""

    infra: bool
    k8s: bool
    postgresql: bool
    mysql: bool
    redis: bool
    kafka: bool
    provision_stack: str

    @property
    def data(self) -> bool:
        return self.postgresql or self.mysql or self.redis or self.kafka


def _provision_stack(merged_vars: dict) -> str:
    return str(merged_vars.get("provision_stack", "k8s")).strip() or "k8s"


def infer_phase_intent(
    phase_refs: Sequence[str],
    merged_vars: dict,
) -> PhaseIntent:
    """Derive inventory-intent flags from ``phases:``."""
    phase_set = {str(ref).strip() for ref in phase_refs if str(ref).strip()}
    provision_stack = _provision_stack(merged_vars)

    def _has(name: str) -> bool:
        return bool(phase_set & PHASE_INTENT_REFS[name])

    return PhaseIntent(
        infra=_has("infra"),
        k8s=_has("k8s"),
        postgresql=_has("postgresql"),
        # No dedicated phase matrix yet — keep provision_stack for mysql only.
        mysql=provision_stack == "mysql",
        redis=_has("redis"),
        kafka=_has("kafka"),
        provision_stack=provision_stack,
    )
