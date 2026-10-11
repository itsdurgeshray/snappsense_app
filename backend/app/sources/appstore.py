"""Apple App Store fetcher.

Apple has no public review API any more: the legacy RSS feed mostly returns
stale, empty CDN snapshots and the web store no longer exposes a client token.
What *is* public and fast:

* iTunes Lookup — app metadata.
* The server-rendered product page of every storefront — the all-time star
  histogram plus a set of featured reviews. Each storefront surfaces a
  different set, so fetching many storefronts concurrently yields a few
  hundred distinct reviews in ~2 seconds.
* The RSS feed, when it happens to have data — used as a bonus source.

For apps you own, configure App Store Connect API credentials to read the
complete review history instead (see README).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import httpx

from .. import scope as scopes
from ..config import settings
from ..links import AppRef
from ..models import AppMeta, Depth, FetchResult, Review
from .playstore import AppNotFound

log = logging.getLogger(__name__)

Progress = Callable[[dict], None]

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

# English-language storefronts first: our text analysis is English-only.
STOREFRONTS = (
    "us gb ca au nz ie in sg za ph my ng ke pk ae hk gh lk bd mt jm tt bs bb ug tz zw zm bw na mu "
    "fj pg bz gy lc vc gd ag kn dm ky bm vg tc ms ai"
).split()
STOREFRONTS_BY_DEPTH: dict[Depth, int] = {"quick": 12, "standard": 28, "deep": len(STOREFRONTS), "all": len(STOREFRONTS), "current": len(STOREFRONTS)}
RSS_PAGES = 10
# "All reviews" also reads the RSS feed of the biggest English storefronts
# (up to 500 recent reviews each): the most public data Apple offers.
RSS_FRONTS_BY_DEPTH: dict[Depth, int] = {"quick": 1, "standard": 1, "deep": 1, "all": 12, "current": 12}
ASC_LIMIT_BY_DEPTH: dict[Depth, int] = {"quick": 1000, "standard": 3000, "deep": 10000}


def _asc_limit(depth: Depth) -> int:
    if depth == "current":
        return settings.current_max_reviews
    return settings.max_reviews if depth == "all" else ASC_LIMIT_BY_DEPTH[depth]

_SSR = re.compile(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', re.S)
_ATOM = "{http://www.w3.org/2005/Atom}"
_IM = "{http://itunes.apple.com/rss}"


def _walk(node, kind: str, out: list):
    if isinstance(node, dict):
        if node.get("$kind") == kind:
            out.append(node)
        for v in node.values():
            _walk(v, kind, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, kind, out)


def _date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


async def _lookup(client: httpx.AsyncClient, ref: AppRef) -> dict:
    for cc in dict.fromkeys([ref.country, "us"]):
        r = await client.get("https://itunes.apple.com/lookup", params={"id": ref.app_id, "country": cc, "entity": "software"})
        if r.status_code == 200:
            results = r.json().get("results") or []
            if results:
                return results[0]
    raise AppNotFound(f"No App Store app with id “{ref.app_id}”.")


async def _storefront(client: httpx.AsyncClient, app_id: str, cc: str) -> tuple[str, list[Review], list[int] | None]:
    try:
        r = await client.get(f"https://apps.apple.com/{cc}/app/id{app_id}", params={"see-all": "reviews"})
        if r.status_code != 200:
            return cc, [], None
        m = _SSR.search(r.text)
        if not m:
            return cc, [], None
        data = json.loads(m.group(1))
    except (httpx.HTTPError, json.JSONDecodeError):
        return cc, [], None

    raw: list[dict] = []
    _walk(data, "Review", raw)
    reviews = []
    for x in raw:
        at = _date(x.get("date"))
        text = (x.get("contents") or "").strip()
        if not at or not text or not x.get("id"):
            continue
        reviews.append(Review(id=f"as:{x['id']}", text=text, title=x.get("title") or "", rating=int(x.get("rating") or 0), at=at, source=f"app:{cc}"))

    ratings: list[dict] = []
    _walk(data, "Ratings", ratings)
    hist = None
    if ratings and ratings[0].get("ratingCounts"):
        counts = [int(round(c)) for c in ratings[0]["ratingCounts"]]  # 5★ … 1★
        if len(counts) == 5:
            hist = counts[::-1]  # → 1★ … 5★
    return cc, reviews, hist


async def _rss_page(client: httpx.AsyncClient, app_id: str, cc: str, page: int) -> list[Review]:
    try:
        r = await client.get(f"https://itunes.apple.com/{cc}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/xml")
        if r.status_code != 200 or "<entry>" not in r.text:
            return []
        root = ET.fromstring(r.content)
    except (httpx.HTTPError, ET.ParseError):
        return []
    out = []
    for e in root.findall(f"{_ATOM}entry"):
        rating = e.findtext(f"{_IM}rating")
        if rating is None:
            continue  # the first entry is the app itself
        content = next((c.text for c in e.findall(f"{_ATOM}content") if c.get("type") == "text"), None)
        at = _date(e.findtext(f"{_ATOM}updated"))
        rid = e.findtext(f"{_ATOM}id")
        if not content or not at or not rid:
            continue
        out.append(Review(
            id=f"as:{rid}", text=content.strip(), title=e.findtext(f"{_ATOM}title") or "", rating=int(rating), at=at,
            source=f"app:{cc}", version=e.findtext(f"{_IM}version") or None,
        ))
    return out


async def _asc_reviews(client: httpx.AsyncClient, app_id: str, limit: int, progress: Progress) -> list[Review] | None:
    """App Store Connect API — full history, only for apps owned by the key's team."""
    if not settings.asc_enabled:
        return None
    import jwt  # PyJWT; imported lazily so the dependency stays optional

    try:
        key = Path(settings.asc_private_key_path).read_text()
        now = int(time.time())
        token = jwt.encode(
            {"iss": settings.asc_issuer_id, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"},
            key, algorithm="ES256", headers={"kid": settings.asc_key_id, "typ": "JWT"},
        )
    except Exception as e:
        log.warning("App Store Connect key unusable: %s", e)
        return None

    url: str | None = f"https://api.appstoreconnect.apple.com/v1/apps/{app_id}/customerReviews"
    params: dict | None = {"limit": 200, "sort": "-createdDate"}
    out: list[Review] = []
    while url and len(out) < limit:
        r = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            if not out:
                log.info("App Store Connect returned %s for %s — falling back to public data", r.status_code, app_id)
                return None
            break
        body = r.json()
        for item in body.get("data", []):
            a = item.get("attributes", {})
            at = _date(a.get("createdDate"))
            if at and a.get("body"):
                out.append(Review(id=f"asc:{item['id']}", text=a["body"].strip(), title=a.get("title") or "", rating=int(a.get("rating") or 0), at=at, source=f"asc:{a.get('territory', '').lower()}"))
        progress({"stage": "fetch", "fetched": len(out), "target": limit})
        url, params = body.get("links", {}).get("next"), None
    return out


async def fetch_appstore(ref: AppRef, depth: Depth, progress: Progress, *, on_page: Callable[[list[Review]], None] | None = None) -> FetchResult:
    limits = httpx.Limits(max_connections=64, max_keepalive_connections=64)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=httpx.Timeout(12.0, connect=5.0), limits=limits, follow_redirects=True, http2=False) as client:
        lookup_task = asyncio.create_task(_lookup(client, ref))
        asc_task = asyncio.create_task(_asc_reviews(client, ref.app_id, _asc_limit(depth), progress))

        fronts = list(dict.fromkeys([ref.country, *STOREFRONTS[: STOREFRONTS_BY_DEPTH[depth]]]))
        done = {"n": 0}
        seen: dict[str, Review] = {}

        async def track(coro):
            res = await coro
            revs = res[1] if isinstance(res, tuple) else res
            fresh = [r for r in revs if r.id not in seen]
            for r in fresh:
                seen[r.id] = r
            if fresh and on_page:
                on_page(fresh)
            done["n"] += 1
            progress({"stage": "fetch", "fetched": len(seen), "target": None, "sources": done["n"]})
            return res

        front_tasks = [asyncio.create_task(track(_storefront(client, ref.app_id, cc))) for cc in fronts]
        rss_fronts = list(dict.fromkeys([ref.country, *STOREFRONTS[: RSS_FRONTS_BY_DEPTH[depth] - 1]]))
        rss_tasks = [asyncio.create_task(track(_rss_page(client, ref.app_id, cc, p))) for cc in rss_fronts for p in range(1, RSS_PAGES + 1)]

        info = await lookup_task  # fail fast on a bad id
        progress({"stage": "meta", "name": info.get("trackName"), "icon": info.get("artworkUrl512") or info.get("artworkUrl100")})
        front_results = await asyncio.gather(*front_tasks)
        await asyncio.gather(*rss_tasks)
        asc = await asc_task

    hist = next((h for cc, _, h in front_results if cc == ref.country and h), None) or next((h for _, _, h in front_results if h), None)
    meta = AppMeta(
        store="app",
        app_id=ref.app_id,
        country=ref.country,
        name=info.get("trackName") or ref.app_id,
        developer=info.get("sellerName") or info.get("artistName") or "",
        icon=info.get("artworkUrl512") or info.get("artworkUrl100"),
        genre=info.get("primaryGenreName"),
        rating=info.get("averageUserRating"),
        ratings_count=info.get("userRatingCount") or (sum(hist) if hist else None),
        installs=None,
        url=info.get("trackViewUrl"),
        histogram=hist,
    )

    # Apple's public reviews mostly carry no version: the table covers a time window.
    floor = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=settings.period_days)
    if asc:
        return FetchResult(
            meta=meta, reviews=asc, sources=["App Store Connect API (complete history)"],
            scope=scopes.choose(asc, None, floor) if depth == "current" else None,
        )
    reviews = list(seen.values())
    return FetchResult(
        meta=meta,
        reviews=reviews,
        sources=[f"App Store public reviews ({sum(1 for _, r, _ in front_results if r)} storefronts)"],
        notes=["sample:featured"],
        scope=scopes.choose(reviews, None, floor) if depth == "current" else None,
    )
