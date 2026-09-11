"""Phase 5 gate: ADR 008 — offline CI + sample ``--phases`` plan (ADR complete)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.context import ClusterContext
from clusterctl.phase_plan import resolve_phase_execution_plan
from clusterctl.phase_selector import resolve_cli_phase_window
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.validate import Severity, validate_cluster

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
RUN_CI = ROOT / "tests" / "run_ci.sh"
PHASE5_GATE = ROOT / "tests" / "test_adr_008_phases_cli_selector_phase5.py"


class Adr008PhasesCliSelectorPhase5Test(unittest.TestCase):
    def test_adr_status_phase5(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase 5", text)
        self.assertIn("Current runtime (Phase 5)", text)
        self.assertIn("[x] Offline `./tests/run_ci.sh` green (Phase 5)", text)
        self.assertIn("run_ci.sh", text)
        self.assertIn("no live labs", text.lower())
        self.assertIn("ADR complete", text)
        self.assertIn("test_adr_008_phases_cli_selector_phase5.py", text)
        # Product Phase 5 green ≠ current-tree / Variant B claim.
        self.assertIn("acceptance-time proof", text)
        self.assertIn("Variant B offline proof", text)

    def test_adr_index_phase5(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase 5)", text)
        self.assertIn("008-phases-cli-selector.md", text)

    def test_changelog_phase5(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008", text)
        self.assertIn("Phase 5", text)
        self.assertIn("run_ci.sh", text)
        self.assertIn("ADR complete", text)

    def test_clusterctl_doc_phase5(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 008 Phase 5", text)
        self.assertIn("--phases", text)
        self.assertIn("removed", text.lower())

    def test_run_ci_script_exists(self) -> None:
        self.assertTrue(RUN_CI.is_file(), RUN_CI)
        self.assertTrue(os.access(RUN_CI, os.X_OK), RUN_CI)
        self.assertTrue(PHASE5_GATE.is_file(), PHASE5_GATE)

    def test_sample_validate_and_phases_selector_plan(self) -> None:
        """Leaf plan via ``--phases`` range + CSV (leaf order); no live labs."""
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

                leaf = root / "clusters" / "lab" / "adr008"
                leaf.mkdir(parents=True)
                (leaf / "cluster.yaml").write_text(
                    yaml.safe_dump(
                        {
                            "schema_version": 2,
                            "id": "lab/adr008",
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
                            "execution": {"mode": "local"},
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

                ctx = ClusterContext.load(cluster_id="lab/adr008")

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

                range_window = resolve_cli_phase_window(
                    phases_selector="provision..init"
                )
                range_plan = resolve_phase_execution_plan(
                    ctx,
                    from_phase=range_window.from_phase,
                    to_phase=range_window.to_phase,
                    only_phases=range_window.only_phases,
                )
                self.assertEqual(
                    list(range_plan.summary.phases),
                    [
                        "atlas-compute-provision/provision",
                        "atlas-node-foundation/init",
                    ],
                )

                # CSV skip-middle: templates + init (omit provision); leaf order.
                csv_window = resolve_cli_phase_window(
                    phases_selector="init,templates"
                )
                csv_plan = resolve_phase_execution_plan(
                    ctx,
                    from_phase=csv_window.from_phase,
                    to_phase=csv_window.to_phase,
                    only_phases=csv_window.only_phases,
                )
                self.assertEqual(
                    list(csv_plan.summary.phases),
                    [
                        "atlas-compute-provision/templates",
                        "atlas-node-foundation/init",
                    ],
                )
                self.assertGreater(csv_plan.summary.invocation_count, 0)
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
