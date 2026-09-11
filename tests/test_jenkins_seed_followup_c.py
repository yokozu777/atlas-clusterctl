"""Jenkins seed follow-up Phase C: comments, URL form, branch-only refs, Phase 5 status."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "jenkins-seed.md"
JENKINS_DOC = ROOT / "docs" / "jenkins.md"
CHANGELOG = ROOT / "CHANGELOG.md"
SEED_README = ROOT / "examples" / "internal" / "seed" / "README.md"
SEED_JF = ROOT / "examples" / "internal" / "seed" / "Jenkinsfile"
SEED_DSL = ROOT / "examples" / "internal" / "seed" / "seed_deploy_jobs.groovy"
GATE = ROOT / "tests" / "test_jenkins_seed_followup_c.py"

_SCP_STYLE_DEFAULT = re.compile(
    r"defaultValue:\s*'git@[^']+'"
)
_SSH_URL_INVENTORY = "ssh://git@gitea.mxhash.com/root/atlas-inventory.git"
_SSH_URL_CLUSTERCTL = "ssh://git@gitea.mxhash.com/root/atlas-clusterctl.git"


class JenkinsSeedFollowupCTest(unittest.TestCase):
    def test_changelog_phase_c(self) -> None:
        text = CHANGELOG.read_text(encoding="utf-8")
        self.assertIn("Jenkins seed — follow-up Phase C", text)
        self.assertIn("test_jenkins_seed_followup_c.py", text)
        self.assertIn("ssh://git@", text)
        self.assertIn("branch", text.lower())

    def test_seed_comments_phase_complete_ui_sot(self) -> None:
        seed = SEED_JF.read_text(encoding="utf-8")
        self.assertIn("Phase 0–5 done", seed)
        self.assertIn("UI SoT", seed)
        self.assertNotIn("Phase 1 only", seed)
        self.assertNotIn("Until Phase 2", seed)

        dsl = SEED_DSL.read_text(encoding="utf-8")
        self.assertIn("UI SoT", dsl)
        self.assertIn("Phase 0–5", dsl)
        self.assertNotIn("Phase 2 only", dsl)
        self.assertNotIn("Until Phase 2", dsl)

    def test_default_git_urls_unified_ssh(self) -> None:
        seed = SEED_JF.read_text(encoding="utf-8")
        self.assertIn(_SSH_URL_INVENTORY, seed)
        self.assertIn(_SSH_URL_CLUSTERCTL, seed)
        self.assertIsNone(
            _SCP_STYLE_DEFAULT.search(seed),
            "seed defaults must not mix scp-style git@host:path with ssh://",
        )
        # Both inventory defaults (URL + URL_DEFAULT) and clusterctl share ssh://.
        self.assertEqual(seed.count(_SSH_URL_INVENTORY), 2)

    def test_git_ref_branch_only_contract(self) -> None:
        seed = SEED_JF.read_text(encoding="utf-8")
        self.assertIn("not a commit SHA", seed)
        self.assertIn("branch name", seed.lower())

        dsl = SEED_DSL.read_text(encoding="utf-8")
        self.assertIn("not a commit SHA", dsl)
        self.assertIn("--branch", dsl)

        contract = re.sub(r"\s+", " ", CONTRACT.read_text(encoding="utf-8").lower())
        self.assertIn("ssh://git@host/path", contract)
        self.assertIn("branch names", contract)
        self.assertIn("commit shas", contract)

        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("branch name", jenkins.lower())
        self.assertIn("not a commit SHA", jenkins)

        readme = re.sub(r"\s+", " ", SEED_README.read_text(encoding="utf-8").lower())
        self.assertIn("ssh://git@host/path", readme)
        self.assertIn("branch names", readme)

    def test_phase5_offline_done_live_org(self) -> None:
        contract = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("| **Offline** | **Done**", contract)
        self.assertIn("| **Live controller** |", contract)
        self.assertIn("not** exercised by this repo", contract)
        self.assertIn("operator checklist — org-local", contract)
        self.assertIn("does **not** prove live UI", contract)

        jenkins = JENKINS_DOC.read_text(encoding="utf-8")
        self.assertIn("offline done", jenkins.lower())
        self.assertIn("live = org checklist", jenkins.lower())

    def test_gate_file_exists(self) -> None:
        self.assertTrue(GATE.is_file(), GATE)


if __name__ == "__main__":
    unittest.main()
