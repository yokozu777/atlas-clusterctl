"""ADR 007 — inline phase aliases contract matrix (Phase 1 engine)."""

from __future__ import annotations

import unittest

from clusterctl.exceptions import ClusterctlError, PhaseAliasesRemovedError
from clusterctl.playbooks_config import (
    parse_cluster_config_v2_fragment,
    parse_phase_ref,
    parse_phases_config,
    phases_config_to_raw,
    resolve_phase_alias,
)

TARGET_INLINE_PHASES = [
    {"templates": "atlas-compute-provision/templates"},
    {"provision": "atlas-compute-provision/provision"},
    {"init": "atlas-node-foundation/init"},
]

TARGET_MIXED_BARE_AND_ALIAS = [
    "atlas-compute-provision/templates",
    {"provision": "atlas-compute-provision/provision"},
]


class PhasesInlineAliasesContractTest(unittest.TestCase):
    def test_inline_single_key_map_registers_alias(self) -> None:
        cfg = parse_phases_config(TARGET_INLINE_PHASES)
        assert cfg is not None
        self.assertEqual(
            cfg.phases,
            (
                "atlas-compute-provision/templates",
                "atlas-compute-provision/provision",
                "atlas-node-foundation/init",
            ),
        )
        self.assertEqual(
            cfg.phase_aliases["init"],
            "atlas-node-foundation/init",
        )
        self.assertEqual(
            resolve_phase_alias("templates", cfg.phase_aliases),
            "atlas-compute-provision/templates",
        )
        for ref in cfg.phases:
            parse_phase_ref(ref)

    def test_bare_repo_entry_allowed_without_alias(self) -> None:
        cfg = parse_phases_config(TARGET_MIXED_BARE_AND_ALIAS)
        assert cfg is not None
        self.assertEqual(cfg.phases[0], "atlas-compute-provision/templates")
        self.assertNotIn("templates", cfg.phase_aliases)
        self.assertEqual(
            cfg.phase_aliases["provision"],
            "atlas-compute-provision/provision",
        )

    def test_duplicate_alias_errors(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            parse_phases_config(
                [
                    {"init": "atlas-node-foundation/init"},
                    {"init": "atlas-k8s-core/cluster"},
                ]
            )
        self.assertIn("duplicate phase alias", str(ctx.exception))

    def test_duplicate_ref_errors_at_parse(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            parse_phases_config(
                [
                    {"a": "atlas-compute-provision/templates"},
                    {"b": "atlas-compute-provision/templates"},
                ]
            )
        self.assertIn("duplicate phase ref", str(ctx.exception))

    def test_duplicate_bare_ref_errors_at_parse(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            parse_phases_config(
                [
                    "atlas-compute-provision/templates",
                    "atlas-compute-provision/templates",
                ]
            )
        self.assertIn("duplicate phase ref", str(ctx.exception))

    def test_alias_with_slash_errors(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            parse_phases_config(
                [{"bad/name": "atlas-node-foundation/init"}]
            )
        self.assertIn("must not contain '/'", str(ctx.exception))

    def test_multi_key_map_errors(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            parse_phases_config(
                [
                    {
                        "a": "atlas-node-foundation/init",
                        "b": "atlas-k8s-core/cluster",
                    }
                ]
            )
        self.assertIn("exactly one key", str(ctx.exception))

    def test_top_level_phase_aliases_hard_rejected(self) -> None:
        with self.assertRaises(PhaseAliasesRemovedError) as ctx:
            parse_cluster_config_v2_fragment(
                {
                    "schema_version": 2,
                    "phases": ["atlas-compute-provision/templates"],
                    "phase_aliases": {
                        "templates": "atlas-compute-provision/templates",
                    },
                }
            )
        self.assertEqual(ctx.exception.code, "phase_aliases_removed")

    def test_dump_emits_inline_aliases_without_top_level_key(self) -> None:
        cfg = parse_phases_config(TARGET_INLINE_PHASES)
        assert cfg is not None
        raw = phases_config_to_raw(cfg)
        self.assertNotIn("phase_aliases", raw)
        self.assertEqual(raw["phases"], TARGET_INLINE_PHASES)

    def test_dump_rejects_duplicate_refs(self) -> None:
        from clusterctl.playbooks_config import PhasesConfig

        drifted = PhasesConfig(
            phases=(
                "atlas-compute-provision/templates",
                "atlas-compute-provision/templates",
            ),
            phase_aliases={
                "a": "atlas-compute-provision/templates",
                "b": "atlas-compute-provision/templates",
            },
        )
        with self.assertRaises(ClusterctlError) as ctx:
            phases_config_to_raw(drifted)
        self.assertIn("duplicate phase ref", str(ctx.exception))

    def test_dump_rejects_drifted_alias_target(self) -> None:
        from clusterctl.playbooks_config import PhasesConfig

        drifted = PhasesConfig(
            phases=("atlas-compute-provision/templates",),
            phase_aliases={"provision": "atlas-compute-provision/provision"},
        )
        with self.assertRaises(ClusterctlError) as ctx:
            phases_config_to_raw(drifted)
        self.assertIn("is not in phases:", str(ctx.exception))

    def test_dump_rejects_two_aliases_for_one_ref(self) -> None:
        from clusterctl.playbooks_config import PhasesConfig

        drifted = PhasesConfig(
            phases=("atlas-compute-provision/templates",),
            phase_aliases={
                "a": "atlas-compute-provision/templates",
                "b": "atlas-compute-provision/templates",
            },
        )
        with self.assertRaises(ClusterctlError) as ctx:
            phases_config_to_raw(drifted)
        self.assertIn("duplicate phase aliases", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
