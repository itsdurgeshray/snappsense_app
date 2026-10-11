"""Domain types shared by the fetchers, the analysis pipeline and the API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .scope import Scope

Store = Literal["play", "app"]
Depth = Literal["quick", "standard", "deep", "all", "current"]

SENTIMENTS = ("delighted", "happy", "neutral", "angry", "frustrated")


@dataclass(slots=True)
class Review:
    id: str
    text: str
    rating: int  # 1-5 stars
    at: datetime
    title: str = ""
    source: str = ""  # e.g. "play:en/us", "app:gb"
    thumbs: int = 0
    version: str | None = None


@dataclass(slots=True)
class AppMeta:
    store: Store
    app_id: str
    country: str
    name: str
    developer: str = ""
    icon: str | None = None
    genre: str | None = None
    rating: float | None = None
    ratings_count: int | None = None
    installs: str | None = None
    url: str | None = None
    # All-time star histogram, index 0 = 1 star ... index 4 = 5 stars.
    histogram: list[int] | None = None


@dataclass(slots=True)
class FetchResult:
    meta: AppMeta
    reviews: list[Review]
    sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Per star (1-5): oldest review date the shard fully covers, or None when
    # the shard reached the end of history. Missing entirely = not a
    # time-complete source (e.g. App Store featured reviews).
    coverage: dict[int, datetime | None] | None = None
    # Coverage of the review store after this run (it can reach further back
    # than this run's own reviews when stored history was reused).
    store_coverage: dict[int, datetime | None] | None = None
    # What the feedback table covers ("current" runs): see scope.py.
    scope: "Scope | None" = None
    # (date, stars) sampled across the year for the sentiment trend (trends.py).
    trend_sample: list[tuple[datetime, int]] | None = None
    # Per star with sampled reviews: the sample is complete from this date on (None = whole history).
    trend_sample_reach: dict[int, datetime | None] | None = None
    # Exact reviews per day ("YYYY-MM-DD") for each star, counted back as far as
    # the trend budget allowed, and how far back each star's counts are complete.
    trend_counts: dict[int, dict[str, int]] | None = None
    trend_coverage: dict[int, datetime | None] | None = None
