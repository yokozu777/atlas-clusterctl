"""PR-13: migration sign-off — docs presence and runtime invariants."""

from __future__ import annotations

from tests.lab_support import lab_id_for, lab_path_for, skip_unless_stack, FULL_K8S_INVOCATION_COUNT, assert_known_labs_subset

import re
import subprocess
import sys
import unittest
from pathlib import Path

from clusterctl.cluster_layout import (
    canonical_cluster_id,
    is_deployable_cluster_id,
    list_cluster_ids,
)
from clusterctl.paths import list_deployable_cluster_ids as repo_list_deployable
from clusterctl.legacy_guard import find_legacy_artifacts
from clusterctl.pipeline_fixture import load_org_baseline_cluster_config
from clusterctl.tools.generate_org_cluster_fixture import main as validate_org_fixture


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# Active operator docs — must not instruct v1 runtime.
_STALE_DOC_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\./cluster run --profile\b"), "use --phases instead of --profile"),
    (re.compile(r"\./cluster plan --profile\b"), "use --phases instead of --profile"),
    (re.compile(r"clusterctl/pipeline\.yaml\)[^—\n]*— см"), "pipeline.yaml removed; point to org baseline"),
    (re.compile(r"v1 loader remains"), "v1 loader removed in PR-11"),
    (re.compile(r"role_repos\.defaults\.yaml` —"), "defaults file removed; use org baseline playbooks"),
    (re.compile(r"deprecated shims.*v1/v2 runners"), "playbooks shims removed"),
)

class MigrationSignoffTest(unittest.TestCase):
    def test_docs_index_exists(self) -> None:
        index = DOCS / "README.md"
        self.assertTrue(index.is_file())
        self.assertIn("cluster-config-v2.md", index.read_text(encoding="utf-8"))

    def test_root_readme_points_to_docs(self) -> None:
        readme = ROOT / "README.md"
        self.assertTrue(readme.is_file())
        self.assertIn("docs/README.md", readme.read_text(encoding="utf-8"))

    def test_real_repo_no_legacy_artifacts(self) -> None:
        artifacts = find_legacy_artifacts(ROOT)
        self.assertEqual(artifacts, [], [str(a.path) for a in artifacts])

    def test_org_baseline_metrics(self) -> None:
        config = load_org_baseline_cluster_config(ROOT)
        config.validate()
        self.assertIsNotNone(config.playbooks)
        self.assertIsNotNone(config.phases)
        self.assertEqual(len(config.phases.phases), 4)
        invocations = config.phases.invocation_count(config.playbooks)
        self.assertEqual(invocations, FULL_K8S_INVOCATION_COUNT)

    def test_org_baseline_fixture_tool_passes(self) -> None:
        code = validate_org_fixture()
        self.assertEqual(code, 0)

    def test_deployable_clusters_are_known_labs_subset(self) -> None:
        deployable = repo_list_deployable(ROOT)
        assert_known_labs_subset(self, deployable)

    def test_policy_dirs_not_deployable(self) -> None:
        clusters_root = ROOT / "clusters"
        policy = {
            cluster_id
            for cluster_id in list_cluster_ids(clusters_root)
            if not is_deployable_cluster_id(clusters_root, cluster_id)
        }
        self.assertIn("default/default", policy)
        if (ROOT / "clusters" / "dev" / "default" / "cluster.yaml").is_file():
            self.assertIn("dev/default", policy)
        for cluster_id in policy:
            self.assertFalse(is_deployable_cluster_id(ROOT, cluster_id), cluster_id)

    @skip_unless_stack("k8s")
    def test_cluster_id_aliases_roundtrip_when_present(self) -> None:
        from clusterctl.cluster_layout import register_cluster_id_aliases
        from clusterctl.context import ClusterContext
        import yaml

        lab_id = lab_id_for("k8s")
        leaf = lab_path_for("k8s")
        assert lab_id and leaf
        ClusterContext.load(cluster_id=lab_id)
        aliases: dict[str, str] = {}
        for path in (leaf / "cluster.yaml",):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            raw = data.get("cluster_id_aliases") or {}
            if isinstance(raw, dict):
                aliases.update({str(k): str(v) for k, v in raw.items()})
        # Also accept aliases that already resolve to this lab after load.
        pointing = [alias for alias, target in aliases.items() if target == lab_id]
        if not pointing:
            # Explicit register still works without inventory aliases.
            register_cluster_id_aliases({"fixture-alias.example": lab_id})
            self.assertEqual(canonical_cluster_id("fixture-alias.example"), lab_id)
            return
        for alias in pointing:
            self.assertEqual(canonical_cluster_id(alias), lab_id)
    def test_active_docs_no_stale_v1_runtime_instructions(self) -> None:
        violations: list[str] = []
        for path in sorted(DOCS.rglob("*.md")):
            rel = path.relative_to(DOCS).as_posix()
            text = path.read_text(encoding="utf-8")
            for pattern, hint in _STALE_DOC_PATTERNS:
                if pattern.search(text):
                    violations.append(f"{rel}: {hint} ({pattern.pattern})")
        self.assertEqual(violations, [])

    def test_cluster_help_has_no_profile_flag(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "clusterctl", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("--profile", proc.stdout)

    def test_no_legacy_playbook_repo_references(self) -> None:
        from clusterctl.tools.check_no_legacy_repos import main as check_legacy_repos

        self.assertEqual(check_legacy_repos(), 0)

    def test_removed_modules_not_importable(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            __import__("clusterctl.profiles")
        with self.assertRaises(ModuleNotFoundError):
            __import__("clusterctl.plan")


if __name__ == "__main__":
    unittest.main()
