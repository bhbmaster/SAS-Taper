# SAS-Taper

**SAS** means **save-a-sliver**.

A geometric buprenorphine (Suboxone) film-taper calculator. **Not medical advice.** Bring the schedule to your prescriber before day 1.

Source: [github.com/bhbmaster/SAS-Taper](https://github.com/bhbmaster/SAS-Taper)  
Live site: [bhbmaster.github.io/SAS-Taper](https://bhbmaster.github.io/SAS-Taper/)

Each day you cut `1/n` off the current piece, **save** the short right sliver, and **take** the long left piece. After `n` days the save jar holds one full piece — a buffer, not extra daily dose. Next cycle the new “whole strip” is `dose × (1 − 1/n)`.

Default: start 8 mg, **n = 6** (16.7% every 6 days), switch to 2 mg films around 2.2 mg.

## Why save-a-sliver

The demanding part of a taper is often not the milligrams but the sense of getting less. SAS frames each day’s remaining piece as a complete strip — the dose you have — while the cut-off sliver leaves the daily ritual.

People tend to work with what is in hand. Surplus that stays in view is easier to use; once the sliver is saved, it is no longer part of today’s dose. The bank is a safety net if you need to step back up, not a second supply for the same day.

## Site

Open the calculator at **[bhbmaster.github.io/SAS-Taper](https://bhbmaster.github.io/SAS-Taper/)**, or open `index.html` in a browser. Measure your film **length only**, put that in the inputs, and the schedule / cut marks / graphs update live. Click a cycle for that day’s ruler (TAKE left, SAVE right). Print it for your prescriber.

## CLI

```bash
python3 taper.py
python3 taper.py --compare
python3 taper.py --cycle 6
python3 taper.py --n 10 --no-switch-2mg
python3 test_taper.py          # math checks
```

No extra packages. Python 3.11 is fine. Same math as the site. Cut marks are a full unused film: TAKE left, SAVE, then the already-off remainder. `--cycle N` prints only that cycle’s cut with the extra note. `--stop-mode above` matches the classic n=6/8/10 comparison (last cycle still strictly above target).

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

