"""Packaging / contributor entry surface (publish step 4)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"
REQUIREMENTS_DEV = ROOT / "requirements-dev.txt"
CLUSTER_WRAPPER = ROOT / "cluster"

_ORG_URL_RE = re.compile(
    r"(?:gitea|harbor|upload|nexus)\.mxhash\.com|Welcomeback\w*|dev-mxhash\.com",
    re.IGNORECASE,
)

_REQUIRED_README_HEADINGS = (
    "## Compatibility",
    "## Quick start",
    "## Sibling playbook repos",
    "## Local labs vs public tree",
    "## Jenkins Pipeline",
    "## Documentation",
    "## Development",
    "## Layout",
    "## Security",
    "## Contributing",
)


class PackagingSurfaceTest(unittest.TestCase):
    def test_requirements_declare_pyyaml(self) -> None:
        self.assertTrue(REQUIREMENTS.is_file(), str(REQUIREMENTS))
        text = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertIn("PyYAML", text)
        self.assertTrue(REQUIREMENTS_DEV.is_file(), str(REQUIREMENTS_DEV))
        dev = REQUIREMENTS_DEV.read_text(encoding="utf-8")
        self.assertIn("requirements.txt", dev)
        self.assertIn("unittest", dev)

    def test_pyproject_metadata_and_script(self) -> None:
        self.assertTrue(PYPROJECT.is_file(), str(PYPROJECT))
        text = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn('name = "atlas-clusterctl"', text)
        self.assertIn("PyYAML", text)
        self.assertIn('requires-python = ">=3.11"', text)
        self.assertIn('cluster = "clusterctl.__main__:main"', text)
        self.assertIn("clusterctl*", text)
        # Packaging Phase 6: no fake forge Documentation URL (and no [project.urls] yet).
        self.assertNotIn("[project.urls]", text)
        self.assertNotIn("Documentation =", text)
        self.assertNotIn("gitea.mxhash.com", text)
        # [dev] must not re-declare runtime PyYAML (empty beyond project.dependencies).
        self.assertIn("[project.optional-dependencies]", text)
        self.assertIn("dev = []", text)
        # Count PyYAML pins: only under [project] dependencies, not duplicated in [dev].
        self.assertEqual(text.count("PyYAML>="), 1)

    def test_cluster_wrapper_sets_atlas_root(self) -> None:
        self.assertTrue(CLUSTER_WRAPPER.is_file())
        self.assertTrue(CLUSTER_WRAPPER.stat().st_mode & 0o111)
        text = CLUSTER_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("ATLAS_CLUSTER_ROOT", text)
        self.assertIn("python3 -m clusterctl", text)

    def test_readme_standalone_first_sections(self) -> None:
        text = README.read_text(encoding="utf-8")
        for heading in _REQUIRED_README_HEADINGS:
            self.assertIn(heading, text, heading)
        # Contract: controller does not vendor playbook roles
        self.assertIn("does **not** ship Ansible roles", text)
        self.assertIn("sibling", text.lower())
        self.assertIn("./cluster", text)
        self.assertIn("requirements.txt", text)
        self.assertIn("./tests/run_ci.sh", text)
        self.assertIn("unittest discover", text)
        # Product narrative must stay org-clean (history lives in SECURITY.md)
        self.assertIsNone(_ORG_URL_RE.search(text), _ORG_URL_RE.findall(text))
        # Prefer clone wrapper over implying pip-only workflow
        self.assertIn("Preferred entrypoint", text)

    def test_ci_surface_files(self) -> None:
        run_ci = ROOT / "tests" / "run_ci.sh"
        hygiene = ROOT / "tests" / "check_publish_hygiene.sh"
        yaml_check = ROOT / "tests" / "check_public_templates_yaml.py"
        audit = ROOT / "tests" / "check_pre_publish_audit.py"
        prepublish = ROOT / "docs" / "pre-publish.md"
        workflow = ROOT / ".github" / "workflows" / "ci.yml"
        for path in (run_ci, hygiene, yaml_check, audit, prepublish, workflow):
            self.assertTrue(path.is_file(), str(path))
        self.assertTrue(run_ci.stat().st_mode & 0o111, "tests/run_ci.sh must be executable")
        self.assertTrue(hygiene.stat().st_mode & 0o111, "hygiene script must be executable")
        self.assertFalse((ROOT / "scripts").exists(), "repo root scripts/ is forbidden")
        self.assertTrue((ROOT / ".config" / "config.yaml.example").is_file())
        example = (ROOT / ".config" / "config.yaml.example").read_text(encoding="utf-8")
        self.assertIn("clusters:", example)
        self.assertIn("workspace:", example)
        self.assertIn("cp .config/config.yaml.example .config/config.yaml", example)
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/.config/config.yaml", gitignore)
        self.assertNotIn("\n/config.yaml\n", f"\n{gitignore}\n")
        wf = workflow.read_text(encoding="utf-8")
        self.assertIn("./tests/run_ci.sh", wf)
        self.assertIn("requirements-dev.txt", wf)
        self.assertIn('python-version: "3.12"', wf)
        run_ci_text = run_ci.read_text(encoding="utf-8")
        self.assertIn("check_pre_publish_audit.py", run_ci_text)
        self.assertIn("clusters/_template/k8s_full", run_ci_text)
        for leaf in ("infra_edge", "jenkins_agent", "kafka", "postgresql", "redis"):
            self.assertIn(leaf, run_ci_text, leaf)
        self.assertIn("pre-publish", prepublish.read_text(encoding="utf-8").lower())

    def test_version_aligned(self) -> None:
        from clusterctl import __version__

        pyproject = PYPROJECT.read_text(encoding="utf-8")
        self.assertIn(f'version = "{__version__}"', pyproject)


if __name__ == "__main__":
    unittest.main()
