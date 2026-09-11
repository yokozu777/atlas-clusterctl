"""Tests for clusterctl.execution."""

from __future__ import annotations

import unittest

from clusterctl.exceptions import ClusterctlError
from clusterctl.execution import (
    ExecutionConfig,
    parse_execution_config,
    resolve_docker_image_ref,
    resolve_execution,
)


class ExecutionParseTest(unittest.TestCase):
    def test_local_default(self) -> None:
        cfg = parse_execution_config(None)
        self.assertEqual(cfg.mode, "local")
        self.assertEqual(cfg.docker.image, "")

    def test_docker_requires_image_tag(self) -> None:
        with self.assertRaises(ClusterctlError):
            parse_execution_config({"mode": "docker"})
        with self.assertRaises(ClusterctlError):
            parse_execution_config({"mode": "docker", "image": "reg.io/foo/bar"})

    def test_docker_from_yaml(self) -> None:
        cfg = parse_execution_config(
            {
                "mode": "docker",
                "image": "harbor.example.com/library/cluster-executor",
                "tag": "42",
            }
        )
        self.assertTrue(cfg.is_docker)
        self.assertEqual(cfg.docker.image_ref, "harbor.example.com/library/cluster-executor:42")

    def test_rejects_krang_mode(self) -> None:
        with self.assertRaises(ClusterctlError):
            parse_execution_config({"mode": "krang", "image": "a/b/c", "tag": "1"})

    def test_rejects_krang_block(self) -> None:
        with self.assertRaises(ClusterctlError):
            parse_execution_config(
                {
                    "mode": "docker",
                    "krang": {"image": "a/b/c", "tag": "1"},
                }
            )

    def test_resolve_image_from_yaml_only(self) -> None:
        docker = ExecutionConfig(
            mode="docker",
            docker=parse_execution_config(
                {"mode": "docker", "image": "reg.io/repo/name", "tag": "99"}
            ).docker,
        ).docker
        self.assertEqual(resolve_docker_image_ref(docker), "reg.io/repo/name:99")

    def test_rejects_krang_executor_alias(self) -> None:
        base = parse_execution_config(
            {"mode": "docker", "image": "reg.io/repo/name", "tag": "1"}
        )
        with self.assertRaises(ClusterctlError):
            resolve_execution(base, explicit="krang")


if __name__ == "__main__":
    unittest.main()
