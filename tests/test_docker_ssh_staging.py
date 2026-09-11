"""Per-run Docker SSH staging (tempfile.mkdtemp) — Stage 2 gates."""

from __future__ import annotations

import concurrent.futures
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clusterctl.docker_executor import (
    CONTAINER_SSH_KEY,
    extra_args_detach_flag,
    extra_args_user_flag,
    prepare_container_ssh_key,
    reject_docker_detach_extra_args,
    reject_docker_user_extra_args,
    run_docker_container,
)
from clusterctl.exceptions import ClusterctlError


class RejectDockerDetachExtraArgsTest(unittest.TestCase):
    """-d/--detach must be rejected (per-run SSH staging needs sync docker run)."""

    def test_detects_short_long_and_combined(self) -> None:
        cases = (
            (("-d",), "-d"),
            (("--detach",), "--detach"),
            (("--detach=true",), "--detach=true"),
            (("-itd",), "-itd"),
            (("-td",), "-td"),
            (("--network=host", "-d"), "-d"),
            (("-dns",), None),
            (("--rm",), None),
            (("-i", "-t"), None),
            (("--dns", "8.8.8.8"), None),
            ((), None),
        )
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(extra_args_detach_flag(args), expected)

    def test_reject_raises_clusterctl_error(self) -> None:
        with self.assertRaises(ClusterctlError) as raised:
            reject_docker_detach_extra_args(("--cap-add=NET_ADMIN", "-d"))
        msg = str(raised.exception)
        self.assertTrue(msg.startswith("docker:"))
        self.assertIn("-d/--detach", msg)
        self.assertIn("got '-d'", msg)
        self.assertIn("per-run SSH staging", msg)

    def test_reject_noop_when_clean(self) -> None:
        reject_docker_detach_extra_args(("--network=host", "-e", "FOO=1"))


class RejectDockerUserExtraArgsTest(unittest.TestCase):
    """--user/-u must be rejected (clusterctl sets host uid:gid)."""

    def test_detects_user_flags(self) -> None:
        cases = (
            (("--user", "1000:1000"), "--user"),
            (("--user=1000:1000",), "--user=1000:1000"),
            (("-u", "1000:1000"), "-u"),
            (("-u=1000:1000",), "-u=1000:1000"),
            (("-u1000:1000",), "-u1000:1000"),
            (("-u1000",), "-u1000"),
            (("-uroot",), "-uroot"),
            (("-unobody",), "-unobody"),
            (("-itu",), "-itu"),
            (("--network=host", "--user", "0:0"), "--user"),
            (("-volume",), None),
            (("--userns=host",), None),
            (("--rm",), None),
            (("-i", "-t"), None),
            ((), None),
        )
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(extra_args_user_flag(args), expected)

    def test_reject_raises_clusterctl_error(self) -> None:
        with self.assertRaises(ClusterctlError) as raised:
            reject_docker_user_extra_args(("--cap-add=NET_ADMIN", "--user", "0:0"))
        msg = str(raised.exception)
        self.assertTrue(msg.startswith("docker:"))
        self.assertIn("--user/-u", msg)
        self.assertIn("got '--user'", msg)
        self.assertIn("host uid:gid", msg)

    def test_reject_noop_when_clean(self) -> None:
        reject_docker_user_extra_args(("--network=host", "-e", "FOO=1"))


class PrepareContainerSshKeyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        # Staging parent mimics workspace/<id>/.atlas-ssh (docker-shareable).
        self.staging = self.root / "workspace" / "ci" / "lab" / ".atlas-ssh"
        self.src = self.root / "source_id_rsa"
        self.src.write_bytes(b"unit-test-private-key\n")
        self.src.chmod(0o644)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _prepare(self, ssh_key: Path | None = None):
        return prepare_container_ssh_key(
            ssh_key if ssh_key is not None else self.src,
            staging_parent=self.staging,
        )

    def test_prepare_permissions_prefix_and_contents(self) -> None:
        prepared = self._prepare()
        try:
            self.assertTrue(prepared.key_path.is_file())
            self.assertEqual(prepared.key_path.name, "id_rsa")
            self.assertEqual(prepared.key_path.read_bytes(), b"unit-test-private-key\n")
            self.assertEqual(stat.S_IMODE(prepared.key_path.stat().st_mode), 0o600)
            self.assertTrue(prepared.staging_dir.is_dir())
            self.assertEqual(stat.S_IMODE(prepared.staging_dir.stat().st_mode), 0o700)
            self.assertTrue(prepared.staging_dir.name.startswith("atlas-ssh-"))
            # Under workspace/.atlas-ssh — not host /tmp, not controller .cache.
            self.assertEqual(prepared.staging_dir.parent.resolve(), self.staging.resolve())
            self.assertIn("/.atlas-ssh/", str(prepared.key_path.resolve()) + "/")
            self.assertNotIn("/.cache/", str(prepared.key_path.resolve()) + "/")
            self.assertNotIn("docker-identity", str(prepared.key_path))
        finally:
            prepared.cleanup()

    def test_prepare_unique_staging_dirs(self) -> None:
        a = self._prepare()
        b = self._prepare()
        try:
            self.assertNotEqual(a.staging_dir, b.staging_dir)
            self.assertNotEqual(a.key_path, b.key_path)
            self.assertTrue(a.staging_dir.is_dir())
            self.assertTrue(b.staging_dir.is_dir())
            # Different keys can be staged without overwrite.
            a.key_path.write_bytes(b"key-a\n")
            b.key_path.write_bytes(b"key-b\n")
            self.assertEqual(a.key_path.read_bytes(), b"key-a\n")
            self.assertEqual(b.key_path.read_bytes(), b"key-b\n")
        finally:
            a.cleanup()
            b.cleanup()

    def test_prepare_parallel_unique_dirs(self) -> None:
        prepared_list = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(self._prepare) for _ in range(16)]
                prepared_list = [f.result() for f in futures]
            dirs = {p.staging_dir.resolve() for p in prepared_list}
            keys = {p.key_path.resolve() for p in prepared_list}
            self.assertEqual(len(dirs), 16)
            self.assertEqual(len(keys), 16)
        finally:
            for prepared in prepared_list:
                prepared.cleanup()

    def test_cleanup_removes_staging_dir(self) -> None:
        prepared = self._prepare()
        staging = prepared.staging_dir
        key = prepared.key_path
        self.assertTrue(staging.exists())
        prepared.cleanup()
        self.assertFalse(staging.exists())
        self.assertFalse(key.exists())
        # Idempotent.
        prepared.cleanup()

    def test_prepare_missing_source_raises_clusterctl_error(self) -> None:
        before = set(self.staging.iterdir()) if self.staging.is_dir() else set()
        missing = self.root / "missing_key"
        with self.assertRaises(ClusterctlError) as raised:
            self._prepare(missing)
        self.assertIn("SSH key not found", str(raised.exception))
        self.assertTrue(str(raised.exception).startswith("docker:"))
        after = set(self.staging.iterdir()) if self.staging.is_dir() else set()
        self.assertEqual(before, after)

    def test_prepare_unreadable_source_raises_clusterctl_error(self) -> None:
        before = set(self.staging.iterdir()) if self.staging.is_dir() else set()
        with mock.patch(
            "clusterctl.docker_executor.check_ssh_key",
            return_value=f"SSH key not readable: {self.src}",
        ):
            with self.assertRaises(ClusterctlError) as raised:
                self._prepare()
        self.assertIn("SSH key not readable", str(raised.exception))
        self.assertTrue(str(raised.exception).startswith("docker:"))
        after = set(self.staging.iterdir()) if self.staging.is_dir() else set()
        self.assertEqual(before, after)

    def test_prepare_stage_oserror_wraps_clusterctl_error(self) -> None:
        self.staging.mkdir(parents=True, exist_ok=True)
        before = {p.name for p in self.staging.iterdir()}
        with mock.patch(
            "pathlib.Path.write_bytes",
            side_effect=OSError(13, "Permission denied"),
        ):
            with self.assertRaises(ClusterctlError) as raised:
                self._prepare()
        self.assertIn("failed to stage SSH key", str(raised.exception))
        self.assertTrue(str(raised.exception).startswith("docker:"))
        self.assertEqual(before, {p.name for p in self.staging.iterdir()})

    def test_prepare_mkdtemp_oserror_wraps_clusterctl_error(self) -> None:
        self.staging.mkdir(parents=True, exist_ok=True)
        before = {p.name for p in self.staging.iterdir()}
        with mock.patch(
            "clusterctl.docker_executor.tempfile.mkdtemp",
            side_effect=OSError(28, "No space left on device"),
        ):
            with self.assertRaises(ClusterctlError) as raised:
                self._prepare()
        msg = str(raised.exception)
        self.assertTrue(msg.startswith("docker:"))
        self.assertIn("failed to stage SSH key", msg)
        self.assertIn("No space left", msg)
        self.assertNotIsInstance(raised.exception, OSError)
        self.assertEqual(before, {p.name for p in self.staging.iterdir()})


class RunDockerContainerSshCleanupTest(unittest.TestCase):
    """run_docker_container must always cleanup per-run SSH staging."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.ws = self.root / "workspace" / "ci" / "lab"
        self.staging = self.ws / ".atlas-ssh"
        self.src = self.root / "id_rsa"
        self.src.write_bytes(b"cleanup-key\n")
        self.src.chmod(0o600)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _ctx(self, **kwargs) -> mock.Mock:
        ctx = mock.Mock()
        ctx.ssh_key = self.src
        ctx.repo_root = self.root
        ctx.workspace_root = self.ws
        ctx.execution.docker = mock.Mock()
        ctx.execution.docker.extra_args = ()
        for key, value in kwargs.items():
            setattr(ctx, key, value)
        return ctx

    def _tracking_prepare(self, staging_dirs: list[Path]):
        real_prepare = prepare_container_ssh_key

        def _wrap(ssh_key: Path, *, staging_parent: Path):
            prepared = real_prepare(ssh_key, staging_parent=staging_parent)
            staging_dirs.append(prepared.staging_dir)
            return prepared

        return _wrap

    def _staging_names(self) -> set[str]:
        if not self.staging.is_dir():
            return set()
        return {p.name for p in self.staging.iterdir()}

    def test_run_docker_container_cleans_staging_on_success(self) -> None:
        staging_dirs: list[Path] = []
        ctx = self._ctx()

        with (
            mock.patch("clusterctl.docker_executor.preflight_docker"),
            mock.patch(
                "clusterctl.docker_executor.prepare_container_ssh_key",
                side_effect=self._tracking_prepare(staging_dirs),
            ),
            mock.patch(
                "clusterctl.docker_executor.build_docker_run_command",
                return_value=["true"],
            ),
            mock.patch(
                "clusterctl.docker_executor.resolve_docker_image_ref",
                return_value="img:tag",
            ),
            mock.patch(
                "clusterctl.docker_executor.subprocess.run",
                return_value=mock.Mock(returncode=0),
            ),
        ):
            rc = run_docker_container(ctx, ["plan"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(staging_dirs), 1)
        self.assertFalse(staging_dirs[0].exists())

    def test_run_docker_container_cleans_staging_when_build_fails(self) -> None:
        staging_dirs: list[Path] = []
        ctx = self._ctx()

        with (
            mock.patch("clusterctl.docker_executor.preflight_docker"),
            mock.patch(
                "clusterctl.docker_executor.prepare_container_ssh_key",
                side_effect=self._tracking_prepare(staging_dirs),
            ),
            mock.patch(
                "clusterctl.docker_executor.build_docker_run_command",
                side_effect=RuntimeError("boom"),
            ),
        ):
            with self.assertRaises(RuntimeError):
                run_docker_container(ctx, ["plan"])
        self.assertEqual(len(staging_dirs), 1)
        self.assertFalse(staging_dirs[0].exists())

    def test_run_docker_container_cleans_staging_when_docker_run_fails(self) -> None:
        staging_dirs: list[Path] = []
        ctx = self._ctx()

        with (
            mock.patch("clusterctl.docker_executor.preflight_docker"),
            mock.patch(
                "clusterctl.docker_executor.prepare_container_ssh_key",
                side_effect=self._tracking_prepare(staging_dirs),
            ),
            mock.patch(
                "clusterctl.docker_executor.build_docker_run_command",
                return_value=["false"],
            ),
            mock.patch(
                "clusterctl.docker_executor.resolve_docker_image_ref",
                return_value="img:tag",
            ),
            mock.patch(
                "clusterctl.docker_executor.subprocess.run",
                return_value=mock.Mock(returncode=42),
            ),
        ):
            rc = run_docker_container(ctx, ["apply"])
        self.assertEqual(rc, 42)
        self.assertEqual(len(staging_dirs), 1)
        self.assertFalse(staging_dirs[0].exists())

    def _cache_names(self) -> set[str]:
        if not self.cache.is_dir():
            return set()
        return {p.name for p in self.cache.iterdir()}

    def test_run_docker_container_skips_prepare_when_preflight_fails(self) -> None:
        ctx = self._ctx()
        before = self._staging_names()

        with (
            mock.patch(
                "clusterctl.docker_executor.preflight_docker",
                side_effect=ClusterctlError(
                    "docker execution requires docker CLI on PATH"
                ),
            ),
            mock.patch(
                "clusterctl.docker_executor.prepare_container_ssh_key"
            ) as prepare,
        ):
            with self.assertRaises(ClusterctlError) as raised:
                run_docker_container(ctx, ["plan"])
        self.assertIn("docker CLI", str(raised.exception))
        prepare.assert_not_called()
        self.assertEqual(before, self._staging_names())

    def test_run_docker_container_missing_key_raises_clusterctl_error(self) -> None:
        """Real preflight path: missing key → ClusterctlError, no staging."""
        missing = self.root / "no_such_key"
        ctx = self._ctx()
        ctx.ssh_key = missing
        before = self._staging_names()

        with (
            mock.patch(
                "clusterctl.docker_executor.docker_cli_available",
                return_value=True,
            ),
            mock.patch(
                "clusterctl.docker_executor._docker_local_playbook_mounts",
                return_value=[],
            ),
            mock.patch(
                "clusterctl.docker_executor.prepare_container_ssh_key"
            ) as prepare,
        ):
            with self.assertRaises(ClusterctlError) as raised:
                run_docker_container(ctx, ["plan"])
        msg = str(raised.exception)
        self.assertTrue(msg.startswith("docker:"))
        self.assertIn("SSH key not found", msg)
        prepare.assert_not_called()
        self.assertEqual(before, self._staging_names())

    def test_run_docker_container_rejects_detach_before_prepare(self) -> None:
        """Detach in extra_args → ClusterctlError in preflight; no staging."""
        ctx = self._ctx()
        ctx.execution.docker.extra_args = ("--network=host", "-d")
        before = self._staging_names()

        with (
            mock.patch(
                "clusterctl.docker_executor.docker_cli_available",
                return_value=True,
            ),
            mock.patch(
                "clusterctl.docker_executor.prepare_container_ssh_key"
            ) as prepare,
        ):
            with self.assertRaises(ClusterctlError) as raised:
                run_docker_container(ctx, ["plan"])
        msg = str(raised.exception)
        self.assertTrue(msg.startswith("docker:"))
        self.assertIn("-d/--detach", msg)
        self.assertIn("got '-d'", msg)
        prepare.assert_not_called()
        self.assertEqual(before, self._staging_names())

    def test_run_docker_container_rejects_long_detach_before_prepare(self) -> None:
        ctx = self._ctx()
        ctx.execution.docker.extra_args = ("--detach",)
        before = self._staging_names()

        with (
            mock.patch(
                "clusterctl.docker_executor.docker_cli_available",
                return_value=True,
            ),
            mock.patch(
                "clusterctl.docker_executor.prepare_container_ssh_key"
            ) as prepare,
        ):
            with self.assertRaises(ClusterctlError) as raised:
                run_docker_container(ctx, ["plan"])
        self.assertIn("--detach", str(raised.exception))
        prepare.assert_not_called()
        self.assertEqual(before, self._staging_names())

    def test_run_docker_container_rejects_user_before_prepare(self) -> None:
        """--user in extra_args → ClusterctlError in preflight; no staging."""
        ctx = self._ctx()
        ctx.execution.docker.extra_args = ("--network=host", "--user", "0:0")
        before = self._staging_names()

        with (
            mock.patch(
                "clusterctl.docker_executor.docker_cli_available",
                return_value=True,
            ),
            mock.patch(
                "clusterctl.docker_executor.prepare_container_ssh_key"
            ) as prepare,
        ):
            with self.assertRaises(ClusterctlError) as raised:
                run_docker_container(ctx, ["plan"])
        msg = str(raised.exception)
        self.assertTrue(msg.startswith("docker:"))
        self.assertIn("--user/-u", msg)
        self.assertIn("got '--user'", msg)
        prepare.assert_not_called()
        self.assertEqual(before, self._staging_names())
    def test_run_docker_smoke_missing_key_raises_clusterctl_error(self) -> None:
        from clusterctl.docker_validate import run_docker_smoke

        missing = self.root / "no_such_key"
        ctx = self._ctx()
        ctx.ssh_key = missing
        before = self._staging_names()

        with (
            mock.patch(
                "clusterctl.docker_executor.docker_cli_available",
                return_value=True,
            ),
            mock.patch(
                "clusterctl.docker_executor._docker_local_playbook_mounts",
                return_value=[],
            ),
            mock.patch(
                "clusterctl.docker_validate.prepare_container_ssh_key"
            ) as prepare,
        ):
            with self.assertRaises(ClusterctlError) as raised:
                run_docker_smoke(ctx, timeout_sec=5)
        msg = str(raised.exception)
        self.assertTrue(msg.startswith("docker:"))
        self.assertIn("SSH key not found", msg)
        prepare.assert_not_called()
        self.assertEqual(before, self._staging_names())

    def test_run_docker_smoke_rejects_detach_before_prepare(self) -> None:
        from clusterctl.docker_validate import run_docker_smoke

        ctx = self._ctx()
        ctx.execution.docker.extra_args = ("-itd",)
        before = self._staging_names()

        with (
            mock.patch(
                "clusterctl.docker_executor.docker_cli_available",
                return_value=True,
            ),
            mock.patch(
                "clusterctl.docker_validate.prepare_container_ssh_key"
            ) as prepare,
        ):
            with self.assertRaises(ClusterctlError) as raised:
                run_docker_smoke(ctx, timeout_sec=5)
        msg = str(raised.exception)
        self.assertTrue(msg.startswith("docker:"))
        self.assertIn("-d/--detach", msg)
        self.assertIn("got '-itd'", msg)
        prepare.assert_not_called()
        self.assertEqual(before, self._staging_names())

    def test_run_docker_smoke_cleans_staging(self) -> None:
        from clusterctl.docker_validate import run_docker_smoke

        staging_dirs: list[Path] = []
        ctx = self._ctx()

        with (
            mock.patch("clusterctl.docker_validate.preflight_docker"),
            mock.patch(
                "clusterctl.docker_validate.prepare_container_ssh_key",
                side_effect=self._tracking_prepare(staging_dirs),
            ),
            mock.patch(
                "clusterctl.docker_validate.build_docker_smoke_command",
                return_value=["true"],
            ),
            mock.patch(
                "clusterctl.docker_validate._run_subprocess",
                return_value=(True, "ok"),
            ),
        ):
            ok, msg = run_docker_smoke(ctx, timeout_sec=5)
        self.assertTrue(ok)
        self.assertEqual(msg, "ok")
        self.assertEqual(len(staging_dirs), 1)
        self.assertFalse(staging_dirs[0].exists())

    def test_run_docker_smoke_skips_prepare_when_preflight_fails(self) -> None:
        from clusterctl.docker_validate import run_docker_smoke

        ctx = self._ctx()
        before = self._staging_names()

        with (
            mock.patch(
                "clusterctl.docker_validate.preflight_docker",
                side_effect=ClusterctlError("docker: ssh key missing"),
            ),
            mock.patch(
                "clusterctl.docker_validate.prepare_container_ssh_key"
            ) as prepare,
        ):
            with self.assertRaises(ClusterctlError) as raised:
                run_docker_smoke(ctx, timeout_sec=5)
        self.assertIn("ssh key", str(raised.exception))
        prepare.assert_not_called()
        self.assertEqual(before, self._staging_names())

    def test_container_ssh_key_constant_unchanged(self) -> None:
        self.assertEqual(CONTAINER_SSH_KEY, "/tmp/atlas-ssh/id_rsa")


class SshStagingDocsContractTest(unittest.TestCase):
    """Docs: workspace/.atlas-ssh per-run, not /tmp, not controller .cache identity."""

    def test_execution_md_contract(self) -> None:
        text = (
            Path(__file__).resolve().parents[1] / "docs" / "execution.md"
        ).read_text(encoding="utf-8")
        self.assertIn('tempfile.mkdtemp(prefix="atlas-ssh-")', text)
        self.assertIn("workspace/<cluster_id>/.atlas-ssh/", text)
        self.assertIn("/tmp/atlas-ssh/id_rsa", text)
        self.assertIn("Docker Desktop", text)
        self.assertIn(".cache/docker-identity/", text)
        self.assertIn("no longer created", text)
        self.assertIn('rm -rf "$ATLAS_CLUSTER_ROOT/.cache/docker-identity"', text)
        self.assertIn("Parallel docker runs", text)
        self.assertIn("Keep `/.cache/` in `.gitignore`", text)
        self.assertIn("does **not** write SSH identity under controller `.cache/`", text)
        self.assertIn("preflight_docker", text)
        self.assertIn("-d/--detach", text)
        self.assertIn("not -d/--detach", text)
        self.assertNotIn("under host `/tmp/atlas-ssh-*`", text)
        self.assertNotIn("tempfile.gettempdir()", text)

    def test_gitlab_ci_md_contract(self) -> None:
        text = (
            Path(__file__).resolve().parents[1] / "docs" / "gitlab-ci.md"
        ).read_text(encoding="utf-8")
        self.assertIn('tempfile.mkdtemp(prefix="atlas-ssh-")', text)
        self.assertIn("workspace/<cluster_id>/.atlas-ssh/", text)
        self.assertIn("/tmp/atlas-ssh/id_rsa", text)
        self.assertIn(".cache/docker-identity", text)
        self.assertIn("no longer created", text)
        self.assertIn("rm -rf .cache/docker-identity", text)
        self.assertIn("Keep `/.cache/` in `.gitignore`", text)
        self.assertIn("after preflight", text)
        self.assertNotIn("tempfile.gettempdir()", text)

    def test_compute_provision_md_host_staging_contract(self) -> None:
        """Stack doc must match execution.md: workspace/.atlas-ssh + container path."""
        text = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "stacks"
            / "compute-provision.md"
        ).read_text(encoding="utf-8")
        self.assertIn('tempfile.mkdtemp(prefix="atlas-ssh-")', text)
        self.assertIn("workspace/<cluster_id>/.atlas-ssh/", text)
        self.assertIn("/tmp/atlas-ssh/id_rsa", text)
        self.assertIn(".cache/docker-identity", text)
        self.assertIn("execution.md", text)
        self.assertNotIn("tempfile.gettempdir()", text)

    def test_ownership_fix_paths_doc_mentions_workspace_staging(self) -> None:
        text = (
            Path(__file__).resolve().parents[1]
            / "clusterctl"
            / "docker_executor.py"
        ).read_text(encoding="utf-8")
        start = text.index("def _ownership_fix_paths")
        chunk = text[start : start + 900]
        self.assertIn(".atlas-ssh/atlas-ssh-", chunk)
        self.assertNotIn("gettempdir()", chunk)
        self.assertNotIn("/tmp/atlas-ssh-*", chunk)

    def test_gitignore_keeps_cache_without_identity(self) -> None:
        text = (
            Path(__file__).resolve().parents[1] / ".gitignore"
        ).read_text(encoding="utf-8")
        self.assertIn("/.cache/", text)
        self.assertIn("SSH identity is **not**", text)
        self.assertIn("workspace/<id>/.atlas-ssh/", text)


if __name__ == "__main__":
    unittest.main()
