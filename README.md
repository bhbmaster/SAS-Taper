# SAS-Taper

**SAS** means **save-a-sliver**.

A geometric buprenorphine (Suboxone) film-taper calculator. **Not medical advice.** Bring the schedule to your prescriber before day 1.

- Live site: [bhbmaster.github.io/SAS-Taper](https://bhbmaster.github.io/SAS-Taper/) <--- Main site
- Source: [github.com/bhbmaster/SAS-Taper](https://github.com/bhbmaster/SAS-Taper)  

Each day you cut `1/n` of the current piece. **Save** the short right sliver. **Take** the long left piece. After `n` days the save jar holds one full piece: a buffer, not extra daily dose. Next cycle the new whole strip is `dose × (1 − 1/n)`.

Default: start 8 mg, **n = 6** (16.7% every 6 days), switch to 2 mg films once the strip reaches 2.25 mg.

A dose bigger than one film is just several films: 16 mg on 8 mg strips is two a day. Only one of them is ever cut.

## Two cut modes

The cut is the same physical act either way. What differs is what stays constant.

|  | **Geometric** (default) | **Linear** (easier to cut) |
|---|---|---|
| what you cut | 1/n of the piece **in your hand** | 1/n of the **first** strip, every time |
| the cut | shrinks with the dose | never changes, same mg same mm |
| each step | same **percentage** (16.7% at n = 6) | same **milligrams** |
| the shape | approaches zero, never arrives | lands on zero after n − 1 steps |
| 8 mg at n = 6 | 66 days to 0.96 mg, 425 mg used | **30 days to zero, 120 mg used** |
| CLI | default | `--cut-mode linear` |
| cutting it | a new, smaller measurement each cycle | **measure once, reuse the same mark every day** |

**Linear is the easier one to cut**, which is the practical reason to pick it. The mark never moves. Measure one time. Use that mark every day. You do not calculate a new and smaller measurement each cycle. It never becomes smaller than one millimetre, where a razor and a ruler stop resolving. The site disables the 2 mg switch in that mode and says why: the switch exists to rescue a cut that has become too fine. Here it never does.

**It is also steeper where a taper is hardest.** Equal milligrams are growing percentages:

```
8 mg, n = 6, linear:  6.67 → 5.33 → 4.00 → 2.67 → 1.33 → 0
drop from the previous: 20%    25%    33%    50%   100%
```

The default mode holds a flat 16.7% the whole way; this one finishes with a 50% step and then a 100% one. That is not a reason to avoid it. Plenty of prescriptions are written exactly this way, "come down by a sixth of your starting dose each step". It is the reason the tool shows you those percentages the moment you switch. Neither shape is right for everyone; both let you hold a cycle whenever you need to.

## Why save-a-sliver

The demanding part of a taper is often not the milligrams but the sense of getting less. SAS frames each day's remaining piece as a complete strip, the dose you have, while the cut-off sliver leaves the daily routine.

People work with what is in hand. Surplus that stays in view is easier to use, and once the sliver is saved it is no longer part of today's dose. The bank is a safety net if you need to step back up, not a second supply for the same day.

## Pace

Every step is held for days on purpose. Buprenorphine's half-life is long, usually quoted as 24-42 hours, so a new dose needs most of a cycle to land: about 88-91% of the way there on day 1, and 98-100% by day 6. That is why the ladder moves in cycles instead of shaving a little off every day, and it puts a floor under how fast this can honestly go. The default is roughly two months from 8 mg to 1 mg.

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

There is no build step and no server. `index.html` is one self-contained file. All the CSS and JavaScript are inline and nothing is fetched over the network, so opening it straight from disk in any browser gives you the identical calculator, working offline. Clone the repo, or just save that one file and double-click it.

Either way: measure your film **length only**. Put that in the inputs. The schedule, cut marks and graphs update live. Click a cycle for that day's ruler (TAKE left, SAVE right). Print it for your prescriber.

### Two ways to find the cut

The life-size film panel offers a choice, and only that panel. Everything else on the page measures.

- **Folding** (the default) approximates the dose as whole parts of a folded grid. Halve the film, halve it again, take five of the six parts. No ruler and no arithmetic, which for most people is *more* reproducible at 6 am than measuring 15.28 mm. The long side folds into 2, 3, 4 or 8; the short side into 2, 3 or 4.
- **Measuring** is the exact mark: one straight cut at a millimetre figure the schedule gives you, accurate to whatever your ruler and blade manage. One button away, and the cut-mark panel above always measures whichever is selected.

A fold can only land on the fractions it can make, so the panel always states the dose it gives, the dose the ladder asked for, and the difference between them. It buys simplicity only inside the cutting tolerance you set. If a plain half is within the slip you would make with a ruler anyway, it offers the plain half. Among folds that take the same strokes, it still takes the closer dose.

**[How the fold is chosen](https://bhbmaster.github.io/SAS-Taper/fold.html)** is a page of its own, an interactive walkthrough of the search, with every diagram driven by a slider. The algorithm listing is 80-column text with its comments in an aligned second column, so it scrolls sideways rather than re-wrapping; a **Wrap** button on the listing takes the lines apart if you would rather have them all on screen. The ladder of reachable fractions is a control as well as a picture: click any of the 54 ticks, or take one from the list under it, and that fold is drawn beside the one the search chose, with both difficulty scores itemised and a plain statement of what the trade cost. It ships with the site (`fold.html`), so it works offline too.

**[How the dashed line is drawn](https://bhbmaster.github.io/SAS-Taper/lag.html)** is the same kind of page for the lag curve on the first graph. A half-life slider, a drop / jump / washout / taper switch, and the recurrence one day at a time, including the closed form of a single step. It ships with the site (`lag.html`) and works offline too.

**In linear mode the folds come out exact.** A constant step lands on `5/6, 2/3, 1/2, 1/3, 1/6` and so on, every cycle, so a linear taper can be cut from the first day to the last without measuring anything.

### The numbers at the strip

You should never have to do arithmetic while holding a razor. Five columns of the schedule are tinted as one block, and they are the whole job:

| Column | What it is |
|---|---|
| **Take mg** | how much you take that day. This is the day's total. You can split the take piece |
| **Take mm** | mark a full film that far from its **left** end, then cut once. The left piece is the day's take. You can split that piece after you cut |
| **Save mg** | milligrams that go in the jar. Do not take this as extra dose |
| **Save mm** | everything right of the mark. Put that in the jar |
| **Δ save mm** | how much more the jar gets than last cycle. That extra is the sliver |

Take + Save is the film you opened, so nothing is unaccounted for. The save is larger than that cycle's sliver, because it also holds the part earlier cycles already removed, and it grows every cycle. That growth is Δ save, and it is the sliver. Δ save shows a dash where there is nothing to compare: a restart on a fresh 2 mg film, a day that opens fewer films than the last, or a day whose dose is a whole number of films and needs no cut.

The other columns are running totals. They are not a second cut instruction:

| Column | What it is |
|---|---|
| **Used mg** | milligrams you consumed in this cycle |
| **Sum mg** | milligrams you have consumed since day 1 |
| **Sum strips** | how many strips you consumed, at the strip strength you set. This is less than the strips you opened, because you saved some |
| **Banked mg** | this cycle's slivers added up. After a full cycle that is one whole piece. Buffer, not extra daily dose |

Units sit small and muted **beside every value as well as the heading**, so a row reads on its own, the same treatment as on the compare, prescription and film-size tables, and on the calendar. Not sure what a column means? Hover its heading on a desktop, or open **What each column means** under the table. Same twelve definitions either way.

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

No extra packages. Python 3.11 is fine. Same math as the site. The table carries the same tinted block the site does: Take mg / Take mm / Save mg / Save mm / +Save mm. Cut marks are a full unused film: TAKE on the left, then the save, split into this cycle's extra (`#`) and the part already removed before (`.`). Everything right of the take mark goes in the jar. `--cycle N` prints only that cycle's cut with the extra note. `--stop-mode above` matches the classic n=6/8/10 comparison (last cycle still strictly above target). `--start-date` adds real dates to the schedule, the same ones the site's calendar shows. `--film-strength` says which strength you actually hold, when it is not the one the start dose implies. `--cut-mode linear` changes from the default geometric cut to the linear one. The report names the mode, the day the dose reaches zero, and the percentage each step actually is.

## Tests

Three suites. The first needs nothing but Python; the other two need Node and a browser.

```bash
python3 test_taper.py       # schedule maths
node test_parity.js         # index.html vs taper.py
node test_layout.js         # viewport sweep, 280px to 1920px
```

Each suite prints how much it actually checked, because the headline test count
badly understates it. Most of the work happens inside matrix loops, and one
test method can make tens of thousands of assertions:

| Suite | Test cases | What that means |
|---|---|---|
| `test_taper.py` | **74 tests, ~501,000 assertions** | 1,440 ladders / 15,422 cycles in the matrix alone |
| `test_parity.js` | **1,323 schedules + 13,920 folded cuts + 2,444 lag checks, ~647,000 field comparisons** | 13,567 matrix cycles × 28 row fields, plus summaries, months, the compare table, the fraction search, the lag-curve closed form and the explainer copy |
| `test_layout.js` | **697 viewport states, 989 checks** | each state is a whole rendered page, `index.html`, `fold.html` or `lag.html`, measured for five failure modes, plus a source scan for leftover dashes, ranges spelled "to", and Take still being the day's total you can split |

Around **1,148,000 individual checks** in total, in about five minutes.

### `test_taper.py`

74 test methods, and because most of them walk a matrix, roughly 501,000 individual assertions. They cover the arithmetic the schedule is built on: the closed forms against the simulation, the per-cycle invariants (dose splits exactly, length fraction equals dose fraction, the bank is one whole piece per cycle), that the daily dose never rises across a film switch, and the published film geometry. A class of its own covers the folded-grid search: among folds that take the same strokes it takes the closer dose (0.32 mg on an 8 mg film is 1/24, not 1/16). Another covers the linear mode: the cut never changes in either unit, the dose falls in equal steps, it lands on zero after exactly n − 1 of them, no cycle ever has a zero or negative dose, the closed form matches the simulation, the percentage step grows every cycle, and the two rescues the default mode needs are switched off. Standard library only.

The multi-film layout gets a matrix of its own: **1,440 ladders, 15,422 cycles**, covering start doses from 1 to 32 mg against all four official strengths, `n` from 2 to 30, three film lengths, the 2 mg switch both ways, and **both cut modes**, checked cycle by cycle for the properties that make the instruction safe to follow. Nothing is lost between films; milligrams still track millimetres; no mark runs off the end of a film; exactly one film a day is ever cut; you open exactly the films the dose needs and never one more; the sliver is measured from the piece on the marked film rather than the film's own end; take and save partition the films you opened in both units; Δ save is the sliver wherever it is reported and never negative; it is blank for exactly the three stated reasons and each of those is actually reached; and the save grows on every cycle that reports one. A further check asserts the matrix reaches the hard shapes: days from 1 to 16 films, days whose sliver runs onto film you never open, days with nothing to cut at all, so it cannot quietly stop covering them.

### `test_parity.js`: what it tests and why

The taper maths is written **twice**: `buildSchedule()` in `index.html` and `build_schedule()` in `taper.py`. The site tells people the two agree, and `test_taper.py` only covers the Python one. This test checks the claim, because the two had already drifted once.

It loads `index.html` in a headless browser, runs both implementations over the same inputs, and diffs the results, comparing all 28 fields of every cycle row, 9 summary figures, every 30-day month bucket, and the n = 6/8/10 comparison table.

**43 named schedules** go through the CLI, so the argument plumbing is covered too: start doses 0.1-64 mg, `n` from 2 to 30, the 2 mg switch on and off, stretched cycles, `n`-below-3, non-default film lengths and strengths, doses needing two to eight films a day, clamp boundaries, empty ladders.

**1,280 more** go straight at `build_schedule()`, the whole grid in both cut modes, in one Python process: every start dose from 1 to 32 mg against every official film strength, `n` from 2 to 30, and two non-default film lengths. That is **13,567 cycles** compared field by field, up to a sixteen-strip day. It also checks the shape of its own coverage, so a grid that stopped producing multi-film days would fail rather than pass silently. Then `baseFilmMg` across 11 film sizes.

The dashed lag curve is JS-only, so it is not in that field-by-field diff. The same suite still checks it: the closed form of a step down, a step up and a washout across film and depot-scale half-lives, that a longer half-life stays higher, that 900 h does not hug the ladder, and that typing 900 is no longer clamped to 80.

It exits **0** on a match, **1** with a list of mismatches otherwise. If Node or a browser is missing it prints `skipped` and exits 0, so a plain checkout still passes.

#### Setup on Linux and macOS

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

The script also finds a browser on its own in the usual places: the Playwright cache (`~/.cache/ms-playwright` on Linux, `~/Library/Caches/ms-playwright` on macOS) and installed Chrome or Chromium, so `CHROMIUM_PATH` is only needed for something in an unusual location.

### `test_layout.js`: what it tests and why

Several parts of the page are positioned from measured pixels rather than by normal flow: the ruler tick captions, the life-size cut label, the calendar grid. Those have broken four separate times: captions stacked on each other, a percentage painted over a button, "SAVE" sliced in half, the page scrolling sideways on a narrow phone. Each was found by sweeping viewports by hand, then lost again, because nothing re-ran the sweep.

This is that sweep, committed. It loads the page at **14 widths from 280px to 1920px**, in both themes, across several cycles, zoom levels, calendar densities and measurement modes, plus twenty-one reshaping input cases, a pass that redraws one day on each of the four film strengths, and a pass over the linear mode. That is **697 viewport states**, `fold.html` and `lag.html` included, and it checks five things at each:

| Failure | Detected by |
|---|---|
| **overflow**, the page scrolls sideways | `scrollWidth > clientWidth` on the document |
| **overlap**, two pieces of text drawn on top of each other | pairwise rectangle intersection within each positioned group |
| **clipping**, a box too small for its text | `scrollWidth`/`scrollHeight` vs `clientWidth`/`clientHeight` |
| **spill**, an absolute label escaping its container | bounding box against its parent's |
| **bar count**, a drawing showing a different day than it describes | one bar per film in each panel, against the layout for that panel's strength |

Any console or page error fails it too. Same setup as the parity test; same skip behaviour without a browser.

Via npm scripts:

```bash
npm test           # parity + layout
npm run test:all   # all three suites
```

All three run in GitHub Actions on every push and pull request.

## Method (every day of a cycle)

0. Pick a cut mode. Geometric (default) or linear. See [Two cut modes](#two-cut-modes). Everything below is the same either way. Only the size of the next cut differs.
1. Start with the current whole strip. For cycle 1, this is one full 8 mg film. If your dose is larger than one film, start with that number of films.
2. Keep the full width. Cut along the length only. Mark the cut first. Then cut with a razor. Do not use scissors.
3. Cut `1/n` from the **right** end. Save that sliver. Take the long left piece. That is how much you take that day, the day's total. You do not have to take it all at once. You can split the take piece. Example: one piece in the morning and one in the evening. Or more often. Or less often. If the day is more than one film, cut one of them and take the rest whole.
4. After `n` days the save jar holds one full piece. Do not take the bank as extra daily dose. If you do, the taper does not decrease.
5. Next cycle, the leftover size is the new whole strip. In geometric mode the next cut is smaller. In linear mode you cut the identical piece again. Repeat until you reach the target (default 1 mg). In linear mode, repeat until there is nothing left to cut.

**Cutting aids.** A steel ruler and a new blade on a mat covers most of the ladder. If your cuts wander, purpose-made film slicers exist (search "Suboxone film cutter" or "subslicer"). **Below what you can cut.** Some people move to liquid dosing. A 2 mg film in 20 mL is *theoretically* 0.1 mg/mL. The manufacturer does not sanction this. Buprenorphine is only sparingly water-soluble, so the real strength can differ from the arithmetic. A homemade solution is not sterile. Raise it with your prescriber first.

Hold a cycle if cravings spike, sleep goes, or you are restless and sweating. When the sliver is under ~1 mm, change to 2 mg films. Lock saved pieces (dangerous to children and pets). Ask the prescriber to decrease quantity with the dose.

## More than one film a day

Start at 16 mg with 8 mg strips and one day's dose is two films. That is supported, and it changes nothing about the arithmetic. The ladder is milligrams, and 16 mg cuts 1/6 the same way 8 mg does. What it changes is the daily ritual, so the tool spells that part out:

> **2 × 8 mg films a day: 1 taken whole, plus the marked one below.**

TAKE the whole ones as they are. **Only one strip is ever cut, on any day, at any dose**. Picture the day laid end to end. You take from the left. Everything past the mark goes in the jar. So you open only the strips the dose actually reaches. A strip that would be opened only to put it in the jar stays in the box. The schedule's Film column shows `×2`. The calendar puts a small `×2` beside the dose. Both drawings show one bar per strip you open.

The **Life-size film** panel is the one exception, on purpose: pick a different strength in the size table and it redraws the same day on that film, film count and all, so you can see what a 32 mg day looks like on 12 mg strips instead of 8 mg ones. The cut-mark panel above always stays on the strength your inputs describe.

Above 12 mg no single official film holds the dose, so the plan defaults to 8 mg strips. Set **Film strength you cut** (or `--film-strength`) if you hold something else: 20 mg is two 12 mg strips if that is what is in the box.

## Limitation

The schedule runs on **one film strength at a time**. It then keeps that strength, or it **changes only to 2 mg films**. It does not auto-step 12 → 8 → 4 mg. A click on those rows on the site only changes the life-size drawing.

To plan a different start, change the inputs and calculate again. Try start dose 12, start dose 4, or disable the 2 mg switch to stay on 8 mg films the whole way. The base film is the smallest official strength that holds the start dose (2 / 4 / 8 / 12 mg), and 8 mg above that. `--film-strength` overrides it if you are cutting something else.

All four Suboxone strengths measure 22 mm on the side this tool cuts, so the film-length input is the same number whichever you start on. The two low strengths (2 and 4 mg) share one density and the two high ones (8 and 12 mg) share another that is 4× as concentrated, which is why moving from 8 mg to 2 mg films makes the same dose four times longer, and the same cut four times more forgiving.

If a run stops at the 40-cycle cap before reaching the target, or the 2 mg switch cannot fire without raising the dose, both the site and the CLI say so instead of quietly returning a short ladder.

## Contributing

[ARCHITECTURE.md](ARCHITECTURE.md) explains how the whole thing runs: entry points, every formula, the film-layout rule, and what each test suite is guarding. [CLAUDE.md](CLAUDE.md) is the checklist for making a change. [CONTRIBUTING.md](CONTRIBUTING.md) has the house rules.

The short version: `index.html` stays one self-contained file, `taper.py` stays standard-library only, and if you touch the maths in one you touch it in both and run `node test_parity.js`.

## License

[MIT](LICENSE) © 2026 Kostia K.

The licence covers the code. It is not medical advice and carries no warranty. That is the "AS IS" clause doing real work here, not boilerplate. Take the schedule to a prescriber before day 1.

---

Strictly unofficially, the method can be called **SAS-Sub-minning**, because the stat you are grinding down is Suboxone.

