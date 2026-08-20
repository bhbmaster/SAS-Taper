# SAS-Taper

**SAS** means **save-a-sliver**.

A geometric buprenorphine (Suboxone) film-taper calculator. **Not medical advice.** Bring the schedule to your prescriber before day 1.

- Live site: [bhbmaster.github.io/SAS-Taper](https://bhbmaster.github.io/SAS-Taper/) <--- Main site
- Source: [github.com/bhbmaster/SAS-Taper](https://github.com/bhbmaster/SAS-Taper)  

Each day you cut `1/n` off the current piece, **save** the short right sliver, and **take** the long left piece. After `n` days the save jar holds one full piece — a buffer, not extra daily dose. Next cycle the new “whole strip” is `dose × (1 − 1/n)`.

Default: start 8 mg, **n = 6** (16.7% every 6 days), switch to 2 mg films once the strip reaches 2.25 mg.

A dose bigger than one film is just several films: 16 mg on 8 mg strips is two a day. Only one of them is ever cut.

## Two cut modes

The cut is the same physical act either way. What differs is what stays constant.

|  | **Geometric** (default) | **Linear** (easier to cut) |
|---|---|---|
| what you cut | 1/n of the piece **in your hand** | 1/n of the **first** strip, every time |
| the cut | shrinks with the dose | never changes — same mg, same mm |
| each step | same **percentage** (16.7% at n = 6) | same **milligrams** |
| the shape | approaches zero, never arrives | lands on zero after n − 1 steps |
| 8 mg at n = 6 | 66 days to 0.96 mg, 425 mg used | **30 days to zero, 120 mg used** |
| CLI | default | `--cut-mode linear` |
| cutting it | a new, smaller measurement each cycle | **measure once, reuse the same mark every day** |

**Linear is the easier one to actually cut**, which is the practical reason to pick it. The mark never moves: you measure once and reuse it every day, instead of working out a new and smaller measurement each cycle — and it never shrinks into the sub-millimetre range where a razor and a ruler stop resolving. The site turns the 2 mg switch off in that mode and says why: the switch exists to rescue a cut that has got too fine, and here it never does.

**It is also steeper where a taper is hardest.** Equal milligrams are growing percentages:

```
8 mg, n = 6, linear:  6.67 → 5.33 → 4.00 → 2.67 → 1.33 → 0
drop from the previous: 20%    25%    33%    50%   100%
```

The default mode holds a flat 16.7% the whole way; this one finishes with a 50% step and then a 100% one. That is not a reason to avoid it — plenty of prescriptions are written exactly this way, "come down by a sixth of your starting dose each step" — but it is the reason the tool shows you those percentages the moment you switch. Neither shape is right for everyone; both let you hold a cycle whenever you need to.

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

There is nothing to build and no server. `index.html` is one self-contained file — all the CSS and JavaScript are inline, nothing is fetched over the network — so opening it straight from disk in any browser gives you the identical calculator, working offline. Clone the repo, or just save that one file and double-click it.

The schedule maths inside it is not written twice. It lives once, in `taper.py`, and `gen_core.py` translates it into a block of JavaScript that is committed into `index.html` — which is how the page and the CLI can promise the same numbers. That happens before the commit, never in your browser.

Either way: measure your film **length only**, put that in the inputs, and the schedule / cut marks / graphs update live. Click a cycle for that day’s ruler (TAKE left, SAVE right). Print it for your prescriber.

### The four numbers at the strip

You should never have to do arithmetic while holding a razor. Five columns of the schedule are tinted as one block, and they are the whole job:

| Column | What you do with it |
|---|---|
| **Take mg** | the dose — what you swallow |
| **Take mm** | mark a full film that far from its **left** end, and cut once |
| **Save mg** | what goes in the jar, in milligrams |
| **Save mm** | everything right of the mark — the rest of the film |
| **Δ save mm** | how much more the jar gets than last cycle |

Take + Save is the film you opened, so nothing is unaccounted for. The save is bigger than that cycle's sliver, because it also carries the part earlier cycles had already taken off, and it grows every cycle — that growth is Δ save, and it is the sliver. Δ save shows a dash where there is nothing comparable: a restart on a fresh 2 mg film, a day that opens fewer films than the last, or a day whose dose is a whole number of films and needs no cut.

Everything else on the row is context. Units sit small and muted **beside every value as well as the heading**, so a row reads on its own — the same treatment on the compare, prescription and film-size tables, and on the calendar. Not sure what a column means? Hover its heading on a desktop, or open **What each column means** under the table — same twelve definitions either way.

## CLI

```bash
python3 taper.py
python3 taper.py --compare
python3 taper.py --cycle 6
python3 taper.py --n 10 --no-switch-2mg
python3 taper.py --start-date 2026-03-01
python3 taper.py --cut-mode linear          # same cut every cycle, ends at zero
python3 taper.py --cut-mode linear --n 10 --target 0
python3 taper.py --start-mg 16          # two 8 mg strips a day
python3 taper.py --start-mg 20 --film-strength 12
python3 test_taper.py          # math checks
```

No extra packages. Python 3.11 is fine. Same math as the site. The table carries the same tinted block the site does — Take mg / Take mm / Save mg / Save mm / +Save mm. Cut marks are a full unused film: TAKE on the left, then the save, split into this cycle's extra (`#`) and the part already off before (`.`). Everything right of the take mark goes in the jar. `--cycle N` prints only that cycle’s cut with the extra note. `--stop-mode above` matches the classic n=6/8/10 comparison (last cycle still strictly above target). `--start-date` adds real dates to the schedule, the same ones the site's calendar shows. `--film-strength` says which strength you actually hold, when it is not the one the start dose implies. `--cut-mode linear` switches from the default geometric cut to the linear one; the report names the mode, the day the dose reaches zero, and the percentage each step actually is.

## Tests

Three suites. The first needs nothing but Python, the second nothing but Python and Node, and only the third needs a browser.

```bash
python3 gen_core.py --check # the site's copy of the maths is current
python3 test_taper.py       # schedule maths, and the translator
node test_parity.js         # the generated block vs taper.py
node test_layout.js         # viewport sweep, 280px to 1920px
```

Each suite prints how much it actually checked, because the headline test count
badly understates it — most of the work happens inside matrix loops, and one
test method can make tens of thousands of assertions:

| Suite | Test cases | What that means |
|---|---|---|
| `test_taper.py` | **79 tests, ~482,000 assertions** | 1,440 ladders / 15,422 cycles in the matrix alone, plus the generator's own tests |
| `test_parity.js` | **1,323 schedules, 463,504 field comparisons** | 13,567 matrix cycles × 28 row fields, plus summaries, months and the compare table |
| `test_layout.js` | **537 viewport states, 587 checks** | each state is a whole rendered page measured for five failure modes |

Around **945,000 individual checks** in total, in about three minutes.

### `test_taper.py`

79 test methods — and, because most of them walk a matrix, roughly 482,000 individual assertions — over the arithmetic the schedule is built on — the closed forms against the simulation, the per-cycle invariants (dose splits exactly, length fraction equals dose fraction, the bank is one whole piece per cycle), that the daily dose never rises across a film switch, and the published film geometry. A class of its own covers the linear mode: the cut never changes in either unit, the dose falls in equal steps, it lands on zero after exactly n − 1 of them, no cycle ever has a zero or negative dose, the closed form matches the simulation, the percentage step grows every cycle, and the two rescues the default mode needs are switched off. Standard library only.

The multi-film layout gets a matrix of its own: **1,440 ladders, 15,422 cycles** — start doses from 1 to 32 mg against all four official strengths, `n` from 2 to 30, three film lengths, the 2 mg switch both ways, **both cut modes** — checked cycle by cycle for the properties that make the instruction safe to follow. Nothing is lost between films; milligrams still track millimetres; no mark runs off the end of a film; exactly one film a day is ever cut; you open exactly the films the dose needs and never one more; the sliver is measured from the piece on the marked film rather than the film's own end; take and save partition the films you opened in both units; Δ save is the sliver wherever it is reported and never negative; it is blank for exactly the three stated reasons and each of those is actually reached; and the save grows on every cycle that reports one. A further check asserts the matrix reaches the hard shapes — days from 1 to 16 films, days whose sliver runs onto film you never open, days with nothing to cut at all — so it cannot quietly stop covering them.

Eighteen more tests cover `gen_core.py`, the translator that turns the maths in `taper.py` into the JavaScript the site runs — what it accepts, what it refuses by file and line, and the four places Python and JavaScript disagree about the same code. One of those, `int()` versus `//`, is invisible to the parity suite, because the core only ever divides positive numbers.

### `test_parity.js` — what it tests and why

The taper maths is written **once**, between the `# --- CORE BEGIN ---` and `# --- CORE END ---` markers in `taper.py`. `gen_core.py` translates it into the generated block inside `index.html`, so the site and the CLI cannot disagree by construction — but a translator can still be wrong, and it is the only thing between the two.

This test is what checks it. It lifts the generated block and its adapter straight out of `index.html`, evaluates them in Node, and diffs the result against `taper.py` — all 28 fields of every cycle row, 13 summary figures, every 30-day month bucket, and the n = 6/8/10 comparison table. It runs `python3 gen_core.py --check` first, so a stale block fails here rather than shipping, and it evaluates the block in strict mode, where the scoping mistake a translator is most likely to make throws instead of computing something plausible.

**No browser needed.** It used to drive headless Chromium to reach into the page; now the maths is a self-contained block of arithmetic it can simply run, so the whole suite finishes in about eight seconds on a bare checkout. Only `test_layout.js` still needs Chromium.

**43 named schedules** go through the CLI, so the argument plumbing is covered too: start doses 0.1–64 mg, `n` from 2 to 30, the 2 mg switch on and off, stretched cycles, `n`-below-3, non-default film lengths and strengths, doses needing two to eight films a day, clamp boundaries, empty ladders.

**1,280 more** go straight at `build_schedule()` — the whole grid in both cut modes — in one Python process — every start dose from 1 to 32 mg against every official film strength, `n` from 2 to 30, and two non-default film lengths. That is **13,567 cycles** compared field by field, up to a sixteen-strip day. It also checks the shape of its own coverage, so a grid that stopped producing multi-film days would fail rather than pass silently. Then `baseFilmMg` across 11 film sizes.

It exits **0** on a match and **1** with a list of mismatches otherwise.

### `test_layout.js` — setup, Linux and macOS

`playwright-core` deliberately ships without a browser, so you need one. Easiest route, and what CI uses:

```bash
npm install                          # installs playwright-core from package.json
npx --yes playwright install chromium   # ~150 MB, downloads once
node test_layout.js
```

On Linux, if Chromium refuses to start over missing system libraries:

```bash
npx --yes playwright install --with-deps chromium   # needs sudo
```

**Already have Chrome?** Skip the download and point at it:

```bash
# macOS
CHROMIUM_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" node test_layout.js

# Linux
CHROMIUM_PATH=/usr/bin/google-chrome node test_layout.js
```

The script also finds a browser on its own in the usual places — the Playwright cache (`~/.cache/ms-playwright` on Linux, `~/Library/Caches/ms-playwright` on macOS) and installed Chrome or Chromium — so `CHROMIUM_PATH` is only needed for something in an unusual location. Without any browser it prints `skipped` and exits 0, so a plain checkout still passes.

### `test_layout.js` — what it tests and why

Several parts of the page are positioned from measured pixels rather than by normal flow: the ruler tick captions, the life-size cut label, the calendar grid. Those have broken four separate times — captions stacked on each other, a percentage painted over a button, "SAVE" sliced in half, the page scrolling sideways on a narrow phone. Each was found by sweeping viewports by hand, then lost again, because nothing re-ran the sweep.

This is that sweep, committed. It loads the page at **14 widths from 280px to 1920px**, in both themes, across several cycles, zoom levels, calendar densities and measurement modes, plus twenty reshaping input cases, a pass that redraws one day on each of the four film strengths, and a pass over the linear mode — **537 viewport states** — and checks five things at each:

| Failure | Detected by |
|---|---|
| **overflow** — the page scrolls sideways | `scrollWidth > clientWidth` on the document |
| **overlap** — two pieces of text drawn on top of each other | pairwise rectangle intersection within each positioned group |
| **clipping** — a box too small for its text | `scrollWidth`/`scrollHeight` vs `clientWidth`/`clientHeight` |
| **spill** — an absolute label escaping its container | bounding box against its parent's |
| **bar count** — a drawing showing a different day than it describes | one bar per film in each panel, against the layout for that panel's strength |

Any console or page error fails it too.

Via npm scripts:

```bash
npm run gen        # regenerate the site's copy of the maths
npm run test:gen   # ...or just check it is current
npm test           # generated-core check + parity + layout
npm run test:all   # all three suites
```

All three run in GitHub Actions on every push and pull request.

## Method (every day of a cycle)

0. Pick a cut mode. Geometric (default) or linear — see [Two cut modes](#two-cut-modes). Everything below is the same either way; only the size of the next cut differs.
1. Start with the current “whole strip” (cycle 1: a full 8 mg film, or several if your dose is bigger than one).
2. Keep full width; cut along length only. Mark, then cut with a razor, not scissors.
3. Cut `1/n` off the **right** end. Save that sliver. Take the long left piece. Once daily. If the day is more than one film, cut one of them and take the rest whole.
4. After `n` days the save jar holds one full piece. Do not use the bank as extra daily dose or the taper never drops.
5. Next cycle, the leftover size is the new whole strip. In geometric mode that means the next cut is smaller; in linear mode you cut the identical piece again. Repeat to the target (default 1 mg), or in linear mode until there is nothing left to cut.

**Cutting aids:** a steel ruler and a fresh blade on a mat covers most of the ladder; if your cuts wander, purpose-made film slicers exist (search “Suboxone film cutter” or “subslicer”). **Below what you can cut:** some people move to liquid dosing — a 2 mg film in 20 mL is *theoretically* 0.1 mg/mL — but that is not manufacturer-sanctioned, buprenorphine is only sparingly water-soluble so the real strength can differ from the arithmetic, and a homemade solution is not sterile. Raise it with your prescriber first.

Hold a cycle if cravings spike, sleep goes, or you are restless and sweating. When the sliver is under ~1 mm, switch to 2 mg films. Lock up saved pieces (dangerous to kids and pets). Ask the prescriber to step quantity down with the dose.

## More than one film a day

Start at 16 mg with 8 mg strips and one day's dose is two films. That is supported, and it changes nothing about the arithmetic — the ladder is milligrams, and 16 mg cuts 1/6 the same way 8 mg does. What it changes is the daily ritual, so the tool spells that part out:

> **2 × 8 mg films a day: 1 taken whole, plus the marked one below.**

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

The short version: `index.html` stays one self-contained file, `taper.py` stays standard-library only, and the maths is written once — inside the CORE markers in `taper.py`. After changing it run `python3 gen_core.py` to update the generated block in `index.html`, then `node test_parity.js`. Never edit that block by hand.

## License

[MIT](LICENSE) © 2026 Kostia K.

The licence covers the code. It is not medical advice and carries no warranty — that is the "AS IS" clause doing real work here, not boilerplate. Take the schedule to a prescriber before day 1.

---

Strictly unofficially, the method can be called **SAS-Sub-minning** — the stat you are grinding down is Suboxone.

