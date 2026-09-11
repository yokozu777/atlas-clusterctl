"""ADR 005: phase intent from phases:; stacks: → StacksRemovedError / stacks_removed."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.context import ClusterContext
from clusterctl.exceptions import StacksRemovedError
from clusterctl.phase_intent import infer_phase_intent
from clusterctl.phase_plan import resolve_phase_execution_plan
from clusterctl.pipeline_fixture import local_playbooks_override_block, seed_org_baseline_fixture
from clusterctl.playbooks_config import (
    load_cluster_config_v2_yaml,
    parse_cluster_config_v2_fragment,
)
from clusterctl.validate import validate_all_clusters

K8S_CORE_PHASE = "atlas-k8s-core/cluster"
K8S_ADDONS_PHASE = "atlas-k8s-addons/addons"


class PhaseIntentAdr005Phase4Test(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)
        self._seed_leaf()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_leaf(self) -> None:
        leaf = self.root / "clusters" / "lab" / "test"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab/test",
                    "inventory": "hosts",
                    "playbooks": local_playbooks_override_block("atlas-node-foundation"),
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
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        (self.root / "atlas-node-foundation" / "roles" / "demo" / "tasks").mkdir(
            parents=True
        )
        (
            self.root / "atlas-node-foundation" / "roles" / "demo" / "tasks" / "main.yaml"
        ).write_text("---\n", encoding="utf-8")

    def test_infer_from_phases_matrix(self) -> None:
        flags = infer_phase_intent(
            (K8S_CORE_PHASE, "atlas-redis/cluster"),
            {"provision_stack": "k8s"},
        )
        self.assertTrue(flags.k8s)
        self.assertTrue(flags.redis)
        self.assertFalse(flags.infra)
        self.assertFalse(flags.kafka)
        self.assertEqual(flags.provision_stack, "k8s")

    def test_execution_plan_is_phases_only(self) -> None:
        ctx = ClusterContext.load(cluster_id="lab/test")
        plan = resolve_phase_execution_plan(ctx)
        self.assertFalse(hasattr(plan, "stacks_skipped"))
        self.assertIn("atlas-node-foundation/init", plan.summary.phases)

    def test_stacks_key_rejected_at_parse(self) -> None:
        with self.assertRaises(StacksRemovedError) as ctx:
            parse_cluster_config_v2_fragment(
                {
                    "schema_version": 2,
                    "id": "lab/x",
                    "stacks": {"k8s": False},
                    "phases": ["atlas-node-foundation/init"],
                }
            )
        exc = ctx.exception
        self.assertEqual(exc.code, "stacks_removed")
        self.assertEqual(StacksRemovedError.code, "stacks_removed")
        self.assertIn("stacks:", str(exc))

    def test_stacks_key_rejected_on_leaf_load(self) -> None:
        leaf = self.root / "clusters" / "lab" / "test" / "cluster.yaml"
        data = yaml.safe_load(leaf.read_text(encoding="utf-8"))
        data["stacks"] = {"infra": False}
        leaf.write_text(yaml.safe_dump(data), encoding="utf-8")
        with self.assertRaises(StacksRemovedError) as ctx:
            ClusterContext.load(cluster_id="lab/test")
        self.assertEqual(ctx.exception.code, "stacks_removed")
        self.assertIn(str(leaf), ctx.exception.source)

    def test_stacks_key_rejected_on_cascade_fragment(self) -> None:
        env_default = self.root / "clusters" / "lab" / "default"
        env_default.mkdir(parents=True, exist_ok=True)
        path = env_default / "cluster.yaml"
        path.write_text(
            "schema_version: 2\nid: lab/default\nstacks:\n  k8s: false\n",
            encoding="utf-8",
        )
        with self.assertRaises(StacksRemovedError) as ctx:
            ClusterContext.load(cluster_id="lab/test")
        self.assertEqual(ctx.exception.code, "stacks_removed")
        self.assertIn(str(path), ctx.exception.source)

    def test_load_cluster_config_v2_yaml_rewrites_source_path(self) -> None:
        path = self.root / "fragment.yaml"
        path.write_text(
            "schema_version: 2\nid: x\nstacks:\n  infra: true\n",
            encoding="utf-8",
        )
        with self.assertRaises(StacksRemovedError) as ctx:
            load_cluster_config_v2_yaml(path)
        self.assertEqual(ctx.exception.source, str(path))

    def test_validate_all_reports_stacks_removed_not_generic_load(self) -> None:
        leaf = self.root / "clusters" / "lab" / "test" / "cluster.yaml"
        data = yaml.safe_load(leaf.read_text(encoding="utf-8"))
        data["stacks"] = {"k8s": False}
        leaf.write_text(yaml.safe_dump(data), encoding="utf-8")

        reports = validate_all_clusters(self.root, docker_smoke=False)
        by_id = {report.cluster_id: report for report in reports}
        self.assertIn("lab/test", by_id)
        report = by_id["lab/test"]
        self.assertFalse(report.ok)
        codes = [issue.code for issue in report.errors]
        self.assertIn("stacks_removed", codes)
        self.assertNotIn("cluster_load_failed", codes)
        issue = next(i for i in report.errors if i.code == "stacks_removed")
        self.assertEqual(issue.hint, StacksRemovedError.hint)

    def test_stacks_module_removed(self) -> None:
        import importlib.util

        self.assertIsNone(importlib.util.find_spec("clusterctl.stacks"))


if __name__ == "__main__":
    unittest.main()
