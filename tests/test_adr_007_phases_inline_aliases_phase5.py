"""Phase 5 gate: ADR 007 — offline CI + sample plan/stage (inline aliases)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.cluster_config_loader import cluster_config_v2_to_yaml_dict
from clusterctl.context import ClusterContext
from clusterctl.phase_plan import resolve_phase_boundary, resolve_phase_execution_plan
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_config import load_cluster_config_v2_yaml
from clusterctl.validate import Severity, validate_cluster

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "007-phases-inline-aliases.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
RUN_CI = ROOT / "tests" / "run_ci.sh"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"

_TEMPLATE_NAMES = (
    "k8s_full",
    "infra_edge",
    "jenkins_agent",
    "postgresql",
    "redis",
    "kafka",
)


class Adr007PhasesInlineAliasesPhase5Test(unittest.TestCase):
    def test_adr_status_phase5(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase 5", text)
        self.assertIn("Current runtime (Phase 5)", text)
        self.assertIn(
            "[x] Offline `./tests/run_ci.sh` (+ sample plan/stage) green (Phase 5)",
            text,
        )
        self.assertIn("run_ci.sh", text)
        self.assertIn("no live labs", text.lower())

    def test_adr_index_phase5(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase 5)", text)

    def test_changelog_phase5(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("Phase 5", text)
        self.assertIn("run_ci.sh", text)

    def test_schema_doc_mentions_phase5(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("Phase 5", text)
        self.assertIn("no live labs", text.lower())

    def test_run_ci_script_exists(self) -> None:
        self.assertTrue(RUN_CI.is_file(), RUN_CI)
        self.assertTrue(os.access(RUN_CI, os.X_OK), RUN_CI)

    def test_public_templates_inline_aliases_no_top_level_key(self) -> None:
        for name in _TEMPLATE_NAMES:
            path = ROOT / "clusters" / "_template" / name / "cluster.yaml"
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\nphase_aliases:\n", text, path)
            cfg = load_cluster_config_v2_yaml(path)
            self.assertIsNotNone(cfg.phases, name)
            assert cfg.phases is not None
            self.assertTrue(cfg.phases.phases, name)
            self.assertTrue(cfg.phases.phase_aliases, name)
            dumped = cluster_config_v2_to_yaml_dict(cfg)
            self.assertNotIn("phase_aliases", dumped, name)
            self.assertIn("phases", dumped, name)

    def test_sample_validate_plan_and_stage_inline_aliases(self) -> None:
        """Leaf uses only inline phases:; validate + plan --phases aliases work."""
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

                leaf = root / "clusters" / "lab" / "adr007"
                leaf.mkdir(parents=True)
                # Intentionally no top-level phase_aliases — ADR 007 inline SoT.
                (leaf / "cluster.yaml").write_text(
                    yaml.safe_dump(
                        {
                            "schema_version": 2,
                            "id": "lab/adr007",
                            "inventory": "hosts",
                            "playbooks": local_playbooks_override_block(
                                "atlas-compute-provision",
                                "atlas-node-foundation",
                            ),
                            "phases": [
                                {"templates": "atlas-compute-provision/templates"},
                                {"provision": "atlas-compute-provision/provision"},
                                {"init": "atlas-node-foundation/init"},
                            ],
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                (leaf / "hosts").write_text(
                    "all:\n  children:\n    k8s_masters:\n      hosts:\n"
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

                ctx = ClusterContext.load(cluster_id="lab/adr007")
                assert ctx.config_v2 is not None
                assert ctx.config_v2.phases is not None
                phases = ctx.config_v2.phases
                self.assertEqual(
                    phases.phases,
                    (
                        "atlas-compute-provision/templates",
                        "atlas-compute-provision/provision",
                        "atlas-node-foundation/init",
                    ),
                )
                self.assertEqual(
                    phases.phase_aliases,
                    {
                        "templates": "atlas-compute-provision/templates",
                        "provision": "atlas-compute-provision/provision",
                        "init": "atlas-node-foundation/init",
                    },
                )
                dumped = cluster_config_v2_to_yaml_dict(ctx.config_v2)
                self.assertNotIn("phase_aliases", dumped)
                self.assertIn("phases", dumped)

                self.assertEqual(
                    resolve_phase_boundary("provision", phases),
                    "atlas-compute-provision/provision",
                )
                self.assertEqual(
                    resolve_phase_boundary("init", phases),
                    "atlas-node-foundation/init",
                )

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

                plan = resolve_phase_execution_plan(
                    ctx,
                    from_phase="provision",
                    to_phase="init",
                )
                self.assertEqual(
                    plan.summary.phases,
                    (
                        "atlas-compute-provision/provision",
                        "atlas-node-foundation/init",
                    ),
                )
                self.assertEqual(len(plan.stages), 2)
                self.assertGreater(plan.summary.invocation_count, 0)
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
