"""Phase 1 gate: ADR 008 — ``--phases`` wired on plan/run."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl import __main__ as main_mod
from clusterctl.context import ClusterContext
from clusterctl.phase_selector import CliPhaseWindow, resolve_cli_phase_window
from clusterctl.phase_plan import resolve_phase_execution_plan
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "008-phases-cli-selector.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
MAIN = ROOT / "clusterctl" / "__main__.py"


class Adr008PhasesCliSelectorPhase1Test(unittest.TestCase):
    def test_adr_status_phase1(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn(
            "[x] `--phases` on `plan`/`run` (+ conflict with from/to) (Phase 1)",
            text,
        )
        self.assertIn("resolve_cli_phase_window", text)

    def test_adr_index_phase1(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase1(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 008", text)
        self.assertIn("Phase 1", text)
        self.assertIn("--phases", text)

    def test_clusterctl_doc_phase1(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 008", text)
        self.assertIn("--phases", text)
        self.assertIn("provision..k8s-addons", text)

    def test_main_wires_phases_flag(self) -> None:
        text = MAIN.read_text(encoding="utf-8")
        self.assertIn('"--phases"', text)
        self.assertIn("resolve_cli_phase_window", text)
        self.assertIn("phases_selector", text)

    def test_argparse_accepts_phases_and_short_p(self) -> None:
        parser = main_mod._build_parser()
        for argv in (
            ["plan", "--phases", "provision..k8s-addons"],
            ["plan", "-p", "init"],
            ["run", "--phases", "templates", "--dry-run"],
            ["run", "--phases", "provision,k8s-addons"],
        ):
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertIsNotNone(args.phases_selector)

    def test_argparse_rejects_plan_run_from_to(self) -> None:
        import contextlib
        import io

        parser = main_mod._build_parser()
        for argv in (
            ["plan", "--from", "init", "--to", "k8s-addons"],
            ["run", "--from", "provision"],
            ["run", "--to", "init"],
        ):
            with self.subTest(argv=argv):
                buf = io.StringIO()
                with contextlib.redirect_stderr(buf):
                    with self.assertRaises(SystemExit):
                        parser.parse_args(argv)

    def test_phases_range_selector_on_plan(self) -> None:
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
                            "cluster_id": "lab/adr008",
                            "dns_domain_suffix": "example.com",
                            "cluster_domain": "k8s.example.com",
                            "provision_stack": "k8s",
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )

                ctx = ClusterContext.load(cluster_id="lab/adr008")
                window = resolve_cli_phase_window(
                    phases_selector="provision..k8s-addons"
                )
                self.assertEqual(
                    window,
                    CliPhaseWindow(from_phase="provision", to_phase="k8s-addons"),
                )

                with patch(
                    "clusterctl.validate.playbook_repo_layout_ready",
                    return_value=True,
                ):
                    plan = resolve_phase_execution_plan(
                        ctx,
                        from_phase=window.from_phase,
                        to_phase=window.to_phase,
                    )
                self.assertEqual(
                    plan.summary.phases,
                    (
                        "atlas-compute-provision/provision",
                        "atlas-node-foundation/init",
                        "atlas-k8s-core/cluster",
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
