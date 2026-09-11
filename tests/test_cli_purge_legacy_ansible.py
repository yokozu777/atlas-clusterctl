"""CLI / ansible_env auto-purge of legacy repo-root .ansible."""

from __future__ import annotations

import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clusterctl.exceptions import ClusterctlError
from clusterctl.workspace_paths import (
    purge_legacy_repo_root_ansible,
    report_purged_legacy_repo_root_ansible,
)


class PurgeLegacyApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_purge_raises_clusterctl_error_on_permission(self) -> None:
        (self.root / ".ansible" / "tmp").mkdir(parents=True)
        with mock.patch(
            "clusterctl.workspace_paths.shutil.rmtree",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(ClusterctlError) as ctx:
                purge_legacy_repo_root_ansible(self.root)
        self.assertIn("cannot remove legacy repo-root .ansible", str(ctx.exception))
        self.assertIn("denied", str(ctx.exception))

    def test_report_prints_exact_path_names(self) -> None:
        (self.root / ".ansible" / "tmp").mkdir(parents=True)
        buf = io.StringIO()
        removed = report_purged_legacy_repo_root_ansible(self.root, stream=buf)
        self.assertEqual([p.name for p in removed], [".ansible"])
        text = buf.getvalue()
        match = re.search(r"removed legacy repo-root ([^(\n]+)", text)
        self.assertIsNotNone(match)
        assert match is not None
        names = [part.strip() for part in match.group(1).split(",") if part.strip()]
        self.assertEqual(names, [".ansible"])


class EnsureLegacyClearedTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_ensure_clears_nonempty_legacy_dir(self) -> None:
        from clusterctl.ansible_env import _ensure_legacy_repo_root_ansible_cleared

        ansible = self.root / ".ansible"
        (ansible / "tmp").mkdir(parents=True)
        buf = io.StringIO()
        with mock.patch(
            "clusterctl.ansible_env.report_purged_legacy_repo_root_ansible",
            side_effect=lambda root, stream=None: report_purged_legacy_repo_root_ansible(
                root, stream=buf if stream is None else stream
            ),
        ):
            _ensure_legacy_repo_root_ansible_cleared(self.root)
        self.assertFalse(ansible.exists())
        self.assertIn("removed legacy repo-root .ansible", buf.getvalue())

    def test_build_workspace_env_calls_ensure(self) -> None:
        from clusterctl import ansible_env

        ctx = mock.Mock()
        ctx.repo_root = self.root
        ctx.workspace_root = self.root / "workspace" / "lab"
        ctx.workspace_id = "lab"
        ctx.controller_temp_location.return_value = "workspace"
        ctx.ansible_env.return_value = {
            "ANSIBLE_CACHE_PLUGIN_CONNECTION": str(ctx.workspace_root / ".ansible_facts_cache"),
            "ANSIBLE_LOCAL_TEMP": str(ctx.workspace_root / ".ansible" / "tmp"),
            "ANSIBLE_COLLECTIONS_PATHS": str(ctx.workspace_root / ".ansible" / "collections"),
            "TMPDIR": str(ctx.workspace_root / ".ansible" / "tmp"),
            "ANSIBLE_FORCE_COLOR": "true",
        }
        ensure = mock.Mock()
        with (
            mock.patch.object(ansible_env.ClusterContext, "load", return_value=ctx),
            mock.patch.object(
                ansible_env, "_ensure_legacy_repo_root_ansible_cleared", ensure
            ),
            mock.patch.object(ansible_env, "validate_workspace_ansible_env"),
        ):
            env = ansible_env.build_workspace_env()
        ensure.assert_called_once_with(self.root)
        self.assertEqual(env["ANSIBLE_FORCE_COLOR"], "true")


class CliPurgeLegacyAnsibleTest(unittest.TestCase):
    _ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "ATLAS_CLUSTERS_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        (self.root / "clusters").mkdir()
        self._saved = {key: os.environ.get(key) for key in self._ENV_KEYS}
        for key in self._ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        os.environ["ATLAS_CLUSTERS_ROOT"] = str(self.root / "clusters")

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_main_purges_legacy_ansible(self) -> None:
        from clusterctl.__main__ import main

        ansible = self.root / ".ansible"
        (ansible / "tmp").mkdir(parents=True)
        (ansible / "tmp" / "x").write_text("x", encoding="utf-8")
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            rc = main(["cluster", "list"])
        self.assertEqual(rc, 0)
        self.assertFalse(ansible.exists())
        self.assertIn("removed legacy repo-root .ansible", stderr.getvalue())

    def test_ansible_env_main_purges_legacy_ansible(self) -> None:
        from clusterctl.ansible_env import main as ansible_env_main

        ansible = self.root / ".ansible"
        (ansible / "tmp").mkdir(parents=True)
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            # May fail later without an active cluster; purge must still run first.
            ansible_env_main(["export-workspace"])
        self.assertFalse(ansible.exists())
        self.assertIn("removed legacy repo-root .ansible", stderr.getvalue())

    def test_ansible_env_purge_failure_uses_cluster_prefix(self) -> None:
        from clusterctl.ansible_env import main as ansible_env_main

        (self.root / ".ansible" / "tmp").mkdir(parents=True)
        stderr = io.StringIO()
        with (
            mock.patch(
                "clusterctl.ansible_env.report_purged_legacy_repo_root_ansible",
                side_effect=ClusterctlError("cannot remove legacy repo-root .ansible"),
            ),
            mock.patch("sys.stderr", stderr),
        ):
            rc = ansible_env_main(["export-workspace"])
        self.assertEqual(rc, 1)
        self.assertTrue(stderr.getvalue().startswith("cluster:"))


if __name__ == "__main__":
    unittest.main()
