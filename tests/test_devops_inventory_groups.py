"""DevOps phase intent must match the devops_stack inventory group."""

from __future__ import annotations

import unittest

from clusterctl.inventory import DEVOPS_GROUPS
from clusterctl.phase_intent import PhaseIntent
from clusterctl.validate import Severity, ValidationReport, _validate_phase_intent_vs_inventory


def _intent(*, devops: bool, stack: str = "devops") -> PhaseIntent:
    return PhaseIntent(
        infra=False,
        k8s=False,
        postgresql=False,
        mysql=False,
        redis=False,
        kafka=False,
        ceph=False,
        devops=devops,
        mlops=False,
        provision_stack=stack,
    )


class DevopsInventoryGroupsTest(unittest.TestCase):
    def test_devops_group_is_a_working_group(self) -> None:
        self.assertIn("devops_stack", DEVOPS_GROUPS)
        self.assertNotIn("devops", DEVOPS_GROUPS)

    def test_devops_phase_requires_the_group(self) -> None:
        report = ValidationReport()
        _validate_phase_intent_vs_inventory(report, _intent(devops=True), {"devops"})
        codes = [issue.code for issue in report.errors]
        self.assertIn("phase_intent_devops_no_inventory", codes)

    def test_devops_phase_ok_with_the_group(self) -> None:
        report = ValidationReport()
        _validate_phase_intent_vs_inventory(
            report, _intent(devops=True), {"devops", "devops_stack"}
        )
        self.assertEqual(report.errors, [])

    def test_group_without_phase_warns(self) -> None:
        report = ValidationReport()
        _validate_phase_intent_vs_inventory(
            report, _intent(devops=False, stack="k8s"), {"devops_stack"}
        )
        codes = [issue.code for issue in report.warnings]
        self.assertIn("inventory_devops_phases_omitted", codes)

    def test_parent_without_child_warns(self) -> None:
        report = ValidationReport()
        _validate_phase_intent_vs_inventory(report, _intent(devops=True), {"devops"})
        warnings = [
            issue for issue in report.warnings if issue.code == "inventory_devops_parent_empty"
        ]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, Severity.WARNING)


if __name__ == "__main__":
    unittest.main()
