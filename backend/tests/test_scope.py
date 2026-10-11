"""The feedback table's scope: current versions (rollouts included), with time fallbacks."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import scope as scopes
from app.links import parse_link

from .factories import as_page
from app.models import Review
from app.sources import playstore

NOW = datetime.now(timezone.utc).replace(tzinfo=None)


def version_at(age: timedelta, i: int) -> str | None:
    """A new release every 2 days (v20.0 is the newest), each rolled out gradually."""
    if i % 8 == 0:
        return None  # ~12% of reviews carry no version, like real Play data
    k = age.days // 2
    if k == 0 and i % 10 >= 6:
        k = 1  # mid-rollout: 40% of users are still on the previous release
    return f"{20 - k}.0"


class VersionedPlay:
    def __init__(self, per_star=None, minutes=10, versions=True):
        per_star = per_star or {1: 600, 2: 300, 3: 400, 4: 900, 5: 3000}
        self.pages = 0
        self.feeds = {
            star: [
                {
                    "reviewId": f"{star}-{i}", "content": "it keeps crashing after the update", "score": star,
                    "at": NOW - timedelta(minutes=minutes * (i + 1)),
                    "reviewCreatedVersion": version_at(timedelta(minutes=minutes * (i + 1)), i) if versions else None,
                }
                for i in range(n)
            ]
            for star, n in per_star.items()
        }

    def reviews(self, app_id, lang, country, sort, count, filter_score_with, continuation_token):
        self.pages += 1
        if filter_score_with is None:  # the unfiltered "most relevant" feed: every star, any order
            feed = [x for f in self.feeds.values() for x in f[::7]]
        else:
            feed = self.feeds[filter_score_with]
        start = continuation_token.pos if continuation_token else 0
        end = start + count >= len(feed)
        return feed[start : start + count], SimpleNamespace(token=None if end else "t", pos=start + count)

    def app(self, app_id, lang, country):
        return {"title": "Versioned App"}


def run(fake, monkeypatch, depth="current"):
    monkeypatch.setattr(playstore, "gp_page", as_page(fake.reviews))
    monkeypatch.setattr(playstore, "gp_app", fake.app)

    async def go():
        with ThreadPoolExecutor(8) as pool:
            return await playstore.fetch_play(parse_link("com.v.app", "us"), depth, pool, lambda ev: None)

    return asyncio.run(go())


def test_picker_offers_recent_complete_versions_and_opens_on_the_latest(monkeypatch):
    fake = VersionedPlay(per_star={1: 6000, 2: 3000, 3: 4000, 4: 9000, 5: 30000}, minutes=1)  # 5★: 20 days of reviews
    monkeypatch.setattr(playstore.settings.__class__, "current_max_reviews", property(lambda self: 100_000), raising=False)
    res = run(fake, monkeypatch)
    sc = res.scope
    assert sc.kind == "versions" and sc.default == ("20.0",)
    assert sc.versions[0] == "20.0" and list(sc.versions) == sorted(sc.versions, key=scopes.version_key, reverse=True)
    assert 4 <= len(sc.versions) <= scopes.RECENT_VERSIONS + 2
    # Paging stopped after the recent versions (~6 releases ≈ 12-14 days), not at the 5★ feed's 20 days.
    assert NOW - min(r.at for r in res.reviews) < timedelta(days=17)
    assert len(res.reviews) < sum(len(f) for f in fake.feeds.values()) - 5000
    assert res.trend_sample  # the year-long trend sample came back too
    # Every offered version was read completely: its reviews start after the complete-from date.
    for v in sc.versions:
        assert sum(r.version == v for r in res.reviews) >= scopes.MIN_VERSION_REVIEWS
    assert all(sc.includes(r) == (r.version in sc.versions) for r in res.reviews)


def test_review_limit_offers_only_fully_read_versions(monkeypatch):
    """A huge app hits the review limit: only versions read completely are offered."""
    fake = VersionedPlay(per_star={1: 6000, 2: 3000, 3: 4000, 4: 9000, 5: 30000}, minutes=1)
    monkeypatch.setattr(playstore.settings.__class__, "current_max_reviews", property(lambda self: 20_000), raising=False)
    res = run(fake, monkeypatch)
    cuts = [c for c in res.coverage.values() if c]
    assert cuts and res.scope.kind == "versions" and res.scope.default == ("20.0",)
    for v in res.scope.versions:
        first = sorted(r.at for r in res.reviews if r.version == v)
        assert first[int(0.02 * len(first))] >= max(cuts)


def test_latest_with_few_reviews_preselects_previous_versions():
    t = NOW
    reviews = [Review(id=f"n{i}", text="x", rating=3, at=t - timedelta(hours=i), version="3.0") for i in range(40)]
    reviews += [Review(id=f"o{i}", text="x", rating=3, at=t - timedelta(days=3, hours=i), version="2.0") for i in range(90)]
    sc = scopes.choose(reviews, {"3.0", "2.0"}, t - timedelta(days=90))
    assert sc.default == ("3.0", "2.0")


def test_no_version_data_falls_back_to_last_90_days(monkeypatch):
    fake = VersionedPlay(per_star={1: 300, 2: 100, 3: 100, 4: 300, 5: 600}, minutes=60 * 6, versions=False)
    res = run(fake, monkeypatch)
    assert res.scope.kind == "period"
    assert timedelta(days=89) <= NOW - res.scope.since <= timedelta(days=90, minutes=5)
    assert all(NOW - r.at <= timedelta(days=366) for r in res.reviews)  # trends read up to a year


def test_beta_reviews_dont_hide_a_version():
    t = NOW
    reviews = [Review(id=f"b{i}", text="x", rating=3, at=t - timedelta(days=200 + i), version="5.0") for i in range(3)]  # betas
    reviews += [Review(id=f"r{i}", text="x", rating=3, at=t - timedelta(hours=i), version="5.0") for i in range(600)]
    sc = scopes.choose(reviews, {"5.0"}, t - timedelta(days=90), complete_from=t - timedelta(days=30))
    assert sc.versions == ("5.0",) and t - sc.since < timedelta(days=30)


def test_version_ordering_and_short_labels():
    assert sorted(["9.1.90.2270", "9.1.84.2231", "9.1.100.1"], key=scopes.version_key)[-1] == "9.1.100.1"
    assert scopes.short_version("9.1.90.2270") == "9.1.90"
    assert scopes.short_version("449.0.0.43.105") == "449.0" and scopes.short_version("2.24.0") == "2.24"
