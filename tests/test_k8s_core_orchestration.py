"""Orchestration contract for atlas-k8s-core via clusterctl.

SoT: ``_template/k8s_full``. Optional local lab: discovered via ``lab_id_for('k8s')`` (see docs/local-labs.md).
"""

from __future__ import annotations

import os
import unittest

import yaml

from clusterctl.context import ClusterContext
from clusterctl.inventory import extract_inventory_groups
from clusterctl.pipeline_fixture import load_public_reference_cluster_config
from tests.lab_support import (
    lab_id_for,
    lab_path_for,
    skip_unless_stack,

    group_vars_all_file,
    PUBLIC_K8S_TEMPLATE,
    ROOT,
)

STACK = "k8s"
TEMPLATE = PUBLIC_K8S_TEMPLATE

EXPECTED_CORE_TAGS = (
    "00_ensure_workspace",
    "00_controller_tooling",
    "01_validate_vars",
    "02_gather_facts",
    "03_sync_time",
    "09_lb_vip_dns",
    "10_lb",
    "11_k8s_hosts",
    # 04_cluster_state co-tagged with each lifecycle gate (same ansible-playbook process).
    "04_cluster_state,21_kubeadm_init",
    "04_cluster_state,22_cluster_join_token",
    "29_fetch_kubeconfig",
    "04_cluster_state,23_join_masters",
    "04_cluster_state,24_join_workers,12_workers_kernel_rbd",
    "04_cluster_state,25_kubeadm_upgrade_control_plane",
    "04_cluster_state,26_kubeadm_upgrade_workers",
)


class K8sCoreOrchestrationTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import list_deployable_cluster_ids, repo_root

        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    def test_phases_include_k8s_core(self) -> None:
        config = load_public_reference_cluster_config(ROOT)
        assert config.phases is not None
        phases = config.phases.phases
        self.assertIn("atlas-k8s-core/cluster", phases)
        self.assertIn("atlas-k8s-addons/addons", phases)
        self.assertLess(
            phases.index("atlas-k8s-core/cluster"),
            phases.index("atlas-k8s-addons/addons"),
        )
        aliases = config.phases.phase_aliases
        self.assertEqual(aliases.get("k8s-core"), "atlas-k8s-core/cluster")

    def test_playbooks_include_atlas_k8s_core(self) -> None:
        config = load_public_reference_cluster_config(ROOT)
        assert config.playbooks is not None
        self.assertIn("atlas-k8s-core", config.playbooks.repos)
        entry = config.playbooks.repos["atlas-k8s-core"].entries["cluster"]
        self.assertEqual(entry.file, "playbooks/cluster_core.yaml")
        tags = [inv.tags for inv in entry.invocations]
        for tag in EXPECTED_CORE_TAGS:
            self.assertIn(tag, tags)
        self.assertLess(
            tags.index("04_cluster_state,22_cluster_join_token"),
            tags.index("29_fetch_kubeconfig"),
        )
        self.assertLess(
            tags.index("29_fetch_kubeconfig"),
            tags.index("04_cluster_state,23_join_masters"),
        )

    def test_atlas_k8s_core_targeting(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        leaves = [TEMPLATE]
        if lab:
            leaves.append(path)
        for leaf in leaves:
            text = (leaf / "group_vars" / "all" / "atlas-k8s-core.yml").read_text(encoding="utf-8")
            self.assertIn("k8s_lb_hosts: k8s_lbs", text, leaf)
            self.assertIn("k8s_master_hosts: k8s_masters", text, leaf)
            self.assertIn("k8s_worker_hosts: k8s_workers", text, leaf)
            self.assertIn("groups.get(k8s_master_hosts", text, leaf)
            self.assertIn("docs/stacks/k8s-core.md", text, leaf)

    def test_init_targets_k8s_groups(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        leaves = [TEMPLATE]
        if lab:
            leaves.append(path)
        for leaf in leaves:
            text = group_vars_all_file(leaf, "atlas-node-foundation.yml").read_text(encoding="utf-8")
            self.assertIn("k8s_lbs:k8s_masters:k8s_workers", text, leaf)
            self.assertIn("docs/stacks/k8s-core.md", text, leaf)

    def test_inventory_has_k8s_groups(self) -> None:
        groups = extract_inventory_groups(TEMPLATE / "hosts")
        for name in ("k8s_lbs", "k8s_masters", "k8s_workers"):
            self.assertIn(name, groups)

    @skip_unless_stack(STACK)
    def test_lab_inventory_has_k8s_groups(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        groups = extract_inventory_groups(path / "hosts")
        for name in ("k8s_lbs", "k8s_masters", "k8s_workers"):
            self.assertIn(name, groups)

    def test_template_invocation_limits_aligned(self) -> None:
        expected_limits = {
            "02_gather_facts": "k8s_lbs:k8s_masters:k8s_workers",
            "03_sync_time": "k8s_lbs:k8s_masters:k8s_workers",
            "10_lb": "k8s_lbs",
            "11_k8s_hosts": "k8s_masters:k8s_workers",
            "04_cluster_state,21_kubeadm_init": "k8s_masters",
            "04_cluster_state,23_join_masters": "k8s_masters",
            "04_cluster_state,24_join_workers,12_workers_kernel_rbd": "k8s_workers",
            "04_cluster_state,25_kubeadm_upgrade_control_plane": "k8s_masters",
            "04_cluster_state,26_kubeadm_upgrade_workers": "k8s_workers",
        }
        path = TEMPLATE / "cluster.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        inv = data["playbooks"]["atlas-k8s-core"]["entries"]["cluster"]["invocations"]
        tags = [item["tags"] for item in inv]
        for tag in EXPECTED_CORE_TAGS:
            self.assertIn(tag, tags, path)
        limits = {item["tags"]: item.get("limit") for item in inv}
        for tag, limit in expected_limits.items():
            self.assertEqual(limits[tag], limit, f"{path}: {tag}")
        for tag in (
            "00_ensure_workspace",
            "00_controller_tooling",
            "01_validate_vars",
            "09_lb_vip_dns",
            "04_cluster_state,22_cluster_join_token",
            "29_fetch_kubeconfig",
        ):
            self.assertIsNone(limits.get(tag), f"{path}: {tag} must not set limit")
        # No standalone 04 — lifecycle facts must be probed in-process with each gate.
        self.assertNotIn("04_cluster_state", tags, path)
        for tag in tags:
            if "21_kubeadm_init" in tag or "22_cluster_join_token" in tag:
                self.assertTrue(
                    tag.startswith("04_cluster_state,"),
                    f"{path}: {tag} must co-tag 04_cluster_state",
                )
            if tag.startswith("04_cluster_state,23_") or tag.startswith("04_cluster_state,24_"):
                self.assertIn("04_cluster_state,", tag)
            if "25_kubeadm_upgrade" in tag or "26_kubeadm_upgrade" in tag:
                self.assertTrue(
                    tag.startswith("04_cluster_state,"),
                    f"{path}: {tag} must co-tag 04_cluster_state",
                )

    @skip_unless_stack(STACK)
    def test_lab_invocations_match_template(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        template_inv = yaml.safe_load(
            (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        )["playbooks"]["atlas-k8s-core"]["entries"]["cluster"]["invocations"]
        lab_inv = yaml.safe_load(
            (path / "cluster.yaml").read_text(encoding="utf-8")
        )["playbooks"]["atlas-k8s-core"]["entries"]["cluster"]["invocations"]
        self.assertEqual(
            [(i.get("tags"), i.get("limit")) for i in template_inv],
            [(i.get("tags"), i.get("limit")) for i in lab_inv],
        )
        for inv in (template_inv, lab_inv):
            tags = [item["tags"] for item in inv]
            for tag in EXPECTED_CORE_TAGS:
                self.assertIn(tag, tags)

    def test_k8s_full_template_exists(self) -> None:
        self.assertTrue(TEMPLATE.is_dir())
        self.assertTrue((TEMPLATE / "group_vars" / "all" / "atlas-k8s-core.yml").is_file())
        self.assertFalse((TEMPLATE / "group_vars" / "all" / "cluster.yml").exists())
        content = (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas-k8s-core", content)
        self.assertIn("k8s-core: atlas-k8s-core/cluster", content)

    def test_orchestration_docs_and_readme_links(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        docs = (ROOT / "docs" / "stacks" / "k8s-core.md").read_text(encoding="utf-8")
        self.assertIn("k8s_lb_hosts", docs)
        self.assertIn("k8s_master_hosts", docs)
        self.assertIn("k8s_worker_hosts", docs)
        self.assertIn("00_ensure_workspace", docs)
        self.assertIn("29_fetch_kubeconfig", docs)
        self.assertIn("04_cluster_state,21_kubeadm_init", docs)
        self.assertIn("co-tag", docs)
        self.assertIn("atlas-k8s-addons", docs)
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("k8s-core.md", index)
        clusters_doc = (ROOT / "docs" / "clusters.md").read_text(encoding="utf-8")
        self.assertIn("k8s-core.md", clusters_doc)
        template_readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/k8s-core.md", template_readme)
        leaf = path
        readme = None if leaf is None else leaf / "README.md"
        if readme is not None and readme.is_file():
            ref_readme = (readme).read_text(encoding="utf-8")
            self.assertIn("docs/stacks/k8s-core.md", ref_readme)

    @skip_unless_stack(STACK)
    def test_context_loads_reference(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.paths import clusters_root

        os.environ["ATLAS_CLUSTER_ROOT"] = str(ROOT)
        ctx = ClusterContext.load(cluster_id=lab)
        self.assertEqual(ctx.cluster_id, lab)
        self.assertTrue((ctx.config_dir / "group_vars" / "all" / "atlas-k8s-core.yml").is_file())
        self.assertFalse((ctx.config_dir / "group_vars" / "all" / "cluster.yml").exists())


if __name__ == "__main__":
    unittest.main()
