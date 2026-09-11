"""Tests for PR-G3: pipeline/stages derived from org baseline (no STAGE_* constants)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.pipeline import load_pipeline
from clusterctl.pipeline_fixture import migration_table, seed_org_baseline_fixture
from clusterctl.playbooks_config import stage_name_for_phase_ref


class PipelineG3Test(unittest.TestCase):
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

    def test_pipeline_playbooks_match_org_baseline_entries(self) -> None:
        from clusterctl.pipeline_fixture import load_org_baseline_cluster_config
        from clusterctl.playbooks_config import parse_phase_ref

        config = load_org_baseline_cluster_config(self.root)
        assert config.playbooks is not None
        stages = load_pipeline(self.root)
        self.assertEqual(len(stages), 4)
        for stage in stages:
            repo_name, entry_id = parse_phase_ref(stage.phase_ref)
            entry = config.playbooks.repos[repo_name].entries[entry_id]
            self.assertEqual(stage.playbook, entry.file)

    def test_migration_table_matches_pipeline(self) -> None:
        stages = load_pipeline(self.root)
        rows = migration_table(self.root)
        self.assertEqual(len(rows), len(stages))
        by_stage = {row["legacy_stage"]: row for row in rows}
        for stage in stages:
            row = by_stage[stage.name]
            self.assertEqual(row["v2_phase_ref"], stage.phase_ref)
            self.assertEqual(row["v2_playbook_file"], stage.playbook)
            self.assertEqual(row["legacy_playbook"], stage.playbook)

    def test_fifth_phase_uses_entry_id_when_no_alias(self) -> None:
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
        path.write_text(yaml.safe_dump(data), encoding="utf-8")

        stages = load_pipeline(self.root)
        rare = next(s for s in stages if s.phase_ref == "rare-stack/install")
        self.assertEqual(rare.name, "install")
        self.assertEqual(rare.playbook, "playbooks/install.yaml")

    def test_custom_alias_becomes_stage_name(self) -> None:
        path = self.root / "clusters" / "default" / "default" / "cluster.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        phases = []
        for item in data["phases"]:
            ref = (
                next(iter(item.values()))
                if isinstance(item, dict)
                else str(item)
            )
            if ref == "atlas-compute-provision/provision":
                phases.append({"build": ref})
            else:
                phases.append(item)
        data["phases"] = phases
        path.write_text(yaml.safe_dump(data), encoding="utf-8")

        stages = load_pipeline(self.root)
        provision = next(
            s for s in stages if s.phase_ref == "atlas-compute-provision/provision"
        )
        self.assertEqual(provision.name, "build")

    def test_stage_name_for_phase_ref_helper(self) -> None:
        aliases = {"provision": "atlas-compute-provision/provision"}
        self.assertEqual(
            stage_name_for_phase_ref("atlas-compute-provision/provision", aliases),
            "provision",
        )
        self.assertEqual(
            stage_name_for_phase_ref("rare-stack/install", aliases),
            "install",
        )


if __name__ == "__main__":
    unittest.main()
