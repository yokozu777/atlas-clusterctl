"""Layout checks for atlas-k8s-core / atlas-k8s-addons sibling repos."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIBLING_ROOT = REPO_ROOT.parent

CORE_REPO = SIBLING_ROOT / "atlas-k8s-core"
ADDONS_REPO = SIBLING_ROOT / "atlas-k8s-addons"

CORE_ROLES = (
    "00_ensure_workspace",
    "00_controller_tooling",
    "01_validate_vars",
    "02_gather_facts",
    "03_sync_time",
    "04_cluster_state",
    "10_lb",
    "11_k8s_hosts",
    "12_workers_kernel_rbd",
    "21_kubeadm_init",
    "22_cluster_join_token",
    "23_join_masters",
    "24_join_workers",
    "25_kubeadm_upgrade_control_plane",
    "26_kubeadm_upgrade_workers",
    "29_fetch_kubeconfig",
)

ADDON_ROLES = (
    "120_controller_tooling",
    "140_fetch_kubeconfig",
    "210_helm_bootstrap",
    "220_calico",
    "310_prometheus",
    "340_calico_metrics",
    "560_apply_ingress",
    "920_keycloak",
    "930_keycloak_realm",
    "941_k8s_oidc",
    "940_apiserver_oidc",
    "996_cluster_report",
    "999_debug_tooling",
)

CORE_COMMON_TASKS = (
    "kubeadm_generate_join_commands.yaml",
    "kubeadm_cleanup_join_commands.yaml",
)

ADDONS_COMMON_TASKS = (
    "helm_chart_absent.yaml",
    "helm_chart_absent_calico.yaml",
    "fetch_control_plane_files.yaml",
    "ensure_kubectl_secret_from_dir.yaml",
    "rook_csi_volumeattributesclass_rbac.yaml",
    "install_helm_binary.yaml",
)

CORE_FILTER_PLUGINS = (
    "pkg_repo.py",
    "registry_mirror.py",
)

ADDONS_FILTER_PLUGINS = (
    "expand_debug_tooling_hosts.py",
    "helm_repo.py",
    "helm_version.py",
    "oidc_kubeadm.py",
)

CORE_VALIDATE_TASKS = (
    "infra_docker_registry.yml",
    "infra_pkg_repo.yml",
    "inventory_bootstrap.yml",
    "vars_cluster_core.yml",
    "workspace_controller_core.yml",
    "workspace_layout_core.yml",
)

ADDONS_VALIDATE_TASKS = (
    "infra_helm_repo.yml",
    "controller_pki.yml",
    "snapshotter.yml",
    "helm_repos_catalog.yml",
    "namespaces_calico.yml",
    "calico_cluster_network.yml",
    "inventory_masters.yml",
    "vars_cluster_addons.yml",
    "ingress_hosts.yml",
    "namespaces_addons.yml",
    "secrets.yml",
    "workspace_controller_addons.yml",
    "workspace_layout_addons.yml",
    "cluster_credentials.yml",
)

ROLE_PATH_COMMON_INCLUDE = re.compile(
    r'include_tasks:\s*["\']?\{\{\s*role_path\s*\}\}/\.\./common/tasks/([^"\']+)'
)
COMMON_RELATIVE_INCLUDE = re.compile(r"include_tasks:\s*([a-zA-Z0-9_.-]+\.ya?ml)")


def _skip_unless_repo(path: Path) -> None:
    if not path.is_dir():
        raise unittest.SkipTest(f"sibling repo not present: {path}")


def _assert_no_root_level_roles(repo: Path) -> None:
    for child in repo.iterdir():
        if child.is_dir() and re.fullmatch(r"\d{2}_.+", child.name):
            raise AssertionError(f"role must live under roles/: {child.name}")


def _missing_common_includes(repo: Path) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for playbook in list(repo.rglob("*.yaml")) + list(repo.rglob("*.yml")):
        text = playbook.read_text(encoding="utf-8", errors="ignore")
        for match in ROLE_PATH_COMMON_INCLUDE.finditer(text):
            task = match.group(1)
            path = repo / "roles/common/tasks" / task
            if not path.is_file():
                missing.append((str(playbook.relative_to(repo)), task))
        if "roles/common/tasks" not in str(playbook):
            continue
        for match in COMMON_RELATIVE_INCLUDE.finditer(text):
            include = match.group(1).strip()
            if include.startswith("{{"):
                continue
            path = playbook.parent / include
            if not path.is_file():
                missing.append((str(playbook.relative_to(repo)), include))
    return missing


class K8sSplitReposLayoutTest(unittest.TestCase):
    def test_core_repo_layout(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _assert_no_root_level_roles(CORE_REPO)
        self.assertTrue((CORE_REPO / "playbooks/cluster_core.yaml").is_file())
        self.assertEqual((CORE_REPO / "ansible.cfg").read_text(encoding="utf-8").count("roles_path = roles"), 1)
        for role in CORE_ROLES:
            self.assertTrue((CORE_REPO / "roles" / role).is_dir(), role)
        for role in ("210_helm_bootstrap", "220_calico"):
            self.assertFalse(
                (CORE_REPO / "roles" / role).exists(),
                f"core must not ship {role}",
            )
        for task in CORE_COMMON_TASKS:
            path = CORE_REPO / "roles/common/tasks" / task
            self.assertTrue(path.is_file(), str(path))
        for forbidden in (
            "helm_chart_absent.yaml",
            "helm_chart_absent_calico.yaml",
            "install_helm_binary.yaml",
            "fetch_control_plane_files.yaml",
            "ensure_kubectl_secret_from_dir.yaml",
        ):
            path = CORE_REPO / "roles/common/tasks" / forbidden
            self.assertFalse(path.exists(), f"core common must not ship {forbidden}")
        for plugin in CORE_FILTER_PLUGINS:
            path = CORE_REPO / "filter_plugins" / plugin
            self.assertTrue(path.is_file(), str(path))
        for forbidden_plugin in ("helm_repo.py", "helm_version.py"):
            path = CORE_REPO / "filter_plugins" / forbidden_plugin
            self.assertFalse(path.exists(), f"core must not ship {forbidden_plugin}")
        for task in CORE_VALIDATE_TASKS:
            path = CORE_REPO / "roles/01_validate_vars/tasks" / task
            self.assertTrue(path.is_file(), str(path))
        core_validate = (CORE_REPO / "roles/01_validate_vars/tasks/main.yml").read_text(encoding="utf-8")
        self.assertNotIn("snapshotter.yml", core_validate)
        self.assertNotIn("ingress_hosts.yml", core_validate)
        self.assertNotIn("infra_helm_repo.yml", core_validate)
        self.assertNotIn("namespaces_calico.yml", core_validate)
        self.assertEqual(_missing_common_includes(CORE_REPO), [])

    def test_addons_repo_layout(self) -> None:
        _skip_unless_repo(ADDONS_REPO)
        _assert_no_root_level_roles(ADDONS_REPO)
        self.assertTrue((ADDONS_REPO / "playbooks/cluster_addons.yaml").is_file())
        playbook = (ADDONS_REPO / "playbooks/cluster_addons.yaml").read_text(encoding="utf-8")
        self.assertLess(
            playbook.index("120_controller_tooling"),
            playbook.index("130_validate_vars"),
            "controller tooling must run before validate in cluster_addons.yaml",
        )
        self.assertLess(
            playbook.index("130_validate_vars"),
            playbook.index("140_fetch_kubeconfig"),
            "kubeconfig fetch must run after validate in cluster_addons.yaml",
        )
        self.assertLess(
            playbook.index("140_fetch_kubeconfig"),
            playbook.index("210_helm_bootstrap"),
            "kubeconfig fetch must precede helm bootstrap in cluster_addons.yaml",
        )
        self.assertLess(
            playbook.index("120_controller_tooling"),
            playbook.index("210_helm_bootstrap"),
            "controller tooling must precede helm bootstrap in cluster_addons.yaml",
        )
        self.assertLess(
            playbook.index("210_helm_bootstrap"),
            playbook.index("310_prometheus"),
            "helm bootstrap must precede prometheus stack in cluster_addons.yaml",
        )
        self.assertLess(
            playbook.index("220_calico"),
            playbook.index("310_prometheus"),
            "prometheus stack must follow calico in cluster_addons.yaml",
        )
        self.assertLess(
            playbook.index("310_prometheus"),
            playbook.index("410_snapshotter"),
            "prometheus operator must precede rook/storage addons in cluster_addons.yaml",
        )
        self.assertLess(
            playbook.index("340_calico_metrics"),
            playbook.index("410_snapshotter"),
            "calico metrics must precede storage addons in cluster_addons.yaml",
        )
        self.assertLess(
            playbook.index("310_prometheus"),
            playbook.index("430_rook_cluster"),
            "prometheus operator must precede rook-cluster PrometheusRule install",
        )
        self.assertEqual((ADDONS_REPO / "ansible.cfg").read_text(encoding="utf-8").count("roles_path = roles"), 1)
        for role in ADDON_ROLES:
            self.assertTrue((ADDONS_REPO / "roles" / role).is_dir(), role)
        for task in ADDONS_COMMON_TASKS:
            path = ADDONS_REPO / "roles/common/tasks" / task
            self.assertTrue(path.is_file(), str(path))
        for plugin in ADDONS_FILTER_PLUGINS:
            path = ADDONS_REPO / "filter_plugins" / plugin
            self.assertTrue(path.is_file(), str(path))
        for forbidden in ("kubeadm_generate_join_commands.yaml",):
            path = ADDONS_REPO / "roles/common/tasks" / forbidden
            self.assertFalse(path.exists(), f"addons common must not ship {forbidden}")
        for task in ADDONS_VALIDATE_TASKS:
            path = ADDONS_REPO / "roles/130_validate_vars/tasks" / task
            self.assertTrue(path.is_file(), str(path))
        for forbidden_plugin in ("pkg_repo.py", "registry_mirror.py"):
            path = ADDONS_REPO / "filter_plugins" / forbidden_plugin
            self.assertFalse(path.exists(), f"addons must not ship unused {forbidden_plugin}")
        addons_validate = (ADDONS_REPO / "roles/130_validate_vars/tasks/main.yml").read_text(encoding="utf-8")
        self.assertNotIn("infra_docker_registry.yml", addons_validate)
        self.assertNotIn("inventory_bootstrap.yml", addons_validate)
        self.assertIn("namespaces_calico.yml", addons_validate)
        self.assertIn("calico_cluster_network.yml", addons_validate)
        self.assertEqual(_missing_common_includes(ADDONS_REPO), [])


if __name__ == "__main__":
    unittest.main()
