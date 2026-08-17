# SAS-Taper

**SAS** means **save-a-sliver**.

A geometric buprenorphine (Suboxone) film-taper calculator. **Not medical advice.** Bring the schedule to your prescriber before day 1.

Source: [github.com/bhbmaster/SAS-Taper](https://github.com/bhbmaster/SAS-Taper)  
Live site: [bhbmaster.github.io/SAS-Taper](https://bhbmaster.github.io/SAS-Taper/)

Each day you cut `1/n` off the current piece, **save** the short right sliver, and **take** the long left piece. After `n` days the save jar holds one full piece — a buffer, not extra daily dose. Next cycle the new “whole strip” is `dose × (1 − 1/n)`.

Default: start 8 mg, **n = 6** (16.7% every 6 days), switch to 2 mg films once the strip reaches 2.25 mg.

## Why save-a-sliver

The demanding part of a taper is often not the milligrams but the sense of getting less. SAS frames each day’s remaining piece as a complete strip — the dose you have — while the cut-off sliver leaves the daily routine.

People tend to work with what is in hand. Surplus that stays in view is easier to use; once the sliver is saved, it is no longer part of today’s dose. The bank is a safety net if you need to step back up, not a second supply for the same day.

## Site

The calculator lives at **[bhbmaster.github.io/SAS-Taper](https://bhbmaster.github.io/SAS-Taper/)**.

There is no build step and no server. `index.html` is one self-contained file — all the CSS and JavaScript are inline, nothing is fetched over the network — so opening it straight from disk in any browser gives you the identical calculator, working offline. Clone the repo, or just save that one file and double-click it.

Either way: measure your film **length only**, put that in the inputs, and the schedule / cut marks / graphs update live. Click a cycle for that day’s ruler (TAKE left, SAVE right). Print it for your prescriber.

## CLI

```bash
python3 taper.py
python3 taper.py --compare
python3 taper.py --cycle 6
python3 taper.py --n 10 --no-switch-2mg
python3 taper.py --start-date 2026-03-01
python3 test_taper.py          # math checks
```

No extra packages. Python 3.11 is fine. Same math as the site. Cut marks are a full unused film: TAKE left, SAVE, then the already-off remainder. `--cycle N` prints only that cycle’s cut with the extra note. `--stop-mode above` matches the classic n=6/8/10 comparison (last cycle still strictly above target). `--start-date` adds real dates to the schedule, the same ones the site's calendar shows.

## Tests

Three suites. The first needs nothing but Python; the other two need Node and a browser.

```bash
python3 test_taper.py       # schedule maths
node test_parity.js         # index.html vs taper.py
node test_layout.js         # viewport sweep, 280px to 1920px
```

### `test_taper.py`

23 checks over the arithmetic the schedule is built on — the closed forms against the simulation, the per-cycle invariants (dose splits exactly, length fraction equals dose fraction, the bank is one whole piece per cycle), that the daily dose never rises across a film switch, and the published film geometry. Standard library only.

### `test_parity.js` — what it tests and why

The taper maths is written **twice**: `buildSchedule()` in `index.html` and `build_schedule()` in `taper.py`. The site tells people the two agree, and `test_taper.py` only covers the Python one. This test checks the claim, because the two had already drifted once.

It loads `index.html` in a headless browser, runs both implementations over the same inputs, and diffs the results — **21 schedules** (start doses 0.1–12 mg, `n` from 3 to 30, the 2 mg switch on and off, stretched cycles, `n`-below-3, non-default film lengths, clamp boundaries, empty ladders), comparing all 19 fields of every cycle row plus 9 summary figures, then `baseFilmMg` across 8 film sizes.

It exits **0** on a match, **1** with a list of mismatches otherwise. If Node or a browser is missing it prints `skipped` and exits 0, so a plain checkout still passes.

#### Setup — Linux and macOS

`playwright-core` deliberately ships without a browser, so you need one. Easiest route, and what CI uses:

```bash
npm install                          # installs playwright-core from package.json
npx --yes playwright install chromium   # ~150 MB, downloads once
node test_parity.js
```

On Linux, if Chromium refuses to start over missing system libraries:

```bash
npx --yes playwright install --with-deps chromium   # needs sudo
```

**Already have Chrome?** Skip the download and point at it:

```bash
# macOS
CHROMIUM_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" node test_parity.js

# Linux
CHROMIUM_PATH=/usr/bin/google-chrome node test_parity.js
```

The script also finds a browser on its own in the usual places — the Playwright cache (`~/.cache/ms-playwright` on Linux, `~/Library/Caches/ms-playwright` on macOS) and installed Chrome or Chromium — so `CHROMIUM_PATH` is only needed for something in an unusual location.

### `test_layout.js` — what it tests and why

Several parts of the page are positioned from measured pixels rather than by normal flow: the ruler tick captions, the life-size cut label, the calendar grid. Those have broken four separate times — captions stacked on each other, a percentage painted over a button, "SAVE" sliced in half, the page scrolling sideways on a narrow phone. Each was found by sweeping viewports by hand, then lost again, because nothing re-ran the sweep.

This is that sweep, committed. It loads the page at **14 widths from 280px to 1920px**, in both themes, across several cycles, zoom levels, calendar densities and measurement modes, plus five reshaping input cases — **239 viewport states** — and checks four things at each:

| Failure | Detected by |
|---|---|
| **overflow** — the page scrolls sideways | `scrollWidth > clientWidth` on the document |
| **overlap** — two pieces of text drawn on top of each other | pairwise rectangle intersection within each positioned group |
| **clipping** — a box too small for its text | `scrollWidth`/`scrollHeight` vs `clientWidth`/`clientHeight` |
| **spill** — an absolute label escaping its container | bounding box against its parent's |

Any console or page error fails it too. Same setup as the parity test; same skip behaviour without a browser.

Via npm scripts:

```bash
npm test           # parity + layout
npm run test:all   # all three suites
```

All three run in GitHub Actions on every push and pull request.

## Method (every day of a cycle)

1. Start with the current “whole strip” (cycle 1: a full 8 mg film).
2. Keep full width; cut along length only. Mark, then cut with a razor, not scissors.
3. Cut `1/n` off the **right** end. Save that sliver. Take the long left piece. Once daily.
4. After `n` days the save jar holds one full piece. Do not use the bank as extra daily dose or the taper never drops.
5. Next cycle, the leftover size is the new whole strip. Repeat to the target (default 1 mg).

Hold a cycle if cravings spike, sleep goes, or you are restless and sweating. When the sliver is under ~1 mm, switch to 2 mg films. Lock up saved pieces (dangerous to kids and pets). Ask the prescriber to step quantity down with the dose.

## Limitation

The schedule starts from **one given film size** and then either stays on that strength or **switches only to 2 mg films**. It does not auto-step 12 → 8 → 4 mg. Clicking those rows on the site only changes the life-size drawing.

To plan a different start, change the inputs and recalc — for example start dose 12, start dose 4, or turn off the 2 mg switch to stay on 8 mg films the whole way. The base film is the smallest official strength that holds the start dose (2 / 4 / 8 / 12 mg), so day 1 is always one whole film; `--film-strength` overrides that if you are cutting something else.

All four Suboxone strengths measure 22 mm on the side this tool cuts, so the film-length input is the same number whichever you start on. The two low strengths (2 and 4 mg) share one density and the two high ones (8 and 12 mg) share another that is 4× as concentrated — which is why moving from 8 mg to 2 mg films makes the same dose four times longer, and the same cut four times more forgiving.

If a run stops at the 40-cycle cap before reaching the target, or the 2 mg switch cannot fire without raising the dose, both the site and the CLI say so instead of quietly returning a short ladder.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version: `index.html` stays one self-contained file, `taper.py` stays standard-library only, and if you touch the maths in one you touch it in both and run `node test_parity.js`.

## License

[MIT](LICENSE) © 2026 Kostia K.

The licence covers the code. It is not medical advice and carries no warranty — that is the "AS IS" clause doing real work here, not boilerplate. Take the schedule to a prescriber before day 1.

---

Strictly unofficially, the method can be called **SAS-Sub-minning** — the stat you are grinding down is Suboxone.

