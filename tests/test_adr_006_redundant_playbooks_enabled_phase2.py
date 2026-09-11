"""Phase 2 gate: ADR 006 — public templates/org baseline omit redundant true."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "006-redundant-playbooks-enabled.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"

_TEMPLATE_NAMES = (
    "k8s_full",
    "infra_edge",
    "jenkins_agent",
    "postgresql",
    "redis",
    "kafka",
    "pve_templates",
)


class Adr006RedundantPlaybooksEnabledPhase2Test(unittest.TestCase):
    def test_adr_status_phase2(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn(
            "[x] Public templates omit redundant `playbooks_enabled: true`",
            text,
        )
        self.assertIn("[x] Org baseline omits redundant `true`", text)
        self.assertIn("[x] Inventory labs omit redundant `true`", text)

    def test_adr_index_phase2(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 006", text)
        self.assertIn("Phase 2", text)
        self.assertIn("_template", text)

    def test_schema_doc_notes_phase2_public_omit(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 006", text)
        self.assertIn("Public templates omit redundant", text)

    def test_public_templates_omit_playbooks_enabled_true(self) -> None:
        parent = ROOT / "clusters" / "_template" / "cluster.yaml"
        self.assertNotIn(
            "playbooks_enabled: true",
            parent.read_text(encoding="utf-8"),
        )
        for name in _TEMPLATE_NAMES:
            path = ROOT / "clusters" / "_template" / name / "cluster.yaml"
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("playbooks_enabled: true", text, path)
            # Still a playbooks catalog so infer stays enabled.
            self.assertIn("\nplaybooks:", text, path)

    def test_org_baseline_omits_playbooks_enabled_true(self) -> None:
        path = ROOT / "clusters" / "default" / "default" / "cluster.yaml"
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("playbooks_enabled: true", text)
        self.assertIn("id: default/default", text)

    def test_grep_clusters_no_playbooks_enabled_true(self) -> None:
        """No live ``playbooks_enabled: true`` under public clusters/."""
        proc = subprocess.run(
            [
                "git",
                "grep",
                "-n",
                "-I",
                "--full-name",
                "-F",
                "playbooks_enabled: true",
                "--",
                "clusters",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            1,
            "playbooks_enabled: true still under clusters/:\n" + proc.stdout,
        )

    def test_public_template_infers_enabled(self) -> None:
        from clusterctl.playbooks_config import load_cluster_config_v2_yaml

        path = ROOT / "clusters" / "_template" / "k8s_full" / "cluster.yaml"
        cfg = load_cluster_config_v2_yaml(path)
        self.assertIsNone(cfg.playbooks_enabled)
        self.assertTrue(cfg.effective_playbooks_enabled())
        self.assertTrue(cfg.playbooks and cfg.playbooks.repos)


if __name__ == "__main__":
    unittest.main()
