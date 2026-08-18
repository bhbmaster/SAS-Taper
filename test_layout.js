#!/usr/bin/env node
/* Layout checks for SAS-Taper. Run: node test_layout.js
 *
 * index.html has to stay readable from a 280px phone to a 1920px desktop, in
 * both themes, and several of its parts are positioned from measured pixels
 * rather than by normal flow — the ruler tick captions, the life-size cut
 * label, the calendar grid. Those have broken four separate times: captions
 * stacked on each other, a percentage painted over a button, "SAVE" sliced in
 * half, the page scrolling sideways on a narrow phone.
 *
 * Every one of those was found by sweeping viewports by hand and then lost
 * again, because nothing in the repo re-ran the sweep. This is that sweep,
 * committed.
 *
 * Four failure modes, checked at every size:
 *   overflow   the page scrolls horizontally
 *   overlap    two pieces of text are drawn on top of each other
 *   clipping   a box is too small for the text inside it
 *   spill      an absolutely positioned label escapes its container
 * Plus any console or page error.
 *
 * Needs playwright-core and a Chromium; skips with exit 0 without them.
 */

"use strict";

const { launchOrSkip, PAGE } = require("./test_browser");

/* Phone through desktop, with the known breakpoints (360, 420, 640, 820) and
   both sides of each. 280 is a Galaxy Fold cover screen — the narrowest thing
   worth supporting, and where three of the four bugs showed up first. */
const WIDTHS = [280, 320, 360, 390, 414, 430, 540, 639, 641, 768, 820, 1024, 1280, 1920];
const CAL_WIDTHS = [280, 360, 414, 768, 1024, 1440];
const THEMES = ["dark", "light"];

/* Groups whose members must never be drawn on top of one another. Each is a
   place where text is positioned rather than flowed. */
const OVERLAP_GROUPS = {
  "ruler ticks": "#ruler .ticks span",
  "scale row": ".scale-row label span.k, .scale-row .pct, .scale-row button, .viz-nav button",
  "strip dims": "#ruler .strip-dims span",
  "calendar controls": ".cal-controls .k, .cal-controls button",
  "calendar cells": ".cal-cell[data-cycle]",
};

/* Boxes that hide their overflow, so text too big for them is silently cut. */
const CLIP_SELECTORS = [
  "#ruler .film > div[data-short]",
  "#stripViz .strip-full > div[data-short]",
  ".cal-cell[data-cycle]",
];

/* Absolutely positioned labels that must stay inside the named container. */
const SPILL_PAIRS = [[".strip-cut-label", ".strip-draw"]];

const probe = () => {
  const de = document.documentElement;
  const out = { scrollX: de.scrollWidth - de.clientWidth, overlaps: [], clipped: [], spills: [] };
  const vis = (n) => n.offsetWidth > 0 && n.offsetHeight > 0
    && getComputedStyle(n).display !== "none" && getComputedStyle(n).visibility !== "hidden";

  for (const [name, sel] of Object.entries(window.__groups)) {
    const els = [...document.querySelectorAll(sel)].filter(vis);
    for (let i = 0; i < els.length; i++) {
      for (let j = i + 1; j < els.length; j++) {
        const A = els[i], B = els[j];
        if (A.contains(B) || B.contains(A)) continue;
        const a = A.getBoundingClientRect(), b = B.getBoundingClientRect();
        const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        /* 2px of slack: adjacent boxes and grid gaps should not count. */
        if (ox > 2 && oy > 2) {
          out.overlaps.push(`${name}: "${A.textContent.trim().slice(0, 18)}" over "${B.textContent.trim().slice(0, 18)}"`);
        }
      }
    }
  }

  for (const sel of window.__clip) {
    for (const n of [...document.querySelectorAll(sel)].filter(vis)) {
      if (!n.textContent.trim()) continue;
      if (n.scrollWidth > n.clientWidth + 1 || n.scrollHeight > n.clientHeight + 1) {
        out.clipped.push(`${sel}: "${n.textContent.trim().slice(0, 18)}" needs ${n.scrollWidth}x${n.scrollHeight} in ${n.clientWidth}x${n.clientHeight}`);
      }
    }
  }

  for (const [labelSel, boxSel] of window.__spill) {
    const l = document.querySelector(labelSel), b = document.querySelector(boxSel);
    if (!l || !b || !vis(l)) continue;
    const lb = l.getBoundingClientRect(), bb = b.getBoundingClientRect();
    if (lb.right > bb.right + 1 || lb.left < bb.left - 1) {
      out.spills.push(`${labelSel} escapes ${boxSel} by ${Math.round(Math.max(lb.right - bb.right, bb.left - lb.left))}px`);
    }
  }
  return out;
};

(async () => {
  const browser = await launchOrSkip();
  if (!browser) process.exit(0);

  const failures = [];
  let checks = 0;
  const record = (where, r, errs) => {
    checks++;
    if (r.scrollX > 0) failures.push(`${where}: page scrolls horizontally by ${r.scrollX}px`);
    r.overlaps.forEach((m) => failures.push(`${where}: ${m}`));
    r.clipped.forEach((m) => failures.push(`${where}: clipped ${m}`));
    r.spills.forEach((m) => failures.push(`${where}: ${m}`));
    errs.forEach((m) => failures.push(`${where}: ${m}`));
  };

  async function openPage(width, theme) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, timezoneId: "America/Los_Angeles" });
    const page = await ctx.newPage();
    const errs = [];
    page.on("pageerror", (e) => errs.push("page error: " + e));
    page.on("console", (m) => { if (m.type() === "error") errs.push("console error: " + m.text()); });
    await page.goto(PAGE);
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForFunction(() => !!window.SASTaperInternals, null, { timeout: 10000 });
    await page.evaluate(([g, c, s]) => {
      window.__groups = g; window.__clip = c; window.__spill = s;
    }, [OVERLAP_GROUPS, CLIP_SELECTORS, SPILL_PAIRS]);
    if (theme === "light") {
      await page.click("#themeBtn");
      await page.waitForTimeout(60);
    }
    return { ctx, page, errs };
  }

  const setField = (page, id, v) => page.evaluate(([i, val]) => {
    const el = document.getElementById(i);
    el.value = String(val);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, [id, v]);

  const selectCycle = (page, c) => page.evaluate((n) => {
    const tr = document.querySelector(`#schedTable tbody tr[data-cycle="${n}"]`);
    if (tr) tr.click();
  }, c);

  /* 1. The page itself, no calendar. Cycle 1 has no already-off region; a
        later cycle has all four tick captions competing for the same row. */
  for (const theme of THEMES) {
    for (const width of WIDTHS) {
      const { ctx, page, errs } = await openPage(width, theme);
      for (const cycle of [1, 5, 11]) {
        await selectCycle(page, cycle);
        await page.waitForTimeout(60);
        errs.length = 0;
        record(`${theme} ${width}px cycle ${cycle}`, await page.evaluate(probe), errs);
      }
      /* Zoom extremes move the life-size drawing and its label. */
      for (const scale of [50, 300]) {
        await setField(page, "stripScale", scale);
        await page.waitForTimeout(60);
        errs.length = 0;
        record(`${theme} ${width}px zoom ${scale}%`, await page.evaluate(probe), errs);
      }
      await ctx.close();
    }
  }

  /* 2. The calendar, in both densities and all three measurement modes. */
  for (const theme of THEMES) {
    for (const width of CAL_WIDTHS) {
      const { ctx, page, errs } = await openPage(width, theme);
      await setField(page, "startDate", "2026-08-01");
      await page.waitForTimeout(180);
      for (const density of ["detailed", "compact"]) {
        if (density === "compact") {
          await page.click("#calDensityBtn");
          await page.waitForTimeout(80);
        }
        for (const mode of ["off", "take", "save"]) {
          if (mode !== "off") {
            await page.click("#calModeBtn");
            await page.waitForTimeout(80);
          }
          errs.length = 0;
          record(`${theme} ${width}px calendar ${density}/${mode}`, await page.evaluate(probe), errs);
        }
        await page.click("#calModeBtn"); // back to "off" for the next density
        await page.waitForTimeout(60);
      }
      /* Every scheduled day must have a cell, and only those. */
      const cells = await page.evaluate(() => ({
        n: document.querySelectorAll(".cal-cell[data-cycle]").length,
        end: window.SASTaperInternals.buildSchedule({
          startMg: 8, n: 6, filmMm: 22, film2Mm: 22, targetMg: 1, stripMg: 8,
          switch2mg: true, holdDays: null, nBelow3: null, stopMode: "reach",
        }).endDay,
      }));
      checks++;
      if (cells.n !== cells.end) {
        failures.push(`${theme} ${width}px calendar: ${cells.n} day cells for a ${cells.end}-day run`);
      }
      await ctx.close();
    }
  }

  /* 3. Inputs that reshape the page: doses needing more than one film a day, a
        target that yields no ladder, the longest run the cap allows. The
        multi-film cases each name the cycles worth looking at — a two-strip run
        grows a kit banner, a ×N pill and, at the cycle where the ladder crosses
        a whole-film boundary, a second film bar and its caption. */
  for (const [label, fields, cycles] of [
    ["oversize start dose", { startMg: 64, stripMg: 8 }, [1, 5]],
    ["two-strip start", { startMg: 16, stripMg: 8 }, [1, 2, 4, 5, 12]],
    ["two-strip on 12 mg film", { startMg: 20, filmStrengthMg: 12 }, [1, 3]],
    ["four-strip start", { startMg: 30, stripMg: 8, n: 3 }, [1, 2]],
    ["sliver over one film", { startMg: 40, n: 2, targetMg: 8 }, [1, 2]],
    ["empty ladder", { startMg: 1.1, targetMg: 1 }, [1]],
    ["max cycles", { n: 30, targetMg: 0.1 }, [1]],
    ["stretched cycles", { holdDays: 30 }, [1]],
    ["no 2 mg switch", { targetMg: 0.4 }, [1]],
  ]) {
    for (const width of [320, 768, 1280]) {
      for (const theme of THEMES) {
        const { ctx, page, errs } = await openPage(width, theme);
        for (const [k, v] of Object.entries(fields)) await setField(page, k, v);
        await page.waitForTimeout(200);
        for (const cycle of cycles) {
          await selectCycle(page, cycle);
          await page.waitForTimeout(80);
          errs.length = 0;
          record(`${label} ${theme} @${width}px cycle ${cycle}`, await page.evaluate(probe), errs);
        }
        await ctx.close();
      }
    }
  }

  /* 4. The calendar on a two-strip run: every cell carries a ×N beside the
        dose, in cells only 44px wide once compact mode is on. */
  for (const width of CAL_WIDTHS) {
    const { ctx, page, errs } = await openPage(width, "dark");
    await setField(page, "startMg", 16);
    await setField(page, "startDate", "2026-08-01");
    await page.waitForTimeout(220);
    for (const density of ["detailed", "compact"]) {
      if (density === "compact") {
        await page.click("#calDensityBtn");
        await page.waitForTimeout(80);
      }
      for (const mode of ["off", "take", "save"]) {
        if (mode !== "off") {
          await page.click("#calModeBtn");
          await page.waitForTimeout(80);
        }
        errs.length = 0;
        record(`two-strip calendar ${density}/${mode} @${width}px`, await page.evaluate(probe), errs);
      }
      await page.click("#calModeBtn");
      await page.waitForTimeout(60);
    }
    await ctx.close();
  }

  await browser.close();

  if (failures.length) {
    console.error(`FAILED — ${failures.length} layout problem(s) across ${checks} checks:`);
    const seen = new Set();
    for (const f of failures) {
      if (seen.has(f)) continue;
      seen.add(f);
      if (seen.size > 40) { console.error(`  … and ${failures.length - 40} more`); break; }
      console.error("  " + f);
    }
    process.exit(1);
  }
  console.log(`OK — no overflow, overlap, clipping or spill across ${checks} viewport states`);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
