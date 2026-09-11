"""Tests for playbooks_resolve effective config."""

from __future__ import annotations

import os
import unittest

from clusterctl.playbooks_config import PlaybookRepoSpec, PlaybooksConfig
from clusterctl.playbooks_sync import apply_playbooks_env_overrides


class PlaybooksResolveTest(unittest.TestCase):
    def test_playbooks_env_local_override(self) -> None:
        key_path = "PLAYBOOKS_ATLAS_NODE_FOUNDATION_PATH"
        key_source = "PLAYBOOKS_ATLAS_NODE_FOUNDATION_SOURCE"
        old_path = os.environ.get(key_path)
        old_source = os.environ.get(key_source)
        os.environ[key_path] = "atlas-node-foundation"
        os.environ[key_source] = "local"
        try:
            playbooks = PlaybooksConfig(
                repos={
                    "atlas-node-foundation": PlaybookRepoSpec(
                        name="atlas-node-foundation",
                        source="git",
                        url="git@example.com/init.git",
                        ref="main",
                    )
                }
            )
            merged = apply_playbooks_env_overrides(playbooks)
            spec = merged.repos["atlas-node-foundation"]
            self.assertEqual(spec.source, "local")
            self.assertEqual(spec.path, "atlas-node-foundation")
        finally:
            if old_path is None:
                os.environ.pop(key_path, None)
            else:
                os.environ[key_path] = old_path
            if old_source is None:
                os.environ.pop(key_source, None)
            else:
                os.environ[key_source] = old_source


if __name__ == "__main__":
    unittest.main()
