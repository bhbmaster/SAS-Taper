#!/usr/bin/env node
/* Parity checks for SAS-Taper. Run: node test_parity.js
 *
 * The ladder maths is implemented twice — buildSchedule() in index.html and
 * build_schedule() in taper.py — and the site's footer promises the two agree.
 * test_taper.py only covers the Python side, so this diffs the JS one against
 * it: same inputs into both, then every row field compared.
 *
 * Needs playwright-core and a Chromium. If neither is present the script says
 * so and exits 0 — a checkout without a browser should not fail the suite.
 */

"use strict";

const { execFileSync } = require("child_process");
const { launchOrSkip, PAGE } = require("./test_browser");

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
  // zeroed summary fields rather than leaving them undefined — an undefined
  // endDay turned Math.max(endDay, 1) into NaN and broke the comparison chart.
  { startMg: 1.1, targetMg: 1, stopMode: "above" },
  { startMg: 8, targetMg: 8, stopMode: "above" },
];

function pyRun(c) {
  const args = ["taper.py", "--json"];
  for (const [k, v] of Object.entries(c)) {
    if (FLAGS[k]) args.push(FLAGS[k], String(v));
  }
  if (c.switch2mg === false) args.push("--no-switch-2mg");
  if (c.compare) args.push("--compare");
  return JSON.parse(execFileSync("python3", args, { cwd: REPO, maxBuffer: 1 << 28 }));
}

function compareRows(label, js, py, fail) {
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
      if (Math.abs(js[i][k] - py[i][p]) > 1e-6) {
        fail(`${label}: compare row ${i} ${k} = ${js[i][k]} (js) vs ${py[i][p]} (py)`);
      }
    }
  }
}

function compareSummary(label, js, py, fail) {
  for (const [j, p] of SUMMARY) {
    const av = js[j];
    const ev = py[p];
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
for (const startMg of MATRIX_STARTS) {
  for (const n of MATRIX_NS) {
    for (const filmStrengthMg of MATRIX_STRENGTHS) {
      MATRIX.push({ startMg, n, filmStrengthMg, targetMg: Math.min(1, startMg / 2) });
    }
  }
}
/* Film length only scales millimetres, so it gets a slice rather than the full
   cross — but it has to be in here, because every layout figure is derived
   from it. */
for (const startMg of MATRIX_STARTS) {
  for (const filmStrengthMg of MATRIX_STRENGTHS) {
    for (const filmMm of [20, 30]) {
      MATRIX.push({ startMg, n: 6, filmStrengthMg, filmMm, film2Mm: filmMm,
                    targetMg: Math.min(1, startMg / 2) });
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
    )))
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
        filmStrengthMg: null,
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
  for (const [startMg, targetMg, stripMg] of [[8, 1, 8], [16, 1, 8], [12, 0.5, 12], [32, 0.5, 8]]) {
    const label = `compare ${startMg}/${targetMg}/${stripMg}`;
    const py = pyRun({ startMg, targetMg, stripMg, compare: true }).compare;
    const js = await page.evaluate(
      ([s, t, m]) => window.SASTaperInternals.compareClassic(s, t, m),
      [startMg, targetMg, stripMg]
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

  /* The matrix: same grid through both implementations, one process each. */
  const pyMatrix = JSON.parse(execFileSync("python3", ["-c", PY_MATRIX], {
    cwd: REPO, input: JSON.stringify(MATRIX), maxBuffer: 1 << 30,
  }));
  const jsMatrix = await page.evaluate((cases) => cases.map((c) =>
    window.SASTaperInternals.buildSchedule(Object.assign({
      startMg: 8, n: 6, filmMm: 22, film2Mm: 22, targetMg: 1, stripMg: 8,
      switch2mg: true, holdDays: null, nBelow3: null, stopMode: "reach",
      filmStrengthMg: null,
    }, c))), MATRIX);

  let matrixRows = 0;
  let widestDay = 0;
  const shapes = { multi: 0, spareFilm: 0, noCut: 0, wholeFilms: 0 };
  for (let i = 0; i < MATRIX.length; i++) {
    const label = "matrix " + JSON.stringify(MATRIX[i]);
    compareRows(label, jsMatrix[i], pyMatrix[i], fail);
    compareSummary(label, jsMatrix[i], pyMatrix[i], fail);
    compareMonths(label, jsMatrix[i], pyMatrix[i], fail);
    for (const r of jsMatrix[i].rows) {
      matrixRows++;
      widestDay = Math.max(widestDay, r.filmsOut);
      if (r.filmsOut > 1) shapes.multi++;
      if (r.spareMm > 0) shapes.spareFilm++;
      if (r.cutTakeMm === 0) shapes.noCut++;
      if (r.takeFilms > 0) shapes.wholeFilms++;
    }
  }
  /* A grid that only produced one-film days would agree perfectly and prove
     nothing about the layout, so the shape of the coverage is itself checked. */
  if (widestDay < 14) fail(`matrix never reached a 14-film day (widest ${widestDay})`);
  for (const [k, v] of Object.entries(shapes)) {
    if (v === 0) fail(`matrix produced no ${k} rows`);
  }

  if (pageErrors.length) fail("page errors: " + pageErrors.join("; "));
  await browser.close();

  const checks = CASES.length + 11 + 4 + MATRIX.length;
  if (failures.length) {
    console.error(`FAILED — ${failures.length} mismatch(es) across ${checks} checks:`);
    for (const f of failures.slice(0, 40)) console.error("  " + f);
    process.exit(1);
  }
  console.log(
    `OK — index.html matches taper.py across ${CASES.length + MATRIX.length} schedules `
    + `(${matrixRows} matrix cycles, widest day ${widestDay} films: `
    + `${shapes.multi} multi-film, ${shapes.spareFilm} whose sliver runs onto unopened film, `
    + `${shapes.noCut} with nothing to cut), 11 film sizes, `
    + `every month bucket and the n = 6/8/10 table`
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
