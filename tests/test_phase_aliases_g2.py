"""Tests for PR-G2 / ADR 007: phase aliases from phases: YAML (no Python alias table)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.exceptions import ClusterctlError, PhaseAliasesRemovedError
from clusterctl.phase_plan import resolve_phase_boundary
from clusterctl.pipeline import load_pipeline
from clusterctl.pipeline_fixture import seed_org_baseline_fixture
from clusterctl.playbooks_config import (
    PhasesConfig,
    parse_cluster_config_v2_fragment,
    parse_phases_config,
    phase_ref_to_alias_map,
    stage_name_for_phase_ref,
)


class PhaseAliasesG2Test(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT",)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_unknown_alias_raises_without_python_fallback(self) -> None:
        phases = PhasesConfig(
            phases=("atlas-compute-provision/provision",),
            phase_aliases={"provision": "atlas-compute-provision/provision"},
        )
        with self.assertRaises(ClusterctlError) as ctx:
            resolve_phase_boundary("templates", phases)
        self.assertIn("unknown phase boundary", str(ctx.exception))
        self.assertIn("provision", str(ctx.exception))

    def test_stage_name_for_phase_ref_uses_yaml_aliases(self) -> None:
        aliases = {
            "provision": "atlas-compute-provision/provision",
            "templates": "atlas-compute-provision/templates",
        }
        self.assertEqual(
            stage_name_for_phase_ref("atlas-compute-provision/provision", aliases),
            "provision",
        )
        self.assertEqual(
            stage_name_for_phase_ref("rare-stack/install", aliases),
            "install",
        )

    def test_phase_ref_to_alias_map_first_alias_wins(self) -> None:
        inverse = phase_ref_to_alias_map(
            {
                "alpha": "repo/entry",
                "beta": "repo/entry",
            }
        )
        self.assertEqual(inverse["repo/entry"], "alpha")

    def test_pipeline_stages_carry_phase_ref_from_org_baseline(self) -> None:
        stages = load_pipeline(self.root)
        self.assertGreaterEqual(len(stages), 4)
        for stage in stages:
            self.assertTrue(stage.phase_ref)
            self.assertIn("/", stage.phase_ref)

    def test_custom_alias_inline_in_phases_yaml(self) -> None:
        path = self.root / "clusters" / "default" / "default" / "cluster.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        phases = []
        for item in data["phases"]:
            ref = (
                next(iter(item.values()))
                if isinstance(item, dict)
                else str(item)
            )
            if ref == "atlas-compute-provision/provision":
                phases.append({"build": ref})
            else:
                phases.append(item)
        data["phases"] = phases
        path.write_text(yaml.safe_dump(data), encoding="utf-8")

        cfg = parse_phases_config(data["phases"])
        assert cfg is not None
        self.assertEqual(
            resolve_phase_boundary("build", cfg),
            "atlas-compute-provision/provision",
        )

    def test_top_level_phase_aliases_hard_rejected(self) -> None:
        with self.assertRaises(PhaseAliasesRemovedError):
            parse_cluster_config_v2_fragment(
                {
                    "schema_version": 2,
                    "phases": ["atlas-compute-provision/templates"],
                    "phase_aliases": {
                        "templates": "atlas-compute-provision/templates",
                    },
                }
            )


if __name__ == "__main__":
    unittest.main()
