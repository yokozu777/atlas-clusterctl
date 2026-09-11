"""ADR 006 Phase 0: playbooks_enabled omit→infer / false override matrix."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_config import (
    merge_cluster_config_v2,
    parse_cluster_config_v2_fragment,
    resolve_playbooks_enabled,
)

# Minimal catalog — enough for effective_playbooks_enabled() infer.
_MIN_PLAYBOOKS = {
    "rare-stack": {
        "source": "local",
        "path": "rare-stack",
        "path_relative_to": "sibling",
        "layout": "roles/",
        "sync": "never",
        "entries": {
            "install": {
                "file": "playbooks/install.yaml",
                "invocations": [{"tags": "all"}],
            }
        },
    }
}


class PlaybooksEnabledInferContractTest(unittest.TestCase):
    """Phase 0 matrix — documents current runtime (no YAML SoT deletion)."""

    def test_omit_flag_with_playbooks_infers_enabled(self) -> None:
        cfg = parse_cluster_config_v2_fragment(
            {
                "schema_version": 2,
                "id": "lab/rare",
                "playbooks": _MIN_PLAYBOOKS,
                "phases": ["rare-stack/install"],
            }
        )
        self.assertIsNone(cfg.playbooks_enabled)
        self.assertTrue(cfg.effective_playbooks_enabled())
        self.assertTrue(resolve_playbooks_enabled({}, config_v2=cfg))

    def test_omit_flag_without_playbooks_is_disabled(self) -> None:
        cfg = parse_cluster_config_v2_fragment(
            {"schema_version": 2, "id": "lab/empty"}
        )
        self.assertIsNone(cfg.playbooks_enabled)
        self.assertFalse(cfg.effective_playbooks_enabled())

    def test_explicit_true_still_enabled(self) -> None:
        cfg = parse_cluster_config_v2_fragment(
            {
                "schema_version": 2,
                "playbooks_enabled": True,
                "playbooks": _MIN_PLAYBOOKS,
                "phases": ["rare-stack/install"],
            }
        )
        self.assertTrue(cfg.playbooks_enabled)
        self.assertTrue(cfg.effective_playbooks_enabled())

    def test_explicit_false_disables_even_with_playbooks(self) -> None:
        cfg = parse_cluster_config_v2_fragment(
            {
                "schema_version": 2,
                "playbooks_enabled": False,
                "playbooks": _MIN_PLAYBOOKS,
                "phases": ["rare-stack/install"],
            }
        )
        self.assertFalse(cfg.playbooks_enabled)
        self.assertFalse(cfg.effective_playbooks_enabled())
        self.assertFalse(
            resolve_playbooks_enabled({"playbooks_enabled": False}, config_v2=cfg)
        )

    def test_cascade_both_omit_infers_from_merged_playbooks(self) -> None:
        base = parse_cluster_config_v2_fragment(
            {
                "schema_version": 2,
                "playbooks": _MIN_PLAYBOOKS,
            }
        )
        child = parse_cluster_config_v2_fragment(
            {
                "schema_version": 2,
                "id": "lab/rare",
                "phases": ["rare-stack/install"],
            }
        )
        merged = merge_cluster_config_v2(base, child)
        self.assertIsNone(base.playbooks_enabled)
        self.assertIsNone(child.playbooks_enabled)
        self.assertIsNone(merged.playbooks_enabled)
        self.assertTrue(merged.effective_playbooks_enabled())

    def test_cascade_parent_true_child_omit_stays_enabled(self) -> None:
        base = parse_cluster_config_v2_fragment({"playbooks_enabled": True})
        child = parse_cluster_config_v2_fragment({"id": "lab/rare"})
        merged = merge_cluster_config_v2(base, child)
        self.assertIsNone(child.playbooks_enabled)
        self.assertTrue(merged.playbooks_enabled)
        self.assertTrue(merged.effective_playbooks_enabled())

    def test_cascade_parent_omit_child_false_disables(self) -> None:
        base = parse_cluster_config_v2_fragment(
            {
                "playbooks": _MIN_PLAYBOOKS,
            }
        )
        child = parse_cluster_config_v2_fragment({"playbooks_enabled": False})
        merged = merge_cluster_config_v2(base, child)
        self.assertTrue(base.effective_playbooks_enabled())
        self.assertFalse(merged.playbooks_enabled)
        self.assertFalse(merged.effective_playbooks_enabled())

    def test_leaf_explicit_false_wins_over_merged_infer(self) -> None:
        """resolve_playbooks_enabled: leaf YAML explicit beats merged v2."""
        merged = parse_cluster_config_v2_fragment(
            {
                "playbooks": _MIN_PLAYBOOKS,
                "phases": ["rare-stack/install"],
            }
        )
        self.assertTrue(merged.effective_playbooks_enabled())
        self.assertFalse(
            resolve_playbooks_enabled(
                {"playbooks_enabled": False},
                config_v2=merged,
            )
        )

    def test_playbooks_feature_enabled_matches_effective_infer(self) -> None:
        """Phase 1: single-fragment helper agrees with ClusterConfigV2 infer."""
        from clusterctl.playbooks_config import playbooks_feature_enabled

        raw = {
            "schema_version": 2,
            "playbooks": _MIN_PLAYBOOKS,
            "phases": ["rare-stack/install"],
        }
        cfg = parse_cluster_config_v2_fragment(raw)
        self.assertTrue(cfg.effective_playbooks_enabled())
        self.assertTrue(playbooks_feature_enabled(raw))
        self.assertFalse(
            playbooks_feature_enabled(
                {**raw, "playbooks_enabled": False}
            )
        )


class PlaybooksEnabledInferContextTest(unittest.TestCase):
    """End-to-end: ClusterContext.load with omit / false on a leaf."""

    _ISOLATED_ENV_KEYS = (
        "ATLAS_CLUSTER_ROOT",
        "CLUSTER_ID",
        "ATLAS_CLUSTERCTL_CONFIG",
    )

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)
        seed_local_playbook_repo_stubs(self.root)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _write_leaf(self, data: dict) -> None:
        leaf = self.root / "clusters" / "lab" / "infer"
        leaf.mkdir(parents=True)
        (leaf / "hosts").write_text(
            "all:\n  hosts:\n    localhost: {}\n",
            encoding="utf-8",
        )
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/infer",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(data, sort_keys=False),
            encoding="utf-8",
        )
        (self.root / ".cluster-active").write_text("lab/infer\n", encoding="utf-8")

    def test_context_omitted_flag_with_playbooks_is_enabled(self) -> None:
        self._write_leaf(
            {
                "schema_version": 2,
                "id": "lab/infer",
                "inventory": "hosts",
                "playbooks": local_playbooks_override_block(
                    "atlas-node-foundation",
                    "atlas-compute-provision",
                    "atlas-k8s-core",
                    "atlas-k8s-addons",
                ),
                "phases": [
                    "atlas-compute-provision/templates",
                    "atlas-compute-provision/provision",
                    "atlas-node-foundation/init",
                    "atlas-k8s-core/cluster",
                    "atlas-k8s-addons/addons",
                ],
            }
        )
        ctx = ClusterContext.load(cluster_id="lab/infer")
        self.assertTrue(ctx.playbooks_enabled)

    def test_context_explicit_false_is_disabled(self) -> None:
        self._write_leaf(
            {
                "schema_version": 2,
                "id": "lab/infer",
                "inventory": "hosts",
                "playbooks_enabled": False,
                "playbooks": local_playbooks_override_block(
                    "atlas-node-foundation",
                    "atlas-compute-provision",
                    "atlas-k8s-core",
                    "atlas-k8s-addons",
                ),
                "phases": [
                    "atlas-compute-provision/templates",
                    "atlas-node-foundation/init",
                ],
            }
        )
        ctx = ClusterContext.load(cluster_id="lab/infer")
        self.assertFalse(ctx.playbooks_enabled)


if __name__ == "__main__":
    unittest.main()
