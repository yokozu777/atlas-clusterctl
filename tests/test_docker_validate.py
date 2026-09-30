"""Tests for clusterctl.docker_validate."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from clusterctl.context import ClusterContext
from clusterctl.docker_executor import (
    CONTAINER_ASYNC_DIR,
    CONTAINER_HOME,
    DOCKER_WORKSPACE_ANSIBLE_ENV_KEYS,
    build_container_env,
)
from clusterctl.docker_validate import (
    DockerValidateOptions,
    check_docker_playbooks_host,
    check_docker_workspace_ansible_host,
    cmd_docker_pull,
    docker_pull_image,
    validate_docker_deep,
    verify_container_mounts,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import local_playbooks_override_block, seed_org_baseline_fixture
from clusterctl.workspace_paths import container_controller_ansible_tmp_dir


class DockerValidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._env_root = os.environ.get("ATLAS_CLUSTER_ROOT")
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._seed_cluster()

    def tearDown(self) -> None:
        if self._env_root is None:
            os.environ.pop("ATLAS_CLUSTER_ROOT", None)
        else:
            os.environ["ATLAS_CLUSTER_ROOT"] = self._env_root
        self._tmpdir.cleanup()

    def _seed_cluster(self) -> None:
        cluster = self.root / "clusters" / "lab"
        all_dir = cluster / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        seed_org_baseline_fixture(self.root)
        (cluster / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab",
                    "playbooks_enabled": True,
                    "playbooks": local_playbooks_override_block(),
                    "execution": {
                        "mode": "docker",
                        "image": "reg.example.com/library/cluster-executor",
                        "tag": "1",
                    },
                    "inventory": "hosts",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (cluster / "hosts").write_text(
            'all:\n  children:\n    k8s_masters:\n      hosts:\n        m1: {}\n',
            encoding="utf-8",
        )
        (all_dir / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        from clusterctl.pipeline_fixture import seed_local_playbook_repo_stubs
        seed_local_playbook_repo_stubs(self.root)

    def _ctx(self) -> ClusterContext:
        return ClusterContext.load(cluster_id="lab")

    def test_skips_when_local_mode(self) -> None:
        cluster_yaml = self.root / "clusters" / "lab" / "cluster.yaml"
        data = yaml.safe_load(cluster_yaml.read_text(encoding="utf-8"))
        data["execution"] = {"mode": "local"}
        cluster_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        checks = validate_docker_deep(self._ctx())
        self.assertEqual(checks, [])

    @mock.patch("clusterctl.docker_validate.run_docker_smoke")
    @mock.patch("clusterctl.docker_validate.docker_pull_image")
    @mock.patch("clusterctl.docker_validate.docker_cli_available", return_value=True)
    @mock.patch("clusterctl.docker_validate.check_ssh_key", return_value=None)
    def test_deep_validate_pull_and_smoke(
        self,
        _ssh: mock.Mock,
        _cli: mock.Mock,
        pull: mock.Mock,
        smoke: mock.Mock,
    ) -> None:
        pull.return_value = (True, "Image is up to date")
        smoke.return_value = (True, "dry-run ok")

        checks = validate_docker_deep(self._ctx())
        codes = [check.code for check in checks]
        self.assertIn("execution_docker_repos", codes)
        self.assertIn("execution_docker_pull", codes)
        self.assertIn("execution_docker_smoke", codes)
        pull.assert_called_once()
        smoke.assert_called_once()

    @mock.patch("clusterctl.docker_validate.docker_pull_image")
    @mock.patch("clusterctl.docker_validate.docker_cli_available", return_value=True)
    @mock.patch("clusterctl.docker_validate.check_ssh_key", return_value=None)
    def test_pull_failure_skips_smoke(
        self,
        _ssh: mock.Mock,
        _cli: mock.Mock,
        pull: mock.Mock,
    ) -> None:
        pull.return_value = (False, "unauthorized")

        with mock.patch("clusterctl.docker_validate.run_docker_smoke") as smoke:
            checks = validate_docker_deep(self._ctx())
            smoke.assert_not_called()

        errors = [check for check in checks if check.severity == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code, "execution_docker_pull")

    def test_verify_container_mounts_detects_missing(self) -> None:
        ctx = self._ctx()
        missing = verify_container_mounts(ctx)
        self.assertEqual(missing, [])

        shutil.rmtree(self.root / "atlas-k8s-core")
        missing = verify_container_mounts(ctx)
        self.assertIn("atlas-k8s-core", missing)

    def test_build_container_env_sets_workspace_ansible_paths(self) -> None:
        ctx = self._ctx()
        env = build_container_env(ctx)
        ws = ctx.workspace_root.resolve()
        container_tmp = container_controller_ansible_tmp_dir(ctx.workspace_id)
        self.assertEqual(
            env["ANSIBLE_CACHE_PLUGIN_CONNECTION"],
            str(ws / ".ansible_facts_cache"),
        )
        self.assertEqual(env["ANSIBLE_LOCAL_TEMP"], str(container_tmp))
        self.assertEqual(env["TMPDIR"], str(container_tmp))
        self.assertEqual(env["HOME"], CONTAINER_HOME)
        self.assertEqual(env["ANSIBLE_ASYNC_DIR"], CONTAINER_ASYNC_DIR)
        for key in DOCKER_WORKSPACE_ANSIBLE_ENV_KEYS:
            self.assertIn(key, env)
        self.assertIn("/tmp/atlas-ssh/id_rsa", env["GIT_SSH_COMMAND"])
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "safe.directory")
        self.assertEqual(env["GIT_CONFIG_VALUE_0"], "*")

    def test_build_container_env_ignores_host_git_ssh_command(self) -> None:
        os.environ["GIT_SSH_COMMAND"] = "ssh -i /host/only/key -o IdentitiesOnly=yes"
        try:
            env = build_container_env(self._ctx())
        finally:
            os.environ.pop("GIT_SSH_COMMAND", None)
        self.assertIn("/tmp/atlas-ssh/id_rsa", env["GIT_SSH_COMMAND"])
        self.assertNotIn("/host/only/key", env["GIT_SSH_COMMAND"])

    def test_check_docker_workspace_ansible_host(self) -> None:
        check = check_docker_workspace_ansible_host(self._ctx())
        self.assertIsNotNone(check)
        assert check is not None
        self.assertEqual(check.severity, "ok")
        self.assertEqual(check.code, "execution_docker_workspace_ansible")

    def test_check_docker_playbooks_host_ok_with_phase_runner(self) -> None:
        check = check_docker_playbooks_host(self._ctx())
        self.assertIsNotNone(check)
        assert check is not None
        self.assertEqual(check.severity, "ok")
        self.assertEqual(check.code, "execution_docker_repos")

    def test_check_docker_playbooks_host_errors_without_phase_runner(self) -> None:
        with mock.patch("clusterctl.docker_validate.uses_phase_runner", return_value=False):
            check = check_docker_playbooks_host(self._ctx())
        self.assertIsNotNone(check)
        assert check is not None
        self.assertEqual(check.severity, "error")
        self.assertEqual(check.code, "execution_docker_phases_missing")

    def test_check_docker_playbooks_host_errors_without_playbooks_enabled(self) -> None:
        cluster_yaml = self.root / "clusters" / "lab" / "cluster.yaml"
        data = yaml.safe_load(cluster_yaml.read_text(encoding="utf-8"))
        data["playbooks_enabled"] = False
        cluster_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        check = check_docker_playbooks_host(self._ctx())
        self.assertIsNotNone(check)
        assert check is not None
        self.assertEqual(check.severity, "error")
        self.assertEqual(check.code, "execution_docker_repos_missing")

    @mock.patch("clusterctl.docker_validate.run_docker_smoke")
    @mock.patch("clusterctl.docker_validate.docker_pull_image", return_value=(True, "ok"))
    @mock.patch("clusterctl.docker_validate.docker_cli_available", return_value=True)
    @mock.patch("clusterctl.docker_validate.check_ssh_key", return_value=None)
    def test_no_pull_when_disabled(
        self,
        _ssh: mock.Mock,
        _cli: mock.Mock,
        pull: mock.Mock,
        smoke: mock.Mock,
    ) -> None:
        smoke.return_value = (True, "ok")
        opts = DockerValidateOptions(pull=False)
        checks = validate_docker_deep(self._ctx(), options=opts)
        pull.assert_not_called()
        self.assertTrue(any(check.code == "execution_docker_smoke" for check in checks))

    @mock.patch("clusterctl.docker_validate.subprocess.run")
    def test_docker_pull_pins_linux_amd64(self, run: mock.Mock) -> None:
        run.return_value = mock.Mock(returncode=0, stdout="ok\n", stderr="")
        ok, _detail = docker_pull_image(
            "harbor.example/library/krang:latest",
            timeout_sec=5,
        )
        self.assertTrue(ok)
        self.assertEqual(
            run.call_args.args[0],
            [
                "docker",
                "pull",
                "--platform",
                "linux/amd64",
                "harbor.example/library/krang:latest",
            ],
        )

    @mock.patch("clusterctl.docker_validate.docker_pull_image", return_value=(True, "Digest: sha256:abc"))
    def test_cmd_docker_pull(self, pull: mock.Mock) -> None:
        code = cmd_docker_pull(self._ctx())
        self.assertEqual(code, 0)
        pull.assert_called_once_with(
            "reg.example.com/library/cluster-executor:1",
            timeout_sec=600,
        )

    @mock.patch("clusterctl.docker_validate.docker_pull_image", return_value=(False, "denied"))
    def test_cmd_docker_pull_failure(self, _pull: mock.Mock) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            cmd_docker_pull(self._ctx())
        self.assertIn("denied", str(ctx.exception))

    def test_cmd_docker_pull_local_mode(self) -> None:
        cluster_yaml = self.root / "clusters" / "lab" / "cluster.yaml"
        data = yaml.safe_load(cluster_yaml.read_text(encoding="utf-8"))
        data["execution"] = {"mode": "local"}
        cluster_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        with self.assertRaises(ClusterctlError) as ctx:
            cmd_docker_pull(self._ctx())
        self.assertIn("not docker", str(ctx.exception))

    def test_cli_parses_docker_pull(self) -> None:
        from clusterctl.__main__ import _build_parser

        parsed = _build_parser().parse_args(["--cluster", "lab", "docker", "pull"])
        self.assertEqual(parsed.command, "docker")
        self.assertEqual(parsed.docker_command, "pull")
        self.assertEqual(parsed.cluster, "lab")


if __name__ == "__main__":
    unittest.main()
