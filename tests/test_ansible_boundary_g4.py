"""Tests for PR-G4: ansible env via inline phase aliases → repo/entry (no PHASE_TO_LOGICAL)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.ansible_config import resolve_boundary_entry
from clusterctl.ansible_env import export_phase
from clusterctl.config_cmd import build_config_show_report
from clusterctl.exceptions import ClusterctlError
from clusterctl.pipeline_fixture import local_playbooks_override_block, seed_org_baseline_fixture
from clusterctl.playbooks_resolve import effective_playbooks_config


class AnsibleBoundaryG4Test(unittest.TestCase):
    _ISOLATED_ENV_KEYS = ("ATLAS_CLUSTER_ROOT", "CLUSTER_ID")

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self._saved = {k: os.environ.get(k) for k in self._ISOLATED_ENV_KEYS}
        for key in self._ISOLATED_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["ATLAS_CLUSTER_ROOT"] = str(self.root)
        self._seed_cluster()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _seed_cluster(self) -> None:
        (self.root / "ansible.cfg").write_text("[defaults]\n", encoding="utf-8")
        seed_org_baseline_fixture(self.root)
        cluster = self.root / "clusters" / "lab"
        cluster.mkdir(parents=True)
        (cluster / "cluster.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "id": "lab",
                    "inventory": "hosts",
                    "playbooks": local_playbooks_override_block(
                        "atlas-k8s-core",
                        "atlas-k8s-addons",
                    ),
                    "execution": {"mode": "local"},
                }
            ),
            encoding="utf-8",
        )
        (cluster / "hosts").write_text("all:\n  hosts:\n    localhost:\n", encoding="utf-8")
        gv = cluster / "group_vars" / "all"
        gv.mkdir(parents=True)
        (gv / "cluster.yml").write_text(
            yaml.safe_dump(
                {
                    "cluster_id": "lab",
                    "dns_domain_suffix": "example.com",
                    "cluster_domain": "k8s.example.com",
                }
            ),
            encoding="utf-8",
        )
        from clusterctl.pipeline_fixture import seed_local_playbook_repo_stubs
        seed_local_playbook_repo_stubs(self.root)

    def test_export_by_alias_and_phase_ref_match(self) -> None:
        by_alias = export_phase("k8s-core", cluster_id="lab")
        by_ref = export_phase("atlas-k8s-core/cluster", cluster_id="lab")
        self.assertEqual(by_alias, by_ref)

    def test_config_show_accepts_phase_ref(self) -> None:
        from clusterctl.context import ClusterContext

        ctx = ClusterContext.load(cluster_id="lab")
        report = build_config_show_report(ctx, "atlas-k8s-core/cluster")
        self.assertEqual(report.phase_ref, "atlas-k8s-core/cluster")
        self.assertTrue(any("atlas-k8s-core/cluster" in line for line in report.ansible_lines))

    def test_fifth_repo_boundary_without_python_table(self) -> None:
        from clusterctl.context import ClusterContext

        path = self.root / "clusters" / "default" / "default" / "cluster.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        data["playbooks"]["rare-stack"] = {
            "source": "git",
            "url": "git@example.com/org/rare-stack.git",
            "ref": "main",
            "layout": "roles/",
            "entries": {
                "install": {
                    "file": "playbooks/install.yaml",
                    "invocations": [{"tags": "all"}],
                    "ansible": {"strategy": "free", "forks": 5},
                }
            },
        }
        data["phases"].append({"rare": "rare-stack/install"})
        path.write_text(yaml.safe_dump(data), encoding="utf-8")

        ctx = ClusterContext.load(cluster_id="lab")
        playbooks = effective_playbooks_config(ctx)
        assert ctx.config_v2 is not None and ctx.config_v2.phases is not None
        phase_ref, _, entry = resolve_boundary_entry("rare", playbooks, ctx.config_v2.phases)
        self.assertEqual(phase_ref, "rare-stack/install")
        self.assertEqual(entry.ansible.strategy, "free")
        self.assertEqual(entry.ansible.forks, 5)

    def test_unknown_boundary_raises(self) -> None:
        from clusterctl.context import ClusterContext

        ctx = ClusterContext.load(cluster_id="lab")
        playbooks = effective_playbooks_config(ctx)
        assert ctx.config_v2 is not None and ctx.config_v2.phases is not None
        with self.assertRaises(ClusterctlError):
            resolve_boundary_entry("missing-alias", playbooks, ctx.config_v2.phases)


if __name__ == "__main__":
    unittest.main()
