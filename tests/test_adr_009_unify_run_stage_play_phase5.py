"""Phase 5 gate: ADR 009 — offline CI + sample ``run``/``play`` ``--dry-run`` (ADR complete)."""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from clusterctl.__main__ import main
from clusterctl.context import ClusterContext
from clusterctl.phase_plan import resolve_phase_execution_plan
from clusterctl.phase_selector import resolve_cli_phase_window
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.run_overrides import apply_run_cli_overrides
from clusterctl.validate import Severity, validate_cluster

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
CHANGELOG = ROOT / "CHANGELOG.md"
RUN_CI = ROOT / "tests" / "run_ci.sh"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PHASE5_GATE = ROOT / "tests" / "test_adr_009_unify_run_stage_play_phase5.py"
MAIN = ROOT / "clusterctl" / "__main__.py"


def _seed_lab_adr009(root: Path) -> None:
    (root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
    (root / "workspace").mkdir()
    seed_org_baseline_fixture(root)
    seed_local_playbook_repo_stubs(root)

    leaf = root / "clusters" / "lab" / "adr009"
    leaf.mkdir(parents=True)
    (leaf / "cluster.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "id": "lab/adr009",
                "inventory": "hosts",
                "playbooks": local_playbooks_override_block(
                    "atlas-compute-provision",
                    "atlas-node-foundation",
                ),
                "phases": [
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


class Adr009UnifyRunStagePlayPhase5Test(unittest.TestCase):
    def test_adr_status_phase5(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        status = text.split("## Context", 1)[0]
        self.assertIn("Status:** Accepted (Phase 5", status)
        self.assertIn("alias hard-removal Phase 1–5 done", status)
        self.assertIn("acceptance-time", status)
        self.assertIn("CI workflow", status)
        self.assertIn("does **not** subprocess", status)
        self.assertIn("Current runtime", status)

        self.assertIn("Current runtime (Phase 5", text)
        self.assertIn("[x] Offline `./tests/run_ci.sh` green (Phase 5)", text)
        self.assertIn("run_ci.sh", text)
        self.assertIn("no live labs", text.lower())
        self.assertIn("test_adr_009_unify_run_stage_play_phase5.py", text)
        self.assertIn("acceptance-time proof", text)
        self.assertIn("does not subprocess", text.lower())
        self.assertIn(".github/workflows/ci.yml", text)
        self.assertIn("Historical problem statement (pre–Phase 1)", text)
        self.assertIn("sole execute verb", text.lower())

    def test_adr_index_phase5(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("009-unify-run-stage-play.md", text)
        self.assertIn("Accepted (Phase 5", text)

    def test_changelog_phase5(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 009 — Phase 5", text)
        self.assertIn("run_ci.sh", text)
        self.assertIn("ADR complete", text)
        self.assertIn("test_adr_009_unify_run_stage_play_phase5.py", text)

    def test_clusterctl_doc_phase5(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("run --phases", text)
        self.assertIn("**Removed** (ADR 009 alias-removal Phase 1–5)", text)

    def test_run_ci_script_and_aliases_removed(self) -> None:
        self.assertTrue(RUN_CI.is_file(), RUN_CI)
        self.assertTrue(os.access(RUN_CI, os.X_OK), RUN_CI)
        self.assertTrue(PHASE5_GATE.is_file(), PHASE5_GATE)
        self.assertTrue(CI_WORKFLOW.is_file(), CI_WORKFLOW)
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("./tests/run_ci.sh", workflow)
        main_text = MAIN.read_text(encoding="utf-8")
        self.assertNotIn('command="stage"', main_text)
        self.assertNotIn('command="play"', main_text)
        self.assertNotIn("_warn_deprecated_execute_alias", main_text)

    def _with_lab(self, fn) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = {
                k: os.environ.get(k)
                for k in (
                    "ATLAS_CLUSTER_ROOT",
                    "CLUSTER_ID",
                    "ATLAS_CLUSTERS_ROOT",
                    "ATLAS_CLUSTERCTL_CONFIG",
                )
            }
            try:
                for key in saved:
                    os.environ.pop(key, None)
                os.environ["ATLAS_CLUSTER_ROOT"] = str(root)
                _seed_lab_adr009(root)
                fn(root)
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

    def test_sample_run_dry_run_merge_e(self) -> None:
        """Fixture leaf: validate + ``run --phases … -e … --dry-run`` (no ansible)."""

        def body(root: Path) -> None:
            ctx = ClusterContext.load(cluster_id="lab/adr009")
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

            window = resolve_cli_phase_window(phases_selector="provision")
            plan = resolve_phase_execution_plan(
                ctx,
                from_phase=window.from_phase,
                to_phase=window.to_phase,
                only_phases=window.only_phases,
            )
            merged = apply_run_cli_overrides(
                plan,
                extra_vars=("provision_mode=destroy",),
            )
            self.assertEqual(len(merged.stages), 1)
            self.assertGreater(len(merged.stages[0].invocations), 1)
            for inv in merged.stages[0].invocations:
                self.assertIn(
                    "provision_mode=destroy",
                    inv.invocation.extra_e or (),
                )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = main(
                    [
                        "--cluster",
                        "lab/adr009",
                        "run",
                        "--phases",
                        "provision",
                        "-e",
                        "provision_mode=destroy",
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 0, stderr.getvalue())
            out = stdout.getvalue()
            self.assertIn("dry-run", out.lower())
            self.assertIn("atlas-compute-provision/provision", out)

        self._with_lab(body)

    def test_sample_play_dry_run_merge_e(self) -> None:
        """Former ``play -e`` path: ``run --phases … -e`` keeps ``merge_e``."""

        def body(root: Path) -> None:
            ctx = ClusterContext.load(cluster_id="lab/adr009")
            window = resolve_cli_phase_window(phases_selector="provision")
            catalog = resolve_phase_execution_plan(
                ctx,
                from_phase=window.from_phase,
                to_phase=window.to_phase,
                only_phases=window.only_phases,
            )
            catalog_n = len(catalog.stages[0].invocations)
            self.assertGreater(catalog_n, 1)

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = main(
                    [
                        "--cluster",
                        "lab/adr009",
                        "run",
                        "--phases",
                        "provision",
                        "-e",
                        "provision_mode=destroy",
                        "--dry-run",
                    ]
                )
            err = stderr.getvalue()
            self.assertEqual(code, 0, err)
            self.assertNotIn("deprecated", err.lower())
            out = stdout.getvalue()
            self.assertIn("dry-run", out.lower())
            self.assertIn("atlas-compute-provision/provision", out)
            self.assertIn(f"{catalog_n} invocations", out)

        self._with_lab(body)


if __name__ == "__main__":
    unittest.main()
