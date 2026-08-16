#!/usr/bin/env python3
"""SAS-Taper (save-a-sliver): geometric Suboxone (buprenorphine) film-taper calculator.

Not medical advice. Bring the output to your prescriber.
Saved slivers are a buffer, not extra daily dose.
https://github.com/bhbmaster/SAS-Taper
"""

from __future__ import annotations

import argparse
import json
import sys
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
CUT_WARN_MM = 1.0
SITE_URL = "https://bhbmaster.github.io/SAS-Taper/"


@dataclass(frozen=True)
class FilmSpec:
    mg: float
    nal: float
    cut_mm: float
    keep_mm: float
    label: str

    @property
    def area_mm2(self) -> float:
        return self.cut_mm * self.keep_mm

    @property
    def density(self) -> float:
        return self.mg / self.area_mm2


# Official Suboxone film sizes. Cut along cut_mm; keep keep_mm as full width.
FILM_SPECS: dict[int, FilmSpec] = {
    2: FilmSpec(2, 0.5, 22.0, 12.8, "2 mg / 0.5 mg"),
    4: FilmSpec(4, 1.0, 22.0, 25.6, "4 mg / 1 mg"),
    8: FilmSpec(8, 2.0, 22.0, 12.8, "8 mg / 2 mg"),
    12: FilmSpec(12, 3.0, 22.0, 19.2, "12 mg / 3 mg"),
}


def spec_key_for_mg(film_mg: float) -> int:
    if film_mg <= 2.01:
        return 2
    if film_mg <= 4.01:
        return 4
    if film_mg <= 8.01:
        return 8
    return 12


def film_spec_for_mg(film_mg: float) -> FilmSpec:
    return FILM_SPECS[spec_key_for_mg(film_mg)]


HOW_TO = f"""\
SAS means save-a-sliver. Source: https://github.com/bhbmaster/SAS-Taper

How to use this
  Site: {SITE_URL}  (or open index.html offline)
  CLI:  python3 taper.py
        python3 taper.py --compare
        python3 taper.py --cycle 6
        python3 taper.py --n 10 --no-switch-2mg
  Same math either way. Print / save the site, or copy this CLI output, for
  your prescriber before day 1.

Why save-a-sliver
  The hard part is often the sense of getting less, not the milligrams. Each day's
  remaining piece is framed as a complete strip — the dose you have. Surplus in
  view is easier to use; once the sliver is saved, it is not part of today's dose.
  The bank is a safety net, not extra daily supply.

The method — every day of a cycle
  1. The current piece is the "whole strip" (cycle 1: a full 8 mg film).
  2. Keep full width; cut along length only. Mark, then cut with a razor, not scissors.
  3. Cut 1/n off the RIGHT end. SAVE that sliver. TAKE the long left piece. Once daily.
  4. After n days the save jar holds one full piece — buffer, not extra dose.
     If you eat the bank, the dose never drops.
  5. Next cycle the new whole strip is dose × (1 − 1/n). Repeat to the target.

If it gets rough: hold this dose another cycle (cravings matter most). Stretch the
cycle to 8–9 days or switch n to 10 below 3 mg. When the sliver is under ~1 mm,
switch to 2 mg films. Lock up saved pieces. Step the prescribed quantity down
with the dose.

Limitation: the schedule starts on one given film size and either stays there or
switches only to 2 mg films (not 12→8→4). The official size table is a reference;
it does not change the ladder. To plan a 12 mg or 4 mg start, change --start-mg /
--strip-mg and recalc; the base film becomes the smallest official strength that
holds the start dose (--film-strength overrides it).
"""

NOTES = """\
Practical notes
- Cut along one axis only. Keep the full width of the film and only shorten it.
  Length fraction = dose fraction. Cutting both dimensions loses the arithmetic.
- Use a fresh razor/craft blade and a ruler on a clean mat, not scissors. Mark
  before you cut. Cutting films is not manufacturer-sanctioned; the drug is
  distributed reasonably evenly, which is why this method is widely used.
- Saved slivers are surplus / a safety net. Do not add them back into the daily
  dose or the taper never drops. Store airtight and dry, separated by wax paper,
  and keep them locked up. Buprenorphine is severely dangerous to kids and pets.
- The low end is where cutting 8 mg films breaks down. A ~1 mm sliver is already
  in the noise. Ask your prescriber for 2 mg films before you need them (around
  the time daily dose is heading through ~4 mg toward ~2 mg). A 2 mg film is one
  quarter the density, so the same dose is four times longer on it and the same
  cut is four times more forgiving.
- Holding is not failure. If a cycle leaves you with bad sleep, restlessness,
  sweats, GI upset, or — most importantly — a spike in cravings, stay at that
  dose for another cycle or two before dropping again.
- Once daily is fine at every level here. Buprenorphine's half-life is long
  enough that splitting doses buys you nothing.
- 16.7% every 6 days (n=6) is at the fast end of typical 10–25% steps. You may
  not feel a drop until day 4 or 5, right as you are about to drop again. Hedge
  by stretching the cycle to 8–9 days (same cut, more settling time) or switch
  to n=10 below 3 mg.
- Tell your prescriber this schedule so quantity can step down with the dose.
  A 30-strips-a-month prescription on a falling taper builds a stockpile — a
  diversion risk and a household hazard. Return surplus via pharmacy take-back.

Bring this to your prescriber. A taper from 8 mg to 1–2 mg is a routine goal;
they are the one who can write 2 mg films and match the quantity to the ladder.

Strictly unofficially, the method can be called SAS-Sub-minning — the stat you
are grinding down is Suboxone.
"""


@dataclass
class CycleRow:
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
    used_mg: float
    cum_mg: float
    cum_strips: float
    banked_mg: float
    cum_banked_mg: float
    switched_2mg: bool
    cut_warn: bool
    n_changed: bool


@dataclass
class MonthRow:
    month: int
    day_start: int
    day_end: int
    used_mg: float
    used_strips: float
    rx_strips: float
    surplus_strips: float


@dataclass
class ScheduleResult:
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
    end_day: int = 0
    end_daily_mg: float = 0.0
    total_mg: float = 0.0
    total_strips: float = 0.0
    total_banked_mg: float = 0.0
    stay_mg: float = 0.0
    saved_vs_stay_mg: float = 0.0
    saved_vs_stay_strips: float = 0.0


def keep_ratio(n: int) -> float:
    return 1.0 - 1.0 / n


def base_film_mg(start_mg: float) -> float:
    """Smallest official film strength that can hold the start dose.

    The piece you cut on day 1 is the start dose, so it has to fit on one film.
    Above 12 mg there is no single film; the caller gets 12 and a piece longer
    than one strip.
    """
    strengths = sorted(FILM_SPECS)
    for mg in strengths:
        if start_mg <= mg + 1e-9:
            return float(mg)
    return float(strengths[-1])


def lifetime_ceiling_mg(start_mg: float, n: int, days_per_cycle: Optional[int] = None) -> float:
    """Total mg if the ladder ran forever: days × (n − 1) × D0.

    Σ_k days·D0·r^k = days·D0·r/(1−r) = days·D0·(n−1). With the default
    cycle length (days = n) that is the familiar n(n−1)·D0.
    """
    days = int(days_per_cycle) if days_per_cycle and days_per_cycle >= 1 else n
    return days * (n - 1) * start_mg


def ingested_closed_form(
    start_mg: float, n: int, cycles: int, days_per_cycle: Optional[int] = None
) -> float:
    """days × n × D0 × r × (1 − r^K). Valid when n, D0, and cycle length stay fixed.

    With the default cycle length (days = n) this is n² × D0 × r × (1 − r^K).
    """
    r = keep_ratio(n)
    days = int(days_per_cycle) if days_per_cycle and days_per_cycle >= 1 else n
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
    rx_strips: float = DEFAULT_RX_STRIPS,
    month_days: int = DEFAULT_MONTH_DAYS,
) -> ScheduleResult:
    """Build the geometric taper.

    stop_mode:
      reach — include the first cycle whose daily dose is <= target (default).
      above — stop after the last cycle still strictly above target
              (classic n=6/8/10 comparison tables).
    """
    if n < 2:
        raise ValueError("n must be at least 2")
    if start_mg <= 0 or film_mm <= 0 or strip_mg <= 0 or target_mg < 0:
        raise ValueError("doses, film length, and strip strength must be positive")
    if stop_mode not in ("reach", "above"):
        raise ValueError("stop_mode must be 'reach' or 'above'")

    # Day 1 cuts the start dose out of one film, so the base film has to be the
    # smallest official strength that holds it: 8 mg by default, 12 mg for a
    # 12 mg start, 2 or 4 mg for a low start.
    film_mg = float(film_strength_mg) if film_strength_mg else base_film_mg(start_mg)
    current_film_mm = film_2mg_mm if film_mg <= 2.0 + 1e-9 else film_mm

    D = float(start_mg)
    current_n = int(n)
    switched = False
    already_switched_n = False
    day = 0
    cum_mg = 0.0
    cum_banked = 0.0
    truncated = False
    prev_daily: Optional[float] = None
    rows: list[CycleRow] = []

    for cycle in range(1, max_cycles + 1):
        n_changed = False
        if (
            n_below_3mg
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
            switch_2mg
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

        r = keep_ratio(current_n)
        daily = D * r
        sliver = D / current_n

        if stop_mode == "above" and daily <= target_mg + 1e-12:
            break

        days = int(hold_days) if hold_days and hold_days >= 1 else current_n
        piece_mm = current_film_mm * D / film_mg
        cut_mm = piece_mm / current_n
        used = days * daily
        banked = days * sliver

        day_start = day + 1
        day_end = day + days
        cum_mg += used
        cum_banked += banked

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
                used_mg=used,
                cum_mg=cum_mg,
                cum_strips=cum_mg / strip_mg,
                banked_mg=banked,
                cum_banked_mg=cum_banked,
                switched_2mg=just_switched,
                cut_warn=cut_mm < CUT_WARN_MM,
                n_changed=n_changed,
            )
        )

        D = daily
        prev_daily = daily
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
        r=keep_ratio(n),
        ceiling_mg=lifetime_ceiling_mg(start_mg, n, hold_days),
        ceiling_strips=lifetime_ceiling_mg(start_mg, n, hold_days) / strip_mg,
        base_film_mg=(float(film_strength_mg) if film_strength_mg else base_film_mg(start_mg)),
        truncated=truncated,
        # Only a real miss if the ladder ran past 2 mg still on the bigger film.
        switch_never_fired=bool(
            switch_2mg and not switched and rows and rows[-1].daily_mg < 2.0
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
    rows = result.rows
    if not rows:
        return
    result.end_day = rows[-1].day_end
    result.end_daily_mg = rows[-1].daily_mg
    result.total_mg = rows[-1].cum_mg
    result.total_strips = rows[-1].cum_strips
    result.total_banked_mg = rows[-1].cum_banked_mg
    result.stay_mg = result.start_mg * result.end_day
    result.saved_vs_stay_mg = result.stay_mg - result.total_mg
    result.saved_vs_stay_strips = result.saved_vs_stay_mg / result.strip_mg

    for row in rows:
        if result.days_to_2mg is None and row.daily_mg <= 2.0 + 1e-9:
            result.days_to_2mg = row.day_start
            result.dose_at_2mg = row.daily_mg
        if result.days_to_1mg is None and row.daily_mg <= 1.0 + 0.12:
            # ~1 mg: first cycle at or under ~1.12 mg (covers the classic 1.08
            # landing). Same convention as ~2 mg — the first day at that dose.
            result.days_to_1mg = row.day_start
            result.dose_at_1mg = row.daily_mg

    result.months = monthly_usage(rows, result.strip_mg, month_days, rx_strips)


def monthly_usage(
    rows: list[CycleRow],
    strip_mg: float,
    month_days: int = DEFAULT_MONTH_DAYS,
    rx_strips: float = DEFAULT_RX_STRIPS,
) -> list[MonthRow]:
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
) -> list[dict[str, Any]]:
    """Side-by-side at ~1 mg: 8 mg films all the way, last cycle still above target."""
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
    """TAKE (=) on the left, SAVE (#) , already-off original (.) on the right."""
    inner = max(12, width - 2)
    take_c, save_c, ghost_c = share_cols([take_mm, save_mm, ghost_mm], inner)
    parts = [("=", take_c), ("#", save_c), (".", ghost_c)]
    body = "|".join(ch * n for ch, n in parts if n > 0)
    return "[" + body + "]"


def cut_context(row: CycleRow, sched: ScheduleResult) -> dict[str, Any]:
    spec = film_spec_for_mg(row.film_mg)
    full_mm = sched.film_2mg_mm if row.film_mg <= 2.01 else sched.film_mm
    take_mm = row.piece_mm - row.cut_mm
    save_mm = row.cut_mm
    ghost_mm = max(0.0, full_mm - row.piece_mm)
    ghost_mg = row.film_mg * (ghost_mm / full_mm) if full_mm else 0.0
    return {
        "cycle": row.cycle,
        "label": spec.label,
        "keep_mm": spec.keep_mm,
        "full_mm": full_mm,
        "take_mm": take_mm,
        "save_mm": save_mm,
        "ghost_mm": ghost_mm,
        "take_mg": row.daily_mg,
        "save_mg": row.sliver_mg,
        "ghost_mg": ghost_mg,
        "piece_mm": row.piece_mm,
        "n": row.n,
        "ruler": ascii_ruler(take_mm, save_mm, ghost_mm),
    }


def film_specs_payload() -> list[dict[str, Any]]:
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
    warn = "  << sliver under 1 mm — switch film strength" if row.cut_warn else ""
    extra = ""
    if row.switched_2mg:
        extra = "  [switched to 2 mg films, restarted as a whole strip]"
    has_ghost = ctx["ghost_mm"] > 0.05
    print(
        f"  cycle {row.cycle:2d}  unused {ctx['full_mm']:.1f} × {ctx['keep_mm']:.1f} mm"
        f"  in hand {ctx['piece_mm']:.1f} mm"
        f"{extra}{warn}"
    )
    print(f"           {ctx['ruler']}")
    bits = [
        f"TAKE {ctx['take_mm']:.1f} mm ({ctx['take_mg']:.2f} mg)",
        f"SAVE {ctx['save_mm']:.2f} mm ({ctx['save_mg']:.2f} mg)",
    ]
    if has_ghost:
        bits.append(
            f"already off {ctx['ghost_mm']:.1f} mm ({ctx['ghost_mg']:.2f} mg)"
        )
    print("           " + "  |  ".join(bits))
    print(
        f"           mark {ctx['save_mm']:.2f} mm from the right of the "
        f"{ctx['piece_mm']:.1f} mm piece in hand (TAKE/SAVE line)"
    )
    if detailed:
        if has_ghost:
            print(
                "           This bar is the full unused film, not a zoomed leftover. "
                "The dotted end was already reduced in earlier cycles — extra bank "
                "if you start from a fresh strip, not extra daily dose."
            )
        else:
            print("           Cycle 1 uses the whole unused strip.")
        print(
            f"           Keep full width ({ctx['keep_mm']:.1f} mm); shorten length only."
        )


def print_table(headers: list[str], rows: list[list[str]]) -> None:
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


def print_schedule(sched: ScheduleResult, selected_cycle: Optional[int] = None) -> None:
    n = sched.n
    r = sched.r
    print("SAS-Taper")
    print("Not medical advice. Calculator for a plan to take to your prescriber.")
    print()
    print(HOW_TO)
    print(
        f"Start {sched.start_mg:g} mg  n={n}  "
        f"({100 / n:.1f}% cut, {n}-day cycles, keep {n - 1}/{n} = {r:.4f})"
    )
    print(f"Film {sched.film_mm:g} mm ({sched.base_film_mg:g} mg strength)  "
          f"target {sched.target_mg:g} mg  "
          f"strip {sched.strip_mg:g} mg  2 mg switch {'ON' if sched.switch_2mg else 'OFF'}")
    if sched.hold_days:
        print(f"Stretched cycle: {sched.hold_days} days at each level (cut still 1/{n}).")
    if sched.n_below_3mg:
        print(f"Below 3 mg, n switches to {sched.n_below_3mg}.")
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
            "WARNING: the 2 mg switch never fired — --switch-at is below 2 mg, and "
            "restarting on a 2 mg film there would raise the dose. Use --switch-at 2.25."
        )
    if sched.rows and sched.rows[0].piece_mm > sched.film_mm + 1e-9:
        print(
            f"WARNING: day 1 needs {sched.rows[0].piece_mm:.1f} mm, longer than one "
            f"{sched.film_mm:g} mm film — that dose does not fit on a single strip."
        )
    print()

    headers = [
        "Cyc", "Days", "Film", "Cut from", "Daily", "Sliver",
        "Piece", "Cut at", "Cycle mg", "Cum mg", "Cum strips", "Banked",
    ]
    table = []
    for row in sched.rows:
        flags = []
        if row.switched_2mg:
            flags.append("→2mg")
        if row.n_changed:
            flags.append(f"n={row.n}")
        if row.cut_warn:
            flags.append("thin")
        film = f"{row.film_mg:g}mg"
        if flags:
            film += " " + ",".join(flags)
        table.append(
            [
                str(row.cycle),
                f"{row.day_start}–{row.day_end}",
                film,
                f"{row.cut_from_mg:5.2f}",
                f"{row.daily_mg:5.2f}",
                f"{row.sliver_mg:5.2f}",
                f"{row.piece_mm:5.1f}",
                f"{row.cut_mm:5.2f}",
                f"{row.used_mg:6.1f}",
                f"{row.cum_mg:7.1f}",
                f"{row.cum_strips:6.1f}",
                f"{row.banked_mg:5.2f}",
            ]
        )
    print_table(headers, table)
    print()
    print_film_table()
    print("Cut marks (full unused film: TAKE left, SAVE, then already-off original)")
    print("Do not measure today’s cut from the right of the original film.")
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
        f"  Banked (buffer, not ingested): {sched.total_banked_mg:.1f} mg "
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
          "stockpile — ask to step quantity down; return the rest via take-back.")
    print()
    mheaders = ["Month", "Days", "Used mg", "Used strips", "If Rx=30", "Surplus"]
    mtable = []
    for m in sched.months:
        mtable.append(
            [
                str(m.month),
                f"{m.day_start}–{m.day_end}",
                f"{m.used_mg:6.1f}",
                f"{m.used_strips:5.1f}",
                f"{m.rx_strips:g}",
                f"{m.surplus_strips:+5.1f}",
            ]
        )
    print_table(mheaders, mtable)
    print()


def print_compare(rows: list[dict[str, Any]]) -> None:
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
    payload: dict[str, Any] = asdict(sched)
    if compare is not None:
        payload["compare"] = compare
    return payload


def build_parser() -> argparse.ArgumentParser:
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
        help="print only this cycle’s cut mark, with the full unused-film note",
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
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
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

    print_schedule(sched, selected_cycle=args.cycle)
    if compare_rows is not None:
        print_compare(compare_rows)

    if not args.no_notes:
        print(NOTES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
