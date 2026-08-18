# Architecture

How SAS-Taper is put together: where it starts, what the formulas are, and what the tests are guarding.

For the rules you have to follow when changing it, see [CLAUDE.md](CLAUDE.md) and [CONTRIBUTING.md](CONTRIBUTING.md). For what the tool is *for*, see [README.md](README.md).

---

## 1. The shape of the thing

Two programs compute the same taper, in two languages, and the site tells people they agree:

```
index.html   the site — one self-contained file, no build, no network
taper.py     the CLI  — standard library only
```

That duplication is deliberate. The site has to work offline from a double-clicked file, so it cannot import anything; the CLI has to run on a machine with nothing installed, so it cannot depend on Node. Neither can be generated from the other without a build step, and a build step would break the first constraint.

The cost is that **the ladder maths exists twice and can drift** — it already did once. `test_parity.js` is the mechanism that keeps the promise honest: it runs both implementations over the same inputs and diffs every field. Everything else in this document is downstream of that one fact.

```
                    ┌───────────────────────────┐
   the contract →   │  same inputs, same rows   │
                    └─────────────┬─────────────┘
                    ┌─────────────┴─────────────┐
            buildSchedule()              build_schedule()
             (index.html)                    (taper.py)
                    │                             │
             8 renderers                    print_schedule()
             8 SVG charts                   --json payload
                    └───────── test_parity.js ────┘
```

---

## 2. Repository map

| File | What it is |
|---|---|
| `index.html` | The whole site: HTML, CSS and JS in one file. ~3060 lines. |
| `taper.py` | The CLI and the reference implementation of the maths. ~1370 lines. |
| `test_taper.py` | Maths checks, standard library only. No browser, no Node. |
| `test_parity.js` | Runs both implementations and diffs them. Needs Node + Chromium. |
| `test_layout.js` | Sweeps viewports for overflow, overlap, clipping, spill, bar-count. |
| `test_browser.js` | Shared browser discovery for the two Node suites. |
| `.github/workflows/tests.yml` | Runs all three on push, PR and manual dispatch. |
| `package.json` | `playwright-core` only, plus the `npm test` scripts. |
| `sitemap.xml`, `.python-version`, `.editorconfig` | Housekeeping. |

There is no `src/`, no bundler, no lockfile-driven install for the site itself. `npm install` exists only to fetch the test browser driver.

---

## 3. Entry points

### The site

`index.html` is a single `<script>` wrapped in an IIFE. The last five lines are the entry point:

```js
applyTheme(currentTheme(), false);   // dark unless the reader chose otherwise
loadStripScale();                    // life-size zoom from localStorage
loadCalPrefs();                      // calendar mode + density
loadInputs();                        // form values from localStorage
render();                            // first paint
```

After that, everything is driven by `render()`, which is called on every form `input`/`change`, on cycle selection, and on the calendar and theme controls:

```js
function render() {
  const opts = readOpts();            // read + clamp the form, note any clamps
  saveInputs(opts);                   // persist (the already-clamped opts)
  const s = buildSchedule(...opts);   // THE maths — everything below is display
  renderCards(s);                     // 7 headline tiles, then the warning banners
  renderCharts(s, opts);              // 8 SVG charts
  renderSchedule(s);                  // the cycle table
  renderCalendar(s, opts);            // month grids, only if a start date is set
  renderRuler(s);                     // the schematic cut-mark bars
  renderStripViz(s);                  // the life-size drawing
  renderCompare(opts);                // the n = 6 / 8 / 10 table
  renderMonths(s);                    // prescription-quantity table
}
```

`readOpts()` is where the display-only inputs are separated from the ones that reach the maths. `cutTolMm`, `halfLifeH` and `startDate` are read into `opts` but **never passed to `buildSchedule`** — that is what stops a chart control from silently moving the ladder and breaking parity.

`saveInputs(opts)` takes the already-read opts rather than re-reading. Re-reading would run `clampOpts` a second time against values it had just corrected, find nothing to fix, and wipe the clamp notices before the banner could show them.

The script is laid out in the order its header comment describes: constants and film specs, maths, input handling, renderers, chart infrastructure, wiring. The CSS carries matching `/* ---- … ---- */` section markers.

### The CLI

`taper.py` ends with `main()` under `raise SystemExit(main())`. It parses arguments, builds the schedule, and then takes one of two paths:

```
main()
 ├── parse_start_date()          # YYYY-MM-DD or None; exit 2 on garbage
 ├── build_schedule(...)         # exit 2 on out-of-range input
 ├── compare_classic()           # only with --compare
 └── --json ? result_to_json()   # asdict(sched) + film_specs + cut_context
           : print_schedule()    # the human-readable report
```

**The two front ends handle bad input differently on purpose.** `build_schedule` raises `ValueError` for a non-positive dose, a non-positive film length or strip strength, or `n < 2`, and the CLI exits 2. The site cannot throw at its reader mid-typing, so `clampOpts()` bounds every field, writes the corrected value back into the box, and reports what it changed in the `#warnings` banner.

The two sets of limits are *not* identical, and that is worth knowing before you assume otherwise: the CLI rejects only what is nonsensical, while the site also imposes upper bounds it can keep a reader inside — `n` 2–30, start dose 0.1–64 mg, film length 1–200 mm, film strength 0.1–12 mg. `python3 taper.py --n 1000` runs; typing 1000 into the site clamps to 30 and says so.

---

## 4. The maths

### The ladder

One number does two jobs, which is the whole trick: **`n` is both the cut denominator and the cycle length in days.** Cut `1/n` off the piece each day, and after `n` days the saved slivers add up to exactly one whole piece.

| | |
|---|---|
| keep ratio | `r = 1 − 1/n` |
| strip at cycle *k* | `D_k = D₀ · r^(k−1)` |
| daily dose in that cycle | `daily = D · r` |
| daily sliver | `sliver = D / n` |
| days in the cycle | `hold_days` if set, else `n` |
| banked over the cycle | `days · sliver` — exactly `D`, one whole piece, when `days == n` |

`daily + sliver = D` exactly, which is why the dose splits without remainder.

Two closed forms let the tests check the simulation against algebra rather than against itself:

```
lifetime ceiling   Σ_{k≥1} days·D₀·r^k  =  days · D₀ · r/(1−r)  =  days · (n−1) · D₀
ingested after K   Σ_{k=1..K}           =  days · n · D₀ · r · (1 − r^K)
```

With the default cycle length (`days = n`) the ceiling is the familiar `n(n−1)·D₀` and the ingested form is `n²·D₀·r·(1 − r^K)`.

### Millimetres

Cutting along one axis only is what makes the geometry trivial: keep the full width, shorten the length, and **length fraction = dose fraction**.

```
piece_mm = film_mm × D / film_mg      the day's whole strip, across however many films
cut_mm   = piece_mm / n               the day's sliver
```

`film_mm` is the measured length of one film along the cut axis (22 mm on all four official strengths). `film_mg` is the strength being cut, chosen by `base_film_mg(start_mg)` — the smallest official size that holds the start dose, or 8 mg above 12 mg where none does — and overridable with `--film-strength` / the *Film strength you cut* input.

`piece_mm` is a **total for the day** and can exceed one film. Splitting it into real films is the job of the next section.

### Film layout — one day across several strips

A 32 mg start on 8 mg strips is four films a day. The arithmetic above does not care, but the person holding a razor does. `film_layout()` answers the only two questions that matter: **how many strips do I open, and where is the one cut?**

Picture the day's strip as films laid end to end. You take from the left; everything past the mark goes in the jar. So the only films worth opening are the ones the TAKE reaches:

```
take_films       whole films swallowed untouched, no cut
the marked film  TAKE cut_take_mm | SAVE cut_save_mm | already off
```

**One cut a day, on one film, always** — wherever the dose happens to land. There is no second marked film and no arrangement where the reader measures twice.

A film the take never reaches would be opened only to put it straight in the jar, so it is left in the box instead. `spare_mm` is the part of today's sliver sitting on those unopened films; it is zero whenever the day fits inside the films the take needs, which is every cycle of any run that fits on one film.

Worked through on a 32 mg start:

| Cycle | Strip | Take | Films opened | The cut |
|---|---|---|---|---|
| 1 | 32.00 mg (88.0 mm) | 73.3 mm | 4 | 3 whole, then mark the 4th at 7.3 mm |
| 2 | 26.67 mg (73.3 mm) | 61.1 mm | **3** | 2 whole, then mark the 3rd at 17.1 mm |
| 3 | 22.22 mg (61.1 mm) | 50.9 mm | 3 | 2 whole, then mark the 3rd at 6.9 mm |

Cycle 2 is the interesting one: the *strip* spans four films but the *take* only reaches into the third, so the fourth is never opened and 7.3 mm of the sliver is booked to `spare_mm`.

When the take lands exactly on a film boundary there is no marked film at all — 8 mg of 2 mg film at `n = 4` is three whole films and nothing to measure. Both front ends detect this (`cut_context()["no_cut"]`) and say so instead of drawing an empty bar.

The layout is exactly backward compatible: when the day fits on one film, `take_films` and `spare_mm` are zero, `cut_take_mm` is the old take and `cut_save_mm` the old cut. The one-film picture is a special case of the general one, not a separate code path.

> **Measuring the cut.** The mark is `cut_save_mm` in from the right of **the strip on the marked film**, not from the film's own right end. On any cycle with an already-off region those are different places, and using the film's end puts the cut millimetres wrong. `cut_context()` exposes this as `marked_piece_mm`; a matrix test asserts it is strictly less than the film length whenever an already-off region exists.

### Two automatic changes mid-run

Both are opt-out, both are flagged on the row that they fire on.

**The 2 mg switch.** When the strip you are cutting reaches `switch_at_mg` (2.25 by default), the ladder restarts on a fresh 2 mg film. A 2 mg film is a quarter the density of an 8 mg one, so the same dose is four times longer and the same cut four times more forgiving. It only fires while the resulting daily dose is still a step down — otherwise a low `--switch-at` would walk the dose back up. If it was wanted and could never fire, `switch_never_fired` says so rather than the run quietly staying on the big film.

**`n` below 3 mg.** Optional. Once the strip drops under 3 mg, switch to a different `n` — usually 10, so the back half drops 10% a cycle instead of 16.7%. Fires once.

### Illustrative models (display only, never in the ladder)

Two figures on the page are models rather than schedule arithmetic. Neither is passed to `buildSchedule`, and both are captioned as illustrations.

**The lag curve.** One-compartment, once-daily accumulation, expressed as the steady dose that would produce the level — never as a plasma concentration:

```
k     = ln2 / half_life_h
decay = e^(−k·24)
level ← level · decay + dose          once per day
eff    = level · (1 − decay)          the same level as a dose-equivalent mg
```

Seeded at steady state on the pre-taper dose (`level = D₀ / (1 − decay)`), because someone starting a taper is not starting the drug — seeding at zero drew a loading ramp through cycle 1 that nobody in this situation experiences. This is the picture behind the note *"you may not feel a drop until day 4 or 5"*.

**Cut error vs step size.** How much of one cycle's dose drop your cutting accuracy could swallow:

```
error_mg  = tolerance_mm × (film_mg / 22)
step_mg   = previous daily − this daily
plotted   = error_mg / step_mg × 100 %
```

Past 100% the error is bigger than the entire drop — you are no longer tapering, you are guessing. It is the quantitative version of the tool's own advice to move to 2 mg films.

---

## 5. Data model

One row per cycle, 24 fields, identical on both sides (camelCase in JS, snake_case in Python — `test_parity.js` maps between them automatically):

| Group | Fields |
|---|---|
| identity | `cycle`, `day_start`, `day_end`, `n`, `days` |
| doses | `film_mg`, `cut_from_mg`, `daily_mg`, `sliver_mg` |
| millimetres | `piece_mm`, `cut_mm` |
| film layout | `films_out`, `take_films`, `cut_take_mm`, `cut_save_mm`, `spare_mm` |
| running totals | `used_mg`, `cum_mg`, `cum_strips`, `banked_mg`, `cum_banked_mg` |
| flags | `switched_2mg`, `cut_warn`, `n_changed` |

`ScheduleResult` wraps the rows with the echoed inputs, the derived `r` / `ceiling_mg` / `base_film_mg`, nine summary figures filled in by `_fill_summary`, the 30-day `months` buckets, and two honesty flags — `truncated` (hit the 40-cycle cap before the target) and `switch_never_fired`.

**Summary fields default to 0 / None, not undefined.** An empty ladder still has to answer every question asked of it: an undefined `end_day` once turned `Math.max(endDay, 1)` into `NaN` and blanked the comparison chart's axis. Both sides mirror the same defaults and `test_parity.js` checks them on two deliberately-empty cases.

---

## 6. Rendering

### Two drawings, one list

`renderRuler` (schematic, "Cut mark") and `renderStripViz` (true size, "Life-size film") both draw the selected cycle, and both build their bars from the same `dayFilms(row, fullMm)` list — one entry per film you open, whole films first and the marked one last, so the run of bars reads as the day's strip laid end to end.

They answer different questions, though, and that is deliberate:

- **Cut mark** is always the schedule's own film strength. It is the instruction you follow.
- **Life-size** redraws the same day on whichever strength is selected in the size table, by re-running `filmLayout()` at that strength. A 12 mg film holds a day in fewer strips than an 8 mg one, so the bar count moves with the selection. It answers "what would this day look like on that film?"

`test_layout.js` checks both: the cut-mark panel must show exactly the row's `filmsOut` bars with one marked bar and one tick row, and the life-size panel must show the count the layout gives for the strength selected.

### Positioned-by-pixel elements

Several things are placed from measured pixels rather than by normal flow, and **this is the page's most frequent source of bugs**:

| Function | What it places |
|---|---|
| `pinRulerTickLabels()` | the tick captions under the cut-mark bar, treating the CSS-pinned `0` and `22.0 mm` as obstacles |
| `pinStripCutLabel()` | the "today's cut" caption over the cut line, widening its mat to fit |
| `fitBandLabels()` | steps each band's label down — full → short → nothing — checking **both** width and height |
| `fitCalCells()` | measures every calendar number and shrinks the ones that overflow their cell |

All four re-run on resize as well as on render, because a rotation leaves the old offsets describing the old width.

`fitCalCells` writes a `--fit` multiplier that the CSS applies on top of whichever breakpoint tier is active, rather than trying to out-specify four tiers of hardcoded font sizes.

### Charts

Eight SVG charts, built as strings by `renderCharts` and dropped into `#charts`. They share `plotBox()`, `svgOpen()`, `gridAndAxes()` and `evenTicks()`. Anything with `data-cycle` on it is click-to-select for free.

Chart colours are **baked into the SVG at render time**, so they cannot come from CSS variables directly. `readChartPalette()` reads the current theme's tokens into a module-level `C` at the top of every render. Hardcoding a colour there breaks the light theme and printing.

### Theming

Dark is the default, on bare `:root`. Every colour token must be declared in **all three** blocks or it is undefined in one of them:

```
:root                        dark  (the default)
:root[data-theme="light"]    light
@media print                 always light, whatever the screen theme
```

The one deliberate exception: **the film specimen keeps a fixed orange palette in both themes.** A real Suboxone film is orange, and recolouring it would misrepresent the product. Everything around it — the stage, the already-off hatching, the mark colour — themes normally.

### Dates

The calendar anchors every date to **UTC noon**. Parsing `yyyy-mm-dd` with `new Date(str)` or using local midnight both shift days across a DST boundary; noon has twelve hours of slack in either direction. `--start-date` on the CLI produces the same date ranges.

---

## 7. Tests

Three suites, three different things they can see. All three run in CI on every push and pull request.

```bash
python3 test_taper.py       # schedule maths — stdlib only, no browser
node test_parity.js         # index.html vs taper.py
node test_layout.js         # viewport sweep, 280px to 1920px
npm run test:all            # all three
```

The two Node suites share `test_browser.js`, which looks for a browser in `CHROMIUM_PATH`, then the Playwright caches (Linux and macOS), then an installed Chrome or Chromium. **If it finds none, both print `skipped` and exit 0** — a plain checkout without a browser should not fail the suite.

That skip is right locally and wrong in CI, where it would be a green tick over a page nobody tested, so the workflow has an explicit gate: after installing the browser it calls `findBrowser()` and fails the job if the answer is null. Note the skip only covers a *missing binary* — a browser that exists but fails to launch throws, and both suites exit 1.

### `test_taper.py` — 40 checks

Standard library, no I/O, runs in under half a second.

Named classes cover the closed forms against the simulation, the per-cycle invariants, that the daily dose never rises across a film switch, the published film geometry, the summary figures, and worked multi-film examples a reader can follow.

`TestMultiFilmMatrix` covers the *space* rather than examples: **720 ladders, 10,597 cycles** — start doses 1 to 32 mg against all four official strengths, `n` from 2 to 30, three film lengths, the 2 mg switch both ways — built once in `setUpClass` and walked by six property tests:

| Property | Why |
|---|---|
| nothing is lost between the films | the pieces must add back up to the day's take and save |
| milligrams still track millimetres | length fraction = dose fraction is the basis of the method |
| no mark runs off the end of a film | a mark past the strip is not a mark |
| exactly one film a day is ever cut | two marks means two measurements a day |
| you open exactly the films the dose needs | never one more; a film that would go straight to the jar stays in the box |
| the sliver is measured from the piece, not the film | the film's right end is elsewhere |

A seventh test checks **the shape of the coverage itself** — that the matrix really does produce days of 1 through 16 films, days needing a second cut film, and days with nothing to cut. A grid that quietly stopped generating multi-film days would otherwise pass everything above while testing nothing.

### `test_parity.js` — 671 schedules

The suite that keeps the site's promise true. It loads `index.html` in headless Chromium, reaches into `window.SASTaperInternals` (a frozen, read-only test surface exposed at the bottom of the IIFE — the page itself never uses it), and diffs against `taper.py`.

Two phases:

- **31 named cases** go through the CLI (`python3 taper.py --json`), so the argument plumbing is covered too. Start doses 0.1–64 mg, `n` 2–30, the switch both ways, stretched cycles, `n`-below-3, non-default lengths and strengths, clamp boundaries, empty ladders.
- **640 matrix cases** go straight at `build_schedule()` in one Python process — 1 to 32 mg × all four strengths × `n` 2–30, plus two non-default film lengths. **9,212 cycles** of layout fields, compared field by field.

Every one of the 24 row fields is compared, plus 9 summary figures, every 30-day month bucket, the n = 6/8/10 comparison table, and `base_film_mg` over 11 film sizes. Field naming is bridged automatically (`cutTakeMm` → `cut_take_mm`), so **a field added to one side and not the other fails the test** rather than being skipped.

The months and the comparison table were the last two things written twice and checked nowhere: `compareRows` only walks rows and `compareSummary` only walks scalars, so `monthly_usage()` and `compare_classic()` could have drifted from their JS twins in silence.

Like the Python matrix, it asserts the shape of its own coverage.

### `test_layout.js` — 472 viewport states

Committed because this class of bug had been found by hand and lost again four separate times. 14 widths from 280 px to 1920 px, both themes, several cycles, zoom extremes, calendar densities and measurement modes, plus fifteen reshaping input cases and a pass that redraws one day on each of the four film strengths.

Five failure modes at every state:

| Failure | Detected by |
|---|---|
| **overflow** — the page scrolls sideways | `scrollWidth > clientWidth` on the document |
| **overlap** — two pieces of text drawn on each other | pairwise rectangle intersection within each positioned group, 2 px slack |
| **clipping** — a box too small for its text | `scrollWidth`/`scrollHeight` vs `clientWidth`/`clientHeight` |
| **spill** — an absolute label escaping its container | bounding box against its parent's |
| **bar count** — a drawing showing a different day than it describes | one bar per film in each panel, against the layout for that panel's strength |

It also carries a short pass over **rendered figures no other suite can see** — the display maths layered on top of the schedule. The cutting-error chart must scale with the film-length input, the comparison heading must name the target actually used, and every chart must have an accessible name. Each of those three had been wrong.

Any console error or page error fails it too.

### CI

`.github/workflows/tests.yml` runs all three on push to `main`, on every pull request, and on manual dispatch. Roughly three minutes end to end.

Two things in it are load-bearing and worth not undoing:

- **No `--with-deps` on the Playwright install.** That flag runs `apt-get update` against the Azure Ubuntu mirrors on every run, and has hung for 10+ minutes when they are unhealthy. It buys nothing: the `ubuntu-latest` image already ships Chrome and Chromium, so the shared libraries Playwright's Chromium needs are installed. If that ever stops being true the browser fails to *launch*, which throws — it cannot become a silent pass.
- **`timeout-minutes`,** 15 on the job and 5 on the browser install. Without them a wedged step sits for the six-hour default.

The browser download is cached at `~/.cache/ms-playwright`, keyed on the two files that name the Playwright version.

### Making sure a test can fail

Every guard above was checked by injecting the fault it is meant to catch:

| Injected fault | Result |
|---|---|
| wrong `takeFilms` in the JS layout | 89 parity mismatches across all six layout fields |
| wrong layout for 2 mg film above 25 mg | 154 matrix mismatches |
| renderer draws one bar instead of all | 372 layout failures |
| life-size panel ignores the selected strength | bar-count mismatch at every strength but 8 mg |
| cutting-error chart hardcodes a 22 mm film | caught at 11 mm |
| charts lose their accessible names | 7 unnamed charts reported |
| `monthly_usage` drifts by 0.1% | 14,304 parity mismatches |
| `compareClassic` drifts by 2% on the target | 14 parity mismatches |
| 0.1% error in `keepRatio` | 1985 mismatches |

A guard that has never been seen to fail is not yet a guard.

---

## 8. Invariants

Things that are true today and that a change must keep true. Most are enforced by a test; the ones that are not are marked.

1. `index.html` is one file with no external requests. *(Not enforced — read the diff.)*
2. `taper.py` imports only the standard library. *(Not enforced.)*
3. `buildSchedule` and `build_schedule` produce identical rows. — `test_parity.js`
4. Display-only inputs never reach either schedule builder. — `test_parity.js`, indirectly: they are not in its input set
5. Every colour token exists in all three theme blocks. *(Not enforced — `test_layout.js` renders both screen themes, which catches most of it.)*
6. Nothing is lost between the films of one day. — `test_taper.py`
7. Exactly one film per day is ever cut. — `test_taper.py`
8. You open exactly the films the dose needs, never one more. — `test_taper.py`
9. Each drawing shows one bar per film it is describing. — `test_layout.js`
10. No text overlaps, clips or overflows from 280 px to 1920 px. — `test_layout.js`
11. Summary fields are 0/None on an empty ladder, never undefined. — `test_parity.js`
