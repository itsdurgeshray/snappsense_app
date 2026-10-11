# Snappsense

Paste a Google Play or App Store link and get a live report of what users are unhappy about: sentiment trends, all-time ratings, and a prioritised table of concerns with suggested fixes — built entirely on free, local tooling.

> **Proprietary: all rights reserved.** This code is shared for viewing only. You may not copy, reuse, deploy or build on it, in whole or in part, without written permission. See [LICENSE](LICENSE).

```
snappsense/
├── src/            React + TypeScript frontend (Vite)
├── public/         Static assets (fonts, icons, share image, legal & 404 pages, robots/sitemap)
└── backend/        FastAPI service: fetching, analysis, caching (see backend/README.md)
```

## Run locally

```bash
# 1. Backend (Python 3.11+)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000

# 2. Frontend (Node 18+), in another terminal
npm install
npm run dev            # http://localhost:5173 — /api is proxied to :8000
```

Tests: `cd backend && .venv/bin/python -m pytest -q`

## Deploy

- **Frontend → Vercel** (static Vite build).
- **Backend → a host that runs a long-lived Python process** (e.g. Render, using `render.yaml`). The API streams live progress and keeps an in-memory job list and a SQLite cache, which serverless functions can't hold between requests.

Set `VITE_API_URL` on Vercel to the backend URL, and `SNAPPSENSE_CORS` on the backend to the Vercel URL.

## What the feedback table covers

The table is built **per app version** (`backend/app/scope.py`), with a version picker above it:

- the fetch reads back past the start of the six newest versions that have ≥30 reviews (bounded by a 30k-review limit, configurable with `SNAPPSENSE_CURRENT_MAX`); every version read completely is offered;
- it opens on the **latest** version (the newest with a real share of users, so a few beta reviews don't count); tick more versions to combine them, or use Select all / Clear all;
- issues are clustered once across the offered versions, each with per-version counts, so switching versions re-ranks the table in the browser instantly (`src/versions.ts` mirrors the server's ranking and priority rules);
- without version data (App Store public reviews) the table covers the last 90 days.

## Sentiment trend (a whole year)

`backend/app/analysis/trends.py` — bars are sentiment *shares* (100% stacked):

- **Exact**: the reviews read for the table (every star rating, back to the same date) give exact daily counts. Apps of ordinary size are read for the whole year this way.
- **Estimated** (bigger apps' older months): from the start of a run, a second set of cursors reads a thin, date-ordered device segment of the feed (Play's device filter 3). It reaches a year back in a few pages and is calibrated per star against the exact window; thin months borrow from neighbouring weeks, so only months before an app's first review are empty. Play's "most relevant" feed was tried first and rejected: it keeps old negative reviews far longer than positive ones, which skewed older months.
- Everything arrives in one report from the loading screen (no partial reports); the biggest apps take ~20–25 s locally, most apps a few seconds.
- Each star rating maps to sentiments with the mix observed in the analysed reviews.

## Large apps ("Analyse all reviews")

Depths: quick 1k · standard 4k · deep 10k · **all**: every review, up to `SNAPPSENSE_MAX_REVIEWS` (default 50,000; memory peaks at ~155 MB + ~3 MB per 1,000 reviews).

- **Streaming:** each page of reviews is analysed as it downloads; the dashboard appears after the first ~4,000 and fills in (partial reports) while the run continues.
- **Bounded cost:** per-review work is linear (~0.2 ms/review); clustering, vocabulary and titles are fitted on stable samples and then applied to every review, so counts stay exact while time and memory stay flat.
- **Review store** (`backend/data/reviews.db`): every analysed review is kept, so a refresh or a deeper run only downloads and analyses what's new (100k-review refresh: ~8 s instead of ~110 s). Least recently used apps are dropped past `SNAPPSENSE_STORE_MAX`.
- **Limits that come from the stores, not the code:** Google Play serves one sequential cursor per star rating (~150–200 reviews/s each), so the download of a huge app is the slow part; Apple publishes only a few thousand recent reviews per app publicly (complete history needs App Store Connect credentials for your own apps).

| Setting | Default | |
|---|---|---|
| `SNAPPSENSE_MAX_REVIEWS` | 50000 | ceiling for "all reviews" (100k needs ~450 MB) |
| `SNAPPSENSE_FETCH_BUDGET` | 300 | seconds before a fetch stops and keeps what it has |
| `SNAPPSENSE_MAX_FULL_JOBS` | 1 | concurrent "all reviews" runs |
| `SNAPPSENSE_STORE_MAX` | 1000000 | reviews kept in the store |

## Notes

- Store data comes from public, unofficial endpoints; heavy traffic from one server IP can be rate-limited by Google/Apple.
- The bundled Orbiter FBS **Trial** font must be licensed for public/commercial use.
