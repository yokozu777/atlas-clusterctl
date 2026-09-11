"""Phase 1 gate: ADR 007 — engine + public SoT inline phase aliases."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from clusterctl.exceptions import PhaseAliasesRemovedError
from clusterctl.playbooks_config import (
    load_cluster_config_v2_yaml,
    parse_cluster_config_v2_fragment,
)

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "007-phases-inline-aliases.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SCHEMA_DOC = ROOT / "docs" / "cluster-config-v2.md"
EXCEPTIONS = ROOT / "clusterctl" / "exceptions.py"
PLAYBOOKS_CONFIG = ROOT / "clusterctl" / "playbooks_config.py"

_TEMPLATE_NAMES = (
    "k8s_full",
    "infra_edge",
    "jenkins_agent",
    "postgresql",
    "redis",
    "kafka",
)


class Adr007PhasesInlineAliasesPhase1Test(unittest.TestCase):
    def test_adr_status_phase1(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Status:** Accepted (Phase", text)
        self.assertIn("Current runtime (Phase", text)
        self.assertIn(
            "[x] Engine parse/dump/merge rejects top-level `phase_aliases:` (Phase 1)",
            text,
        )
        self.assertIn(
            "[x] User-facing errors/hints point at inline `phases:` (Phase 1)",
            text,
        )
        self.assertIn(
            "[x] Public templates omit `phase_aliases:` (Phase 1 / Phase 2)",
            text,
        )
        self.assertIn("PhaseAliasesRemovedError", text)

    def test_adr_index_phase1(self) -> None:
        text = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("Accepted (Phase", text)

    def test_changelog_phase1(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("Phase 1", text)
        self.assertIn("PhaseAliasesRemovedError", text)

    def test_schema_doc_phase1_live(self) -> None:
        text = SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 007", text)
        self.assertIn("phase_aliases_removed", text)
        self.assertNotIn("Runtime still uses the legacy", text)
        self.assertNotIn("do not rewrite leaves yet", text.lower())

    def test_engine_exports_typed_error(self) -> None:
        text = EXCEPTIONS.read_text(encoding="utf-8")
        self.assertIn("class PhaseAliasesRemovedError", text)
        self.assertIn('code = "phase_aliases_removed"', text)
        cfg_text = PLAYBOOKS_CONFIG.read_text(encoding="utf-8")
        self.assertIn("PhaseAliasesRemovedError", cfg_text)

    def test_top_level_phase_aliases_raises_typed_error(self) -> None:
        with self.assertRaises(PhaseAliasesRemovedError) as ctx:
            parse_cluster_config_v2_fragment(
                {
                    "schema_version": 2,
                    "phases": ["atlas-compute-provision/templates"],
                    "phase_aliases": {
                        "templates": "atlas-compute-provision/templates",
                    },
                }
            )
        self.assertEqual(ctx.exception.code, "phase_aliases_removed")

    def test_public_templates_inline_and_load(self) -> None:
        for name in _TEMPLATE_NAMES:
            path = ROOT / "clusters" / "_template" / name / "cluster.yaml"
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("phase_aliases:", text, path)
            cfg = load_cluster_config_v2_yaml(path)
            assert cfg.phases is not None
            self.assertTrue(cfg.phases.phases, name)
            self.assertTrue(cfg.phases.phase_aliases, name)

    def test_grep_clusters_no_phase_aliases_key(self) -> None:
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
        # Comments may mention the forbidden key; live YAML key must not appear
        # as a document key. Filter comment-only hits.
        offenders = []
        for line in (proc.stdout or "").splitlines():
            if "# " in line.split(":", 2)[-1] or line.rstrip().endswith("#"):
                # crude: allow comment lines
                body = line.split(":", 2)[-1].lstrip()
                if body.startswith("#"):
                    continue
            if ":#" in line.replace(" ", ""):
                continue
            # real key line looks like path:NN:phase_aliases:
            if line.endswith("phase_aliases:") or "phase_aliases:\n" in line + "\n":
                # path:lineno:phase_aliases:
                parts = line.split(":", 2)
                if len(parts) >= 3 and parts[2].strip() == "phase_aliases:":
                    offenders.append(line)
        self.assertEqual(
            offenders,
            [],
            "live phase_aliases: under clusters/:\n" + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
