# enf-timestamp

Find out **when** an audio recording was made, from the mains hum in it.

The grid frequency isn't exactly 50 Hz (60 Hz in the Americas): it wanders by a few hundredths
of a hertz every second, and a whole grid wanders together. Transformers, motors and plugged-in
recorders put that wobble into recordings as a faint hum. Match the hum against a log of the grid
frequency and you get a timestamp. This is *electric network frequency (ENF) analysis*.

Video: [The hidden timestamp in (almost) any audio recording](https://youtu.be/bi7EwMiDQTQ)

## Quick start

```bash
pip install -r requirements.txt   # numpy, scipy (+ ffmpeg for non-WAV audio)

python hum_check.py recording.m4a                    # 1. is there a hum line?
python gridradar_logger.py                           # 2. log grid data (run every 30 min)
python enf_match.py recording.m4a ~/.local/share/gridradar/*.csv --harmonics 2   # 3. match
```

```
best match : 2026-11-04 12:35:23 UTC  corr 0.478
runner-up  : 2026-11-05 10:25:20 UTC  corr 0.309
z-score 5.0, margin 0.169 -> CONFIDENT
true start : 2026-11-04 12:35:17 UTC  error +5.9 s
```

Use `--harmonics 2` for an acoustic 100 Hz hum, `1` for 50 Hz electrical pickup (whichever
`hum_check.py` shows as strong); `--nominal 60` outside Europe. The verdict is strict:
CONFIDENT only when the match stands out (z ≥ 4) and beats the runner-up by ≥ 0.1.

## Grid data

`gridradar_logger.py` builds a 1-second archive of the Continental-European grid from
[Gridradar](https://gridradar.net)'s free API (token in `~/.config/gridradar/token`; a systemd
timer is in `systemd/`). The free API only returns the last hour, and **each request returns only
the data since your previous request**, so log from one place and keep the files. You need the
log covering the time of the recording. Check Gridradar's terms; this repo contains no data.

## Does it work?

Blind tests, start time hidden from the analysis:

| Recording | Result |
|---|---|
| Laptop mic, something humming nearby (100 Hz line) | **6 s off**, searching 36 h of grid data |
| Phone on its charger (50 Hz line) | right minute, twice, but weak margin |
| Phone on battery / quiet room | nothing usable |

You need something that hums. ENF tells you *when* and *which grid*, not where within a grid.

## Files

`hum_check.py` hum line strength per 30 s · `enf_match.py` extract + FFT sliding correlation ·
`gridradar_logger.py` grid archive · `selftest.py` synthetic end-to-end test

MIT license
