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

## Notes

- Store data comes from public, unofficial endpoints; heavy traffic from one server IP can be rate-limited by Google/Apple.
- The bundled Orbiter FBS **Trial** font must be licensed for public/commercial use.
