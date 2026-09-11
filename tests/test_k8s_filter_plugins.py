"""Filter plugin inventory for atlas-k8s-core / atlas-k8s-addons."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIBLING_ROOT = REPO_ROOT.parent

CORE_REPO = SIBLING_ROOT / "atlas-k8s-core"
ADDONS_REPO = SIBLING_ROOT / "atlas-k8s-addons"


def _skip_unless_repo(path: Path) -> None:
    if not path.is_dir():
        raise unittest.SkipTest(f"sibling repo not present: {path}")


def _load_filter_names(plugin_path: Path) -> set[str]:
    spec = importlib.util.spec_from_file_location(plugin_path.stem, plugin_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    filter_module = module.FilterModule()
    return set(filter_module.filters().keys())


def _repo_declared_filters(repo: Path) -> set[str]:
    declared: set[str] = set()
    plugin_dir = repo / "filter_plugins"
    if not plugin_dir.is_dir():
        return declared
    for plugin in sorted(plugin_dir.glob("*.py")):
        declared |= _load_filter_names(plugin)
    return declared


class K8sFilterPluginsTest(unittest.TestCase):
    def test_core_filter_plugins_match_usage(self) -> None:
        _skip_unless_repo(CORE_REPO)
        declared = _repo_declared_filters(CORE_REPO)
        self.assertEqual(
            declared,
            {
                "pkg_repo_uri",
                "containerd_mirror_endpoint",
            },
        )
        hosts_toml = (
            CORE_REPO / "roles/11_k8s_hosts/templates/containerd/hosts.toml.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("containerd_mirror_endpoint", hosts_toml)

    def test_addons_filter_plugins_match_usage(self) -> None:
        _skip_unless_repo(ADDONS_REPO)
        declared = _repo_declared_filters(ADDONS_REPO)
        self.assertEqual(
            declared,
            {
                "helm_chart_version_args",
                "expand_debug_tooling_hosts",
                "helm_repo_client_url",
                "oidc_merge_cluster_config",
                "oidc_cm_has_flags",
                "oidc_pod_has_flags",
            },
        )
        prom = (ADDONS_REPO / "roles/310_prometheus/tasks/main.yaml").read_text(encoding="utf-8")
        self.assertIn("helm_chart_version_args", prom)
        calico = (ADDONS_REPO / "roles/220_calico/tasks/main.yaml").read_text(encoding="utf-8")
        self.assertIn("helm_chart_version_args", calico)
        helm_repo = (
            ADDONS_REPO / "roles/210_helm_bootstrap/tasks/repo.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("helm_repo_client_url", helm_repo)
        debug = (
            ADDONS_REPO / "roles/999_debug_tooling/tasks/resolve_targets.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("expand_debug_tooling_hosts", debug)
        apiserver = (
            ADDONS_REPO / "roles/940_apiserver_oidc/tasks/main.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("oidc_merge_cluster_config", apiserver)
        self.assertIn("oidc_pod_has_flags", apiserver)
        self.assertIn("oidc_cm_has_flags", apiserver)


if __name__ == "__main__":
    unittest.main()
