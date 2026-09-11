"""Contract: local labs stay usable on disk but out of the public git tree."""

from __future__ import annotations

import subprocess
import unittest

from clusterctl.paths import clusters_root, product_clusters_root
from tests.lab_support import ROOT, present_deployable_ids

GITIGNORE = ROOT / ".gitignore"
LOCAL_LABS_DOC = ROOT / "docs" / "local-labs.md"
SECURITY = ROOT / "SECURITY.md"


class LocalLabsContractTest(unittest.TestCase):
    def test_gitignore_excludes_ci_and_dev(self) -> None:
        text = GITIGNORE.read_text(encoding="utf-8")
        self.assertIn("/clusters/ci/", text)
        self.assertIn("/clusters/dev/", text)
        self.assertIn("secrets.yml", text)

    def test_local_labs_doc_operator_runbook(self) -> None:
        self.assertTrue(LOCAL_LABS_DOC.is_file(), str(LOCAL_LABS_DOC))
        text = LOCAL_LABS_DOC.read_text(encoding="utf-8")
        for needle in (
            "config.yaml.example",
            ".config/config.yaml",
            "ATLAS_CLUSTERS_ROOT",
            "ATLAS_WORKSPACE_ROOT",
            "clusters.path",
            "workspace.path",
            "./cluster list",
            "clusters/ci/",
            "clusters/dev/",
            "_template/k8s_full",
            "tests/lab_support.py",
            "lab_id_for",
            "list_deployable",
            "export_template",
            "adr/004-universal-export-template.md",
            "scrub",
            "git check-ignore",
        ):
            self.assertIn(needle, text if needle != "scrub" else text.lower(), needle)
        self.assertNotIn("export_k8s_full_template", text)
        self.assertNotIn("~/.config/atlas-clusterctl", text)
        # Discover-based docs — no fixed path whitelist required.
        self.assertIn("skip_unless_stack", text)

    def test_security_mentions_local_labs(self) -> None:
        text = SECURITY.read_text(encoding="utf-8")
        self.assertIn("clusters/ci/", text)
        self.assertIn("clusters/dev/", text)
        self.assertIn("gitignored", text.lower())

    def test_no_labs_tracked_in_git_index(self) -> None:
        proc = subprocess.run(
            ["git", "ls-files", "clusters/ci", "clusters/dev"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        tracked = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(tracked, [], tracked)

    def test_present_labs_are_ignored_and_listed(self) -> None:
        deployable = present_deployable_ids()
        if not deployable:
            self.skipTest("no local labs on disk (public CI)")

        inv = clusters_root().resolve()
        product = product_clusters_root(ROOT).resolve()
        in_product_tree = inv == product

        for cluster_id in deployable:
            self.assertRegex(
                cluster_id,
                r"^[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_-]*$",
                cluster_id,
            )
            leaf = inv.joinpath(*cluster_id.split("/")) / "cluster.yaml"
            self.assertTrue(leaf.is_file(), leaf)
            if not in_product_tree:
                # Private inventory checkout — product .gitignore does not apply.
                continue
            rel = f"clusters/{cluster_id}/cluster.yaml"
            proc = subprocess.run(
                ["git", "check-ignore", "-v", rel],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, f"{rel} should be ignored: {proc.stderr}")
            self.assertIn(".gitignore", proc.stdout)


if __name__ == "__main__":
    unittest.main()
