"""Phase 3: docker_executor unified phase-runner mounts."""

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
    CONTAINER_NSS_USER,
    CONTAINER_NSS_WRAPPER_SO,
    CONTAINER_SSH_KEY,
    _ownership_fix_paths,
    build_docker_mounts,
    build_docker_run_command,
    docker_bind_source,
    docker_ssh_staging_parent,
    fix_bind_mount_ownership,
    normalize_docker_host_source,
    prepare_container_ssh_key,
    preflight_docker,
    run_docker_container,
)
from clusterctl.exceptions import ClusterctlError
from clusterctl.execution import resolve_docker_image_ref
from clusterctl.pipeline_fixture import (
    local_playbooks_override_block,
    seed_local_playbook_repo_stubs,
    seed_org_baseline_fixture,
)


class DockerExecutorUnifiedTest(unittest.TestCase):
    _ISOLATED_ENV_KEYS = (
        "ATLAS_CLUSTER_ROOT",
        "ATLAS_CLUSTERS_ROOT",
        "ATLAS_WORKSPACE_ROOT",
        "ATLAS_CLUSTER_ROOT_HOST",
        "ATLAS_CLUSTERS_ROOT_HOST",
        "ATLAS_WORKSPACE_ROOT_HOST",
        "CLUSTER_ID",
        # run_ci.sh points this at an empty file; fixtures use .config/config.yaml.
        "ATLAS_CLUSTERCTL_CONFIG",
        "ATLAS_EXECUTION_ID",
    )

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        self._seed_v1_legacy_cluster()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_v2_docker_cluster(self) -> None:
        seed_org_baseline_fixture(self.root)
        seed_local_playbook_repo_stubs(self.root)
        sibling_repo = self.root.parent / f"sibling_init_{self.root.name}"
        sibling_repo.mkdir(exist_ok=True)
        (sibling_repo / "roles" / "dummy").mkdir(parents=True)
        self._sibling_repo = sibling_repo

        leaf = self.root / "clusters" / "lab" / "docker"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab/docker",
                    "playbooks": {
                        **local_playbooks_override_block(
                            "atlas-infra-edge",
                            "atlas-compute-provision",
                            "atlas-k8s-core",
                            "atlas-k8s-addons",
                        ),
                        "atlas-node-foundation": {
                            "source": "local",
                            "path": sibling_repo.name,
                            "path_relative_to": "sibling",
                        },
                    },
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
        (leaf / "hosts").write_text(
            'all:\n  children:\n    k8s_masters:\n      hosts:\n        m1: {}\n',
            encoding="utf-8",
        )
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/docker",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.docker.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def _seed_v1_legacy_cluster(self) -> None:
        leaf = self.root / "clusters" / "lab" / "legacy"
        leaf.mkdir(parents=True)
        (leaf / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "id": "lab/legacy",
                    "inventory": "hosts",
                    "execution": {"mode": "docker", "image": "reg.example.com/x", "tag": "1"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (leaf / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        gv = leaf / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab/legacy",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.legacy.example.com",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def test_build_docker_mounts_uses_phase_runner_path(self) -> None:
        self._seed_v2_docker_cluster()
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        prepared = prepare_container_ssh_key(
            ssh, staging_parent=docker_ssh_staging_parent(ctx.workspace_root)
        )
        try:
            mounts = build_docker_mounts(ctx, ssh_key_host=prepared.key_path)
            mount_text = " ".join(mounts)
            self.assertIn(str(self._sibling_repo), mount_text)
            self.assertIn(str(prepared.key_path), mount_text)
            self.assertIn(f"{prepared.key_path}:{CONTAINER_SSH_KEY}:ro", mount_text)
            self.assertIn("/.atlas-ssh/atlas-ssh-", mount_text)
            self.assertNotIn("/.cache/docker-identity/", mount_text)
            self.assertNotIn(str(self.root / ".cache"), mount_text)
        finally:
            prepared.cleanup()

    def test_build_docker_mounts_sibling_inventory_and_workspace(self) -> None:
        self._seed_v2_docker_cluster()
        inventory = self.root.parent / f"inv_{self.root.name}"
        workspace = inventory / "workspace"
        clusters = inventory / "clusters"
        src = self.root / "clusters" / "lab" / "docker"
        dest = clusters / "lab" / "docker"
        dest.mkdir(parents=True)
        for item in src.iterdir():
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                target.write_bytes(item.read_bytes())
        workspace.mkdir(parents=True)
        cfg_dir = self.root / ".config"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "clusters": {"path": str(clusters)},
                    "workspace": {"path": str(workspace)},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        prepared = prepare_container_ssh_key(
            ssh, staging_parent=docker_ssh_staging_parent(ctx.workspace_root)
        )
        try:
            mounts = build_docker_mounts(ctx, ssh_key_host=prepared.key_path)
            mount_text = " ".join(mounts)
            self.assertIn(str(inventory.resolve()), mount_text)
            self.assertIn(str(self.root.resolve()), mount_text)
        finally:
            prepared.cleanup()

    def test_build_docker_run_command_mkdirs_controller_tmp(self) -> None:
        self._seed_v2_docker_cluster()
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        prepared = prepare_container_ssh_key(
            ssh, staging_parent=docker_ssh_staging_parent(ctx.workspace_root)
        )
        try:
            # build_docker_run_command no longer runs preflight (caller does).
            cmd = build_docker_run_command(
                ctx,
                ["python3", "-m", "clusterctl", "plan"],
                ssh_key_host=prepared.key_path,
            )
            joined = " ".join(cmd)
            self.assertIn("mkdir -p", joined)
            self.assertIn("/tmp/clusterctl/", joined)
            self.assertIn(CONTAINER_HOME, joined)
            self.assertIn(f"HOME={CONTAINER_HOME}", joined)
            self.assertIn(CONTAINER_ASYNC_DIR, joined)
            self.assertIn(f"ANSIBLE_ASYNC_DIR={CONTAINER_ASYNC_DIR}", joined)
            self.assertIn(CONTAINER_NSS_WRAPPER_SO, joined)
            self.assertIn("NSS_WRAPPER_PASSWD", joined)
            self.assertIn("LD_PRELOAD", joined)
            self.assertIn(f"USER={CONTAINER_NSS_USER}", joined)
            self.assertIn("nss_wrapper required", joined)
            self.assertIn("/tmp/atlas-ssh/id_rsa", joined)
            self.assertIn(str(prepared.key_path), joined)
            self.assertIn("--user", cmd)
            user_at = cmd.index("--user")
            self.assertEqual(cmd[user_at + 1], f"{os.getuid()}:{os.getgid()}")
            self.assertEqual(cmd[user_at + 2 : user_at + 4], ["--platform", "linux/amd64"])
            self.assertEqual(cmd[user_at + 4], resolve_docker_image_ref(ctx.execution.docker))
            self.assertNotIn("/etc/passwd", joined)
        finally:
            prepared.cleanup()

    def test_build_docker_run_command_names_container_from_execution_id(self) -> None:
        self._seed_v2_docker_cluster()
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        os.environ["ATLAS_EXECUTION_ID"] = "198fbeab-43e8-4707-bf47-396fcfcb0caa"
        ctx = ClusterContext.load(cluster_id="lab/docker")
        prepared = prepare_container_ssh_key(
            ssh, staging_parent=docker_ssh_staging_parent(ctx.workspace_root)
        )
        try:
            cmd = build_docker_run_command(
                ctx,
                ["python3", "-m", "clusterctl", "plan"],
                ssh_key_host=prepared.key_path,
            )
            self.assertIn("--name", cmd)
            self.assertEqual(
                cmd[cmd.index("--name") + 1],
                "atlas-exec-198fbeab-43e8-4707-bf47-396fcfcb0caa",
            )
            self.assertIn("--label", cmd)
            self.assertEqual(
                cmd[cmd.index("--label") + 1],
                "atlas.execution_id=198fbeab-43e8-4707-bf47-396fcfcb0caa",
            )
        finally:
            prepared.cleanup()

    @mock.patch("clusterctl.docker_executor.subprocess.run")
    @mock.patch("clusterctl.docker_executor.fix_bind_mount_ownership")
    @mock.patch("clusterctl.docker_executor.preflight_docker")
    @mock.patch("clusterctl.docker_executor.prepare_container_ssh_key")
    @mock.patch(
        "clusterctl.docker_executor.build_docker_run_command",
        return_value=["true"],
    )
    @mock.patch(
        "clusterctl.docker_executor.resolve_docker_image_ref",
        return_value="img:tag",
    )
    def test_run_docker_container_does_not_chown(
        self,
        _ref: mock.Mock,
        _build: mock.Mock,
        prepare: mock.Mock,
        _preflight: mock.Mock,
        chown: mock.Mock,
        run: mock.Mock,
    ) -> None:
        self._seed_v2_docker_cluster()
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        staging = tempfile.TemporaryDirectory(dir=self.root)
        key = Path(staging.name) / "id_rsa"
        key.write_text("k\n", encoding="utf-8")
        prepared = mock.Mock()
        prepared.key_path = key
        prepared.cleanup = mock.Mock()
        prepare.return_value = prepared
        run.return_value = mock.Mock(returncode=0)
        try:
            self.assertEqual(run_docker_container(ctx, ["plan"]), 0)
        finally:
            staging.cleanup()
        chown.assert_not_called()
        prepared.cleanup.assert_called_once()

    @mock.patch("clusterctl.docker_executor.subprocess.run")
    @mock.patch("clusterctl.docker_executor.docker_cli_available", return_value=True)
    def test_fix_bind_mount_ownership_chowns_workspace(
        self,
        _docker: mock.Mock,
        run: mock.Mock,
    ) -> None:
        self._seed_v2_docker_cluster()
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        ws = ctx.workspace_root
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "marker").write_text("x", encoding="utf-8")
        # Sibling under shared parent must not be in the reclaim set.
        sibling = ws.parent.parent / "ci" / "redis"
        sibling.mkdir(parents=True, exist_ok=True)
        fix_bind_mount_ownership(ctx)
        run.assert_called_once()
        chown_cmd = run.call_args.args[0]
        self.assertEqual(chown_cmd[0:3], ["docker", "run", "--rm"])
        chown_at = chown_cmd.index("chown")
        self.assertEqual(
            chown_cmd[chown_at - 3 : chown_at - 1],
            ["--platform", "linux/amd64"],
        )
        reclaim = {Path(p).resolve() for p in chown_cmd[chown_at + 3 :]}
        self.assertIn(ws.resolve(), reclaim)
        self.assertNotIn((self.root / "workspace").resolve(), reclaim)
        self.assertNotIn(sibling.resolve(), reclaim)
        self.assertIn(f"{os.getuid()}:{os.getgid()}", chown_cmd)

    def test_ownership_fix_paths_narrow_inventory_scope(self) -> None:
        """Phase 6 Stage 3: chown inventory tfstate/.git only — not clusters/."""
        self._seed_v2_docker_cluster()
        inv = self.root.parent / f"inv_{self.root.name}"
        shutil.rmtree(inv, ignore_errors=True)
        inv.mkdir(parents=True)
        (inv / "tfstate").mkdir()
        (inv / ".git").mkdir()
        src_leaf = self.root / "clusters" / "lab" / "docker"
        dst_leaf = inv / "clusters" / "lab" / "docker"
        shutil.copytree(src_leaf, dst_leaf)
        # Org baseline still resolved from product clusters under controller when
        # inventory cascade lacks default/default — copy minimal baseline.
        src_baseline = self.root / "clusters" / "default" / "default"
        if src_baseline.is_dir():
            shutil.copytree(src_baseline, inv / "clusters" / "default" / "default")
        os.environ["ATLAS_CLUSTERS_ROOT"] = str((inv / "clusters").resolve())
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        paths = _ownership_fix_paths(ctx)
        path_set = {p.resolve() for p in paths}
        self.assertIn((inv / "tfstate").resolve(), path_set)
        self.assertIn((inv / ".git").resolve(), path_set)
        self.assertNotIn((inv / "clusters").resolve(), path_set)
        self.assertNotIn(inv.resolve(), path_set)

    def test_ownership_fix_paths_per_cluster_workspace_sibling_layout(self) -> None:
        """Reclaim workspace/<id>/ only — not shared workspace parent or siblings."""
        self._seed_v2_docker_cluster()
        inv = self.root.parent / f"inv_ws_{self.root.name}"
        shutil.rmtree(inv, ignore_errors=True)
        inv.mkdir(parents=True)
        (inv / "tfstate").mkdir()
        (inv / ".git").mkdir()
        ws_parent = inv / "workspace"
        ws_cluster = ws_parent / "lab" / "docker"
        ws_sibling = ws_parent / "ci" / "redis"
        ws_cluster.mkdir(parents=True)
        ws_sibling.mkdir(parents=True)
        (ws_sibling / "logs").mkdir()
        src_leaf = self.root / "clusters" / "lab" / "docker"
        shutil.copytree(src_leaf, inv / "clusters" / "lab" / "docker")
        src_baseline = self.root / "clusters" / "default" / "default"
        if src_baseline.is_dir():
            shutil.copytree(src_baseline, inv / "clusters" / "default" / "default")
        cfg = self.root / ".config"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.yaml").write_text(
            yaml.safe_dump(
                {
                    "clusters": {"path": str((inv / "clusters").resolve())},
                    "workspace": {"path": str(ws_parent.resolve())},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        self.assertEqual(ctx.workspace_root.resolve(), ws_cluster.resolve())
        path_set = {p.resolve() for p in _ownership_fix_paths(ctx)}
        self.assertIn(ws_cluster.resolve(), path_set)
        self.assertNotIn(ws_parent.resolve(), path_set)
        self.assertNotIn(ws_sibling.resolve(), path_set)
        self.assertIn((inv / "tfstate").resolve(), path_set)
        self.assertIn((inv / ".git").resolve(), path_set)
        self.assertNotIn((inv / "clusters").resolve(), path_set)

    def test_ownership_fix_paths_per_cluster_workspace_controller_local(self) -> None:
        """Controller-local: reclaim repo/workspace/<id>, not repo/workspace/."""
        self._seed_v2_docker_cluster()
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        ws = ctx.workspace_root
        ws.mkdir(parents=True, exist_ok=True)
        sibling = self.root / "workspace" / "ci" / "other"
        sibling.mkdir(parents=True, exist_ok=True)
        path_set = {p.resolve() for p in _ownership_fix_paths(ctx)}
        self.assertIn(ws.resolve(), path_set)
        self.assertNotIn((self.root / "workspace").resolve(), path_set)
        self.assertNotIn(sibling.resolve(), path_set)

    def test_docs_host_user_docker(self) -> None:
        """Docs must say docker --user host uid:gid; no post-run chown contract."""
        root = Path(__file__).resolve().parents[1]
        execution = (root / "docs" / "execution.md").read_text(encoding="utf-8")
        gitlab = (root / "docs" / "gitlab-ci.md").read_text(encoding="utf-8")
        workspace = (root / "docs" / "workspace.md").read_text(encoding="utf-8")
        labs = (root / "docs" / "local-labs.md").read_text(encoding="utf-8")
        for text, name in (
            (execution, "execution.md"),
            (gitlab, "gitlab-ci.md"),
            (workspace, "workspace.md"),
            (labs, "local-labs.md"),
        ):
            self.assertIn("workspace/<cluster_id>/", text, name)
        self.assertIn("--user", execution)
        self.assertIn("uid:gid", execution)
        self.assertIn("does **not** run post-run `chown`", execution)
        self.assertIn("must not include `--user`", execution)
        self.assertIn("nss_wrapper", execution)
        self.assertIn("≥336", execution)
        self.assertIn("--user", gitlab)
        self.assertIn("host uid:gid", gitlab)
        self.assertIn("host uid:gid", workspace)
        self.assertIn("host uid:gid", labs)
        self.assertNotIn(
            "Override image user only via `execution.extra_args`",
            execution,
        )

    def test_build_docker_mounts_rejects_v1_without_phase_runner(self) -> None:
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/legacy")
        prepared = prepare_container_ssh_key(
            ssh, staging_parent=docker_ssh_staging_parent(ctx.workspace_root)
        )
        try:
            with self.assertRaises(ClusterctlError) as raised:
                build_docker_mounts(ctx, ssh_key_host=prepared.key_path)
            self.assertIn("schema v2 playbooks + phases", str(raised.exception))
        finally:
            prepared.cleanup()

    def test_build_docker_mounts_rewrites_host_bind_source(self) -> None:
        self._seed_v2_docker_cluster()
        host_ctl = "/run/desktop/mnt/host/c/Users/me/atlas-clusterctl"
        os.environ["ATLAS_CLUSTER_ROOT_HOST"] = host_ctl
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        prepared = prepare_container_ssh_key(
            ssh, staging_parent=docker_ssh_staging_parent(ctx.workspace_root)
        )
        try:
            with mock.patch(
                "clusterctl.docker_executor.load_self_bind_mounts",
                return_value=[],
            ):
                mounts = build_docker_mounts(ctx, ssh_key_host=prepared.key_path)
            mount_text = " ".join(mounts)
            self.assertIn(f"{host_ctl}:{self.root.resolve()}:rw", mount_text)
            rel = prepared.key_path.resolve().relative_to(self.root.resolve())
            expected_key = host_ctl + "/" + rel.as_posix()
            self.assertIn(f"{expected_key}:{CONTAINER_SSH_KEY}:ro", mount_text)
            self.assertNotIn(f"{self.root.resolve()}:{self.root.resolve()}:rw", mount_text)
        finally:
            prepared.cleanup()

    def test_build_docker_mounts_inspect_source_beats_env_host(self) -> None:
        self._seed_v2_docker_cluster()
        os.environ["ATLAS_CLUSTER_ROOT_HOST"] = "/from-env-host"
        inspect_src = "/run/desktop/mnt/host/c/Users/me/ctl"
        ssh = self.root / "id_rsa"
        ssh.write_text("stub\n", encoding="utf-8")
        os.environ["SSH_KEY"] = str(ssh)
        ctx = ClusterContext.load(cluster_id="lab/docker")
        prepared = prepare_container_ssh_key(
            ssh, staging_parent=docker_ssh_staging_parent(ctx.workspace_root)
        )
        try:
            with mock.patch(
                "clusterctl.docker_executor.load_self_bind_mounts",
                return_value=[(str(self.root.resolve()), inspect_src)],
            ):
                mounts = build_docker_mounts(ctx, ssh_key_host=prepared.key_path)
            mount_text = " ".join(mounts)
            self.assertIn(f"{inspect_src}:{self.root.resolve()}:rw", mount_text)
            self.assertNotIn("/from-env-host:", mount_text)
        finally:
            prepared.cleanup()

    @mock.patch("clusterctl.docker_executor.check_ssh_key", return_value=None)
    @mock.patch("clusterctl.docker_executor.docker_cli_available", return_value=True)
    def test_preflight_docker_rejects_v1_without_phase_runner(
        self,
        _docker: mock.Mock,
        _ssh: mock.Mock,
    ) -> None:
        ctx = ClusterContext.load(cluster_id="lab/legacy")
        with self.assertRaises(ClusterctlError) as raised:
            preflight_docker(ctx)
        self.assertIn("schema v2 playbooks + phases", str(raised.exception))


class DockerBindSourceTest(unittest.TestCase):
    _KEYS = (
        "ATLAS_CLUSTER_ROOT",
        "ATLAS_CLUSTERS_ROOT",
        "ATLAS_WORKSPACE_ROOT",
        "ATLAS_CLUSTER_ROOT_HOST",
        "ATLAS_CLUSTERS_ROOT_HOST",
        "ATLAS_WORKSPACE_ROOT_HOST",
    )

    def setUp(self) -> None:
        self._saved = {key: os.environ.get(key) for key in self._KEYS}
        for key in self._KEYS:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_normalize_windows_drive_to_desktop_mnt(self) -> None:
        self.assertEqual(
            normalize_docker_host_source(r"C:\Users\me\atlas-clusterctl"),
            "/run/desktop/mnt/host/c/Users/me/atlas-clusterctl",
        )
        self.assertEqual(
            normalize_docker_host_source("C:/Users/me/atlas-clusterctl"),
            "/run/desktop/mnt/host/c/Users/me/atlas-clusterctl",
        )
        self.assertEqual(
            normalize_docker_host_source("/home/me/atlas-clusterctl"),
            "/home/me/atlas-clusterctl",
        )

    def test_one_to_one_without_host_env(self) -> None:
        path = Path("/tmp/atlas-bind-source-one-to-one")
        self.assertEqual(
            docker_bind_source(path, mounts=[]),
            str(path.resolve()),
        )

    def test_env_host_prefix_rewrite(self) -> None:
        os.environ["ATLAS_CLUSTER_ROOT"] = "/atlas/clusterctl"
        os.environ["ATLAS_CLUSTER_ROOT_HOST"] = r"C:\Users\me\atlas-clusterctl"
        self.assertEqual(
            docker_bind_source(Path("/atlas/clusterctl"), mounts=[]),
            "/run/desktop/mnt/host/c/Users/me/atlas-clusterctl",
        )
        self.assertEqual(
            docker_bind_source(Path("/atlas/clusterctl/clusterctl"), mounts=[]),
            "/run/desktop/mnt/host/c/Users/me/atlas-clusterctl/clusterctl",
        )

    def test_inspect_mounts_rewrite(self) -> None:
        mounts = [("/atlas/workspace", "/host/inventory/workspace")]
        os.environ["ATLAS_WORKSPACE_ROOT"] = "/atlas/workspace"
        os.environ["ATLAS_WORKSPACE_ROOT_HOST"] = "/from-env"
        self.assertEqual(
            docker_bind_source(
                Path("/atlas/workspace/dev-k8s/.atlas-ssh/key"),
                mounts=mounts,
            ),
            "/host/inventory/workspace/dev-k8s/.atlas-ssh/key",
        )


if __name__ == "__main__":
    unittest.main()
