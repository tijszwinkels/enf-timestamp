# enf-timestamp

Find out **when** an audio recording was made from the mains hum in it.

The power grid's frequency is not exactly 50 Hz (60 Hz in the Americas). It wanders by a few
hundredths of a hertz from second to second, and a whole synchronous grid wanders together
(Continental Europe is one grid from Portugal to Turkey). Transformers, motors, lamps and
plugged-in recorders put that wobble into recordings as a faint hum at 100 Hz (twice the grid
frequency, acoustic) or 50 Hz (electrical pickup). Match the hum against a log of the grid
frequency and you get a timestamp. This is called *electric network frequency (ENF) analysis*;
forensic labs have used it for years.

These are small, readable scripts from a home experiment, explained in the video
[The hidden timestamp in (almost) any audio recording](https://youtu.be/bi7EwMiDQTQ).

## What's here

| Script | What it does |
|---|---|
| `hum_check.py` | Shows how strong the hum lines are, per 30 s. Run this first: no line, no timestamp. |
| `gridradar_logger.py` (+ `systemd/`) | Builds your own 1-second archive of the Continental-European grid frequency from [Gridradar](https://gridradar.net)'s free API. |
| `enf_match.py` | Extracts the hum curve from a recording and slides it along the grid log (FFT-based; days of data in seconds). Reports the best start time, the runner-up, a z-score and a verdict. |
| `selftest.py` | Synthetic end-to-end test (no real data needed). |

## Quick start

```bash
pip install -r requirements.txt        # numpy, scipy; ffmpeg for non-WAV input

# 1. Is there hum in the recording?
python hum_check.py recording.m4a

# 2. Collect grid data (needed BEFORE the recording you want to date; see below)
#    Put your Gridradar token in ~/.config/gridradar/token, then run periodically:
python gridradar_logger.py              # appends to ~/.local/share/gridradar/YYYY-MM-DD.csv

# 3. Match: use the harmonic that hum_check showed as strong (2 = 100 Hz, 1 = 50 Hz)
python enf_match.py recording.m4a ~/.local/share/gridradar/2026-11-*.csv --harmonics 2
```

Output looks like this (real run, laptop recording, 36 h of grid data searched):

```
recording: 10.2 min
  100 Hz line: median 9.6 dB above band median, curve std 32 mHz
searched 129849 candidate start times (36.1 h of reference)
best match : 2026-11-04 12:35:23 UTC  corr 0.478
runner-up  : 2026-11-05 10:25:20 UTC  corr 0.309
z-score 5.0, margin 0.169 -> CONFIDENT
true start : 2026-11-04 12:35:17 UTC  error +5.9 s
```

The verdict is deliberately strict: **CONFIDENT** only if the best match stands out
(z ≥ 4) *and* beats the runner-up by at least 0.1 in correlation. `--start` is only used to
print the error when you already know the answer.

## Grid data

The matcher needs a log of the grid frequency, one value per second, as CSV rows `utc,hz`.
For Continental Europe, Gridradar's free API gives 1-second data with a ~15 minute delay,
but only for the last hour, and **each request returns only the data since your previous
request with that token**. So run the logger from one place on a schedule (the systemd
timer in `systemd/` runs it every 30 minutes) and keep the files. A test request from
another machine silently "uses up" that stretch of data. Check Gridradar's terms before
using or sharing the data; this repo contains none.

For Great Britain, NESO publishes historic 1-second frequency data openly.

## What worked (and what didn't)

From the experiment in the video, all blind (the start time was hidden from the analysis):

| Recording | Hum | Result |
|---|---|---|
| Laptop mic, something humming in the house | strong 100 Hz line (~20 dB) | right start time, **6 s off**, z 5 over 36 h of data |
| Laptop mic, quiet room | weak, fading | no match |
| Phone voice memo on battery (3×) | nothing usable | no match |
| Phone voice memo **on its charger** (2×) | steady 50 Hz line (~9–17 dB) | **right minute** both times, but weak margin (z 2–3, "not confident") |

Things to know:
- You need something that hums: fridges, fans, pumps, transformers, plugged-in recorders.
  Phones on battery mostly hear nothing, and their noise suppression removes steady hum.
- The correlation peak is broad (a few seconds), and part of the remaining offset is probably
  a fixed timestamp convention in the reference data.
- Longer recordings and stronger hum give clearer peaks.
- ENF tells you **when** and **which grid**, not where within a grid. Research on intra-grid
  location reaches a few dozen km at best, with clean power-outlet data
  ([arXiv:2105.00668](https://arxiv.org/abs/2105.00668)).
- Edits show up too: a cut makes the hum curve jump, so it no longer matches one continuous
  stretch of grid history.

## How it works

1. Band-pass around the chosen harmonic of the nominal frequency.
2. Every second, take a 16 s Hann window, zero-padded FFT, and find the peak within
   ±0.1 Hz × harmonic (quadratic interpolation); divide by the harmonic number.
3. Smooth the grid log with the same 16 s window.
4. Pearson correlation of the hum curve against every possible start time, computed with
   FFT convolution; windows with missing grid data are skipped.

## Related

- colsto, [I discovered a sound that leaks your exact location](https://www.youtube.com/watch?v=UytYrhYLOKI):
  matches aircraft Doppler curves against flight data, which needs the recording time. ENF can supply it.
- The Register (2010), [the Metropolitan Police lab's mains-hum recordings](https://www.theregister.com/2010/06/01/enf_met_police/).

## License

MIT
