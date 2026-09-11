"""Logging helpers for clusterctl pipeline runs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, TextIO

ENV_RUN_LOG_DIR = "CLUSTER_RUN_LOG_DIR"
_LATEST_LINK = "latest"
_RUN_CLUSTER_LINK = "run_cluster.log"
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


class Tee:
    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


def _run_log_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")


def _allocate_run_root(workspace_logs: Path) -> Path:
    base_stamp = _run_log_stamp()
    for suffix in ("",) + tuple(f"-{index:02d}" for index in range(1, 100)):
        candidate = workspace_logs / f"{base_stamp}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"unable to allocate run log directory under {workspace_logs}")


def _safe_stage_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("-", name.strip()).strip("-")
    return cleaned or "stage"


def _update_workspace_log_links(workspace_logs: Path, run_root: Path) -> None:
    workspace_logs.mkdir(parents=True, exist_ok=True)
    latest = workspace_logs / _LATEST_LINK
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(run_root.name)

    run_cluster = workspace_logs / _RUN_CLUSTER_LINK
    if run_cluster.is_symlink() or run_cluster.exists():
        run_cluster.unlink()
    run_cluster.symlink_to(f"{run_root.name}/run.log")


@dataclass
class RunLogSession:
    """One pipeline execution under ``workspace/<id>/logs/<timestamp>/``."""

    root: Path
    main_log: Path
    stages_dir: Path
    workspace_logs: Path
    _main_handle: TextIO | None = field(default=None, repr=False)
    _stage_handles: dict[str, TextIO] = field(default_factory=dict, repr=False)
    _exit_code: int | None = field(default=None, repr=False)

    @classmethod
    def create(
        cls,
        workspace_logs: Path,
        *,
        command: str,
        header: str,
        metadata: dict[str, object] | None = None,
    ) -> RunLogSession:
        env_dir = os.environ.get(ENV_RUN_LOG_DIR, "").strip()
        if env_dir:
            root = Path(env_dir).resolve()
            root.mkdir(parents=True, exist_ok=True)
            session = cls(
                root=root,
                main_log=root / "run.log",
                stages_dir=root / "stages",
                workspace_logs=workspace_logs.resolve(),
            )
            session.stages_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            session.write_line(f"=== {stamp} {header} (executor) ===")
            return session

        root = _allocate_run_root(workspace_logs.resolve())
        root.mkdir(parents=True, exist_ok=False)
        (root / "stages").mkdir(parents=True, exist_ok=True)

        session = cls(
            root=root,
            main_log=root / "run.log",
            stages_dir=root / "stages",
            workspace_logs=workspace_logs.resolve(),
        )
        _update_workspace_log_links(session.workspace_logs, session.root)
        os.environ[ENV_RUN_LOG_DIR] = str(session.root)

        meta = {
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "command": command,
            "header": header,
            **(metadata or {}),
        }
        (session.root / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        session.write_line(f"=== {meta['started_at']} {header} ===")
        return session

    def stage_log_path(self, stage_name: str) -> Path:
        return self.stages_dir / f"{_safe_stage_name(stage_name)}.log"

    def _main(self) -> TextIO:
        if self._main_handle is None:
            self.main_log.parent.mkdir(parents=True, exist_ok=True)
            self._main_handle = self.main_log.open("a", encoding="utf-8")
        return self._main_handle

    def _stage(self, stage_name: str) -> TextIO:
        handle = self._stage_handles.get(stage_name)
        if handle is None:
            path = self.stage_log_path(stage_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a", encoding="utf-8")
            self._stage_handles[stage_name] = handle
        return handle

    def write_line(self, text: str, *, stage: str | None = None) -> None:
        line = text if text.endswith("\n") else f"{text}\n"
        self._main().write(line)
        self._main().flush()
        if stage is not None:
            self._stage(stage).write(line)
            self._stage(stage).flush()
        sys.stdout.write(line)
        sys.stdout.flush()

    def log_streams(self, *, stage: str | None = None) -> list[TextIO]:
        streams: list[TextIO] = [self._main()]
        if stage is not None:
            streams.append(self._stage(stage))
        return streams

    def set_exit_code(self, exit_code: int) -> None:
        self._exit_code = int(exit_code)

    def write_result(self, *, exit_code: int, ok: bool) -> None:
        path = self.root / "meta.json"
        if not path.is_file():
            return
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(meta, dict):
            return
        meta["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        meta["exit_code"] = int(exit_code)
        meta["ok"] = bool(ok)
        path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def close(self) -> None:
        for handle in self._stage_handles.values():
            handle.close()
        self._stage_handles.clear()
        if self._main_handle is not None:
            self._main_handle.close()
            self._main_handle = None

    def summary_path(self) -> str:
        return str(self.root)


def run_subprocess_logged(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str],
    log_streams: list[TextIO] | None = None,
    echo_command: bool = True,
) -> int:
    """Run a subprocess and tee combined stdout/stderr to console and log file(s).

    When ``cwd`` is omitted, the child inherits the current working directory
    (same as ``subprocess.run`` / ``Popen`` default).
    """
    if echo_command:
        line = f"$ {subprocess.list2cmdline(cmd)}\n"
        sys.stdout.write(line)
        sys.stdout.flush()
        for stream in log_streams or []:
            stream.write(line)
            stream.flush()

    popen_kwargs: dict[str, object] = {
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if cwd is not None:
        popen_kwargs["cwd"] = str(cwd)

    process = subprocess.Popen(cmd, **popen_kwargs)  # type: ignore[arg-type]
    assert process.stdout is not None
    try:
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            for stream in log_streams or []:
                stream.write(line)
                stream.flush()
    finally:
        process.stdout.close()
    return int(process.wait())


@contextmanager
def run_log_session(
    workspace_logs: Path,
    *,
    command: str,
    header: str,
    metadata: dict[str, object] | None = None,
) -> Iterator[RunLogSession]:
    session = RunLogSession.create(
        workspace_logs,
        command=command,
        header=header,
        metadata=metadata,
    )
    try:
        yield session
    except Exception:
        session.write_result(exit_code=1, ok=False)
        raise
    else:
        code = 0 if session._exit_code is None else session._exit_code
        session.write_result(exit_code=code, ok=code == 0)
    finally:
        session.close()


@contextmanager
def tee_log_file(log_path: Path, *, header: str | None = None) -> Iterator[None]:
    """Legacy tee for stdout/stderr (Python-level only). Prefer RunLogSession."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_handle:
        if header:
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            log_handle.write(f"=== {stamp} {header} ===\n")
            log_handle.flush()
            print(f"=== {stamp} {header} ===")
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = Tee(original_stdout, log_handle)  # type: ignore[assignment]
        sys.stderr = Tee(original_stderr, log_handle)  # type: ignore[assignment]
        try:
            yield
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
