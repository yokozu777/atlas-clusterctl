"""Tests for schema v2 playbooks + phases (PR-0)."""

from __future__ import annotations

from tests.lab_support import lab_id_for, skip_unless_stack, FULL_K8S_INVOCATION_COUNT

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config_loader import (
    dump_cluster_config_v2,
    load_cluster_config_v2_fragments,
    load_merged_cluster_config_v2,
)
from clusterctl.cluster_layout import (
    cascade_fragment_paths,
    cluster_config_dir,
    is_deployable_config_dir,
    list_cluster_ids,
    validate_cluster_id,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.phase_filter import PhaseFilterContext, filter_phases
from clusterctl.pipeline import load_pipeline
from clusterctl.pipeline_fixture import (
    build_org_baseline_cluster_config,
    build_org_baseline_phases,
    default_git_repos_from_yaml,
    load_org_baseline_cluster_config,
    load_public_reference_cluster_config,
    migration_table,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_config import (
    SCHEMA_VERSION,
    merge_cluster_config_v2,
    merge_playbooks_configs,
    parse_cluster_config_v2_fragment,
    parse_phase_ref,
    playbooks_feature_enabled,
    resolve_phase_alias,
)


class PlaybooksConfigTest(unittest.TestCase):
    def test_parse_phase_ref(self) -> None:
        self.assertEqual(parse_phase_ref("atlas-compute-provision/provision"), ("atlas-compute-provision", "provision"))

    def test_invalid_phase_ref(self) -> None:
        with self.assertRaises(ClusterctlError):
            parse_phase_ref("no-slash")

    def test_playbooks_feature_enabled_infers_from_playbooks(self) -> None:
        """ADR 006 Phase 1: omit flag + non-empty playbooks → enabled."""
        self.assertTrue(
            playbooks_feature_enabled(
                {
                    "playbooks": {
                        "rare-stack": {
                            "source": "local",
                            "path": "rare-stack",
                            "entries": {
                                "install": {
                                    "file": "playbooks/install.yaml",
                                    "invocations": [{"tags": "all"}],
                                }
                            },
                        }
                    }
                }
            )
        )
        self.assertFalse(playbooks_feature_enabled({"playbooks": {}}))
        self.assertFalse(
            playbooks_feature_enabled(
                {
                    "playbooks_enabled": False,
                    "playbooks": {
                        "rare-stack": {
                            "source": "local",
                            "path": "rare-stack",
                            "entries": {
                                "install": {
                                    "file": "playbooks/install.yaml",
                                    "invocations": [{"tags": "all"}],
                                }
                            },
                        }
                    },
                }
            )
        )

    def test_playbooks_feature_enabled_explicit_only(self) -> None:
        self.assertTrue(playbooks_feature_enabled({"playbooks_enabled": True}))
        self.assertFalse(playbooks_feature_enabled({}))
        with self.assertRaises(ClusterctlError):
            playbooks_feature_enabled(
                {"role_repos": {"atlas-node-foundation": {"source": "local", "path": "atlas-node-foundation"}}}
            )
        self.assertFalse(playbooks_feature_enabled({}))

    def test_merge_playbooks_local_override(self) -> None:
        base_raw = {
            "atlas-compute-provision": {
                "source": "git",
                "url": "git@example.com/a.git",
                "ref": "main",
                "layout": "roles/",
                "entries": {
                    "provision": {
                        "file": "playbooks/provision_nodes.yaml",
                        "invocations": [{"tags": "10_tf_apply"}],
                    }
                },
            }
        }
        override_raw = {
            "atlas-compute-provision": {
                "source": "local",
                "path": "atlas-compute-provision",
                "path_relative_to": "sibling",
                "sync": "never",
            }
        }
        from clusterctl.playbooks_config import parse_playbooks_config

        merged = merge_playbooks_configs(
            parse_playbooks_config(base_raw),
            parse_playbooks_config(override_raw),
        )
        assert merged is not None
        repo = merged.repos["atlas-compute-provision"]
        self.assertEqual(repo.source, "local")
        self.assertEqual(repo.path, "atlas-compute-provision")
        self.assertEqual(repo.layout, "roles/")
        self.assertEqual(repo.url, "git@example.com/a.git")
        self.assertEqual(len(repo.entries["provision"].invocations), 1)

    def test_merge_phases_replace(self) -> None:
        from clusterctl.playbooks_config import PhasesConfig, merge_phases_configs

        base = PhasesConfig(phases=("a/one", "b/two"))
        override = PhasesConfig(phases=("c/three",))
        merged = merge_phases_configs(base, override)
        assert merged is not None
        self.assertEqual(merged.phases, ("c/three",))

    def test_merge_phases_empty_list_replaces(self) -> None:
        """Explicit phases: [] replaces parent; omit (None) still inherits."""
        from clusterctl.playbooks_config import PhasesConfig, merge_phases_configs

        base = PhasesConfig(
            phases=("a/one",),
            phase_aliases={"a": "a/one"},
        )
        empty = PhasesConfig(phases=(), phase_aliases={})
        merged = merge_phases_configs(base, empty)
        assert merged is not None
        self.assertEqual(merged.phases, ())
        self.assertEqual(merged.phase_aliases, {})

        inherited = merge_phases_configs(base, None)
        assert inherited is not None
        self.assertEqual(inherited.phases, ("a/one",))
        self.assertEqual(inherited.phase_aliases, {"a": "a/one"})


class ClusterLayoutTest(unittest.TestCase):
    def test_validate_hierarchical_id(self) -> None:
        self.assertEqual(validate_cluster_id("fixture/k8s"), "fixture/k8s")

    def test_org_baseline_id(self) -> None:
        self.assertEqual(validate_cluster_id("default/default", allow_policy_ids=True), "default/default")

    def test_env_policy_id_blocked_for_deploy(self) -> None:
        with self.assertRaises(ClusterctlError):
            validate_cluster_id("dev/default")

    def test_cluster_config_dir(self) -> None:
        root = Path("/repo/clusters")
        self.assertEqual(
            cluster_config_dir(root, "fixture/k8s"),
            Path("/repo/clusters/fixture/k8s"),
        )


K8S_CORE_PHASE = "atlas-k8s-core/cluster"
K8S_ADDONS_PHASE = "atlas-k8s-addons/addons"
K8S_STACK_SKIP_PHASES = (K8S_CORE_PHASE, K8S_ADDONS_PHASE)


class PhaseFilterTest(unittest.TestCase):
    def test_skip_platform_without_k8s(self) -> None:
        config = build_org_baseline_cluster_config(Path(__file__).resolve().parents[1])
        assert config.playbooks is not None
        assert config.phases is not None
        ctx = PhaseFilterContext(
            inventory_groups=frozenset({"infra_platform"}),
            merged_vars={"provision_stack": "infra"},
        )
        result = filter_phases(config.phases.phases, config.playbooks, ctx)
        for phase_ref in K8S_STACK_SKIP_PHASES:
            self.assertNotIn(phase_ref, result.included)
            self.assertTrue(any(ref == phase_ref for ref, _ in result.skipped))

    def test_full_stack_inventory_includes_platform(self) -> None:
        config = build_org_baseline_cluster_config(Path(__file__).resolve().parents[1])
        assert config.playbooks is not None
        assert config.phases is not None
        ctx = PhaseFilterContext(
            inventory_groups=frozenset(
                {"infra_platform", "k8s_lbs", "k8s_masters", "k8s_workers"}
            ),
            merged_vars={"provision_stack": "k8s"},
        )
        result = filter_phases(config.phases.phases, config.playbooks, ctx)
        for phase_ref in K8S_STACK_SKIP_PHASES:
            self.assertIn(phase_ref, result.included)


class PipelineFixtureTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT",)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)

    def tearDown(self) -> None:
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmpdir.cleanup()

    def test_migration_table_covers_all_stages(self) -> None:
        stages = {row["legacy_stage"] for row in migration_table()}
        self.assertEqual(stages, {stage.name for stage in load_pipeline()})

    def test_org_baseline_invocation_parity(self) -> None:
        config = build_org_baseline_cluster_config(self.root)
        config.validate()
        pipeline_count = sum(len(stage.invocations) for stage in load_pipeline())
        assert config.playbooks is not None
        assert config.phases is not None
        self.assertEqual(config.phases.invocation_count(config.playbooks), pipeline_count)
        self.assertEqual(pipeline_count, FULL_K8S_INVOCATION_COUNT)

    def test_all_stages_mapped_to_phase_refs(self) -> None:
        phases = build_org_baseline_phases()
        for stage in load_pipeline():
            self.assertIn(stage.phase_ref, phases.phases)
            self.assertEqual(
                resolve_phase_alias(stage.name, phases.phase_aliases),
                stage.phase_ref,
            )

    def test_phase_aliases_resolve(self) -> None:
        phases = build_org_baseline_phases()
        target = resolve_phase_alias("k8s-addons", phases.phase_aliases)
        self.assertEqual(target, "atlas-k8s-addons/addons")

    def test_generated_yaml_roundtrip(self) -> None:
        config = build_org_baseline_cluster_config(self.root)
        dumped = yaml.safe_load(dump_cluster_config_v2(config))
        reparsed = parse_cluster_config_v2_fragment(dumped)
        reparsed.validate()
        self.assertEqual(reparsed.schema_version, SCHEMA_VERSION)
        assert reparsed.playbooks is not None
        assert config.playbooks is not None
        self.assertEqual(
            set(reparsed.playbooks.repos),
            set(config.playbooks.repos),
        )


class OrgFixtureFileTest(unittest.TestCase):
    def test_public_k8s_template_loads_as_org_baseline_sot(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "clusters" / "default" / "default" / "cluster.yaml").is_file())
        self.assertTrue((root / "clusters" / "_template" / "k8s_full" / "cluster.yaml").is_file())
        config = load_org_baseline_cluster_config(root)
        config.validate()
        assert config.playbooks is not None
        assert config.phases is not None
        self.assertEqual(len(config.phases.phases), 4)
        self.assertEqual(config.phases.invocation_count(config.playbooks), FULL_K8S_INVOCATION_COUNT)
        self.assertNotIn("atlas-infra-edge", config.playbooks.repos)

    def test_public_template_fragment_parses(self) -> None:
        config = load_public_reference_cluster_config()
        config.validate()
        assert config.playbooks is not None
        self.assertIn("atlas-k8s-core", config.playbooks.repos)
        self.assertNotIn("atlas-infra-edge", config.playbooks.repos)

    @skip_unless_stack("k8s")
    def test_lab_k8s_loads_full_cascade(self) -> None:
        lab = lab_id_for("k8s")
        assert lab is not None
        from clusterctl.cluster_config_loader import load_merged_cluster_config_v2_for_repo

        root = Path(__file__).resolve().parents[1]
        config = load_merged_cluster_config_v2_for_repo(root, lab)
        config.validate()
        assert config.playbooks is not None
        assert config.phases is not None
        self.assertEqual(len(config.phases.phases), 4)
        self.assertEqual(config.phases.invocation_count(config.playbooks), FULL_K8S_INVOCATION_COUNT)
        self.assertNotIn("atlas-infra-edge", config.playbooks.repos)
        self.assertEqual(config.cluster_id, lab)

    def test_cascade_paths_include_org_baseline(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = cascade_fragment_paths(root / "clusters", "default/default")
        self.assertTrue(paths)
        self.assertEqual(paths[0].name, "cluster.yaml")


class CascadeMergeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.clusters = self.root / "clusters"
        org = build_org_baseline_cluster_config()
        org_path = self.clusters / "default" / "default" / "cluster.yaml"
        org_path.parent.mkdir(parents=True)
        org_path.write_text(dump_cluster_config_v2(org), encoding="utf-8")

        env_default = {
            "schema_version": 2,
            "playbooks": {
                "atlas-node-foundation": {
                    "source": "local",
                    "path": "atlas-node-foundation",
                    "path_relative_to": "sibling",
                    "sync": "never",
                }
            },
            "execution": {"mode": "local"},
        }
        env_path = self.clusters / "fixture" / "default" / "cluster.yaml"
        env_path.parent.mkdir(parents=True)
        env_path.write_text(yaml.safe_dump(env_default), encoding="utf-8")

        leaf = {
            "schema_version": 2,
            "id": "fixture/k8s",
            "display_name": "Fixture k8s",
            "inventory": "hosts",
            "playbooks_enabled": True,
        }
        leaf_path = self.clusters / "fixture" / "k8s" / "cluster.yaml"
        leaf_path.parent.mkdir(parents=True)
        leaf_path.write_text(yaml.safe_dump(leaf), encoding="utf-8")
        (leaf_path.parent / "hosts").write_text("[all]\nlocalhost\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_merged_fixture_k8s_local_override(self) -> None:
        config = load_merged_cluster_config_v2(self.clusters, "fixture/k8s")
        config.validate()
        assert config.playbooks is not None
        foundation_repo = config.playbooks.repos["atlas-node-foundation"]
        self.assertEqual(foundation_repo.source, "local")
        self.assertEqual(foundation_repo.path, "atlas-node-foundation")
        self.assertEqual(config.execution.get("mode"), "local")
        self.assertEqual(config.cluster_id, "fixture/k8s")
        self.assertTrue(config.deployable)
        self.assertTrue(is_deployable_config_dir(self.clusters / "fixture" / "k8s"))

    def test_list_cluster_ids_finds_hierarchical(self) -> None:
        ids = list_cluster_ids(self.clusters)
        self.assertIn("fixture/k8s", ids)
        self.assertIn("fixture/default", ids)


if __name__ == "__main__":
    unittest.main()
