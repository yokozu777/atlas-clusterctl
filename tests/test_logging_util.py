"""Tests for clusterctl.logging_util."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from clusterctl.logging_util import (
    ENV_RUN_LOG_DIR,
    RunLogSession,
    run_log_session,
    run_subprocess_logged,
)


class LoggingUtilTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        os.environ.pop(ENV_RUN_LOG_DIR, None)

    def tearDown(self) -> None:
        os.environ.pop(ENV_RUN_LOG_DIR, None)
        self._tmpdir.cleanup()

    def test_run_log_session_creates_timestamped_dir(self) -> None:
        session = RunLogSession.create(
            self.root,
            command="run",
            header="cluster run profile=full",
            metadata={"cluster_id": "lab"},
        )
        try:
            self.assertTrue(session.root.is_dir())
            self.assertTrue(session.main_log.is_file())
            self.assertTrue((self.root / "latest").is_symlink())
            self.assertTrue((self.root / "run_cluster.log").is_symlink())
            self.assertTrue((session.root / "meta.json").is_file())
            session.write_line("hello", stage="templates")
            self.assertIn("hello", session.main_log.read_text(encoding="utf-8"))
            self.assertIn(
                "hello",
                session.stage_log_path("templates").read_text(encoding="utf-8"),
            )
        finally:
            session.close()

    def test_run_subprocess_logged_tees_output(self) -> None:
        log_path = self.root / "subprocess.log"
        with log_path.open("w", encoding="utf-8") as handle:
            code = run_subprocess_logged(
                ["bash", "-c", "echo captured-line"],
                cwd=self.root,
                env={**dict(**__import__("os").environ), "LC_ALL": "C"},
                log_streams=[handle],
                echo_command=False,
            )
        self.assertEqual(code, 0)
        self.assertIn("captured-line", log_path.read_text(encoding="utf-8"))

    def test_run_subprocess_logged_default_cwd(self) -> None:
        """Omitting cwd must inherit process cwd (not str(None) → 'None')."""
        log_path = self.root / "subprocess-no-cwd.log"
        with log_path.open("w", encoding="utf-8") as handle:
            code = run_subprocess_logged(
                ["bash", "-c", "echo ok-no-cwd"],
                env={**dict(**__import__("os").environ), "LC_ALL": "C"},
                log_streams=[handle],
                echo_command=False,
            )
        self.assertEqual(code, 0)
        self.assertIn("ok-no-cwd", log_path.read_text(encoding="utf-8"))

    def test_run_log_session_writes_result_ok(self) -> None:
        with run_log_session(
            self.root,
            command="run",
            header="cluster run",
            metadata={"cluster_id": "lab"},
        ) as session:
            session.set_exit_code(0)
            meta_path = session.root / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertTrue(meta["ok"])
        self.assertEqual(meta["exit_code"], 0)
        self.assertIn("finished_at", meta)
        self.assertEqual(meta["command"], "run")

    def test_run_log_session_writes_result_fail_on_exception(self) -> None:
        root: Path | None = None
        with self.assertRaises(RuntimeError):
            with run_log_session(
                self.root,
                command="run",
                header="cluster run",
                metadata={"cluster_id": "lab"},
            ) as session:
                root = session.root
                raise RuntimeError("boom")
        assert root is not None
        meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
        self.assertFalse(meta["ok"])
        self.assertEqual(meta["exit_code"], 1)
        self.assertIn("finished_at", meta)


if __name__ == "__main__":
    unittest.main()
