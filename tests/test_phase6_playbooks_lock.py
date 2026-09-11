"""Phase 6: playbooks.lock pinned SHAs after sync."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from clusterctl.playbooks_config import PlaybookRepoSpec, PlaybooksConfig
from clusterctl.playbooks_lock import (
    PLAYBOOKS_LOCK_SCHEMA_VERSION,
    PlaybookLockEntry,
    PlaybooksLock,
    playbooks_lock_path,
    read_playbooks_lock,
    update_playbooks_lock,
    validate_playbooks_lock,
    write_playbooks_lock,
)
from clusterctl.playbooks_sync import PlaybookSyncResult
from clusterctl.pipeline_fixture import seed_org_baseline_fixture


class PlaybooksLockTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.workspace = self.root / "workspace" / "k8s.example.com"
        self.workspace.mkdir(parents=True)
        seed_org_baseline_fixture(self.root)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _git_spec(self) -> PlaybookRepoSpec:
        return PlaybookRepoSpec(
            name="atlas-node-foundation",
            source="git",
            url="git@example.com/atlas-node-foundation.git",
            ref="main",
            layout="roles/",
        )

    def test_write_and_read_roundtrip(self) -> None:
        lock = PlaybooksLock(
            schema_version=PLAYBOOKS_LOCK_SCHEMA_VERSION,
            cluster_id="lab/test",
            workspace_id="k8s.example.com",
            updated_at="2026-07-09T12:00:00+00:00",
            repos={
                "atlas-node-foundation": PlaybookLockEntry(
                    source="git",
                    url="git@example.com/atlas-node-foundation.git",
                    requested_ref="main",
                    resolved_sha="abc123def456",
                    materialized_path=str(self.workspace / "repos" / "atlas-node-foundation"),
                    sync_action="cloned",
                )
            },
        )
        path = write_playbooks_lock(self.workspace, lock)
        self.assertEqual(path, playbooks_lock_path(self.workspace))
        loaded = read_playbooks_lock(self.workspace)
        assert loaded is not None
        self.assertEqual(loaded.cluster_id, "lab/test")
        self.assertEqual(loaded.repos["atlas-node-foundation"].resolved_sha, "abc123def456")

    def test_update_playbooks_lock_merges_repos(self) -> None:
        playbooks = PlaybooksConfig(
            repos={
                "atlas-node-foundation": self._git_spec(),
                "atlas-k8s-core": PlaybookRepoSpec(
                    name="atlas-k8s-core",
                    source="git",
                    url="git@example.com/atlas-k8s-core.git",
                    ref="master",
                    layout="",
                ),
            }
        )
        repo_dest = self.workspace / "repos" / "atlas-node-foundation"
        repo_dest.mkdir(parents=True)
        (repo_dest / ".git").mkdir()
        (repo_dest / "roles").mkdir()

        with mock.patch("clusterctl.playbooks_lock.git_rev_parse", return_value="deadbeef" * 5):
            update_playbooks_lock(
                cluster_id="lab/test",
                workspace_id="k8s.example.com",
                workspace_root=self.workspace,
                playbooks=playbooks,
                results=[
                    PlaybookSyncResult(
                        name="atlas-node-foundation",
                        action="cloned",
                        path=repo_dest,
                        ref="main",
                    )
                ],
                repo_root_path=self.root,
                repo_names=("atlas-node-foundation",),
            )

        lock = read_playbooks_lock(self.workspace)
        assert lock is not None
        self.assertIn("atlas-node-foundation", lock.repos)
        self.assertEqual(lock.repos["atlas-node-foundation"].resolved_sha, "deadbeef" * 5)

    def test_validate_missing_lock_warns_by_default(self) -> None:
        playbooks = PlaybooksConfig(repos={"atlas-node-foundation": self._git_spec()})
        issues = validate_playbooks_lock(
            cluster_id="lab/test",
            workspace_id="k8s.example.com",
            playbooks=playbooks,
            workspace_root=self.workspace,
            repo_root_path=self.root,
            phase_repo_names={"atlas-node-foundation"},
            strict=False,
        )
        codes = [code for _sev, code, _msg, _hint in issues]
        self.assertIn("playbooks_lock_missing", codes)

    def test_validate_missing_lock_errors_in_strict(self) -> None:
        playbooks = PlaybooksConfig(repos={"atlas-node-foundation": self._git_spec()})
        issues = validate_playbooks_lock(
            cluster_id="lab/test",
            workspace_id="k8s.example.com",
            playbooks=playbooks,
            workspace_root=self.workspace,
            repo_root_path=self.root,
            phase_repo_names={"atlas-node-foundation"},
            strict=True,
        )
        self.assertTrue(any(sev == "error" for sev, _c, _m, _h in issues))

    def test_validate_lock_drift_detected(self) -> None:
        repo_dest = self.workspace / "repos" / "atlas-node-foundation"
        repo_dest.mkdir(parents=True)
        (repo_dest / ".git").mkdir()
        lock = PlaybooksLock(
            schema_version=PLAYBOOKS_LOCK_SCHEMA_VERSION,
            cluster_id="lab/test",
            workspace_id="k8s.example.com",
            updated_at="2026-07-09T12:00:00+00:00",
            repos={
                "atlas-node-foundation": PlaybookLockEntry(
                    source="git",
                    requested_ref="main",
                    resolved_sha="a" * 40,
                )
            },
        )
        write_playbooks_lock(self.workspace, lock)

        with mock.patch(
            "clusterctl.playbooks_lock.current_git_sha_for_spec",
            return_value="b" * 40,
        ):
            playbooks = PlaybooksConfig(repos={"atlas-node-foundation": self._git_spec()})
            issues = validate_playbooks_lock(
                cluster_id="lab/test",
                workspace_id="k8s.example.com",
                playbooks=playbooks,
                workspace_root=self.workspace,
                repo_root_path=self.root,
                phase_repo_names={"atlas-node-foundation"},
                strict=True,
            )
        self.assertTrue(any("playbooks_lock_drift" in code for _s, code, _m, _h in issues))


if __name__ == "__main__":
    unittest.main()
