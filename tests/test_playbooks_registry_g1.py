"""Tests for PR-G1: schema-driven playbook repo registry."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import (
    org_baseline_required_repo_names,
    seed_org_baseline_fixture,
)
from clusterctl.playbooks_registry import (
    repo_names_from_phase_refs,
    required_playbook_repo_names,
)
from clusterctl.playbooks_repos import resolved_playbook_repos_from_config
from clusterctl.playbooks_resolve import build_resolved_playbooks_repos
from clusterctl.playbooks_validate import validate_org_baseline_playbooks
from clusterctl.tools.generate_org_cluster_fixture import main as validate_org_fixture


class PlaybooksRegistryG1Test(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT",)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        seed_org_baseline_fixture(self.root)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_org_baseline_required_repos_from_phases(self) -> None:
        required = org_baseline_required_repo_names(self.root)
        self.assertEqual(len(required), 4)
        self.assertIn("atlas-k8s-core", required)
        self.assertIn("atlas-node-foundation", required)
        self.assertNotIn("atlas-infra-edge", required)

    def test_repo_names_from_phase_refs_preserves_order(self) -> None:
        names = repo_names_from_phase_refs(
            (
                "atlas-compute-provision/templates",
                "atlas-compute-provision/provision",
                "atlas-node-foundation/init",
            )
        )
        self.assertEqual(names, ("atlas-compute-provision", "atlas-node-foundation"))

    def test_fifth_repo_validate_and_resolve_without_python_changes(self) -> None:
        from clusterctl.cluster_config_loader import load_merged_cluster_config_v2

        path = self.root / "clusters" / "default" / "default" / "cluster.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["playbooks"]["rare-stack"] = {
            "source": "git",
            "url": "git@example.com/org/rare-stack.git",
            "ref": "main",
            "layout": "roles/",
            "entries": {
                "install": {
                    "file": "playbooks/install.yaml",
                    "invocations": [{"tags": "all"}],
                }
            },
        }
        data["phases"].append("rare-stack/install")
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

        self.assertEqual(validate_org_fixture(), 0)
        config = load_merged_cluster_config_v2(self.root / "clusters", "default/default")
        required = required_playbook_repo_names(config.playbooks, config.phases)
        self.assertIn("rare-stack", required)
        self.assertEqual(len(required), 5)

        derived = resolved_playbook_repos_from_config(config.playbooks)
        resolved = build_resolved_playbooks_repos(config.playbooks, required_repos=required)
        self.assertIn("rare-stack", resolved.specs)

    def test_phases_reference_unknown_repo_fails(self) -> None:
        from clusterctl.playbooks_config import PhasesConfig, PlaybooksConfig

        with self.assertRaises(ClusterctlError) as ctx:
            required_playbook_repo_names(
                PlaybooksConfig(repos={}),
                PhasesConfig(phases=("missing-repo/entry",)),
            )
        self.assertIn("missing-repo", str(ctx.exception))

    def test_validate_defaults_incomplete_when_phase_repo_missing(self) -> None:
        partial_path = self.root / "clusters" / "default" / "default" / "cluster.yaml"
        partial_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "playbooks": {
                        "atlas-node-foundation": {
                            "source": "git",
                            "url": "git@example.com/init.git",
                            "ref": "main",
                            "entries": {
                                "init": {
                                    "file": "playbooks/init_nodes.yaml",
                                    "invocations": [{"tags": "all"}],
                                }
                            },
                        }
                    },
                    "phases": [
                        "atlas-node-foundation/init",
                        "atlas-compute-provision/provision",
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ClusterctlError) as ctx:
            validate_org_baseline_playbooks(self.root)
        self.assertIn("atlas-compute-provision", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
