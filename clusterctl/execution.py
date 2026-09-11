"""Execution runtime: local controller vs Docker container."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clusterctl.exceptions import ClusterctlError

EXECUTION_MODES = frozenset({"local", "docker"})
_REJECTED_EXECUTION_MODE = "krang"

ENV_EXECUTOR = "CLUSTER_EXECUTOR"
ENV_FORCE_LOCAL = "CLUSTER_EXECUTOR_FORCE_LOCAL"
ENV_DOCKER_IMAGE = "EXECUTION_DOCKER_IMAGE"
ENV_DOCKER_TAG = "EXECUTION_DOCKER_TAG"


@dataclass(frozen=True)
class DockerConfig:
    """Docker executor settings from cluster.yaml ``execution`` (mode=docker)."""

    image: str = ""
    tag: str = ""
    repos_root: str | None = None
    extra_args: tuple[str, ...] = ()

    @property
    def image_ref(self) -> str:
        return f"{self.image}:{self.tag}"


@dataclass(frozen=True)
class ExecutionConfig:
    mode: str = "local"
    docker: DockerConfig = field(default_factory=DockerConfig)

    @property
    def is_local(self) -> bool:
        return self.mode == "local"

    @property
    def is_docker(self) -> bool:
        return self.mode == "docker"

    def summary(self) -> str:
        if self.is_docker:
            return f"docker ({self.docker.image_ref})"
        return "local"


@dataclass(frozen=True)
class ExecutionResolution:
    configured: ExecutionConfig
    effective: ExecutionConfig
    source: str

    @property
    def mode_changed(self) -> bool:
        return self.configured.mode != self.effective.mode


def default_execution_config() -> ExecutionConfig:
    return ExecutionConfig()


def _reject_legacy_execution_block(raw: dict) -> None:
    if _REJECTED_EXECUTION_MODE in raw:
        raise ClusterctlError(
            "execution.krang removed — set execution.mode: docker with "
            "execution.image and execution.tag in cluster.yaml"
        )


def _parse_docker_config(raw: dict, *, mode: str) -> DockerConfig:
    _reject_legacy_execution_block(raw)

    image = str(raw.get("image", "")).strip()
    tag = str(raw.get("tag", "")).strip()

    if mode == "docker":
        if not image:
            raise ClusterctlError(
                "execution.mode: docker requires execution.image in cluster.yaml"
            )
        if not tag:
            raise ClusterctlError(
                "execution.mode: docker requires execution.tag in cluster.yaml"
            )
        if "/" not in image and "." not in image:
            raise ClusterctlError(
                f"execution.image looks invalid: {image!r} "
                "(expected registry/repo/name)"
            )

    repos_root_raw = raw.get("repos_root")
    repos_root = (
        None
        if repos_root_raw is None
        else (str(repos_root_raw).strip() or None)
    )

    extra_args_raw = raw.get("extra_args")
    extra_args: tuple[str, ...] = ()
    if extra_args_raw is not None:
        if not isinstance(extra_args_raw, list):
            raise ClusterctlError("execution.extra_args must be a list of strings")
        extra_args = tuple(str(item).strip() for item in extra_args_raw if str(item).strip())

    return DockerConfig(image=image, tag=tag, repos_root=repos_root, extra_args=extra_args)


def _normalize_mode(mode_raw: object) -> str:
    mode = str(mode_raw).strip().lower()
    if mode == _REJECTED_EXECUTION_MODE:
        raise ClusterctlError(
            "execution.mode: krang removed — use execution.mode: docker"
        )
    if mode not in EXECUTION_MODES:
        raise ClusterctlError(
            f"execution.mode must be one of {sorted(EXECUTION_MODES)}, got {mode_raw!r}"
        )
    return mode


def parse_execution_config(raw: object | None) -> ExecutionConfig:
    if raw is None:
        return default_execution_config()

    if isinstance(raw, str):
        mode = _normalize_mode(raw)
        if mode == "docker":
            raise ClusterctlError(
                "execution: docker mode requires a mapping with image and tag"
            )
        return ExecutionConfig(mode=mode)

    if not isinstance(raw, dict):
        raise ClusterctlError(
            f"execution must be a string or mapping, got {type(raw).__name__}"
        )

    mode = _normalize_mode(raw.get("mode", "local"))
    docker = _parse_docker_config(raw, mode=mode)
    return ExecutionConfig(mode=mode, docker=docker)


def resolve_execution_mode(
    configured: ExecutionConfig | None = None,
    *,
    explicit: str | None = None,
    respect_env: bool = True,
) -> ExecutionConfig:
    return resolve_execution(
        configured,
        explicit=explicit,
        respect_env=respect_env,
    ).effective


def _normalize_executor_override(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == _REJECTED_EXECUTION_MODE:
        raise ClusterctlError(
            "executor mode 'krang' removed — use 'docker' "
            "(set execution.mode: docker in cluster.yaml)"
        )
    return normalized


def resolve_execution(
    configured: ExecutionConfig | None = None,
    *,
    explicit: str | None = None,
    respect_env: bool = True,
) -> ExecutionResolution:
    base = configured or default_execution_config()

    if respect_env and os.environ.get(ENV_FORCE_LOCAL, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return ExecutionResolution(
            configured=base,
            effective=ExecutionConfig(mode="local", docker=base.docker),
            source=f"{ENV_FORCE_LOCAL} (inside docker container)",
        )

    cli_override = _normalize_executor_override(explicit or "")
    env_override = (
        _normalize_executor_override(os.environ.get(ENV_EXECUTOR, ""))
        if respect_env
        else ""
    )

    if cli_override:
        if cli_override not in EXECUTION_MODES:
            raise ClusterctlError(
                f"--executor must be one of {sorted(EXECUTION_MODES)}, got {cli_override!r}"
            )
        return ExecutionResolution(
            configured=base,
            effective=ExecutionConfig(mode=cli_override, docker=base.docker),
            source=f"--executor {cli_override}",
        )

    if env_override:
        if env_override not in EXECUTION_MODES:
            raise ClusterctlError(
                f"{ENV_EXECUTOR} must be one of {sorted(EXECUTION_MODES)}, got {env_override!r}"
            )
        return ExecutionResolution(
            configured=base,
            effective=ExecutionConfig(mode=env_override, docker=base.docker),
            source=f"{ENV_EXECUTOR}={env_override}",
        )

    if configured is not None:
        return ExecutionResolution(
            configured=base,
            effective=base,
            source="cluster.yaml",
        )

    return ExecutionResolution(
        configured=base,
        effective=base,
        source="default",
    )


def is_inside_docker_container() -> bool:
    return os.environ.get(ENV_FORCE_LOCAL, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _env_docker_image() -> str:
    return os.environ.get(ENV_DOCKER_IMAGE, "").strip()


def _env_docker_tag() -> str:
    return os.environ.get(ENV_DOCKER_TAG, "").strip()


def resolve_docker_image_ref(docker: DockerConfig) -> str:
    image = _env_docker_image() or docker.image
    tag = _env_docker_tag() or docker.tag
    if not image or not tag:
        raise ClusterctlError(
            "docker image:tag not configured — set execution.image and execution.tag "
            "in cluster.yaml"
        )
    return f"{image}:{tag}"


def execution_config_from_cluster_data(data: dict[str, Any]) -> ExecutionConfig:
    return parse_execution_config(data.get("execution"))


def docker_cli_available() -> bool:
    return shutil.which("docker") is not None


def check_ssh_key(path: Path) -> str | None:
    if not path.is_file():
        return f"SSH key not found: {path}"
    if not os.access(path, os.R_OK):
        return f"SSH key not readable: {path}"
    return None


@dataclass(frozen=True)
class ExecutionCheck:
    severity: str
    code: str
    message: str
    hint: str | None = None


def validate_execution_runtime(
    resolution: ExecutionResolution,
    *,
    ssh_key: Path,
) -> list[ExecutionCheck]:
    checks: list[ExecutionCheck] = []
    execution = resolution.effective
    configured_mode = resolution.configured.mode

    source_detail = resolution.source
    if resolution.mode_changed:
        source_detail = f"{configured_mode} → {execution.mode} ({resolution.source})"

    checks.append(
        ExecutionCheck(
            severity="ok",
            code="execution_resolved",
            message=f"execution: {execution.summary()} [{source_detail}]",
        )
    )

    if execution.is_local:
        if configured_mode == "docker" and resolution.mode_changed:
            checks.append(
                ExecutionCheck(
                    severity="warning",
                    code="execution_override_local",
                    message=f"cluster.yaml requests docker but {resolution.source} forces local",
                )
            )
        return checks

    if not execution.docker.image or not execution.docker.tag:
        checks.append(
            ExecutionCheck(
                severity="error",
                code="execution_docker_image_missing",
                message="execution.mode=docker requires execution.image and execution.tag in cluster.yaml",
            )
        )

    if not docker_cli_available():
        checks.append(
            ExecutionCheck(
                severity="error",
                code="execution_docker_cli_missing",
                message="execution.mode=docker requires docker CLI on PATH",
                hint="install docker or set execution.mode: local / --executor local",
            )
        )

    ssh_error = check_ssh_key(ssh_key)
    if ssh_error:
        checks.append(
            ExecutionCheck(
                severity="error",
                code="execution_ssh_key",
                message=ssh_error,
                hint="set SSH_KEY to a readable private key path",
            )
        )

    if configured_mode == "local" and resolution.mode_changed:
        checks.append(
            ExecutionCheck(
                severity="warning",
                code="execution_override_docker",
                message=f"{resolution.source} overrides cluster.yaml execution.mode: local",
            )
        )

    if _env_docker_tag() or _env_docker_image():
        try:
            effective_ref = resolve_docker_image_ref(execution.docker)
            checks.append(
                ExecutionCheck(
                    severity="ok",
                    code="execution_docker_env_override",
                    message=(
                        f"docker env override active: {effective_ref} "
                        f"(cluster.yaml: {execution.docker.image_ref})"
                    ),
                )
            )
        except ClusterctlError:
            pass

    return checks
