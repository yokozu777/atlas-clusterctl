"""Phase 4 gate: ADR 003 — docs + FAIL [cluster_yml_legacy] (soft-compat follow-up)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.context import ClusterContext
from clusterctl.pipeline_fixture import local_playbooks_override_block, seed_org_baseline_fixture
from clusterctl.validate import Severity, format_report_text, validate_cluster

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "003-optional-cluster-yml.md"
CLUSTERS_DOC = ROOT / "docs" / "clusters.md"
STACKS_README = ROOT / "docs" / "stacks" / "README.md"
KAFKA_STACK = ROOT / "docs" / "stacks" / "kafka.md"
VALIDATE = ROOT / "clusterctl" / "validate.py"


class Adr003OptionalClusterYmlPhase4Test(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID", "CLUSTER_WORKSPACE_ID")

    def test_adr_status_phase4_complete(self) -> None:
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("Phase 4 complete", text)
        self.assertIn("Current runtime (Phase 4)", text)
        self.assertIn("FAIL [cluster_yml_legacy]", text)
        self.assertIn(
            "[x] External scripts that `test -f …/cluster.yml` must be updated",
            text,
        )
        self.assertIn("Phases 0–4 — complete", text)

    def test_clusters_md_phase4_runtime(self) -> None:
        text = CLUSTERS_DOC.read_text(encoding="utf-8")
        self.assertIn("Current runtime (Phase 4)", text)
        self.assertIn("FAIL [cluster_yml_legacy]", text)
        self.assertIn("test -f", text)

    def test_stacks_docs_point_at_atlas_overlays(self) -> None:
        stacks = STACKS_README.read_text(encoding="utf-8")
        self.assertIn("adr/003-optional-cluster-yml.md", stacks)
        self.assertIn("no `group_vars/all/cluster.yml`", stacks)
        kafka = KAFKA_STACK.read_text(encoding="utf-8")
        self.assertNotIn("/ `cluster.yml`", kafka)
        self.assertNotIn("/cluster.yml`", kafka)

    def test_validate_emits_cluster_yml_legacy_code(self) -> None:
        text = VALIDATE.read_text(encoding="utf-8")
        self.assertIn('"cluster_yml_legacy"', text)
        self.assertIn("cluster_yml_legacy", text)

    def test_validate_error_format(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        self.addCleanup(lambda: self._restore_env(saved))
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)

        cluster = root / "clusters" / "lab"
        all_dir = cluster / "group_vars" / "all"
        all_dir.mkdir(parents=True)
        (cluster / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab",
                    "inventory": "hosts",
                    "playbooks": local_playbooks_override_block(),
                    "execution": {"mode": "local"},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (cluster / "hosts").write_text(
            "all:\n  children:\n    k8s_masters:\n      hosts:\n        m1: {}\n",
            encoding="utf-8",
        )
        (all_dir / "cluster.yml").write_text(
            "dns_domain_suffix: example.com\n"
            'cluster_domain: "k8s.{{ dns_domain_suffix }}"\n',
            encoding="utf-8",
        )
        (all_dir / "atlas-node-foundation.yml").write_text(
            "# Leaf DNS identity\n"
            "dns_domain_suffix: example.com\n"
            'cluster_domain: "k8s.{{ dns_domain_suffix }}"\n'
            "admin_user: localuser\n",
            encoding="utf-8",
        )
        (root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        seed_org_baseline_fixture(root)
        for repo in (
            "atlas-infra-edge",
            "atlas-compute-provision",
            "atlas-node-foundation",
            "atlas-k8s-core",
        ):
            path = root / repo
            path.mkdir()
            if repo == "atlas-k8s-core":
                (path / "00_controller_tooling").mkdir()
            elif repo == "atlas-node-foundation":
                (path / "roles" / "dummy").mkdir(parents=True)
            else:
                (path / "roles").mkdir()

        os.environ["ATLAS_CLUSTER_ROOT"] = str(root)
        ctx = ClusterContext.load(cluster_id="lab", executor="local")
        report = validate_cluster(ctx, root=root, docker_smoke=False)
        issue = next(i for i in report.issues if i.code == "cluster_yml_legacy")
        self.assertEqual(issue.severity, Severity.ERROR)
        self.assertIn("FAIL [cluster_yml_legacy]", format_report_text(report))

    @staticmethod
    def _restore_env(saved: dict[str, str | None]) -> None:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
