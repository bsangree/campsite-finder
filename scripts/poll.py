#!/usr/bin/env python3
"""
Poll live availability for all parks and emit one JSONL line per park to stdout.
Run by .github/workflows/record.yml every 15 min; output is appended to log.jsonl
on the `data` branch.
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone

RC_API = "https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr"
RG_API = "https://www.recreation.gov/api/camps/availability/campground"

# (id, system, external_id) — keep in sync with PARKS in index.html
PARKS = [
    ("samuel-p-taylor", "rc", 705), ("china-camp", "rc", 626), ("pantoll", "rc", 682),
    ("steep-ravine", "rc", 682), ("angel-island", "rc", 614), ("mt-diablo", "rc", 683),
    ("half-moon-bay", "rc", 652), ("portola-redwoods", "rc", 695), ("big-basin", "rc", 3),
    ("castle-rock", "rc", 1111), ("henry-cowell", "rc", 655), ("new-brighton", "rc", 685),
    ("sunset-sb", "rc", 726), ("manresa-sb", "rc", 672), ("henry-coe", "rc", 656),
    ("fremont-peak", "rc", 645), ("sugarloaf", "rc", 725), ("bothe-napa", "rc", 620),
    ("austin-creek", "rc", 1085), ("bodega-dunes", "rc", 718), ("salt-point", "rc", 703),
    ("brannan-island", "rc", 621),
    ("pfeiffer-big-sur", "rc", 690), ("andrew-molera", "rc", 1077),
    ("julia-pfeiffer", "rc", 661), ("limekiln", "rc", 666),
    ("hendy-woods", "rc", 654), ("van-damme", "rc", 731),
    ("russian-gulch", "rc", 701), ("mackerricher", "rc", 668),
    ("kirby-cove", "rg", 232491), ("bicentennial", "rg", 272229), ("hawk-camp", "rg", 258815),
    ("haypress", "rg", 10067346), ("point-reyes", "rg", 233359), ("pinnacles", "rg", 234015),
    ("kirk-creek", "rg", 233116), ("plaskett-creek", "rg", 231959),
    # --- expansion 2026-08-01 (region build-out) ---
    ("grizzly-creek", "rc", 650),
    ("humboldt-redwoods", "rc", 657),
    ("richardson-grove", "rc", 700),
    ("standish-hickey", "rc", 721),
    ("sue-meg", "rc", 688),
    ("prairie-creek", "rc", 696),
    ("gold-bluffs-beach", "rc", 697),
    ("jedediah-smith", "rc", 660),
    ("del-norte-mill-creek", "rc", 638),
    ("castle-crags", "rc", 624),
    ("burney-falls", "rc", 674),
    ("manzanita-lake", "rg", 234039),
    ("summit-lake-lassen", "rg", 234041),
    ("antlers", "rg", 232753),
    ("fowlers-mccloud", "rg", 255119),
    ("hayward-flat", "rg", 232234),
    ("donner-memorial", "rc", 640),
    ("sugar-pine-point", "rc", 724),
    ("dl-bliss", "rc", 637),
    ("emerald-bay", "rc", 641),
    ("grover-hot-springs", "rc", 651),
    ("fallen-leaf", "rg", 232769),
    ("william-kent", "rg", 232874),
    ("nevada-beach", "rg", 232768),
    ("stumpy-meadows", "rg", 232107),
    ("upper-pines", "rg", 232447),
    ("lower-pines", "rg", 232450),
    ("north-pines", "rg", 232449),
    ("wawona", "rg", 232446),
    ("bridalveil-creek", "rg", 232453),
    ("hodgdon-meadow", "rg", 232451),
    ("crane-flat", "rg", 232452),
    ("tuolumne-meadows", "rg", 232448),
    ("summerdale", "rg", 233837),
    ("pinecrest", "rg", 232254),
    ("lake-alpine", "rg", 274410),
    ("calaveras-big-trees", "rc", 5),
    ("glory-hole", "rg", 234073),
    ("oh-ridge", "rg", 232269),
    ("silver-lake-june", "rg", 234330),
    ("twin-lakes-mammoth", "rg", 234329),
    ("lake-mary", "rg", 233404),
    ("convict-lake", "rg", 234311),
    ("four-jeffrey", "rg", 233807),
    ("big-pine-creek", "rg", 232305),
    ("whitney-portal", "rg", 232123),
    ("onion-valley", "rg", 232077),
    ("montana-de-oro", "rc", 679),
    ("morro-bay", "rc", 680),
    ("san-simeon", "rc", 713),
    ("pismo", "rc", 691),
]

def http_json(url, payload=None, timeout=15):
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "campsite-finder/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def upcoming_friday():
    from datetime import date, timedelta
    today = date.today()
    days = (4 - today.weekday()) % 7  # Mon=0..Sun=6; Fri=4
    return today + timedelta(days=days)

def upcoming_wednesday():
    from datetime import date, timedelta
    today = date.today()
    days = (2 - today.weekday()) % 7  # Wed=2
    return today + timedelta(days=days)

def check_rc(place_id, start, nights=2):
    body = {
        "PlaceId": place_id, "Latitude": 0, "Longitude": 0,
        "StartDate": start.strftime("%m-%d-%Y"), "Nights": nights,
        "CustomerId": 0, "UnitCategoryId": 1, "SleepingUnitId": 0, "MinVehicleLength": 0,
        "UnitTypesGroupIds": None, "AmenityIds": None, "Sort": "name",
        "IsADA": False, "RestrictADA": False, "NearbyLimit": 100,
        "isSearchAllParks": False, "customerClassificationId": 0,
        "InSeasonOnly": True, "WebOnly": True, "NearbyCountLimit": 0,
        "NearbyOnlyAvailable": False, "CountNearby": False, "CountUnits": True, "HighlightedPlaceId": 0,
    }
    d = http_json(f"{RC_API}/search/place", body)
    n = 0
    for f in (d.get("SelectedPlace", {}).get("Facilities") or {}).values():
        for ut in (f.get("UnitTypes") or {}).values():
            n += ut.get("AvailableCount") or 0
    return n

def check_rg(facility_id, start, nights=2):
    from datetime import timedelta
    month1 = start.replace(day=1)
    d = http_json(f"{RG_API}/{facility_id}/month?start_date={month1.isoformat()}T00%3A00%3A00.000Z")
    want = {(start + timedelta(days=i)).isoformat() + "T00:00:00Z" for i in range(nights)}
    # Fetch second month if the stay spans into it
    end = start + timedelta(days=nights-1)
    if end.month != start.month:
        d2 = http_json(f"{RG_API}/{facility_id}/month?start_date={end.replace(day=1).isoformat()}T00%3A00%3A00.000Z")
        for k, v in (d2.get("campsites") or {}).items():
            d.setdefault("campsites", {}).setdefault(k, {"availabilities": {}})["availabilities"].update(v.get("availabilities", {}))
    n = 0
    for s in (d.get("campsites") or {}).values():
        loop = (s.get("loop") or "") + (s.get("site") or "")
        if "day use" in loop.lower(): continue
        if all(s.get("availabilities", {}).get(dt) == "Available" for dt in want):
            n += 1
    return n

def main():
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    targets = [(upcoming_wednesday(), 1), (upcoming_friday(), 2)]  # midweek + weekend
    # POLL_SKIP=rc in the Action: ReserveCalifornia 403s GitHub runner IPs (since 2026-07-17).
    # Run locally (residential IP) without the env var to record RC parks too.
    skip = set(filter(None, os.environ.get("POLL_SKIP", "").split(",")))
    seen = {}  # (system, ext, date) — pantoll & steep-ravine share placeId 682
    for pid, sys_, ext in PARKS:
        if sys_ in skip:
            continue
        for d, nights in targets:
            key = (sys_, ext, d)
            try:
                n = seen.get(key)
                if n is None:
                    n = seen[key] = check_rc(ext, d, nights) if sys_ == "rc" else check_rg(str(ext), d, nights)
                rec = {"ts": ts, "park": pid, "date": d.isoformat(), "nights": nights, "open": n}
            except Exception as e:
                rec = {"ts": ts, "park": pid, "date": d.isoformat(), "nights": nights, "error": str(e)[:120]}
            print(json.dumps(rec), flush=True)
            time.sleep(0.15)  # be polite

if __name__ == "__main__":
    main()
