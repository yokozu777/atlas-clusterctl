"""Phase 5 gate: ADR 006 — offline CI + sample validate/plan (infer-enabled leaf)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.context import ClusterContext
from clusterctl.phase_plan import resolve_phase_execution_plan
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_config import load_cluster_config_v2_yaml
from clusterctl.validate import Severity, validate_cluster

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "006-redundant-playbooks-enabled.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
RUN_CI = ROOT / "tests" / "run_ci.sh"

_TEMPLATE_NAMES = (
    "k8s_full",
    "infra_edge",
    "jenkins_agent",
    "postgresql",
    "redis",
    "kafka",
)


class Adr006RedundantPlaybooksEnabledPhase5Test(unittest.TestCase):
    def test_adr_status_phase5(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase 5", text)
        self.assertIn("Current runtime (Phase 5)", text)
        self.assertIn(
            "[x] Offline `./tests/run_ci.sh` (+ sample validate/plan) green (Phase 5)",
            text,
        )
        self.assertIn("run_ci.sh", text)
        self.assertIn("no live labs", text.lower())

    def test_adr_index_phase5(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase 5)", text)

    def test_changelog_phase5(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 006", text)
        self.assertIn("Phase 5", text)
        self.assertIn("run_ci.sh", text)

    def test_run_ci_script_exists(self) -> None:
        self.assertTrue(RUN_CI.is_file(), RUN_CI)
        self.assertTrue(os.access(RUN_CI, os.X_OK), RUN_CI)

    def test_public_templates_infer_enabled_without_true(self) -> None:
        for name in _TEMPLATE_NAMES:
            path = ROOT / "clusters" / "_template" / name / "cluster.yaml"
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("playbooks_enabled: true", text, path)
            cfg = load_cluster_config_v2_yaml(path)
            self.assertIsNone(cfg.playbooks_enabled, name)
            self.assertTrue(cfg.effective_playbooks_enabled(), name)
            self.assertTrue(cfg.phases, name)

    def test_sample_validate_and_plan_omit_playbooks_enabled(self) -> None:
        """Leaf omits playbooks_enabled; validate + plan still work via infer."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = {
                k: os.environ.get(k)
                for k in ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "ATLAS_CLUSTERS_ROOT")
            }
            try:
                for key in saved:
                    os.environ.pop(key, None)
                os.environ["ATLAS_CLUSTER_ROOT"] = str(root)

                (root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
                (root / "workspace").mkdir()
                seed_org_baseline_fixture(root)
                seed_local_playbook_repo_stubs(root)

                leaf = root / "clusters" / "lab" / "adr006"
                leaf.mkdir(parents=True)
                # Intentionally no playbooks_enabled — ADR 006 infer path.
                (leaf / "cluster.yaml").write_text(
                    yaml.safe_dump(
                        {
                            "schema_version": 2,
                            "id": "lab/adr006",
                            "inventory": "hosts",
                            "playbooks": local_playbooks_override_block(
                                "atlas-node-foundation",
                                "atlas-infra-edge",
                                "atlas-compute-provision",
                                "atlas-k8s-core",
                                "atlas-k8s-addons",
                            ),
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                (leaf / "hosts").write_text(
                    "all:\n  children:\n    k8s_masters:\n      hosts:\n"
                    "        localhost:\n    infra_platform:\n      hosts:\n"
                    "        localhost:\n",
                    encoding="utf-8",
                )
                pub = leaf / "pub_keys"
                pub.mkdir()
                (pub / "localuser.pub").write_text("ssh-rsa test\n", encoding="utf-8")
                gv = leaf / "group_vars" / "all"
                gv.mkdir(parents=True)
                (gv / "atlas-node-foundation.yml").write_text(
                    yaml.safe_dump(
                        {
                            "dns_domain_suffix": "example.com",
                            "cluster_domain": "k8s.example.com",
                            "provision_stack": "k8s",
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )

                ctx = ClusterContext.load(cluster_id="lab/adr006")
                assert ctx.config_v2 is not None
                self.assertIsNone(ctx.config_v2.playbooks_enabled)
                self.assertTrue(ctx.playbooks_enabled)

                with (
                    patch(
                        "clusterctl.validate.playbook_repo_layout_ready",
                        return_value=True,
                    ),
                    patch(
                        "clusterctl.validate.validate_docker_deep",
                        return_value=[],
                    ),
                ):
                    report = validate_cluster(ctx, root=root, docker_smoke=False)
                errors = [i for i in report.issues if i.severity == Severity.ERROR]
                self.assertEqual(errors, [], [i.code for i in errors])

                plan = resolve_phase_execution_plan(ctx)
                self.assertGreater(len(plan.summary.phases), 0)
                self.assertGreater(plan.summary.invocation_count, 0)
                self.assertGreater(len(plan.stages), 0)
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
