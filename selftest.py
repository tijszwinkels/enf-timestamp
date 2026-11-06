#!/usr/bin/env python3
"""Self-test: synthesize a grid log and a hummy recording, then check the matcher finds the start.

No real data needed. Exits non-zero on failure.
"""
import datetime as dt, sys, tempfile, os
import numpy as np
from scipy.io import wavfile
import enf_match as em

rng = np.random.default_rng(1)
hours = 6
n = hours * 3600
# grid frequency: slowly wandering around 50 Hz (AR(1)-ish), ~20 mHz spread, 1 value/s
drift = np.zeros(n)
for i in range(1, n):
    drift[i] = 0.995 * drift[i - 1] + rng.normal(0, 0.002)
grid = 50 + drift
t0 = dt.datetime(2026, 1, 1, tzinfo=em.UTC)

true_start = 2 * 3600 + 1234  # seconds after t0
dur, sr = 600, 8000
f = np.repeat(grid[true_start:true_start + dur], sr)  # instantaneous grid frequency
phase = 2 * np.pi * np.cumsum(2 * f) / sr  # 100 Hz hum = 2nd harmonic
x = 0.02 * np.sin(phase) + rng.normal(0, 0.3, len(phase))  # weak hum in loud noise
wav = os.path.join(tempfile.mkdtemp(), "synthetic.wav")
wavfile.write(wav, sr, (x * 3000).astype(np.int16))

sr2, xx = em.load_audio(wav)
curve, db = em.track_harmonic(xx, sr2, 2)
r = em.match(curve - np.median(curve), t0, grid.copy(), 16.0)
err = (r["best_start"] - (t0 + dt.timedelta(seconds=true_start))).total_seconds()
print(f"line {db:.1f} dB, best corr {r['best_corr']:.3f}, runner-up {r['runner_up_corr']:.3f}, z {r['z']:.1f}, error {err:+.0f} s")
if abs(err) > 3:
    sys.exit("FAIL: start time off by more than 3 s")
print("OK")
