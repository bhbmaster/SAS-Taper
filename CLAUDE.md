# CLAUDE.md

Working notes for anyone — human or agent — changing this repo.

Read [ARCHITECTURE.md](ARCHITECTURE.md) first if you do not already know how the two front ends fit together, and how the maths gets from one to the other. [CONTRIBUTING.md](CONTRIBUTING.md) has the project's own house rules; this file is the checklist.

---

## Before you finish any change

**1. The maths lives in one file. Change it there, then regenerate.**

Everything between `# --- CORE BEGIN ---` and `# --- CORE END ---` in `taper.py` is the only copy of the ladder. `gen_core.py` translates it into the block in `index.html` between `/* ===== GENERATED CORE ... */` markers:

```bash
python3 gen_core.py          # after any change inside the core markers
python3 gen_core.py --check   # what CI runs — fails on a stale or hand-edited block
```

**Never hand-edit the generated block.** `--check` fails on it, `node test_parity.js` fails on it, and `test_taper.py` fails on it. Add a `CycleRow` field in Python and the site gets it for free; you no longer add it twice.

`gen_core.py` accepts a deliberately small subset of Python and refuses the rest by file and line rather than guessing. If it stops you, either write it another way or teach it the construct **and add a case to `TestCoreGenerator`**. Four differences it exists to police, all of which have bitten:

- **truthiness** — `[]` is falsy in Python and *truthy* in JavaScript. A bare value in a boolean position is rejected unless it is known to be a number or a bool, so write `len(rows) == 0`, not `not rows`.
- **`int()` is `Math.trunc`, `//` is `Math.floor`.** They only agree on positive operands, and the core's `//` sites only ever see positives — so `test_parity.js` will *not* catch a mix-up here. `TestCoreGenerator` is what does.
- **function scope vs block scope** — Python scopes a local to the whole function, `let` scopes it to its block. Every local is hoisted to the top of the function for that reason. `test_parity.js` evaluates the block in strict mode, where the mistake throws.
- **naming** — snake_case becomes camelCase, including dict keys. Five names are overridden by hand in `NAME_OVERRIDES` because the display code already reads them; the table is validated against `taper.py` on every run.

`cut_context()`/`kit_line()` in `taper.py` and `dayFilms()` in `index.html` are **not** in the core and are still written twice. They shape the same day for two different media. Nothing checks them against each other.

Display-only values (`cutTolMm`, `halfLifeH`, `startDate`) are read into `opts` but must **never** reach the maths. The hand-written adapter under the generated block is the only place `opts` meets it — that is what stops a chart control from moving the ladder.

**2. Run all three suites. All three, not the fast one.**

```bash
python3 test_taper.py       # maths + the translator — stdlib, sub-second
node test_parity.js         # generated block vs taper.py — ~8s, no browser
node test_layout.js         # viewport sweep — ~2 min, needs Chromium
npm run test:all            # all three
```

Each sees something the others cannot:

- `test_taper.py` catches wrong arithmetic, and `TestCoreGenerator` in it catches the translator mistranslating.
- `test_parity.js` catches the generated block not computing what `taper.py` computes. It needs no browser: it lifts the block out of `index.html` and runs it in Node.
- `test_layout.js` catches text colliding, clipping or overflowing at a width nobody looked at. **This is the most frequent bug in this repo.** Run it after touching any CSS, any label, any measured-pixel positioning, or anything that changes how much text goes in a box.

Without a browser `test_layout.js` prints `skipped` and exits 0. That is deliberate for a bare checkout — but if you are changing the page, a `skipped` is not a pass. Get a browser.

**3. Add a test for what you changed, and prove it can fail.**

A guard that has never been observed failing is not yet a guard. Inject the fault it is supposed to catch, watch the suite go red, then revert the injection. The PR history has four worked examples of this.

Prefer properties over fixtures for anything with a range of inputs. `TestMultiFilmMatrix` walks 1,440 ladders and asserts ten properties per cycle; that has found real bugs that hand-picked cases missed twice now. When you add a matrix, also assert **the shape of its own coverage**, so it fails rather than quietly stops covering the interesting cases — and, where the code has named reasons for doing something (the three that blank `delta_save_mm`), assert that each named reason is actually reached.

Each suite prints how much it checked, not just how many tests ran: assertions for `test_taper.py`, field comparisons for `test_parity.js`, states and checks for `test_layout.js`. Those totals are the numbers the README quotes, so read them off a run rather than guessing.

**4. Update every doc the change touches.**

Docs in this repo carry live numbers, and stale numbers are worse than none:

| File | Update it when |
|---|---|
| `README.md` | behaviour, CLI flags, inputs, or any test count / schedule count / viewport-state count changes |
| `ARCHITECTURE.md` | structure, formulas, entry points, data model, or what a suite covers changes |
| `CLAUDE.md` | the rules themselves change |
| `CONTRIBUTING.md` | a constraint changes |
| `gen_core.py` — its docstring | the accepted subset or one of the four language differences changes |
| `index.html` — the "What each input does" list | you add, remove or re-scope an input |
| `taper.py` — `HOW_TO` / `NOTES` | the same, or the daily ritual changes |

If you change what the tool does, the site's own instructions are part of the change, not follow-up work.

**5. Check the default page did not move.**

Most changes should leave a plain 8 mg run byte-identical. Diff the rendered text of the panels before and after against `main`, and diff `python3 taper.py` output too. If something moved, either it was intended and you can say why, or it is a regression.

---

## Constraints that are easy to break by accident

- **`index.html` stays one self-contained file.** All CSS and JS inline, no external requests, nothing for the reader to build. People open it from disk, offline. A CDN link or a bundler breaks that. `gen_core.py` runs before the commit, never at page load — the file in the repo is the file that works.
- **`taper.py` stays standard-library only.** No pip installs, and `gen_core.py` and `test_taper.py` likewise. `gen_core.py` uses `ast` and `tokenize`, both stdlib.
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
