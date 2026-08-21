# Architecture

How SAS-Taper is put together: where it starts, what the formulas are, and what the tests are guarding.

For the rules you have to follow when changing it, see [CLAUDE.md](CLAUDE.md) and [CONTRIBUTING.md](CONTRIBUTING.md). For what the tool is *for*, see [README.md](README.md).

---

## 1. The shape of the thing

Two programs compute the same taper, in two languages, and the site tells people they agree:

```
index.html   the site, one self-contained file, no build, no network
taper.py     the CLI, standard library only
```

That duplication is deliberate. The site has to work offline from a double-clicked file, so it cannot import anything; the CLI has to run on a machine with nothing installed, so it cannot depend on Node. Neither can be generated from the other without a build step, and a build step would break the first constraint.

The cost is that **the ladder maths exists twice and can drift**, and it already did once. `test_parity.js` is the mechanism that keeps the promise honest: it runs both implementations over the same inputs and diffs every field. Everything else in this document is downstream of that one fact.

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
  const s = buildSchedule(...opts);   // THE maths. Everything below is display
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

`readOpts()` is where the display-only inputs are separated from the ones that reach the maths. `cutTolMm`, `halfLifeH` and `startDate` are read into `opts` but **never passed to `buildSchedule`**, which is what stops a chart control from silently moving the ladder and breaking parity.

`saveInputs(opts)` takes the already-read opts rather than re-reading. Re-reading would run `clampOpts` a second time against values it had just corrected, find nothing to fix, and wipe the clamp notices before the banner could show them.

The script is laid out in the order its header comment describes: constants and film specs, maths, input handling, renderers, chart infrastructure, wiring. The CSS carries matching `/* ---- ... ---- */` section markers.

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

The two sets of limits are *not* identical, and that is worth knowing before you assume otherwise. The CLI rejects only what is nonsensical, while the site also imposes upper bounds it can keep a reader inside: `n` 2-30, start dose 0.1-64 mg, film length 1-200 mm, film strength 0.1-12 mg. `python3 taper.py --n 1000` runs; typing 1000 into the site clamps to 30 and says so.

---

## 4. The maths

### The ladder

One number does two jobs, which is the whole trick: **`n` is both the cut denominator and the cycle length in days.** Cut `1/n` off the piece each day, and after `n` days the saved slivers add up to exactly one whole piece.

`1/n` **of what**, though, is the one real choice in the model, and it is the `cut_mode` input:

| | `geometric` (default) | `linear` (easier to cut) |
|---|---|---|
| the sliver | `D / n`, 1/n of the piece in hand | `D₀ / n`, 1/n of the **first** strip, fixed once |
| the cut in mm | shrinks with the dose | never changes |
| dose at cycle *k* | `D₀ · r^(k−1)` | `D₀ · (1 − (k−1)/n)` |
| each step | same percentage | same milligrams |
| where it ends | asymptotic, pick a target | zero, after exactly `n − 1` doses |
| cutting it | a new, smaller mark each cycle | one mark, measured once, reused every day |

Everything below is written for the geometric mode, and notes where linear differs.

| | |
|---|---|
| keep ratio | `r = 1 − 1/n` |
| strip at cycle *k* | `D_k = D₀ · r^(k−1)` |
| daily dose in that cycle | `daily = D · r` |
| daily sliver | `sliver = D / n` (geometric) or `D₀ / n` (linear, constant) |
| days in the cycle | `hold_days` if set, else `n` |
| banked over the cycle | `days · sliver`, exactly `D`, one whole piece, when `days == n` |

`daily + sliver = D` exactly, which is why the dose splits without remainder.

Closed forms let the tests check the simulation against algebra rather than against itself:

```
geometric
  lifetime ceiling   Σ_{k≥1} days·D₀·r^k  =  days · D₀ · r/(1−r)  =  days · (n−1) · D₀
  ingested after K   Σ_{k=1..K}           =  days · n · D₀ · r · (1 − r^K)

linear
  whole-run total    Σ_{k=1..n−1} days·D₀(1 − k/n)  =  days · D₀ · (n−1)/2
  ingested after K   days · D₀ · (K − K(K+1)/(2n))
```

With the default cycle length (`days = n`) the geometric ceiling is the familiar `n(n−1)·D₀` and its ingested form is `n²·D₀·r·(1 − r^K)`. The linear figure is not a ceiling at all but the actual total, because that run finishes: 8 mg at n = 6 is 120 mg over 30 days, against 425 mg over 66 days for the geometric run down to ~1 mg.

**`cut_mm` comes from the sliver, not from `piece_mm / n`.** The two are identical under geometric, where the sliver *is* the piece over n, but under linear the sliver is a fixed number of milligrams and the millimetres have to hold still with it. That constant mark is the entire point of the mode, and it is why linear is the easier one to cut: measure once, reuse it every day, and it never shrinks into the sub-millimetre range where a razor stops resolving.

### What linear mode switches off, and why

Two features exist to rescue the geometric mode from itself, and neither applies:

- **The 2 mg switch** exists because the geometric sliver eventually gets too thin to cut. A constant cut never does, so there is nothing to rescue.
- **`n below 3 mg`** changes `n` partway, which would change the one step the linear mode is defined by.

Both are ignored when `cut_mode == "linear"`, and both front ends say so rather than leaving a control looking active.

### Where the linear ladder stops

`daily = D − D₀/n` hits exactly zero at cycle `n`. A cycle of `n` days at 0 mg is not an instruction, so **the loop breaks before appending it** and `zero_day` reports the landing instead: the day after the last dosing cycle ends.

That break has one consequence worth knowing: it leaves the loop early, so `truncated` must be cleared explicitly. It is initialised `true` for `stop_mode == "reach"` and is otherwise only cleared where the target is met. `test_parity.js` caught exactly this. The JS side reported a completed linear run as truncated while Python did not, which is why `truncated` and `switch_never_fired` are now compared fields rather than assumed.

### The honest caveat

Equal milligrams are growing percentages. An 8 mg n = 6 linear run drops 20%, 25%, 33%, 50%, and the last cut is 100%, so the mode is at its steepest exactly where a taper is hardest, which is the opposite of what the rest of this tool argues for. That is not a defect in the arithmetic; it is the arithmetic. Both front ends compute those percentages from the built rows and show them, unprompted, whenever the mode is on.

### Millimetres

Cutting along one axis only is what makes the geometry trivial: keep the full width, shorten the length, and **length fraction = dose fraction**.

```
piece_mm = film_mm × D / film_mg      the day's whole strip, across however many films
cut_mm   = film_mm × sliver / film_mg the day's sliver
take_mm  = piece_mm − cut_mm          the dose as a length
save_mm  = film_mm − cut_take_mm      the rest of the marked film
```

`film_mm` is the measured length of one film along the cut axis (22 mm on all four official strengths). `film_mg` is the strength being cut, chosen by `base_film_mg(start_mg)`: the smallest official size that holds the start dose, or 8 mg above 12 mg where none does, and overridable with `--film-strength` / the *Film strength you cut* input.

`piece_mm` is a **total for the day** and can exceed one film. Splitting it into real films is the job of the next section.

#### Take and save, the pair the reader acts on

`piece_mm` and `cut_mm` describe the *ladder*: the piece you conceptually hold and the sliver the method shaves off it. Nobody keeps yesterday's offcut, though. In practice you open a fresh film every day and cut it down. `take_mm` and `save_mm` describe **that**, and they are what the schedule's tinted block shows:

```
take_mm + save_mm = films_out × film_mm      the film you actually opened
save_mg / film_mg = save_mm / film_mm        same proportion, other unit
```

So the save is not the sliver. It is the sliver *plus everything earlier cycles had already taken off*, because all of it comes off the same fresh film and all of it goes in the same jar. It grows every cycle, and:

```
delta_save_mm = save_mm(k) − save_mm(k−1) ≡ cut_mm(k)
```

The identity holds because `take(k−1)` is `piece(k)`: the difference of two "full minus take" figures is exactly this cycle's sliver. Two things break it, and both make "extra" meaningless rather than merely different. A **2 mg restart** puts a different film underneath, and a cycle that **drops a whole film** from the day changes how much film is opened at all. A day with **no cut** breaks it too, having nothing to compare. In all three `delta_save_mm` is `None` and the schedule, cards and calendar all show a dash. A no-cut cycle also leaves the baseline where it was, so the next real cut is compared with the last real cut rather than with zero.

The one reported case where the delta is *not* the sliver is the **first cut of a run**, where the baseline is still an empty jar and the delta is the whole save. Both front ends detect that (`delta == save`) and word it "the first cut of this strip" rather than "more than last cycle", which beside an identical SAVE figure would read as a mistake.

`banked_mg` is a different accounting and stays that way: it is the *ladder's* count of the sliver, `days × sliver`, exactly one whole piece per full cycle. That is the method's milestone and the buffer it promises, deliberately **not** a tally of every offcut a reader physically ends up holding, which depends on whether a big offcut can serve as a whole dose and is outside what this tool models. `save_mm` is what leaves the film in front of you today. Both are true, and the glossary says which is which rather than letting one stand in for the other.

#### Folding instead of measuring

The life-size panel has two modes and **folding is the default**, because halving a film is more reproducible by hand than measuring 15.28 mm of it. The choice is `vizMode`, persisted in `localStorage`. Load only acts on the *non-default* value, so flipping the default later moves everyone who never touched the buttons and leaves everyone who did where they put themselves.

`fraction_cut()` / `fractionCut()` approximate the marked film's take as whole cells of a folded grid: the long axis into `FRAC_LONG_DIVS` (1, 2, 3, 4, 8: three successive halvings stay reproducible over 22 mm), the short axis into `FRAC_SHORT_DIVS` (1, 2, 3, 4: at 12.8 mm an eighth is 1.6 mm and nobody judges that by eye).

The chosen piece is always `columns` whole columns plus `tab_cells` cells of the next one, so it is a rectangle or an L, never something scattered. That shape is what makes the cut count small:

| Shape | Cuts | Pieces |
|---|---|---|
| the whole film | 0 | 1 |
| whole columns only | 1 | 1 |
| part of the first column | 2 | 1 |
| columns + a tab in the last column | 2 | 2 |
| columns + a tab mid-film | 3 | 2 |

A tab that runs to the film's own edge needs no cut on that side, which is what makes 5/6 on a 3×2 grid two strokes rather than three.

Two things about the search are load-bearing:

- **A lengthwise cut costs more than a crosswise one.** Both are "one cut", but 12.8 mm guided by the film's own straight edge is not the same job as 22 mm freehand down the middle. Without that term a plain half comes out as `1×2`, the wrong instruction.
- **`tol_mg` caps the error, it does not add to the best one.** Pass the reader's own cutting tolerance: a fold inside it is no worse than the slip they would make with a rule, so the simplest of those wins. Written as `best + tol` the two compound and the chosen cut can land further out than the tolerance allows, which it did on the first pass.

The result is deterministic, same arguments and same cut, so the drawing never moves under a reader who has changed nothing. **`fold.html`** is a second shipped page explaining all of the above: the whole algorithm in one annotated block, then the same thing as seven live stages driven by a slider. The listing scrolls sideways rather than wrapping, with a Wrap button for readers who want the lines taken apart. It reimplements the search a third time, in the page, deliberately. It is an explainer, not the tool, and nothing doses off it. It is self-contained like `index.html` and the layout sweep checks that, plus that its links home still resolve, and that the glossary still names the listing. Stage 02's ladder doubles as a picker: 54 ticks, a `<select>` carrying the same 54 for the keyboard, and a comparison panel that draws whatever is picked next to the search's own choice. The panel itemises both difficulty scores from `SCORE_ROWS`, the single list `difficulty()` sums, so the number and the account of the number cannot drift; the sweep adds up the printed rows and checks they equal the printed total. It also names the one outcome that must never occur: a fold the search considered and could have had for fewer points than the one it chose. The sweep fails if that verdict ever renders, which makes the pool's difficulty-first sort a tested claim rather than a comment. `test_parity.js` sweeps 13,920 cases across six film sizes and four tolerances, because a search with a tie-break is exactly the kind of code that drifts between two implementations.

Every drawing states the error in milligrams. **An approximation whose size the reader cannot see is worse than no approximation**, and the panel refuses to imply otherwise.

In **linear mode the folds are exact at every cycle**. A constant step lands on `5/6, 2/3, 1/2, 1/3, 1/6`, so a linear taper needs no ruler at all. `TestFractionCut` asserts that for n = 4, 6 and 8.

### Film layout: one day across several strips

A 32 mg start on 8 mg strips is four films a day. The arithmetic above does not care, but the person holding a razor does. `film_layout()` answers the only two questions that matter: **how many strips do I open, and where is the one cut?**

Picture the day's strip as films laid end to end. You take from the left; everything past the mark goes in the jar. So the only films worth opening are the ones the TAKE reaches:

```
take_films       whole films swallowed untouched, no cut
the marked film  TAKE cut_take_mm | Δ SAVE cut_save_mm | already off
```

The last two regions of the marked film are both jarred. `cut_save_mm` is what this cycle newly shaves off, the already-off remainder is what earlier cycles had. Together they are `save_mm`, which is why the drawings label the middle band Δ SAVE rather than SAVE.

**One cut a day, on one film, always**, wherever the dose happens to land. There is no second marked film and no arrangement where the reader measures twice.

A film the take never reaches would be opened only to put it straight in the jar, so it is left in the box instead. `spare_mm` is the part of today's sliver sitting on those unopened films; it is zero whenever the day fits inside the films the take needs, which is every cycle of any run that fits on one film.

Worked through on a 32 mg start:

| Cycle | Strip | Take | Films opened | The cut |
|---|---|---|---|---|
| 1 | 32.00 mg (88.0 mm) | 73.3 mm | 4 | 3 whole, then mark the 4th at 7.3 mm |
| 2 | 26.67 mg (73.3 mm) | 61.1 mm | **3** | 2 whole, then mark the 3rd at 17.1 mm |
| 3 | 22.22 mg (61.1 mm) | 50.9 mm | 3 | 2 whole, then mark the 3rd at 6.9 mm |

Cycle 2 is the interesting one: the *strip* spans four films but the *take* only reaches into the third, so the fourth is never opened and 7.3 mm of the sliver is booked to `spare_mm`.

When the take lands exactly on a film boundary there is no marked film at all. 8 mg of 2 mg film at `n = 4` is three whole films and nothing to measure. Both front ends detect this (`cut_context()["no_cut"]`) and say so instead of drawing an empty bar.

The layout is exactly backward compatible: when the day fits on one film, `take_films` and `spare_mm` are zero, `cut_take_mm` is the old take and `cut_save_mm` the old cut. The one-film picture is a special case of the general one, not a separate code path.

> **Measuring the cut.** The mark is `cut_save_mm` in from the right of **the strip on the marked film**, not from the film's own right end. On any cycle with an already-off region those are different places, and using the film's end puts the cut millimetres wrong. `cut_context()` exposes this as `marked_piece_mm`; a matrix test asserts it is strictly less than the film length whenever an already-off region exists.

### Two automatic changes mid-run

Both are opt-out, both are flagged on the row that they fire on.

**The 2 mg switch.** When the strip you are cutting reaches `switch_at_mg` (2.25 by default), the ladder restarts on a fresh 2 mg film. A 2 mg film is a quarter the density of an 8 mg one, so the same dose is four times longer and the same cut four times more forgiving. It only fires while the resulting daily dose is still a step down. Otherwise a low `--switch-at` would walk the dose back up. If it was wanted and could never fire, `switch_never_fired` says so rather than the run quietly staying on the big film.

**`n` below 3 mg.** Optional. Once the strip drops under 3 mg, switch to a different `n`, usually 10, so the back half drops 10% a cycle instead of 16.7%. Fires once.

### Illustrative models (display only, never in the ladder)

Two figures on the page are models rather than schedule arithmetic. Neither is passed to `buildSchedule`, and both are captioned as illustrations.

**The lag curve.** One-compartment, once-daily accumulation, expressed as the steady dose that would produce the level, never as a plasma concentration:

```
k     = ln2 / half_life_h
decay = e^(−k·24)
level ← level · decay + dose          once per day
eff    = level · (1 − decay)          the same level as a dose-equivalent mg
```

In those units the recurrence is an exponential moving average, `eff(n) = decay·eff(n−1) + (1−decay)·dose(n)`. A single step from `D₀` to a new constant `D` has the closed form `eff(n) = D + (D₀ − D)·decay^n`: a drop leaves the curve above the new dose, a jump leaves it below, and a long half-life (`decay` close to 1) stays near `D₀` instead of hugging the ladder. `lagFromDoses` is the recurrence; `lagSeries` just expands each cycle into daily doses and calls it. Both are JS-only, exported on `SASTaperInternals` so `test_parity.js` can check the properties, and never passed to `buildSchedule`.

Seeded at steady state on the pre-taper dose (`level = D₀ / (1 − decay)`), because someone starting a taper is not starting the drug. Seeding at zero drew a loading ramp through cycle 1 that nobody in this situation experiences. This is the picture behind the note *"you may not feel a drop until day 4 or 5"*.

The half-life input is display-only and runs 0-2160 hours (90 days). 0 hides the curve. The old 80 h cap silently replaced 90 and 900 with 80, so a depot-scale value still hugged the doses. 2160 h is long enough to sketch a 60-day injection tail without letting a stray zero divide by `1 − decay`.

**Cut error vs step size.** How much of one cycle's dose drop your cutting accuracy could swallow:

```
error_mg  = tolerance_mm × (film_mg / 22)
step_mg   = previous daily − this daily
plotted   = error_mg / step_mg × 100 %
```

Past 100% the error is bigger than the entire drop. You are no longer tapering, you are guessing. It is the quantitative version of the tool's own advice to move to 2 mg films.

---

## 5. Data model

One row per cycle, 28 fields, identical on both sides (camelCase in JS, snake_case in Python; `test_parity.js` maps between them automatically):

| Group | Fields |
|---|---|
| identity | `cycle`, `day_start`, `day_end`, `n`, `days` |
| doses | `film_mg`, `cut_from_mg`, `daily_mg`, `sliver_mg` |
| millimetres | `piece_mm`, `cut_mm` |
| what you act on | `take_mm`, `save_mm`, `save_mg`, `delta_save_mm` (`None` where nothing is comparable) |
| film layout | `films_out`, `take_films`, `cut_take_mm`, `cut_save_mm`, `spare_mm` |
| running totals | `used_mg`, `sum_mg`, `sum_strips`, `banked_mg`, `sum_banked_mg` |
| flags | `switched_2mg`, `cut_warn`, `n_changed` |

`ScheduleResult` wraps the rows with the echoed inputs (including `cut_mode`), the derived `r` / `ceiling_mg` / `base_film_mg`, `zero_day` for a linear run that reaches it, ten summary figures filled in by `_fill_summary`, the 30-day `months` buckets, and two honesty flags: `truncated` (hit the 40-cycle cap before the target) and `switch_never_fired`.

**Summary fields default to 0 / None, not undefined.** An empty ladder still has to answer every question asked of it: an undefined `end_day` once turned `Math.max(endDay, 1)` into `NaN` and blanked the comparison chart's axis. Both sides mirror the same defaults and `test_parity.js` checks them on two deliberately-empty cases.

---

## 6. Rendering

### Two drawings, one list

`renderRuler` (schematic, "Cut mark") and `renderStripViz` (true size, "Life-size film") both draw the selected cycle, and both build their bars from the same `dayFilms(row, fullMm)` list, one entry per film you open, whole films first and the marked one last, so the run of bars reads as the day's strip laid end to end.

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
| `fitBandLabels()` | steps each band's label down, full to short to nothing, checking **both** width and height |
| `calMeasure()` | one cycle's cut as the three numbers a day cell can show (`save`, `take`, `delta`), with the mode picking which |
| `renderFoldViz()` | the life-size panel's folding mode: the chosen grid, the strokes, and the dose error in milligrams |
| `fold.html` | the explainer page, its own file and its own stylesheet, linked from the mode switch |
| `foldSvg()` | one folded film as SVG, sized in CSS mm like the flex bars beside it, not in pixels |
| `renderCalLegend()` | the worked day cell above the grid: one real day, its three lines named, and a swatch per cell state |
| `fitCalCells()` | measures every calendar number and shrinks the ones that overflow their cell |

All four re-run on resize as well as on render, because a rotation leaves the old offsets describing the old width.

`fitCalCells()` only works because `.cal-cell .mg` and `.cal-cell .cut` are `white-space: nowrap`. It compares `scrollWidth` with `clientWidth`, and a line allowed to wrap never overflows. It grows a fourth row and pushes the whole calendar taller instead. That is exactly what happened the moment units were added to the cell values.

Cells are far tighter than the window suggests: three month grids sit side by side, so a day is about **36-44 px wide however large the screen is**. Two things were dropped to make room for units there, both because something else on the page already says them:

- **The mode word.** "save 11.39 mm" wants 70 px in 36 px. The mode is named on the button, in the legend and in the key under the grid; "mm" is the only thing saying what the number is, so the word goes and the unit stays.
- **The ×N pill, when it is what does not fit.** "13.33 mg ×2" wants 48 px in the 44 px a two-strip run gets at 768 px. `fitCalCells()` adds `no-fx` to the panel and re-measures. ×N is constant across a whole cycle and is already on the schedule row, the cut mark, the day's tooltip and the key, and it is dropped from every cell at once, because a grid where some days carry ×2 and others do not is a lie about the days that do not. The 420 px tier drops it for the same reason; this decides by measurement instead of by a fixed width.

The legend is built from a real day of the current run, never from invented numbers: this is a tool people dose from, and a plausible-looking fabricated figure beside real ones is the kind of number the project rules forbid. Its swatches are the same custom properties the real cells use, so light, dark and print follow with nothing to keep in step, and the layout sweep asserts none of them computes to transparent, which is what a token missing from one theme block looks like.

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

The one deliberate exception: **the film specimen keeps a fixed orange palette in both themes.** A real Suboxone film is orange, and recolouring it would misrepresent the product. Everything around it themes normally: the stage, the already-off hatching, the mark colour.

### Dates

The calendar anchors every date to **UTC noon**. Parsing `yyyy-mm-dd` with `new Date(str)` or using local midnight both shift days across a DST boundary; noon has twelve hours of slack in either direction. `--start-date` on the CLI produces the same date ranges.

---

## 7. Tests

Three suites, three different things they can see. All three run in CI on every push and pull request.

```bash
python3 test_taper.py       # schedule maths, stdlib only, no browser
node test_parity.js         # index.html vs taper.py
node test_layout.js         # viewport sweep, 280px to 1920px
npm run test:all            # all three
```

The two Node suites share `test_browser.js`, which looks for a browser in `CHROMIUM_PATH`, then the Playwright caches (Linux and macOS), then an installed Chrome or Chromium. **If it finds none, both print `skipped` and exit 0**, because a plain checkout without a browser should not fail the suite.

That skip is right locally and wrong in CI, where it would be a green tick over a page nobody tested, so the workflow has an explicit gate: after installing the browser it calls `findBrowser()` and fails the job if the answer is null. Note the skip only covers a *missing binary*. A browser that exists but fails to launch throws, and both suites exit 1.

### `test_taper.py`: 71 tests, ~500,000 assertions

Standard library, no I/O, runs in about a second.

The test count is the misleading number here: most of these walk a matrix, so
one test method can make tens of thousands of assertions. The runner wraps
`TestCase`'s assert methods with a counter and prints the real total on the
last line, which is where the figure above comes from, so nobody has to remember
to update it.

Named classes cover the closed forms against the simulation, the per-cycle invariants, that the daily dose never rises across a film switch, the published film geometry, the summary figures, and worked multi-film examples a reader can follow.

`TestLinearCutMode` covers the second cut mode: the cut never changes in either unit, the dose falls in equal steps, it lands on zero after exactly `n − 1` of them, no cycle ever has a zero or negative dose, the closed form matches the simulation, it still stops at a target above zero, the percentage step grows every cycle, the two geometric rescues are switched off, the cut never goes thin where geometric would, and the default mode is untouched.

`TestMultiFilmMatrix` covers the *space* rather than examples: **1,440 ladders, 15,422 cycles**, covering start doses 1 to 32 mg against all four official strengths, `n` from 2 to 30, three film lengths, the 2 mg switch both ways, **both cut modes**, built once in `setUpClass` and walked by ten property tests:

| Property | Why |
|---|---|
| nothing is lost between the films | the pieces must add back up to the day's take and save |
| milligrams still track millimetres | length fraction = dose fraction is the basis of the method |
| no mark runs off the end of a film | a mark past the strip is not a mark |
| exactly one film a day is ever cut | two marks means two measurements a day |
| you open exactly the films the dose needs | never one more; a film that would go straight to the jar stays in the box |
| the sliver is measured from the piece, not the film | the film's right end is elsewhere |
| take and save partition the films you opened, in mm and mg | the tinted block promises nothing falls between them |
| Δ save is the sliver wherever it is reported, and never negative | the identity the column rests on |
| Δ save is blank for exactly the three stated reasons | a fourth, unnamed reason would be a column the reader cannot trust, and a stated reason the grid never reaches would be a claim with nothing behind it |
| the save grows on every cycle that reports a Δ | the thing the method is sold on |

`TestFractionCut` covers the folded-grid cut over the whole 0-1 range and every exact grid point: the piece really is the fraction it claims, the cut count matches the shape the drawing builds from, a zero tolerance takes the closest fraction available, a non-zero one caps the error rather than adding to it, extra slack is only ever spent on fewer cuts, a plain half comes out crosswise, the result is deterministic, the brief's six example fractions are all reachable exactly, and every cycle of a linear run is exact at n = 4, 6 and 8.

`TestTakeAndSave` covers the pair the reader acts on: take and save partition the film with nothing between them, the worked default by hand, linear mode saving the same extra every cycle while the total climbs by that step, and the three cases where `delta_save_mm` has to be `None`: a 2 mg restart, a cycle that drops a whole film, and a day that lands on a film boundary and saves nothing without moving the baseline for the next real cut.

An eleventh test checks **the shape of the coverage itself**: that the matrix really does produce days of 1 through 16 films, days needing a second cut film, and days with nothing to cut. A grid that quietly stopped generating multi-film days would otherwise pass everything above while testing nothing.

### `test_parity.js`: 1,323 schedules

The suite that keeps the site's promise true. It loads `index.html` in headless Chromium, reaches into `window.SASTaperInternals` (a frozen, read-only object the tests read, exposed at the bottom of the IIFE; the page itself never uses it), and diffs against `taper.py`.

Two phases:

- **43 named cases** go through the CLI (`python3 taper.py --json`), so the argument plumbing is covered too. Start doses 0.1-64 mg, `n` 2-30, the switch both ways, stretched cycles, `n`-below-3, non-default lengths and strengths, clamp boundaries, empty ladders.
- **1,280 matrix cases** go straight at `build_schedule()` in one Python process: 1-32 mg × all four strengths × `n` 2-30 × **both cut modes**, plus non-default film lengths. **13,567 cycles**, compared field by field.

Every one of the 28 row fields is compared, plus 9 summary figures, every 30-day month bucket, the n = 6/8/10 comparison table, and `base_film_mg` over 11 film sizes. That is **about 647,000 field comparisons**, which the suite counts as it goes and prints. `fractionCut()` gets its own sweep of 13,920 cases on top of the ladder, and the lag curve adds 2,342 checks of its own. Field naming is bridged automatically (`cutTakeMm` → `cut_take_mm`), so **a field added to one side and not the other fails the test** rather than being skipped.

The months and the comparison table were the last two things written twice and checked nowhere: `compareRows` only walks rows and `compareSummary` only walks scalars, so `monthly_usage()` and `compare_classic()` could have drifted from their JS twins in silence.

The lag curve is JS-only, so it is not in the field-by-field ladder diff. `test_parity.js` still checks it: the closed form of a step down, a step up and a washout, that a longer half-life stays higher, that 900 h does not hug the ladder on a default run, and that typing 900 is no longer clamped to 80.

Like the Python matrix, it asserts the shape of its own coverage.

### `test_layout.js`: 680 viewport states, 904 checks

Committed because this class of bug had been found by hand and lost again four separate times. 14 widths from 280 px to 1920 px, both themes, several cycles, zoom extremes, calendar densities and measurement modes, plus twenty-one reshaping input cases, a pass that redraws one day on each of the four film strengths, and a pass over the linear mode.

Five failure modes at every state:

| Failure | Detected by |
|---|---|
| **overflow**, the page scrolls sideways | `scrollWidth > clientWidth` on the document |
| **overlap**, two pieces of text drawn on each other | pairwise rectangle intersection within each positioned group, 2 px slack |
| **clipping**, a box too small for its text | `scrollWidth`/`scrollHeight` vs `clientWidth`/`clientHeight` |
| **spill**, an absolute label escaping its container | bounding box against its parent's |
| **bar count**, a drawing showing a different day than it describes | one bar per film in each panel, against the layout for that panel's strength |

`fold.html`'s algorithm listing scrolls sideways inside its own `<pre>` at every width, and **Wrap** is the opt-in. It is written as hard-wrapped 80-column text with its comments in an aligned second column, so soft-wrapping costs more than it saves: at 375 px, 108 of its 167 lines re-wrap, the `──` rules break into orphan stubs, and every continuation returns to column 0 where it reads as a new statement. The sweep checks the default at four widths, that each button flips the listing, that the scroller stays inside the `<pre>` instead of widening the page, that only the non-default value is stored, and that the restore lives in the `<head>`. That last one is read off the file, because by the time a test can evaluate anything both scripts have run and a before-paint restore is indistinguishable from an after-load one.

It also greps the glossary against the listing **in both directions**. Glossary → listing catches a table still teaching names the code has renamed; listing → glossary catches a name the search introduces that nobody ever defines. Only the first direction existed at first, and `parts_in_all`, the denominator of the whole fraction, sat undocumented behind it. Names match on word boundaries, so a row for `err` cannot be satisfied by the `error_mg` that replaced it.

The schedule's column tooltips get their own pass. They are `position: fixed` because the table sits in an `overflow-x` scroller that would clip anything parented to a `<th>`, and they are gated to mouse and keyboard: `pointerover` ignores non-mouse pointers, `focusin` requires `:focus-visible`. The sweep drives a real hover at two widths and asserts the tooltip appears inside the viewport, then opens a touch context and asserts a tap produces nothing. Touch readers get the twelve-entry glossary under the table instead, which is why that glossary exists rather than being decoration. One `COLUMN_DOC` list feeds four things: the heading, its unit, the tooltip and the glossary entry. They cannot disagree. Each entry is `[name, unit, key, meaning]`.

`key` marks the five columns the reader acts on, as one contiguous block: **Take mg / Take mm / Save mg / Save mm / Δ save mm**. They are tinted with an `inset` box-shadow rather than a `background`, because the row states (selected, 2 mg switch, thin sliver) set `td` backgrounds at higher specificity and would paint straight over a background. The sweep checks the tint survives on a switch row, that the tinted columns are those five and are adjacent, and that a unit never runs into its name in the DOM. A CSS margin looks right and still reads as "Save mm" run together aloud.

It also reads the claim the block is built on straight off the rendered table: **Save mm grows every cycle**, and **Δ save is the amount it grew**, skipping the cycles that show a dash, which is where the comparison is deliberately undefined. No other suite looks at the rendered numbers.

It also carries a short pass over **rendered figures no other suite can see**: the display maths layered on top of the schedule. The cutting-error chart must scale with the film-length input, the comparison heading must name the target actually used, and every chart must have an accessible name. Each of those three had been wrong.

Any console error or page error fails it too.

Before it looks for a browser it also scans the source for the punctuation tells the unslop pass removed: em dashes, en dashes, curly quotes and the ellipsis character. Compact numeric ranges have to stay hyphenated (`24-42 hours`); spelling the same range with the word "to" fails the scan.

### CI

`.github/workflows/tests.yml` runs all three on push to `main`, on every pull request, and on manual dispatch. Roughly three minutes end to end.

Two things in it are load-bearing and worth not undoing:

- **No `--with-deps` on the Playwright install.** That flag runs `apt-get update` against the Azure Ubuntu mirrors on every run, and has hung for 10+ minutes when they are unhealthy. It buys nothing: the `ubuntu-latest` image already ships Chrome and Chromium, so the shared libraries Playwright's Chromium needs are installed. If that ever stops being true the browser fails to *launch*, which throws. It cannot become a silent pass.
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
| linear cut derived from `piece_mm / n` again | `linear cut column is not constant: 3.67, 3.06, 2.44 ...` |
| 2 mg switch allowed to fire in linear mode | 2,840 parity mismatches |
| cutting-error chart hardcodes a 22 mm film | caught at 11 mm |
| charts lose their accessible names | 7 unnamed charts reported |
| `monthly_usage` drifts by 0.1% | 14,304 parity mismatches |
| `compareClassic` drifts by 2% on the target | 14 parity mismatches |
| 0.1% error in `keepRatio` | 1985 mismatches |

A guard that has never been seen to fail is not yet a guard.

---

## 8. Invariants

Things that are true today and that a change must keep true. Most are enforced by a test; the ones that are not are marked.

1. `index.html` is one file with no external requests. *(Not enforced; read the diff.)*
2. `taper.py` imports only the standard library. *(Not enforced.)*
3. `buildSchedule` and `build_schedule` produce identical rows. (`test_parity.js`)
4. Display-only inputs never reach either schedule builder. (`test_parity.js`, indirectly: they are not in its input) set
5. Every colour token exists in all three theme blocks. *(Not enforced, though `test_layout.js` renders both screen themes, which catches most of it.)*
6. Nothing is lost between the films of one day. (`test_taper.py`)
7. Exactly one film per day is ever cut. (`test_taper.py`)
8. You open exactly the films the dose needs, never one more. (`test_taper.py`)
9. Each drawing shows one bar per film it is describing. (`test_layout.js`)
10. No text overlaps, clips or overflows from 280 px to 1920 px. (`test_layout.js`)
11. Summary fields are 0/None on an empty ladder, never undefined. (`test_parity.js`)
12. A linear cut is the same size in every cycle, in mg and in mm. (`test_taper.py`, and `test_layout.js` reads it off the rendered table)
13. No cycle ever carries a zero or negative dose. (`test_taper.py`)
14. The schedule's column tooltips never appear on a touch device. (`test_layout.js`)
