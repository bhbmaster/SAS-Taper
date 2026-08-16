# SAS-Taper

**SAS** means **save-a-sliver**.

A geometric buprenorphine (Suboxone) film-taper calculator. **Not medical advice.** Bring the schedule to your prescriber before day 1.

Source: [github.com/bhbmaster/SAS-Taper](https://github.com/bhbmaster/SAS-Taper)

Each day you cut `1/n` off the current piece, **save** the short right sliver, and **take** the long left piece. After `n` days the save jar holds one full piece — a buffer, not extra daily dose. Next cycle the new “whole strip” is `dose × (1 − 1/n)`.

Default: start 8 mg, **n = 6** (16.7% every 6 days), switch to 2 mg films around 2.2 mg.

## Why save-a-sliver

The demanding part of a taper is often not the milligrams but the sense of getting less. SAS frames each day’s remaining piece as a complete strip — the dose you have — while the cut-off sliver leaves the daily ritual.

People tend to work with what is in hand. Surplus that stays in view is easier to use; once the sliver is saved, it is no longer part of today’s dose. The bank is a safety net if you need to step back up, not a second supply for the same day.

## Site

Open `index.html` in a browser, or use the GitHub Pages site if enabled. Measure your film **length only**, put that in the inputs, and the schedule / cut marks / graphs update live. Click a cycle for that day’s ruler (TAKE left, SAVE right). Print it for your prescriber.

## CLI

```bash
python3 taper.py
python3 taper.py --compare
python3 taper.py --n 10 --no-switch-2mg
```

No extra packages. Python 3.11 is fine.

## Method (every day of a cycle)

1. Start with the current “whole strip” (cycle 1: a full 8 mg film).
2. Keep full width; cut along length only. Mark, then cut with a razor, not scissors.
3. Cut `1/n` off the **right** end. Save that sliver. Take the long left piece. Once daily.
4. After `n` days the save jar holds one full piece. Do not use the bank as extra daily dose or the taper never drops.
5. Next cycle, the leftover size is the new whole strip. Repeat to the target (default 1 mg).

Hold a cycle if cravings spike, sleep goes, or you are restless and sweating. When the sliver is under ~1 mm, switch to 2 mg films. Lock up saved pieces (dangerous to kids and pets). Ask the prescriber to step quantity down with the dose.
