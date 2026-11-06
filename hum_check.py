#!/usr/bin/env python3
"""Quick check: is there a usable mains-hum line in this recording?

Prints the line strength (dB above the surrounding noise) at the first harmonics of the
grid frequency, for every 30 s of the recording. A line that stays roughly 10 dB or more
above the noise for most of the recording is worth matching; a few dB is noise.

Usage: python hum_check.py recording.m4a [--nominal 50] [--block 30]
"""
import argparse
import numpy as np
from scipy.signal import welch
from enf_match import load_audio

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("recording")
ap.add_argument("--nominal", type=float, default=50.0)
ap.add_argument("--block", type=int, default=30, help="block length in seconds")
a = ap.parse_args()

sr, x = load_audio(a.recording)
print(f"recording: {len(x) / sr / 60:.1f} min, {a.block} s blocks")
for h in (1, 2, 3, 4, 6):
    c = a.nominal * h
    vals = []
    for s in range(0, len(x) - a.block * sr + 1, a.block * sr):
        f, p = welch(x[s:s + a.block * sr], sr, nperseg=sr * 16)
        near = (f > c - 0.3) & (f < c + 0.3)
        around = (f > c - 3) & (f < c + 3)
        vals.append(10 * np.log10(p[near].max() / np.median(p[around])))
    print(f"{c:5g} Hz  median {np.median(vals):4.0f} dB | " + " ".join(f"{v:.0f}" for v in vals))
