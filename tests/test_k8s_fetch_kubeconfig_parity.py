"""140_fetch_kubeconfig fetch logic must stay in sync with atlas-k8s-core 29_fetch_kubeconfig."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIBLING_ROOT = REPO_ROOT.parent

CORE_REPO = SIBLING_ROOT / "atlas-k8s-core"
ADDONS_REPO = SIBLING_ROOT / "atlas-k8s-addons"

_SYNC_MARKER = "Keep 140_fetch_kubeconfig tasks/fetch.yaml and templates/fetch_admin_kubeconfig.sh.j2"

_CORE_FETCH_TASKS = CORE_REPO / "roles/29_fetch_kubeconfig/tasks/main.yaml"
_ADDONS_FETCH_TASKS = ADDONS_REPO / "roles/140_fetch_kubeconfig/tasks/fetch.yaml"
_CORE_TEMPLATE = CORE_REPO / "roles/29_fetch_kubeconfig/templates/fetch_admin_kubeconfig.sh.j2"
_ADDONS_TEMPLATE = ADDONS_REPO / "roles/140_fetch_kubeconfig/templates/fetch_admin_kubeconfig.sh.j2"
_ADDONS_MAIN = ADDONS_REPO / "roles/140_fetch_kubeconfig/tasks/main.yaml"


def _skip_unless_repo(path: Path) -> None:
    if not path.is_dir():
        raise unittest.SkipTest(f"sibling repo not present: {path}")


class K8sFetchKubeconfigParityTest(unittest.TestCase):
    def test_fetch_tasks_match_core_role(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        self.assertTrue(_CORE_FETCH_TASKS.is_file(), str(_CORE_FETCH_TASKS))
        self.assertTrue(_ADDONS_FETCH_TASKS.is_file(), str(_ADDONS_FETCH_TASKS))
        self.assertEqual(
            _CORE_FETCH_TASKS.read_text(encoding="utf-8"),
            _ADDONS_FETCH_TASKS.read_text(encoding="utf-8"),
        )

    def test_fetch_template_matches_core_role(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        self.assertTrue(_CORE_TEMPLATE.is_file(), str(_CORE_TEMPLATE))
        self.assertTrue(_ADDONS_TEMPLATE.is_file(), str(_ADDONS_TEMPLATE))
        self.assertEqual(
            _CORE_TEMPLATE.read_text(encoding="utf-8"),
            _ADDONS_TEMPLATE.read_text(encoding="utf-8"),
        )

    def test_addons_defaults_document_sync(self) -> None:
        _skip_unless_repo(ADDONS_REPO)
        defaults = (
            ADDONS_REPO / "roles/140_fetch_kubeconfig/defaults/main.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(_SYNC_MARKER, defaults)

    def test_addons_wrapper_skips_when_kubeconfig_present(self) -> None:
        _skip_unless_repo(ADDONS_REPO)
        main = _ADDONS_MAIN.read_text(encoding="utf-8")
        self.assertIn("import_tasks: fetch.yaml", main)
        self.assertIn("k8s_fetch_kubeconfig_needed", main)
        self.assertIn("when: k8s_fetch_kubeconfig_needed | bool", main)
        self.assertIn("when: not k8s_fetch_kubeconfig_needed | bool", main)

    def test_helm_bootstrap_imports_fetch_role(self) -> None:
        _skip_unless_repo(ADDONS_REPO)
        helm_main = (
            ADDONS_REPO / "roles/210_helm_bootstrap/tasks/main.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("import_role:", helm_main)
        self.assertIn("name: 140_fetch_kubeconfig", helm_main)


if __name__ == "__main__":
    unittest.main()
