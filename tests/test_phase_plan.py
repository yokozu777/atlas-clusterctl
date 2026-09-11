"""Tests for schema v2 phase plan (PR-3)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config_loader import dump_cluster_config_v2
from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.phase_plan import (
    resolve_phase_boundary,
    resolve_phase_execution_plan,
    slice_phase_refs,
)
from clusterctl.pipeline_fixture import (
    build_org_baseline_cluster_config,
    local_playbooks_override_block,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_config import PhasesConfig

K8S_CORE_PHASE = "atlas-k8s-core/cluster"
K8S_ADDONS_PHASE = "atlas-k8s-addons/addons"
K8S_STACK_SKIP_PHASES = (K8S_CORE_PHASE, K8S_ADDONS_PHASE)

class PhasePlanTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._seed_cluster()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_cluster(self) -> None:
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        seed_org_baseline_fixture(self.root)
        org = build_org_baseline_cluster_config(self.root)

        leaf = self.root / "clusters" / "lab" / "test"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab/test",
                    "inventory": "hosts",
                    "playbooks": local_playbooks_override_block("atlas-node-foundation")
                }
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text(
            "all:\n  children:\n    k8s_masters:\n      hosts:\n        localhost:\n",
            encoding="utf-8",
        )
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/test",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                    "provision_stack": "k8s",
                }
            ),
            encoding="utf-8",
        )
        sibling = self.root / "atlas-node-foundation"
        (sibling / "roles" / "demo" / "tasks").mkdir(parents=True, exist_ok=True)
        (sibling / "roles" / "demo" / "tasks" / "main.yaml").write_text("---\n", encoding="utf-8")

    def test_resolve_phase_boundary_alias(self) -> None:
        phases = PhasesConfig(
            phases=("atlas-compute-provision/provision",),
            phase_aliases={"provision": "atlas-compute-provision/provision"},
        )
        self.assertEqual(
            resolve_phase_boundary("provision", phases),
            "atlas-compute-provision/provision",
        )

    def test_slice_phase_refs(self) -> None:
        phases = PhasesConfig(
            phases=(
                "atlas-compute-provision/templates",
                "atlas-compute-provision/provision",
                "atlas-node-foundation/init",
            ),
            phase_aliases={
                "provision": "atlas-compute-provision/provision",
                "init": "atlas-node-foundation/init",
            },
        )
        sliced = slice_phase_refs(
            phases.phases,
            from_phase="provision",
            to_phase="init",
            phases=phases,
        )
        self.assertEqual(
            sliced,
            ("atlas-compute-provision/provision", "atlas-node-foundation/init"),
        )

    def test_execution_plan_uses_overlay_and_counts_invocations(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab/test")
        plan = resolve_phase_execution_plan(ctx)
        self.assertGreaterEqual(len(plan.summary.phases), 4)
        self.assertGreater(plan.summary.invocation_count, 50)
        foundation_stage = next(
            stage for stage in plan.stages if stage.repo_name == "atlas-node-foundation"
        )
        self.assertIn("atlas-node-foundation", foundation_stage.repo_base)

    def test_execution_plan_uses_phases_without_stack_filter(self) -> None:
        """ADR 005 Phase 2: plan API has no stack filter / stacks_skipped."""
        ctx = ClusterContext.load(cluster_id="lab/test")
        plan = resolve_phase_execution_plan(ctx)
        self.assertIn(K8S_CORE_PHASE, plan.summary.phases)
        self.assertIn(K8S_ADDONS_PHASE, plan.summary.phases)
        self.assertFalse(hasattr(plan, "stacks_skipped"))

    def test_invalid_slice_raises(self) -> None:
        phases = PhasesConfig(phases=("atlas-compute-provision/provision",))
        with self.assertRaises(ClusterctlError):
            slice_phase_refs(phases.phases, from_phase="missing", phases=phases)

    def test_unknown_alias_no_python_fallback(self) -> None:
        phases = PhasesConfig(
            phases=("atlas-compute-provision/provision",),
            phase_aliases={"provision": "atlas-compute-provision/provision"},
        )
        with self.assertRaises(ClusterctlError):
            resolve_phase_boundary("templates", phases)

if __name__ == "__main__":
    unittest.main()
