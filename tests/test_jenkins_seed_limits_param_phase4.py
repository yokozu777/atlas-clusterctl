"""Jenkins seed LIMIT follow-up Phase 4: operator docs / troubleshooting."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
CHANGELOG = ROOT / "CHANGELOG.md"
ADR011 = ROOT / "docs" / "adr" / "011-jenkins-limits-active-choices.md"
ADR_INDEX = ROOT / "docs" / "adr" / "README.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
GATE = ROOT / "tests" / "test_jenkins_seed_limits_param_phase4.py"


class JenkinsSeedLimitsParamPhase4Test(unittest.TestCase):
    def test_contract_phase4_done(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertTrue(
            "Phase 0–4 done" in text
            or "LIMIT follow-up Phase 0–4 done" in text
            or "LIMIT follow-up Phase 0–5 done" in text
            or "Phase 0–5 done" in text
            or "jenkins.md + seed README crisp — **done**" in text,
            "contract banner / plan must mark Phase 4 complete",
        )
        self.assertIn(
            "jenkins.md + seed README crisp — **done**",
            text,
        )
        self.assertIn("### Phase 4 artifacts (`LIMIT` follow-up)", text)
        self.assertIn("#### Operator notes (`LIMIT`)", text)
        self.assertIn(
            "[x] Phase 4 — operator docs / troubleshooting "
            "(`tests/test_jenkins_seed_limits_param_phase4.py`)",
            text,
        )
        self.assertIn("test_jenkins_seed_limits_param_phase4.py", text)
        # Core operator themes from ADR 011 Phase 4.
        self.assertIn("host keys", text.lower())
        self.assertIn("empty checkbox", text.lower())
        self.assertTrue(
            "re-run seed" in text.lower() or "re-seed" in text.lower(),
            "contract must tell operators when to re-run seed",
        )
        self.assertIn("IP", text)
        self.assertIn("hostname:", text)

    def test_adr_phase4_done(self) -> None:
        text = ADR011.read_text(encoding="utf-8")
        self.assertTrue(
            "Phase 0–4" in text or "Phase 0–5" in text,
            "ADR status must mark Phase 4 complete",
        )
        self.assertIn("test_jenkins_seed_limits_param_phase4.py", text)
        self.assertIn("[x] Phase 4 operator docs", text)
        self.assertTrue(
            "[ ] Phase 5 acceptance" in text or "[x] Phase 5 acceptance" in text,
            "ADR must track Phase 5 acceptance",
        )
        self.assertIn("IP keys", text)
        index = ADR_INDEX.read_text(encoding="utf-8")
        self.assertIn("011-jenkins-limits-active-choices.md", index)
        self.assertTrue(
            "Phase 0–4" in index or "Phase 0–5" in index,
            "ADR index must mark Phase 4+",
        )

    def test_changelog_phase4(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — LIMIT follow-up Phase 4", text)
        self.assertIn("test_jenkins_seed_limits_param_phase4.py", text)
        self.assertIn("jenkins.md", text)
        self.assertTrue(
            "host-key" in text.lower()
            or "host key" in text.lower()
            or "IP keys" in text
            or "empty UI" in text.lower(),
            "changelog must mention host-key / IP / empty-UI operator theme",
        )

    def test_jenkins_md_operator_notes(self) -> None:
        text = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("ADR 011", text)
        self.assertIn("uno-choice", text)
        self.assertIn("hosts", text.lower())
        self.assertIn("host keys", text.lower())
        self.assertIn("hostname:", text)
        self.assertIn("cluster-limits.json", text)
        # Re-seed guidance for LIMIT catalog.
        self.assertTrue(
            "hosts` / groups" in text
            or "hosts/groups" in text
            or "`hosts`/groups" in text
            or "hosts / groups" in text,
            "jenkins.md must say re-run seed after hosts/groups changes",
        )
        self.assertTrue(
            "Phase 0–4 delivered" in text or "Phase 0–5 delivered" in text,
            "jenkins.md must mark LIMIT cascade delivered through Phase 4+",
        )
        # Script Approval wording: seed-time JsonSlurper, not form-render.
        self.assertIn("switch", text.lower())
        self.assertIn("form-render", text.lower())

    def test_seed_readme_troubleshooting(self) -> None:
        text = SEED_README.read_text(encoding="utf-8")
        self.assertIn("LIMIT` follow-up Phase 4", text)
        self.assertIn("list_cluster_limits", text)
        self.assertIn("host keys", text.lower())
        self.assertIn("hostname:", text)
        self.assertIn("cluster-limits.json", text)
        self.assertIn("without limits catalog", text)
        self.assertIn("IP", text)
        self.assertTrue(
            "ADR 011" in text and "uno-choice" in text,
            "seed README must keep Active Choices / ADR 011 pointers",
        )
        # Advanced patterns still documented.
        self.assertTrue("&" in text or "`&`" in text)
        self.assertIn("LIMIT` follow-up Phase 3", text)

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
