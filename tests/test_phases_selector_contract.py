"""ADR 008 — ``--phases`` selector contract matrix."""

from __future__ import annotations

import unittest

from clusterctl.exceptions import ClusterctlError
from clusterctl.phase_selector import (
    CliPhaseWindow,
    PhaseListSelector,
    PhaseRangeSelector,
    parse_phases_selector,
    resolve_cli_phase_window,
)


class PhasesSelectorContractTest(unittest.TestCase):
    def test_single_phase(self) -> None:
        sel = parse_phases_selector("init")
        self.assertEqual(sel, PhaseRangeSelector(from_phase="init", to_phase="init"))
        assert isinstance(sel, PhaseRangeSelector)
        self.assertTrue(sel.is_single)

    def test_single_phase_strips_whitespace(self) -> None:
        sel = parse_phases_selector("  provision  ")
        assert isinstance(sel, PhaseRangeSelector)
        self.assertEqual(sel.from_phase, "provision")
        self.assertEqual(sel.to_phase, "provision")

    def test_range_aliases(self) -> None:
        sel = parse_phases_selector("provision..k8s-addons")
        self.assertEqual(
            sel,
            PhaseRangeSelector(from_phase="provision", to_phase="k8s-addons"),
        )
        assert isinstance(sel, PhaseRangeSelector)
        self.assertFalse(sel.is_single)

    def test_range_full_refs(self) -> None:
        sel = parse_phases_selector(
            "atlas-compute-provision/provision..atlas-k8s-addons/addons"
        )
        assert isinstance(sel, PhaseRangeSelector)
        self.assertEqual(sel.from_phase, "atlas-compute-provision/provision")
        self.assertEqual(sel.to_phase, "atlas-k8s-addons/addons")

    def test_range_allows_spaces_around_separator(self) -> None:
        sel = parse_phases_selector("provision .. k8s-addons")
        assert isinstance(sel, PhaseRangeSelector)
        self.assertEqual(sel.from_phase, "provision")
        self.assertEqual(sel.to_phase, "k8s-addons")

    def test_empty_errors(self) -> None:
        for raw in ("", "   ", None):
            with self.subTest(raw=raw):
                with self.assertRaises(ClusterctlError) as ctx:
                    parse_phases_selector(raw)  # type: ignore[arg-type]
                self.assertIn("empty", str(ctx.exception).lower())

    def test_bare_separator_errors(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            parse_phases_selector("..")
        self.assertIn("non-empty", str(ctx.exception))

    def test_open_range_errors(self) -> None:
        for raw in ("provision..", "..k8s-addons", "  .. init", "init ..  "):
            with self.subTest(raw=raw):
                with self.assertRaises(ClusterctlError) as ctx:
                    parse_phases_selector(raw)
                self.assertIn("non-empty", str(ctx.exception))

    def test_multiple_separators_error(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            parse_phases_selector("a..b..c")
        self.assertIn("exactly one", str(ctx.exception))

    def test_comma_list_accepted(self) -> None:
        sel = parse_phases_selector("provision,init,k8s-core")
        self.assertEqual(
            sel,
            PhaseListSelector(names=("provision", "init", "k8s-core")),
        )

    def test_comma_list_strips_whitespace(self) -> None:
        sel = parse_phases_selector(" provision , init ")
        self.assertEqual(sel, PhaseListSelector(names=("provision", "init")))

    def test_comma_list_empty_item_errors(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            parse_phases_selector("provision,,init")
        self.assertIn("non-empty", str(ctx.exception))

    def test_comma_list_duplicate_name_errors(self) -> None:
        with self.assertRaises(ClusterctlError) as ctx:
            parse_phases_selector("init,provision,init")
        self.assertIn("duplicate", str(ctx.exception).lower())

    def test_mix_range_and_comma_errors(self) -> None:
        for raw in ("provision..k8s-addons,init", "provision,init..k8s-core"):
            with self.subTest(raw=raw):
                with self.assertRaises(ClusterctlError) as ctx:
                    parse_phases_selector(raw)
                self.assertIn("mix", str(ctx.exception).lower())

    def test_unicode_ellipsis_lookalikes_error(self) -> None:
        for raw in ("provision…k8s-addons", "provision‥k8s-addons", "provision⋯k8s-addons"):
            with self.subTest(raw=raw):
                with self.assertRaises(ClusterctlError) as ctx:
                    parse_phases_selector(raw)
                msg = str(ctx.exception)
                self.assertIn("ASCII '..'", msg)
                self.assertNotIn("ASCII '-'", msg)

    def test_unicode_dash_lookalikes_error(self) -> None:
        for raw in ("k8s–addons", "provision—k8s-addons", "provision–init"):
            with self.subTest(raw=raw):
                with self.assertRaises(ClusterctlError) as ctx:
                    parse_phases_selector(raw)
                msg = str(ctx.exception)
                self.assertIn("ASCII '-'", msg)
                self.assertIn("ASCII '..'", msg)

    def test_single_phase_ok_csv_needs_two(self) -> None:
        sel = parse_phases_selector("init")
        self.assertEqual(sel, PhaseRangeSelector(from_phase="init", to_phase="init"))
        # Trailing/leading comma → empty item (not a one-name CSV).
        for raw in ("init,", ",init"):
            with self.subTest(raw=raw):
                with self.assertRaises(ClusterctlError) as ctx:
                    parse_phases_selector(raw)
                self.assertIn("non-empty", str(ctx.exception).lower())


    def test_resolve_cli_window_from_selector(self) -> None:
        self.assertEqual(
            resolve_cli_phase_window(phases_selector="provision..init"),
            CliPhaseWindow(from_phase="provision", to_phase="init"),
        )
        self.assertEqual(
            resolve_cli_phase_window(phases_selector="templates"),
            CliPhaseWindow(from_phase="templates", to_phase="templates"),
        )

    def test_resolve_cli_window_explicit_list(self) -> None:
        self.assertEqual(
            resolve_cli_phase_window(phases_selector="provision,k8s-addons"),
            CliPhaseWindow(only_phases=("provision", "k8s-addons")),
        )

    def test_resolve_cli_window_omit_means_full_plan(self) -> None:
        self.assertEqual(resolve_cli_phase_window(), CliPhaseWindow())
        self.assertEqual(
            resolve_cli_phase_window(phases_selector=None),
            CliPhaseWindow(),
        )


if __name__ == "__main__":
    unittest.main()
