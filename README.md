# SAS-Taper

**SAS** means **save-a-sliver**.

A geometric buprenorphine (Suboxone) film-taper calculator. **Not medical advice.** Bring the schedule to your prescriber before day 1.

Source: [github.com/bhbmaster/SAS-Taper](https://github.com/bhbmaster/SAS-Taper)  
Live site: [bhbmaster.github.io/SAS-Taper](https://bhbmaster.github.io/SAS-Taper/)

Each day you cut `1/n` off the current piece, **save** the short right sliver, and **take** the long left piece. After `n` days the save jar holds one full piece — a buffer, not extra daily dose. Next cycle the new “whole strip” is `dose × (1 − 1/n)`.

Default: start 8 mg, **n = 6** (16.7% every 6 days), switch to 2 mg films once the strip reaches 2.25 mg.

A dose bigger than one film is just several films: 16 mg on 8 mg strips is two a day. Only one of them is ever cut.

## Why save-a-sliver

The demanding part of a taper is often not the milligrams but the sense of getting less. SAS frames each day’s remaining piece as a complete strip — the dose you have — while the cut-off sliver leaves the daily routine.

People tend to work with what is in hand. Surplus that stays in view is easier to use; once the sliver is saved, it is no longer part of today’s dose. The bank is a safety net if you need to step back up, not a second supply for the same day.

## Pace

Every step is held for days on purpose. Buprenorphine’s half-life is long — usually quoted as 24–42 hours — so a new dose needs most of a cycle to fully land: about 88–91% of the way there on day 1, 98–100% by day 6. That is why the ladder moves in cycles instead of shaving a little off every day, and it puts a floor under how fast this can honestly go. The default is roughly two months from 8 mg to 1 mg.

Plenty of people need longer than that, and the tool is built for it. Hold a cycle, raise `n`, or stretch the cycle length:

| Settings | Cycle | Step | 8 mg → ~1 mg |
|---|---|---|---|
| default (`n = 6`) | 6 days | 16.7% | 66 days (~2.2 months) |
| `--hold-days 9` | 9 days | 16.7% | 99 days (~3.3 months) |
| `--n 10 --hold-days 9` | 9 days | 10.0% | 180 days (~5.9 months) |
| `--n 10` | 10 days | 10.0% | 200 days (~6.6 months) |

Going slower is a plan, not a failure.

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
python3 taper.py --start-mg 16          # two 8 mg strips a day
python3 taper.py --start-mg 20 --film-strength 12
python3 test_taper.py          # math checks
```

No extra packages. Python 3.11 is fine. Same math as the site. Cut marks are a full unused film: TAKE left, SAVE, then the already-off remainder. `--cycle N` prints only that cycle’s cut with the extra note. `--stop-mode above` matches the classic n=6/8/10 comparison (last cycle still strictly above target). `--start-date` adds real dates to the schedule, the same ones the site's calendar shows. `--film-strength` says which strength you actually hold, when it is not the one the start dose implies.

## Tests

Three suites. The first needs nothing but Python; the other two need Node and a browser.

```bash
python3 test_taper.py       # schedule maths
node test_parity.js         # index.html vs taper.py
node test_layout.js         # viewport sweep, 280px to 1920px
```

### `test_taper.py`

40 checks over the arithmetic the schedule is built on — the closed forms against the simulation, the per-cycle invariants (dose splits exactly, length fraction equals dose fraction, the bank is one whole piece per cycle), that the daily dose never rises across a film switch, and the published film geometry. Standard library only.

The multi-film layout gets a matrix of its own: **720 ladders, 10,597 cycles** — start doses from 1 to 32 mg against all four official strengths, `n` from 2 to 30, three film lengths, the 2 mg switch both ways — checked cycle by cycle for the properties that make the instruction safe to follow. Nothing is lost between films; milligrams still track millimetres; no mark runs off the end of a film; exactly one film a day is ever cut; you open exactly the films the dose needs and never one more; and the sliver is measured from the piece on the marked film rather than the film's own end. A further check asserts the matrix actually reaches the hard shapes — days from 1 to 16 films, days whose sliver runs onto film you never open, days with nothing to cut at all — so it cannot quietly stop covering them.

### `test_parity.js` — what it tests and why

The taper maths is written **twice**: `buildSchedule()` in `index.html` and `build_schedule()` in `taper.py`. The site tells people the two agree, and `test_taper.py` only covers the Python one. This test checks the claim, because the two had already drifted once.

It loads `index.html` in a headless browser, runs both implementations over the same inputs, and diffs the results — comparing all 24 fields of every cycle row plus 9 summary figures.

**31 named schedules** go through the CLI, so the argument plumbing is covered too: start doses 0.1–64 mg, `n` from 2 to 30, the 2 mg switch on and off, stretched cycles, `n`-below-3, non-default film lengths and strengths, doses needing two to eight films a day, clamp boundaries, empty ladders.

**640 more** go straight at `build_schedule()` in one Python process — every start dose from 1 to 32 mg against every official film strength, `n` from 2 to 30, and two non-default film lengths. That is **9,212 cycles** of the film layout compared field by field, up to a sixteen-strip day. It also checks the shape of its own coverage, so a grid that stopped producing multi-film days would fail rather than pass silently. Then `baseFilmMg` across 11 film sizes.

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

This is that sweep, committed. It loads the page at **14 widths from 280px to 1920px**, in both themes, across several cycles, zoom levels, calendar densities and measurement modes, plus fifteen reshaping input cases and a pass that redraws one day on each of the four film strengths — **467 viewport states** — and checks five things at each:

| Failure | Detected by |
|---|---|
| **overflow** — the page scrolls sideways | `scrollWidth > clientWidth` on the document |
| **overlap** — two pieces of text drawn on top of each other | pairwise rectangle intersection within each positioned group |
| **clipping** — a box too small for its text | `scrollWidth`/`scrollHeight` vs `clientWidth`/`clientHeight` |
| **spill** — an absolute label escaping its container | bounding box against its parent's |
| **bar count** — a drawing showing a different day than it describes | one bar per film in each panel, against the layout for that panel's strength |

Any console or page error fails it too. Same setup as the parity test; same skip behaviour without a browser.

Via npm scripts:

```bash
npm test           # parity + layout
npm run test:all   # all three suites
```

All three run in GitHub Actions on every push and pull request.

## Method (every day of a cycle)

1. Start with the current “whole strip” (cycle 1: a full 8 mg film, or several if your dose is bigger than one).
2. Keep full width; cut along length only. Mark, then cut with a razor, not scissors.
3. Cut `1/n` off the **right** end. Save that sliver. Take the long left piece. Once daily. If the day is more than one film, cut one of them and take the rest whole.
4. After `n` days the save jar holds one full piece. Do not use the bank as extra daily dose or the taper never drops.
5. Next cycle, the leftover size is the new whole strip. Repeat to the target (default 1 mg).

Hold a cycle if cravings spike, sleep goes, or you are restless and sweating. When the sliver is under ~1 mm, switch to 2 mg films. Lock up saved pieces (dangerous to kids and pets). Ask the prescriber to step quantity down with the dose.

## More than one film a day

Start at 16 mg with 8 mg strips and one day's dose is two films. That is supported, and it changes nothing about the arithmetic — the ladder is milligrams, and 16 mg cuts 1/6 the same way 8 mg does. What it changes is the daily ritual, so the tool spells that part out:

> **2 × 8 mg films a day: 1 film taken whole, plus the marked film below.**

Take the whole ones as they are; **only one strip is ever cut, on any day, at any dose**. Picture the day laid end to end: you take from the left, and everything past the mark goes in the jar. So you open only the strips the dose actually reaches — a strip that would be opened purely to put it in the jar stays in the box. The schedule's Film column shows `×2`, the calendar puts a small `×2` beside the dose, and both drawings show one bar per strip you open.

The **Life-size film** panel is the one exception, on purpose: pick a different strength in the size table and it redraws the same day on that film, film count and all, so you can see what a 32 mg day looks like on 12 mg strips instead of 8 mg ones. The cut-mark panel above always stays on the strength your inputs describe.

Above 12 mg no single official film holds the dose, so the plan defaults to 8 mg strips. Set **Film strength you cut** (or `--film-strength`) if you hold something else — 20 mg is two 12 mg strips if that is what is in the box.

## Limitation

The schedule runs on **one film strength at a time** and either stays on that strength or **switches only to 2 mg films**. It does not auto-step 12 → 8 → 4 mg. Clicking those rows on the site only changes the life-size drawing.

To plan a different start, change the inputs and recalc — for example start dose 12, start dose 4, or turn off the 2 mg switch to stay on 8 mg films the whole way. The base film is the smallest official strength that holds the start dose (2 / 4 / 8 / 12 mg), and 8 mg above that; `--film-strength` overrides it if you are cutting something else.

All four Suboxone strengths measure 22 mm on the side this tool cuts, so the film-length input is the same number whichever you start on. The two low strengths (2 and 4 mg) share one density and the two high ones (8 and 12 mg) share another that is 4× as concentrated — which is why moving from 8 mg to 2 mg films makes the same dose four times longer, and the same cut four times more forgiving.

If a run stops at the 40-cycle cap before reaching the target, or the 2 mg switch cannot fire without raising the dose, both the site and the CLI say so instead of quietly returning a short ladder.

## Contributing

[ARCHITECTURE.md](ARCHITECTURE.md) explains how the whole thing runs — entry points, every formula, the film-layout rule, and what each test suite is guarding. [CLAUDE.md](CLAUDE.md) is the checklist for making a change. [CONTRIBUTING.md](CONTRIBUTING.md) has the house rules.

The short version: `index.html` stays one self-contained file, `taper.py` stays standard-library only, and if you touch the maths in one you touch it in both and run `node test_parity.js`.

## License

[MIT](LICENSE) © 2026 Kostia K.

The licence covers the code. It is not medical advice and carries no warranty — that is the "AS IS" clause doing real work here, not boilerplate. Take the schedule to a prescriber before day 1.

---

Strictly unofficially, the method can be called **SAS-Sub-minning** — the stat you are grinding down is Suboxone.

