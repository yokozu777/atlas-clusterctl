"""Phase 2: play --phase / --git-ssh overrides, empty-run guard, slice messages."""

from __future__ import annotations

import unittest

from clusterctl.cli_args import SUBCOMMANDS, normalize_global_argv
from clusterctl.docker_executor import CLUSTER_SUBCOMMANDS
from clusterctl.exceptions import ClusterctlError
from clusterctl.phase_plan import (
    PhaseExecutionPlan,
    PhaseInvocationPlan,
    PhasePlanSummary,
    PhaseStagePlan,
    apply_play_cli_overrides,
    ensure_run_plan_nonempty,
    resolve_play_phase_target,
    slice_phase_refs,
)
from clusterctl.playbooks_config import InvocationSpec, PhasesConfig


def _stage(*, git_ssh: bool = False, inv_count: int = 2) -> PhaseStagePlan:
    invocations = tuple(
        PhaseInvocationPlan(
            phase_ref="atlas-redis/cluster",
            repo_name="atlas-redis",
            entry_name="cluster",
            repo_base="/tmp/atlas-redis",
            playbook_file="playbooks/redis_cluster.yaml",
            invocation_index=index,
            invocation=InvocationSpec(tags=f"tag{index}"),
        )
        for index in range(1, inv_count + 1)
    )
    return PhaseStagePlan(
        phase_ref="atlas-redis/cluster",
        repo_name="atlas-redis",
        entry_name="cluster",
        playbook_file="playbooks/redis_cluster.yaml",
        repo_base="/tmp/atlas-redis",
        git_ssh=git_ssh,
        invocations=invocations,
    )


def _plan(
    stage: PhaseStagePlan | None = None,
    *,
    filter_skipped: tuple[tuple[str, str], ...] = (),
) -> PhaseExecutionPlan:
    if stage is None:
        return PhaseExecutionPlan(
            summary=PhasePlanSummary(
                cluster_id="lab/test",
                workspace_id="ws",
                execution="local",
                execution_source="cluster.yaml",
                phases=(),
                invocation_count=0,
                inventory="hosts",
                schema_version=2,
            ),
            stages=(),
            filter_skipped=filter_skipped,
        )
    return PhaseExecutionPlan(
        summary=PhasePlanSummary(
            cluster_id="lab/test",
            workspace_id="ws",
            execution="local",
            execution_source="cluster.yaml",
            phases=(stage.phase_ref,),
            invocation_count=len(stage.invocations),
            inventory="hosts",
            schema_version=2,
        ),
        stages=(stage,),
        filter_skipped=filter_skipped,
    )


class PlayPhaseTargetTest(unittest.TestCase):
    def test_positional_only(self) -> None:
        self.assertEqual(resolve_play_phase_target(playbook="redis", phase=None), "redis")

    def test_matching_phase_flag(self) -> None:
        self.assertEqual(
            resolve_play_phase_target(playbook="redis", phase="redis"),
            "redis",
        )

    def test_conflict_raises(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            resolve_play_phase_target(playbook="redis", phase="provision")
        self.assertIn("conflicting play targets", str(ctx.exception))

    def test_empty_raises(self) -> None:
        with self.assertRaises(ClusterctlError):
            resolve_play_phase_target(playbook="  ", phase=None)


class PlayCliOverridesTest(unittest.TestCase):
    def test_git_ssh_alone_keeps_catalog_invocations(self) -> None:
        plan = _plan(_stage(git_ssh=False, inv_count=3))
        out = apply_play_cli_overrides(plan, git_ssh=True)
        self.assertTrue(out.stages[0].git_ssh)
        self.assertEqual(len(out.stages[0].invocations), 3)
        self.assertEqual(out.summary.invocation_count, 3)

    def test_git_ssh_noop_when_already_set(self) -> None:
        plan = _plan(_stage(git_ssh=True))
        out = apply_play_cli_overrides(plan, git_ssh=True)
        self.assertIs(out, plan)

    def test_tags_collapse_to_single_invocation(self) -> None:
        plan = _plan(_stage(git_ssh=False, inv_count=3))
        out = apply_play_cli_overrides(plan, tags="204_redis_verify", git_ssh=True)
        self.assertEqual(len(out.stages[0].invocations), 1)
        self.assertEqual(out.stages[0].invocations[0].invocation.tags, "204_redis_verify")
        self.assertTrue(out.stages[0].git_ssh)
        self.assertEqual(out.summary.invocation_count, 1)

    def test_no_overrides_passthrough(self) -> None:
        plan = _plan(_stage(git_ssh=False))
        self.assertIs(apply_play_cli_overrides(plan), plan)


class EmptyRunGuardTest(unittest.TestCase):
    def test_nonempty_passthrough(self) -> None:
        plan = _plan(_stage())
        self.assertIs(ensure_run_plan_nonempty(plan), plan)

    def test_empty_raises_with_when_hint(self) -> None:
        plan = _plan(
            filter_skipped=(("atlas-redis/cluster", "missing inventory group"),),
        )
        with self.assertRaises(ClusterctlError) as ctx:
            ensure_run_plan_nonempty(plan)
        msg = str(ctx.exception)
        self.assertIn("execution plan is empty", msg)
        self.assertIn("when-filter skipped", msg)
        self.assertIn("atlas-redis/cluster", msg)


class SlicePhaseRefsMessageTest(unittest.TestCase):
    def test_missing_boundary_lists_available_not_phases_flag(self) -> None:
        phases = PhasesConfig(
            phases=("atlas-redis/cluster",),
            phase_aliases={"init": "atlas-node-foundation/init"},
        )
        with self.assertRaises(ClusterctlError) as ctx:
            slice_phase_refs(phases.phases, from_phase="init", phases=phases)
        msg = str(ctx.exception)
        self.assertIn("available:", msg)
        self.assertIn("atlas-redis/cluster", msg)
        self.assertNotIn("(--phases)", msg)


class SubcommandsParityTest(unittest.TestCase):
    def test_playbooks_repos_in_cli_and_docker(self) -> None:
        self.assertIn("playbooks", SUBCOMMANDS)
        self.assertIn("repos", SUBCOMMANDS)
        self.assertEqual(SUBCOMMANDS, CLUSTER_SUBCOMMANDS)

    def test_hoist_cluster_before_playbooks(self) -> None:
        argv = normalize_global_argv(
            ["cluster", "playbooks", "status", "--cluster", "lab/x"]
        )
        self.assertEqual(
            argv,
            ["cluster", "--cluster", "lab/x", "playbooks", "status"],
        )

    def test_hoist_cluster_before_repos(self) -> None:
        argv = normalize_global_argv(["repos", "show", "--cluster", "lab/x"])
        self.assertEqual(argv, ["cluster", "--cluster", "lab/x", "repos", "show"])


if __name__ == "__main__":
    unittest.main()
