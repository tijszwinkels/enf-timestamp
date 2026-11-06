#!/usr/bin/env python3
"""Append Continental-European grid frequency (1 value/s) from Gridradar to daily CSV files.

Gridradar's free API (https://gridradar.net/en/api) returns 1-second data for the last hour
with ~15 minutes delay, and each request only returns the data since your previous request
with the same token. So: run this from ONE place only (e.g. a systemd timer every 30 min)
and keep the files; a test request elsewhere "uses up" that stretch of data.

Files: $GRIDRADAR_DATA_DIR/YYYY-MM-DD.csv (UTC date), rows "utc,hz"; days older than
yesterday are gzipped. Gaps are reported on stderr.

Environment: GRIDRADAR_TOKEN_FILE (default ~/.config/gridradar/token),
             GRIDRADAR_DATA_DIR   (default ~/.local/share/gridradar)
Check the Gridradar terms of use before using or sharing the data.
"""
import csv, datetime as dt, gzip, json, os, pathlib, sys, urllib.request

TOKEN_FILE = pathlib.Path(os.environ.get("GRIDRADAR_TOKEN_FILE", "~/.config/gridradar/token")).expanduser()
DATA_DIR = pathlib.Path(os.environ.get("GRIDRADAR_DATA_DIR", "~/.local/share/gridradar")).expanduser()
URL = "https://api.gridradar.net/query?metric=frequency-ucte-median-1s&format=json"


def fetch():
    req = urllib.request.Request(URL, headers={"Authorization": f"Bearer {TOKEN_FILE.read_text().strip()}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return [(dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S"), f) for f, ts in data[0]["datapoints"]]


def last_stored():
    files = sorted(DATA_DIR.glob("*.csv"))
    if not files:
        return None
    last = None
    with open(files[-1]) as fh:
        for row in csv.reader(fh):
            if row and row[0] != "utc":
                last = row[0]
    return dt.datetime.fromisoformat(last) if last else None


def compress_old(today):
    for f in DATA_DIR.glob("*.csv"):
        if f.stem < (today - dt.timedelta(days=1)).isoformat():
            with open(f, "rb") as src, gzip.open(f"{f}.gz", "wb") as dst:
                dst.write(src.read())
            f.unlink()


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    points = fetch()
    last = last_stored()
    new = [(t, f) for t, f in points if last is None or t > last]
    if last and new and (new[0][0] - last).total_seconds() > 1:
        print(f"GAP: {last} -> {new[0][0]} UTC", file=sys.stderr)
    for t, f in new:
        path = DATA_DIR / f"{t.date().isoformat()}.csv"
        fresh = not path.exists()
        with open(path, "a", newline="") as fh:
            w = csv.writer(fh)
            if fresh:
                w.writerow(["utc", "hz"])
            w.writerow([t.isoformat(sep=" "), f])
    compress_old(dt.datetime.now(dt.timezone.utc).date())
    span = f"{new[0][0]} .. {new[-1][0]} UTC" if new else "nothing new"
    print(f"fetched {len(points)}, appended {len(new)} ({span})")


if __name__ == "__main__":
    main()
