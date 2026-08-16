#!/usr/bin/env python3
"""Math checks for SAS-Taper. Run: python3 test_taper.py (or pytest).

These pin the arithmetic the schedule is built on, not the wording around it.
No extra packages needed.
"""

from __future__ import annotations

import unittest

from taper import (
    base_film_mg,
    build_schedule,
    compare_classic,
    ingested_closed_form,
    keep_ratio,
    lifetime_ceiling_mg,
)

FILM_SPECS = {
    # strength: (cut-axis mm, other side mm, published density mg/mm² to 3 s.f.)
    2: (22.0, 12.8, 0.00710),
    4: (22.0, 25.6, 0.00710),
    8: (22.0, 12.8, 0.0284),
    12: (22.0, 19.2, 0.0284),
}


class TestClosedForms(unittest.TestCase):
    def test_simulation_matches_closed_form(self):
        for n in (2, 3, 6, 8, 10, 20):
            for start in (2.0, 8.0, 12.0):
                for cycles in (1, 3, 7, 15):
                    sched = build_schedule(
                        start_mg=start, n=n, switch_2mg=False, target_mg=0.0,
                        max_cycles=cycles, stop_mode="reach",
                    )
                    self.assertAlmostEqual(
                        sched.total_mg,
                        ingested_closed_form(start, n, cycles),
                        places=9,
                        msg=f"n={n} start={start} cycles={cycles}",
                    )

    def test_closed_form_honours_stretched_cycles(self):
        sched = build_schedule(
            start_mg=8.0, n=6, hold_days=9, switch_2mg=False, target_mg=0.0,
            max_cycles=5, stop_mode="reach",
        )
        self.assertAlmostEqual(
            sched.total_mg, ingested_closed_form(8.0, 6, 5, days_per_cycle=9), places=9
        )

    def test_ceiling_is_the_limit_of_the_closed_form(self):
        for n in (2, 6, 10):
            for start in (8.0, 12.0):
                self.assertAlmostEqual(
                    lifetime_ceiling_mg(start, n),
                    ingested_closed_form(start, n, 10_000),
                    places=6,
                )

    def test_ceiling_scales_with_cycle_length(self):
        # days × (n − 1) × D0, not n(n − 1) × D0, once cycles are stretched.
        self.assertEqual(lifetime_ceiling_mg(8.0, 6), 240.0)
        self.assertEqual(lifetime_ceiling_mg(8.0, 6, days_per_cycle=9), 360.0)
        self.assertEqual(build_schedule(hold_days=9).ceiling_mg, 360.0)


class TestCycleInvariants(unittest.TestCase):
    def rows(self, **kw):
        return build_schedule(**kw).rows

    def test_dose_splits_exactly(self):
        for row in self.rows():
            self.assertAlmostEqual(row.daily_mg + row.sliver_mg, row.cut_from_mg, places=12)
            self.assertAlmostEqual(row.sliver_mg, row.cut_from_mg / row.n, places=12)

    def test_length_fraction_equals_dose_fraction(self):
        for row in self.rows():
            self.assertAlmostEqual(row.cut_mm * row.n, row.piece_mm, places=12)
            # mg per mm is the film's, so the piece length tracks the dose.
            self.assertAlmostEqual(
                row.piece_mm / row.cut_from_mg, 22.0 / row.film_mg, places=12
            )

    def test_bank_is_one_whole_piece_per_n_days(self):
        for row in self.rows():
            self.assertAlmostEqual(row.banked_mg, row.days * row.sliver_mg, places=12)
            if row.days == row.n:
                self.assertAlmostEqual(row.banked_mg, row.cut_from_mg, places=12)

    def test_stretched_cycle_banks_proportionally_more(self):
        row = self.rows(hold_days=9)[0]
        self.assertAlmostEqual(row.banked_mg, 9 * 8.0 / 6, places=12)

    def test_days_are_contiguous(self):
        rows = self.rows()
        self.assertEqual(rows[0].day_start, 1)
        for a, b in zip(rows, rows[1:]):
            self.assertEqual(a.day_end + 1, b.day_start)

    def test_totals_accumulate(self):
        sched = build_schedule()
        self.assertAlmostEqual(sched.total_mg, sum(r.used_mg for r in sched.rows), places=9)
        self.assertAlmostEqual(
            sched.total_banked_mg, sum(r.banked_mg for r in sched.rows), places=9
        )
        self.assertAlmostEqual(
            sched.total_mg, sum(m.used_mg for m in sched.months), places=9
        )
        self.assertAlmostEqual(
            sched.saved_vs_stay_mg, 8.0 * sched.end_day - sched.total_mg, places=9
        )


class TestDoseNeverGoesUp(unittest.TestCase):
    def assert_monotone(self, sched, label):
        for a, b in zip(sched.rows, sched.rows[1:]):
            self.assertLessEqual(
                b.daily_mg, a.daily_mg + 1e-12,
                msg=f"{label}: {a.daily_mg:.3f} -> {b.daily_mg:.3f}",
            )

    def test_across_switch_points(self):
        # A --switch-at below 2 mg used to restart the strip at 2 mg and walk
        # the daily dose back up.
        for switch_at in (1.0, 1.2, 1.5, 1.8, 2.0, 2.25, 3.0, 4.0):
            self.assert_monotone(
                build_schedule(switch_at_mg=switch_at), f"switch_at={switch_at}"
            )

    def test_across_start_doses_and_n(self):
        for start in (2.0, 2.2, 3.0, 4.0, 8.0, 12.0):
            for n in (2, 4, 6, 10):
                self.assert_monotone(
                    build_schedule(start_mg=start, n=n, strip_mg=start),
                    f"start={start} n={n}",
                )

    def test_impossible_switch_is_reported_not_applied(self):
        sched = build_schedule(switch_at_mg=1.5)
        self.assertTrue(sched.switch_never_fired)
        self.assertFalse(any(r.switched_2mg for r in sched.rows))


class TestFilmGeometry(unittest.TestCase):
    def test_base_film_is_the_smallest_that_holds_the_start_dose(self):
        self.assertEqual(base_film_mg(2.0), 2.0)
        self.assertEqual(base_film_mg(2.5), 4.0)
        self.assertEqual(base_film_mg(4.0), 4.0)
        self.assertEqual(base_film_mg(8.0), 8.0)
        self.assertEqual(base_film_mg(12.0), 12.0)

    def test_day_one_piece_is_never_longer_than_the_film(self):
        for start in (2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 12.0):
            sched = build_schedule(start_mg=start, strip_mg=start)
            self.assertLessEqual(
                sched.rows[0].piece_mm, 22.0 + 1e-9,
                msg=f"start={start} needs {sched.rows[0].piece_mm:.1f} mm of a 22 mm film",
            )

    def test_published_film_densities(self):
        # The site quotes density to 3 significant figures.
        for mg, (cut_mm, other_mm, density) in FILM_SPECS.items():
            self.assertAlmostEqual(mg / (cut_mm * other_mm), density, delta=density * 5e-4)

    def test_the_two_film_families_share_a_density(self):
        def density(mg):
            cut_mm, other_mm, _ = FILM_SPECS[mg]
            return mg / (cut_mm * other_mm)

        self.assertAlmostEqual(density(2), density(4), places=12)
        self.assertAlmostEqual(density(8), density(12), places=12)
        self.assertAlmostEqual(density(8) / density(2), 4.0, places=12)

    def test_switching_to_2mg_makes_the_same_dose_four_times_longer(self):
        # Same footprint, one quarter the density, so 4× the mm per mg.
        eight = FILM_SPECS[8][0] * FILM_SPECS[8][1] / 8
        two = FILM_SPECS[2][0] * FILM_SPECS[2][1] / 2
        self.assertAlmostEqual(two / eight, 4.0, places=9)


class TestSummary(unittest.TestCase):
    def test_milestones_use_the_same_convention(self):
        sched = build_schedule()
        first2 = next(r for r in sched.rows if r.daily_mg <= 2.0 + 1e-9)
        first1 = next(r for r in sched.rows if r.daily_mg <= 1.12)
        self.assertEqual(sched.days_to_2mg, first2.day_start)
        self.assertEqual(sched.days_to_1mg, first1.day_start)

    def test_truncation_is_flagged(self):
        self.assertTrue(build_schedule(n=25, switch_2mg=False).truncated)
        self.assertFalse(build_schedule().truncated)

    def test_compare_table_stops_above_target(self):
        for row in compare_classic():
            self.assertGreater(row["end_daily_mg"], 1.0)
            self.assertAlmostEqual(
                row["ceiling_mg"], lifetime_ceiling_mg(8.0, row["n"]), places=9
            )

    def test_slower_taper_costs_about_three_times_as_much(self):
        by_n = {row["n"]: row for row in compare_classic()}
        self.assertAlmostEqual(by_n[10]["total_mg"] / by_n[6]["total_mg"], 3.0, delta=0.15)
        self.assertAlmostEqual(by_n[10]["days"] / by_n[6]["days"], 3.0, delta=0.2)

    def test_keep_ratio(self):
        self.assertAlmostEqual(keep_ratio(6), 5 / 6)
        self.assertAlmostEqual(build_schedule().r, 5 / 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
