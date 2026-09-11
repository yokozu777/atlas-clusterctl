"""Tests for clusterctl.playbooks_sync (PR-2)."""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.exceptions import ClusterctlError
from clusterctl.playbooks_config import (
    PhasesConfig,
    PlaybookRepoSpec,
    PlaybooksConfig,
)
from clusterctl.playbooks_sync import (
    ensure_playbooks_synced,
    repo_names_for_all_phases,
    repo_names_for_phase_alias,
    sync_playbook_repo_spec,
    sync_playbooks,
)


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _init_bare_remote_with_branch(tmp: Path, *, branch: str = "main") -> Path:
    bare = tmp / "remote.git"
    work = tmp / "work"
    _run(["git", "init", "--bare", str(bare)])
    _run(["git", "init", "-b", branch, str(work)])
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "test"], cwd=work)
    (work / "roles").mkdir()
    (work / "roles" / "dummy").mkdir()
    (work / "roles" / "dummy" / "tasks").mkdir(parents=True)
    (work / "roles" / "dummy" / "tasks" / "main.yaml").write_text("---\n", encoding="utf-8")
    _run(["git", "add", "roles"], cwd=work)
    _run(["git", "commit", "-m", "init"], cwd=work)
    _run(["git", "remote", "add", "origin", str(bare)], cwd=work)
    _run(["git", "push", "-u", "origin", branch], cwd=work)
    return bare


def _platform_remote(tmp: Path) -> Path:
    bare = tmp / "platform-remote.git"
    work = tmp / "platform-work"
    _run(["git", "init", "--bare", str(bare)])
    _run(["git", "init", "-b", "main", str(work)])
    _run(["git", "config", "user.email", "test@example.com"], cwd=work)
    _run(["git", "config", "user.name", "test"], cwd=work)
    (work / "00_controller_tooling").mkdir()
    (work / "00_controller_tooling" / "README").write_text("ok\n", encoding="utf-8")
    _run(["git", "add", "."], cwd=work)
    _run(["git", "commit", "-m", "init"], cwd=work)
    _run(["git", "remote", "add", "origin", str(bare)], cwd=work)
    _run(["git", "push", "-u", "origin", "main"], cwd=work)
    return bare


def _sample_playbooks(
    init_remote: Path,
    platform_remote: Path,
) -> PlaybooksConfig:
    return PlaybooksConfig(
        repos={
            "atlas-node-foundation": PlaybookRepoSpec(
                name="atlas-node-foundation",
                source="git",
                url=str(init_remote),
                ref="main",
                layout="roles/",
                sync="always",
            ),
            "atlas-infra-edge": PlaybookRepoSpec(
                name="atlas-infra-edge",
                source="git",
                url=str(init_remote),
                ref="main",
                layout="roles/",
                sync="if_missing",
            ),
            "atlas-compute-provision": PlaybookRepoSpec(
                name="atlas-compute-provision",
                source="git",
                url=str(init_remote),
                ref="main",
                layout="roles/",
                sync="never",
            ),
            "atlas-k8s-core": PlaybookRepoSpec(
                name="atlas-k8s-core",
                source="git",
                url=str(platform_remote),
                ref="main",
                layout="",
                sync="always",
            ),
        }
    )


class PlaybooksSyncTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "GIT_SSH_COMMAND")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved_env = {key: os.environ.get(key) for key in self._ISOLATED_ENV_KEYS}
        self._saved_playbooks = {k: v for k, v in os.environ.items() if k.startswith("PLAYBOOKS_")}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        for key in self._saved_playbooks:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self.git_root = self.root / "git-fixtures"
        self.git_root.mkdir()
        self.init_remote = _init_bare_remote_with_branch(self.git_root)
        self.platform_remote = _platform_remote(self.git_root)
        self.workspace = self.root / "workspace" / "k8s.example.com"
        self.playbooks = _sample_playbooks(self.init_remote, self.platform_remote)
        self.phases = PhasesConfig(
            phases=(
                "atlas-compute-provision/templates",
                "atlas-compute-provision/provision",
                "atlas-node-foundation/init-infra",
                "atlas-infra-edge/infra",
                "atlas-node-foundation/init",
                "atlas-k8s-core/cluster",
            ),
            phase_aliases={"provision": "atlas-compute-provision/provision"},
        )

    def tearDown(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for key in list(os.environ):
            if key.startswith("PLAYBOOKS_") and key not in self._saved_playbooks:
                os.environ.pop(key, None)
        for key, value in self._saved_playbooks.items():
            os.environ[key] = value
        self._tmpdir.cleanup()

    def test_clone_git_repo_with_roles_layout(self) -> None:
        spec = self.playbooks.repos["atlas-node-foundation"]
        result = sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(result.action, "cloned")
        roles_dir = self.workspace / "repos" / "atlas-node-foundation" / "roles" / "dummy"
        self.assertTrue(roles_dir.is_dir())

    def test_if_missing_skips_second_sync(self) -> None:
        spec = self.playbooks.repos["atlas-infra-edge"]
        first = sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(first.action, "cloned")
        second = sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(second.action, "skipped")

    def test_always_updates_existing_clone(self) -> None:
        spec = self.playbooks.repos["atlas-node-foundation"]
        sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        updated = sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(updated.action, "updated")

    def test_never_does_not_clone(self) -> None:
        spec = self.playbooks.repos["atlas-compute-provision"]
        result = sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(result.action, "never")
        self.assertFalse((self.workspace / "repos" / "atlas-compute-provision").exists())

    def test_platform_clone_at_repo_root_layout(self) -> None:
        spec = self.playbooks.repos["atlas-k8s-core"]
        result = sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(result.action, "cloned")
        tooling = self.workspace / "repos" / "atlas-k8s-core" / "00_controller_tooling"
        self.assertTrue(tooling.is_dir())

    def test_sync_only_phase_repos(self) -> None:
        names = repo_names_for_phase_alias("provision", phases=self.phases)
        self.assertEqual(names, ("atlas-compute-provision",))
        results = sync_playbooks(
            self.playbooks,
            workspace_root=self.workspace,
            repo_root_path=self.root,
            repo_names=names,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "atlas-compute-provision")
        self.assertEqual(results[0].action, "never")

    def test_sync_all_phase_repos(self) -> None:
        names = repo_names_for_all_phases(self.phases)
        self.assertEqual(
            names,
            ("atlas-compute-provision", "atlas-node-foundation", "atlas-infra-edge", "atlas-k8s-core"),
        )
        results = sync_playbooks(
            self.playbooks,
            workspace_root=self.workspace,
            repo_root_path=self.root,
            repo_names=names,
        )
        self.assertEqual(len(results), 4)

    def test_dry_run_reports_planned_action(self) -> None:
        spec = self.playbooks.repos["atlas-node-foundation"]
        result = sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
            dry_run=True,
        )
        self.assertTrue(result.action.startswith("dry-run-"))
        self.assertFalse((self.workspace / "repos" / "atlas-node-foundation").exists())

    def test_local_repo_requires_existing_layout(self) -> None:
        local_root = self.root / "sibling-repo"
        (local_root / "roles" / "demo" / "tasks").mkdir(parents=True)
        (local_root / "roles" / "demo" / "tasks" / "main.yaml").write_text("---\n", encoding="utf-8")
        spec = PlaybookRepoSpec(
            name="custom-stack",
            source="local",
            path="sibling-repo",
            path_relative_to="repo_root",
            layout="roles/",
        )
        result = sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(result.action, "local")
        self.assertEqual(result.path, local_root.resolve())

    def test_local_missing_raises(self) -> None:
        spec = PlaybookRepoSpec(
            name="missing-local",
            source="local",
            path="does-not-exist",
            path_relative_to="repo_root",
            layout="roles/",
        )
        with self.assertRaises(ClusterctlError):
            sync_playbook_repo_spec(
                spec,
                workspace_root=self.workspace,
                repo_root_path=self.root,
            )

    def test_env_ref_override(self) -> None:
        os.environ["PLAYBOOKS_ATLAS_NODE_FOUNDATION_REF"] = "main"
        spec = self.playbooks.repos["atlas-node-foundation"]
        result = sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(result.action, "cloned")

    def test_ensure_playbooks_synced_noop_when_disabled(self) -> None:
        results = ensure_playbooks_synced(
            playbooks_enabled=False,
            playbooks=self.playbooks,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )
        self.assertEqual(results, [])

    def test_log_streams_accepted(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        spec = self.playbooks.repos["atlas-node-foundation"]
        sync_playbook_repo_spec(
            spec,
            workspace_root=self.workspace,
            repo_root_path=self.root,
            log_streams=(stdout, stderr),
        )
        self.assertTrue((self.workspace / "repos" / "atlas-node-foundation").is_dir())

    def test_arbitrary_repo_name_not_whitelisted(self) -> None:
        bare = _init_bare_remote_with_branch(self.git_root / "extra")
        playbooks = PlaybooksConfig(
            repos={
                "rare-stack": PlaybookRepoSpec(
                    name="rare-stack",
                    source="git",
                    url=str(bare),
                    ref="main",
                    layout="roles/",
                )
            }
        )
        result = sync_playbooks(
            playbooks,
            workspace_root=self.workspace,
            repo_root_path=self.root,
        )[0]
        self.assertEqual(result.action, "cloned")
        self.assertTrue((self.workspace / "repos" / "rare-stack" / "roles").is_dir())


class PlaybooksSyncIntegrationTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self.git_root = self.root / "git-fixtures"
        self.git_root.mkdir()
        self.init_remote = _init_bare_remote_with_branch(self.git_root)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_v2_cluster(self) -> None:
        cluster = self.root / "clusters" / "lab" / "test"
        cluster.mkdir(parents=True)
        config = {
            "schema_version": 2,
            "id": "lab/test",
            "inventory": "hosts",
            "playbooks": {
                "atlas-node-foundation": {
                    "source": "git",
                    "url": str(self.init_remote),
                    "ref": "main",
                    "layout": "roles/",
                    "sync": "always",
                    "entries": {
                        "init": {
                            "file": "playbooks/init_nodes.yaml",
                            "invocations": [{"tags": "all"}],
                        }
                    },
                }
            },
            "phases": ["atlas-node-foundation/init"],
        }
        (cluster / "cluster.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
        (cluster / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        gv = cluster / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/test",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                }
            ),
            encoding="utf-8",
        )

    def test_context_playbooks_sync_via_cli_path(self) -> None:
        from clusterctl.context import ClusterContext
        from clusterctl.playbooks_cmd import cmd_playbooks_sync

        self._seed_v2_cluster()
        ctx = ClusterContext.load(cluster_id="lab/test")
        code = cmd_playbooks_sync(ctx, dry_run=True)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
