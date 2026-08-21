#!/usr/bin/env node
/* Parity checks for SAS-Taper. Run: node test_parity.js
 *
 * The ladder maths is implemented twice, buildSchedule() in index.html and
 * build_schedule() in taper.py, and the site's footer promises the two agree.
 * test_taper.py only covers the Python side, so this diffs the JS one against
 * it: same inputs into both, then every row field compared.
 *
 * Needs playwright-core and a Chromium. If neither is present the script says
 * so and exits 0. A checkout without a browser should not fail the suite.
 */

"use strict";

const { execFileSync } = require("child_process");
const { launchOrSkip, PAGE, LAG_PAGE } = require("./test_browser");

const REPO = __dirname;
const TOL = 1e-9;

/* dailyMg -> daily_mg. The two sides name the same 19 row fields in their own
   house style; nothing else differs. */
const snake = (s) => s.replace(/[A-Z0-9]+/g, (m) => "_" + m.toLowerCase());

const FLAGS = {
  startMg: "--start-mg",
  n: "--n",
  targetMg: "--target",
  stripMg: "--strip-mg",
  filmMm: "--film-mm",
  film2Mm: "--film-2mg-mm",
  holdDays: "--hold-days",
  nBelow3: "--n-below-3",
  stopMode: "--stop-mode",
  cutMode: "--cut-mode",
  filmStrengthMg: "--film-strength",
};

const CASES = [
  {},
  { startMg: 2, stripMg: 2 },
  { startMg: 4, stripMg: 4 },
  { startMg: 12, stripMg: 12 },
  { n: 3 },
  { n: 4 },
  { n: 10 },
  { n: 20 },
  { switch2mg: false },
  { targetMg: 0.5 },
  { targetMg: 2 },
  { holdDays: 9 },
  { holdDays: 8, n: 8 },
  { nBelow3: 10 },
  { startMg: 12, stripMg: 12, n: 10, targetMg: 0.5 },
  { startMg: 2, stripMg: 2, n: 8, switch2mg: false },
  { filmMm: 20 },
  /* Linear mode: the same cut every cycle, so the dose falls in equal steps and
     lands on zero. The interesting parts are the landing itself, an n that
     divides the dose exactly, and the inputs the mode ignores. */
  { cutMode: "linear" },
  { cutMode: "linear", n: 2 },
  { cutMode: "linear", n: 3, targetMg: 0 },
  { cutMode: "linear", n: 30, targetMg: 0 },
  { cutMode: "linear", targetMg: 4 },
  { cutMode: "linear", switch2mg: false },
  { cutMode: "linear", nBelow3: 10 },
  { cutMode: "linear", holdDays: 9 },
  { cutMode: "linear", startMg: 16 },
  { cutMode: "linear", startMg: 32, targetMg: 0 },
  { cutMode: "linear", startMg: 2, stripMg: 2, filmStrengthMg: 2 },
  { cutMode: "linear", startMg: 1.1, targetMg: 1, stopMode: "above" },
  /* Start doses that need more than one film a day. 16 mg on 8 mg films is the
     plain two-strip case; 9.26 is where the ladder crosses a whole-film
     boundary and TAKE and SAVE stop fitting on one film; the rest push the
     layout past two films and past one film of sliver. */
  { startMg: 16 },
  { startMg: 16, n: 3 },
  { startMg: 16, n: 2, targetMg: 4 },
  { startMg: 24, n: 8 },
  { startMg: 9.26 },
  { startMg: 13, switch2mg: false },
  { startMg: 20, filmStrengthMg: 12 },
  { startMg: 16, filmStrengthMg: 4 },
  { startMg: 64, n: 2, targetMg: 8 },
  { startMg: 16, filmMm: 30, n: 7 },
  // clamp boundaries from clampOpts()
  { n: 30 },
  { startMg: 0.1, stripMg: 0.1 },
  // Empty ladder: target too close to the start dose. Both sides must report
  // zeroed summary fields rather than leaving them undefined, an undefined
  // endDay turned Math.max(endDay, 1) into NaN and broke the comparison chart.
  { startMg: 1.1, targetMg: 1, stopMode: "above" },
  { startMg: 8, targetMg: 8, stopMode: "above" },
];

function pyRun(c) {
  /* Run taper.py --json with the same inputs the JS side used. */
  const args = ["taper.py", "--json"];
  for (const [k, v] of Object.entries(c)) {
    if (FLAGS[k]) args.push(FLAGS[k], String(v));
  }
  if (c.switch2mg === false) args.push("--no-switch-2mg");
  if (c.compare) args.push("--compare");
  return JSON.parse(execFileSync("python3", args, { cwd: REPO, maxBuffer: 1 << 28 }));
}

/* Every single field-to-field comparison the run makes, so the suite can say
   how much it actually checked rather than how many schedules it built. */
let comparisons = 0;
let fracChecked = 0;

function compareRows(label, js, py, fail) {
  /* Diff every field of every cycle row. JS camelCase vs Python snake_case. */
  if (js.rows.length !== py.rows.length) {
    fail(`${label}: row count ${js.rows.length} (js) vs ${py.rows.length} (py)`);
    return;
  }
  for (let i = 0; i < js.rows.length; i++) {
    const a = js.rows[i];
    const e = py.rows[i];
    for (const k of Object.keys(a)) {
      const key = snake(k);
      if (!(key in e)) {
        fail(`${label}: row ${i} field ${k} missing from taper.py output`);
        continue;
      }
      const av = a[k];
      const ev = e[key];
      comparisons++;
      if (typeof av === "number") {
        if (!Number.isFinite(av) || Math.abs(av - ev) > TOL) {
          fail(`${label}: row ${i} ${k} = ${av} (js) vs ${ev} (py)`);
        }
      } else if (av !== ev) {
        fail(`${label}: row ${i} ${k} = ${JSON.stringify(av)} (js) vs ${JSON.stringify(ev)} (py)`);
      }
    }
  }
}

const SUMMARY = [
  ["endDay", "end_day"],
  ["endDailyMg", "end_daily_mg"],
  ["totalMg", "total_mg"],
  ["totalStrips", "total_strips"],
  ["totalBankedMg", "total_banked_mg"],
  ["ceilingMg", "ceiling_mg"],
  ["baseFilmMg", "base_film_mg"],
  ["daysTo2mg", "days_to_2mg"],
  ["daysTo1mg", "days_to_1mg"],
  ["zeroDay", "zero_day"],
  ["cutMode", "cut_mode"],
  /* Both flags exist to stop the tool hiding a short ladder, and neither was
     compared until a linear run broke out of the loop early and the two sides
     disagreed about whether that counted as truncation. */
  ["truncated", "truncated"],
  ["switchNeverFired", "switch_never_fired"],
];

/* The 30-day buckets. Written twice like everything else, and until now
   compared nowhere: compareRows only walks rows and compareSummary only walks
   scalars, so monthly_usage() could have drifted from monthlyUsage() silently. */
function compareMonths(label, js, py, fail) {
  if (js.months.length !== py.months.length) {
    fail(`${label}: month count ${js.months.length} (js) vs ${py.months.length} (py)`);
    return;
  }
  const FIELDS = [
    ["month", "month"], ["dayStart", "day_start"], ["dayEnd", "day_end"],
    ["usedMg", "used_mg"], ["usedStrips", "used_strips"],
    ["rxStrips", "rx_strips"], ["surplusStrips", "surplus_strips"],
  ];
  for (let i = 0; i < js.months.length; i++) {
    for (const [j, p] of FIELDS) {
      comparisons++;
      if (Math.abs(js.months[i][j] - py.months[i][p]) > 1e-9) {
        fail(`${label}: month ${i} ${j} = ${js.months[i][j]} (js) vs ${py.months[i][p]} (py)`);
      }
    }
  }
}

/* The n = 6 / 8 / 10 table, likewise implemented twice and likewise unchecked.
   It runs its own schedules in "above" stop mode, so it is not covered by the
   row comparison above. */
function compareCompare(label, js, py, fail) {
  if (js.length !== py.length) {
    fail(`${label}: compare row count ${js.length} (js) vs ${py.length} (py)`);
    return;
  }
  for (let i = 0; i < js.length; i++) {
    for (const k of Object.keys(js[i])) {
      const p = snake(k);
      if (!(p in py[i])) { fail(`${label}: compare field ${k} missing from taper.py`); continue; }
      comparisons++;
      if (Math.abs(js[i][k] - py[i][p]) > 1e-6) {
        fail(`${label}: compare row ${i} ${k} = ${js[i][k]} (js) vs ${py[i][p]} (py)`);
      }
    }
  }
}

function compareSummary(label, js, py, fail) {
  /* Diff the headline totals. Both sides must answer the same questions,
     including the empty-ladder defaults of 0 and null. */
  for (const [j, p] of SUMMARY) {
    const av = js[j];
    const ev = py[p];
    comparisons++;
    if (av == null && ev == null) continue;
    if (typeof av === "number" && typeof ev === "number") {
      if (Math.abs(av - ev) > 1e-6) fail(`${label}: ${j} = ${av} (js) vs ${ev} (py)`);
    } else if (av !== ev) {
      fail(`${label}: ${j} = ${JSON.stringify(av)} (js) vs ${JSON.stringify(ev)} (py)`);
    }
  }
}

/* The matrix phase. CASES above go through the CLI, which also covers the
   argument plumbing; this goes straight at build_schedule() so the whole grid
   fits in one Python process instead of one per case. Same function, same
   fields, three hundred times the coverage.

   Doses run to 32 mg against all four official strengths, which is where the
   film layout does its work: 32 mg of 2 mg film is sixteen strips a day. */
const MATRIX_STARTS = [1, 2, 3, 4, 6, 8, 9.26, 10, 12, 13, 16, 18, 20, 24, 28, 32];
const MATRIX_NS = [2, 3, 4, 6, 10, 30];
const MATRIX_STRENGTHS = [null, 2, 4, 8, 12];
const MATRIX = [];
for (const cutMode of ["geometric", "linear"]) {
  for (const startMg of MATRIX_STARTS) {
    for (const n of MATRIX_NS) {
      for (const filmStrengthMg of MATRIX_STRENGTHS) {
        MATRIX.push({ startMg, n, filmStrengthMg, cutMode, targetMg: Math.min(1, startMg / 2) });
      }
    }
  }
}
/* Film length only scales millimetres, so it gets a slice rather than the full
   cross, but it has to be in here, because every layout figure is derived
   from it. */
for (const startMg of MATRIX_STARTS) {
  for (const filmStrengthMg of MATRIX_STRENGTHS) {
    for (const filmMm of [20, 30]) {
      MATRIX.push({ startMg, n: 6, filmStrengthMg, filmMm, film2Mm: filmMm,
                    targetMg: Math.min(1, startMg / 2) });
      MATRIX.push({ startMg, n: 6, filmStrengthMg, filmMm, film2Mm: filmMm,
                    cutMode: "linear", targetMg: 0 });
    }
  }
}

const PY_MATRIX = `
import json, sys
from dataclasses import asdict
from taper import build_schedule
out = []
for c in json.load(sys.stdin):
    out.append(asdict(build_schedule(
        start_mg=c["startMg"], n=c["n"], film_strength_mg=c["filmStrengthMg"],
        film_mm=c.get("filmMm", 22.0), film_2mg_mm=c.get("film2Mm", 22.0),
        target_mg=c["targetMg"], strip_mg=8.0,
        cut_mode=c.get("cutMode", "geometric"),
    )))
json.dump(out, sys.stdout)
`;

/* fraction_cut() returns a dataclass with two derived properties, so it needs
   its own shim rather than a bare asdict. */
const PY_FRAC = `
import json, sys
from dataclasses import asdict
from taper import fraction_cut
out = []
for c in json.load(sys.stdin):
    fc = fraction_cut(c["want"], c["filmMg"], c["fullMm"], c["wideMm"], tol_mg=c["tolMg"])
    if fc is None:
        out.append(None)
        continue
    d = asdict(fc)
    d["label"] = fc.label
    d["exact"] = fc.exact
    out.append(d)
json.dump(out, sys.stdout)
`;

(async () => {
  const browser = await launchOrSkip();
  if (!browser) process.exit(0);

  const failures = [];
  const fail = (m) => failures.push(m);
  const page = await browser.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  await page.goto(PAGE);
  await page.waitForFunction(() => !!window.SASTaperInternals, null, { timeout: 10000 });

  for (const c of CASES) {
    const label = JSON.stringify(c) === "{}" ? "defaults" : JSON.stringify(c);
    const py = pyRun(c);
    const js = await page.evaluate(
      (o) => window.SASTaperInternals.buildSchedule(Object.assign({
        startMg: 8, n: 6, filmMm: 22, film2Mm: 22, targetMg: 1, stripMg: 8,
        switch2mg: true, holdDays: null, nBelow3: null, stopMode: "reach",
        filmStrengthMg: null, cutMode: "geometric",
      }, o)),
      c
    );
    compareRows(label, js, py, fail);
    compareSummary(label, js, py, fail);
    compareMonths(label, js, py, fail);
  }

  /* compare_classic() builds its own schedules in "above" stop mode, so the
     rows above never touch it. Three starts, because the table is derived from
     whatever start/target/strip the reader has set, not from the defaults. */
  for (const [startMg, targetMg, stripMg, cutMode] of [
    [8, 1, 8, "geometric"], [16, 1, 8, "geometric"], [12, 0.5, 12, "geometric"],
    [32, 0.5, 8, "geometric"], [8, 1, 8, "linear"], [8, 0, 8, "linear"],
    [16, 0, 8, "linear"],
  ]) {
    const label = `compare ${startMg}/${targetMg}/${stripMg} ${cutMode}`;
    const py = pyRun({ startMg, targetMg, stripMg, cutMode, compare: true }).compare;
    const js = await page.evaluate(
      ([s, t, m, cm]) => window.SASTaperInternals.compareClassic(s, t, m, cm),
      [startMg, targetMg, stripMg, cutMode]
    );
    compareCompare(label, js, py, fail);
  }

  /* baseFilmMg picks the smallest official film that holds the start dose, or
     8 mg above 12 where none does; a mismatch here silently changes every mm
     figure on the page. */
  for (const mg of [0.5, 2, 2.5, 4, 4.1, 8, 8.5, 12, 12.5, 16, 64]) {
    const js = await page.evaluate((v) => window.SASTaperInternals.baseFilmMg(v), mg);
    const py = pyRun({ startMg: mg, stripMg: mg }).base_film_mg;
    if (js !== py) fail(`baseFilmMg(${mg}) = ${js} (js) vs ${py} (py)`);
  }

  /* fractionCut() is the second thing written twice on both sides, and unlike
     the ladder it is a search with a tie-break, exactly the kind of code that
     drifts silently. Swept across the whole 0-1 range on several film sizes and
     both tolerance regimes, comparing every field of the result. */
  {
    const FRAC_CASES = [];
    for (const [filmMg, fullMm, wideMm] of [[8, 22, 12.8], [2, 22, 12.8],
                                            [12, 22, 19.2], [4, 22, 25.6],
                                            [8, 20, 12.8], [8, 30, 12.8]]) {
      for (const tolMg of [0, 0.05, 0.18, 0.4]) {
        for (let i = 1; i <= 400; i++) {
          FRAC_CASES.push({ want: i / 400, filmMg, fullMm, wideMm, tolMg });
        }
        /* The exact grid points too: ties are where a tie-break shows. */
        for (const L of [1, 2, 3, 4, 8]) {
          for (const S of [1, 2, 3, 4]) {
            for (let k = 1; k <= L * S; k++) {
              FRAC_CASES.push({ want: k / (L * S), filmMg, fullMm, wideMm, tolMg });
            }
          }
        }
      }
    }
    const jsFrac = await page.evaluate((cases) => cases.map(
      (c) => window.SASTaperInternals.fractionCut(c.want, c.filmMg, c.fullMm, c.wideMm, c.tolMg)),
      FRAC_CASES);
    const pyFrac = JSON.parse(execFileSync("python3", ["-c", PY_FRAC], {
      cwd: REPO, input: JSON.stringify(FRAC_CASES), maxBuffer: 1 << 30,
    }));
    const FRAC_FIELDS = [
      ["longDiv", "long_div"], ["shortDiv", "short_div"], ["cells", "cells"],
      ["columns", "columns"], ["tabCells", "tab_cells"], ["cuts", "cuts"],
      ["pieces", "pieces"], ["fraction", "fraction"], ["doseMg", "dose_mg"],
      ["wantMg", "want_mg"], ["errorMg", "error_mg"], ["label", "label"],
      ["exact", "exact"],
    ];
    for (let i = 0; i < FRAC_CASES.length; i++) {
      const c = FRAC_CASES[i], a = jsFrac[i], e = pyFrac[i];
      const tag = `fractionCut(${c.want.toFixed(4)}, ${c.filmMg}mg, ${c.fullMm}mm, tol ${c.tolMg})`;
      if (!a || !e) { fail(`${tag}: ${a} (js) vs ${e} (py)`); continue; }
      for (const [j, p] of FRAC_FIELDS) {
        comparisons++;
        if (typeof a[j] === "number") {
          if (Math.abs(a[j] - e[p]) > TOL) fail(`${tag}: ${j} = ${a[j]} (js) vs ${e[p]} (py)`);
        } else if (a[j] !== e[p]) {
          fail(`${tag}: ${j} = ${JSON.stringify(a[j])} (js) vs ${JSON.stringify(e[p])} (py)`);
        }
      }
    }
    fracChecked = FRAC_CASES.length;
  }

  /* The matrix: same grid through both implementations, one process each. */
  const pyMatrix = JSON.parse(execFileSync("python3", ["-c", PY_MATRIX], {
    cwd: REPO, input: JSON.stringify(MATRIX), maxBuffer: 1 << 30,
  }));
  const jsMatrix = await page.evaluate((cases) => cases.map((c) =>
    window.SASTaperInternals.buildSchedule(Object.assign({
      startMg: 8, n: 6, filmMm: 22, film2Mm: 22, targetMg: 1, stripMg: 8,
      switch2mg: true, holdDays: null, nBelow3: null, stopMode: "reach",
      filmStrengthMg: null, cutMode: "geometric",
    }, c))), MATRIX);

  let matrixRows = 0;
  let widestDay = 0;
  const shapes = { multi: 0, spareFilm: 0, noCut: 0, wholeFilms: 0, linear: 0, reachedZero: 0 };
  for (let i = 0; i < MATRIX.length; i++) {
    const label = "matrix " + JSON.stringify(MATRIX[i]);
    compareRows(label, jsMatrix[i], pyMatrix[i], fail);
    compareSummary(label, jsMatrix[i], pyMatrix[i], fail);
    compareMonths(label, jsMatrix[i], pyMatrix[i], fail);
    if (jsMatrix[i].zeroDay != null) shapes.reachedZero++;
    for (const r of jsMatrix[i].rows) {
      matrixRows++;
      widestDay = Math.max(widestDay, r.filmsOut);
      if (r.filmsOut > 1) shapes.multi++;
      if (r.spareMm > 0) shapes.spareFilm++;
      if (r.cutTakeMm === 0) shapes.noCut++;
      if (r.takeFilms > 0) shapes.wholeFilms++;
      if (jsMatrix[i].cutMode === "linear") shapes.linear++;
    }
  }
  /* A grid that only produced one-film days would agree perfectly and prove
     nothing about the layout, so the shape of the coverage is itself checked. */
  if (widestDay < 14) fail(`matrix never reached a 14-film day (widest ${widestDay})`);
  for (const [k, v] of Object.entries(shapes)) {
    if (v === 0) fail(`matrix produced no ${k} rows`);
  }

  /* The lag curve is display-only and lives only in index.html, so the ladder
     diff cannot see it. A 900 h half-life used to be clamped to 80, which made
     the dashed line hug the doses. These properties are the shape the graph
     has to have: a drop stays above the new dose, a jump stays below, a long
     half-life stays near the start, and the recurrence matches the closed
     form of a single step. */
  let lagChecked = 0;
  {
    const report = await page.evaluate(() => {
      const I = window.SASTaperInternals;
      const fails = [];
      let n = 0;
      const check = (ok, msg) => { n++; if (!ok) fails.push(msg); };
      const decayOf = (hl) => Math.exp(-Math.LN2 * 24 / hl);
      const closed = (d0, d, hl, day) => d + (d0 - d) * Math.pow(decayOf(hl), day);

      check(typeof I.lagFromDoses === "function", "lagFromDoses is not exported");
      check(typeof I.lagSeries === "function", "lagSeries is not exported");
      check(I.HALF_LIFE_MAX_H === 2160, `HALF_LIFE_MAX_H is ${I.HALF_LIFE_MAX_H}, not 2160`);
      check(I.lagFromDoses([8], 0, 8).length === 0, "half-life 0 should hide the curve");
      check(I.lagSeries([], 32, 8).length === 0, "empty rows should yield no lag points");

      const HLS = [24, 32, 36, 90, 456, 900, 1440, 2160];
      const shapes = { drop: 0, jump: 0, wash: 0, longStay: 0 };
      for (const hl of HLS) {
        const down = I.lagFromDoses(Array(40).fill(4), hl, 8);
        const up = I.lagFromDoses(Array(40).fill(8), hl, 4);
        const wash = I.lagFromDoses(Array(40).fill(0), hl, 8);
        check(down.length === 41 && up.length === 41 && wash.length === 41,
          `${hl}h series length ${down.length}/${up.length}/${wash.length}`);
        for (let i = 0; i < down.length; i++) {
          check(Math.abs(down[i].eff - closed(8, 4, hl, i)) < 1e-9,
            `drop closed form ${hl}h day ${i}: ${down[i].eff} vs ${closed(8, 4, hl, i)}`);
          check(Math.abs(up[i].eff - closed(4, 8, hl, i)) < 1e-9,
            `jump closed form ${hl}h day ${i}: ${up[i].eff} vs ${closed(4, 8, hl, i)}`);
          check(Math.abs(wash[i].eff - closed(8, 0, hl, i)) < 1e-9,
            `washout closed form ${hl}h day ${i}: ${wash[i].eff} vs ${closed(8, 0, hl, i)}`);
          if (i === 0) continue;
          check(down[i].eff + 1e-9 >= 4,
            `drop ${hl}h day ${i} fell below the new dose (${down[i].eff})`);
          check(up[i].eff - 1e-9 <= 8,
            `jump ${hl}h day ${i} rose above the new dose (${up[i].eff})`);
          /* Until the closed form has numerically landed, the series must
             still be on the lag side of the new dose: above after a drop,
             below after a jump. Late days of a short half-life really have
             landed, and 4 + 1e-12 would then fail as a false "already there". */
          if (closed(8, 4, hl, i) - 4 > 1e-9) {
            check(down[i].eff > 4, `drop ${hl}h day ${i} already landed`);
          }
          if (8 - closed(4, 8, hl, i) > 1e-9) {
            check(up[i].eff < 8, `jump ${hl}h day ${i} already landed`);
          }
          shapes.drop++;
          shapes.jump++;
          shapes.wash++;
        }
      }

      const sched = I.buildSchedule({
        startMg: 8, n: 6, filmMm: 22, film2Mm: 22, targetMg: 1, stripMg: 8,
        switch2mg: true, holdDays: null, nBelow3: null, stopMode: "reach",
        filmStrengthMg: null, cutMode: "geometric",
      });
      const t36 = I.lagSeries(sched.rows, 36, sched.startMg);
      const t90 = I.lagSeries(sched.rows, 90, sched.startMg);
      const t900 = I.lagSeries(sched.rows, 900, sched.startMg);
      check(t36.length === t90.length && t90.length === t900.length && t900.length > 60,
        `taper lag lengths ${t36.length}/${t90.length}/${t900.length}`);
      const last = t900.length - 1;
      check(t900[last].eff > t90[last].eff && t90[last].eff > t36[last].eff,
        `longer half-life should stay higher: 900=${t900[last].eff} 90=${t90[last].eff} 36=${t36[last].eff}`);
      check(t900[last].eff - t900[last].dose > 2,
        `900 h hugged the ladder at the end: gap ${t900[last].eff - t900[last].dose}`);
      shapes.longStay++;
      const d6_36 = t36.find((p) => p.day === 6);
      check(d6_36 && d6_36.eff - d6_36.dose < 0.2,
        `36 h should nearly land by day 6, gap ${d6_36 && d6_36.eff - d6_36.dose}`);
      const d6_900 = t900.find((p) => p.day === 6);
      const remain = d6_900 ? (d6_900.eff - d6_900.dose) / (8 - d6_900.dose) : 0;
      check(remain > 0.8,
        `900 h remaining fraction after cycle 1 is ${remain}, expected > 0.8`);

      const flat = [];
      for (const r of sched.rows) for (let i = 0; i < r.days; i++) flat.push(r.dailyMg);
      const fromFlat = I.lagFromDoses(flat, 32, 8);
      const fromRows = I.lagSeries(sched.rows, 32, 8);
      check(fromFlat.length === fromRows.length, "lagSeries length mismatch vs flattened doses");
      for (let i = 0; i < fromFlat.length; i++) {
        check(Math.abs(fromFlat[i].eff - fromRows[i].eff) < 1e-12,
          `lagSeries vs lagFromDoses at day ${i}`);
      }

      for (const [k, v] of Object.entries(shapes)) {
        check(v > 0, `lag coverage never reached a ${k} case`);
      }
      check(HLS.indexOf(900) !== -1 && HLS.indexOf(36) !== -1,
        "lag half-life sweep dropped 36 or 900");

      return { fails, n, shapes };
    });
    lagChecked = report.n;
    comparisons += report.n;
    for (const f of report.fails) fail("lag: " + f);

    const form = await page.evaluate(() => {
      const I = window.SASTaperInternals;
      const el = document.getElementById("halfLifeH");
      const warn = () => (document.getElementById("warnings").innerText || "");
      const cap = () => {
        const p = document.querySelector("#charts .chart .cap");
        return p ? p.innerText : "";
      };
      const maxAttr = el.getAttribute("max");
      el.value = "900";
      el.dispatchEvent(new Event("input", { bubbles: true }));
      const at900 = { value: el.value, warn: warn(), cap: cap() };
      el.value = String(I.HALF_LIFE_MAX_H + 1);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      const over = { value: el.value, warn: warn() };
      el.value = "32";
      el.dispatchEvent(new Event("input", { bubbles: true }));
      return { maxAttr, maxH: I.HALF_LIFE_MAX_H, at900, over };
    });
    comparisons += 5;
    lagChecked += 5;
    if (form.maxAttr !== String(form.maxH)) {
      fail(`lag: input max=${form.maxAttr} vs HALF_LIFE_MAX_H=${form.maxH}`);
    }
    if (form.at900.value !== "900") fail(`lag: typing 900 stored ${form.at900.value}`);
    if (/Half-life/.test(form.at900.warn)) fail(`lag: typing 900 still clamped: ${form.at900.warn}`);
    if (!form.at900.cap.includes("900 h")) fail(`lag: caption after 900 is ${form.at900.cap}`);
    if (!form.at900.cap.includes("stays up while the ladder drops")) {
      fail(`lag: 900 h caption does not mention the curve staying up: ${form.at900.cap}`);
    }
    if (form.over.value !== String(form.maxH)) {
      fail(`lag: ${form.maxH + 1} clamped to ${form.over.value}, not ${form.maxH}`);
    }
    if (!/Half-life/.test(form.over.warn)) {
      fail(`lag: over-max half-life produced no clamp warning`);
    }
  }

  /* The explainer is a third copy of lagFromDoses. Same rule as fold.html:
     if the listing's function drifts from the calculator, the page starts
     teaching the wrong algorithm. */
  {
    const lagPage = await browser.newPage();
    await lagPage.goto(LAG_PAGE);
    await lagPage.waitForFunction(() => !!window.SASLagExplainer, null, { timeout: 10000 });
    const cases = [
      { hl: 32, start: 8, doses: Array(20).fill(4) },
      { hl: 36, start: 8, doses: Array(20).fill(4) },
      { hl: 90, start: 4, doses: Array(20).fill(8) },
      { hl: 900, start: 8, doses: Array(20).fill(0) },
      { hl: 1440, start: 8, doses: Array(12).fill(6.6667) },
    ];
    const fromIndex = await page.evaluate((cs) => cs.map((c) =>
      window.SASTaperInternals.lagFromDoses(c.doses, c.hl, c.start)), cases);
    const fromExplainer = await lagPage.evaluate((cs) => cs.map((c) =>
      window.SASLagExplainer.lagFromDoses(c.doses, c.hl, c.start)), cases);
    for (let i = 0; i < cases.length; i++) {
      const a = fromIndex[i], b = fromExplainer[i];
      comparisons++;
      lagChecked++;
      if (a.length !== b.length) {
        fail(`lag explainer case ${i}: length ${b.length} vs calculator ${a.length}`);
        continue;
      }
      for (let d = 0; d < a.length; d++) {
        comparisons++;
        lagChecked++;
        if (Math.abs(a[d].eff - b[d].eff) > TOL) {
          fail(`lag explainer case ${i} day ${d}: ${b[d].eff} vs calculator ${a[d].eff}`);
        }
      }
    }
    await lagPage.close();
  }

  if (pageErrors.length) fail("page errors: " + pageErrors.join("; "));
  await browser.close();

  const checks = CASES.length + 11 + 7 + MATRIX.length;
  if (failures.length) {
    console.error(`FAILED: ${failures.length} mismatch(es) across ${checks} checks:`);
    for (const f of failures.slice(0, 40)) console.error("  " + f);
    process.exit(1);
  }
  console.log(
    `OK. index.html matches taper.py across ${CASES.length + MATRIX.length} schedules `
    + `(${matrixRows} matrix cycles, widest day ${widestDay} films: `
    + `${shapes.multi} multi-film, ${shapes.spareFilm} whose sliver runs onto unopened film, `
    + `${shapes.noCut} with nothing to cut), 11 film sizes, `
    + `every month bucket and the n = 6/8/10 table, and `
    + `${fracChecked.toLocaleString("en-US")} folded-grid cuts, and `
    + `${lagChecked.toLocaleString("en-US")} lag-curve checks. `
    + `${comparisons.toLocaleString("en-US")} field comparisons in all.`
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
