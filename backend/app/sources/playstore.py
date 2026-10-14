"""Google Play fetcher.

Speed comes from big pages and sharding. Play's review feed is a single
cursor per (sort, star-filter) pair; a page of 4,500 reviews takes ~4 s
(~1,100 reviews/s, vs ~140/s with the usual 200-review pages). Reading one
cursor is strictly sequential, so we read five at once, one per star rating.
Metadata is fetched in parallel with the first pages.

Sample depths (quick/standard/deep) give each star an equal share of the
budget, passing unused shares on. "current" and "all" runs instead page the
stars in step through time: a star that's further back than the others
waits for them, so when the review limit is reached every star has been read
back to about the same date. That makes the window where *every* review is
known as long as the limit allows (equal shares would leave the busiest
star, usually 5★, covering only a fraction of it).

Each star's coverage is recorded: reviews newer than its cutoff are complete,
not sampled, so trends can use exact counts (see trends.py).

The default "current" depth reads what the version picker needs: each star
stops collecting reviews once it's past the start of the recent versions
(scope.py), or a year back. Apps of ordinary size are read completely for
the year that way. For the year-long sentiment trend of bigger apps, a
second set of cursors runs alongside from the start: one device segment of
the newest-first feed (Play's device filter 3, mostly tablets), a few
percent of all reviews in date order and not ranked by relevance, so it
reaches a year back in a handful of pages and calibrates cleanly against the
window we read completely (trends.py).

Built for very large runs as well:

* pages are handed to `on_page` as they arrive, so analysis overlaps download;
* reviews already in the review store are recognised: once a shard reaches
  reviews we already have, it replays the stored ones instead of downloading
  them again;
* transient errors and rate limits back off exponentially, and the whole
  fetch stops gracefully at a time budget, keeping what it has.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import socket
import sys
import threading
import time
from concurrent.futures import Executor
from datetime import datetime, timedelta, timezone
from typing import Callable

from google_play_scraper import Sort, app as gp_app
from google_play_scraper.constants.request import Formats
from google_play_scraper.exceptions import NotFoundError
import httpx

from .. import scope as scopes
from ..config import settings
from ..links import AppRef
from ..models import AppMeta, Depth, FetchResult, Review

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per page is noise

# google-play-scraper calls urlopen() with no timeout, so a stalled response
# from Google would hang a shard forever. Sockets without their own timeout
# (httpx sets explicit ones) now give up after this many seconds and retry.
SOCKET_TIMEOUT = 20.0
socket.setdefaulttimeout(SOCKET_TIMEOUT)
PAGE_TIMEOUT = SOCKET_TIMEOUT * 2  # hard ceiling per page, even if a read trickles

FIRST_PAGE = 1000  # first request per star: quick first results (later pages can be bigger)
PAGE = max(1000, min(4500, settings.play_page))  # later requests: up to Play's maximum, ~8× the throughput of small pages
TAIL = 200  # newest-first tail used to decide we're past a release
REPLAY = 1000  # stored reviews replayed per step
TREND_PAGES = 8  # max pages per star of the device-segment sample for the year-long trend
TREND_DEVICE = 3  # Play's device filter: a small, date-ordered segment (mostly tablets)

SYNC_SLACK = timedelta(hours=3)  # a star may run this far ahead (back in time) of the others…
SYNC_SHARE = 0.25  # …or this share of their covered span, whichever is more (keeps stars downloading in parallel)
# Big pages parsed at once (settings.play_inflight) bounds memory.
TOTAL_BY_DEPTH: dict[Depth, int] = {"quick": 1000, "standard": 4000, "deep": 10000}
DISCOVERY_EVERY = 1  # pages between checks for which versions are current
EMPTY_RETRIES = 3  # tries before an empty page counts as the real end of a feed
KNOWN_PAGE = 0.8  # a page this full of stored reviews means we've reached stored history

Progress = Callable[[dict], None]
OnPage = Callable[[list[Review]], None]
Coverage = dict[int, datetime | None]


class AppNotFound(LookupError):
    pass


def target_for(depth: Depth) -> int:
    if depth == "current":
        return settings.current_max_reviews
    return settings.max_reviews if depth == "all" else TOTAL_BY_DEPTH[depth]


def floor_for(depth: Depth, now: datetime | None = None) -> datetime | None:
    """Oldest review date a "current" run may read (a year back); None for other depths."""
    if depth != "current":
        return None
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return now - timedelta(days=settings.trend_days)


def gp_page(
    app_id: str, lang: str, country: str, sort: Sort, count: int, star: int | None, token: str | None, device: int | None = None
) -> tuple[list[dict], str | None]:
    """One page of reviews and the next page's token (None at the end).

    google_play_scraper.reviews() would reuse the first request's page size for
    every later page, and it swallows network errors (returning an empty last
    page, which would look like the end of the history). This raises instead,
    so the caller retries, and takes any page size up to 4,500.
    """
    body = Formats.Reviews.build_body(app_id, sort.value, count, "null" if star is None else star, "null" if device is None else device, token)
    r = _client().post(Formats.Reviews.build(lang=lang, country=country), content=body, headers={"content-type": "application/x-www-form-urlencoded"})
    if r.status_code == 404:
        raise NotFoundError("App not found (404).")
    r.raise_for_status()
    text = r.text
    if "PlayGatewayError" in text:
        raise RuntimeError("Google Play rate limit")  # retried with backoff by the caller
    # ")]}'\n\n" + JSON whose payload is another JSON string. Parsed once (the
    # scraper parses it twice), and each review slimmed down straight away.
    data = r.content
    del r, text
    outer = json.loads(data[data.find(b"\n\n") + 2 :])
    del data
    payload = outer[0][2]
    del outer
    if payload is None:
        return [], None
    inner = json.loads(payload)
    del payload
    try:
        nxt = inner[-2][-1]
    except (IndexError, TypeError):
        nxt = None
    items = inner[0] if inner and inner[0] else []
    return [x for x in map(_lean, items) if x], nxt if isinstance(nxt, str) else None


_local = threading.local()


def _client() -> httpx.Client:
    """One keep-alive client per worker thread: no new TLS handshake per page, certificates verified."""
    c = getattr(_local, "client", None)
    if c is None:
        c = _local.client = httpx.Client(timeout=httpx.Timeout(PAGE_TIMEOUT, connect=10.0), follow_redirects=True)
    return c


def _get(item, *path):
    try:
        for p in path:
            item = item[p]
        return item
    except (IndexError, TypeError, KeyError):
        return None


def _lean(item) -> dict | None:
    """Only the fields we use (the scraper's full dicts cost ~2 KB per review: a lot at 4,500 a page).
    Dates in UTC (the scraper uses the server's local time zone)."""
    ts = _get(item, 5, 0)
    if not ts or not _get(item, 0):
        return None
    return {
        "reviewId": item[0],
        "content": _get(item, 4),
        "score": _get(item, 2),
        "thumbsUpCount": _get(item, 6),
        "reviewCreatedVersion": _get(item, 10),
        "at": datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None),
    }


def _intern(s: str | None) -> str | None:
    return sys.intern(s) if s else None


def _to_review(r: dict, lang: str, country: str) -> Review | None:
    text = (r.get("content") or "").strip()
    if not text or not r.get("at"):
        return None
    return Review(
        id=f"gp:{r['reviewId']}",
        text=text,
        rating=int(r.get("score") or 0),
        at=r["at"],
        source=sys.intern(f"play:{lang}/{country}"),  # shared, not one copy per review
        thumbs=int(r.get("thumbsUpCount") or 0),
        version=_intern(r.get("reviewCreatedVersion") or r.get("appVersion")),
    )


class _Budget:
    """Shares a review budget between shards; an exhausted shard's leftover goes to the rest."""

    def __init__(self, total: int, n: int):
        self.total = total
        self.counts = [0] * n
        self.exhausted = [False] * n
        self.parked = [False] * n
        self.cond = asyncio.Condition()

    def quota(self, i: int) -> int:
        spent = sum(c for c, e in zip(self.counts, self.exhausted) if e)
        live = sum(1 for e in self.exhausted if not e) or 1
        return max(TAIL, (self.total - spent) // live)

    async def finish(self, i: int, exhausted: bool) -> None:
        async with self.cond:
            self.exhausted[i] = exhausted
            self.parked[i] = not exhausted
            self.cond.notify_all()

    async def wait_for_more(self, i: int) -> bool:
        """Parked at quota: wait until another shard frees budget (True) or everyone is done (False)."""
        async with self.cond:
            while True:
                if self.counts[i] < self.quota(i):
                    self.parked[i] = False
                    return True
                if all(e or p for e, p in zip(self.exhausted, self.parked)):
                    self.cond.notify_all()
                    return False
                await self.cond.wait()

    def allowance(self, i: int) -> int:
        """How many reviews shard i may ask for next."""
        return self.quota(i) - self.counts[i]

    def size(self, i: int, default: int) -> int:
        """Reviews to ask for next; equal shares just take full pages."""
        return default

    async def ready(self, i: int) -> None:
        """Called before each request; equal shares need no pacing."""

    def release(self, i: int) -> None:
        """Called after each request, whatever happened."""

    def advance(self, i: int, oldest: datetime | None) -> None:
        """Called after each page with the shard's oldest review."""


class _Paced(_Budget):
    """One review limit for all stars, paged in step through time (see module docstring)."""

    def __init__(self, total: int, n: int):
        super().__init__(total, n)
        self.oldest: list[datetime | None] = [None] * n
        self.done = [False] * n
        self.inflight = 0

    def remaining(self) -> int:
        return self.total - sum(self.counts)

    def quota(self, i: int) -> int:
        return self.counts[i] + max(0, self.remaining())

    async def finish(self, i: int, exhausted: bool) -> None:
        async with self.cond:
            self.done[i] = True
            self.cond.notify_all()

    async def wait_for_more(self, i: int) -> bool:
        return self.remaining() > 0  # the limit is shared: once it's spent, everyone stops

    def allowance(self, i: int) -> int:
        # Split between the stars downloading right now, so parallel requests can't overshoot the limit.
        return max(0, self.remaining()) // max(1, self.inflight)

    def size(self, i: int, default: int) -> int:
        """Ask for only as many reviews as keep this star level in time with the others.

        Star feeds fill at very different rates (WhatsApp: 4,500 2★ reviews
        span ~46 days, 4,500 5★ reviews ~2): fixed-size pages would spend the
        shared limit on sparse stars' old history while the busy star barely
        moves, and the window where every star is complete would shrink.
        """
        mine = self.oldest[i]
        if mine is None or not self.counts[i]:
            return min(default, FIRST_PAGE)  # first page: learn this star's pace
        others = [o for j, o in enumerate(self.oldest) if j != i and not self.done[j] and o is not None]
        if not others:
            return default
        slowest = max(others)  # the star that reaches back least far
        if mine >= slowest:
            return default  # this star is the one holding everyone back: full speed
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rate = self.counts[i] / max(60.0, (now - mine).total_seconds())  # reviews per second
        lead = max(SYNC_SLACK, SYNC_SHARE * (now - slowest))
        target = slowest - lead
        need = rate * max(0.0, (mine - target).total_seconds())
        return int(min(default, max(TAIL, need)))

    async def ready(self, i: int) -> None:
        async with self.cond:
            while self.remaining() > 0:
                mine = self.oldest[i]
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                behind = [o for j, o in enumerate(self.oldest) if j != i and not self.done[j]]
                # Wait while another star is well short of how far back this one already reaches.
                if mine is None or not any(o is None or o - mine > max(SYNC_SLACK, SYNC_SHARE * (now - o)) for o in behind):
                    break
                try:
                    await asyncio.wait_for(self.cond.wait(), 1.0)
                except asyncio.TimeoutError:
                    pass
            self.inflight += 1

    def release(self, i: int) -> None:
        self.inflight = max(0, self.inflight - 1)

    def advance(self, i: int, oldest: datetime | None) -> None:
        if oldest is not None:
            self.oldest[i] = oldest
        loop = asyncio.get_running_loop()
        loop.create_task(self._notify())

    async def _notify(self) -> None:
        async with self.cond:
            self.cond.notify_all()


async def fetch_play(
    ref: AppRef,
    depth: Depth,
    pool: Executor,
    progress: Progress,
    lang: str = "en",
    *,
    on_page: OnPage | None = None,
    known: dict[str, Review] | None = None,
    prior: Coverage | None = None,
    on_meta: Callable[[AppMeta], None] | None = None,
) -> FetchResult:
    """`known`/`prior`: reviews from the store and the per-star coverage of the run that stored them."""
    loop = asyncio.get_running_loop()
    country = ref.country
    known = known or {}
    deadline = time.monotonic() + settings.fetch_budget_seconds
    attempts = 3 if depth in ("quick", "standard") else 6

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
        if on_meta:
            on_meta(meta)
        return meta

    meta_task = asyncio.create_task(get_meta())
    total = target_for(depth)
    floor = floor_for(depth)
    current = depth == "current"
    sorts = [Sort.NEWEST] + ([Sort.MOST_RELEVANT] if depth == "deep" else [])
    plan = [(star, so) for so in sorts for star in range(1, 6)]
    budget = _Paced(total, len(plan)) if depth in ("current", "all") else _Budget(total, len(plan))
    seen: set[str] = set()
    fetched = {"n": 0}
    shard_out: list[list[Review]] = [[] for _ in plan]
    shard_done: list[bool] = [False] * len(plan)
    live: dict[str, set[str] | None] = {"versions": None}  # None until the newest reviews tell us
    # Exact reviews per day for each star (from what's collected), and how far back each is complete.
    started = time.monotonic()
    trend_days: dict[int, dict] = {s: {} for s in range(1, 6)}
    trend_cut: dict[int, datetime | None] = {}
    vcount: dict[str, int] = {}  # reviews per version so far

    def emit(batch: list[Review]) -> None:
        fresh = [r for r in batch if r.id not in seen]
        seen.update(r.id for r in fresh)
        for r in fresh:
            if r.version:
                vcount[r.version] = vcount.get(r.version, 0) + 1
        fetched["n"] += len(fresh)
        if fresh and on_page:
            on_page(fresh)
        progress({"stage": "fetch", "fetched": fetched["n"], "target": None if depth in ("all", "current") else total, "limit": total})

    def discover() -> None:
        """Once every star has been read back to a common date with enough reviews, decide the current versions."""
        if live["versions"] is not None or not current:
            return
        if any(not out and not done for out, done in zip(shard_out[:5], shard_done[:5])):
            return
        span = max((out[-1].at for out, done in zip(shard_out[:5], shard_done[:5]) if out and not done), default=None)
        recent = sorted(
            (r for out in shard_out[:5] for r in out if r.version and (span is None or r.at >= span)),
            key=lambda r: r.at, reverse=True,
        )
        if len(recent) >= scopes.LIVE_SAMPLE or all(shard_done[:5]) or (span is not None and floor is not None and span <= floor):
            live["versions"] = scopes.live_versions(recent)

    inflight = asyncio.Semaphore(max(1, settings.play_inflight))

    sampling = asyncio.Semaphore(max(1, settings.trend_lanes))  # the trend sample's own lanes (one per star by default)

    async def page(star: int | None, sort: Sort, token, count: int = PAGE, device: int | None = None):
        for attempt in range(attempts):
            try:
                async with (sampling if device else inflight):
                    res = await asyncio.wait_for(call(gp_page, ref.app_id, lang, country, sort, count, star, token, device), PAGE_TIMEOUT)
                # Google sometimes answers with an empty page and no next-page token
                # (a soft failure, ~10 s in), which looks exactly like the end of a
                # star's history. Retry it; only a repeatedly empty page is the end.
                if not res[0] and res[1] is None and attempt < min(attempts, EMPTY_RETRIES) - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return res
            except NotFoundError:
                return None
            except Exception as e:  # network hiccups and rate limits: back off and retry
                if attempt == attempts - 1 or time.monotonic() > deadline:
                    log.warning("play shard %s failed: %s", star, e)
                    raise
                await asyncio.sleep(min(15.0, 0.5 * 2**attempt) * (0.75 + random.random() / 2))

    async def shard(i: int, star: int, sort: Sort) -> tuple[list[Review], str | None, object]:
        out, done, stored_from, _ = await collect(i, star, sort)
        if sort == Sort.NEWEST:
            # Exact reviews per day for the trend, from what was collected.
            days = trend_days[star]
            for r in out:
                d = r.at.date()
                days[d] = days.get(d, 0) + 1
            trend_cut[star] = None if done == "end" else floor if done == "floor" else min((r.at for r in out), default=None)
        return out, done, stored_from

    async def collect(i: int, star: int, sort: Sort) -> tuple[list[Review], str | None, object, str | None]:
        """Collects reviews for the table. Returns (reviews, done, stored_from, next page token).

        `done`: "end" = the star's whole history was read, "floor" = read back
        to the oldest date allowed, "release" = read back past the start of
        the current versions, None = stopped early (budget, time or errors). `stored_from`: how far back the store is contiguous for
        this star after the run (None = complete history, "run" = this run).
        """
        out = shard_out[i]
        ids: set[str] = set()
        token = None
        replay: list[Review] = []  # stored history, served as pages instead of downloaded
        replaying = False
        jumped = False
        cutoff_known = prior.get(star, "missing") if (prior is not None and sort == Sort.NEWEST) else "missing"

        async def stop(done: str | None, stored_from):
            shard_done[i] = True
            await budget.finish(i, exhausted=done is not None)
            discover()
            return out, done, stored_from, token

        while True:
            stored_from = cutoff_known if jumped else "run"
            if budget.counts[i] >= budget.quota(i):
                await budget.finish(i, exhausted=False)
                if not await budget.wait_for_more(i):
                    shard_done[i] = True
                    discover()
                    return out, None, stored_from, token
            if time.monotonic() > deadline:
                log.info("play fetch hit its %ss budget", settings.fetch_budget_seconds)
                return await stop(None, stored_from)

            network_end = False
            past_floor = False
            if replay:
                batch, replay[:] = replay[:REPLAY], replay[REPLAY:]
                replaying = True
            else:
                if replaying and (cutoff_known is None or (floor is not None and cutoff_known <= floor)):
                    # The stored history went back as far as this run needs.
                    return await stop("end" if cutoff_known is None and floor is None else "floor", cutoff_known)
                replaying = False
                await budget.ready(i)
                want = budget.size(i, FIRST_PAGE if token is None else PAGE)
                want = max(TAIL, min(want, budget.allowance(i)))
                try:
                    res = await page(star, sort, token, want)
                except Exception:
                    return await stop(None, stored_from)
                finally:
                    budget.release(i)
                if res is None:
                    return await stop("end", None)
                raw, token = res
                batch = [r for r in (_to_review(x, lang, country) for x in raw) if r and r.id not in ids]
                past_floor = floor is not None and any(x.get("at") and x["at"] < floor for x in raw)
                network_end = not raw or token is None
                # Reached reviews we already have? Replay the stored history instead of re-downloading it.
                if not jumped and cutoff_known != "missing" and batch and sum(r.id in known for r in batch) >= KNOWN_PAGE * len(batch):
                    jumped = True
                    in_batch = {b.id for b in batch}
                    replay = sorted(
                        (
                            r for r in known.values()
                            if r.rating == star and r.id not in ids and r.id not in in_batch
                            and (cutoff_known is None or r.at >= cutoff_known) and (floor is None or r.at >= floor)
                        ),
                        key=lambda r: r.at, reverse=True,
                    )
            if floor is not None:
                batch = [r for r in batch if r.at >= floor]
            batch = [r for r in batch if r.id not in ids]
            out.extend(batch)
            ids.update(r.id for r in batch)
            budget.counts[i] = len(out)
            budget.advance(i, out[-1].at if out else None)
            emit(batch)
            discover()

            if past_floor:
                return await stop("floor", stored_from)
            if current:
                recent = scopes.recent_versions(vcount)
                if len(recent) >= scopes.RECENT_VERSIONS and scopes.past_release_start(out[-TAIL:], recent):
                    return await stop("release", stored_from)
            if network_end and not replay:
                return await stop("end", None)
            if meta_task.done() and meta_task.exception():
                return await stop("end", None)  # bad app id — stop paging

    year_ago = (floor or datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=365)) + timedelta(days=30)

    # The trend sample, kept as it arrives so a run that hits its time budget
    # still uses every page it got. reach[star]: the sample is complete from
    # this date on (None = the star's whole history).
    sample_rows: dict[int, list[tuple[datetime, int]]] = {s: [] for s in range(1, 6)}
    sample_reach: dict[int, datetime | None] = {}

    async def trend_sample(star: int) -> None:
        """One device segment of the newest-first feed for one star: a thin, date-ordered
        slice of all reviews that reaches a year back in a few pages."""
        rows = sample_rows[star]
        token = None
        until = started + settings.trend_budget_seconds
        for _ in range(TREND_PAGES):
            if time.monotonic() > until:
                return
            try:
                res = await page(star, Sort.NEWEST, token, 4500, device=TREND_DEVICE)
            except Exception:
                return
            if res is None:
                sample_reach[star] = None
                return
            raw, token = res
            rows += [(x["at"], star) for x in raw if x.get("at")]
            if rows:
                sample_reach[star] = rows[-1][0]
            if not raw or token is None:
                sample_reach[star] = None if rows else sample_reach.get(star)  # empty: no usable data for this star
                return
            if rows[-1][0] < year_ago - timedelta(days=30):
                return

    shards = [asyncio.create_task(shard(i, star, so)) for i, (star, so) in enumerate(plan)]
    # Busiest stars first: they need the most pages to reach a year back.
    samplers = {st: asyncio.create_task(trend_sample(st)) for st in (5, 4, 1, 3, 2)} if current else {}
    sample_reach_out: dict[int, datetime | None] | None = None
    try:
        meta = await meta_task  # raises AppNotFound early if the id is wrong
    except BaseException:
        for t in [*shards, *samplers.values()]:
            t.cancel()
        raise
    results = await asyncio.gather(*shards)

    merged: dict[str, Review] = {}
    for revs, _, _ in results:
        for r in revs:
            merged.setdefault(r.id, r)
    reviews = list(merged.values())

    # Coverage per star: None = complete history; a date = complete back to it.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    coverage: Coverage = {}
    store_coverage: Coverage = {}
    for star, (revs, done, stored_from) in zip(range(1, 6), results[:5]):
        if done == "end":
            coverage[star] = None
        elif done == "floor":
            coverage[star] = floor
        else:  # past the release start, or stopped early: complete back to its oldest review
            coverage[star] = min((r.at for r in revs), default=now)
        if stored_from == "run":
            store_coverage[star] = coverage[star]
        elif stored_from is None or coverage[star] is None:
            store_coverage[star] = None
        else:
            store_coverage[star] = min(stored_from, coverage[star])
    complete = all(done == "end" for _, done, _ in results[:5])

    table_scope = None
    sample: list[tuple[datetime, int]] | None = None
    if current:
        live["versions"] = live["versions"] if live["versions"] is not None else scopes.live_versions(sorted(reviews, key=lambda r: r.at, reverse=True))
        # The date from which every star was read completely (None = complete history).
        cuts = [c for c in coverage.values() if c is not None]
        complete_from = max(cuts) if cuts else None
        period_floor = now - timedelta(days=settings.period_days)
        table_scope = scopes.choose(reviews, live["versions"], period_floor, complete_from)
        if complete_from is None or complete_from <= floor:
            for t in samplers.values():
                t.cancel()  # the newest-first feed already covers the whole year exactly
        else:
            left = max(1.0, started + settings.trend_budget_seconds - time.monotonic())
            done, pending = await asyncio.wait(samplers.values(), timeout=left)
            for t in pending:
                t.cancel()
            sample = [x for st in range(1, 6) for x in sample_rows[st]]
            # Stars with sampled reviews: complete back to where they reached (None = whole history).
            sample_reach_out = {st: sample_reach.get(st) for st in range(1, 6) if sample_rows[st]}

    return FetchResult(
        meta=meta,
        reviews=reviews,
        sources=[f"Google Play ({lang}, {country.upper()})"],
        coverage=coverage,
        store_coverage=store_coverage,
        notes=["complete"] if complete else [],
        scope=table_scope,
        trend_sample=sample,
        trend_sample_reach=sample_reach_out,
        trend_counts={s: {d.isoformat(): n for d, n in days.items()} for s, days in trend_days.items()} if current else None,
        trend_coverage=dict(trend_cut) if current else None,
    )
