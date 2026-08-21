#!/usr/bin/env python3
"""SAS-Taper (save-a-sliver): geometric Suboxone (buprenorphine) film-taper calculator.

Not medical advice. Bring the output to your prescriber.
Saved slivers are a buffer, not extra daily dose.
https://github.com/bhbmaster/SAS-Taper
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

DEFAULT_START_MG = 8.0
DEFAULT_N = 6
DEFAULT_FILM_MM = 22.0
DEFAULT_TARGET_MG = 1.0
DEFAULT_STRIP_MG = 8.0
DEFAULT_SWITCH_AT_MG = 2.25
DEFAULT_RX_STRIPS = 30
DEFAULT_MONTH_DAYS = 30
MAX_CYCLES = 40
CUT_MODES = ("geometric", "linear")
CUT_WARN_MM = 1.0

# Subdivisions the fraction cut is allowed to fold the film into. The long axis
# gets eighths because three successive halvings stay reproducible over 22 mm;
# the short axis stops at quarters, because at 12.8 mm an eighth is 1.6 mm and
# nobody is judging that by eye.
FRAC_LONG_DIVS = (1, 2, 3, 4, 8)
FRAC_SHORT_DIVS = (1, 2, 3, 4)
# A tab narrower than this on its short side is not handleable, whatever the
# arithmetic says.
FRAC_MIN_TAB_MM = 2.0
SITE_URL = "https://bhbmaster.github.io/SAS-Taper/"


@dataclass(frozen=True)
class FilmSpec:
    """One official Suboxone film size.

    mg / nal are the buprenorphine and naloxone content. cut_mm is the side this
    tool cuts along (22 mm on every strength, which is why the film-length input
    is the same number whichever you start on); keep_mm is the side kept at full
    width.
    """

    mg: float
    nal: float
    cut_mm: float
    keep_mm: float
    label: str

    @property
    def area_mm2(self) -> float:
        """Footprint of one whole film in mm². cut_mm × keep_mm."""
        return self.cut_mm * self.keep_mm

    @property
    def density(self) -> float:
        """Buprenorphine per mm² of film. Constant within a strength family:
        the 2 and 4 mg films share one value, the 8 and 12 mg another that is
        four times higher.
        """
        return self.mg / self.area_mm2


# Official Suboxone film sizes. Cut along cut_mm; keep keep_mm as full width.
FILM_SPECS: dict[int, FilmSpec] = {
    2: FilmSpec(2, 0.5, 22.0, 12.8, "2 mg / 0.5 mg"),
    4: FilmSpec(4, 1.0, 22.0, 25.6, "4 mg / 1 mg"),
    8: FilmSpec(8, 2.0, 22.0, 12.8, "8 mg / 2 mg"),
    12: FilmSpec(12, 3.0, 22.0, 19.2, "12 mg / 3 mg"),
}


def spec_key_for_mg(film_mg: float) -> int:
    """Round a film strength to the nearest official one at or above it.

    Args:
        film_mg: strength being cut, in mg.
    Returns:
        One of 2, 4, 8, 12, the key into FILM_SPECS. Tolerances of 0.01 absorb
        float drift from the geometric ladder, so 1.9999 still keys to 2.
    """
    if film_mg <= 2.01:
        return 2
    if film_mg <= 4.01:
        return 4
    if film_mg <= 8.01:
        return 8
    return 12


def film_spec_for_mg(film_mg: float) -> FilmSpec:
    """FilmSpec for a strength. Convenience wrapper over spec_key_for_mg."""
    return FILM_SPECS[spec_key_for_mg(film_mg)]


HOW_TO = f"""\
SAS means save-a-sliver. Source: https://github.com/bhbmaster/SAS-Taper

How to use this
  Site: {SITE_URL}  (or open index.html offline)
  CLI:  python3 taper.py
        python3 taper.py --compare
        python3 taper.py --cycle 6
        python3 taper.py --n 10 --no-switch-2mg
        python3 taper.py --start-date 2026-03-01
  Same math either way. Print / save the site, or copy this CLI output, for
  your prescriber before day 1.

Why save-a-sliver
  The hard part is often the sense of getting less, not the milligrams. Each day's
  remaining piece is framed as a complete strip, the dose you have. Surplus in
  view is easier to use; once the sliver is saved, it is not part of today's dose.
  The bank is a safety net, not extra daily supply.

The method, every day of a cycle
  1. The current piece is the "whole strip" (cycle 1: a full 8 mg film).
  2. Keep full width; cut along length only. Mark, then cut with a razor, not scissors.
  3. Cut 1/n off the RIGHT end. SAVE that sliver. TAKE the long left piece. Once daily.
  4. In practice you open a FRESH film each day, so measure the same cut from
     the other end: mark Take mm from the LEFT, take that, and everything right
     of the mark, Save mm, goes in the jar. Same cut. The save is bigger than
     the sliver because it also carries what earlier cycles took off, and it
     grows every cycle; that growth is the +Save column, and it is the sliver.
  5. After n days the save jar holds one full piece: buffer, not extra dose.
     If you eat the bank, the dose never drops.
  6. Next cycle the new whole strip is dose × (1 − 1/n). Repeat to the target.

Two cut modes (--cut-mode)
  geometric (default)  Cut 1/n off the piece in your hand. The cut shrinks as
      the dose does, so every cycle is the same PERCENTAGE step, 16.7% at n=6,
      all the way down. The dose keeps halving and never quite reaches zero, so
      you pick a target and stop there.
  linear (easier to cut)  Cut the same AMOUNT every cycle: 1/n of the original
      strip, the same milligrams and the same millimetres from the first day to
      the last. The dose falls in equal steps and lands on zero after n-1 of
      them: 8 mg at n=6 goes 6.67, 5.33, 4.00, 2.67, 1.33, then nothing.
      Easier because the mark never moves: measure once, reuse it every day,
      and it never shrinks under a millimetre where a razor stops resolving.

  Same cut, very different shape. Equal steps in milligrams are growing steps in
  percentage: that run drops 20%, then 25%, 33%, 50%, and the last step is 100%.
  The back end is where a taper is hardest and linear is at its most aggressive
  exactly there. It is much shorter and uses much less medication; neither of
  those is the same as easier. Ask your prescriber which shape suits you, and
  remember that holding a cycle is available in either mode.

If it gets rough: hold this dose another cycle (cravings matter most). Stretch the
cycle to 8-9 days or switch n to 10 below 3 mg. When the sliver is under ~1 mm,
switch to 2 mg films. Lock up saved pieces. Step the prescribed quantity down
with the dose.

More than one strip a day: a dose bigger than one film, say 16 mg on 8 mg strips,
is simply several strips, and still one cut. Take the whole ones as they are and
mark only the last; the Film column shows ×2, ×3 and so on. If the day's sliver
runs past the strips you opened, that is a strip you never need to open.

Limitation: the schedule starts on one given film size and either stays there or
switches only to 2 mg films (not 12→8→4). The official size table is a reference;
it does not change the ladder. To plan a 12 mg or 4 mg start, change --start-mg /
--strip-mg and recalc; the base film becomes the smallest official strength that
holds the start dose, or 8 mg above 12 mg where no single film holds it
(--film-strength overrides either).
"""

NOTES = """\
Practical notes
- Cut along one axis only. Keep the full width of the film and only shorten it.
  (The site's film panel offers a folding mode that cuts both axes instead; the
  arithmetic holds there because area fraction is dose fraction on an evenly
  made sheet. What you must not do is cut both axes while thinking in lengths.)
  Length fraction = dose fraction. Cutting both dimensions loses the arithmetic.
- Use a fresh razor/craft blade and a ruler on a clean mat, not scissors. Mark
  before you cut. Cutting films is not manufacturer-sanctioned; the drug is
  distributed reasonably evenly, which is why this method is widely used.
- Cutting aids. A steel ruler and a fresh blade on a mat is enough for most of
  the ladder. If your cuts wander, small purpose-made film slicers exist;
  search "Suboxone film cutter" or "subslicer". A guided cut you can repeat
  beats a freehand one you cannot.
- Doses below what you can cut. Some people move to liquid (volumetric) dosing
  at the very bottom: dissolve a film in a measured volume of water and draw a
  dose with an oral syringe. A 2 mg film in 20 mL is THEORETICALLY 0.1 mg/mL,
  arithmetic, not a measurement. It is not manufacturer-sanctioned (the
  labelling says take the film whole), buprenorphine is only sparingly
  water-soluble so the real concentration can differ from the calculated one, a
  homemade solution is not sterile, and you only absorb what you hold under the
  tongue. Raise it with your prescriber first; quartered 2 mg films, a different
  product, or a compounded liquid may be the better route.
- Saved slivers are surplus / a safety net. Do not add them back into the daily
  dose or the taper never drops. Store airtight and dry, separated by wax paper,
  and keep them locked up. Buprenorphine is severely dangerous to kids and pets.
- The low end is where cutting 8 mg films breaks down. A ~1 mm sliver is already
  in the noise. Ask your prescriber for 2 mg films before you need them (around
  the time daily dose is heading through ~4 mg toward ~2 mg). A 2 mg film is one
  quarter the density, so the same dose is four times longer on it and the same
  cut is four times more forgiving.
- A dose over one film is just more films, and still only one cut. Take the
  whole strips as they are and mark the last one; the cut marks name it. If the
  day's sliver runs past the strips you opened, that is a strip you simply do
  not need to open. Leave it in the box.
- Holding is not failure. If a cycle leaves you with bad sleep, restlessness,
  sweats, GI upset, or above all a spike in cravings, stay at that
  dose for another cycle or two before dropping again.
- The two cut modes trade different things. Geometric holds the percentage step
  constant and lets the milligrams shrink, which is the gentler shape at the low
  end but never reaches zero. Linear holds the milligrams constant and lets the
  percentage grow, which reaches zero on a schedule but makes the last steps the
  biggest ones you will have taken. Either way, holding a cycle is always
  available and never a failure.
- Linear is the easier mode to cut. The mark never moves, so you measure once
  and reuse it every day instead of working out a new smaller one each cycle,
  and it never shrinks under a millimetre where a razor stops resolving. That is
  also why the 2 mg switch is unnecessary there.
- Once daily is fine at every level here. Buprenorphine's half-life is long
  enough that splitting doses buys you nothing.
- Every step is held for days on purpose. That same long half-life means a new
  dose needs most of a cycle to land: about 88-91% of the way there on
  day 1, and 98-100% by day 6, across the usual 24-42 hour range. It is why the
  ladder moves in cycles instead of shaving a little off daily, and it puts a
  floor under how fast this can honestly go: the default is roughly two months
  from 8 mg to 1 mg. Plenty of people need longer than that, and the tool is
  built for it. Hold a cycle, raise --n, or stretch --hold-days. --n 10
  --hold-days 9 is about six months. Going slower is a plan, not a failure.
- 16.7% every 6 days (n=6) is at the fast end of typical 10-25% steps. You may
  not feel a drop until day 4 or 5, right as you are about to drop again. Hedge
  by stretching the cycle to 8-9 days (same cut, more settling time) or switch
  to n=10 below 3 mg.
- Ask about the long-acting injections. Sublocade (monthly) and Brixadi
  (weekly or monthly) are buprenorphine, the same active drug as your film
  without the naloxone, injected under the skin by a clinician, where it forms
  a depot that releases for weeks. Two things make them worth raising here.
  First, you do not have to reach the bottom of this ladder before switching:
  both are labelled for a direct transfer from an established daily sublingual
  dose. Second, after the LAST injection the drug leaves over months rather than
  days. The prescribing information puts the terminal half-life at roughly 43-60
  days for Sublocade and 19-26 days for monthly Brixadi, against the 24-42 hours
  this tool assumes for a film. That is why people describe the ending as
  tapering itself. That is a fair reading of the pharmacology, but NEITHER
  PRODUCT IS APPROVED AS A TAPER, and withdrawal can still arrive, sometimes
  weeks or months after the final shot, so it needs watching for longer than you
  would expect. The two differ in a way that matters to this goal: Brixadi has
  more strengths, so a prescriber can step you further down before stopping,
  while Sublocade has the longer tail once you do. Do not read the injection's
  milligrams against your film's. Different route, different absorption;
  Sublocade's 100 mg monthly maintenance dose sits near a 24 mg/day sublingual
  blood level, not a 100 mg one. Both are supplied under restricted distribution
  and given in a clinic rather than collected from a pharmacy, so ask whether an
  office actually ADMINISTERS them, not just whether it prescribes
  buprenorphine. Raise it with a prescriber; it is not a plan you can make from
  this tool.
- Tell your prescriber this schedule so quantity can step down with the dose.
  A 30-strips-a-month prescription on a falling taper builds a stockpile, which is a
  diversion risk and a household hazard. Return surplus via pharmacy take-back.

Bring this to your prescriber. A taper from 8 mg to 1-2 mg is a routine goal;
they are the one who can write 2 mg films and match the quantity to the ladder.
"""

# Printed at the end of every run, --no-notes included: this names the method
# rather than advising anything, so it does not belong in the notes block.
FOOTER = """\
Strictly unofficially, the method can be called SAS-Sub-minning, because the stat you
are grinding down is Suboxone.
"""


@dataclass
class CycleRow:
    """One cycle of the ladder, n days at a fixed dose and a fixed cut.

    cut_from_mg is the piece you start the cycle holding; daily_mg is what you
    take each day after removing sliver_mg. piece_mm and cut_mm are the same two
    quantities in millimetres of film, totals for the day, which can exceed one
    film when the dose does. banked_mg is the cycle's slivers added up, which
    is exactly one whole piece when days == n, the method's milestone, not a
    tally of every offcut the reader physically ends up holding. cut_warn flags
    a sliver under CUT_WARN_MM, where hand-cutting stops being meaningful.

    take_mm / save_mg / save_mm are the three numbers the reader acts on at the
    strip, and they are about the film in front of them rather than the ladder:
    open a film, cut once, swallow take_mm, and everything past that mark,
    save_mm, worth save_mg, goes in the jar. take_mm + save_mm is the film you
    opened (films_out of them on a day whose dose needs more than one), so the
    two partition it with nothing unaccounted for. The save grows every cycle,
    because it is this cycle's sliver plus everything earlier cycles had
    already taken off.

    delta_save_mm is how much more that is than the last cycle which cut a
    film. The "extra", and equals cut_mm whenever the day keeps opening the
    same films off the same strip. It is None in the three cases where that
    comparison would be against a different thing: a restart on a fresh 2 mg
    film, a cycle that drops a whole film from the day, and a whole-films-only
    cycle with no cut at all.

    The films_out .. spare_mm block is film_layout() flattened onto the row:
    how many films the day needs and where its single cut falls. See FilmLayout
    for what each one means.
    """

    cycle: int
    day_start: int
    day_end: int
    n: int
    days: int
    film_mg: float
    cut_from_mg: float
    daily_mg: float
    sliver_mg: float
    piece_mm: float
    cut_mm: float
    take_mm: float
    save_mm: float
    save_mg: float
    delta_save_mm: Optional[float]
    films_out: int
    take_films: int
    cut_take_mm: float
    cut_save_mm: float
    spare_mm: float
    used_mg: float
    sum_mg: float
    sum_strips: float
    banked_mg: float
    sum_banked_mg: float
    switched_2mg: bool
    cut_warn: bool
    n_changed: bool


@dataclass
class MonthRow:
    """One 30-day bucket of the run, for matching the prescription to the dose.

    used_strips is ingested-equivalent, not strips dispensed; surplus_strips is
    what a static rx_strips prescription would leave over, the stockpile.
    """

    month: int
    day_start: int
    day_end: int
    used_mg: float
    used_strips: float
    rx_strips: float
    surplus_strips: float


@dataclass
class ScheduleResult:
    """A built ladder: the inputs it came from, the cycles, and the totals.

    Everything from base_film_mg down is derived. The summary fields default to
    0/None so an empty ladder still answers every question asked of it,
    index.html mirrors these exact defaults, and test_parity.js checks that.

    cut_mode is "geometric" (cut 1/n off what is left, so the step shrinks and
    the dose never quite reaches zero) or "linear" (cut the same 1/n of the
    ORIGINAL strip every cycle, so the step never changes and the dose lands on
    zero after n − 1 of them). r is the geometric keep ratio and describes the
    linear mode not at all, there the per-cycle drop grows every step.

    zero_day is the first day at 0 mg, which only a linear run reaches.

    truncated means the run hit MAX_CYCLES before reaching the target;
    switch_never_fired means the 2 mg switch was wanted but could not fire
    without raising the dose. Both are reported rather than hidden.
    """

    start_mg: float
    n: int
    film_mm: float
    film_2mg_mm: float
    target_mg: float
    strip_mg: float
    switch_2mg: bool
    hold_days: Optional[int]
    n_below_3mg: Optional[int]
    stop_mode: str
    cut_mode: str
    r: float
    ceiling_mg: float
    ceiling_strips: float
    base_film_mg: float = 8.0
    truncated: bool = False
    switch_never_fired: bool = False
    rows: list[CycleRow] = field(default_factory=list)
    months: list[MonthRow] = field(default_factory=list)
    days_to_2mg: Optional[int] = None
    dose_at_2mg: Optional[float] = None
    days_to_1mg: Optional[int] = None
    dose_at_1mg: Optional[float] = None
    zero_day: Optional[int] = None
    end_day: int = 0
    end_daily_mg: float = 0.0
    total_mg: float = 0.0
    total_strips: float = 0.0
    total_banked_mg: float = 0.0
    stay_mg: float = 0.0
    saved_vs_stay_mg: float = 0.0
    saved_vs_stay_strips: float = 0.0


def keep_ratio(n: int) -> float:
    """Fraction of the piece kept after one day's cut: 1 − 1/n.

    The whole taper is this number applied once per cycle. n = 6 keeps 5/6, so
    each cycle is 16.7% lower than the one before.
    """
    return 1.0 - 1.0 / n


def base_film_mg(start_mg: float) -> float:
    """Film strength the plan is built on: the smallest that holds the start dose.

    Args:
        start_mg: the dose on day 1.
    Returns:
        One of 2, 4, 8, 12, or 8 for a start above 12 mg, where no single film
        holds the dose and the day is made up of several. 8 mg is the strength
        people are normally tapering from and the one the 2 mg switch assumes;
        --film-strength overrides this if you hold something else.
    """
    strengths = sorted(FILM_SPECS)
    for mg in strengths:
        if start_mg <= mg + 1e-9:
            return float(mg)
    return 8.0


@dataclass
class FilmLayout:
    """How one day of a cycle is laid out across real films.

    A day's strip can be longer than one film: a 32 mg start on 8 mg strips is
    four of them. The dose arithmetic does not care. It is all milligrams,
    but the person holding a razor does.

    Think of the day's strip as the films laid end to end. You take from the
    left; everything past the mark goes in the jar. So the only films worth
    opening are the ones the TAKE reaches:

        take_films    whole films swallowed untouched, no cut
        the marked film  TAKE cut_take_mm | SAVE cut_save_mm | already off

    That is **one cut a day**, on one film, wherever the dose lands. A film
    the take never reaches would be opened only to put it straight in the jar,
    so it is left in the box instead and counted in spare_mm.

    spare_mm is the part of today's sliver sitting on those unopened films. It
    is zero whenever the day fits inside the films the take needs, which is
    every cycle of any run that fits on one film.

    When the take lands exactly on a film boundary there is no marked film at
    all, take the whole ones and nothing needs measuring.
    """

    films_out: int
    take_films: int
    cut_take_mm: float
    cut_save_mm: float
    spare_mm: float


def film_layout(
    strip_mg: float, sliver_mg: float, film_mg: float, film_mm: float
) -> FilmLayout:
    """Lay one day's strip across whole films, with a single cut.

    Args:
        strip_mg: the day's whole strip, what you start the day holding.
        sliver_mg: the part of it saved, strip_mg / n.
        film_mg: strength of one film you are cutting.
        film_mm: length of one such film along the cut axis.
    Returns:
        A FilmLayout. Guarantees:
          take_films * film_mm + cut_take_mm  == the day's TAKE length
          cut_save_mm + spare_mm              == the day's SLIVER length
          films_out                           == the films you actually open
        and at most one of them carries a mark.
    """
    if film_mg <= 0 or film_mm <= 0:
        return FilmLayout(0, 0, 0.0, 0.0, 0.0)
    mm_per_mg = film_mm / film_mg
    take_mg = max(0.0, strip_mg - sliver_mg)
    take_mm = take_mg * mm_per_mg
    sliver_mm = max(0.0, sliver_mg) * mm_per_mg

    # int() truncates and both operands are positive, so this is floor(). The
    # 1e-9 keeps an exact multiple, 16 mg of 8 mg film, off the wrong side of
    # the boundary after the geometric ladder's float drift.
    take_films = int(take_mg / film_mg + 1e-9)
    cut_take_mm = take_mm - take_films * film_mm

    if cut_take_mm < 1e-9:
        # The take ends on a film boundary. Nothing is measured today: swallow
        # the whole films and leave the sliver's film in the box.
        return FilmLayout(take_films, take_films, 0.0, 0.0, sliver_mm)

    # Everything past the mark on the marked film goes in the jar. Only as much
    # of it as fits is today's sliver; any remainder is on film never opened.
    leftover_mm = film_mm - cut_take_mm
    cut_save_mm = min(leftover_mm, sliver_mm)
    spare_mm = sliver_mm - cut_save_mm
    if spare_mm < 1e-9:
        spare_mm = 0.0
    return FilmLayout(
        films_out=take_films + 1,
        take_films=take_films,
        cut_take_mm=cut_take_mm,
        cut_save_mm=cut_save_mm,
        spare_mm=spare_mm,
    )


@dataclass(frozen=True)
class FractionCut:
    """One day's dose expressed as whole cells of a folded grid.

    The film is folded into `long_div` columns across its length and
    `short_div` rows across its width, and you take `cells` of the
    `long_div * short_div` that makes. Those cells are always `columns` whole
    columns plus `tab_cells` cells of the next one, so the piece is a rectangle
    or an L, never something scattered.

    cuts is how many strokes that needs and pieces how many bits of film end up
    in your mouth. A tab that runs to the film's own edge needs no cut on that
    side, which is what makes 5/6 on a 3x2 grid two strokes rather than three.

    error_mg is the dose this lands on minus the dose the ladder asked for. It
    is not hidden: a fraction cut is an approximation and the panel, the CLI and
    the schedule all say so.
    """

    long_div: int
    short_div: int
    cells: int
    columns: int
    tab_cells: int
    cuts: int
    pieces: int
    fraction: float
    dose_mg: float
    want_mg: float
    error_mg: float

    @property
    def label(self) -> str:
        """The fraction in lowest terms, as "5/6"."""
        g = math.gcd(self.cells, self.long_div * self.short_div)
        return f"{self.cells // g}/{self.long_div * self.short_div // g}"

    @property
    def exact(self) -> bool:
        return abs(self.error_mg) < 5e-4


def _frac_difficulty(
    long_div: int, short_div: int, columns: int, tab_cells: int,
    cuts: int, pieces: int, full_mm: float, wide_mm: float,
) -> float:
    """How hard this cut is by hand. Lower is easier.

    Only the physical work: stroke type, extra pieces, a tab too small to hold.
    A cut across the short axis is a 12.8 mm stroke guided by the film's own
    straight edge. A cut along the long axis is freehand down the middle and
    materially harder to keep square, so the two are not worth the same. A
    plain half should come out as a crosswise cut, not a lengthwise one, even
    though both are "one cut".

    Grid fineness is not part of this score. Two folds that take the same
    strokes are ranked by how close they are, then by `_frac_fineness`. Putting
    the grid into the score spent 0.17 mg to prefer 1/16 over 1/24 at 0.32 mg.
    `columns` is unused; it is here so the call site matches `fracDifficulty`.
    """
    lengthwise = 1 if tab_cells else 0
    d = (cuts - lengthwise) * 10 + lengthwise * 14 + (pieces - 1) * 4
    if tab_cells:
        tab = min(full_mm / long_div, wide_mm * tab_cells / short_div)
        if tab < FRAC_MIN_TAB_MM:
            d += 20
    return d


def _frac_fineness(long_div: int, short_div: int) -> int:
    """How fine the grid is, as a tertiary ranking after error.

    Halving is exact; thirds are a judgement, and the short axis has less room
    to be wrong in. Used only when two folds already take the same strokes and
    land equally close, never to spend milligrams on a coarser-looking grid.
    """
    return (
        {1: 0, 2: 0, 3: 2, 4: 3, 8: 6}[long_div]
        + {1: 0, 2: 2, 3: 5, 4: 7}[short_div]
    )


def fraction_cut(
    want_frac: float,
    film_mg: float,
    full_mm: float,
    wide_mm: float,
    tol_mg: float = 0.0,
) -> Optional[FractionCut]:
    """Closest practical folded-grid piece to `want_frac` of one film.

    Args:
        want_frac: the wanted piece as a fraction of one whole film.
        film_mg: strength of that film.
        full_mm: its length along the cut axis.
        wide_mm: its width across.
        tol_mg: the error a simpler cut may carry and still win, in absolute
            terms. Pass the reader's own cutting tolerance in milligrams: any
            cut inside it is no worse than the slip they would make with a
            rule, so among those the simplest is the better instruction. Among
            folds that take the same strokes, the closer dose wins; grid
            fineness only breaks a remaining tie. Note this is a cap on the
            error itself, not a margin on top of the best one, otherwise the
            two would compound and the chosen cut could be further out than the
            tolerance allows. Zero means always take the closest.
    Returns:
        The chosen FractionCut, or None if the film has no size to fold.

    Deterministic: the same arguments always give the same cut, so the drawing
    never changes under a reader who has changed nothing.
    """
    if full_mm <= 0 or wide_mm <= 0 or film_mg <= 0:
        return None
    want_mg = want_frac * film_mg
    best: Optional[tuple] = None
    pool: list[tuple] = []
    for long_div in FRAC_LONG_DIVS:
        for short_div in FRAC_SHORT_DIVS:
            total = long_div * short_div
            for cells in range(1, total + 1):
                columns, tab = divmod(cells, short_div)
                if cells == total:
                    cuts, pieces = 0, 1
                elif tab == 0:
                    cuts, pieces = 1, 1
                else:
                    cuts = ((1 if columns else 0)
                            + (1 if columns + 1 < long_div else 0) + 1)
                    pieces = 2 if columns else 1
                frac = cells / total
                err = abs(frac - want_frac) * film_mg
                entry = (err, long_div, short_div, cells, columns, tab, cuts, pieces, frac)
                pool.append(entry)
                if best is None or err < best[0]:
                    best = entry
    assert best is not None
    cap = max(best[0], max(0.0, tol_mg))
    near = [e for e in pool if e[0] <= cap + 1e-12]
    near.sort(key=lambda e: (
        _frac_difficulty(e[1], e[2], e[4], e[5], e[6], e[7], full_mm, wide_mm),
        e[0], _frac_fineness(e[1], e[2]), e[2], -e[1], e[3],
    ))
    err, long_div, short_div, cells, columns, tab, cuts, pieces, frac = near[0]
    return FractionCut(
        long_div=long_div, short_div=short_div, cells=cells, columns=columns,
        tab_cells=tab, cuts=cuts, pieces=pieces, fraction=frac,
        dose_mg=frac * film_mg, want_mg=want_mg,
        error_mg=frac * film_mg - want_mg,
    )


def lifetime_ceiling_mg(
    start_mg: float,
    n: int,
    days_per_cycle: Optional[int] = None,
    cut_mode: str = "geometric",
) -> float:
    """Total mg the ladder would ever deliver, per cut mode.

    Args:
        start_mg: dose on day 1.
        n: cut denominator and default cycle length.
        days_per_cycle: hold days, or None for n.
        cut_mode: "geometric" or "linear".
    Returns:
        geometric, days × (n − 1) × D0. The run never reaches zero, so this is
        a ceiling: Σ_k days·D0·r^k = days·D0·r/(1−r) = days·D0·(n−1).
        linear, days × D0 × (n − 1) / 2, which is not a ceiling but the whole
        total, because a constant step does reach zero after n − 1 doses:
        Σ_{k=1..n−1} D0(1 − k/n) = D0 (n−1)/2.
    """
    days = days_per_cycle if days_per_cycle and days_per_cycle >= 1 else n
    if cut_mode == "linear":
        return days * start_mg * (n - 1) / 2.0
    return days * (n - 1) * start_mg


def ingested_closed_form(
    start_mg: float,
    n: int,
    cycles: int,
    days_per_cycle: Optional[int] = None,
    cut_mode: str = "geometric",
) -> float:
    """Total mg after a given number of cycles, in closed form.

    Args:
        start_mg: dose on day 1.
        n: cut denominator and default cycle length.
        cycles: how many cycles have run.
        days_per_cycle: hold days, or None for n.
        cut_mode: "geometric" or "linear".
    Returns:
        geometric, days·n·D0·r·(1 − r^cycles).
        linear, days·D0·(K − K(K+1)/(2n)) for K cycles, the sum of an
        arithmetic sequence rather than a geometric one.

    The tests check the simulation against this, so a change to the loop that
    is not also a change here shows up as a failure rather than as new truth.
    """
    days = days_per_cycle if days_per_cycle and days_per_cycle >= 1 else n
    if cut_mode == "linear":
        k = float(cycles)
        return days * start_mg * (k - k * (k + 1) / (2.0 * n))
    r = keep_ratio(n)
    return days * n * start_mg * r * (1.0 - r ** cycles)


def build_schedule(
    start_mg: float = DEFAULT_START_MG,
    n: int = DEFAULT_N,
    film_mm: float = DEFAULT_FILM_MM,
    target_mg: float = DEFAULT_TARGET_MG,
    strip_mg: float = DEFAULT_STRIP_MG,
    switch_2mg: bool = True,
    switch_at_mg: float = DEFAULT_SWITCH_AT_MG,
    film_2mg_mm: float = DEFAULT_FILM_MM,
    film_strength_mg: Optional[float] = None,
    hold_days: Optional[int] = None,
    n_below_3mg: Optional[int] = None,
    max_cycles: int = MAX_CYCLES,
    stop_mode: str = "reach",
    cut_mode: str = "geometric",
    rx_strips: float = DEFAULT_RX_STRIPS,
    month_days: int = DEFAULT_MONTH_DAYS,
) -> ScheduleResult:
    """Build the geometric taper.

    stop_mode:
      reach, include the first cycle whose daily dose is <= target (default).
      above, stop after the last cycle still strictly above target
              (classic n=6/8/10 comparison tables).

    cut_mode:
      geometric, cut 1/n off the piece in your hand (default). The cut shrinks
              with the dose, every cycle is the same percentage step, and the
              dose approaches zero without arriving.
      linear, cut the same amount every cycle: 1/n of the ORIGINAL strip, in
              the same milligrams and the same millimetres, from the first day
              to the last. The dose falls in equal steps and reaches zero after
              n − 1 of them. Because the cut never gets thinner there is nothing
              for the 2 mg switch to rescue, and changing n partway would break
              the one constant the mode is built on, so both are ignored here.
    """
    if n < 2:
        raise ValueError("n must be at least 2")
    if start_mg <= 0 or film_mm <= 0 or strip_mg <= 0 or target_mg < 0:
        raise ValueError("doses, film length, and strip strength must be positive")
    if stop_mode not in ("reach", "above"):
        raise ValueError("stop_mode must be 'reach' or 'above'")
    if cut_mode not in CUT_MODES:
        raise ValueError("cut_mode must be one of " + ", ".join(CUT_MODES))

    # Day 1 cuts the start dose out of one film, so the base film has to be the
    # smallest official strength that holds it: 8 mg by default, 12 mg for a
    # 12 mg start, 2 or 4 mg for a low start.
    film_mg = float(film_strength_mg) if film_strength_mg else base_film_mg(start_mg)
    current_film_mm = film_2mg_mm if film_mg <= 2.0 + 1e-9 else film_mm

    linear = cut_mode == "linear"
    # The one constant of the linear mode, fixed before the first cut and never
    # recomputed: 1/n of the ORIGINAL strip, in mg. Everything else follows.
    step_mg = float(start_mg) / n

    D = float(start_mg)
    current_n = int(n)
    switched = False
    already_switched_n = False
    day = 0
    sum_mg = 0.0
    sum_banked = 0.0
    truncated = False
    prev_daily: Optional[float] = None
    prev_save_mm: Optional[float] = 0.0
    prev_take_films: Optional[int] = None
    rows: list[CycleRow] = []

    for cycle in range(1, max_cycles + 1):
        n_changed = False
        # Both of these are geometric-mode rescues. In linear mode the cut never
        # gets thinner, so there is nothing for the 2 mg switch to fix, and
        # changing n would change the step the whole mode is defined by.
        if (
            not linear
            and n_below_3mg
            and n_below_3mg >= 2
            and D < 3.0
            and current_n != n_below_3mg
            and not already_switched_n
        ):
            current_n = int(n_below_3mg)
            already_switched_n = True
            n_changed = True

        just_switched = False
        if (
            not linear
            and switch_2mg
            and not switched
            and film_mg > 2.0 + 1e-9
            and D <= switch_at_mg + 1e-12
            # Restarting on a 2 mg film pins the whole strip at 2 mg, so only do
            # it while the resulting daily dose is still a step down. A low
            # --switch-at would otherwise walk the dose back up mid-taper.
            and (prev_daily is None or 2.0 * keep_ratio(current_n) < prev_daily)
        ):
            D = 2.0
            film_mg = 2.0
            current_film_mm = film_2mg_mm
            switched = True
            just_switched = True

        if linear:
            sliver = step_mg
            daily = D - sliver
            # The last cut takes the dose to exactly zero. A cycle of n days at
            # 0 mg is not an instruction, so the ladder ends before it and the
            # summary reports the day the dose reaches zero instead.
            if daily <= 1e-12:
                break
        else:
            sliver = D / current_n
            daily = D * keep_ratio(current_n)

        if stop_mode == "above" and daily <= target_mg + 1e-12:
            break

        days = int(hold_days) if hold_days and hold_days >= 1 else current_n
        piece_mm = current_film_mm * D / film_mg
        # From the sliver, not from piece_mm / n. The two are identical in
        # geometric mode, where the sliver IS the piece over n, but in linear
        # mode the sliver is a fixed number of milligrams, and the millimetres
        # have to hold still with it. That constant cut is the whole point of
        # the mode: the same mark, every day, from the first cut to the last.
        cut_mm = current_film_mm * sliver / film_mg
        # The dose as a length. Take + save is the film you opened, so this is
        # the half of that pair the reader swallows.
        take_mm = max(0.0, piece_mm - cut_mm)
        # Where that cut actually falls on real films. Above one film's worth of
        # dose the day is several strips and only one of them gets marked.
        lay = film_layout(D, sliver, film_mg, current_film_mm)
        # What physically goes in the jar from the film you mark: everything
        # past the take mark. That is the day's sliver plus the part earlier
        # cycles had already taken off, so it grows as the ladder descends,
        # and it is the number the reader acts on, not cut_mm.
        if lay.cut_take_mm > 1e-9:
            save_mm = max(0.0, current_film_mm - lay.cut_take_mm)
            save_mg = film_mg * (save_mm / current_film_mm) if current_film_mm else 0.0
            # How much more goes in the jar than the last cycle that cut one.
            # Identically cut_mm while the day keeps opening the same films,
            # take(k−1) is piece(k), so the difference of two "full minus take"
            # figures is exactly this cycle's sliver. Two things break that and
            # both make "extra" meaningless rather than merely different: a
            # 2 mg restart puts a different film underneath, and dropping a
            # whole film from the day changes how much film is opened at all.
            comparable = (
                not just_switched
                and prev_save_mm is not None
                and (prev_take_films is None or prev_take_films == lay.take_films)
            )
            delta_save_mm = save_mm - prev_save_mm if comparable else None
        else:
            # The take lands on a film boundary: nothing is marked, so nothing
            # is cut off a film to save and there is no cut to compare against.
            save_mm = 0.0
            save_mg = 0.0
            delta_save_mm = None
        used = days * daily
        banked = days * sliver

        day_start = day + 1
        day_end = day + days
        sum_mg += used
        sum_banked += banked

        rows.append(
            CycleRow(
                cycle=cycle,
                day_start=day_start,
                day_end=day_end,
                n=current_n,
                days=days,
                film_mg=film_mg,
                cut_from_mg=D,
                daily_mg=daily,
                sliver_mg=sliver,
                piece_mm=piece_mm,
                cut_mm=cut_mm,
                take_mm=take_mm,
                save_mm=save_mm,
                save_mg=save_mg,
                delta_save_mm=delta_save_mm,
                films_out=lay.films_out,
                take_films=lay.take_films,
                cut_take_mm=lay.cut_take_mm,
                cut_save_mm=lay.cut_save_mm,
                spare_mm=lay.spare_mm,
                used_mg=used,
                sum_mg=sum_mg,
                sum_strips=sum_mg / strip_mg,
                banked_mg=banked,
                sum_banked_mg=sum_banked,
                switched_2mg=just_switched,
                cut_warn=cut_mm < CUT_WARN_MM,
                n_changed=n_changed,
            )
        )

        D = daily
        prev_daily = daily
        # Only a cycle that actually cut a film moves the baseline; a
        # whole-films-only day saves nothing, and the next cut should be
        # compared with the last real one.
        if lay.cut_take_mm > 1e-9:
            prev_save_mm = save_mm
            prev_take_films = lay.take_films
        day = day_end

        if stop_mode == "reach" and daily <= target_mg + 1e-12:
            break
    else:
        # Fell out of the loop with the target still above us.
        truncated = stop_mode == "reach"

    result = ScheduleResult(
        start_mg=start_mg,
        n=n,
        film_mm=film_mm,
        film_2mg_mm=film_2mg_mm,
        target_mg=target_mg,
        strip_mg=strip_mg,
        switch_2mg=switch_2mg,
        hold_days=hold_days,
        n_below_3mg=n_below_3mg,
        stop_mode=stop_mode,
        cut_mode=cut_mode,
        r=keep_ratio(n),
        ceiling_mg=lifetime_ceiling_mg(start_mg, n, hold_days, cut_mode),
        ceiling_strips=lifetime_ceiling_mg(start_mg, n, hold_days, cut_mode) / strip_mg,
        base_film_mg=(float(film_strength_mg) if film_strength_mg else base_film_mg(start_mg)),
        truncated=truncated,
        # Only a real miss if the ladder ran past 2 mg still on the bigger film.
        switch_never_fired=bool(
            not linear and switch_2mg and not switched and rows and rows[-1].daily_mg < 2.0
        ),
        rows=rows,
    )
    _fill_summary(result, rx_strips=rx_strips, month_days=month_days)
    return result


def _fill_summary(
    result: ScheduleResult,
    rx_strips: float = DEFAULT_RX_STRIPS,
    month_days: int = DEFAULT_MONTH_DAYS,
) -> None:
    """Fill in the whole-run totals on a built schedule, in place.

    Args:
        result: a ScheduleResult whose .rows are already populated.
        rx_strips: strips per month the prescription currently supplies, used
            for the surplus column.
        month_days: days per billing month, normally 30.
    Returns:
        None, result is mutated. On an empty ladder every summary field keeps
        its dataclass default of 0/None, which is what index.html matches.
    """
    rows = result.rows
    if not rows:
        return
    result.end_day = rows[-1].day_end
    result.end_daily_mg = rows[-1].daily_mg
    result.total_mg = rows[-1].sum_mg
    result.total_strips = rows[-1].sum_strips
    result.total_banked_mg = rows[-1].sum_banked_mg
    result.stay_mg = result.start_mg * result.end_day
    result.saved_vs_stay_mg = result.stay_mg - result.total_mg
    result.saved_vs_stay_strips = result.saved_vs_stay_mg / result.strip_mg

    for row in rows:
        if result.days_to_2mg is None and row.daily_mg <= 2.0 + 1e-9:
            result.days_to_2mg = row.day_start
            result.dose_at_2mg = row.daily_mg
        if result.days_to_1mg is None and row.daily_mg <= 1.0 + 0.12:
            # ~1 mg: first cycle at or under ~1.12 mg (covers the classic 1.08
            # landing). Same convention as ~2 mg, the first day at that dose.
            result.days_to_1mg = row.day_start
            result.dose_at_1mg = row.daily_mg

    # A linear run lands on zero. The ladder stops before the cycle that would
    # have you taking nothing, so the first zero day is the day after the last
    # dose, but only if the run actually got that far, rather than stopping at
    # a target or the cycle cap on the way.
    if result.cut_mode == "linear" and not result.truncated:
        last = rows[-1]
        if last.daily_mg - last.sliver_mg <= 1e-12:
            result.zero_day = last.day_end + 1

    result.months = monthly_usage(rows, result.strip_mg, month_days, rx_strips)


def monthly_usage(
    rows: list[CycleRow],
    strip_mg: float,
    month_days: int = DEFAULT_MONTH_DAYS,
    rx_strips: float = DEFAULT_RX_STRIPS,
) -> list[MonthRow]:
    """Bucket the ladder into fixed 30-day months.

    Args:
        rows: the cycle rows, which may straddle month boundaries.
        strip_mg: strength of one dispensed film, for the mg→strips conversion.
        month_days: length of a bucket, normally 30.
        rx_strips: strips the prescription supplies per bucket.
    Returns:
        One MonthRow per bucket. Cycles are split across buckets day by day
        rather than assigned whole, so a cycle spanning a boundary contributes
        to both.
    """
    if not rows:
        return []
    end_day = rows[-1].day_end
    n_months = (end_day + month_days - 1) // month_days
    used = [0.0] * n_months
    for row in rows:
        for d in range(row.day_start, row.day_end + 1):
            used[(d - 1) // month_days] += row.daily_mg
    out: list[MonthRow] = []
    for i, mg in enumerate(used):
        strips = mg / strip_mg
        out.append(
            MonthRow(
                month=i + 1,
                day_start=i * month_days + 1,
                day_end=min((i + 1) * month_days, end_day),
                used_mg=mg,
                used_strips=strips,
                rx_strips=rx_strips,
                surplus_strips=rx_strips - strips,
            )
        )
    return out


def compare_classic(
    start_mg: float = DEFAULT_START_MG,
    target_mg: float = DEFAULT_TARGET_MG,
    strip_mg: float = DEFAULT_STRIP_MG,
    ns: tuple[int, ...] = (6, 8, 10),
    cut_mode: str = "geometric",
) -> list[dict[str, Any]]:
    """Side-by-side at the target: one strength all the way, last cycle above it.

    Runs in whichever cut mode the caller is using, so the panel compares three
    speeds of the same method rather than quietly showing the other one.
    """
    out = []
    for n in ns:
        sched = build_schedule(
            start_mg=start_mg,
            n=n,
            target_mg=target_mg,
            strip_mg=strip_mg,
            switch_2mg=False,
            hold_days=None,
            n_below_3mg=None,
            stop_mode="above",
            cut_mode=cut_mode,
        )
        out.append(
            {
                "n": n,
                "pct": 100.0 / n,
                "cycles": len(sched.rows),
                "days": sched.end_day,
                "end_daily_mg": sched.end_daily_mg,
                "total_mg": sched.total_mg,
                "total_strips": sched.total_strips,
                "ceiling_mg": sched.ceiling_mg,
                "ceiling_strips": sched.ceiling_strips,
                "stay_strips": sched.end_day * start_mg / strip_mg,
                "saved_strips": sched.saved_vs_stay_strips,
            }
        )
    return out


def share_cols(values: list[float], inner: int) -> list[int]:
    """Integer column counts that sum to inner, proportional to values."""
    n = len(values)
    total = sum(max(0.0, v) for v in values)
    if inner <= 0 or n == 0:
        return [0] * n
    if total <= 0:
        return [0] * n
    exact = [max(0.0, v) / total * inner for v in values]
    cols = [int(x) for x in exact]
    leftover = inner - sum(cols)
    order = sorted(range(n), key=lambda i: (exact[i] - cols[i], exact[i]), reverse=True)
    i = 0
    while leftover > 0:
        cols[order[i % n]] += 1
        leftover -= 1
        i += 1
    for i, v in enumerate(values):
        if v > 0.02 and cols[i] == 0:
            j = max(range(n), key=lambda k: cols[k])
            if cols[j] > 1:
                cols[j] -= 1
                cols[i] = 1
    drift = inner - sum(cols)
    if drift:
        cols[-1] += drift
    return cols


def ascii_ruler(
    take_mm: float,
    save_mm: float,
    ghost_mm: float = 0.0,
    width: int = 52,
) -> str:
    """TAKE (=) on the left, then the SAVE: this cycle's extra (#), then the
    part already off before (.). Everything right of the = is saved."""
    inner = max(12, width - 2)
    take_c, save_c, ghost_c = share_cols([take_mm, save_mm, ghost_mm], inner)
    parts = [("=", take_c), ("#", save_c), (".", ghost_c)]
    body = "|".join(ch * n for ch, n in parts if n > 0)
    return "[" + body + "]"


def cut_context(row: CycleRow, sched: ScheduleResult) -> dict[str, Any]:
    """Everything needed to describe one cycle's cut, in one dict.

    Args:
        row: the cycle to describe.
        sched: its parent schedule, for the film lengths.
    Returns:
        A dict of the three drawn regions of a full unused film, take, this
        cycle's extra, and the part already gone from earlier cycles, in both
        mm and mg, plus the day's take_mm / save_mm / save_mg totals (the last
        two of those regions added together) and an ASCII ruler. Shared by the CLI's cut block and the --json payload so
        the two cannot disagree.
    """
    spec = film_spec_for_mg(row.film_mg)
    full_mm = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
    take_mm = row.take_mm
    save_mm = row.save_mm
    # The ruler draws the one film that carries the cut, so its leftover is what
    # "already off" means, not full_mm − piece_mm, which goes negative as soon
    # as the day spans more than one film.
    no_cut = row.cut_take_mm <= 1e-9
    ghost_mm = 0.0 if no_cut else max(0.0, full_mm - row.cut_take_mm - row.cut_save_mm)
    per_mm = (row.film_mg / full_mm) if full_mm else 0.0
    return {
        "cycle": row.cycle,
        "label": spec.label,
        "keep_mm": spec.keep_mm,
        "full_mm": full_mm,
        "take_mm": take_mm,
        "save_mm": save_mm,
        "ghost_mm": ghost_mm,
        "take_mg": row.daily_mg,
        "save_mg": row.save_mg,
        "delta_save_mm": row.delta_save_mm,
        "ghost_mg": ghost_mm * per_mm,
        "piece_mm": row.piece_mm,
        "n": row.n,
        "films_out": row.films_out,
        "take_films": row.take_films,
        "cut_take_mm": row.cut_take_mm,
        "cut_save_mm": row.cut_save_mm,
        "cut_take_mg": row.cut_take_mm * per_mm,
        "cut_save_mg": row.cut_save_mm * per_mm,
        "spare_mm": row.spare_mm,
        "spare_mg": row.spare_mm * per_mm,
        # Length of the strip ON the marked film. The sliver is measured from
        # the right of THIS, not of the film: on a later cycle the film's right
        # end is past the already-off mark, and measuring from there would put
        # the cut millimetres out. Equals piece_mm on a single-film day.
        "marked_piece_mm": row.cut_take_mm + row.cut_save_mm,
        "no_cut": no_cut,
        "kit": kit_line(row, full_mm),
        "ruler": "" if no_cut else ascii_ruler(row.cut_take_mm, row.cut_save_mm, ghost_mm),
    }


def kit_line(row: CycleRow, full_mm: float) -> str:
    """One sentence naming every film the day needs, or "" if it needs one.

    Args:
        row: the cycle, for its film_layout fields and strength.
        full_mm: length of one whole film at that strength.
    Returns:
        Something like "3 x 8 mg films a day: 2 taken whole, plus the marked
        one." Empty when films_out <= 1, where the drawing says it all.
    """
    if row.films_out <= 1:
        return ""
    whole = f"{row.take_films} taken whole"
    if row.cut_take_mm > 1e-9:
        tail = f"{whole}, plus the marked one below"
    else:
        tail = f"{whole}, nothing to cut today"
    line = f"{row.films_out} \u00d7 {row.film_mg:g} mg films a day: {tail}."
    if row.spare_mm > 1e-9:
        line += (
            f" Today's sliver runs {row.spare_mm:.1f} mm past them, onto a film "
            f"you do not need to open. Leave that one in the box."
        )
    return line



def film_specs_payload() -> list[dict[str, Any]]:
    """The official film size table as plain dicts, for --json.

    Returns:
        One dict per strength, ascending, with dimensions, area and density.
        Reference data only, it never affects the ladder.
    """
    out = []
    for key in (2, 4, 8, 12):
        spec = FILM_SPECS[key]
        out.append(
            {
                "mg": spec.mg,
                "nal": spec.nal,
                "label": spec.label,
                "cut_mm": spec.cut_mm,
                "keep_mm": spec.keep_mm,
                "area_mm2": spec.area_mm2,
                "density_mg_per_mm2": spec.density,
            }
        )
    return out


def print_film_table() -> None:
    """Print the official size table. Reference only; changes nothing."""
    print("Official Suboxone film sizes (buprenorphine / naloxone)")
    print("Cut along the 22 mm side; keep the other side as full width.")
    print("This table is a reference. It does not change the taper math.")
    print()
    headers = ["Film", "Cut mm", "Keep mm", "Area mm²", "mg/mm²"]
    rows = []
    for key in (2, 4, 8, 12):
        spec = FILM_SPECS[key]
        rows.append(
            [
                spec.label,
                f"{spec.cut_mm:.1f}",
                f"{spec.keep_mm:.1f}",
                f"{spec.area_mm2:.1f}",
                f"{spec.density:.5f}",
            ]
        )
    print_table(headers, rows)
    print()


def print_cut_block(ctx: dict[str, Any], row: CycleRow, detailed: bool = False) -> None:
    """Print one cycle's cut mark and ASCII ruler.

    Args:
        ctx: a cut_context() dict for the cycle.
        row: the cycle itself, for the day range and film strength.
        detailed: add the note explaining the ruler is a full unused film rather
            than a zoomed leftover, used by --cycle N, where no surrounding
            table makes that obvious.
    """
    warn = "  << sliver under 1 mm, switch film strength" if row.cut_warn else ""
    extra = ""
    if row.switched_2mg:
        extra = "  [switched to 2 mg films, restarted as a whole strip]"
    has_ghost = ctx["ghost_mm"] > 0.05
    multi = ctx["films_out"] > 1
    print(
        f"  cycle {row.cycle:2d}  unused {ctx['full_mm']:.1f} × {ctx['keep_mm']:.1f} mm"
        f"  in hand {ctx['piece_mm']:.1f} mm"
        f"{extra}{warn}"
    )
    if multi:
        print(f"           {ctx['kit']}")
    if ctx["no_cut"]:
        print("           no cut this cycle, every film today is taken whole")
        print(
            f"           TAKE {ctx['take_mm']:.1f} mm ({ctx['take_mg']:.2f} mg)"
            f"  |  SAVE nothing. The dose is a whole number of films"
        )
        if detailed:
            print(f"           Keep full width ({ctx['keep_mm']:.1f} mm); shorten length only.")
        return
    print(f"           {ctx['ruler']}")
    # The ruler is the one marked film. Everything right of the take mark is
    # saved, whether it came off this cycle or an earlier one, so TAKE and SAVE
    # here add up to that whole film.
    delta = ctx["delta_save_mm"]
    # On the first cut of a strip the whole save IS this cycle's extra, and
    # saying so twice in one line reads like a mistake.
    extra = (
        f", of which {delta:.2f} mm is new this cycle"
        if delta is not None and delta > 1e-9
        and abs(delta - ctx["save_mm"]) > 1e-9 else ""
    )
    print(
        f"           TAKE {ctx['cut_take_mm']:.1f} mm ({ctx['cut_take_mg']:.2f} mg)"
        f"  |  SAVE {ctx['save_mm']:.2f} mm ({ctx['save_mg']:.2f} mg)"
        f"{extra}" + ("   (marked film)" if multi else "")
    )
    if multi:
        # Only the take spans several films; the save is all on the marked one.
        print(
            f"           day total: TAKE {ctx['take_mm']:.1f} mm "
            f"({ctx['take_mg']:.2f} mg) across {ctx['films_out']} films"
        )
    print(
        f"           mark {ctx['cut_take_mm']:.2f} mm from the left end of a "
        f"full {ctx['full_mm']:.1f} mm film. Left is the dose, right is the jar"
        + ("; the whole films need no cut" if row.take_films else "")
    )
    if has_ghost:
        print(
            f"           carrying on from the {ctx['marked_piece_mm']:.1f} mm piece "
            f"in hand instead? Mark {ctx['cut_save_mm']:.2f} mm from its right. "
            f"Same cut, other end."
        )
    if detailed:
        if has_ghost:
            print(
                "           This bar is a full unused film, not a zoomed leftover. "
                "Everything right of the take mark is the save: the # part is this "
                "cycle's extra, the dotted end was already coming off in earlier "
                "cycles. All of it goes in the jar; none of it is extra daily dose."
            )
        elif not multi:
            print("           Cycle 1 uses the whole unused strip.")
        if multi:
            print(
                "           One day's dose is more than one film here, so the day is "
                "several strips, but only one of them is ever cut."
            )
        print(
            f"           Keep full width ({ctx['keep_mm']:.1f} mm); shorten length only."
        )


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a plain-text table, each column padded to its widest cell.

    Args:
        headers: column titles.
        rows: pre-formatted cells; no number formatting happens here.
    """
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    rule = "  ".join("-" * widths[i] for i in range(len(headers)))
    print(line)
    print(rule)
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))


def parse_start_date(raw: Optional[str]) -> Optional[date]:
    """YYYY-MM-DD, or None. Raises ValueError on anything else."""
    if not raw:
        return None
    return date.fromisoformat(raw.strip())


def print_schedule(
    sched: ScheduleResult,
    selected_cycle: Optional[int] = None,
    start_date: Optional[date] = None,
) -> None:
    """Print the whole human-readable report: how-to, warnings, the cycle
    table, film sizes, cut marks, headline figures and monthly quantity.

    Args:
        sched: the built schedule.
        selected_cycle: print only this cycle's cut mark, with the extra note.
            None prints every cycle's.
        start_date: day 1. When given, the table gains a Dates column carrying
            the same dates the site's calendar shows.
    """
    n = sched.n
    r = sched.r
    print("SAS-Taper")
    print("Not medical advice. Calculator for a plan to take to your prescriber.")
    print()
    print(HOW_TO)
    linear = sched.cut_mode == "linear"
    if linear:
        step = sched.start_mg / n
        print(
            f"Start {sched.start_mg:g} mg  n={n}  cut mode LINEAR "
            f"(same cut every cycle: 1/{n} of the original strip = {step:.2f} mg, "
            f"{n}-day cycles)"
        )
    else:
        print(
            f"Start {sched.start_mg:g} mg  n={n}  "
            f"({100 / n:.1f}% cut, {n}-day cycles, keep {n - 1}/{n} = {r:.4f})"
        )
    print(f"Film {sched.film_mm:g} mm ({sched.base_film_mg:g} mg strength)  "
          f"target {sched.target_mg:g} mg  "
          f"strip {sched.strip_mg:g} mg  2 mg switch {'ON' if sched.switch_2mg else 'OFF'}")
    if sched.hold_days:
        print(f"Stretched cycle: {sched.hold_days} days at each level (cut still 1/{n}).")
    if sched.n_below_3mg and not linear:
        print(f"Below 3 mg, n switches to {sched.n_below_3mg}.")
    if linear and (sched.switch_2mg or sched.n_below_3mg):
        ignored = []
        if sched.switch_2mg:
            ignored.append("the 2 mg switch")
        if sched.n_below_3mg:
            ignored.append("n below 3 mg")
        print(
            f"Ignored in linear mode: {' and '.join(ignored)}. The cut never gets "
            f"thinner here, so there is nothing for a film switch to rescue, and "
            f"changing n partway would change the one step the mode is built on."
        )
    if linear:
        print(
            f"Whole-run total (equal steps all the way to zero): "
            f"{sched.ceiling_mg:.0f} mg "
            f"({sched.ceiling_strips:.1f} strips of {sched.strip_mg:g} mg)."
        )
    else:
        print(
            f"Lifetime ceiling (fixed n and cycle length, never stop): "
            f"{sched.ceiling_mg:.0f} mg "
            f"({sched.ceiling_strips:.1f} strips of {sched.strip_mg:g} mg)."
        )
    if sched.truncated:
        print(
            f"WARNING: stopped at the {len(sched.rows)}-cycle cap without reaching "
            f"{sched.target_mg:g} mg. Raise --max-cycles to see the rest of the ladder."
        )
    if sched.switch_never_fired:
        print(
            "WARNING: the 2 mg switch never fired, --switch-at is below 2 mg, and "
            "restarting on a 2 mg film there would raise the dose. Use --switch-at 2.25."
        )
    if linear and sched.zero_day is not None:
        print(
            f"Reaches 0 mg on day {sched.zero_day}: the cut after the last cycle "
            f"takes the whole remaining piece. The ladder stops before that day "
            f"because a cycle at 0 mg is not an instruction."
        )
    if linear and len(sched.rows) >= 3:
        # Equal milligrams are growing percentages, and the growth is the whole
        # safety story of this mode. State it in numbers rather than adjectives.
        drops = []
        for prev, row in zip(sched.rows, sched.rows[1:]):
            if prev.daily_mg > 0:
                drops.append(100.0 * (prev.daily_mg - row.daily_mg) / prev.daily_mg)
        if drops:
            shape = ", ".join(f"{d:.0f}%" for d in drops)
            tail = (
                f", and the last cut after that is 100%"
                if sched.zero_day is not None else ""
            )
            print(
                f"NOTE: equal cuts are not equal steps. Cycle to cycle this run "
                f"drops {shape}{tail}. The percentage grows as the dose falls, so "
                f"the hardest part of a linear taper is the end. Hold a cycle "
                f"whenever you need to, or use the default geometric mode for a "
                f"flat {100 / n:.1f}% step the whole way."
            )
    if sched.rows and sched.rows[0].films_out > 1:
        r0 = sched.rows[0]
        print(
            f"NOTE: day 1 needs {r0.piece_mm:.1f} mm, more than one "
            f"{sched.film_mm:g} mm film, so it is {r0.films_out} × "
            f"{r0.film_mg:g} mg strips a day, {r0.take_films} of them taken whole. "
            f"Only one strip is ever cut; see the cut marks below. Use "
            f"--film-strength if you hold a different strength."
        )
    print()

    # Take and Save are the pair you act on at the strip: open a film, cut
    # once, swallow the take, jar the save. Delta is how much more the jar
    # gets than last cycle. Everything after them is running totals.
    headers = [
        "Cyc", "Days", "Film", "Take mg", "Take mm", "Save mg", "Save mm",
        "+Save mm", "Cycle mg", "Sum mg", "Sum strips", "Banked",
    ]
    print("Take = the dose and where to mark it, from the LEFT end of a full film.")
    print("Save = everything right of that mark, which all goes in the jar.")
    print("+Save = how much more than last cycle; a dash where nothing is comparable.")
    if start_date is not None:
        headers.insert(2, "Dates")
    table = []
    for row in sched.rows:
        flags = []
        if row.switched_2mg:
            # Just an arrow pointing at the strength beside it. "→2mg" next to a
            # Film column already reading "2mg" looked like "2 mg to 2 mg".
            flags.append("←")
        if row.n_changed:
            flags.append(f"n={row.n}")
        if row.cut_warn:
            flags.append("thin")
        film = f"{row.film_mg:g}mg"
        if row.films_out > 1:
            film += f" \u00d7{row.films_out}"
        if flags:
            film += " " + ",".join(flags)
        cells = [
                str(row.cycle),
                f"{row.day_start}-{row.day_end}",
                film,
                f"{row.daily_mg:5.2f}",
                f"{row.take_mm:5.2f}",
                f"{row.save_mg:5.2f}",
                f"{row.save_mm:5.2f}",
                "    -" if row.delta_save_mm is None else f"{row.delta_save_mm:5.2f}",
                f"{row.used_mg:6.1f}",
                f"{row.sum_mg:7.1f}",
                f"{row.sum_strips:6.1f}",
                f"{row.banked_mg:5.2f}",
        ]
        if start_date is not None:
            d0 = start_date + timedelta(days=row.day_start - 1)
            d1 = start_date + timedelta(days=row.day_end - 1)
            cells.insert(2, f"{d0:%d %b}-{d1:%d %b}")
        table.append(cells)
    print_table(headers, table)
    # Only explain the markers this run actually used.
    key = []
    if any(r.switched_2mg for r in sched.rows):
        key.append("←  restart on a fresh 2 mg film")
    if any(r.n_changed for r in sched.rows):
        key.append("n=N  cycle length changed")
    if any(r.cut_warn for r in sched.rows):
        key.append("thin  sliver under 1 mm")
    if any(r.films_out > 1 for r in sched.rows):
        key.append("×N  films needed per day")
    if key:
        print("Film column: " + "    ".join(key))
    print()
    print_film_table()
    print("Cut marks, one full film: TAKE (=) on the left, then the SAVE:")
    print("this cycle's extra (#), then the part already off before (.).")
    print("Everything right of the take mark goes in the jar.")
    print()
    selected_row = None
    for row in sched.rows:
        ctx = cut_context(row, sched)
        if selected_cycle is None or row.cycle == selected_cycle:
            print_cut_block(ctx, row, detailed=(selected_cycle is not None))
            print()
        if selected_cycle is not None and row.cycle == selected_cycle:
            selected_row = row
    if selected_cycle is not None and selected_row is None:
        print(f"  (cycle {selected_cycle} is not on this run)")
        print()

    print("Headline")
    if sched.days_to_2mg is not None:
        print(
            f"  ~2 mg: day {sched.days_to_2mg} at {sched.dose_at_2mg:.2f} mg/day"
        )
    else:
        print("  ~2 mg: not reached on this run")
    if sched.days_to_1mg is not None:
        print(
            f"  ~1 mg: day {sched.days_to_1mg} at {sched.dose_at_1mg:.2f} mg/day"
        )
    else:
        print(
            f"  ~1 mg: not reached; last daily dose {sched.end_daily_mg:.2f} mg "
            f"on day {sched.end_day}"
        )
    print(
        f"  End of run: day {sched.end_day}, {sched.end_daily_mg:.2f} mg/day, "
        f"{sched.total_mg:.1f} mg ingested ({sched.total_strips:.1f} × "
        f"{sched.strip_mg:g} mg strips)"
    )
    print(
        f"  Slivers banked (buffer, not ingested): {sched.total_banked_mg:.1f} mg "
        f"({sched.total_banked_mg / sched.strip_mg:.1f} strips)"
    )
    print(
        f"  Vs staying at {sched.start_mg:g} mg/day for {sched.end_day} days: "
        f"saves {sched.saved_vs_stay_mg:.1f} mg "
        f"({sched.saved_vs_stay_strips:.1f} strips)"
    )
    print()

    print(f"Prescription quantity (ingested-equivalent strips per {DEFAULT_MONTH_DAYS} days)")
    print(f"If the prescription stays at {DEFAULT_RX_STRIPS} strips a month, the surplus is a "
          "stockpile. Ask to step quantity down; return the rest via take-back.")
    print()
    mheaders = ["Month", "Days", "Used mg", "Used strips", "If Rx=30", "Surplus"]
    mtable = []
    for m in sched.months:
        mtable.append(
            [
                str(m.month),
                f"{m.day_start}-{m.day_end}",
                f"{m.used_mg:6.1f}",
                f"{m.used_strips:5.1f}",
                f"{m.rx_strips:g}",
                f"{m.surplus_strips:+5.1f}",
            ]
        )
    print_table(mheaders, mtable)
    print()


def print_compare(rows: list[dict[str, Any]]) -> None:
    """Print the n = 6 / 8 / 10 comparison from compare_classic() rows."""
    print("Compare n = 6 / 8 / 10 at ~1 mg")
    print("8 mg films all the way; last cycle still above 1 mg. Bank is not re-dosed.")
    print()
    headers = [
        "n", "Cut", "Cycles", "Days", "End mg/d",
        "Total mg", "Strips", "Ceiling mg", "Vs stay", "Saved strips",
    ]
    table = []
    for c in rows:
        table.append(
            [
                str(c["n"]),
                f"{c['pct']:.1f}%",
                str(c["cycles"]),
                str(c["days"]),
                f"{c['end_daily_mg']:.2f}",
                f"{c['total_mg']:.1f}",
                f"{c['total_strips']:.1f}",
                f"{c['ceiling_mg']:.0f}",
                f"{c['stay_strips']:.0f} strips",
                f"{c['saved_strips']:.1f}",
            ]
        )
    print_table(headers, table)
    print()
    print("Slower is not free: n=10 uses about 3× the medication of n=6 because")
    print("you spend about 3× longer on the ladder.")
    print()


def result_to_json(sched: ScheduleResult, compare: Optional[list[dict[str, Any]]]) -> dict[str, Any]:
    """Flatten a schedule to a JSON-safe dict for --json.

    Args:
        sched: the built schedule.
        compare: optional compare_classic() rows to include under "compare".
    Returns:
        asdict(sched), plus the optional compare key. This is the payload
        test_parity.js diffs against index.html, so these field names are part
        of the contract between the two implementations.
    """
    payload: dict[str, Any] = asdict(sched)
    if compare is not None:
        payload["compare"] = compare
    return payload


def build_parser() -> argparse.ArgumentParser:
    """The CLI. Defaults mirror the site's, so both produce the same ladder."""
    p = argparse.ArgumentParser(
        description="SAS-Taper: geometric Suboxone film-taper calculator "
        "(not medical advice)."
    )
    p.add_argument("--start-mg", type=float, default=DEFAULT_START_MG)
    p.add_argument("--n", type=int, default=DEFAULT_N, help="cycle length and cut denominator (default 6)")
    p.add_argument("--film-mm", type=float, default=DEFAULT_FILM_MM)
    p.add_argument("--film-2mg-mm", type=float, default=DEFAULT_FILM_MM)
    p.add_argument("--film-strength", type=float, default=None, dest="film_strength_mg",
                   help="film strength you are cutting (default: smallest official size "
                        "that holds the start dose)")
    p.add_argument("--target", type=float, default=DEFAULT_TARGET_MG, dest="target_mg")
    p.add_argument("--strip-mg", type=float, default=DEFAULT_STRIP_MG)
    p.add_argument("--no-switch-2mg", action="store_true", help="stay on 8 mg films the whole way")
    p.add_argument("--switch-at", type=float, default=DEFAULT_SWITCH_AT_MG, help="cut-from mg that triggers a 2 mg restart")
    p.add_argument("--hold-days", type=int, default=None, help="stretch each cycle to this many days; cut is still 1/n")
    p.add_argument("--n-below-3", type=int, default=None, dest="n_below_3mg", help="switch n once cut-from drops below 3 mg")
    p.add_argument("--compare", action="store_true", help="also print n=6/8/10 classic totals")
    p.add_argument(
        "--cycle",
        type=int,
        default=None,
        help="print only this cycle's cut mark, with the full unused-film note",
    )
    p.add_argument(
        "--cut-mode",
        choices=CUT_MODES,
        default="geometric",
        help="geometric = cut 1/n off the piece in your hand, so the cut shrinks "
        "with the dose and every cycle is the same percentage step (default); "
        "linear = cut the same amount every cycle, 1/n of the ORIGINAL strip in "
        "the same mg and the same mm, so the dose falls in equal steps and "
        "reaches zero after n-1 of them",
    )
    p.add_argument(
        "--stop-mode",
        choices=("reach", "above"),
        default="reach",
        help="reach = include first cycle at or under target (default); "
        "above = stop while still strictly above target (classic compare)",
    )
    p.add_argument("--json", action="store_true", help="dump machine-readable JSON")
    p.add_argument("--max-cycles", type=int, default=MAX_CYCLES)
    p.add_argument("--no-notes", action="store_true", help="skip the practical-notes block")
    p.add_argument("--start-date", default=None,
                   help="YYYY-MM-DD for day 1; adds real dates to the schedule")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point.

    Args:
        argv: argument list, defaulting to sys.argv[1:].
    Returns:
        Exit code, 0 on success, 2 for a malformed date, an out-of-range input,
        or a --cycle not on this run. Invalid input is rejected here rather than
        corrected; the web version clamps instead, because a page cannot throw
        at its reader.
    """
    args = build_parser().parse_args(argv)
    try:
        start_date = parse_start_date(args.start_date)
    except ValueError:
        print(f"error: --start-date must be YYYY-MM-DD, got {args.start_date!r}", file=sys.stderr)
        return 2

    try:
        sched = build_schedule(
            start_mg=args.start_mg,
            n=args.n,
            film_mm=args.film_mm,
            target_mg=args.target_mg,
            strip_mg=args.strip_mg,
            switch_2mg=not args.no_switch_2mg,
            switch_at_mg=args.switch_at,
            film_2mg_mm=args.film_2mg_mm,
            film_strength_mg=args.film_strength_mg,
            hold_days=args.hold_days,
            n_below_3mg=args.n_below_3mg,
            max_cycles=args.max_cycles,
            stop_mode=args.stop_mode,
            cut_mode=args.cut_mode,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.cycle is not None and not any(r.cycle == args.cycle for r in sched.rows):
        print(f"error: cycle {args.cycle} is not on this run", file=sys.stderr)
        return 2

    compare_rows = compare_classic(
        start_mg=args.start_mg,
        target_mg=args.target_mg,
        strip_mg=args.strip_mg,
        cut_mode=args.cut_mode,
    ) if args.compare else None

    if args.json:
        payload = result_to_json(sched, compare_rows)
        payload["film_specs"] = film_specs_payload()
        payload["cut_context"] = [cut_context(r, sched) for r in sched.rows]
        if args.cycle is not None:
            row = next(r for r in sched.rows if r.cycle == args.cycle)
            payload["selected_cycle"] = args.cycle
            payload["selected_cut"] = cut_context(row, sched)
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print_schedule(sched, selected_cycle=args.cycle, start_date=start_date)
    if compare_rows is not None:
        print_compare(compare_rows)

    if not args.no_notes:
        print(NOTES)
    print(FOOTER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
