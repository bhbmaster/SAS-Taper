#!/usr/bin/env python3
"""Math checks for SAS-Taper. Run: python3 test_taper.py (or pytest).

These pin the arithmetic the schedule is built on, not the wording around it.
No extra packages needed.
"""

from __future__ import annotations

import math
import unittest

from taper import (
    base_film_mg,
    build_schedule,
    film_layout,
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
    """The ladder simulated cycle by cycle must equal the algebra.

    build_schedule walks the cycles; ingested_closed_form and lifetime_ceiling_mg
    answer the same questions in one step. If the two ever disagree, one of them
    is wrong — and the closed forms are what the summary cards quote.
    """

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
    """Properties that must hold for every cycle of every run.

    These are the method itself, stated as arithmetic: the dose splits exactly
    into take and save, length fraction equals dose fraction (which is only
    true while cutting one axis), the jar gains exactly one whole piece per n
    days, and the day numbering has no gaps.
    """

    def rows(self, **kw):
        """Cycle rows for a schedule built from the defaults plus kw."""
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
    """A taper must never step upward, at any setting.

    This is the one failure that would actively harm someone following the
    schedule. It has happened: restarting on a 2 mg film below the switch point
    used to walk the daily dose back up, so --switch-at 1.5 went 1.29 -> 1.67
    mg/day. The switch now only fires while the result is still a step down.
    """

    def assert_monotone(self, sched, label):
        """Fail if any cycle's daily dose exceeds the one before it.

        Args:
            sched: the schedule to walk.
            label: printed on failure, to identify which setting broke it.
        """
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
    """The physical facts the millimetre figures rest on.

    Every cut mark on the page is derived from the published film dimensions
    and the rule that day 1 fits on one whole film. If the geometry is wrong,
    every measurement the reader is asked to make is wrong with it.
    """

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
            """mg of buprenorphine per mm² for one official strength."""
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


class TestMultiFilmDays(unittest.TestCase):
    """Days whose dose is bigger than one film.

    A 16 mg start on 8 mg strips is two films a day. The dose arithmetic is
    unchanged — it is all milligrams — but the physical instruction is not, and
    everything the reader measures comes out of film_layout(). These pin the two
    properties that make it safe to follow: nothing is lost between the films,
    and the sliver is never split across two of them.
    """

    LADDERS = [
        dict(start_mg=16.0, strip_mg=8.0),
        dict(start_mg=16.0, n=3),
        dict(start_mg=24.0, n=8),
        dict(start_mg=13.0, switch_2mg=False),
        dict(start_mg=40.0, n=2, target_mg=8.0),
        dict(start_mg=20.0, film_strength_mg=12.0),
        dict(start_mg=8.0),
        dict(start_mg=2.0, strip_mg=2.0),
    ]

    def test_the_pieces_add_back_up_to_the_day(self):
        # Nothing may go missing between films: the whole ones plus the cut ones
        # have to equal the day's total take and save, to the millimetre.
        for opts in self.LADDERS:
            sched = build_schedule(**opts)
            for row in sched.rows:
                full = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
                take = row.take_films * full + row.cut_take_mm + row.short_take_mm
                save = row.save_films * full + row.cut_save_mm
                self.assertAlmostEqual(take, row.piece_mm - row.cut_mm, places=9, msg=str(opts))
                self.assertAlmostEqual(save, row.cut_mm, places=9, msg=str(opts))
                self.assertAlmostEqual(take + save, row.piece_mm, places=9, msg=str(opts))

    def test_every_cut_fits_on_the_film_it_is_marked_on(self):
        # The point of the layout: a mark that runs off the end of the strip is
        # not a mark. Both cut films must fit inside one film's length.
        for opts in self.LADDERS:
            sched = build_schedule(**opts)
            for row in sched.rows:
                full = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
                self.assertLessEqual(row.cut_take_mm + row.cut_save_mm, full + 1e-9, msg=str(opts))
                self.assertLessEqual(row.short_take_mm, full + 1e-9, msg=str(opts))
                for v in (row.cut_take_mm, row.cut_save_mm, row.short_take_mm):
                    self.assertGreaterEqual(v, -1e-12, msg=str(opts))

    def test_the_sliver_is_never_split_across_two_films(self):
        # Whole films can go to the jar untouched, but the part-film remainder
        # of the sliver is one piece on one film — it is the piece being
        # measured, so splitting it would make the measurement meaningless.
        for opts in self.LADDERS:
            sched = build_schedule(**opts)
            for row in sched.rows:
                full = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
                self.assertAlmostEqual(
                    row.cut_save_mm, row.cut_mm - row.save_films * full, places=9, msg=str(opts)
                )

    def test_film_count_is_the_fewest_that_hold_the_day(self):
        for opts in self.LADDERS:
            sched = build_schedule(**opts)
            for row in sched.rows:
                full = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
                least = math.ceil(row.piece_mm / full - 1e-9)
                # A second cut film is sometimes unavoidable where the ladder
                # crosses a whole-film boundary, so one over the minimum is the
                # worst case — never two over.
                self.assertGreaterEqual(row.films_out, least, msg=str(opts))
                self.assertLessEqual(row.films_out, least + 1, msg=str(opts))

    def test_a_day_inside_one_film_is_the_old_single_film_picture(self):
        # The generalisation must be exactly backward compatible, or every
        # existing cut mark moves.
        sched = build_schedule()
        for row in sched.rows:
            self.assertEqual(row.films_out, 1)
            self.assertEqual(row.take_films, 0)
            self.assertEqual(row.save_films, 0)
            self.assertEqual(row.short_take_mm, 0.0)
            self.assertAlmostEqual(row.cut_take_mm, row.piece_mm - row.cut_mm, places=12)
            self.assertAlmostEqual(row.cut_save_mm, row.cut_mm, places=12)

    def test_sixteen_mg_on_eight_mg_films_is_two_strips_one_of_them_cut(self):
        # The worked example: take two strips, one whole, and cut 1/6 off the
        # other. 1/6 of 16 mg is 2.67 mg, which is 7.33 mm of an 8 mg film.
        row = build_schedule(start_mg=16.0, strip_mg=8.0).rows[0]
        self.assertEqual(row.film_mg, 8.0)
        self.assertEqual(row.films_out, 2)
        self.assertEqual(row.take_films, 1)
        self.assertEqual(row.save_films, 0)
        self.assertEqual(row.short_take_mm, 0.0)
        self.assertAlmostEqual(row.cut_save_mm, 22.0 / 3, places=9)
        self.assertAlmostEqual(row.cut_take_mm, 22.0 - 22.0 / 3, places=9)
        self.assertAlmostEqual(row.sliver_mg, 16.0 / 6, places=9)

    def test_a_start_above_twelve_mg_falls_back_to_eight_mg_films(self):
        # No single official film holds it, so the day becomes several strips of
        # the strength people are normally tapering from.
        self.assertEqual(base_film_mg(12.5), 8.0)
        self.assertEqual(base_film_mg(16.0), 8.0)
        self.assertEqual(base_film_mg(64.0), 8.0)

    def test_film_strength_override_is_respected(self):
        row = build_schedule(start_mg=20.0, film_strength_mg=12.0).rows[0]
        self.assertEqual(row.film_mg, 12.0)
        self.assertEqual(row.films_out, 2)

    def test_short_film_appears_only_when_take_and_save_cannot_share(self):
        # Called directly, because this is the one rule the schedule rows do not
        # make obvious. 9.26 mg on an 8 mg film: the take is 7.72 mg, which is
        # almost the whole film, so the 1.54 mg sliver has nowhere to sit beside
        # it. The sliver stays whole and the leftover take moves to a second
        # film — not the other way round.
        lay = film_layout(9.2593, 9.2593 / 6, 8.0, 22.0)
        self.assertGreater(lay.short_take_mm, 0.0)
        self.assertAlmostEqual(lay.cut_take_mm + lay.cut_save_mm, 22.0, places=6)
        self.assertAlmostEqual(lay.cut_save_mm, 9.2593 / 6 * 22.0 / 8.0, places=9)

        # A dose that fits on one film keeps both on it, with no second film.
        lay = film_layout(8.0, 8.0 / 6, 8.0, 22.0)
        self.assertEqual(lay.short_take_mm, 0.0)
        self.assertEqual(lay.films_out, 1)

    def test_a_sliver_bigger_than_a_film_banks_whole_films(self):
        # n = 2 off a 40 mg day saves 20 mg — two whole 8 mg films plus 4 mg.
        row = build_schedule(start_mg=40.0, n=2, target_mg=8.0).rows[0]
        self.assertEqual(row.save_films, 2)
        self.assertAlmostEqual(row.cut_save_mm, 4.0 * 22.0 / 8.0, places=9)


class TestSummary(unittest.TestCase):
    """The headline figures and the n = 6 / 8 / 10 comparison.

    Mostly about consistency of convention — the ~2 mg and ~1 mg milestones
    once reported opposite ends of their cycle, five days apart on the default
    run — and about the comparison being an honest like-for-like.
    """

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
