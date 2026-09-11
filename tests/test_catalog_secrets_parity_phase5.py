"""Phase 5: key parity sibling ↔ template ↔ inventory + secrets placement."""

from __future__ import annotations

import unittest

import yaml

from clusterctl.cluster_layout import cascade_group_vars_dirs
from clusterctl.cluster_vars_loader import load_cluster_vars
from clusterctl.paths import clusters_root, list_deployable_cluster_ids, repo_root
from tests.catalog_parity import (
    INVENTORY_SECRET_REQUIRED,
    LEAF_PRODUCTS,
    LEAF_STACK,
    PRODUCT_REPOS,
    SECRET_REQUIRED_IN_SECRETS,
    TEMPLATE_ROOT,
    assert_no_forbidden_secrets,
    foundation_repo_surface_ok,
    leaf_product_overlays,
    must_add_for_product,
    parity_keys,
    product_pair_keys,
    sibling_all_dir,
    sibling_present,
)
from tests.lab_support import lab_exists, lab_leaf, lab_id_for, lab_path_for, skip_unless_stack


class CatalogSecretsParityPhase5Test(unittest.TestCase):
    def test_sibling_template_key_parity(self) -> None:
        """Sibling operational keys == template keys (identity/controller/other maps excluded)."""
        missing_siblings: list[str] = []
        for leaf, products in LEAF_PRODUCTS.items():
            stack = LEAF_STACK[leaf]
            tmpl_dir = TEMPLATE_ROOT / leaf / "group_vars" / "all"
            for product in products:
                if not sibling_present(product):
                    missing_siblings.append(product)
                    continue
                _s_cat, _s_sec, s_all = product_pair_keys(sibling_all_dir(product), product)
                _t_cat, _t_sec, t_all = product_pair_keys(tmpl_dir, product)
                stack_arg = stack if product == "atlas-compute-provision" else None
                s_par = parity_keys(s_all, stack=stack_arg)
                t_par = parity_keys(t_all, stack=stack_arg)
                only_sib = sorted(s_par - t_par)
                only_tmpl = sorted(t_par - s_par)
                self.assertEqual(
                    only_sib,
                    [],
                    f"{product} vs _template/{leaf}: only in sibling: {only_sib}",
                )
                self.assertEqual(
                    only_tmpl,
                    [],
                    f"{product} vs _template/{leaf}: only in template: {only_tmpl}",
                )
        if missing_siblings:
            self.skipTest(f"sibling repos not present: {sorted(set(missing_siblings))}")

    def test_template_secrets_placement(self) -> None:
        for leaf, products in LEAF_PRODUCTS.items():
            all_dir = TEMPLATE_ROOT / leaf / "group_vars" / "all"
            for product in products:
                cat, sec, _ = product_pair_keys(all_dir, product)
                leaks = assert_no_forbidden_secrets(cat, product)
                self.assertEqual(
                    leaks, [], f"_template/{leaf}/{product}: secrets in catalog: {leaks}"
                )
                for key in SECRET_REQUIRED_IN_SECRETS.get(product, ()):
                    self.assertIn(
                        key,
                        sec,
                        f"_template/{leaf}/{product}.secrets.yml missing {key}",
                    )

    def test_sibling_secrets_placement(self) -> None:
        skipped = 0
        for product in PRODUCT_REPOS:
            if not sibling_present(product):
                skipped += 1
                continue
            cat, sec, _ = product_pair_keys(sibling_all_dir(product), product)
            leaks = assert_no_forbidden_secrets(cat, product)
            self.assertEqual(leaks, [], f"{product}: secrets in catalog: {leaks}")
            for key in SECRET_REQUIRED_IN_SECRETS.get(product, ()):
                self.assertIn(key, sec, f"{product}.secrets.yml missing {key}")
        if skipped == len(PRODUCT_REPOS):
            self.skipTest("no sibling repos present")

    def test_inventory_pairs_secrets_and_must_add(self) -> None:
        """Discover deployable leaves; must-add / repos via cascade (path-agnostic)."""
        root = repo_root()
        croot = clusters_root(root)
        lab_ids = list_deployable_cluster_ids(root)
        if not lab_ids:
            self.skipTest("no local inventory labs present")

        any_lab = False
        for lab_id in lab_ids:
            parts = tuple(p for p in lab_id.split("/") if p)
            if not lab_exists(*parts):
                continue
            any_lab = True
            leaf = lab_leaf(*parts)
            all_dir = leaf / "group_vars" / "all"
            products = leaf_product_overlays(all_dir)
            self.assertTrue(
                products,
                f"{lab_id}: expected at least one atlas-*.yml product overlay",
            )

            cluster_yaml = yaml.safe_load(
                (leaf / "cluster.yaml").read_text(encoding="utf-8")
            ) or {}
            playbooks = cluster_yaml.get("playbooks") or {}
            playbook_keys = set(playbooks) if isinstance(playbooks, dict) else set()
            cascade = cascade_group_vars_dirs(croot, lab_id)
            merged = load_cluster_vars(leaf, cascade_dirs=cascade)
            # Thin infra-edge bridge on k8s leaves has overlay but no playbooks entry.
            products_for_playbooks = [
                p
                for p in products
                if not (
                    p == "atlas-infra-edge" and "infra_platform_hosts" not in merged
                )
            ]
            missing_playbooks = sorted(set(products_for_playbooks) - playbook_keys)
            self.assertEqual(
                missing_playbooks,
                [],
                f"{lab_id}: overlays not in cluster.yaml playbooks: {missing_playbooks}",
            )

            for product in products:
                cat_path = all_dir / f"{product}.yml"
                sec_path = all_dir / f"{product}.secrets.yml"
                self.assertTrue(cat_path.is_file(), cat_path)
                cat, sec, _ = product_pair_keys(all_dir, product)
                leaks = assert_no_forbidden_secrets(cat, product)
                self.assertEqual(
                    leaks, [], f"{lab_id}/{product}: secrets in catalog: {leaks}"
                )

                thin_infra = (
                    product == "atlas-infra-edge"
                    and "infra_platform_hosts" not in merged
                )
                if thin_infra:
                    self.assertFalse(
                        sec_path.is_file(),
                        f"{lab_id}: unexpected {sec_path.name} "
                        f"(thin infra-edge; use k8s-addons secrets)",
                    )
                    continue

                required_secrets = INVENTORY_SECRET_REQUIRED.get(product, ())
                if product == "atlas-kafka":
                    required_secrets = ()
                if sec_path.is_file():
                    _c, sec_keys, _ = product_pair_keys(all_dir, product)
                    for key in required_secrets:
                        self.assertIn(
                            key,
                            sec_keys,
                            f"{lab_id}/{product}.secrets.yml missing {key}",
                        )
                else:
                    # Secrets may live only on env/org default (cascade).
                    for key in required_secrets:
                        self.assertIn(
                            key,
                            merged,
                            f"{lab_id}/{product}: secret {key!r} missing on leaf "
                            f"and cascade",
                        )

                required = must_add_for_product(product, merged)
                missing = sorted(required - set(merged))
                self.assertEqual(
                    missing,
                    [],
                    f"{lab_id}/{product}: must-add missing in cascade: {missing}",
                )

            if "atlas-node-foundation" in products:
                self.assertTrue(
                    foundation_repo_surface_ok(merged),
                    f"{lab_id}: cascade needs non-empty pkg_repos and/or "
                    f"pkg_repos_extra (role combines into _pkg_repos_effective)",
                )

            self.assertFalse((all_dir / "secrets.yml").is_file(), lab_id)
            self.assertFalse((all_dir / "secrets.yml.example").is_file(), lab_id)

        if not any_lab:
            self.skipTest("no local inventory labs present")

    @skip_unless_stack("redis")
    def test_ci_redis_vip_auth_only_in_secrets(self) -> None:
        all_dir = lab_path_for("redis") / "group_vars" / "all"
        cat, sec, _ = product_pair_keys(all_dir, "atlas-redis")
        self.assertNotIn("vip_auth_pass", cat)
        self.assertIn("vip_auth_pass", sec)
        self.assertNotIn("redis_requirepass", cat)
        self.assertIn("redis_requirepass", sec)


if __name__ == "__main__":
    unittest.main()
