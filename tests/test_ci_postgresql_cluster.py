"""Tests for PostgreSQL HA cluster.

SoT for public CI: ``_template/postgresql``. Optional lab: discovered postgresql lab (``lab_id_for('postgresql')``).
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config_loader import load_merged_cluster_config_v2
from clusterctl.context import ClusterContext
from clusterctl.inventory import PGSQL_GROUPS, extract_inventory_groups
from clusterctl.paths import clusters_root, list_deployable_cluster_ids, repo_root
from tests.lab_support import (
    lab_id_for,
    lab_path_for,

    PUBLIC_POSTGRESQL_TEMPLATE,
    skip_unless_stack,
    group_vars_all_file,
    foundation_has_pkg_repos_key,
    foundation_merged_repo_names,
)

ROOT = Path(__file__).resolve().parents[1]
STACK = "postgresql"
TEMPLATE = PUBLIC_POSTGRESQL_TEMPLATE


class CiPostgresqlClusterTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    @skip_unless_stack(STACK)
    def test_phases_include_postgresql_cluster(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.phases is not None
        phases = config.phases.phases
        self.assertEqual(len(phases), 3)
        self.assertNotIn("atlas-compute-provision/templates", phases)
        self.assertIn("atlas-compute-provision/provision", phases)
        self.assertIn("atlas-node-foundation/init", phases)
        self.assertIn("atlas-postgresql/cluster", phases)
        for ref in phases:
            self.assertNotIn("k8s-core", ref)
            self.assertNotIn("infra-edge", ref)

    @skip_unless_stack(STACK)
    def test_playbooks_include_atlas_postgresql(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.playbooks is not None
        self.assertIn("atlas-postgresql", config.playbooks.repos)
        entry = config.playbooks.repos["atlas-postgresql"].entries["cluster"]
        self.assertEqual(entry.file, "playbooks/postgresql_cluster.yaml")
        tags = [inv.tags for inv in entry.invocations]
        self.assertIn("01_validate_vars", tags)
        self.assertIn("200_pgsql_etcd", tags)
        self.assertIn("201_pgsql_cluster,202_pgsql_patroni,203_pgsql_bouncer", tags)
        self.assertIn("204_pgsql_lb", tags)
        self.assertIn("202_pgsql_patroni_verify", tags)

    @skip_unless_stack(STACK)
    def test_provision_stack_postgresql_in_group_vars(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        ctx = ClusterContext.load(cluster_id=lab)
        text = group_vars_all_file(ctx.config_dir, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: postgresql", text)
        self.assertIn("provision_inventory_group_map_postgresql", text)
        self.assertNotIn("provision_pve_templates:", text)
        self.assertNotIn("image_url:", text)
        hosts = (ctx.config_dir / "hosts").read_text(encoding="utf-8")
        self.assertIn("ubuntu-base", hosts)

    @skip_unless_stack(STACK)
    def test_repos_enable_pgdg(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-node-foundation.yml").read_text(encoding="utf-8")
        self.assertTrue(
            foundation_has_pkg_repos_key(text),
            "expected pkg_repos: and/or pkg_repos_extra:",
        )
        self.assertIn("name: pgdg-apt", text)
        self.assertIn("name: pgdg-yum", text)
        names = foundation_merged_repo_names(lab)
        self.assertIn("pgdg-apt", names)
        self.assertIn("pgdg-yum", names)
        for os_name in ("ubuntu", "debian-main", "OL9_baseos"):
            self.assertIn(os_name, names, f"cascade missing {os_name}")
        self.assertNotIn("enable_repo_", text)
        self.assertNotIn("pkg_repo_name_prefix", text)

    def test_postgresql_template_repos_match_ci_pgdg_contract(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        template_init = (TEMPLATE / "group_vars" / "all" / "atlas-node-foundation.yml").read_text(encoding="utf-8")
        markers = (
            "name: pgdg-yum",
            "name: pgdg-apt",
            "name: debian-main",
            "name: OL9_baseos",
            "pkg_repos:",
        )
        for marker in markers:
            self.assertIn(marker, template_init, marker)
        self.assertNotIn("enable_repo_", template_init)
        if lab:
            ci_init = group_vars_all_file(path, "atlas-node-foundation.yml").read_text(encoding="utf-8")
            self.assertTrue(foundation_has_pkg_repos_key(ci_init), path)
            self.assertIn("name: pgdg-apt", ci_init)
            self.assertIn("name: pgdg-yum", ci_init)
            names = foundation_merged_repo_names(lab)
            for os_name in ("ubuntu", "debian-main", "OL9_baseos", "pgdg-apt", "pgdg-yum"):
                self.assertIn(os_name, names, os_name)
            self.assertNotIn("enable_repo_", ci_init)

    @skip_unless_stack(STACK)
    def test_postgresql_yml_pgdg_from_init(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-postgresql.yml").read_text(encoding="utf-8")
        self.assertIn('pgsql_version: "18"', text)
        self.assertIn("pgsql_pgdg_repo_from_init: true", text)
        self.assertNotIn("pkg_repo_name_prefix", text)
        self.assertIn("pgsql_etcd_hosts: pgsql_etcd_cluster", text)
        self.assertIn("pgsql_cluster_hosts: pgsql_cluster", text)
        self.assertIn("pgsql_lb_hosts: pgsql_lbs", text)

    @skip_unless_stack(STACK)
    def test_init_targets_all_pgsql_groups(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-node-foundation.yml").read_text(encoding="utf-8")
        self.assertIn('node_foundation_init_hosts: "pgsql_etcd_cluster:pgsql_cluster:pgsql_lbs"', text)
        self.assertTrue(foundation_has_pkg_repos_key(text))

    def test_pgdg_from_init_uses_catalog_paths(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        leaves = [TEMPLATE]
        if lab:
            leaves.append(path)
        for leaf in leaves:
            prepare = group_vars_all_file(leaf, "atlas-node-foundation.yml").read_text(encoding="utf-8")
            pgsql = group_vars_all_file(leaf, "atlas-postgresql.yml").read_text(encoding="utf-8")
            self.assertTrue(foundation_has_pkg_repos_key(prepare), leaf)
            self.assertIn("name: pgdg-apt", prepare, leaf)
            self.assertIn("name: pgdg-yum", prepare, leaf)
            self.assertNotIn("pkg_repo_name_prefix", prepare, leaf)
            self.assertNotIn("pkg_repo_name_prefix", pgsql, leaf)
            self.assertIn("pgsql_pgdg_repo_from_init: true", pgsql, leaf)
            for key in (
                "pgsql_etcd_hosts: pgsql_etcd_cluster",
                "pgsql_cluster_hosts: pgsql_cluster",
                "pgsql_lb_hosts: pgsql_lbs",
            ):
                self.assertIn(key, pgsql, f"{leaf}: {key}")

    def test_cluster_yaml_invocations_match_standalone_tag_contract(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        expected = [
            "00_ensure_workspace",
            "01_validate_vars",
            "200_pgsql_etcd",
            "201_pgsql_cluster,202_pgsql_patroni,203_pgsql_bouncer",
            "204_pgsql_lb",
            "202_pgsql_patroni_verify",
        ]
        paths = [TEMPLATE / "cluster.yaml"]
        if lab:
            paths.append(path / "cluster.yaml")
        for leaf in paths:
            data = yaml.safe_load(leaf.read_text(encoding="utf-8"))
            inv = data["playbooks"]["atlas-postgresql"]["entries"]["cluster"]["invocations"]
            tags = [i["tags"] for i in inv]
            self.assertEqual(tags, expected, leaf)
            limits = {i["tags"]: i.get("limit") for i in inv}
            self.assertEqual(limits["200_pgsql_etcd"], "pgsql_etcd_cluster")
            self.assertEqual(
                limits["201_pgsql_cluster,202_pgsql_patroni,203_pgsql_bouncer"],
                "pgsql_cluster",
            )
            self.assertEqual(limits["204_pgsql_lb"], "pgsql_lbs")
            self.assertEqual(limits["202_pgsql_patroni_verify"], "pgsql_cluster")

    def test_orchestration_docs_exist(self) -> None:
        docs = (ROOT / "docs" / "stacks" / "postgresql.md").read_text(encoding="utf-8")
        self.assertIn("pgsql_pgdg_repo_from_init", docs)
        self.assertIn("pgdg-apt.sources", docs)
        self.assertIn("202_pgsql_patroni_verify", docs)
        self.assertIn("pgsql_etcd_hosts", docs)
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("postgresql.md", index)
        template_readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/postgresql.md", template_readme)

    @skip_unless_stack(STACK)
    def test_inventory_has_pgsql_groups_and_parent(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        groups = extract_inventory_groups(path / "hosts")
        self.assertIn("postgresql", groups)
        self.assertTrue(PGSQL_GROUPS <= groups)

    @skip_unless_stack(STACK)
    def test_plan_provision_only(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        from clusterctl.phase_plan import resolve_phase_execution_plan

        ctx = ClusterContext.load(cluster_id=lab)
        plan = resolve_phase_execution_plan(
            ctx,
            from_phase="provision",
            to_phase="provision",
        )
        self.assertEqual(len(plan.summary.phases), 1)
        self.assertEqual(plan.summary.invocation_count, 10)

    def test_init_postgresql_template_from_repo(self) -> None:
        self.assertTrue(TEMPLATE.is_dir())
        self.assertTrue((TEMPLATE / "cluster.yaml").is_file())
        self.assertTrue((TEMPLATE / "group_vars" / "all" / "atlas-postgresql.yml").is_file())
        content = (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas-postgresql", content)
        self.assertNotIn("phase_aliases", content)
        self.assertIn("postgresql: atlas-postgresql/cluster", content)

    @skip_unless_stack(STACK)
    def test_hosts_ips_match_lab_documentation(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        lab_plan_path = path / "lab_plan.yml"
        if not lab_plan_path.is_file():
            self.skipTest(f"no {lab_plan_path.name} on {lab}")
        hosts = yaml.safe_load((path / "hosts").read_text(encoding="utf-8"))
        lab_plan = yaml.safe_load(lab_plan_path.read_text(encoding="utf-8"))
        children = hosts["all"]["children"]["postgresql"]["children"]
        for group in ("pgsql_etcd_cluster", "pgsql_cluster", "pgsql_lbs"):
            self.assertEqual(len(children[group]["hosts"]), 3)
            self.assertEqual(lab_plan["topology"]["groups"][group], 3)
            for entry in lab_plan["network"]["hosts"][group]:
                self.assertIn(entry["ip"], children[group]["hosts"])
        pg_yml = group_vars_all_file(path, "atlas-postgresql.yml").read_text(encoding="utf-8")
        self.assertIn('vip_address: "192.168.1.129"', pg_yml)


if __name__ == "__main__":
    unittest.main()
