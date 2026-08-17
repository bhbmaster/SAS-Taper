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
const fs = require("fs");
const path = require("path");

const REPO = __dirname;
const PAGE = "file://" + path.join(REPO, "index.html");
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
  return JSON.parse(execFileSync("python3", args, { cwd: REPO, maxBuffer: 1 << 28 }));
}

/* playwright-core deliberately ships no browser, so find one: an explicit
   CHROMIUM_PATH first, then a Playwright download cache (Linux and macOS
   defaults), then whatever Chrome or Chromium is already installed. */
function findBrowser() {
  const envPath = process.env.CHROMIUM_PATH;
  if (envPath && fs.existsSync(envPath)) return envPath;

  const home = process.env.HOME || "";
  const caches = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    "/opt/pw-browsers",
    home && path.join(home, ".cache/ms-playwright"),
    home && path.join(home, "Library/Caches/ms-playwright"),
  ].filter(Boolean);
  const rels = [
    "chrome-linux/chrome",
    "chrome-linux/headless_shell",
    "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
    "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium",
    "chrome-headless-shell-mac/chrome-headless-shell",
  ];
  for (const root of caches) {
    if (!fs.existsSync(root)) continue;
    for (const d of fs.readdirSync(root)) {
      for (const rel of rels) {
        const p = path.join(root, d, rel);
        if (fs.existsSync(p)) return p;
      }
    }
  }

  for (const p of [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
  ]) {
    if (fs.existsSync(p)) return p;
  }
  return null;
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

(async () => {
  let chromium;
  try {
    ({ chromium } = require("playwright-core"));
  } catch (e) {
    console.log("skipped: playwright-core is not installed (npm i -D playwright-core)");
    process.exit(0);
  }
  const executablePath = findBrowser();
  if (!executablePath) {
    console.log("skipped: no Chromium found (set CHROMIUM_PATH or PLAYWRIGHT_BROWSERS_PATH)");
    process.exit(0);
  }

  const failures = [];
  const fail = (m) => failures.push(m);

  const browser = await chromium.launch({ executablePath, args: ["--no-sandbox"] });
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
      }, o)),
      c
    );
    compareRows(label, js, py, fail);
    compareSummary(label, js, py, fail);
  }

  /* baseFilmMg picks the smallest official film that holds the start dose;
     a mismatch here silently changes every mm figure on the page. */
  for (const mg of [0.5, 2, 2.5, 4, 4.1, 8, 8.5, 12]) {
    const js = await page.evaluate((v) => window.SASTaperInternals.baseFilmMg(v), mg);
    const py = pyRun({ startMg: mg, stripMg: mg }).base_film_mg;
    if (js !== py) fail(`baseFilmMg(${mg}) = ${js} (js) vs ${py} (py)`);
  }

  if (pageErrors.length) fail("page errors: " + pageErrors.join("; "));
  await browser.close();

  const checks = CASES.length + 8;
  if (failures.length) {
    console.error(`FAILED — ${failures.length} mismatch(es) across ${checks} checks:`);
    for (const f of failures.slice(0, 40)) console.error("  " + f);
    process.exit(1);
  }
  console.log(`OK — index.html matches taper.py across ${CASES.length} schedules and 8 film sizes`);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
