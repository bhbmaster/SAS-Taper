#!/usr/bin/env node
/* Layout checks for SAS-Taper. Run: node test_layout.js
 *
 * index.html has to stay readable from a 280px phone to a 1920px desktop, in
 * both themes, and several of its parts are positioned from measured pixels
 * rather than by normal flow, the ruler tick captions, the life-size cut
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

const { launchOrSkip, PAGE, FOLD_PAGE } = require("./test_browser");

/* Phone through desktop, with the known breakpoints (360, 420, 640, 820) and
   both sides of each. 280 is a Galaxy Fold cover screen, the narrowest thing
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

  /* Each drawing shows one bar per film it is describing, always, for every
     cycle of every run. The count changing between cycles of the same ladder
     means the reader is looking at a picture that is not the day in front of
     them.

     The two panels answer different questions, so they are checked separately.
     The cut-mark panel is the schedule's own film strength, so its count is the
     row's filmsOut. The life-size panel redraws the same day on whichever
     strength is selected in the size table. A 12 mg film holds a day in fewer
     strips than an 8 mg one, so its count comes from re-running the layout at
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
      const lay = window.SASTaperInternals
        .filmLayout(row.cutFromMg, row.sliverMg, specMg, 22);
      const want = lay.filmsOut;
      /* Which drawing to expect comes from the control, not from what turned
         up: folding mode on a day that needs no cut draws neither an SVG nor
         bars. It says in words that every film is taken whole, and reading
         the mode off the output mistook that for measuring mode failing. */
      const btn = document.getElementById("vizModeFrac");
      const folding = !!btn && btn.getAttribute("aria-pressed") === "true";
      const life = document.querySelectorAll("#stripViz .strip-full").length;
      const svgs = document.querySelectorAll("#stripViz svg").length;
      if (folding) {
        if (life) out.bars.push(`folding mode drew ${life} measuring bars as well as the fold`);
        const wantSvg = lay.cutTakeMm > 1e-9 ? 1 : 0;
        if (svgs !== wantSvg) {
          out.bars.push(`folding mode drew ${svgs} folded films on ${specMg} mg film, expected ${wantSvg}`);
        }
      } else {
        if (svgs) out.bars.push(`measuring mode drew ${svgs} folded films`);
        if (life !== want) {
          out.bars.push(`life-size panel drew ${life} bars for a ${want}-film day on ${specMg} mg film`);
        }
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
         is checked against them rather than against a fixed string, and the
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
        /* The sample cell has to be built the same way the real ones are,
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
            failures.push(`${theme} ${width}px legend: the ${name} swatch is invisible, `
              + `a colour token missing from this theme?`);
          }
        }
      }
      await ctx.close();
    }
  }

  /* 3. Inputs that reshape the page: doses needing more than one film a day, a
        target that yields no ladder, the longest run the cap allows. The
        multi-film cases each name the cycles worth looking at, a two-strip run
        grows a kit banner, a ×N pill and, at the cycle where the ladder crosses
        a whole-film boundary, a second film bar and its caption. */
  for (const [label, fields, cycles] of [
    ["oversize start dose", { startMg: 64, stripMg: 8 }, [1, 5]],
    ["two-strip start", { startMg: 16, stripMg: 8 }, [1, 2, 4, 5, 12]],
    ["two-strip on 12 mg film", { startMg: 20, filmStrengthMg: 12 }, [1, 3]],
    ["four-strip start", { startMg: 30, stripMg: 8, n: 3 }, [1, 2]],
    ["sliver over one film", { startMg: 40, n: 2, targetMg: 8 }, [1, 2]],
    /* Every official strength at the top of the dose range. On 2 mg film a
       32 mg day is sixteen bars stacked in both drawings, the widest the
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
        takes. A 32 mg day is 4 x 8 mg bars but only 3 x 12 mg ones. The
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

  /* 4b. The folding mode of the life-size panel. A different drawing entirely.
         An SVG plan view rather than flex bars, so it needs its own sweep,
         across the cycles where the chosen grid is coarsest and finest, both
         themes, and the widths where the facts line has to wrap. */
  for (const width of [320, 414, 768, 1440]) {
    for (const theme of ["dark", "light"]) {
      const { ctx, page, errs } = await openPage(width, theme);
      /* Folding is the default, so the sweep above already covers it, but
         that means measuring is now the mode nothing else exercises. Both are
         driven here so neither drawing can rot behind the other. */
      for (const mode of ["fold", "exact"]) {
      await page.click(mode === "fold" ? "#vizModeFrac" : "#vizModeExact");
      await page.waitForTimeout(150);
      for (const cycle of [1, 2, 5, 7, 9]) {
        await page.evaluate((c) => {
          const tr = document.querySelector(`#schedTable tbody tr[data-cycle="${c}"]`);
          if (tr) tr.click();
        }, cycle);
        await page.waitForTimeout(120);
        errs.length = 0;
        record(`${mode} mode c${cycle} ${theme} @${width}px`, await page.evaluate(probe), errs);
      }
      if (mode === "exact") {
        /* Measuring must still draw flex bars and no SVG. */
        const ok = await page.evaluate(() =>
          !!document.querySelector("#stripViz .strip-full")
          && !document.querySelector("#stripViz svg"));
        checks++;
        if (!ok) failures.push(`${theme} ${width}px: measuring mode drew the wrong thing`);
        continue;
      }

      /* The drawing has to be the fraction the caption claims, and the caption
         has to be the fraction the maths chose. One disagreeing with the other
         is the whole failure mode of a second implementation of the picture. */
      /* Read the claim off data attributes rather than the prose. Parsing the
         caption meant a wording change silently disarmed the check, which is
         exactly what happened the first time the copy was edited. The prose is
         still checked, but only for agreeing with the attributes. */
      const fold = await page.evaluate(() => {
        const wrap = document.querySelector("#stripViz .fold-wrap");
        const svg = wrap && wrap.querySelector("svg");
        if (!svg) return null;
        const text = document.getElementById("stripViz").innerText;
        const [L, S] = wrap.dataset.fold.split("x").map(Number);
        const cells = Number(wrap.dataset.cells);
        const takes = [...svg.querySelectorAll('rect[fill^="url(#f"]')]
          .filter((r) => /t\)$/.test(r.getAttribute("fill")));
        const vb = svg.getAttribute("viewBox").split(" ").map(Number);
        const area = takes.reduce(
          (a, r) => a + Number(r.getAttribute("width")) * Number(r.getAttribute("height")), 0);
        return {
          grid: [L, S],
          drawn: area / ((vb[2] - 8) * (vb[3] - 8)),
          claimed: cells / (L * S),
          blades: svg.querySelectorAll(".fold-blade").length,
          cutsSaid: Number(wrap.dataset.cuts),
          gridLines: svg.querySelectorAll(".fold-grid").length,
          hasApprox: /This is an approximation/.test(text),
          /* The words have to carry the same numbers the attributes do. */
          textAgrees: text.includes(`${L} × ${S}`) && text.includes(`take ${cells} of ${L * S}`),
        };
      });
      checks++;
      if (!fold) {
        failures.push(`${theme} ${width}px: folding mode drew no film`);
      } else {
        if (fold.claimed === null || Math.abs(fold.drawn - fold.claimed) > 1e-6) {
          failures.push(`${theme} ${width}px fold: drawing is ${fold.drawn.toFixed(4)} `
            + `of the film but the caption says ${fold.claimed}`);
        }
        /* One fold line per subdivision, minus the film's own two edges. */
        const want = fold.grid ? (fold.grid[0] - 1) + (fold.grid[1] - 1) : -1;
        if (fold.gridLines !== want) {
          failures.push(`${theme} ${width}px fold: ${fold.gridLines} fold lines drawn for a `
            + `${fold.grid && fold.grid.join("×")} grid, expected ${want}`);
        }
        if (!fold.textAgrees) {
          failures.push(`${theme} ${width}px fold: the caption does not state the `
            + `${fold.grid.join("×")} grid the drawing used`);
        }
        if (String(fold.blades) !== String(fold.cutsSaid)) {
          failures.push(`${theme} ${width}px fold: ${fold.blades} blade lines drawn but the `
            + `caption says ${fold.cutsSaid} cuts`);
        }
        /* An approximation the reader cannot see the size of is worse than
           none, so the disclaimer is not optional. */
        if (!fold.hasApprox) {
          failures.push(`${theme} ${width}px fold: no "this is an approximation" note`);
        }
      }

      }
      await ctx.close();
    }
  }

  /* The default mode itself: a reader who has never touched the buttons must
     land on folding, and a reader who chose measuring must stay there across a
     reload. Only the non-default value is acted on at load, which is what lets
     the default move without dragging people who made a choice. */
  {
    const { ctx, page, errs } = await openPage(1024, "dark");
    const fresh = await page.evaluate(() => ({
      pressed: document.getElementById("vizModeFrac").getAttribute("aria-pressed"),
      drewFold: !!document.querySelector("#stripViz svg"),
    }));
    checks++;
    if (fresh.pressed !== "true" || !fresh.drewFold) {
      failures.push(`a fresh visit did not default to folding (${JSON.stringify(fresh)})`);
    }
    await page.click("#vizModeExact");
    await page.waitForTimeout(120);
    await page.reload();
    await page.waitForFunction(() => !!window.SASTaperInternals, null, { timeout: 10000 });
    await page.waitForTimeout(200);
    const kept = await page.evaluate(() => ({
      pressed: document.getElementById("vizModeExact").getAttribute("aria-pressed"),
      drewBars: !!document.querySelector("#stripViz .strip-full"),
      drewFold: !!document.querySelector("#stripViz svg"),
    }));
    checks++;
    if (kept.pressed !== "true" || !kept.drewBars || kept.drewFold) {
      failures.push(`measuring did not survive a reload (${JSON.stringify(kept)})`);
    }
    /* No probe() here: a reload drops the globals openPage injects, and this
       block is asserting persistence rather than geometry, the sweeps above
       already measured both modes at eight width/theme combinations. */
    checks++;
    if (errs.length) failures.push(`mode persistence: ${errs.join("; ")}`);
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
       Δ save column, how much further in the mark moves each cycle, must not
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
      if (saves[i].delta === "-") continue;
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
        sweep cannot see them, hover has to be driven explicitly. Three things
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
         name and the unit need a real space between them. A CSS margin looks
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

      /* The block the reader acts on, take, save, and how much more the jar
         gets than last cycle, is tinted. The tint is an inset shadow, not a
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
            if (i <= 1 || txt === "-") return;
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
         number they qualify, which is the whole reason they are a span. */
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
       against. The tap alone is timing-dependent, pointerleave can arrive and
       hide the tooltip again, so a broken guard could still look clean, while
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

  /* 9. fold.html, the algorithm explainer. A second shipped page with its own
        stylesheet, so the same failure modes apply. It is also live: every
        diagram redraws from a slider, so the sweep drives that too, and it has
        to stay self-contained like index.html does. */
  {
    const SRC = require("fs").readFileSync(require("path").join(__dirname, "fold.html"), "utf8");
    checks++;
    /* People open this from disk, offline. A CDN link would break that
       silently. It just renders in the wrong font on a machine with no
       network, and nobody notices until someone is holding a razor. */
    const remote = SRC.match(/(?:src|href)\s*=\s*["']https?:\/\/[^"']+/gi) || [];
    const offsite = remote.filter((m) => !/github\.com/.test(m));
    if (offsite.length) {
      failures.push(`fold.html loads something off-site: ${offsite.join(", ")}`);
    }

    /* The glossary is the names the listing uses, and it has to agree with the
       listing in BOTH directions. It drifted one way once already, cells /
       err / cap in the table against parts_taken / error_mg / worst_allowed in
       the block, and a reader who learns one set then meets the other is
       being taught two languages for one function. Checking only glossary →
       listing leaves the other way open: a name the search introduces and
       nobody documents (parts_in_all was exactly that) is just as confusing.
       Names are matched on word boundaries, so a row for `err` cannot be
       satisfied by the `error_mg` that replaced it. */
    checks++;
    {
      const glossBlock = SRC.match(/<table class="gloss">[\s\S]*?<\/table>/);
      const from = SRC.indexOf("<pre class=\"whole\">");
      const listingHtml = from < 0 ? "" : SRC.slice(from, SRC.indexOf("</pre>", from));
      /* Strip the syntax-highlight spans and unescape, so the checks below see
         the code a reader sees rather than the markup around it. */
      const listing = listingHtml.replace(/<[^>]+>/g, "")
        .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
      /* The drawing section is a sketch of the render, not part of the search,
         and its screen-space names (column_width, film_height) are deliberately
         outside the glossary. Everything above it has to be named. */
      const search = listing.split("# \u2500\u2500 Draw it")[0];
      const word = (n) => new RegExp(`\\b${n}\\b`);

      if (!glossBlock) {
        failures.push("fold.html has no names glossary");
      } else if (!listing) {
        failures.push("fold.html has no whole-algorithm listing to check the glossary against");
      } else {
        const names = [...glossBlock[0].matchAll(/<tr><td class="f">([a-z_]+)<\/td>/g)].map((m) => m[1]);
        const missing = names.filter((n) => !word(n).test(listing));
        if (missing.length) {
          failures.push(`fold.html glossary names missing from the listing: ${missing.join(", ")}`);
        }
        /* The other direction: every name the search binds, parameters, loop
           variables, assignments, divmod targets, must have a glossary row. */
        const bound = new Set();
        const add = (t) => t.split(",").forEach((n) => {
          const m = n.trim().match(/^([a-z][a-z0-9_]*)$/);
          if (m) bound.add(m[1]);
        });
        const def = search.match(/def fraction_cut\(([^)]*)\)/);
        if (!def) failures.push("fold.html listing no longer defines fraction_cut");
        else add(def[1]);
        for (const line of search.split("\n")) {
          let m = line.match(/^\s*for\s+([a-z0-9_,\s]+?)\s+in\s/);
          if (m) add(m[1]);
          m = line.match(/^\s*([a-z][a-z0-9_,\s]*?)\s*(?:\+)?=[^=]/);
          if (m) add(m[1]);
        }
        const undocumented = [...bound].filter((n) => !names.includes(n));
        if (undocumented.length) {
          failures.push(`fold.html listing uses names the glossary never defines: ${undocumented.sort().join(", ")}`);
        }
        checks++;
        if (!bound.has("parts_in_all") || !bound.has("parts_taken")) {
          failures.push("fold.html glossary sweep stopped seeing the names it was written for "
            + `(found ${[...bound].sort().join(", ")})`);
        }
      }
    }

    /* Phone through desktop. The listing scrolls at all of them. The default
       does not depend on the viewport any more, so every width is the same
       assertion, and a width-dependent default reappearing would break it. */
    const FOLD_WIDTHS = [320, 414, 768, 1280];

    for (const width of FOLD_WIDTHS) {
      for (const theme of ["dark", "light"]) {
        const ctx = await browser.newContext({
          viewport: { width, height: 900 }, colorScheme: theme,
        });
        const page = await ctx.newPage();
        const errs = [];
        page.on("pageerror", (e) => errs.push("page error: " + e));
        page.on("console", (m) => { if (m.type() === "error") errs.push("console error: " + m.text()); });
        await page.goto(FOLD_PAGE);
        await page.waitForTimeout(250);
        await page.evaluate(([g, c, s2]) => {
          window.__groups = g; window.__clip = c; window.__spill = s2;
          window.__selectedRow = () => null;
        }, [OVERLAP_GROUPS, CLIP_SELECTORS, SPILL_PAIRS]);

        /* The listing is hard-wrapped 80-column text with its comments in an
           aligned second column, so it is read as a strip of code and scrolls
           sideways inside its own <pre> at every width. Soft-wrapping it costs
           more than it saves: on a phone two lines in three re-wrap and every
           continuation lands back at column 0. Wrap is therefore the opt-in,
           not the default, and both buttons have to actually flip the
           listing. The scroller lives inside the <pre>; what must never
           happen is the page itself widening behind it. */
        const readListing = () => page.evaluate(() => {
          const blocks = [...document.querySelectorAll("pre")].map((p) => {
            const cs = getComputedStyle(p);
            return {
              whole: p.classList.contains("whole"),
              whiteSpace: cs.whiteSpace,
              overflowX: p.scrollWidth - p.clientWidth,
            };
          });
          const on = document.getElementById("codeWrapOn");
          const off = document.getElementById("codeWrapOff");
          return {
            blocks,
            whole: blocks.find((b) => b.whole) || null,
            wrapAttr: document.documentElement.getAttribute("data-code-wrap"),
            wrapPressed: on && on.getAttribute("aria-pressed"),
            scrollPressed: off && off.getAttribute("aria-pressed"),
            wrapLabel: on && on.textContent.trim(),
            scrollLabel: off && off.textContent.trim(),
            hasPair: !!(on && off),
          };
        });
        const listing = await readListing();
        checks++;
        if (!listing.hasPair) {
          failures.push("fold.html has no Wrap/Scroll controls on the listing");
        } else if (!/Wrap/.test(listing.wrapLabel) || listing.scrollLabel !== "Scroll") {
          failures.push(`fold.html listing controls read "${listing.wrapLabel}" / "${listing.scrollLabel}", expected Wrap / Scroll`);
        }
        if (!listing.whole) {
          failures.push("fold.html has no whole-algorithm code block");
        } else {
          checks++;
          if (listing.wrapPressed !== "false" || listing.scrollPressed !== "true"
              || listing.wrapAttr !== null) {
            failures.push(`fold.html listing default at ${width}px is wrap=${listing.wrapPressed} `
              + `scroll=${listing.scrollPressed} attr=${listing.wrapAttr}, expected Scroll and no attribute`);
          }
          checks++;
          if (/wrap/.test(listing.whole.whiteSpace)) {
            failures.push(`fold.html code listing wraps by default at ${width}px `
              + `(white-space: ${listing.whole.whiteSpace}); wrapping is the opt-in`);
          }
          /* The scroller is the point of the default, so at a phone width the
             listing has to actually have one. A listing that fits is a
             listing something has re-wrapped. */
          if (width <= 414 && listing.whole.overflowX <= 1) {
            failures.push(`fold.html listing has no sideways scroller at ${width}px`);
          }

          await page.click("#codeWrapOn");
          const wrapped = await readListing();
          checks++;
          if (!/wrap/.test(wrapped.whole.whiteSpace) || wrapped.wrapPressed !== "true"
              || wrapped.wrapAttr !== "on") {
            failures.push(`fold.html Wrap at ${width}px did not turn wrapping on `
              + `(white-space: ${wrapped.whole.whiteSpace}, pressed=${wrapped.wrapPressed})`);
          }
          const sideways = wrapped.blocks.filter((b) => b.overflowX > 1);
          if (sideways.length) {
            failures.push(`fold.html <pre> still scrolls sideways with Wrap on at ${width}px `
              + `(${sideways.map((b) => (b.whole ? "whole " : "") + b.overflowX + "px").join(", ")})`);
          }

          await page.click("#codeWrapOff");
          const unwrapped = await readListing();
          checks++;
          if (/wrap/.test(unwrapped.whole.whiteSpace) || unwrapped.scrollPressed !== "true"
              || unwrapped.wrapAttr !== null) {
            failures.push(`fold.html Scroll at ${width}px did not turn wrapping off `
              + `(white-space: ${unwrapped.whole.whiteSpace}, pressed=${unwrapped.scrollPressed})`);
          }
          if (unwrapped.whole.overflowX <= 1 && width <= 414) {
            failures.push(`fold.html Scroll at ${width}px left no sideways scroller on the listing`);
          }
          /* The scroller has to stay inside the listing. If the <pre> widens
             the page instead, the reader drags the whole article sideways,
             and the page-level overflow check above cannot see it, because it
             runs before either button is touched. */
          const after = await page.evaluate(probe);
          checks++;
          if (after.scrollX > 0) {
            failures.push(`fold.html page scrolls horizontally by ${after.scrollX}px `
              + `with the listing scrolling at ${width}px`);
          }
        }

        /* Every preset, so each stage is measured against a real cycle rather
           than only the one it loads with. */
        const presets = await page.evaluate(() =>
          document.querySelectorAll("#presets button").length);
        checks++;
        if (presets < 4) failures.push(`fold.html has ${presets} preset cycles, expected 6`);
        for (let i = 0; i < presets; i++) {
          await page.evaluate((n) => document.querySelectorAll("#presets button")[n].click(), i);
          await page.waitForTimeout(60);
          errs.length = 0;
          record(`fold.html preset ${i} ${theme} @${width}px`, await page.evaluate(probe), errs);
        }

        /* The fold comparison. Stage 02's ladder is a control: 54 ticks, a
           <select> carrying the same 54 as the keyboard path, and the two
           always naming the same fraction. Clicking a tick has to move the
           list, and choosing from the list has to move the highlight. */
        const cmp = await page.evaluate(() => {
          const read = () => ({
            on: [...document.querySelectorAll("#f2 .tick.on")].length,
            sel: document.getElementById("cmpPick").value,
            head: document.getElementById("cmpHb").textContent,
            verdict: document.getElementById("cmpVerdict").textContent,
          });
          const out = { ticks: document.querySelectorAll("#f2 .tick").length,
                        hits: document.querySelectorAll("#f2 .tick-hit").length,
                        opts: document.querySelectorAll("#cmpPick option").length,
                        films: document.querySelectorAll("#cmpFilms svg").length,
                        start: read() };
          const hits = document.querySelectorAll("#f2 .tick-hit");
          hits[3].dispatchEvent(new MouseEvent("click", { bubbles: true }));
          out.clicked = read();
          const sel = document.getElementById("cmpPick");
          sel.value = "50";
          sel.dispatchEvent(new Event("change", { bubbles: true }));
          out.chose = read();
          /* Moving the dose has to drop the comparison. A fold held over from
             the previous dose is answering a question nobody asked. */
          const drv = document.getElementById("drv");
          drv.value = "0.5";
          drv.dispatchEvent(new Event("input", { bubbles: true }));
          out.afterMove = read();
          out.closestSaid = document.getElementById("d2").textContent;
          return out;
        });
        checks++;
        if (cmp.ticks !== 54 || cmp.hits !== 54 || cmp.opts !== 54) {
          failures.push(`fold.html ladder at ${width}px has ${cmp.ticks} ticks, ${cmp.hits} `
            + `click targets and ${cmp.opts} list entries; all three should be 54`);
        }
        checks++;
        if (cmp.films !== 2) {
          failures.push(`fold.html comparison drew ${cmp.films} films, expected 2`);
        }
        checks++;
        if (cmp.start.on !== 1 || cmp.clicked.on !== 1 || cmp.chose.on !== 1) {
          failures.push(`fold.html ladder highlights ${cmp.start.on}/${cmp.clicked.on}/`
            + `${cmp.chose.on} ticks at ${width}px, expected exactly 1 throughout`);
        }
        checks++;
        if (cmp.clicked.sel !== "3" || cmp.clicked.head === cmp.start.head) {
          failures.push(`fold.html: clicking a tick at ${width}px left the list on `
            + `"${cmp.clicked.sel}" and the comparison on ${cmp.clicked.head}`);
        }
        checks++;
        if (cmp.chose.sel !== "50" || cmp.chose.head === cmp.clicked.head) {
          failures.push(`fold.html: choosing from the list at ${width}px did not move the `
            + `comparison (${cmp.clicked.head} → ${cmp.chose.head})`);
        }
        checks++;
        if (!/fold the search chose|closer|easier|Further off|as far off/.test(cmp.afterMove.verdict)) {
          failures.push(`fold.html comparison verdict went blank after the dose moved `
            + `at ${width}px: "${cmp.afterMove.verdict}"`);
        }
        /* Which fraction the panel falls back to is checked in the dose sweep
           below rather than here. At any one dose the chosen fold is very
           often also the closest one, and where those coincide the check
           cannot tell the two apart, a fallback wired to the wrong one of
           them passes. The sweep visits doses where they differ, and counts
           how many, so it cannot quietly stop covering them. */

        /* The diagrams must actually be there and actually move. */
        const live = await page.evaluate(() => {
          const before = document.getElementById("f7").innerHTML;
          const slider = document.getElementById("drv");
          slider.value = String(Math.min(1, parseFloat(slider.value) + 0.2));
          slider.dispatchEvent(new Event("input", { bubbles: true }));
          return {
            svgs: document.querySelectorAll(".fig svg").length,
            rows: document.querySelectorAll("#f5 tr").length,
            changed: document.getElementById("f7").innerHTML !== before,
          };
        });
        checks++;
        if (live.svgs < 6) failures.push(`fold.html drew ${live.svgs} diagrams, expected at least 6`);
        if (!live.rows) failures.push("fold.html ranked no candidates");
        if (!live.changed) failures.push("fold.html did not redraw when the slider moved");

        /* And the way back. A page that cannot return to the calculator is a
           dead end for anyone who arrives from a search result. */
        const links = await page.evaluate(() =>
          [...document.querySelectorAll("nav a")].map((a) => a.getAttribute("href")));
        checks++;
        if (!links.includes("index.html")) failures.push("fold.html has no link back to the calculator");
        if (!links.some((h) => /github\.com/.test(h))) failures.push("fold.html has no link to the source");

        errs.length = 0;
        record(`fold.html ${theme} @${width}px`, await page.evaluate(probe), errs);
        await ctx.close();
      }
    }

    /* Only the non-default value is stored, the same way index.html stores the
       film panel's mode. A chosen Wrap has to survive a reload, and choosing
       Scroll again has to clear the key rather than store "off", so that
       moving the default later does not leave old readers pinned to today's
       one. Whether the restore happens before first paint is checked
       statically below, by the time Playwright can evaluate anything, both
       scripts have run and the two are indistinguishable. */
    {
      const ctx = await browser.newContext({ viewport: { width: 320, height: 900 } });
      const page = await ctx.newPage();
      await page.goto(FOLD_PAGE);
      await page.waitForTimeout(250);
      const fresh = await page.evaluate(() => ({
        pressed: document.getElementById("codeWrapOff").getAttribute("aria-pressed"),
        wrap: getComputedStyle(document.querySelector("pre.whole")).whiteSpace,
        stored: localStorage.getItem("sas-taper-fold-wrap"),
      }));
      checks++;
      if (fresh.pressed !== "true" || /wrap/.test(fresh.wrap) || fresh.stored !== null) {
        failures.push(`a fresh phone visit did not default to Scroll with nothing stored (${JSON.stringify(fresh)})`);
      }
      await page.click("#codeWrapOn");
      await page.reload();
      await page.waitForTimeout(250);
      const kept = await page.evaluate(() => ({
        pressed: document.getElementById("codeWrapOn").getAttribute("aria-pressed"),
        wrap: getComputedStyle(document.querySelector("pre.whole")).whiteSpace,
        attr: document.documentElement.getAttribute("data-code-wrap"),
        stored: localStorage.getItem("sas-taper-fold-wrap"),
      }));
      checks++;
      if (kept.pressed !== "true" || !/wrap/.test(kept.wrap) || kept.attr !== "on" || kept.stored !== "on") {
        failures.push(`Wrap did not survive a reload (${JSON.stringify(kept)})`);
      }
      await page.click("#codeWrapOff");
      const cleared = await page.evaluate(() => localStorage.getItem("sas-taper-fold-wrap"));
      checks++;
      if (cleared !== null) {
        failures.push(`choosing Scroll stored "${cleared}" instead of clearing the key`);
      }
      await ctx.close();
    }

    /* Two invariants of the comparison panel, swept across the whole dose
       range once rather than at every viewport, neither depends on width.

       The first is the panel's own arithmetic: the difficulty table itemises
       where every point comes from, and those rows have to add up to the score
       printed underneath them. They are computed from one list in the page, so
       this fails the moment someone adds a term to the score and forgets to
       give it a row, or gives it a row and forgets the term.

       The second is a claim the page makes in prose and the search had better
       honour: the pool is sorted on difficulty before anything else, so no
       fold the search considered can be cheaper than the one it chose. The
       panel says outright that such a fold would be a bug. If it ever prints
       that, this fails. */
    {
      const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
      const page = await ctx.newPage();
      const errs = [];
      page.on("pageerror", (e) => errs.push("page error: " + e));
      await page.goto(FOLD_PAGE);
      await page.waitForTimeout(250);
      const swept = await page.evaluate(() => {
        const drv = document.getElementById("drv");
        const sel = document.getElementById("cmpPick");
        const bad = [], contradictions = [], fellWrong = [], disagreed = [];
        let doses = 0, sums = 0, differed = 0;
        const nearestSaid = () =>
          (document.getElementById("d2").textContent.match(/nearest is\s*(\d+\/\d+)/) || [])[1];
        for (let w = 0.04; w <= 1.0001; w += 0.004) {
          drv.value = w.toFixed(3);
          drv.dispatchEvent(new Event("input", { bubbles: true }));
          doses++;

          /* With nothing picked the panel compares against the closest
             fraction, which stage 02's facts line names independently. Where
             the chosen fold is not itself the closest, those are two different
             fractions and a fallback wired to the wrong one shows up here. */
          const nearest = nearestSaid();
          const chosenF = document.getElementById("cmpHa").textContent;
          const shownF = document.getElementById("cmpHb").textContent;
          if (nearest && shownF !== nearest) {
            fellWrong.push(`at ${w.toFixed(3)}: comparing against ${shownF}, nearest is ${nearest}`);
          }
          if (nearest && chosenF !== nearest) differed++;

          /* EASIEST and the search have to agree about which fold reaches a
             fraction most cheaply. Ask the list for the chosen fold's own
             fraction and both columns must draw the same grid; if the two
             orderings break a tie differently, they will not. */
          const opt = [...sel.options].find((o) => o.textContent.split(" ·")[0] === chosenF);
          if (!opt) {
            disagreed.push(`at ${w.toFixed(3)}: ${chosenF} is not on the list at all`);
          } else {
            sel.value = opt.value;
            sel.dispatchEvent(new Event("change", { bubbles: true }));
            const [x, y] = [...document.querySelectorAll("#cmpFilms svg")]
              .map((g) => g.getAttribute("aria-label"));
            if (x !== y) disagreed.push(`at ${w.toFixed(3)}: "${x}" vs "${y}"`);
            drv.dispatchEvent(new Event("input", { bubbles: true }));
          }
          const rows = [...document.querySelectorAll("#cmpTab tr")];
          const tot = rows.pop();
          for (const col of [1, 2]) {
            const parts = rows.reduce((n, t) => n + (parseInt(t.children[col].textContent, 10) || 0), 0);
            const said = parseInt(tot.children[col].textContent, 10);
            sums++;
            if (parts !== said) {
              bad.push(`at ${w.toFixed(3)} column ${col}: rows add to ${parts}, total says ${said}`);
            }
          }
          if (/is a bug/.test(document.getElementById("cmpVerdict").textContent)) {
            contradictions.push(w.toFixed(3));
          }
          /* And with a fold explicitly picked, not only the default one. */
          for (const i of [0, 17, 34, 53]) {
            sel.value = String(i);
            sel.dispatchEvent(new Event("change", { bubbles: true }));
            if (/is a bug/.test(document.getElementById("cmpVerdict").textContent)) {
              contradictions.push(`${w.toFixed(3)} vs option ${i}`);
            }
          }
        }
        return { bad, contradictions, fellWrong, disagreed, doses, sums, differed };
      });
      checks++;
      if (swept.bad.length) {
        failures.push(`fold.html difficulty rows do not add up to the difficulty `
          + `(${swept.bad.length} of ${swept.sums}): ${swept.bad[0]}`);
      }
      checks++;
      if (swept.contradictions.length) {
        failures.push(`fold.html found ${swept.contradictions.length} fold(s) the search `
          + `considered and could have had cheaper than the one it chose: `
          + `${swept.contradictions.slice(0, 3).join(", ")}`);
      }
      checks++;
      if (swept.fellWrong.length) {
        failures.push(`fold.html compares against the wrong fold with nothing picked `
          + `(${swept.fellWrong.length} of ${swept.doses} doses): ${swept.fellWrong[0]}`);
      }
      checks++;
      if (swept.disagreed.length) {
        failures.push(`fold.html draws a different grid for the chosen fraction than the `
          + `search chose (${swept.disagreed.length} of ${swept.doses}): ${swept.disagreed[0]}`);
      }
      checks++;
      if (swept.doses < 200 || swept.sums < 400) {
        failures.push(`fold.html comparison sweep only reached ${swept.doses} doses and `
          + `${swept.sums} score totals; it is no longer covering the dose range`);
      }
      /* The shape of the sweep's own coverage. The fallback check above is
         only meaningful at doses where the chosen fold is not also the closest
         one, everywhere else the two fractions coincide and any wiring
         passes. If that population dries up, the check has stopped testing
         anything and should fail rather than go on reporting green. */
      checks++;
      if (swept.differed < 100) {
        failures.push(`fold.html sweep found only ${swept.differed} doses where the chosen `
          + `fold is not the closest one; the fallback check needs those to mean anything`);
      }
      if (errs.length) failures.push(`fold.html comparison sweep: ${errs[0]}`);
      states += 1;
      await ctx.close();
    }

    /* The restore has to run in the <head>, during parse. Put it at the foot
       of the body with the rest of the script and a reader who chose Wrap
       watches the listing render as a strip and then re-flow, which no
       measurement taken after load can tell apart from the correct order, so
       this one is read off the file. The key is written twice, once in each
       script, and the two have to be the same string. */
    checks++;
    {
      const head = SRC.slice(0, SRC.indexOf("</head>"));
      const keys = [...SRC.matchAll(/"(sas-taper-fold-wrap)"/g)].length;
      if (!/data-code-wrap/.test(head)) {
        failures.push("fold.html no longer restores the code-wrap choice in the <head>; "
          + "a stored Wrap would be applied after first paint");
      }
      if (!head.includes("sas-taper-fold-wrap")) {
        failures.push("fold.html's head script no longer reads the code-wrap key");
      }
      if (keys < 2) {
        failures.push(`fold.html writes the code-wrap key ${keys} time(s); `
          + "the head script and the page script each need it, spelled the same");
      }
    }
  }

  await browser.close();

  if (failures.length) {
    console.error(`FAILED: ${failures.length} layout problem(s) across ${checks} checks `
      + `over ${states} viewport states:`);
    const seen = new Set();
    for (const f of failures) {
      if (seen.has(f)) continue;
      seen.add(f);
      if (seen.size > 40) { console.error(`  ... and ${failures.length - 40} more`); break; }
      console.error("  " + f);
    }
    process.exit(1);
  }
  console.log(
    `OK. No overflow, overlap, clipping, spill or bar-count mismatch across `
    + `${states} viewport states (${checks} checks in all).`
  );
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
