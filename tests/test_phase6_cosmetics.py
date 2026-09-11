"""Phase 6: cosmetics — PHASE_BY_ALIAS, neutral help, playbook terminology."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from clusterctl.docker_validate import check_docker_playbooks_host
from clusterctl.pipeline import load_pipeline, reset_pipeline_cache_for_tests
from clusterctl.pipeline_fixture import seed_org_baseline_fixture
from clusterctl.playbooks_config import parse_phase_ref


class Phase6CosmeticsTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT",)

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        reset_pipeline_cache_for_tests()
        seed_org_baseline_fixture(self.root)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_phase_by_alias_indexes_org_baseline(self) -> None:
        from clusterctl.pipeline import PHASE_BY_ALIAS
        import clusterctl.stages as stages_module

        stages = load_pipeline(self.root)
        self.assertGreaterEqual(len(PHASE_BY_ALIAS), 4)
        self.assertIs(stages_module.PHASE_BY_ALIAS, PHASE_BY_ALIAS)
        for stage in stages:
            indexed = PHASE_BY_ALIAS[stage.name]
            self.assertEqual(indexed.phase_ref, stage.phase_ref)
            self.assertEqual(indexed.playbook, stage.playbook)

    def test_docker_validate_playbooks_host_check_exists(self) -> None:
        self.assertTrue(callable(check_docker_playbooks_host))

    def test_cli_help_uses_neutral_phase_ref_examples(self) -> None:
        from clusterctl.__main__ import _build_parser

        parser = _build_parser()
        playbooks_sync = next(
            action
            for action in parser._actions
            if getattr(action, "choices", None)
            and "playbooks" in action.choices
        )
        playbooks_parser = playbooks_sync.choices["playbooks"]
        sync_parser = next(
            sub
            for sub in playbooks_parser._actions
            if getattr(sub, "choices", None) and "sync" in sub.choices
        ).choices["sync"]
        phase_ref_action = next(
            a for a in sync_parser._actions if a.dest == "phase_ref"
        )
        phase_action = next(a for a in sync_parser._actions if a.dest == "phase")
        self.assertIn("my-stack/install", phase_ref_action.help or "")
        self.assertIn("my-stack/install", phase_action.help or "")
        self.assertNotIn("atlas-compute-provision/provision", phase_ref_action.help or "")

    def test_invalid_phase_ref_message_is_neutral(self) -> None:
        from clusterctl.exceptions import ClusterctlError

        with self.assertRaises(ClusterctlError) as ctx:
            parse_phase_ref("bad")
        self.assertIn("my-stack/install", str(ctx.exception))
        self.assertNotIn("atlas-compute-provision", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
