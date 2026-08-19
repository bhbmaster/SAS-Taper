# CLAUDE.md

Working notes for anyone — human or agent — changing this repo.

Read [ARCHITECTURE.md](ARCHITECTURE.md) first if you do not already know how the two implementations fit together. [CONTRIBUTING.md](CONTRIBUTING.md) has the project's own house rules; this file is the checklist.

---

## Before you finish any change

**1. The maths lives in two files. Change one, change the other.**

`buildSchedule()` in `index.html` and `build_schedule()` in `taper.py` must produce identical rows. The site says so in its footer. They have drifted before.

If you add a field to a `CycleRow`, add it on both sides — `test_parity.js` compares every field of the JS row against the snake_case equivalent in the Python one, so a field on one side only is a failure, not a silent pass. Same for `ScheduleResult` summary fields and their empty-ladder defaults.

Display-only values (`cutTolMm`, `halfLifeH`, `startDate`) are read into `opts` but must **never** be passed to `buildSchedule`. That is what stops a chart control from moving the ladder.

**2. Run all three suites. All three, not the fast one.**

```bash
python3 test_taper.py       # maths — stdlib, sub-second
node test_parity.js         # index.html vs taper.py — ~10s
node test_layout.js         # viewport sweep — ~2 min
npm run test:all            # all three
```

Each sees something the others cannot:

- `test_taper.py` catches wrong arithmetic.
- `test_parity.js` catches the two implementations disagreeing.
- `test_layout.js` catches text colliding, clipping or overflowing at a width nobody looked at. **This is the most frequent bug in this repo.** Run it after touching any CSS, any label, any measured-pixel positioning, or anything that changes how much text goes in a box.

Without a browser the two Node suites print `skipped` and exit 0. That is deliberate for a bare checkout — but if you are changing the page, a `skipped` is not a pass. Get a browser.

**3. Add a test for what you changed, and prove it can fail.**

A guard that has never been observed failing is not yet a guard. Inject the fault it is supposed to catch, watch the suite go red, then revert the injection. The PR history has four worked examples of this.

Prefer properties over fixtures for anything with a range of inputs. `TestMultiFilmMatrix` walks 720 ladders and asserts six properties per cycle; that has found real bugs that hand-picked cases missed twice now. When you add a matrix, also assert **the shape of its own coverage**, so it fails rather than quietly stops covering the interesting cases.

**4. Update every doc the change touches.**

Docs in this repo carry live numbers, and stale numbers are worse than none:

| File | Update it when |
|---|---|
| `README.md` | behaviour, CLI flags, inputs, or any test count / schedule count / viewport-state count changes |
| `ARCHITECTURE.md` | structure, formulas, entry points, data model, or what a suite covers changes |
| `CLAUDE.md` | the rules themselves change |
| `CONTRIBUTING.md` | a constraint changes |
| `index.html` — the "What each input does" list | you add, remove or re-scope an input |
| `taper.py` — `HOW_TO` / `NOTES` | the same, or the daily ritual changes |

If you change what the tool does, the site's own instructions are part of the change, not follow-up work.

**5. Check the default page did not move.**

Most changes should leave a plain 8 mg run byte-identical. Diff the rendered text of the panels before and after against `main`, and diff `python3 taper.py` output too. If something moved, either it was intended and you can say why, or it is a regression.

---

## Constraints that are easy to break by accident

- **`index.html` stays one self-contained file.** All CSS and JS inline, no external requests, no build step. People open it from disk, offline. A CDN link or a bundler breaks that.
- **`taper.py` stays standard-library only.** No pip installs, and `test_taper.py` likewise.
- **Every colour token goes in all three theme blocks** — bare `:root` (dark, the default), `:root[data-theme="light"]`, and `@media print`. Miss one and it is undefined in that mode.
- **Chart colours come from `readChartPalette()`**, never hardcoded. They are baked into the SVG at render time, so a CSS variable in an SVG attribute does not resolve.
- **The film specimen keeps its fixed orange palette in both themes.** A real Suboxone film is orange. Everything around it themes normally.
- **Dates anchor to UTC noon.** `new Date("2026-03-01")` and local midnight both shift days across a DST boundary.
- **"Save" is the film in front of you; "sliver" and "banked" are the ladder.** `save_mm` / `save_mg` are everything right of the take mark on a fresh film — the sliver *plus* what earlier cycles had already taken off — and `delta_save_mm` is how much more that is than last cycle. `sliver_mg` and `banked_mg` are the method's own accounting and are deliberately smaller. Do not "fix" one to match the other; they answer different questions and both are checked.
- **`delta_save_mm` is `None` in three cases, not zero**: a 2 mg restart, a cycle that drops a whole film from the day, and a day with no cut. Each one makes "extra saved" a comparison against a different thing. Every surface renders those as a dash.
- **Both drawings build from the same `dayFilms()` list.** Two panels deriving the day separately is how they end up showing different days.

---

## This is a medical-adjacent tool

People may act on what it says. Two things follow, and they are not negotiable:

- **Do not add a number the tool cannot stand behind.** If a figure is illustrative, its caption must say so — see the lag curve, which is plotted in dose-equivalent milligrams and never as a plasma concentration.
- **Keep "not medical advice" prominent.** It is the first thing on the page for a reason.

A wrong cut instruction is a dosing error, not a cosmetic bug. When you change anything about where a mark falls, work an example by hand and check the number.

---

## Git

- Branch, commit, push. Do not commit to `main`.
- One focused concern per pull request; the repo squash-merges.
- Commit messages are prose: what changed and why, not a list of files.
- Do not open a pull request unless asked to.
