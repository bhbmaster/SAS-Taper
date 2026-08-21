# Contributing

Thanks for looking. This is a small project with an unusual constraint or two, worth reading before you open a pull request.

[ARCHITECTURE.md](ARCHITECTURE.md) is the map: entry points, the formulas, the data model, and what each test suite can see. [CLAUDE.md](CLAUDE.md) is the same ground as a pre-flight checklist.

## The one rule that matters

**The taper maths exists twice**, in `buildSchedule()` in `index.html` and `build_schedule()` in `taper.py`, and the site tells people the two agree. If you change one, change the other, and run `node test_parity.js` to prove it. That test exists precisely because the two had already drifted once.

## Constraints

- **`index.html` stays one self-contained file.** All CSS and JS inline, no build step, no external requests. People open it from disk, offline. A CDN link or a bundler would break that. The same is true of `fold.html` and `lag.html`.
- **`taper.py` stays standard-library only.** No pip installs.
- **Colours go in all three theme blocks**: bare `:root` (dark, the default), `:root[data-theme="light"]`, and the `@media print` block. Miss one and it is undefined in that mode.
- **Chart colours are read through `readChartPalette()`**, not hardcoded, because they get baked into the SVG at render time.
- **The film drawing keeps its fixed orange palette in both themes.** A real Suboxone film is orange; recolouring it would misrepresent the product. Everything around it themes normally.

## Running the tests

```bash
python3 test_taper.py      # schedule maths, stdlib only
node test_parity.js        # index.html vs taper.py, see README for setup
node test_layout.js        # viewport sweep for overflow, overlap and clipping
```

All three run in CI on every pull request.

Each one prints how much it actually checked on its last line: assertions, field comparisons, viewport states. Those are the figures the README quotes, so if you change coverage, read the new numbers off a run rather than editing them by hand.

`test_layout.js` is the one to remember when touching CSS or anything that positions text by measured pixels. This page's most frequent bug by far has been text colliding or overflowing at some viewport width nobody checked, and it is invisible to the other two suites.

## Health content

This is a medical-adjacent tool that people may act on. Two things follow:

- **Do not add numbers the tool cannot stand behind.** If a figure is illustrative, the caption has to say so. See the lag curve, which is plotted in dose-equivalent milligrams and never as a plasma concentration.
- **Keep "not medical advice" prominent.** It is the first thing on the page for a reason.

## Style

Match the surrounding code. No formatter is enforced; `.editorconfig` covers whitespace. Commit messages describe what changed and why, in prose.
