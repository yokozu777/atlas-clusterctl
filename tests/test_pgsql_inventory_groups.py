"""Tests for PostgreSQL inventory groups (pgsql_* + optional postgresql parent)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from clusterctl.inventory import DATA_GROUPS, PGSQL_GROUPS, extract_inventory_groups
from clusterctl.phase_intent import PhaseIntent
from clusterctl.validate import Severity, ValidationReport, _validate_phase_intent_vs_inventory


def _pgsql_nested_inventory() -> str:
    return yaml.safe_dump(
        {
            "all": {
                "children": {
                    "postgresql": {
                        "children": {
                            "pgsql_etcd_cluster": {
                                "hosts": {"192.168.1.250": {"hostname": "etcd01.example.com"}}
                            },
                            "pgsql_cluster": {
                                "hosts": {"192.168.1.251": {"hostname": "pg01.example.com"}}
                            },
                            "pgsql_lbs": {
                                "hosts": {"192.168.1.252": {"hostname": "lb01.example.com"}}
                            },
                        }
                    }
                }
            }
        }
    )


def _pgsql_flat_inventory() -> str:
    return yaml.safe_dump(
        {
            "all": {
                "children": {
                    "pgsql_etcd_cluster": {
                        "hosts": {"192.168.1.250": {"hostname": "etcd01.example.com"}}
                    },
                    "pgsql_cluster": {
                        "hosts": {"192.168.1.251": {"hostname": "pg01.example.com"}}
                    },
                    "pgsql_lbs": {
                        "hosts": {"192.168.1.252": {"hostname": "lb01.example.com"}}
                    },
                }
            }
        }
    )


class PgsqlInventoryGroupsTest(unittest.TestCase):
    def test_pgsql_groups_constant(self) -> None:
        self.assertEqual(
            PGSQL_GROUPS,
            frozenset({"pgsql_etcd_cluster", "pgsql_cluster", "pgsql_lbs"}),
        )
        self.assertIn("pgsql_etcd_cluster", DATA_GROUPS)
        self.assertNotIn("postgresql", DATA_GROUPS)

    def test_extract_nested_parent_and_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hosts"
            path.write_text(_pgsql_nested_inventory(), encoding="utf-8")
            groups = extract_inventory_groups(path)
        self.assertIn("postgresql", groups)
        self.assertTrue(PGSQL_GROUPS <= groups)

    def test_extract_flat_pgsql_groups_without_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hosts"
            path.write_text(_pgsql_flat_inventory(), encoding="utf-8")
            groups = extract_inventory_groups(path)
        self.assertNotIn("postgresql", groups)
        self.assertTrue(PGSQL_GROUPS <= groups)

    def test_postgresql_stack_requires_pgsql_groups(self) -> None:
        report = ValidationReport()
        _validate_phase_intent_vs_inventory(
            report,
            PhaseIntent(
                infra=False,
                k8s=False,
                postgresql=True,
                mysql=False,
                redis=False,
                kafka=False,
                provision_stack="postgresql",
            ),
            {"postgresql"},
        )
        codes = [issue.code for issue in report.errors]
        self.assertIn("phase_intent_postgresql_no_inventory", codes)

    def test_postgresql_stack_ok_with_nested_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hosts"
            path.write_text(_pgsql_nested_inventory(), encoding="utf-8")
            groups = extract_inventory_groups(path)

        report = ValidationReport()
        _validate_phase_intent_vs_inventory(
            report,
            PhaseIntent(
                infra=False,
                k8s=False,
                postgresql=True,
                mysql=False,
                redis=False,
                kafka=False,
                provision_stack="postgresql",
            ),
            groups,
        )
        self.assertEqual(report.errors, [])

    def test_pgsql_groups_without_postgresql_stack_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hosts"
            path.write_text(_pgsql_flat_inventory(), encoding="utf-8")
            groups = extract_inventory_groups(path)

        report = ValidationReport()
        _validate_phase_intent_vs_inventory(
            report,
            PhaseIntent(
                infra=False,
                k8s=False,
                postgresql=False,
                mysql=False,
                redis=False,
                kafka=False,
                provision_stack="k8s",
            ),
            groups,
        )
        codes = [issue.code for issue in report.warnings]
        self.assertIn("inventory_postgresql_phases_omitted", codes)

    def test_postgresql_parent_without_children_warns(self) -> None:
        report = ValidationReport()
        _validate_phase_intent_vs_inventory(
            report,
            PhaseIntent(
                infra=False,
                k8s=False,
                postgresql=True,
                mysql=False,
                redis=False,
                kafka=False,
                provision_stack="postgresql",
            ),
            {"postgresql"},
        )
        warnings = [issue for issue in report.warnings if issue.code == "inventory_postgresql_parent_empty"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, Severity.WARNING)


if __name__ == "__main__":
    unittest.main()
