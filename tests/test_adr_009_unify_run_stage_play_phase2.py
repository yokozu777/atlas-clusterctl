"""Phase 2 gate: ADR 009 — historical deprecated aliases (now removed in tree)."""

from __future__ import annotations

import unittest
from pathlib import Path

from clusterctl.phase_plan import (
    PhaseExecutionPlan,
    PhaseInvocationPlan,
    PhasePlanSummary,
    PhaseStagePlan,
)
from clusterctl.playbooks_config import InvocationSpec
from clusterctl.run_overrides import apply_run_cli_overrides

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "009-unify-run-stage-play.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CLUSTERCTL_DOC = ROOT / "docs" / "clusterctl.md"
CHANGELOG = ROOT / "CHANGELOG.md"
MAIN = ROOT / "clusterctl" / "__main__.py"


class Adr009UnifyRunStagePlayPhase2Test(unittest.TestCase):
    def test_adr_status_phase2(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("[x] `stage` / `play` deprecated aliases (Phase 2)", text)

    def test_adr_index_phase2(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("009-unify-run-stage-play.md", text)
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("Phase 2", text)
        self.assertIn("deprecated", text.lower())

    def test_clusterctl_doc_points_at_run(self) -> None:
        text = CLUSTERCTL_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 009", text)
        self.assertIn("**Removed** (ADR 009 alias-removal Phase 1–5)", text)
        self.assertIn("run --phases", text)

    def test_main_shared_execute_no_aliases(self) -> None:
        text = MAIN.read_text(encoding="utf-8")
        self.assertIn("def _cmd_run_execute", text)
        self.assertNotIn("_warn_deprecated_execute_alias", text)
        self.assertNotIn('command="stage"', text)
        self.assertNotIn('command="play"', text)
        self.assertNotIn("apply_play_cli_overrides", text)

    def test_merge_e_policy_unchanged(self) -> None:
        """Historical Phase 2 contract: -e alone does not collapse (merge_e)."""
        stage = PhaseStagePlan(
            phase_ref="atlas-redis/cluster",
            repo_name="atlas-redis",
            entry_name="cluster",
            playbook_file="playbooks/redis_cluster.yaml",
            repo_base="/tmp/atlas-redis",
            git_ssh=False,
            invocations=tuple(
                PhaseInvocationPlan(
                    phase_ref="atlas-redis/cluster",
                    repo_name="atlas-redis",
                    entry_name="cluster",
                    repo_base="/tmp/atlas-redis",
                    playbook_file="playbooks/redis_cluster.yaml",
                    invocation_index=i,
                    invocation=InvocationSpec(tags=f"tag{i}"),
                )
                for i in range(1, 4)
            ),
        )
        plan = PhaseExecutionPlan(
            summary=PhasePlanSummary(
                cluster_id="lab/t",
                workspace_id="ws",
                execution="local",
                execution_source="cluster.yaml",
                phases=(stage.phase_ref,),
                invocation_count=3,
                inventory="hosts",
                schema_version=2,
            ),
            stages=(stage,),
            filter_skipped=(),
        )
        out = apply_run_cli_overrides(plan, extra_vars=("provision_mode=destroy",))
        self.assertEqual(len(out.stages[0].invocations), 3)


if __name__ == "__main__":
    unittest.main()
