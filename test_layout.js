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
  "film bars": "#ruler .film",
  "life-size bars": "#stripViz .strip-full",
  "calendar controls": ".cal-controls .k, .cal-controls button",
  "calendar cells": ".cal-cell[data-cycle]",
};

/* Boxes that hide their overflow, so text too big for them is silently cut. */
const CLIP_SELECTORS = [
  "#ruler .film > div[data-short]",
  "#stripViz .strip-full > div[data-short]",
  ".cal-cell[data-cycle]",
];

/* One bar per film the day needs, in both drawings. If the two disagree the
   reader is being shown two different days on one page. */
const BAR_COUNT_PAIR = ["#ruler .film", "#stripViz .strip-full"];

/* Absolutely positioned labels that must stay inside the named container. */
const SPILL_PAIRS = [[".strip-cut-label", ".strip-draw"]];

const probe = () => {
  const de = document.documentElement;
  const out = { scrollX: de.scrollWidth - de.clientWidth, overlaps: [], clipped: [], spills: [], bars: [] };
  const vis = (n) => n.offsetWidth > 0 && n.offsetHeight > 0
    && getComputedStyle(n).display !== "none" && getComputedStyle(n).visibility !== "hidden";

  /* Each drawing shows one bar per film it is describing — always, for every
     cycle of every run. The count changing between cycles of the same ladder
     means the reader is looking at a picture that is not the day in front of
     them.

     The two panels answer different questions, so they are checked separately.
     The cut-mark panel is the schedule's own film strength, so its count is the
     row's filmsOut. The life-size panel redraws the same day on whichever
     strength is selected in the size table — a 12 mg film holds a day in fewer
     strips than an 8 mg one — so its count comes from re-running the layout at
     that strength. Every official film is 22 mm on the cut axis. */
  {
    const row = window.__selectedRow && window.__selectedRow();
    if (row) {
      const ruler = document.querySelectorAll("#ruler .film").length;
      if (ruler !== row.filmsOut) {
        out.bars.push(`cut-mark panel drew ${ruler} bars for a ${row.filmsOut}-film day`);
      }
      const marked = document.querySelectorAll("#ruler .film.marked").length;
      const wantMarked = row.cutTakeMm > 0 ? 1 : 0;
      if (marked !== wantMarked) out.bars.push(`${marked} marked bars, expected ${wantMarked}`);
      const ticks = document.querySelectorAll("#ruler .ticks").length;
      if (ticks !== wantMarked) out.bars.push(`${ticks} tick rows, expected ${wantMarked}`);

      const picked = document.querySelector("#dimTable tbody tr.selected");
      const specMg = picked ? parseFloat(picked.getAttribute("data-spec")) : row.filmMg;
      const want = window.SASTaperInternals
        .filmLayout(row.cutFromMg, row.sliverMg, specMg, 22).filmsOut;
      const life = document.querySelectorAll("#stripViz .strip-full").length;
      if (life !== want) {
        out.bars.push(`life-size panel drew ${life} bars for a ${want}-film day on ${specMg} mg film`);
      }
      const lifeMarked = document.querySelectorAll("#stripViz .strip-full.marked").length;
      if (lifeMarked > 1) out.bars.push(`life-size panel drew ${lifeMarked} marked bars`);
    }
  }

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

  /* Two counters, because they are two different things and the summary line
     used to conflate them: `states` is one rendered page measured end to end
     (a width × theme × cycle × mode combination), `checks` is every assertion
     the run makes, most but not all of which are a state. */
  const failures = [];
  let checks = 0;
  let states = 0;
  const record = (where, r, errs) => {
    checks++;
    states++;
    if (r.scrollX > 0) failures.push(`${where}: page scrolls horizontally by ${r.scrollX}px`);
    r.overlaps.forEach((m) => failures.push(`${where}: ${m}`));
    r.clipped.forEach((m) => failures.push(`${where}: clipped ${m}`));
    r.spills.forEach((m) => failures.push(`${where}: ${m}`));
    (r.bars || []).forEach((m) => failures.push(`${where}: ${m}`));
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
      /* Open the column glossary: collapsed it is one line and tells the sweep
         nothing about the twelve definitions inside it. */
      const cd = document.querySelector(".coldoc");
      if (cd) cd.open = true;
      window.__selectedRow = window.SASTaperInternals.currentRow;
    }, [OVERLAP_GROUPS, CLIP_SELECTORS, SPILL_PAIRS]);
    if (theme === "light") {
      await page.click("#themeBtn");
      await page.waitForTimeout(60);
    }
    return { ctx, page, errs };
  }

  /* Works for the number inputs and for the cut-mode <select> alike: both
     rebuild the page off an "input" event. */
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
        for (const mode of ["save", "take", "delta"]) {
          if (mode !== "save") {
            await page.click("#calModeBtn");
            await page.waitForTimeout(80);
          }
          errs.length = 0;
          record(`${theme} ${width}px calendar ${density}/${mode}`, await page.evaluate(probe), errs);
        }
        await page.click("#calModeBtn"); // back to "save" for the next density
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

      /* The legend above the grid: one worked cell, its parts named, and a
         swatch per state. It has to say the same things the cells show, so it
         is checked against them rather than against a fixed string — and the
         swatches have to be painted in this theme, not left transparent by a
         colour token that exists in only one of the three blocks. */
      const legend = await page.evaluate(() => {
        const box = document.getElementById("calLegend");
        if (!box || !box.offsetParent) return null;
        const demo = box.querySelector(".cal-cell");
        const first = document.querySelector(".cal-cell[data-cycle]");
        const paint = (sel) => {
          const el = box.querySelector(sel);
          if (!el) return "missing";
          const c = getComputedStyle(el);
          return [c.backgroundColor, c.borderLeftColor, c.borderColor, c.outlineColor, c.boxShadow]
            .join("|");
        };
        return {
          demoLines: demo ? [...demo.children].map((e) => e.textContent.trim()) : null,
          cellLines: first ? [...first.children].map((e) => e.textContent.trim()) : null,
          /* Only the rows the cells actually render at this width: the
             measurement line is dropped on a narrow screen and its bullet has
             to go with it. */
          visibleRows: [...box.querySelectorAll(".rows > div")]
            .filter((e) => e.offsetParent !== null && !e.classList.contains("states")).length,
          demoRows: demo ? [...demo.children].filter((e) => e.offsetParent !== null).length : 0,
          swatches: ["band", "first", "film2", "today", "picked"].map((k) => [k, paint("i." + k)]),
        };
      });
      checks++;
      if (!legend) {
        failures.push(`${theme} ${width}px: the calendar has no visible legend`);
      } else {
        if (legend.demoRows !== legend.visibleRows) {
          failures.push(`${theme} ${width}px legend: ${legend.demoRows} lines in the sample cell `
            + `but ${legend.visibleRows} explaining them`);
        }
        /* The sample cell has to be built the same way the real ones are —
           both ways round, so it cannot drift into showing a unit the grid
           does not, or losing one the grid keeps. */
        for (const u of ["mg", "mm"]) {
          const real = (legend.cellLines || []).join(" ").includes(u);
          const demo = (legend.demoLines || []).join(" ").includes(u);
          if (real !== demo) {
            failures.push(`${theme} ${width}px legend: sample cell ${demo ? "shows" : "omits"} `
              + `the ${u} unit but the real cells ${real ? "show" : "omit"} it`);
          }
        }
        for (const [name, paint] of legend.swatches) {
          if (paint === "missing") {
            failures.push(`${theme} ${width}px legend: no swatch for ${name}`);
          } else if (/rgba\(0, 0, 0, 0\)\|rgba\(0, 0, 0, 0\)/.test(paint)) {
            failures.push(`${theme} ${width}px legend: the ${name} swatch is invisible — `
              + `a colour token missing from this theme?`);
          }
        }
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
    /* Every official strength at the top of the dose range. On 2 mg film a
       32 mg day is sixteen bars stacked in both drawings — the widest the
       inputs allow, and the case most likely to overflow something. */
    ["32 mg on 2 mg film", { startMg: 32, filmStrengthMg: 2, targetMg: 2 }, [1, 3, 6]],
    ["32 mg on 4 mg film", { startMg: 32, filmStrengthMg: 4, targetMg: 2 }, [1, 3, 6]],
    ["32 mg on 8 mg film", { startMg: 32, filmStrengthMg: 8, targetMg: 2 }, [1, 3, 6]],
    ["32 mg on 12 mg film", { startMg: 32, filmStrengthMg: 12, targetMg: 2 }, [1, 3, 6]],
    /* Nothing to cut: dose and sliver both land on whole-film boundaries, so
       the drawing is whole films only and there is no marked bar or tick row. */
    ["whole films, no cut", { startMg: 8, n: 4, filmStrengthMg: 2 }, [1]],
    ["whole films, long run", { startMg: 24, n: 3, filmStrengthMg: 2, targetMg: 2 }, [1, 2]],
    /* Linear mode reshapes the page: a shorter ladder, a constant cut, an
       extra headline tile for the zero day and two warning banners. */
    ["linear default", { cutMode: "linear" }, [1, 3, 5]],
    ["linear to zero", { cutMode: "linear", targetMg: 0 }, [1, 5]],
    ["linear n=30", { cutMode: "linear", n: 30, targetMg: 0 }, [1, 15, 29]],
    ["linear multi-film", { cutMode: "linear", startMg: 32, targetMg: 0 }, [1, 2, 4]],
    ["linear n=2", { cutMode: "linear", n: 2, targetMg: 0 }, [1]],
    ["empty ladder", { startMg: 1.1, targetMg: 1 }, [1]],
    ["max cycles", { n: 30, targetMg: 0.1 }, [1]],
    ["stretched cycles", { holdDays: 30 }, [1]],
    ["no 2 mg switch", { targetMg: 0.4 }, [1]],
  ]) {
    for (const width of [320, 768, 1280]) {
      for (const theme of THEMES) {
        const { ctx, page, errs } = await openPage(width, theme);
        if (fields.filmStrengthMg && fields.filmStrengthMg <= 2) {
          // On 2 mg film the switch would restart the ladder immediately.
          await page.evaluate(() => {
            const c = document.getElementById("switch2");
            c.checked = false;
            c.dispatchEvent(new Event("input", { bubbles: true }));
          });
        }
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

  /* 4. Picking a different strength in the size table. The life-size panel
        redraws the same day on that film, which changes how many strips it
        takes — a 32 mg day is 4 x 8 mg bars but only 3 x 12 mg ones. The
        cut-mark panel above must not move: it is always the schedule's film. */
  for (const width of [360, 768, 1280]) {
    const { ctx, page, errs } = await openPage(width, "dark");
    await setField(page, "startMg", 32);
    await setField(page, "targetMg", 0.5);
    await page.waitForTimeout(220);
    for (const specMg of [2, 4, 8, 12]) {
      await page.evaluate((mg) => {
        const tr = document.querySelector(`#dimTable tbody tr[data-spec="${mg}"]`);
        if (tr) tr.click();
      }, specMg);
      await page.waitForTimeout(120);
      errs.length = 0;
      record(`32 mg drawn on ${specMg} mg film @${width}px`, await page.evaluate(probe), errs);
    }
    /* And back to following the cycle, which is what the button is for. */
    await page.click("#filmFollowCycle");
    await page.waitForTimeout(120);
    errs.length = 0;
    record(`32 mg back to the cycle's film @${width}px`, await page.evaluate(probe), errs);
    await ctx.close();
  }

  /* 5a. The calendar on a linear run: a much shorter ladder, so fewer cells,
         and every one of them carries the same cut. */
  for (const width of [280, 414, 1024]) {
    const { ctx, page, errs } = await openPage(width, "dark");
    await setField(page, "cutMode", "linear");
    await setField(page, "targetMg", 0);
    await setField(page, "startDate", "2026-08-01");
    await page.waitForTimeout(220);
    errs.length = 0;
    record(`linear calendar @${width}px`, await page.evaluate(probe), errs);
    await ctx.close();
  }

  /* 5. The calendar on a two-strip run: every cell carries a ×N beside the
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
      for (const mode of ["save", "take", "delta"]) {
        if (mode !== "save") {
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

  /* 6. Rendered figures that no other suite can see. test_parity.js compares
        the schedule, not the display maths layered on top of it, and these had
        each gone wrong quietly: the cutting-error chart ignored the film-length
        input entirely, and the compare heading named a target it did not use. */
  {
    const { ctx, page, errs } = await openPage(1280, "dark");
    const readErr = () => page.evaluate(() => {
      const m = document.getElementById("charts").textContent
        .replace(/\s+/g, " ").match(/slip is ±([\d.]+) mg/);
      return m ? parseFloat(m[1]) : null;
    });

    await setField(page, "filmMm", 22);
    await page.waitForTimeout(160);
    const at22 = await readErr();
    await setField(page, "filmMm", 11);
    await page.waitForTimeout(160);
    const at11 = await readErr();
    checks++;
    if (at22 == null || at11 == null) {
      failures.push("cutting-error chart: could not read the slip figure");
    } else if (Math.abs(at11 - at22 * 2) > 1e-6) {
      failures.push(
        `cutting-error chart ignores film length: ${at22} mg at 22 mm, ${at11} mg at 11 mm `
        + `(expected ${at22 * 2})`
      );
    }
    await setField(page, "filmMm", 22);

    /* The compare table is built from the live target, so its heading must be. */
    for (const target of [1, 0.5]) {
      await setField(page, "targetMg", target);
      await page.waitForTimeout(160);
      const head = await page.evaluate(() => document.getElementById("compareHead").textContent);
      checks++;
      if (!head.includes(String(target))) {
        failures.push(`compare heading "${head}" does not name the ${target} mg target`);
      }
    }

    /* The linear mode's defining property, read off the rendered schedule: the
       Δ save column — how much further in the mark moves each cycle — must not
       change from the first cycle to the last. This is the thing a reader is
       asked to trust, and no other suite looks at the rendered table. */
    await setField(page, "cutMode", "linear");
    await setField(page, "targetMg", 0);
    await page.waitForTimeout(200);
    const cuts = await page.evaluate(() => [...document.querySelectorAll("#schedTable tbody tr")]
      .map((tr) => tr.children[7].textContent.trim()));
    checks++;
    if (cuts.length < 3) {
      failures.push(`linear schedule has only ${cuts.length} rows`);
    } else if (new Set(cuts).size !== 1) {
      failures.push(`linear cut column is not constant: ${[...new Set(cuts)].join(", ")}`);
    }
    /* And the geometric default must still shrink, or the modes are the same. */
    await setField(page, "cutMode", "geometric");
    await setField(page, "targetMg", 1);
    await page.waitForTimeout(200);
    const geoCuts = await page.evaluate(() => [...document.querySelectorAll("#schedTable tbody tr")]
      .map((tr) => tr.children[7].textContent.trim()));
    checks++;
    if (new Set(geoCuts).size < 3) {
      failures.push("geometric Δ save column stopped shrinking");
    }

    /* The claim the tinted block is built on: every cycle puts more film in
       the jar than the last. Read off the rendered Save mm column, because
       that is the number the reader is being asked to believe. It resets at a
       2 mg restart, which is exactly where Δ save shows a dash, so the run is
       only monotonic between dashes. */
    const saves = await page.evaluate(() => [...document.querySelectorAll("#schedTable tbody tr")]
      .map((tr) => ({
        save: parseFloat(tr.children[6].textContent),
        delta: tr.children[7].textContent.trim(),
      })));
    checks++;
    if (saves.length < 5) {
      failures.push(`geometric schedule has only ${saves.length} rows to check the save against`);
    }
    for (let i = 1; i < saves.length; i++) {
      if (saves[i].delta === "—") continue;
      if (!(saves[i].save > saves[i - 1].save)) {
        failures.push(`Save mm did not grow at cycle ${i + 1}: `
          + `${saves[i - 1].save} then ${saves[i].save}, with Δ save ${saves[i].delta}`);
      }
      /* Both sides are read off the page already rounded to 2 dp, so the
         difference of two of them can be a hundredth out from the exact delta.
         0.02 catches a wrong column while tolerating that. */
      const want = saves[i].save - saves[i - 1].save;
      if (Math.abs(want - parseFloat(saves[i].delta)) > 0.02) {
        failures.push(`Δ save at cycle ${i + 1} is ${saves[i].delta}, `
          + `but Save mm grew by ${want.toFixed(2)}`);
      }
    }

    /* role="img" hides the axis text from assistive tech, so each chart has to
       carry a name of its own or it announces as bare "image". */
    const unnamed = await page.evaluate(() => [...document.querySelectorAll("#charts svg[role=img]")]
      .filter((s) => !s.getAttribute("aria-label")).length);
    checks++;
    if (unnamed) failures.push(`${unnamed} chart(s) have role="img" with no accessible name`);

    errs.length = 0;
    record("rendered figures @1280px", await page.evaluate(probe), errs);
    await ctx.close();
  }

  /* 7. The schedule header tooltips. Mouse-and-keyboard only by design, so the
        sweep cannot see them — hover has to be driven explicitly. Three things
        matter: they appear on a desktop pointer, they stay inside the viewport
        (they are position:fixed precisely because the table's scroll container
        would clip anything else), and they never appear on a touch device. */
  {
    for (const width of [640, 1280]) {
      const { ctx, page, errs } = await openPage(width, "dark");
      const cols = await page.evaluate(() =>
        document.querySelectorAll("#schedTable thead th[data-tip]").length);
      checks++;
      if (cols !== 12) failures.push(`schedule has ${cols} documented headers, expected 12`);

      /* Units live in their own span so they can be small and muted, and the
         name and the unit need a real space between them — a CSS margin looks
         right and still reads as "Cut frommg" to a screen reader. */
      const units = await page.evaluate(() =>
        [...document.querySelectorAll("#schedTable thead th")].map((th) => {
          const u = th.querySelector(".u");
          return { name: th.firstChild.textContent, unit: u ? u.textContent : "", text: th.textContent };
        }));
      checks++;
      const withUnits = units.filter((u) => u.unit).length;
      if (withUnits !== 9) failures.push(`${withUnits} headers carry a unit, expected 9`);
      for (const u of units) {
        if (u.unit && !/ $/.test(u.name)) {
          failures.push(`header "${u.text}" runs its unit into the name`);
        }
      }

      /* The block the reader acts on — take, save, and how much more the jar
         gets than last cycle — is tinted. The tint is an inset shadow, not a
         background, because the row states set td backgrounds and would paint
         straight over it; check it survives on a 2 mg switch row, which is
         where that would show up. It also has to be one contiguous run: five
         tinted columns scattered through the row would not read as "this part
         is the job". */
      const keyCols = await page.evaluate(() => {
        const head = [...document.querySelectorAll("#schedTable thead th")];
        const rows = [...document.querySelectorAll("#schedTable tbody tr")];
        const idx = head.map((th, i) => th.classList.contains("key") ? i : -1).filter((i) => i >= 0);
        const perRow = rows.map((tr) => [...tr.children].map((td, i) => td.classList.contains("key") ? i : -1).filter((i) => i >= 0));
        const sw = document.querySelector("#schedTable tbody tr.switch td.key");
        return {
          idx,
          names: idx.map((i) => head[i].firstChild.textContent.trim()),
          consistent: perRow.every((r) => r.join() === idx.join()),
          tintedOnSwitchRow: sw ? getComputedStyle(sw).boxShadow !== "none" : null,
        };
      });
      checks++;
      const wantKeys = "Take/Take/Save/Save/Δ save";
      if (keyCols.names.join("/") !== wantKeys) {
        failures.push(`tinted columns are ${keyCols.names.join("/") || "none"}, expected ${wantKeys}`);
      }
      if (!keyCols.consistent) failures.push("tinted columns differ between header and body");
      const contiguous = keyCols.idx.every((v, i) => i === 0 || v === keyCols.idx[i - 1] + 1);
      if (!contiguous) failures.push(`tinted columns are not contiguous: ${keyCols.idx.join(",")}`);
      if (keyCols.tintedOnSwitchRow === false) {
        failures.push("the tint disappears on a 2 mg switch row");
      }

      /* Every value carries its unit too, in the same small muted span as the
         heading, so a row reads on its own without a trip back up the table.
         Checked as "every numeric cell", not a fixed list, because the failure
         this catches is a column added later without one. */
      const cellUnits = await page.evaluate(() => {
        const bad = [];
        const rows = [...document.querySelectorAll("#schedTable tbody tr")];
        for (const tr of rows) {
          [...tr.children].forEach((td, i) => {
            const txt = td.textContent.trim();
            /* Cycle, Days and the em-dash in Δ save are the cells with no unit
               to carry: an index, a day range, and "not applicable". */
            if (i <= 1 || txt === "—") return;
            if (!td.querySelector(".u")) bad.push(`col ${i} "${txt}"`);
          });
        }
        return bad.slice(0, 5);
      });
      checks++;
      if (cellUnits.length) {
        failures.push(`schedule values with no unit: ${cellUnits.join(", ")}`);
      }

      /* And the units must be visibly secondary, or they compete with the
         number they qualify — which is the whole reason they are a span. */
      const unitStyle = await page.evaluate(() => {
        const u = document.querySelector("#schedTable tbody td .u");
        if (!u) return null;
        const cu = getComputedStyle(u);
        const cd = getComputedStyle(u.parentElement);
        return {
          smaller: parseFloat(cu.fontSize) < parseFloat(cd.fontSize),
          dimmer: cu.color !== cd.color,
        };
      });
      checks++;
      if (!unitStyle) failures.push("no unit spans in the schedule body");
      else if (!unitStyle.smaller) failures.push("cell units are not smaller than their value");
      else if (!unitStyle.dimmer) failures.push("cell units are not muted against their value");

      /* Bounded by what is actually there: a missing column should be reported
         by the count check above, not crash the run in page.hover(). */
      for (const nth of [1, 8, 12].filter((i) => i <= cols)) {
        await page.hover(`#schedTable thead th:nth-child(${nth})`);
        await page.waitForTimeout(80);
        const r = await page.evaluate(() => {
          const t = document.querySelector(".tip");
          if (!t || getComputedStyle(t).display === "none") return null;
          const b = t.getBoundingClientRect();
          return {
            text: t.textContent.trim(),
            inside: b.left >= 0 && b.top >= 0
              && b.right <= window.innerWidth + 1 && b.bottom <= window.innerHeight + 1,
          };
        });
        checks++;
        if (!r) failures.push(`header ${nth} @${width}px: no tooltip on hover`);
        else if (!r.text) failures.push(`header ${nth} @${width}px: empty tooltip`);
        else if (!r.inside) failures.push(`header ${nth} @${width}px: tooltip escapes the viewport`);
        errs.length = 0;
        record(`tooltip on header ${nth} @${width}px`, await page.evaluate(probe), errs);
      }
      await ctx.close();
    }

    /* And a real touch context: a tap must not leave a tooltip stranded with no
       hover-out to dismiss it. The glossary is what touch readers get instead. */
    const ctx = await browser.newContext({
      viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true,
    });
    const page = await ctx.newPage();
    await page.goto(PAGE);
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForFunction(() => !!window.SASTaperInternals, null, { timeout: 10000 });
    /* A real tap first, then the synthetic event the guard is actually written
       against. The tap alone is timing-dependent — pointerleave can arrive and
       hide the tooltip again, so a broken guard could still look clean — while
       a bare pointerover with pointerType "touch" is exactly the case the code
       branches on and has no follow-up event to rescue it. */
    await page.tap("#schedTable thead th:nth-child(2)").catch(() => {});
    await page.waitForTimeout(120);
    let shown = await page.evaluate(() => {
      const t = document.querySelector(".tip");
      return !!t && getComputedStyle(t).display !== "none";
    });
    checks++;
    if (shown) failures.push("tooltip appeared on a touch tap");

    shown = await page.evaluate(() => {
      const th = document.querySelector("#schedTable thead th[data-tip]");
      th.dispatchEvent(new PointerEvent("pointerover", { bubbles: true, pointerType: "touch" }));
      const t = document.querySelector(".tip");
      return !!t && getComputedStyle(t).display !== "none";
    });
    checks++;
    if (shown) failures.push("tooltip appeared for a touch pointer");
    const defs = await page.evaluate(() => document.querySelectorAll("#colDoc div").length);
    checks++;
    if (defs !== 12) failures.push(`touch glossary has ${defs} entries, expected 12`);
    await ctx.close();
  }

  await browser.close();

  if (failures.length) {
    console.error(`FAILED — ${failures.length} layout problem(s) across ${checks} checks `
      + `over ${states} viewport states:`);
    const seen = new Set();
    for (const f of failures) {
      if (seen.has(f)) continue;
      seen.add(f);
      if (seen.size > 40) { console.error(`  … and ${failures.length - 40} more`); break; }
      console.error("  " + f);
    }
    process.exit(1);
  }
  console.log(
    `OK — no overflow, overlap, clipping, spill or bar-count mismatch across `
    + `${states} viewport states (${checks} checks in all)`
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
