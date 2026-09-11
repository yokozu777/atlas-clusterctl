"""Tests for Redis Cluster HA cluster.

SoT for public CI: ``_template/redis``. Optional lab: discovered redis lab (``lab_id_for('redis')``).
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from clusterctl.cluster_config_loader import load_merged_cluster_config_v2
from clusterctl.context import ClusterContext
from clusterctl.inventory import REDIS_GROUPS, extract_inventory_groups
from clusterctl.paths import clusters_root, list_deployable_cluster_ids, repo_root
from tests.lab_support import (
    lab_id_for,
    lab_path_for,

    PUBLIC_REDIS_TEMPLATE,
    skip_unless_stack,
    group_vars_all_file,
    foundation_merged_repo_names,
)

ROOT = Path(__file__).resolve().parents[1]
STACK = "redis"
TEMPLATE = PUBLIC_REDIS_TEMPLATE


class CiRedisClusterTest(unittest.TestCase):
    @skip_unless_stack(STACK)
    def test_is_deployable(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        deployable = list_deployable_cluster_ids(repo_root())
        self.assertIn(lab, deployable)

    @skip_unless_stack(STACK)
    def test_phases_include_redis_cluster(self) -> None:
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
        self.assertIn("atlas-redis/cluster", phases)
        for ref in phases:
            self.assertNotIn("k8s-core", ref)
            self.assertNotIn("infra-edge", ref)

    @skip_unless_stack(STACK)
    def test_playbooks_include_atlas_redis(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        config = load_merged_cluster_config_v2(clusters_root(), lab)
        assert config.playbooks is not None
        self.assertIn("atlas-redis", config.playbooks.repos)
        entry = config.playbooks.repos["atlas-redis"].entries["cluster"]
        self.assertEqual(entry.file, "playbooks/redis_cluster.yaml")
        tags = [inv.tags for inv in entry.invocations]
        self.assertIn("01_validate_vars", tags)
        self.assertIn("200_redis_node", tags)
        self.assertIn("201_redis_cluster", tags)
        self.assertIn("202_redis_proxy", tags)
        self.assertIn("203_redis_lb", tags)
        self.assertIn("204_redis_verify", tags)

    @skip_unless_stack(STACK)
    def test_provision_stack_redis_in_group_vars(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        ctx = ClusterContext.load(cluster_id=lab)
        text = group_vars_all_file(ctx.config_dir, "atlas-compute-provision.yml").read_text(encoding="utf-8")
        self.assertIn("provision_stack: redis", text)
        self.assertIn("provision_inventory_group_map_redis", text)
        self.assertNotIn("provision_pve_templates:", text)
        self.assertNotIn("image_url:", text)
        hosts = (ctx.config_dir / "hosts").read_text(encoding="utf-8")
        self.assertIn("ubuntu-base", hosts)

    @skip_unless_stack(STACK)
    def test_redis_yml_vip_and_cluster_sizing(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-redis.yml").read_text(encoding="utf-8")
        self.assertIn('vip_address: "192.168.1.130"', text)
        self.assertIn("redis_cluster_replicas_per_master: 1", text)
        self.assertIn('redis_version: "8.8.0"', text)
        self.assertIn("predixy_version:", text)
        self.assertIn("redis_master_hosts: redis_cluster_masters", text)
        self.assertIn("redis_lb_hosts: redis_lbs", text)

    def test_pkg_repos_in_prepare_hosts(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        leaves = [TEMPLATE]
        if lab:
            leaves.append(path)
        for leaf in leaves:
            prepare = group_vars_all_file(leaf, "atlas-node-foundation.yml").read_text(encoding="utf-8")
            if leaf == TEMPLATE:
                self.assertIn("pkg_repos:", prepare, leaf)
                self.assertIn("name: ubuntu", prepare, leaf)
            else:
                names = foundation_merged_repo_names(lab)
                self.assertIn("ubuntu", names, "cascade OS base")
                self.assertNotIn("enable_repo_", prepare, leaf)
            self.assertNotIn("pkg_repo_name_prefix:", prepare, leaf)
            self.assertIn(
                'node_foundation_init_hosts: "redis_cluster_masters:redis_cluster_replicas:redis_proxies:redis_lbs"',
                prepare,
                leaf,
            )

    @skip_unless_stack(STACK)
    def test_init_targets_all_redis_groups(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        text = group_vars_all_file(path, "atlas-node-foundation.yml").read_text(encoding="utf-8")
        self.assertIn(
            'node_foundation_init_hosts: "redis_cluster_masters:redis_cluster_replicas:redis_proxies:redis_lbs"',
            text,
        )

    @skip_unless_stack(STACK)
    def test_inventory_has_redis_groups_and_parent(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        groups = extract_inventory_groups(path / "hosts")
        self.assertIn("redis", groups)
        self.assertTrue(REDIS_GROUPS <= groups)

    @skip_unless_stack(STACK)
    def test_plan_provision_only(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        ctx = ClusterContext.load(cluster_id=lab)
        from clusterctl.phase_plan import resolve_phase_execution_plan

        plan = resolve_phase_execution_plan(
            ctx,
            from_phase="provision",
            to_phase="provision",
        )
        self.assertEqual(len(plan.summary.phases), 1)
        self.assertEqual(plan.summary.invocation_count, 10)

    def test_init_redis_template_from_repo(self) -> None:
        self.assertTrue(TEMPLATE.is_dir())
        self.assertTrue((TEMPLATE / "cluster.yaml").is_file())
        self.assertTrue((TEMPLATE / "group_vars" / "all" / "atlas-redis.yml").is_file())
        self.assertTrue((TEMPLATE / "group_vars" / "all" / "atlas-redis.secrets.yml").is_file())
        catalog = (TEMPLATE / "group_vars" / "all" / "atlas-redis.yml").read_text(encoding="utf-8")
        secrets = (TEMPLATE / "group_vars" / "all" / "atlas-redis.secrets.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("vip_auth_pass:", catalog)
        self.assertIn("vip_auth_pass:", secrets)
        content = (TEMPLATE / "cluster.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas-redis", content)
        self.assertNotIn("phase_aliases", content)
        self.assertIn("redis: atlas-redis/cluster", content)

    @skip_unless_stack(STACK)
    def test_redis_secrets_overlay_holds_vip_auth(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        assert lab is not None and path is not None
        catalog = group_vars_all_file(path, "atlas-redis.yml").read_text(encoding="utf-8")
        secrets = group_vars_all_file(path, "atlas-redis.secrets.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("vip_auth_pass:", catalog)
        self.assertIn("vip_auth_pass:", secrets)

    def test_cluster_yaml_invocations_match_standalone_tag_contract(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        expected = [
            "00_ensure_workspace",
            "01_validate_vars",
            "200_redis_node",
            "201_redis_cluster",
            "202_redis_proxy",
            "203_redis_lb",
            "204_redis_verify",
        ]
        paths = [TEMPLATE / "cluster.yaml"]
        if lab:
            paths.append(path / "cluster.yaml")
        for leaf in paths:
            data = yaml.safe_load(leaf.read_text(encoding="utf-8"))
            inv = data["playbooks"]["atlas-redis"]["entries"]["cluster"]["invocations"]
            tags = [i["tags"] for i in inv]
            self.assertEqual(tags, expected, leaf)
            limits = {i["tags"]: i.get("limit") for i in inv}
            self.assertEqual(limits["200_redis_node"], "redis_cluster_masters:redis_cluster_replicas")
            self.assertEqual(limits["201_redis_cluster"], "redis_cluster_masters:redis_cluster_replicas")
            self.assertEqual(limits["202_redis_proxy"], "redis_proxies")
            self.assertEqual(limits["203_redis_lb"], "redis_lbs")
            self.assertEqual(limits["204_redis_verify"], "redis_cluster_masters:redis_cluster_replicas")

    def test_orchestration_docs_exist(self) -> None:
        lab = lab_id_for(STACK)
        path = lab_path_for(STACK)
        docs = (ROOT / "docs" / "stacks" / "redis.md").read_text(encoding="utf-8")
        self.assertIn("redis_master_hosts", docs)
        self.assertIn("pkg_repos", docs)
        self.assertIn("204_redis_verify", docs)
        self.assertIn("00_ensure_workspace", docs)
        index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("redis.md", index)
        template_readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/stacks/redis.md", template_readme)
        leaves = [TEMPLATE]
        if lab:
            leaves.append(path)
        for leaf in leaves:
            redis_yml = group_vars_all_file(leaf, "atlas-redis.yml").read_text(encoding="utf-8")
            for key in (
                "redis_master_hosts: redis_cluster_masters",
                "redis_replica_hosts: redis_cluster_replicas",
                "redis_proxy_hosts: redis_proxies",
                "redis_lb_hosts: redis_lbs",
            ):
                self.assertIn(key, redis_yml, f"{leaf}: {key}")

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
        children = hosts["all"]["children"]["redis"]["children"]
        for group, count in lab_plan["topology"]["groups"].items():
            self.assertEqual(len(children[group]["hosts"]), count)
            for entry in lab_plan["network"]["hosts"][group]:
                self.assertIn(entry["ip"], children[group]["hosts"])


if __name__ == "__main__":
    unittest.main()
