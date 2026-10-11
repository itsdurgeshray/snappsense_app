"""Play fetching at scale, against a simulated store: shared budget, complete
coverage, reuse of stored history, rate-limit retries, and the review store."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.analysis.features import Feat
from app.links import parse_link

from .factories import as_page
from app.sources import playstore
from app.store import ReviewStore

NOW = datetime(2026, 10, 10, 12, 0)
SIZES = {1: 500, 2: 40, 3: 300, 4: 900, 5: 3000}  # few 2★ reviews, many 5★


class FakePlay:
    """Newest-first review feeds per star, 200 per page, like Google Play."""

    def __init__(self, sizes=SIZES, flaky: bool = False, extra_new: int = 0):
        self.calls = 0
        self.flaky = flaky  # every page fails once (e.g. 429) before succeeding
        self.failed: set = set()
        self.feeds = {}
        for star, n in sizes.items():
            total = n + extra_new
            self.feeds[star] = [
                {"reviewId": f"{star}-{i - extra_new}", "content": f"review {i} about things", "score": star, "at": NOW - timedelta(minutes=10 * i - 10 * extra_new), "thumbsUpCount": 0}
                for i in range(total)
            ]

    def reviews(self, app_id, lang, country, sort, count, filter_score_with, continuation_token):
        self.calls += 1
        feed = self.feeds[filter_score_with] if filter_score_with is not None else [x for f in self.feeds.values() for x in f]
        start = continuation_token.pos if continuation_token else 0
        if self.flaky and (filter_score_with, start) not in self.failed:
            self.failed.add((filter_score_with, start))
            raise ConnectionError("429 Too Many Requests")
        page = feed[start : start + count]
        end = start + count >= len(feed)
        return page, SimpleNamespace(token=None if end else "t", pos=start + count)

    def app(self, app_id, lang, country):
        return {"title": "Big App", "histogram": [1000, 100, 600, 2000, 9000]}


@pytest.fixture()
def fake(monkeypatch):
    f = FakePlay()
    monkeypatch.setattr(playstore, "gp_page", as_page(f.reviews))
    monkeypatch.setattr(playstore, "gp_app", f.app)
    return f


def run(depth="standard", **kw):
    async def go():
        with ThreadPoolExecutor(8) as pool:
            return await playstore.fetch_play(parse_link("com.big.app", "us"), depth, pool, lambda ev: None, **kw)

    return asyncio.run(go())


def test_unused_budget_moves_to_other_stars(fake):
    res = run("standard")  # 4,000 = 800 per star, but 2★ only has 40 and 3★ 300
    by_star = {s: sum(r.rating == s for r in res.reviews) for s in range(1, 6)}
    assert by_star[2] == 40 and by_star[3] == 300 and by_star[1] == 500  # exhausted: all of them
    assert len(res.reviews) >= 4000 - 200  # the leftover went to 4★/5★
    assert res.coverage[2] is None and res.coverage[3] is None and res.coverage[5] is not None


def test_all_reads_every_review_and_says_so(fake, monkeypatch):
    monkeypatch.setattr(playstore.settings.__class__, "max_reviews", property(lambda self: 100_000), raising=False)
    pages = []
    res = run("all", on_page=pages.append)
    assert len(res.reviews) == sum(SIZES.values())
    assert "complete" in res.notes and all(c is None for c in res.coverage.values())
    assert sum(len(p) for p in pages) == len(res.reviews)  # streamed page by page, no duplicates


def test_cap_keeps_newest(fake, monkeypatch):
    monkeypatch.setattr(playstore.settings.__class__, "max_reviews", property(lambda self: 2000), raising=False)
    res = run("all")
    assert 1800 <= len(res.reviews) <= 2000 + 5 * playstore.TAIL and "complete" not in res.notes


def test_rate_limits_are_retried(monkeypatch):
    f = FakePlay(flaky=True)
    monkeypatch.setattr(playstore, "gp_page", as_page(f.reviews))
    monkeypatch.setattr(playstore, "gp_app", f.app)
    monkeypatch.setattr(playstore.asyncio, "sleep", _no_sleep)
    res = run("standard")
    assert len(res.reviews) >= 3800 and len(f.failed) >= 5


async def _no_sleep(*_):
    return None


def test_second_run_reuses_stored_history(monkeypatch):
    monkeypatch.setattr(playstore.settings.__class__, "max_reviews", property(lambda self: 100_000), raising=False)
    big = {1: 5000, 2: 400, 3: 3000, 4: 9000, 5: 30000}
    first = FakePlay(sizes=big)
    monkeypatch.setattr(playstore, "gp_page", as_page(first.reviews))
    monkeypatch.setattr(playstore, "gp_app", first.app)
    res1 = run("all")
    calls_first = first.calls

    # Later: 30 new reviews per star. Only the new pages should be downloaded.
    later = FakePlay(sizes=big, extra_new=30)
    monkeypatch.setattr(playstore, "gp_page", as_page(later.reviews))
    known = {r.id: r for r in res1.reviews}
    res2 = run("all", known=known, prior=res1.store_coverage)
    assert len(res2.reviews) == sum(big.values()) + 5 * 30
    assert "complete" in res2.notes
    assert later.calls == 5 < calls_first  # one page per star, then the stored history


def test_store_roundtrip_and_pruning(tmp_path):
    store = ReviewStore(tmp_path / "r.db", max_reviews=5)
    res = FakePlay(sizes={1: 3, 2: 0, 3: 0, 4: 0, 5: 0})
    revs = [playstore._to_review(x, "en", "us") for x in res.feeds[1]]
    feats = {revs[0].id: Feat("angry", "Bug Report", "it breaks", None)}
    store.save("play:a:us", revs, feats, {1: None, 2: NOW})
    loaded, lf, cov = store.load("play:a:us")
    assert {r.id for r in loaded} == {r.id for r in revs} and loaded[0].at == revs[0].at
    assert lf == feats and cov == {1: None, 2: NOW}
    store.save("play:b:us", revs, {})  # pushes the store over budget: the older app goes
    assert store.count("play:a:us") == 0 and store.count("play:b:us") == 3


def test_a_stalled_page_is_retried_not_hung(monkeypatch):
    """A response that never arrives must time out and be retried."""
    import time as _time

    f = FakePlay(sizes={1: 300, 2: 0, 3: 0, 4: 0, 5: 0})
    stalled = set()
    real = f.reviews

    def sometimes_stall(*a):
        key = (a[5], a[6].pos if a[6] else 0)
        if key == (1, 0) and key not in stalled:
            stalled.add(key)
            _time.sleep(0.5)  # longer than the page timeout below
        return real(*a)

    monkeypatch.setattr(playstore, "gp_page", as_page(sometimes_stall))
    monkeypatch.setattr(playstore, "gp_app", f.app)
    monkeypatch.setattr(playstore, "PAGE_TIMEOUT", 0.2)
    res = run("standard")
    assert sum(r.rating == 1 for r in res.reviews) == 300 and stalled


def test_paced_stars_reach_the_same_date(monkeypatch):
    """5★ reviews arrive 10× faster than 1★: paged in step, the busy star gets most of the
    limit, so the window where every star is complete is several times longer."""

    class Uneven(FakePlay):
        def __init__(self):
            self.calls, self.flaky, self.failed = 0, False, set()
            minutes = {1: 10, 2: 20, 3: 15, 4: 5, 5: 1}
            self.feeds = {
                s: [{"reviewId": f"{s}-{i}", "content": "x y", "score": s, "at": NOW - timedelta(minutes=m * (i + 1))} for i in range(40000 // m)]
                for s, m in minutes.items()
            }

    f = Uneven()
    monkeypatch.setattr(playstore, "gp_page", as_page(f.reviews))
    monkeypatch.setattr(playstore, "gp_app", f.app)
    monkeypatch.setattr(playstore.settings.__class__, "max_reviews", property(lambda self: 12_000), raising=False)
    res = run("all")
    cuts = [c for c in res.coverage.values() if c is not None]
    complete_from = max(cuts)  # every star is complete from here on
    assert NOW - complete_from > timedelta(days=4)  # equal shares (2,400 each) would give 5★ only 40 hours


def test_store_keeps_newest_per_app_and_trims_coverage(tmp_path):
    store = ReviewStore(tmp_path / "r.db", max_reviews=1_000_000, per_app=100)
    revs = [playstore._to_review({"reviewId": str(i), "content": "x", "score": 1, "at": NOW - timedelta(hours=i)}, "en", "us") for i in range(250)]
    store.save("play:a:us", revs, {}, {1: None, 2: NOW - timedelta(days=30)})
    loaded, _, cov = store.load("play:a:us")
    assert len(loaded) == 100 and min(r.at for r in loaded) > NOW - timedelta(hours=101)
    assert cov[1] is not None and cov[1] >= NOW - timedelta(hours=101)  # no longer "complete history"
    assert cov[2] == cov[1]
