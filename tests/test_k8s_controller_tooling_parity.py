"""Controller tooling must stay identical across atlas-k8s-core and atlas-k8s-addons."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIBLING_ROOT = REPO_ROOT.parent

CORE_REPO = SIBLING_ROOT / "atlas-k8s-core"
ADDONS_REPO = SIBLING_ROOT / "atlas-k8s-addons"

_SYNC_MARKER = "Keep task files in sync with sibling"

_TASK_FILES = (
    "tasks/main.yaml",
    "tasks/install_controller_ca.yaml",
    "tasks/detect_controller_os.yaml",
)


def _skip_unless_repo(path: Path) -> None:
    if not path.is_dir():
        raise unittest.SkipTest(f"sibling repo not present: {path}")


class K8sControllerToolingParityTest(unittest.TestCase):
    def test_task_files_match_between_repos(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        for rel in _TASK_FILES:
            core_path = CORE_REPO / "roles/00_controller_tooling" / rel
            addons_path = ADDONS_REPO / "roles/120_controller_tooling" / rel
            self.assertTrue(core_path.is_file(), str(core_path))
            self.assertTrue(addons_path.is_file(), str(addons_path))
            self.assertEqual(
                core_path.read_text(encoding="utf-8"),
                addons_path.read_text(encoding="utf-8"),
                rel,
            )

    def test_defaults_document_sync(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        for repo, role in (
            (CORE_REPO, "00_controller_tooling"),
            (ADDONS_REPO, "120_controller_tooling"),
        ):
            defaults = (
                repo / "roles" / role / "defaults/main.yml"
            ).read_text(encoding="utf-8")
            self.assertIn(_SYNC_MARKER, defaults, str(repo))
            self.assertIn("controller_ssl_cert_file:", defaults, str(repo))
            self.assertIn("controller_tls_environment:", defaults, str(repo))

    def test_install_controller_ca_runs_when_pki_ca_url_set(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        for repo, role in (
            (CORE_REPO, "00_controller_tooling"),
            (ADDONS_REPO, "120_controller_tooling"),
        ):
            main = (
                repo / "roles" / role / "tasks/main.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("install_controller_ca.yaml", main)
            self.assertIn("when: pki_ca_url | default('') | length > 0", main)

    def test_os_package_install_uses_os_venv_capability(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        for repo, role in (
            (CORE_REPO, "00_controller_tooling"),
            (ADDONS_REPO, "120_controller_tooling"),
        ):
            main = (
                repo / "roles" / role / "tasks/main.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("controller_os_venv_capable", main)
            self.assertIn("controller_uid", main)
            self.assertIn(
                "Create controller Python virtual environment with virtualenv",
                main,
            )
            self.assertIn(
                "when: controller_virtualenv_bin.rc | default(1) | int == 0",
                main,
            )
            self.assertNotIn(
                "Create controller Python virtual environment on Alpine",
                main,
            )
            install_whens = [
                block
                for block in main.split("- name: Install controller tooling packages")
                if "become: true" in block
            ]
            self.assertEqual(len(install_whens), 4, str(repo))
            for block in install_whens:
                self.assertIn("controller_os_venv_capable", block)
                self.assertNotIn("controller_venv_probe", block)
            self.assertIn("python3-virtualenv", main)
            self.assertIn(
                "Fail when OS still cannot create a virtualenv after package install",
                main,
            )
            self.assertIn(
                "- controller_python_venv_mod.rc | default(1) | int == 0",
                main,
            )

    def test_ca_merge_bundle_and_root_system_store(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        for repo, role in (
            (CORE_REPO, "00_controller_tooling"),
            (ADDONS_REPO, "120_controller_tooling"),
        ):
            ca = (
                repo / "roles" / role / "tasks/install_controller_ca.yaml"
            ).read_text(encoding="utf-8")
            self.assertIn("ca-bundle.crt", ca)
            self.assertIn("index_var: idx", ca)
            self.assertIn("controller_uid | int == 0", ca)
            self.assertIn("controller_ca_cert_dir }}/org", ca)
            self.assertIn("changed_when: controller_ca_download is changed", ca)
            self.assertIn("state: absent", ca)
            self.assertIn("controller_ca_download.results[0].dest", ca)
            self.assertNotIn(
                "Fail when controller OS is unsupported for PKI system-store",
                ca,
            )
            self.assertNotIn("controller_tls_environment:", ca)

    def test_playbooks_pass_tls_environment_on_localhost(self) -> None:
        _skip_unless_repo(CORE_REPO)
        _skip_unless_repo(ADDONS_REPO)
        core_pb = (CORE_REPO / "playbooks/cluster_core.yaml").read_text(encoding="utf-8")
        addons_pb = (ADDONS_REPO / "playbooks/cluster_addons.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'environment: "{{ controller_tls_environment | default({}) }}"',
            core_pb,
        )
        self.assertIn("controller_tls_environment", addons_pb)
        self.assertNotIn(
            'SSL_CERT_FILE: "{{ controller_ca_cert_path }}"',
            addons_pb,
        )

    def test_k8s_full_template_has_tls_extra_var_stubs(self) -> None:
        template = (
            REPO_ROOT
            / "clusters/_template/k8s_full/group_vars/all/atlas-k8s-core.yml"
        )
        text = template.read_text(encoding="utf-8")
        self.assertIn("controller_ssl_cert_file:", text)
        self.assertIn("controller_tls_environment:", text)

    def test_helm_bootstrap_defines_tls_and_kube_env(self) -> None:
        _skip_unless_repo(ADDONS_REPO)
        defaults = (
            ADDONS_REPO / "roles/210_helm_bootstrap/defaults/main.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("controller_tls_environment:", defaults)
        self.assertIn("_helm_kube_env:", defaults)
        self.assertIn("_helm_client_env:", defaults)


if __name__ == "__main__":
    unittest.main()
