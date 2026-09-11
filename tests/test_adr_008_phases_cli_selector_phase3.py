"""Phase 3 gate: ADR 008 — CSV explicit ``--phases`` set (leaf order)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.context import ClusterContext
from clusterctl.exceptions import ClusterctlError
from clusterctl.phase_plan import resolve_phase_execution_plan, select_explicit_phase_refs
from clusterctl.phase_selector import resolve_cli_phase_window
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_config import PhasesConfig

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
MAIN = ROOT / "clusterctl" / "__main__.py"


class Adr008PhasesCliSelectorPhase3Test(unittest.TestCase):
    def test_adr_status_phase3(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn("[x] CSV explicit set (Phase 3)", text)
        self.assertIn("leaf", text.lower())

    def test_adr_index_phase3(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase3(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008", text)
        self.assertIn("Phase 3", text)
        self.assertIn("comma", text.lower())

    def test_clusterctl_doc_mentions_csv(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("a,b,c", text)
        self.assertIn("ADR 008", text)

    def test_help_mentions_csv_form(self) -> None:
        text = MAIN.read_text(encoding="utf-8")
        self.assertIn("a,b,c", text)

    def test_select_explicit_preserves_leaf_order(self) -> None:
        phases = PhasesConfig(
            phases=(
                "atlas-compute-provision/templates",
                "atlas-compute-provision/provision",
                "atlas-node-foundation/init",
                "atlas-k8s-core/cluster",
                "atlas-k8s-addons/addons",
            ),
            phase_aliases={
                "templates": "atlas-compute-provision/templates",
                "provision": "atlas-compute-provision/provision",
                "init": "atlas-node-foundation/init",
                "k8s-core": "atlas-k8s-core/cluster",
                "k8s-addons": "atlas-k8s-addons/addons",
            },
        )
        # CSV order reversed relative to leaf — result must follow leaf.
        selected = select_explicit_phase_refs(
            phases.phases,
            only_phases=("k8s-addons", "provision"),
            phases=phases,
        )
        self.assertEqual(
            selected,
            (
                "atlas-compute-provision/provision",
                "atlas-k8s-addons/addons",
            ),
        )

    def test_select_explicit_unknown_errors(self) -> None:
        # Known alias whose ref is not in this effective list.
        phases = PhasesConfig(
            phases=("atlas-compute-provision/provision",),
            phase_aliases={
                "provision": "atlas-compute-provision/provision",
                "init": "atlas-node-foundation/init",
            },
        )
        with self.assertRaises(ClusterctlError) as ctx:
            select_explicit_phase_refs(
                phases.phases,
                only_phases=("init",),
                phases=phases,
            )
        self.assertIn("not in effective phase list", str(ctx.exception))

    def test_plan_skip_middle_via_csv(self) -> None:
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

                leaf = root / "clusters" / "lab" / "adr008p3"
                leaf.mkdir(parents=True)
                (leaf / "cluster.yaml").write_text(
                    yaml.safe_dump(
                        {
                            "schema_version": 2,
                            "id": "lab/adr008p3",
                            "inventory": "hosts",
                            "playbooks": local_playbooks_override_block(
                                "atlas-compute-provision",
                                "atlas-node-foundation",
                                "atlas-k8s-core",
                                "atlas-k8s-addons",
                            ),
                            "phases": [
                                {"templates": "atlas-compute-provision/templates"},
                                {"provision": "atlas-compute-provision/provision"},
                                {"init": "atlas-node-foundation/init"},
                                {"k8s-core": "atlas-k8s-core/cluster"},
                                {"k8s-addons": "atlas-k8s-addons/addons"},
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
                (gv / "cluster.yml").write_text(
                    yaml.safe_dump(
                        {
                            "cluster_id": "lab/adr008p3",
                            "dns_domain_suffix": "example.com",
                            "cluster_domain": "k8s.example.com",
                            "provision_stack": "k8s",
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )

                ctx = ClusterContext.load(cluster_id="lab/adr008p3")
                window = resolve_cli_phase_window(
                    phases_selector="k8s-addons,provision"
                )
                self.assertEqual(window.only_phases, ("k8s-addons", "provision"))

                plan = resolve_phase_execution_plan(
                    ctx,
                    only_phases=window.only_phases,
                )
                # Skip init + k8s-core; leaf order kept.
                self.assertEqual(
                    plan.summary.phases,
                    (
                        "atlas-compute-provision/provision",
                        "atlas-k8s-addons/addons",
                    ),
                )
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
