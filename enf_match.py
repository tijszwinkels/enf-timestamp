#!/usr/bin/env python3
"""Find when a recording was made from its mains hum (electric network frequency, ENF).

Extracts the hum line (a harmonic of the nominal grid frequency) from a recording,
turns it into a once-per-second frequency curve, and slides that curve along a log
of the grid frequency (CSV rows "utc,hz", one value per second) to find the best
matching start time.

Usage:
  python enf_match.py recording.wav grid-*.csv [--nominal 50] [--harmonics 2]
                      [--win 16] [--band 0.1] [--start 2026-11-04T12:35:17Z]

The recording may be any format ffmpeg can read; it is converted to 8 kHz mono.
--start is the true start time (UTC), only used to report the error afterwards.
"""
import argparse, csv, datetime as dt, gzip, json, os, subprocess, sys, tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sosfiltfilt

UTC = dt.timezone.utc


def load_audio(path, rate=8000):
    """Return (sample_rate, mono float samples); converts non-WAV input with ffmpeg."""
    if not path.lower().endswith(".wav"):
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-map_metadata", "-1",
                        "-vn", "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", tmp], check=True)
        path = tmp
    sr, x = wavfile.read(path)
    x = x.astype(float)
    if x.ndim > 1:
        x = x.mean(axis=1)
    return sr, x


def track_harmonic(x, sr, h, nominal=50.0, win=16.0, band=0.1):
    """Per-second frequency estimate of harmonic h, divided by h (so it is in grid Hz).

    Returns (curve, line_strength_db). Window i covers [i, i+win) seconds, so value i
    belongs to time i + win/2 after the recording start.
    """
    c = nominal * h
    sos = butter(4, [c - 1.5 * h, c + 1.5 * h], btype="band", fs=sr, output="sos")
    y = sosfiltfilt(sos, x)
    n = int(win * sr)
    nfft = 1 << int(np.ceil(np.log2(n * 32)))
    w = np.hanning(n)
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    sel = (freqs > c - band * h) & (freqs < c + band * h)
    df = freqs[1] - freqs[0]
    est, strength = [], []
    for s in range(0, int(len(x) / sr - win) + 1):
        sp = np.abs(np.fft.rfft(y[s * sr: s * sr + n] * w, nfft)) ** 2
        b = sp[sel]
        i = int(np.argmax(b))
        if 0 < i < len(b) - 1:  # quadratic interpolation of the peak
            l, m, r = np.log(b[i - 1:i + 2] + 1e-30)
            i = i + 0.5 * (l - r) / (l - 2 * m + r)
        est.append((freqs[sel][0] + i * df) / h)
        strength.append(b.max() / np.median(b))
    return np.array(est), 10 * np.log10(np.median(strength))


def load_reference(paths):
    """Read "utc,hz" CSV files (optionally .gz) into a per-second array starting at t0."""
    rows = []
    for p in paths:
        op = gzip.open if p.endswith(".gz") else open
        with op(p, "rt") as fh:
            for r in csv.reader(fh):
                if r and r[0] != "utc":
                    rows.append((dt.datetime.fromisoformat(r[0]).replace(tzinfo=UTC), float(r[1])))
    if not rows:
        sys.exit("no reference rows found")
    rows.sort()
    t0 = rows[0][0]
    sec = np.array([int((t - t0).total_seconds()) for t, _ in rows])
    ref = np.full(sec.max() + 1, np.nan)
    ref[sec] = [f for _, f in rows]
    return t0, ref


def smooth(ref, win):
    """Moving average over win seconds (matching the analysis window); NaN where data is missing."""
    k = int(round(win))
    ker = np.ones(k) / k
    valid = (~np.isnan(ref)).astype(float)
    num = np.convolve(np.nan_to_num(ref), ker, "same")
    den = np.convolve(valid, ker, "same")
    out = num / np.maximum(den, 1e-9)
    out[den < 0.99] = np.nan
    return out


def sliding_corr(curve, ref):
    """Pearson correlation of curve against every window of ref (FFT-based). NaN windows -> nan."""
    L = len(curve)
    e = curve - curve.mean()
    e /= np.sqrt((e ** 2).sum())
    bad = np.isnan(ref)
    r0 = np.where(bad, 0.0, ref)
    ones = np.ones(L)
    nbad = np.rint(fftconvolve(bad.astype(float), ones, "valid"))
    s1 = fftconvolve(r0, ones, "valid")
    s2 = fftconvolve(r0 ** 2, ones, "valid")
    num = fftconvolve(r0, e[::-1], "valid")
    scores = num / np.sqrt(np.maximum(s2 - s1 ** 2 / L, 1e-18))
    scores[nbad > 0] = np.nan
    return scores


def match(curve, t0, ref, win, exclude=30):
    """Return dict with best/runner-up start times, scores, z-score and the score array."""
    scores = sliding_corr(curve, smooth(ref, win))
    finite = np.isfinite(scores)
    if not finite.any():
        sys.exit("reference does not cover a full recording length anywhere")
    s = np.where(finite, scores, -np.inf)
    best = int(np.argmax(s))
    masked = s.copy()
    masked[max(0, best - exclude): best + exclude + 1] = -np.inf
    ru = int(np.argmax(masked))
    off = win / 2  # curve value 0 belongs to win/2 s after the start
    start = lambda i: t0 + dt.timedelta(seconds=float(i) - off)
    vals = scores[finite]
    return {"best_start": start(best), "best_corr": float(scores[best]),
            "runner_up_start": start(ru), "runner_up_corr": float(scores[ru]),
            "z": float((scores[best] - vals.mean()) / vals.std()),
            "candidates": int(finite.sum()), "scores": scores}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording")
    ap.add_argument("reference", nargs="+", help='grid CSV files with rows "utc,hz" (1 per second, UTC)')
    ap.add_argument("--nominal", type=float, default=50.0, help="grid frequency: 50 (Europe) or 60 (Americas)")
    ap.add_argument("--harmonics", default="2", help="comma-separated harmonics to combine, e.g. 2 (100 Hz hum) or 1 (50 Hz)")
    ap.add_argument("--win", type=float, default=16.0, help="analysis window in seconds")
    ap.add_argument("--band", type=float, default=0.1, help="peak search half-width in Hz, per unit of harmonic")
    ap.add_argument("--start", help="true start time (ISO, UTC) to report the error; never used for the search")
    ap.add_argument("--json", help="write the result (and curves) to this JSON file")
    a = ap.parse_args()

    sr, x = load_audio(a.recording)
    print(f"recording: {len(x) / sr / 60:.1f} min")
    hs = [int(h) for h in a.harmonics.split(",")]
    curves, weights = [], []
    for h in hs:
        cur, db = track_harmonic(x, sr, h, a.nominal, a.win, a.band)
        print(f"  {a.nominal * h:g} Hz line: median {db:.1f} dB above band median, curve std {np.std(cur) * 1000:.0f} mHz")
        curves.append(cur - np.median(cur))
        weights.append(1 / max(np.var(cur), 1e-12))  # noisy lines wander more: weight them down
    w = np.array(weights) / sum(weights)
    curve = sum(wi * c for wi, c in zip(w, curves))

    t0, ref = load_reference(a.reference)
    r = match(curve, t0, ref, a.win)
    margin = r["best_corr"] - r["runner_up_corr"]
    confident = r["z"] >= 4 and margin >= 0.1
    print(f"searched {r['candidates']} candidate start times ({r['candidates'] / 3600:.1f} h of reference)")
    print(f"best match : {r['best_start']:%Y-%m-%d %H:%M:%S} UTC  corr {r['best_corr']:.3f}")
    print(f"runner-up  : {r['runner_up_start']:%Y-%m-%d %H:%M:%S} UTC  corr {r['runner_up_corr']:.3f}")
    print(f"z-score {r['z']:.1f}, margin {margin:.3f} -> {'CONFIDENT' if confident else 'not confident (needs z>=4 and margin>=0.1)'}")
    if a.start:
        true = dt.datetime.fromisoformat(a.start.replace("Z", "+00:00"))
        print(f"true start : {true:%Y-%m-%d %H:%M:%S} UTC  error {(r['best_start'] - true).total_seconds():+.1f} s")
    if a.json:
        out = {k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in r.items() if k != "scores"}
        out.update(confident=confident, curve_mhz=list(np.round(curve * 1000, 2)),
                   scores=[None if not np.isfinite(v) else round(float(v), 4) for v in r["scores"]],
                   reference_t0=t0.isoformat(), win=a.win)
        json.dump(out, open(a.json, "w"))


if __name__ == "__main__":
    main()
