"""Google Play fetcher.

Speed comes from sharding: Play's review feed is a single cursor per
(sort, star-filter) pair, and each page is ~200 reviews / ~1 s. Reading one
cursor is therefore strictly sequential — so we read five at once, one per
star rating, each with an equal quota so they all finish together. Metadata
is fetched in parallel with the first pages.

Equal quotas mean the 5★ shard covers a shorter time span than the 1★ shard
for a typical app. Inside the window where *every* truncated shard has full
coverage (`window_start`), the counts are complete, not sampled, so trends
built from that window need no reweighting. Older low-star reviews outside it
still feed issue discovery, where negative text matters most.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Executor
from datetime import datetime
from typing import Callable

from google_play_scraper import Sort, app as gp_app, reviews as gp_reviews
from google_play_scraper.exceptions import NotFoundError

from ..links import AppRef
from ..models import AppMeta, Depth, FetchResult, Review

log = logging.getLogger(__name__)

PAGE = 200
TOTAL_BY_DEPTH: dict[Depth, int] = {"quick": 1000, "standard": 4000, "deep": 10000}

Progress = Callable[[dict], None]


class AppNotFound(LookupError):
    pass


def _to_review(r: dict, lang: str, country: str) -> Review | None:
    text = (r.get("content") or "").strip()
    if not text or not r.get("at"):
        return None
    return Review(
        id=f"gp:{r['reviewId']}",
        text=text,
        rating=int(r.get("score") or 0),
        at=r["at"],
        source=f"play:{lang}/{country}",
        thumbs=int(r.get("thumbsUpCount") or 0),
        version=r.get("reviewCreatedVersion") or r.get("appVersion"),
    )


async def fetch_play(ref: AppRef, depth: Depth, pool: Executor, progress: Progress, lang: str = "en") -> FetchResult:
    loop = asyncio.get_running_loop()
    country = ref.country

    def call(fn, *a, **kw):
        return loop.run_in_executor(pool, lambda: fn(*a, **kw))

    async def get_meta() -> AppMeta:
        try:
            d = await call(gp_app, ref.app_id, lang=lang, country=country)
        except NotFoundError as e:
            raise AppNotFound(f"No Google Play app with id “{ref.app_id}”.") from e
        meta = AppMeta(
            store="play",
            app_id=ref.app_id,
            country=country,
            name=d.get("title") or ref.app_id,
            developer=d.get("developer") or "",
            icon=d.get("icon"),
            genre=d.get("genre"),
            rating=d.get("score"),
            ratings_count=d.get("ratings"),
            installs=d.get("installs"),
            url=d.get("url"),
            histogram=list(d["histogram"]) if d.get("histogram") else None,
        )
        progress({"stage": "meta", "name": meta.name, "icon": meta.icon})
        return meta

    meta_task = asyncio.create_task(get_meta())
    total = TOTAL_BY_DEPTH[depth]
    fetched = {"n": 0}

    async def shard(star: int, sort: Sort) -> tuple[list[Review], bool]:
        """Returns (reviews, exhausted)."""
        out: list[Review] = []
        token = None
        quota = max(PAGE, total // (5 * len(sorts)))
        while True:
            for attempt in range(3):
                try:
                    page, token = await call(
                        gp_reviews, ref.app_id, lang=lang, country=country, sort=sort,
                        count=PAGE, filter_score_with=star, continuation_token=token,
                    )
                    break
                except NotFoundError:
                    return out, True
                except Exception as e:  # network hiccups: back off and retry
                    if attempt == 2:
                        log.warning("play shard %s failed: %s", star, e)
                        return out, False
                    await asyncio.sleep(0.4 * (attempt + 1))
            out.extend(r for r in (_to_review(x, lang, country) for x in page) if r)
            fetched["n"] += len(page)
            progress({"stage": "fetch", "fetched": fetched["n"], "target": total})
            exhausted = not page or token is None or getattr(token, "token", None) is None
            if exhausted:
                return out, True
            if meta_task.done() and meta_task.exception():
                return out, True  # bad app id — stop paging
            if len(out) >= quota:
                return out, False

    sorts = [Sort.NEWEST] + ([Sort.MOST_RELEVANT] if depth == "deep" else [])
    shards = [asyncio.create_task(shard(s, so)) for so in sorts for s in range(1, 6)]
    meta = await meta_task  # raises AppNotFound early if the id is wrong
    results = await asyncio.gather(*shards)

    seen: dict[str, Review] = {}
    for revs, _ in results:
        for r in revs:
            seen.setdefault(r.id, r)
    reviews = list(seen.values())

    coverage: dict[int, datetime | None] = {}
    for star, (revs, exhausted) in zip(range(1, 6), results[:5]):
        coverage[star] = None if exhausted or not revs else min(r.at for r in revs)
    return FetchResult(meta=meta, reviews=reviews, sources=[f"Google Play ({lang}, {country.upper()})"], coverage=coverage)
