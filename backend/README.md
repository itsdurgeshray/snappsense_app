# Snappsense API

FastAPI service that fetches Google Play and App Store reviews, scores sentiment, groups concerns into issues and suggests fixes. **Free to run: no paid APIs.** Built for speed: a standard Play Store report (4,000 reviews) is ready in ~4–7 s, a cached one in ~10 ms.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # optional settings
.venv/bin/uvicorn app.main:app --port 8000
```

The frontend's Vite dev server proxies `/api` to port 8000.

```bash
.venv/bin/python -m pytest -q   # 33 tests, no network needed
```

## API

| Method | Path | |
|---|---|---|
| `POST` | `/api/analyze` | `{url}` or `{store, appId, country}`, plus `depth` (`quick` · `standard` · `deep`) and `refresh`. Returns a cached report immediately, or a `jobId`. |
| `GET` | `/api/jobs/{id}/events` | Server-Sent Events: `progress` → `report` → (`report` again if a local model polished titles) → `done` / `error`. |
| `GET` | `/api/reviews?report=&issue=` | Every review behind one feedback row (loaded when its detail view opens). |
| `GET` | `/api/jobs/{id}` | Current job state (polling fallback). |
| `GET` | `/api/resolve?url=` | Validate a store link. |
| `GET` | `/api/health` | Status, AI and App Store Connect availability. |

## How it stays fast

**Google Play** — the review feed is one cursor per (sort, star filter), ~200 reviews per ~1 s page. Snappsense reads **five cursors in parallel, one per star rating**, with equal quotas so they finish together, while the app metadata loads alongside. Measured on a 77M-rating app: 1,000 reviews in 1.1 s, 4,000 in 3.8 s, 10,000 in 7.7 s (sequential paging: 2,000 in 10.3 s).

**App Store** — Apple has no public review API (the RSS feed now returns stale, mostly empty snapshots, and the web store exposes no client token). Snappsense fetches the server-rendered product page of ~28 storefronts concurrently: the all-time star histogram plus each storefront's featured reviews — a few hundred distinct reviews in ~1.5 s. With App Store Connect credentials, apps your team owns get their complete review history instead.

**Analysis** (~0.3–1 s for 4,000 reviews, in a worker thread, all local and free):
- Sentiment: VADER text polarity blended with the star rating → Delighted / Happy / Neutral / Angry / Frustrated.
- Categories: explainable regex taxonomy — Crash, Transactional, Bug Report, Performance, Support, Pricing & Ads, UI/UX, Feature Request (plus Praise / Other).
- **Concerns only:** a review enters the feedback table only if it states a problem or a request. Angry/frustrated reviews qualify; neutral or happy ones only when the concern sentence itself is negative ("love it, but it crashes on login"). Praise never appears.
- **Concern sentence:** the sentence of a review that states the problem, so mixed reviews are grouped by their complaint, not their compliments.
- **Issues:** concern sentences are embedded with LSA (TF-IDF → SVD) fitted on the app's own reviews, with synonym canonicalisation (customer care/service/support, late/delay…), then grouped with adaptive k-means (≤ 6 per category). Groups that map to the same root cause are merged into one row.
- **Feature requests:** the requested feature is extracted ("dark mode", "download songs offline") and requests are grouped by the feature itself, so different requests are different rows. Negated ("wouldn't let me log in") and sarcastic ("wish I could give zero stars") phrases are rejected.
- **Titles (one-liners):** the clearest real concern sentence among the most central reviews — scored for how many reviewers say the same thing, specificity, English, spelling (vs. the app's own vocabulary) and length — then tidied ("I am not able to…" → "Unable to…"). Feature requests read as actions ("Add dark mode", "Let users download songs offline").
- **Fixes:** a rule-based playbook of ~35 specific remedies matched to the issue's concerns and title, scoped by category.
- **Consistency:** every category in the breakdown has at least one row in the table; the breakdown is computed from the same concerns.
- All-time sentiment: the store's full rating histogram, split per star by the sentiment observed in that star's review text.
- Trends: exact counts where every star's cursor has full coverage; outside that, extrapolated from each star's own review rate within a bounded horizon, and flagged `estimated`. Periods that can't be supported are returned `empty`, never invented.

**Optional local polish** — if a free [Ollama](https://ollama.com) server is running with the configured model, titles are rewritten into crisper one-liners and pushed as a second `report` event. Nothing leaves the machine; without it, built-in titles are used.

**Serving** — identical concurrent requests share one job; reports are cached in SQLite (6 h TTL, a deeper cached report satisfies a shallower request); at most `SNAPPSENSE_MAX_JOBS` analyses run at once.

## Limits worth knowing

- Text analysis is English-only; Play reviews are requested in English, App Store storefronts are English-speaking first.
- For very high-volume apps, a standard fetch covers hours to days of reviews; long-range trend periods show as estimated or empty. Use `depth=deep` for more history.
- App Store results without App Store Connect are a featured-review sample, labelled as such in the report.
