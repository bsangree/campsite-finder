#!/usr/bin/env python3
"""
Compute per-park availability stats from the recorder log and emit stats.json
to stdout. With --notify (and $NTFY_TOPIC set), also push an ntfy notification
for any WATCHED park that flipped full -> open in the most recent poll.

Usage (in .github/workflows/record.yml, after poll.py appends to the log):
    python3 scripts/stats.py data-branch/log.jsonl --notify > data-branch/stats.json
"""
import json, os, sys, urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")
SITE = "https://bsangree.github.io/campsite-finder/"

def load_rows(path):
    rows = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            if "open" in r:
                r["t"] = datetime.fromisoformat(r["ts"])
                rows.append(r)
        except (json.JSONDecodeError, ValueError):
            continue
    return rows

def hour_bucket(h):
    if h < 12: return "mornings"
    if h < 17: return "afternoons"
    if h < 21: return "evenings"
    return "late night"

def main():
    log_path = sys.argv[1] if len(sys.argv) > 1 else "data-branch/log.jsonl"
    notify = "--notify" in sys.argv
    rows = load_rows(log_path)
    if not rows:
        print(json.dumps({"generated": None, "parks": {}}))
        return

    now = max(r["t"] for r in rows)
    cutoff30 = now - timedelta(days=30)

    # One series per (park, target weekday): wed-arrival and fri-arrival tracked separately
    series = defaultdict(list)
    for r in rows:
        dow = datetime.fromisoformat(r["date"]).weekday()
        series[(r["park"], dow)].append(r)

    flips = defaultdict(list)          # park -> [flip datetimes]
    latest_pair = {}                   # (park, dow) -> (prev_row, last_row)
    for key, rs in series.items():
        rs.sort(key=lambda r: r["t"])
        prev = None
        for r in rs:
            if prev is not None and prev["open"] == 0 and r["open"] > 0:
                flips[key[0]].append(r["t"])
            prev = r
        if len(rs) >= 2:
            latest_pair[key] = (rs[-2], rs[-1])

    # A park is "live" only if the recorder has actually seen it recently — otherwise
    # emitting stats (esp. "no openings") would be misleading (e.g. upstream IP blocks).
    last_ok = {}
    for r in rows:
        if r["t"] > last_ok.get(r["park"], datetime.min.replace(tzinfo=timezone.utc)):
            last_ok[r["park"]] = r["t"]

    parks = {}
    for park in {k[0] for k in series}:
        if now - last_ok[park] > timedelta(hours=48):
            continue  # stale — frontend shows nothing rather than a wrong claim
        fs = flips.get(park, [])
        recent = [f for f in fs if f > cutoff30]
        entry = {"flips30": len(recent), "lastOpen": max(fs).isoformat() if fs else None}
        if len(fs) >= 3:  # need a few samples before claiming a pattern
            la = [f.astimezone(LA) for f in fs]
            dow = Counter(f.strftime("%a") for f in la).most_common(1)[0]
            hb = Counter(hour_bucket(f.hour) for f in la).most_common(1)[0]
            # Only claim a pattern when it actually dominates
            if dow[1] / len(la) >= 0.4:
                entry["typical"] = f"{dow[0]} {hb[0]}" if hb[1] / len(la) >= 0.4 else dow[0]
        parks[park] = entry

    print(json.dumps({"generated": now.isoformat(), "parks": parks}, indent=1))

    if notify:
        topic = os.environ.get("NTFY_TOPIC", "").strip()
        try:
            watch = set(json.load(open("watches.json")).get("watch", []))
        except Exception:
            watch = set()
        if not topic or not watch:
            print("notify: no topic or empty watch list", file=sys.stderr)
            return
        fresh = now - timedelta(minutes=20)  # only flips from the poll that just ran
        for (park, dow), (prev, last) in latest_pair.items():
            if park not in watch:
                continue
            if prev["open"] == 0 and last["open"] > 0 and last["t"] >= fresh:
                name = park.replace("-", " ").title()
                day = datetime.fromisoformat(last["date"]).strftime("%a %b %-d")
                body = f"{last['open']} site{'s' if last['open'] != 1 else ''} open for {day} ({last['nights']} night{'s' if last['nights'] != 1 else ''}). Go!"
                req = urllib.request.Request(
                    f"https://ntfy.sh/{topic}", data=body.encode(),
                    headers={
                        "Title": f"{name} just opened",
                        "Click": f"{SITE}?d={last['date']}&n={last['nights']}&v=list",
                        "Priority": "high", "Tags": "tada",
                    })
                try:
                    urllib.request.urlopen(req, timeout=10)
                    print(f"notify: sent for {park}", file=sys.stderr)
                except Exception as e:
                    print(f"notify: FAILED for {park}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
