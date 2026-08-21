#!/usr/bin/env python3
"""Math checks for SAS-Taper. Run: python3 test_taper.py (or pytest).

These pin the arithmetic the schedule is built on, not the wording around it.
No extra packages needed.
"""

from __future__ import annotations

import math
import unittest
from collections import Counter

from taper import (
    CUT_MODES,
    FRAC_LONG_DIVS,
    FRAC_SHORT_DIVS,
    base_film_mg,
    build_schedule,
    cut_context,
    film_layout,
    fraction_cut,
    kit_line,
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
    is wrong, and the closed forms are what the summary cards quote.
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


class TestLinearCutMode(unittest.TestCase):
    """The constant-step mode: cut the same amount every cycle.

    Geometric cuts 1/n of the piece in your hand, so the step shrinks with the
    dose and the ladder approaches zero without arriving. Linear cuts 1/n of the
    ORIGINAL strip every time, same milligrams, same millimetres, so the dose
    falls in equal steps and lands on zero.

    These pin the four properties that make it that mode and not the other one,
    plus the ways it deliberately differs from geometric.
    """

    def test_the_cut_never_changes(self):
        # The defining property, in both units. If either drifts it is not this
        # mode any more.
        for start, n in [(8.0, 6), (16.0, 4), (2.0, 10), (12.5, 3), (32.0, 8)]:
            sched = build_schedule(start_mg=start, n=n, cut_mode="linear", target_mg=0)
            slivers = {round(r.sliver_mg, 12) for r in sched.rows}
            cuts = {round(r.cut_mm, 12) for r in sched.rows}
            self.assertEqual(len(slivers), 1, f"start={start} n={n} sliver moved: {slivers}")
            self.assertEqual(len(cuts), 1, f"start={start} n={n} cut moved: {cuts}")
            self.assertAlmostEqual(sched.rows[0].sliver_mg, start / n, places=12)

    def test_the_dose_falls_in_equal_steps(self):
        for start, n in [(8.0, 6), (16.0, 4), (12.0, 5), (32.0, 8)]:
            sched = build_schedule(start_mg=start, n=n, cut_mode="linear", target_mg=0)
            doses = [r.daily_mg for r in sched.rows]
            steps = [a - b for a, b in zip(doses, doses[1:])]
            for s in steps:
                self.assertAlmostEqual(s, start / n, places=9, msg=f"start={start} n={n}")

    def test_it_reaches_zero_after_n_minus_one_doses(self):
        # The whole point: a fixed number of cycles to nothing, rather than an
        # asymptote you have to pick a stopping point on.
        for start in (8.0, 16.0, 4.0, 32.0):
            for n in (2, 3, 6, 10, 20):
                sched = build_schedule(start_mg=start, n=n, cut_mode="linear", target_mg=0)
                self.assertEqual(len(sched.rows), n - 1, f"start={start} n={n}")
                self.assertAlmostEqual(sched.rows[-1].daily_mg, start / n, places=9)
                self.assertEqual(sched.zero_day, sched.rows[-1].day_end + 1)

    def test_no_cycle_ever_has_a_zero_or_negative_dose(self):
        # A cycle of n days at 0 mg is not an instruction. The ladder has to end
        # before it, with zero_day reporting the landing instead.
        for start in (0.5, 2.0, 8.0, 32.0):
            for n in (2, 5, 6, 13, 30):
                sched = build_schedule(start_mg=start, n=n, cut_mode="linear", target_mg=0)
                for row in sched.rows:
                    self.assertGreater(row.daily_mg, 0.0, f"start={start} n={n} c{row.cycle}")

    def test_the_closed_form_matches_the_simulation(self):
        for start in (2.0, 8.0, 16.0):
            for n in (3, 6, 10):
                for hold in (None, 9):
                    sched = build_schedule(
                        start_mg=start, n=n, hold_days=hold, cut_mode="linear", target_mg=0
                    )
                    self.assertAlmostEqual(
                        sched.total_mg,
                        ingested_closed_form(start, n, len(sched.rows), hold, "linear"),
                        places=9, msg=f"start={start} n={n} hold={hold}",
                    )
                    # A finished run's total is the whole-run figure, not a bound.
                    self.assertAlmostEqual(
                        sched.total_mg, sched.ceiling_mg, places=9,
                        msg=f"start={start} n={n} hold={hold}",
                    )

    def test_it_still_stops_at_a_target_above_zero(self):
        # Doses are 6.67, 5.33, 4.00, 2.67 ... and "reach" includes the first
        # one at or under the target, so a 3 mg target lands on 2.67.
        sched = build_schedule(start_mg=8.0, n=6, cut_mode="linear", target_mg=3.0)
        self.assertAlmostEqual(sched.end_daily_mg, 8.0 * 2 / 6, places=9)
        self.assertIsNone(sched.zero_day, "stopped at a target, so it never reached zero")

    def test_the_percentage_step_grows_every_cycle(self):
        """Not a defect. The arithmetic of a constant step, but the reason the
        mode needs a warning rather than just an option. Equal milligrams are
        growing percentages, and the growth lands on the hardest part."""
        sched = build_schedule(start_mg=8.0, n=6, cut_mode="linear", target_mg=0)
        doses = [r.daily_mg for r in sched.rows]
        drops = [100 * (a - b) / a for a, b in zip(doses, doses[1:])]
        self.assertEqual([round(d) for d in drops], [20, 25, 33, 50])
        for a, b in zip(drops, drops[1:]):
            self.assertGreater(b, a)

    def test_the_rescues_geometric_needs_are_switched_off(self):
        # The 2 mg switch exists because the geometric sliver gets too thin to
        # cut; here it never does. Changing n below 3 mg would change the step
        # the mode is defined by. Both are ignored, and nothing pretends
        # otherwise in the result.
        sched = build_schedule(start_mg=8.0, n=6, cut_mode="linear", target_mg=0,
                               switch_2mg=True, n_below_3mg=10)
        self.assertFalse(any(r.switched_2mg for r in sched.rows))
        self.assertFalse(any(r.n_changed for r in sched.rows))
        self.assertFalse(sched.switch_never_fired)
        self.assertTrue(all(r.film_mg == sched.base_film_mg for r in sched.rows))
        self.assertTrue(all(r.n == 6 for r in sched.rows))

    def test_the_cut_never_gets_thin(self):
        # The practical pay-off, and the reason the 2 mg switch is unnecessary.
        for n in (3, 6, 10, 20):
            sched = build_schedule(start_mg=8.0, n=n, cut_mode="linear", target_mg=0)
            thin = [r.cycle for r in sched.rows if r.cut_warn]
            geo = build_schedule(start_mg=8.0, n=n, cut_mode="geometric",
                                 switch_2mg=False, target_mg=0.1)
            if any(r.cut_warn for r in geo.rows):
                self.assertEqual(thin, [], f"n={n}: a constant cut went thin")

    def test_geometric_is_the_default_and_is_unchanged(self):
        self.assertEqual(build_schedule().cut_mode, "geometric")
        a = build_schedule()
        b = build_schedule(cut_mode="geometric")
        self.assertEqual([r.daily_mg for r in a.rows], [r.daily_mg for r in b.rows])
        self.assertIsNone(a.zero_day)

    def test_an_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            build_schedule(cut_mode="quadratic")
        self.assertEqual(set(CUT_MODES), {"geometric", "linear"})


class TestMultiFilmDays(unittest.TestCase):
    """Days whose dose is bigger than one film.

    A 32 mg start on 8 mg strips is four of them. The dose arithmetic is
    unchanged. It is all milligrams, but the physical instruction is not, and
    everything the reader measures comes out of film_layout(). These are worked
    examples a reader can follow; TestMultiFilmMatrix covers the space.
    """

    LADDERS = [
        dict(start_mg=16.0, strip_mg=8.0),
        dict(start_mg=32.0, target_mg=0.5),
        dict(start_mg=16.0, n=3),
        dict(start_mg=24.0, n=8),
        dict(start_mg=13.0, switch_2mg=False),
        dict(start_mg=40.0, n=2, target_mg=8.0),
        dict(start_mg=20.0, film_strength_mg=12.0),
        dict(start_mg=8.0),
        dict(start_mg=2.0, strip_mg=2.0),
    ]

    def test_the_pieces_add_back_up_to_the_day(self):
        # Nothing may go missing: the whole films plus the marked one have to
        # equal the day's take, and the marked film's sliver plus whatever runs
        # onto unopened film has to equal the day's save.
        for opts in self.LADDERS:
            sched = build_schedule(**opts)
            for row in sched.rows:
                full = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
                take = row.take_films * full + row.cut_take_mm
                self.assertAlmostEqual(take, row.piece_mm - row.cut_mm, places=9, msg=str(opts))
                self.assertAlmostEqual(
                    row.cut_save_mm + row.spare_mm, row.cut_mm, places=9, msg=str(opts)
                )

    def test_only_one_film_a_day_is_ever_cut(self):
        # The point of the layout. Two marked films would mean two measurements
        # a day; a mark past the end of a film would mean none that works.
        for opts in self.LADDERS:
            sched = build_schedule(**opts)
            for row in sched.rows:
                full = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
                marked = 1 if row.cut_take_mm > 1e-9 else 0
                self.assertEqual(row.films_out, row.take_films + marked, msg=str(opts))
                self.assertLessEqual(row.cut_take_mm + row.cut_save_mm, full + 1e-9, msg=str(opts))
                for v in (row.cut_take_mm, row.cut_save_mm, row.spare_mm):
                    self.assertGreaterEqual(v, -1e-12, msg=str(opts))

    def test_a_day_inside_one_film_is_the_old_single_film_picture(self):
        # The generalisation must be exactly backward compatible, or every
        # existing cut mark moves.
        sched = build_schedule()
        for row in sched.rows:
            self.assertEqual(row.films_out, 1)
            self.assertEqual(row.take_films, 0)
            self.assertEqual(row.spare_mm, 0.0)
            self.assertAlmostEqual(row.cut_take_mm, row.piece_mm - row.cut_mm, places=12)
            self.assertAlmostEqual(row.cut_save_mm, row.cut_mm, places=12)

    def test_sixteen_mg_on_eight_mg_films_is_two_strips_one_of_them_cut(self):
        # 1/6 of 16 mg is 2.67 mg. The take is 13.33 mg, one whole film plus
        # 5.33 mg, so one strip goes down whole and the other is marked.
        row = build_schedule(start_mg=16.0, strip_mg=8.0).rows[0]
        self.assertEqual(row.film_mg, 8.0)
        self.assertEqual(row.films_out, 2)
        self.assertEqual(row.take_films, 1)
        self.assertEqual(row.spare_mm, 0.0)
        # take 13.33 mg = one whole 8 mg film + 5.33 mg, which is 22 x 2/3 mm.
        self.assertAlmostEqual(row.cut_take_mm, 22.0 * 2.0 / 3.0, places=9)
        self.assertAlmostEqual(row.cut_save_mm, 22.0 / 3.0, places=9)
        self.assertAlmostEqual(row.sliver_mg, 16.0 / 6, places=9)

    def test_the_sliver_can_run_onto_a_strip_you_never_open(self):
        # 32 mg, cycle 2: the strip is 73.3 mm, which spans four films, but the
        # take only reaches into the third. The fourth would be opened purely to
        # put it in the jar, so it is left in the box and counted in spare_mm.
        row = build_schedule(start_mg=32.0, target_mg=0.5).rows[1]
        self.assertEqual(row.films_out, 3)
        self.assertEqual(row.take_films, 2)
        self.assertAlmostEqual(row.piece_mm, 73.333333, places=4)
        self.assertAlmostEqual(row.cut_take_mm, 17.111111, places=4)
        self.assertAlmostEqual(row.cut_save_mm, 4.888888, places=4)
        self.assertAlmostEqual(row.spare_mm, 7.333333, places=4)
        self.assertAlmostEqual(row.cut_save_mm + row.spare_mm, row.cut_mm, places=9)

    def test_a_take_that_lands_on_a_film_boundary_needs_no_cut(self):
        # 8 mg of 2 mg film at n = 4: the take is 6 mg, exactly three films, so
        # there is nothing to measure and the sliver's film stays in the box.
        lay = film_layout(8.0, 2.0, 2.0, 22.0)
        self.assertEqual(lay.films_out, 3)
        self.assertEqual(lay.take_films, 3)
        self.assertEqual(lay.cut_take_mm, 0.0)
        self.assertEqual(lay.cut_save_mm, 0.0)
        self.assertAlmostEqual(lay.spare_mm, 22.0, places=9)

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


class TestMultiFilmMatrix(unittest.TestCase):
    """Every invariant, over the whole space of doses up to 32 mg.

    TestMultiFilmDays covers named cases a reader can follow. This covers the
    space: start doses from 1 to 32 mg against all four official film
    strengths, n from 2 to 30, three film lengths, the 2 mg switch both ways,
    and it checks every cycle of every one of those ladders, not just the
    first. A 32 mg start on 2 mg films is sixteen strips a day, which is the
    far corner of what the inputs allow.

    The schedules are built once in setUpClass because each property below
    walks the whole grid.
    """

    STARTS = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 9.26, 10.0, 12.0, 13.0,
              16.0, 18.0, 20.0, 24.0, 28.0, 32.0]
    NS = [2, 3, 4, 6, 10, 30]
    STRENGTHS = [None, 2.0, 4.0, 8.0, 12.0]
    MODES = ["geometric", "linear"]

    @classmethod
    def setUpClass(cls):
        cls.grid = []
        for mode in cls.MODES:
            for start in cls.STARTS:
                for n in cls.NS:
                    for strength in cls.STRENGTHS:
                        cls.grid.append(cls._build(start, n, strength, 22.0, True, mode))
            # Non-default film lengths, and the 2 mg switch off, on a thinner
            # slice: the length only scales millimetres, so it does not need
            # the full cross.
            for start in cls.STARTS:
                for strength in cls.STRENGTHS:
                    for length in (20.0, 30.0):
                        cls.grid.append(cls._build(start, 6, strength, length, True, mode))
                    cls.grid.append(cls._build(start, 8, strength, 22.0, False, mode))

    @classmethod
    def _build(cls, start, n, strength, length, switch, mode="geometric"):
        sched = build_schedule(
            start_mg=start, n=n, film_strength_mg=strength, film_mm=length,
            film_2mg_mm=length, switch_2mg=switch, strip_mg=8.0,
            target_mg=min(1.0, start / 2), cut_mode=mode,
        )
        label = (f"{mode} start={start:g} n={n} strength={strength} "
                 f"len={length:g} switch={switch}")
        return label, sched

    def each_schedule(self):
        """(label, schedule, whole-film length for its base strength).

        For the properties that compare a cycle with the one before it, which
        each_row() cannot see.
        """
        for label, sched in self.grid:
            yield label, sched

    def each_row(self):
        """(label, schedule, row, whole-film length) for every cycle in the grid."""
        for label, sched in self.grid:
            for row in sched.rows:
                full = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
                yield f"{label} cycle={row.cycle}", sched, row, full

    def test_the_matrix_reaches_the_cases_it_claims_to(self):
        """A grid that only ever produced one-film days would pass everything
        below while testing nothing. Pin the shapes it has to contain."""
        seen = Counter()
        widest = 0
        for _, _, row, _ in self.each_row():
            seen["rows"] += 1
            widest = max(widest, row.films_out)
            if row.films_out > 1:
                seen["multi-film days"] += 1
            else:
                seen["single-film days"] += 1
            if row.spare_mm > 1e-9:
                seen["days whose sliver runs onto unopened film"] += 1
            if row.cut_take_mm <= 1e-9:
                seen["days with nothing to cut"] += 1
            if row.take_films:
                seen["days with whole films taken"] += 1
        self.assertGreater(seen["rows"], 5000, seen)
        self.assertGreater(seen["single-film days"], 1000, seen)
        self.assertGreater(seen["multi-film days"], 1000, seen)
        self.assertGreater(seen["days whose sliver runs onto unopened film"], 100, seen)
        self.assertGreater(seen["days with nothing to cut"], 10, seen)
        self.assertGreater(seen["days with whole films taken"], 1000, seen)
        # 32 mg of 2 mg film is a fourteen-strip take.
        self.assertGreaterEqual(widest, 14, f"widest day was {widest} films")

    def test_nothing_is_lost_between_the_films(self):
        for tag, _, row, full in self.each_row():
            take = row.take_films * full + row.cut_take_mm
            self.assertAlmostEqual(take, row.piece_mm - row.cut_mm, places=8, msg=tag)
            self.assertAlmostEqual(row.cut_save_mm + row.spare_mm, row.cut_mm, places=8, msg=tag)
            self.assertAlmostEqual(take + row.cut_mm, row.piece_mm, places=8, msg=tag)

    def test_the_milligrams_match_the_millimetres(self):
        # Length fraction = dose fraction is the whole basis of the method, and
        # it has to survive being spread over several films.
        for tag, _, row, full in self.each_row():
            per_mm = row.film_mg / full
            take = row.take_films * full + row.cut_take_mm
            self.assertAlmostEqual(take * per_mm, row.daily_mg, places=8, msg=tag)
            self.assertAlmostEqual(
                (row.cut_save_mm + row.spare_mm) * per_mm, row.sliver_mg, places=8, msg=tag
            )

    def test_exactly_one_film_a_day_is_ever_cut(self):
        # Two marked films would mean two measurements a day, which is the thing
        # the layout exists to avoid.
        for tag, _, row, full in self.each_row():
            marked = 1 if row.cut_take_mm > 1e-9 else 0
            self.assertEqual(row.films_out, row.take_films + marked, msg=tag)
            if marked:
                self.assertGreater(row.cut_save_mm, 0.0, msg=f"{tag}: marked film with no sliver")

    def test_no_mark_ever_runs_off_the_end_of_a_film(self):
        for tag, _, row, full in self.each_row():
            self.assertLessEqual(row.cut_take_mm + row.cut_save_mm, full + 1e-9, msg=tag)
            self.assertLess(row.cut_take_mm, full + 1e-9, msg=tag)
            for name, v in (("cut_take", row.cut_take_mm), ("cut_save", row.cut_save_mm),
                            ("spare", row.spare_mm)):
                self.assertGreaterEqual(v, -1e-12, msg=f"{tag} {name}")

    def test_you_open_exactly_the_films_the_dose_needs(self):
        # Not one more. A film the take never reaches would be opened only to
        # put it straight in the jar, so it stays in the box. That is the whole
        # reason a day can need fewer films than its strip spans.
        for tag, _, row, full in self.each_row():
            take_mm = row.piece_mm - row.cut_mm
            self.assertEqual(row.films_out, math.ceil(take_mm / full - 1e-9), msg=tag)
            self.assertLessEqual(row.films_out, math.ceil(row.piece_mm / full - 1e-9), msg=tag)

    def test_take_and_save_partition_the_films_you_opened(self):
        """Nothing between the two, in either unit.

        This is the promise the tinted block of the schedule makes: what you do
        not swallow, you jar, and the two add back up to whole films with
        nothing unaccounted for.
        """
        for tag, _, row, full in self.each_row():
            self.assertAlmostEqual(
                row.take_mm + row.save_mm, row.films_out * full, places=8, msg=tag)
            self.assertAlmostEqual(
                row.save_mg + row.daily_mg, row.films_out * row.film_mg, places=8, msg=tag)
            per_mm = row.film_mg / full
            self.assertAlmostEqual(row.take_mm * per_mm, row.daily_mg, places=8, msg=tag)
            self.assertAlmostEqual(row.save_mm * per_mm, row.save_mg, places=8, msg=tag)
            self.assertGreaterEqual(row.save_mm, -1e-12, msg=tag)
            self.assertLessEqual(row.save_mm, full + 1e-9, msg=tag)

    def test_delta_save_is_the_sliver_whenever_it_is_reported(self):
        """The identity the whole column rests on.

        take(k−1) is piece(k), so the difference of two "full minus take"
        figures is exactly this cycle's sliver, as long as the day still opens
        the same films off the same strip. The one reported case where it is
        not the sliver is the first cut of a run, where the comparison is
        against an empty jar and the delta is the whole save.
        """
        checked = first_cuts = 0
        for tag, sched in self.each_schedule():
            prev = None                       # the last cycle that cut a film
            for row in sched.rows:
                if row.delta_save_mm is not None:
                    self.assertGreaterEqual(
                        row.delta_save_mm, -1e-12,
                        msg=f"{tag} cycle={row.cycle}: the jar went backwards")
                    if prev is None:
                        first_cuts += 1
                        self.assertAlmostEqual(
                            row.delta_save_mm, row.save_mm, places=8,
                            msg=f"{tag} cycle={row.cycle}")
                    else:
                        checked += 1
                        self.assertAlmostEqual(
                            row.delta_save_mm, row.cut_mm, places=8,
                            msg=f"{tag} cycle={row.cycle}")
                        self.assertAlmostEqual(
                            row.delta_save_mm, row.save_mm - prev.save_mm, places=8,
                            msg=f"{tag} cycle={row.cycle}")
                if row.cut_take_mm > 1e-9:
                    prev = row
        self.assertGreater(checked, 5000, "almost no deltas were compared")
        self.assertGreater(first_cuts, 500, "no first cuts were compared")

    def test_delta_save_is_blank_exactly_when_it_should_be(self):
        """Three reasons and no others, each one actually reached by the grid.

        A dash that appeared for a fourth, unnamed reason would be a column
        the reader cannot trust; a reason that never fires would be a claim in
        the glossary with nothing behind it.
        """
        seen = Counter()
        for tag, sched in self.each_schedule():
            prev = None
            for row in sched.rows:
                no_cut = row.cut_take_mm <= 1e-9
                dropped = prev is not None and prev.take_films != row.take_films
                reason = (
                    "no cut" if no_cut else
                    "2 mg restart" if row.switched_2mg else
                    "film count changed" if dropped else None
                )
                if row.delta_save_mm is None:
                    self.assertIsNotNone(
                        reason, msg=f"{tag} cycle={row.cycle}: blank for no stated reason")
                    seen[reason] += 1
                else:
                    self.assertIsNone(
                        reason, msg=f"{tag} cycle={row.cycle}: {reason} should blank it")
                if not no_cut:
                    prev = row
        for reason in ("no cut", "2 mg restart", "film count changed"):
            self.assertGreater(seen[reason], 0, f"the grid never reached: {reason}\n{seen}")

    def test_the_save_grows_every_cycle_it_is_comparable(self):
        """The claim the method is sold on, the jar's share keeps rising.

        Only between reported deltas: a 2 mg restart and a dropped film both
        genuinely shrink the save, which is why they show a dash rather than a
        negative number.
        """
        grew = 0
        for tag, sched in self.each_schedule():
            prev = None
            for row in sched.rows:
                if row.delta_save_mm is not None and prev is not None:
                    if row.cut_mm > 1e-9:
                        self.assertGreater(
                            row.save_mm, prev.save_mm,
                            msg=f"{tag} cycle={row.cycle}: the save did not grow")
                        grew += 1
                if row.cut_take_mm > 1e-9:
                    prev = row
        self.assertGreater(grew, 5000, "almost nothing was checked for growth")

    def test_the_sliver_is_measured_from_the_piece_not_the_film(self):
        """The mark is cut_save_mm in from the right of the strip ON the marked
        film. On a cycle with an already-off region the film's own right end is
        further out, and measuring from there would put the cut millimetres
        wrong, so cut_context has to hand the caller the piece, not the film.
        """
        ghosted = 0
        for tag, sched, row, full in self.each_row():
            ctx = cut_context(row, sched)
            piece = ctx["marked_piece_mm"]
            self.assertAlmostEqual(piece, row.cut_take_mm + row.cut_save_mm, places=12, msg=tag)
            self.assertLessEqual(piece, full + 1e-9, msg=tag)
            # Measuring the sliver back from the right of the piece lands on the
            # TAKE/SAVE line. Measuring from the film would not, when they differ.
            self.assertAlmostEqual(piece - ctx["cut_save_mm"], row.cut_take_mm, places=12, msg=tag)
            if ctx["ghost_mm"] > 0.05 and not ctx["no_cut"]:
                ghosted += 1
                self.assertLess(piece, full - 1e-9, msg=tag)
        self.assertGreater(ghosted, 1000, "no cycles with an already-off region were checked")

    def test_a_day_of_whole_films_reports_no_cut(self):
        checked = 0
        for tag, sched, row, full in self.each_row():
            ctx = cut_context(row, sched)
            if not ctx["no_cut"]:
                continue
            checked += 1
            self.assertEqual(row.cut_take_mm, 0.0, msg=tag)
            self.assertEqual(row.cut_save_mm, 0.0, msg=tag)
            self.assertEqual(ctx["ruler"], "", msg=tag)
            self.assertEqual(row.films_out, row.take_films, msg=tag)
            self.assertGreaterEqual(row.take_films, 1, msg=tag)
            # Whatever was going to be saved is entirely on film left in the box.
            self.assertAlmostEqual(row.spare_mm, row.cut_mm, places=8, msg=tag)
        self.assertGreater(checked, 10, "no whole-films-only cycles were checked")

    def test_every_multi_film_cycle_states_its_film_count(self):
        # kit_line() is what both the CLI and the site print above the drawing;
        # an empty one on a multi-film day would leave the reader thinking a
        # three-strip day is a one-strip day.
        for tag, sched, row, full in self.each_row():
            line = kit_line(row, full)
            if row.films_out > 1:
                self.assertIn(f"{row.films_out} \u00d7", line, msg=tag)
                if row.spare_mm > 1e-9:
                    self.assertIn("do not need to open", line, msg=tag)
            else:
                self.assertEqual(line, "", msg=tag)


class TestTakeAndSave(unittest.TestCase):
    """The four numbers you read standing at the strip, and the fifth that says
    the jar is filling faster.

    take_mm / save_mm partition the film you opened; save_mg / daily_mg do the
    same in milligrams. delta_save_mm is how much more the jar gets than the
    last cycle that cut a film. The growth the method promises, and is None
    wherever that comparison would be against a different thing.
    """

    def test_take_and_save_are_the_whole_film(self):
        """Nothing between the two: what you do not swallow, you jar."""
        sched = build_schedule(8.0, 6)
        for row in sched.rows:
            full = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
            self.assertAlmostEqual(
                row.take_mm + row.save_mm, row.films_out * full, places=9,
                msg=f"cycle {row.cycle}",
            )

    def test_the_worked_default(self):
        """8 mg, n = 6, 22 mm film, by hand.

        Cycle 1 takes 5/6 of a 22 mm film, 18.33 mm, and jars the other
        3.67 mm. Cycle 2 takes 5/6 of *that*, 15.28 mm off a fresh film, so the
        jar gets 6.72 mm: the same 3.67 mm sliver plus the 3.06 mm the ladder
        moved the mark. Δ save is that 3.06 mm.
        """
        rows = build_schedule(8.0, 6).rows
        self.assertAlmostEqual(rows[0].take_mm, 18.3333, places=3)
        self.assertAlmostEqual(rows[0].save_mm, 3.6667, places=3)
        self.assertAlmostEqual(rows[0].save_mg, 1.3333, places=3)
        self.assertAlmostEqual(rows[0].delta_save_mm, 3.6667, places=3)
        self.assertAlmostEqual(rows[1].take_mm, 15.2778, places=3)
        self.assertAlmostEqual(rows[1].save_mm, 6.7222, places=3)
        self.assertAlmostEqual(rows[1].save_mg, 2.4444, places=3)
        self.assertAlmostEqual(rows[1].delta_save_mm, 3.0556, places=3)

    def test_linear_mode_saves_the_same_extra_every_cycle(self):
        """The whole point of the mode: one mark, moved the same distance."""
        rows = build_schedule(8.0, 6, cut_mode="linear").rows
        deltas = [r.delta_save_mm for r in rows]
        self.assertTrue(all(d is not None for d in deltas), deltas)
        for d in deltas:
            self.assertAlmostEqual(d, 22.0 / 6, places=9)
        # And the save itself climbs by that step, film by film.
        for i, row in enumerate(rows):
            self.assertAlmostEqual(row.save_mm, (i + 1) * 22.0 / 6, places=9)

    def test_the_2mg_restart_has_no_delta(self):
        """A fresh 2 mg film is a different strip; "extra" would be nonsense."""
        rows = build_schedule(8.0, 6).rows
        switches = [r for r in rows if r.switched_2mg]
        self.assertTrue(switches, "the default run should switch to 2 mg film")
        for row in switches:
            self.assertIsNone(row.delta_save_mm, f"cycle {row.cycle}")
            # The save is real, though: it is the first cut of a new strip.
            self.assertGreater(row.save_mm, 0.0)

    def test_dropping_a_film_has_no_delta(self):
        """16 mg on 8 mg strips opens two films a day, then one.

        On the cycle where the second film stops being needed the save falls
        rather than grows, because far less film is opened at all. Comparing
        that with the previous cycle would say the jar shrank, which is true of
        the film and false of the taper, so there is nothing to report.
        """
        rows = build_schedule(16.0, 6).rows
        drops = [
            (prev, row) for prev, row in zip(rows, rows[1:])
            if row.take_films < prev.take_films and not row.switched_2mg
        ]
        self.assertTrue(drops, "a 16 mg start should drop from two films to one")
        for prev, row in drops:
            self.assertIsNone(row.delta_save_mm, f"cycle {row.cycle}")
            self.assertLess(row.save_mm, prev.save_mm)

    def test_a_whole_film_day_saves_nothing_and_keeps_the_baseline(self):
        """No mark means no jar, and the next real cut compares with the last
        real cut rather than with zero."""
        sched = build_schedule(16.0, 2, film_strength_mg=8.0)
        cut_rows = [r for r in sched.rows if r.cut_take_mm > 1e-9]
        no_cut = [r for r in sched.rows if r.cut_take_mm <= 1e-9]
        self.assertTrue(no_cut, "a 16 mg n=2 run should land on a film boundary")
        for row in no_cut:
            self.assertEqual(row.save_mm, 0.0, f"cycle {row.cycle}")
            self.assertEqual(row.save_mg, 0.0, f"cycle {row.cycle}")
            self.assertIsNone(row.delta_save_mm, f"cycle {row.cycle}")
        # Every delta that is reported still lines up with a cutting cycle.
        for prev, row in zip(cut_rows, cut_rows[1:]):
            if row.delta_save_mm is None:
                continue
            self.assertAlmostEqual(
                row.delta_save_mm, row.save_mm - prev.save_mm, places=9,
                msg=f"cycle {row.cycle}",
            )


class TestFractionCut(unittest.TestCase):
    """The folded-grid cut: take whole cells instead of measuring millimetres.

    This is an approximation by construction, so the tests are mostly about it
    being an honest one. The piece it describes is really the fraction it
    claims, the error is really the error, and it never quietly picks something
    further out than it was allowed to.
    """

    FULL, WIDE = 22.0, 12.8

    def each(self, tol_mg=0.0, film_mg=8.0):
        """Walk the whole 0 to 1 range in fine steps, plus the exact grid points."""
        seen = set()
        for i in range(1, 1001):
            seen.add(i / 1000)
        for L in FRAC_LONG_DIVS:
            for S in FRAC_SHORT_DIVS:
                for k in range(1, L * S + 1):
                    seen.add(k / (L * S))
        for want in sorted(seen):
            fc = fraction_cut(want, film_mg, self.FULL, self.WIDE, tol_mg=tol_mg)
            yield want, fc

    def test_the_piece_is_the_fraction_it_claims(self):
        """columns + tab must add back up to cells, and cells to the fraction."""
        for want, fc in self.each():
            tag = f"want={want:.4f}"
            self.assertIsNotNone(fc, tag)
            self.assertEqual(fc.columns * fc.short_div + fc.tab_cells, fc.cells, tag)
            self.assertLess(fc.tab_cells, fc.short_div, tag)
            self.assertLessEqual(fc.cells, fc.long_div * fc.short_div, tag)
            self.assertGreater(fc.cells, 0, tag)
            self.assertAlmostEqual(
                fc.fraction, fc.cells / (fc.long_div * fc.short_div), places=12, msg=tag)
            self.assertAlmostEqual(fc.dose_mg, fc.fraction * 8.0, places=12, msg=tag)
            self.assertAlmostEqual(
                fc.error_mg, fc.dose_mg - fc.want_mg, places=12, msg=tag)
            self.assertIn(fc.long_div, FRAC_LONG_DIVS, tag)
            self.assertIn(fc.short_div, FRAC_SHORT_DIVS, tag)

    def test_the_cut_count_matches_the_shape(self):
        """One stroke per side of the tab's column that is not a film edge.

        The drawing is built from the same numbers, so a wrong count here is a
        caption that disagrees with the picture beside it.
        """
        for want, fc in self.each():
            tag = f"want={want:.4f} {fc.label} {fc.long_div}x{fc.short_div}"
            if fc.cells == fc.long_div * fc.short_div:
                want_cuts, want_pieces = 0, 1
            elif fc.tab_cells == 0:
                want_cuts, want_pieces = 1, 1
            else:
                want_cuts = ((1 if fc.columns else 0)
                             + (1 if fc.columns + 1 < fc.long_div else 0) + 1)
                want_pieces = 2 if fc.columns else 1
            self.assertEqual(fc.cuts, want_cuts, tag)
            self.assertEqual(fc.pieces, want_pieces, tag)
            self.assertLessEqual(fc.cuts, 3, tag)

    def test_with_no_tolerance_it_takes_the_closest_there_is(self):
        best = {}
        for L in FRAC_LONG_DIVS:
            for S in FRAC_SHORT_DIVS:
                for k in range(1, L * S + 1):
                    best.setdefault("all", []).append(k / (L * S))
        grid = sorted(set(best["all"]))
        for want, fc in self.each(tol_mg=0.0):
            closest = min(abs(g - want) for g in grid)
            self.assertAlmostEqual(
                abs(fc.fraction - want), closest, places=12,
                msg=f"want={want:.4f} took {fc.label}, {closest:.6f} was available")

    def test_a_tolerance_caps_the_error_it_does_not_add_to_it(self):
        """The trap this walked into once: `best + tol` compounds, so the cut
        chosen for convenience could sit further out than the tolerance the
        reader stated. The cap is on the error itself."""
        for want, fc in self.each(tol_mg=0.18):
            closest = min(
                abs(k / (L * S) - want)
                for L in FRAC_LONG_DIVS for S in FRAC_SHORT_DIVS
                for k in range(1, L * S + 1)) * 8.0
            self.assertLessEqual(
                abs(fc.error_mg), max(closest, 0.18) + 1e-9,
                msg=f"want={want:.4f} took {fc.label} at {fc.error_mg:+.3f} mg")

    def test_a_looser_tolerance_never_asks_for_more_cuts(self):
        """Slack is only ever spent on making the cut simpler."""
        for want, tight in self.each(tol_mg=0.0):
            loose = fraction_cut(want, 8.0, self.FULL, self.WIDE, tol_mg=0.18)
            self.assertLessEqual(
                loose.cuts, tight.cuts,
                msg=f"want={want:.4f}: {tight.label} in {tight.cuts} became "
                    f"{loose.label} in {loose.cuts}")

    def test_a_plain_half_is_a_crosswise_cut(self):
        """Both 2x1 and 1x2 are "one cut" and both are exactly half. One is a
        12.8 mm stroke along the film's own edge and the other is 22 mm
        freehand down the middle, so they are not the same instruction."""
        for tol in (0.0, 0.18):
            for film, full in ((8.0, 22.0), (2.0, 22.0)):
                fc = fraction_cut(0.5, film, full, self.WIDE, tol_mg=tol)
                self.assertEqual((fc.long_div, fc.short_div), (2, 1),
                                 msg=f"half came out {fc.long_div}x{fc.short_div}")

    def test_it_is_deterministic(self):
        for want, first in self.each(tol_mg=0.12):
            again = fraction_cut(want, 8.0, self.FULL, self.WIDE, tol_mg=0.12)
            self.assertEqual(first, again, msg=f"want={want:.4f} moved")

    def test_the_brief_examples_are_all_reachable(self):
        """1/2, 1/4, 1/8, 1/12, 1/24, 1/32. The combinations the design is
        specified around. Each must come back exact, and as one piece."""
        for want, label in ((1 / 2, "1/2"), (1 / 4, "1/4"), (1 / 8, "1/8"),
                            (1 / 12, "1/12"), (1 / 24, "1/24"), (1 / 32, "1/32")):
            fc = fraction_cut(want, 8.0, self.FULL, self.WIDE)
            self.assertEqual(fc.label, label)
            self.assertTrue(fc.exact, f"{label} came back inexact")
            self.assertEqual(fc.pieces, 1, f"{label} needed {fc.pieces} pieces")

    def test_linear_mode_needs_no_ruler_at_all(self):
        """The claim the mode is sold on: a constant step lands on a simple
        fraction every single cycle, so a linear taper can be cut end to end
        without measuring anything."""
        for n in (4, 6, 8):
            sched = build_schedule(8.0, n, cut_mode="linear", target_mg=0)
            self.assertGreater(len(sched.rows), 2)
            for row in sched.rows:
                full = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
                if row.cut_take_mm <= 1e-9:
                    continue
                fc = fraction_cut(row.cut_take_mm / full, row.film_mg, full, self.WIDE)
                self.assertTrue(
                    fc.exact,
                    msg=f"n={n} cycle {row.cycle}: {fc.label} is {fc.error_mg:+.3f} mg out")

    def test_a_film_with_no_size_has_no_fraction(self):
        for bad in (dict(full_mm=0.0), dict(wide_mm=0.0), dict(film_mg=0.0)):
            kw = dict(film_mg=8.0, full_mm=22.0, wide_mm=12.8)
            kw.update(bad)
            self.assertIsNone(fraction_cut(0.5, **kw), bad)


class TestSummary(unittest.TestCase):
    """The headline figures and the n = 6 / 8 / 10 comparison.

    Mostly about consistency of convention, the ~2 mg and ~1 mg milestones
    once reported opposite ends of their cycle, five days apart on the default
    run, and about the comparison being an honest like-for-like.
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


def _count_assertions() -> dict:
    """Wrap TestCase's assert methods with a counter.

    Most of what this file checks lives inside matrix loops, so "61 tests" says
    almost nothing about how much is actually verified, one of those tests
    makes tens of thousands of assertions. Counting them keeps the number in
    the README honest without anyone having to remember to update it.
    """
    tally = {"n": 0}
    for name in dir(unittest.TestCase):
        if not name.startswith("assert") or "_" in name[6:]:
            continue
        original = getattr(unittest.TestCase, name)
        if not callable(original):
            continue

        def wrap(fn):
            def counted(self, *args, **kwargs):
                tally["n"] += 1
                return fn(self, *args, **kwargs)
            return counted

        setattr(unittest.TestCase, name, wrap(original))
    return tally


if __name__ == "__main__":
    tally = _count_assertions()
    suite = unittest.TestLoader().loadTestsFromModule(__import__("__main__"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"\n{result.testsRun} tests, {tally['n']:,} assertions")
    raise SystemExit(0 if result.wasSuccessful() else 1)
