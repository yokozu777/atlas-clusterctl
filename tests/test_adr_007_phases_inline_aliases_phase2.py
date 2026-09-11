"""Phase 2 gate: ADR 007 — public SoT verify-clean (no live phase_aliases:)."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml

from clusterctl.playbooks_config import (
    load_cluster_config_v2_yaml,
    phases_config_to_raw,
)

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "007-phases-inline-aliases.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
ADR_005 = ROOT / "docs" / "adr" / "005-remove-cluster-stacks.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"
CLUSTERS = ROOT / "clusters"

_TEMPLATE_NAMES = (
    "k8s_full",
    "infra_edge",
    "jenkins_agent",
    "postgresql",
    "redis",
    "kafka",
)


def _cluster_yaml_paths() -> list[Path]:
    return sorted(CLUSTERS.rglob("cluster.yaml"))


def _live_phase_aliases_lines(text: str) -> list[int]:
    """Return 1-based line numbers of a live ``phase_aliases:`` YAML key."""
    hits: list[int] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped == "phase_aliases:" or stripped.startswith("phase_aliases:"):
            hits.append(index)
    return hits


class Adr007PhasesInlineAliasesPhase2Test(unittest.TestCase):
    def test_adr_status_phase2(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn("[x] Public tree verify-clean gate (Phase 2)", text)
        self.assertIn(
            "[x] Public templates omit `phase_aliases:` (Phase 1 / Phase 2)",
            text,
        )

    def test_adr_index_phase2(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase2(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("Phase 2", text)
        self.assertIn("verify-clean", text.lower())

    def test_schema_doc_phase2(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("Public `_template/**`", text)

    def test_adr_005_sot_points_at_inline_phases(self) -> None:
        text = ADR_005.read_text(encoding="utf-8")
        self.assertIn("inline in `phases:`", text)
        self.assertIn("ADR 007", text)

    def test_public_cluster_yaml_paths_exist(self) -> None:
        paths = _cluster_yaml_paths()
        self.assertGreaterEqual(len(paths), 7, paths)

    def test_no_live_phase_aliases_key_under_clusters(self) -> None:
        offenders: list[str] = []
        for path in _cluster_yaml_paths():
            text = path.read_text(encoding="utf-8")
            for line_no in _live_phase_aliases_lines(text):
                offenders.append(f"{path.relative_to(ROOT)}:{line_no}")
            data = yaml.safe_load(text) or {}
            if isinstance(data, dict) and "phase_aliases" in data:
                offenders.append(f"{path.relative_to(ROOT)}:parsed-key")
        self.assertEqual(offenders, [], "live phase_aliases under clusters/:\n" + "\n".join(offenders))

    def test_all_public_cluster_yaml_load(self) -> None:
        for path in _cluster_yaml_paths():
            cfg = load_cluster_config_v2_yaml(path)
            if cfg.phases is None:
                continue
            raw = phases_config_to_raw(cfg.phases)
            self.assertNotIn("phase_aliases", raw, path)
            # Leaf templates should expose at least one alias.
            if path.parent.name in _TEMPLATE_NAMES:
                self.assertTrue(cfg.phases.phase_aliases, path)

    def test_template_samples_have_inline_maps(self) -> None:
        for name in _TEMPLATE_NAMES:
            path = CLUSTERS / "_template" / name / "cluster.yaml"
            text = path.read_text(encoding="utf-8")
            self.assertIn("\nphases:\n", text, path)
            self.assertRegex(
                text,
                r"(?m)^- [A-Za-z0-9][A-Za-z0-9._-]*: [A-Za-z0-9].*/",
                msg=f"{path} missing inline alias map items",
            )

    def test_git_grep_no_live_phase_aliases_under_clusters(self) -> None:
        proc = subprocess.run(
            [
                "git",
                "grep",
                "-n",
                "-I",
                "--full-name",
                "-F",
                "phase_aliases:",
                "--",
                "clusters",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        offenders: list[str] = []
        for line in (proc.stdout or "").splitlines():
            # path:lineno:content
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            body = parts[2].lstrip()
            if body.startswith("#"):
                continue
            if body == "phase_aliases:" or body.startswith("phase_aliases:"):
                offenders.append(line)
        self.assertEqual(
            offenders,
            [],
            "live phase_aliases: under clusters/:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
