"""Phase 6 gate: packaging polish (URLs, [dev], legacy API deprecations)."""

from __future__ import annotations

import os
import tempfile
import unittest
import warnings
from pathlib import Path

import yaml

from clusterctl.cluster_vars_loader import (
    optional_cluster_var_file,
    primary_cluster_var_file,
)
from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import seed_org_baseline_fixture

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
REPORT = ROOT / "notes" / "report_clusterctl.md"
README = ROOT / "README.md"


class PackagingPhase6Test(unittest.TestCase):
    def test_pyproject_has_no_placeholder_urls(self) -> None:
        text = PYPROJECT.read_text(encoding="utf-8")
        self.assertNotIn("[project.urls]", text)
        self.assertNotIn("Documentation =", text)
        self.assertNotIn("gitea.mxhash.com", text)
        self.assertIn("dev = []", text)
        self.assertEqual(text.count("PyYAML>="), 1)
        self.assertIn("pre-publish.md", text)

    def test_changelog_and_readme_phase6(self) -> None:
        changelog = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("packaging Phase 6", changelog)
        self.assertIn("optional-dependencies.dev", changelog)
        readme = README.read_text(encoding="utf-8")
        self.assertIn('pip install -e ".[dev]"', readme)
        self.assertIn("pip install -e .", readme)

    def test_report_synced_with_playbooks_repos(self) -> None:
        text = REPORT.read_text(encoding="utf-8")
        self.assertIn("playbooks_repos", text)
        self.assertIn("Фаза 6", text)
        self.assertIn("packaging", text.lower())

    def test_primary_cluster_var_file_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            all_dir = root / "group_vars" / "all"
            all_dir.mkdir(parents=True)
            self.assertIsNone(optional_cluster_var_file(root))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", DeprecationWarning)
                self.assertIsNone(primary_cluster_var_file(root))
            self.assertTrue(
                any("optional_cluster_var_file" in str(w.message) for w in caught),
                [str(w.message) for w in caught],
            )

    def test_context_default_profile_warns_and_aliases_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = {
                k: os.environ.get(k)
                for k in ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "CLUSTER_WORKSPACE_ID")
            }
            try:
                for key in saved:
                    os.environ.pop(key, None)
                os.environ["ATLAS_CLUSTER_ROOT"] = str(root)
                seed_org_baseline_fixture(root)
                leaf = root / "clusters" / "lab" / "pack6"
                leaf.mkdir(parents=True)
                (leaf / "hosts").write_text(
                    "all:\n  hosts:\n    localhost:\n", encoding="utf-8"
                )
                (leaf / "pub_keys").mkdir()
                (leaf / "pub_keys" / "localuser.pub").write_text("ssh-rsa t\n")
                gv = leaf / "group_vars" / "all"
                gv.mkdir(parents=True)
                (gv / "atlas-node-foundation.yml").write_text(
                    "dns_domain_suffix: example.com\ncluster_domain: k8s.example.com\n",
                    encoding="utf-8",
                )
                (leaf / "cluster.yaml").write_text(
                    yaml.safe_dump(
                        {
                            "schema_version": 2,
                            "id": "lab/pack6",
                            "inventory": "hosts",
                        },
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                ctx = ClusterContext.load(cluster_id="lab/pack6")
                self.assertIsNone(ctx.legacy_profile)
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always", DeprecationWarning)
                    self.assertIsNone(ctx.default_profile)
                self.assertTrue(
                    any("legacy_profile" in str(w.message) for w in caught),
                    [str(w.message) for w in caught],
                )
            finally:
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
