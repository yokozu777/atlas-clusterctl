"""Contract matrix for ADR 009 ``classify_run_overrides`` / ``apply_run_cli_overrides``."""

from __future__ import annotations

import unittest

from clusterctl.exceptions import ClusterctlError
from clusterctl.phase_plan import (
    PhaseExecutionPlan,
    PhaseInvocationPlan,
    PhasePlanSummary,
    PhaseStagePlan,
)
from clusterctl.playbooks_config import InvocationSpec
from clusterctl.run_overrides import (
    RunOverrideMode,
    apply_run_cli_overrides,
    classify_run_overrides,
    normalize_run_extra_vars,
    normalize_run_tags,
    resolve_run_limit,
)


def _stage(
    *,
    phase_ref: str = "atlas-redis/cluster",
    git_ssh: bool = False,
    inv_count: int = 2,
    extra_e: tuple[str, ...] = (),
) -> PhaseStagePlan:
    repo, entry = phase_ref.split("/", 1)
    invocations = tuple(
        PhaseInvocationPlan(
            phase_ref=phase_ref,
            repo_name=repo,
            entry_name=entry,
            repo_base=f"/tmp/{repo}",
            playbook_file=f"playbooks/{entry}.yaml",
            invocation_index=index,
            invocation=InvocationSpec(tags=f"tag{index}", extra_e=extra_e),
        )
        for index in range(1, inv_count + 1)
    )
    return PhaseStagePlan(
        phase_ref=phase_ref,
        repo_name=repo,
        entry_name=entry,
        playbook_file=f"playbooks/{entry}.yaml",
        repo_base=f"/tmp/{repo}",
        git_ssh=git_ssh,
        invocations=invocations,
    )


def _plan(*stages: PhaseStagePlan) -> PhaseExecutionPlan:
    if not stages:
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
            filter_skipped=(),
        )
    return PhaseExecutionPlan(
        summary=PhasePlanSummary(
            cluster_id="lab/test",
            workspace_id="ws",
            execution="local",
            execution_source="cluster.yaml",
            phases=tuple(stage.phase_ref for stage in stages),
            invocation_count=sum(len(stage.invocations) for stage in stages),
            inventory="hosts",
            schema_version=2,
        ),
        stages=stages,
        filter_skipped=(),
    )


class RunOverridesContractTest(unittest.TestCase):
    def test_normalize_tags_empty_is_all(self) -> None:
        self.assertEqual(normalize_run_tags(None), "all")
        self.assertEqual(normalize_run_tags(""), "all")
        self.assertEqual(normalize_run_tags("  "), "all")
        self.assertEqual(normalize_run_tags("204_redis_verify"), "204_redis_verify")

    def test_normalize_extra_vars_drops_blanks(self) -> None:
        self.assertEqual(
            normalize_run_extra_vars(("a=1", "", "  ", "b=2")),
            ("a=1", "b=2"),
        )

    def test_catalog_no_overrides(self) -> None:
        self.assertEqual(
            classify_run_overrides(phase_count=3),
            RunOverrideMode.CATALOG,
        )
        self.assertEqual(
            classify_run_overrides(phase_count=1, tags="all", extra_vars=()),
            RunOverrideMode.CATALOG,
        )

    def test_merge_e_single_and_multi_phase(self) -> None:
        for count in (1, 2, 5):
            self.assertEqual(
                classify_run_overrides(
                    phase_count=count,
                    extra_vars=("provision_mode=destroy",),
                ),
                RunOverrideMode.MERGE_EXTRA,
                msg=f"phase_count={count}",
            )
        self.assertEqual(
            classify_run_overrides(
                phase_count=2,
                tags="all",
                extra_vars=("a=1", "b=2"),
            ),
            RunOverrideMode.MERGE_EXTRA,
        )

    def test_collapse_tags_or_limit_or_root_ssh_single_phase(self) -> None:
        self.assertEqual(
            classify_run_overrides(phase_count=1, tags="204_redis_verify"),
            RunOverrideMode.COLLAPSE,
        )
        self.assertEqual(
            classify_run_overrides(phase_count=1, limit="k8s_masters"),
            RunOverrideMode.COLLAPSE,
        )
        self.assertEqual(
            classify_run_overrides(phase_count=1, root_ssh=True),
            RunOverrideMode.COLLAPSE,
        )
        # Selective + -e still collapses (former play): -e rides on one invocation.
        self.assertEqual(
            classify_run_overrides(
                phase_count=1,
                tags="10_tf_apply",
                extra_vars=("provision_mode=destroy",),
            ),
            RunOverrideMode.COLLAPSE,
        )

    def test_error_multi_phase_selective(self) -> None:
        for kwargs in (
            {"tags": "10_tf_apply"},
            {"limit": "redis_cluster_masters"},
            {"root_ssh": True},
            {"tags": "x", "extra_vars": ("a=1",)},
        ):
            self.assertEqual(
                classify_run_overrides(phase_count=2, **kwargs),
                RunOverrideMode.ERROR_MULTI_PHASE_SELECTIVE,
                msg=str(kwargs),
            )

    def test_git_ssh_not_in_classifier(self) -> None:
        # Documented: --git-ssh alone must not change mode (no parameter here).
        self.assertEqual(
            classify_run_overrides(phase_count=2, extra_vars=()),
            RunOverrideMode.CATALOG,
        )

    def test_blank_extra_vars_ignored(self) -> None:
        self.assertEqual(
            classify_run_overrides(phase_count=1, extra_vars=("", "  ")),
            RunOverrideMode.CATALOG,
        )

    def test_phase_count_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            classify_run_overrides(phase_count=0)


class ApplyRunCliOverridesTest(unittest.TestCase):
    def test_catalog_passthrough(self) -> None:
        plan = _plan(_stage(inv_count=3))
        self.assertIs(apply_run_cli_overrides(plan), plan)

    def test_git_ssh_alone_keeps_catalog(self) -> None:
        plan = _plan(_stage(git_ssh=False, inv_count=3))
        out = apply_run_cli_overrides(plan, git_ssh=True)
        self.assertTrue(out.stages[0].git_ssh)
        self.assertEqual(len(out.stages[0].invocations), 3)

    def test_merge_e_appends_without_collapse_multi_phase(self) -> None:
        plan = _plan(
            _stage(phase_ref="atlas-compute-provision/provision", inv_count=3),
            _stage(phase_ref="atlas-redis/cluster", inv_count=2),
        )
        out = apply_run_cli_overrides(
            plan,
            extra_vars=("provision_mode=destroy", "foo=bar"),
        )
        self.assertEqual(len(out.stages), 2)
        self.assertEqual(len(out.stages[0].invocations), 3)
        self.assertEqual(len(out.stages[1].invocations), 2)
        self.assertEqual(out.summary.invocation_count, 5)
        for stage in out.stages:
            for inv in stage.invocations:
                self.assertEqual(
                    inv.invocation.extra_e,
                    ("provision_mode=destroy", "foo=bar"),
                )

    def test_merge_e_appends_to_existing_extra_e(self) -> None:
        plan = _plan(_stage(inv_count=1, extra_e=("already=1",)))
        out = apply_run_cli_overrides(plan, extra_vars=("provision_mode=destroy",))
        self.assertEqual(
            out.stages[0].invocations[0].invocation.extra_e,
            ("already=1", "provision_mode=destroy"),
        )

    def test_collapse_single_phase_with_tags_and_e(self) -> None:
        plan = _plan(_stage(inv_count=4))
        out = apply_run_cli_overrides(
            plan,
            tags="10_tf_apply",
            extra_vars=("provision_mode=destroy",),
            git_ssh=True,
        )
        self.assertEqual(len(out.stages[0].invocations), 1)
        inv = out.stages[0].invocations[0].invocation
        self.assertEqual(inv.tags, "10_tf_apply")
        self.assertEqual(inv.extra_e, ("provision_mode=destroy",))
        self.assertTrue(out.stages[0].git_ssh)
        self.assertEqual(out.summary.invocation_count, 1)

    def test_multi_phase_tags_errors(self) -> None:
        plan = _plan(
            _stage(phase_ref="atlas-compute-provision/provision"),
            _stage(phase_ref="atlas-redis/cluster"),
        )
        with self.assertRaises(ClusterctlError) as ctx:
            apply_run_cli_overrides(plan, tags="10_tf_apply")
        msg = str(ctx.exception)
        self.assertIn("single phase", msg)
        self.assertIn("ADR 009", msg)

    def test_empty_plan_errors(self) -> None:
        with self.assertRaises(ClusterctlError):
            apply_run_cli_overrides(_plan())


class ResolveRunLimitTest(unittest.TestCase):
    """Post–ADR 009 A1: CLI --limit / env LIMIT unify for all execute verbs."""

    def test_cli_wins_over_env(self) -> None:
        self.assertEqual(
            resolve_run_limit("k8s_masters", env={"LIMIT": "workers"}),
            "k8s_masters",
        )

    def test_env_fallback(self) -> None:
        self.assertEqual(
            resolve_run_limit(None, env={"LIMIT": "redis_cluster_masters"}),
            "redis_cluster_masters",
        )
        self.assertEqual(
            resolve_run_limit("", env={"LIMIT": "  hosts  "}),
            "hosts",
        )

    def test_blank_cli_and_env_unset(self) -> None:
        self.assertIsNone(resolve_run_limit(None, env={}))
        self.assertIsNone(resolve_run_limit("  ", env={"LIMIT": ""}))
        self.assertIsNone(resolve_run_limit(None, env={"LIMIT": "   "}))

    def test_env_limit_collapses_single_phase(self) -> None:
        limit = resolve_run_limit(None, env={"LIMIT": "k8s_masters"})
        self.assertEqual(
            classify_run_overrides(phase_count=1, limit=limit),
            RunOverrideMode.COLLAPSE,
        )
        plan = _plan(_stage(inv_count=3))
        out = apply_run_cli_overrides(plan, limit=limit)
        self.assertEqual(len(out.stages[0].invocations), 1)
        self.assertEqual(out.stages[0].invocations[0].invocation.limit, "k8s_masters")

    def test_env_limit_multi_phase_errors(self) -> None:
        limit = resolve_run_limit(None, env={"LIMIT": "localhost"})
        plan = _plan(
            _stage(phase_ref="atlas-compute-provision/provision"),
            _stage(phase_ref="atlas-redis/cluster"),
        )
        with self.assertRaises(ClusterctlError) as ctx:
            apply_run_cli_overrides(plan, limit=limit)
        self.assertIn("ADR 009", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
