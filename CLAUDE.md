# Campsite Finder — project context for Claude

One-page Bay Area campsite availability dashboard. Owner: Ben Sangree (not an engineer —
explain things plainly, keep everything as simple as possible, never over-engineer).

- **Live:** https://bsangree.github.io/campsite-finder/
- **Repo:** https://github.com/bsangree/campsite-finder (public; GitHub Pages serves `main`)
- **Deploy:** push to `main` → Pages redeploys in ~30s. No build step.

## Architecture (deliberate choices — don't "upgrade" without asking)

- **One file: `index.html`.** No framework, no build, no backend, no database.
  Park data is the `PARKS` array inside the file (47 campgrounds as of 2026-08-01).
  ⚠️ When adding a park with live availability, ALSO add it to `scripts/poll.py`
  so the recorder tracks it — this has drifted before.
- Map popups show an arrival-day forecast from Open-Meteo (free, CORS-open, no key,
  16-day horizon) — fetched lazily on popup open, cached per park+date.
- Tailwind via CDN; Leaflet 1.9.4 via unpkg + free Esri World Topo tiles (map view).
- Ben's machine has **no Node.js** — that's why this is not a Next.js app. Keep it that way.
- Three views, toggled top-right: **List / Map / Scan 8 weekends** (grid of parks × 8 Fridays).
- URL params hold all state and are shareable:
  `?d=YYYY-MM-DD&n=2&drive=90&env=redwoods,coast&dogs=1&rv=1&drivein=1&avail=1&v=map|grid`

## Live availability — reverse-engineered APIs (both CORS-open, no keys)

**ReserveCalifornia** (CA state parks) — base
`https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr`
- Availability: `POST /search/place`, body includes `{PlaceId, StartDate:"MM-DD-YYYY",
  Nights, UnitCategoryId:1, CountUnits:true, InSeasonOnly:true, WebOnly:true, ...}`
  (full payload in `fetchRC()` in index.html). Count = sum of
  `SelectedPlace.Facilities[*].UnitTypes[*].AvailableCount`.
- Park lookup: `GET /fd/citypark/namecontains/{q}` or `GET /fd/citypark/{placeId}` (has lat/lng).
- Booking deep link: `reservecalifornia.com/park/{PlaceId}?date=YYYY-MM-DD&night=N`.

**Recreation.gov** (federal: GGNRA, Point Reyes, Pinnacles, Los Padres)
- `GET https://www.recreation.gov/api/camps/availability/campground/{id}/month?start_date=YYYY-MM-01T00%3A00%3A00.000Z`
  → `campsites{}.availabilities{"YYYY-MM-DDT00:00:00Z": "Available"|...}`.
  A site counts as open only if ALL requested nights are "Available"; skip day-use/group loops.
- Booking deep link: `/camping/campgrounds/{id}/availability?date=YYYY-MM-DD`.

**These are undocumented internal APIs.** If badges suddenly all show "—", the provider
changed something — re-derive from their site's network traffic / JS bundles (that's how
these were found).

**Blocked systems (8 gray "check site" parks):** East Bay Parks uses ReserveAmerica
(403s non-browser clients); Santa Clara County uses gooutsideandplay.org (legacy .asp,
no API — reservations online or (408) 355-2201); San Mateo County is phone-only;
Butano SP is first-come-first-served. Getting these live would require a scraping backend.

## Background recorder (Phase 0 — running since 2026-06-19)

`.github/workflows/record.yml` (cron `*/15`, GitHub throttles to ~hourly in practice)
runs `scripts/poll.py`, which checks every park for the upcoming Friday (2 nights) and
appends one JSONL line per park to `log.jsonl` on the **`data` branch**:
`{ts, park, date, nights, open}`. Free forever on public-repo Actions.

- Health: `gh run list --workflow=record-availability --limit 5`
- Data: `git fetch origin data && git show origin/data:log.jsonl | wc -l` (~12k+ obs)
- ⚠️ Known gap: `poll.py`'s park list (28) predates the Big Sur + later additions in
  `index.html` (42). Sync it when touching Phase 1.

## Roadmap — Phase 1 is next (unblocked, enough data)

1. Daily Action computes per-park stats from `log.jsonl` → commit `stats.json` to main:
   openings in last 30d, typical day-of-week/hour of openings, last-opened timestamp.
2. Cards + map popups show it: "Opened 6× last 30 days · usually Tue evening".
3. **Watch** feature: recorder compares current poll to previous; on full→available flip
   for a watched park, notify (simplest: GitHub Action sends email; Ben will say what he wants).
4. Optional: also record Wednesday arrivals so stats cover midweek, not just weekends.

## Design system (from a design review — keep these rules)

- ONE green (custom `forest` scale) and it means "available" — nothing else is green.
  Full = rust `#A14D3B`. Everything else warm gray/sand. No emerald/rose/amber/blue/purple.
- No emoji as UI icons. No all-caps/letterspaced labels. System font stack (no webfont).
- Cards: name + big open-count number, one meta line, description, source link. No buttons/badges/chips.
- Sticky date bar (arrival + nights — Ben considered start/end dates, chose to keep nights).
- 44px tap targets; mobile-first (filters collapse behind a "Filters" disclosure on phones).

## Gotchas learned the hard way

- Leaflet `fitBounds` on a zero-width container degenerates to max zoom — guarded with a
  ResizeObserver refit in `renderMap()`. Don't remove it.
- ReserveCalifornia rebuilt their site once already (old `/Web/#!park/{id}` URLs 404).
  PlaceIds and the `?date=&night=` params were recovered from their minified bundle.
- A same-URL navigate may be served from cache — cache-bust when testing.
- GitHub Pages caches ~30s; hard-refresh when verifying deploys.
- Git identity is set repo-locally (Ben's machine has no global git config).

## Working style

- Ben reviews everything visually; verify changes in a browser before pushing.
- Commit messages explain the "why"; push to main deploys — so only push working states.
- Prefer deleting features over adding config. The app's job: "where can I camp this
  weekend?" answered in one glance.
