"""Domain types shared by the fetchers, the analysis pipeline and the API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Store = Literal["play", "app"]
Depth = Literal["quick", "standard", "deep"]

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
