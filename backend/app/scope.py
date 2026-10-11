"""Which reviews the feedback table is about: app versions.

A report should describe the app as it is today, and a fixed-size sample
hides how much time it spans. So the table is built per version:

* the fetch reads back past the start of the RECENT_VERSIONS newest versions
  that have at least MIN_VERSION_REVIEWS reviews (bounded by time and a
  review ceiling);
* every such version whose reviews were read completely is offered in the
  version picker; the table opens on the **latest** one (the newest version
  that a real share of users has, so a handful of beta reviews don't count),
  adding the previous versions only if the latest has very few reviews;
* reviews without a version can't be attributed and stay out of the table
  (they still count in the trends).

Without version data (App Store public reviews) the table covers the last
`period_days` instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Literal

from .models import Review

LIVE_SAMPLE = 1000  # newest versioned reviews used to tell which versions are current
LIVE_SHARE = 0.05  # a version is current if it has at least this share of them
BOUNDARY_SHARE = 0.10  # paging back stops once current versions fall below this share
START_PERCENTILE = 0.02  # ignore the earliest 2% of current-version reviews (beta testers)
MIN_REVIEWS = 500  # time-window fallback: fewer than this, widen
RECENT_VERSIONS = 6  # versions the fetch tries to cover completely
MIN_VERSION_REVIEWS = 30  # a version needs this many reviews to be offered
MIN_DEFAULT_REVIEWS = 100  # the latest version alone below this: preselect previous ones too


def version_key(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.\-_ ]", v))


def short_version(v: str) -> str:
    """9.1.90.2270 → 9.1.90 · 449.0.0.43.105 → 449.0 · 2.24.0 → 2.24"""
    parts = v.split(".")[:3]
    while len(parts) > 2 and parts[-1] == "0":
        parts.pop()
    return ".".join(parts)


def _labels(versions) -> dict[str, str]:
    """Short labels, unless two versions would look the same (2.26.39.74 vs .79): then the full one."""
    short = {v: short_version(v) for v in versions}
    clash = {s for s in short.values() if list(short.values()).count(s) > 1}
    return {v: (v if s in clash else s) for v, s in short.items()}


def live_versions(newest: list[Review]) -> set[str]:
    """Current versions from the newest reviews (newest first). Empty if they carry no versions."""
    versioned = [r.version for r in newest if r.version][:LIVE_SAMPLE]
    if not versioned:
        return set()
    counts: dict[str, int] = {}
    for v in versioned:
        counts[v] = counts.get(v, 0) + 1
    return {v for v, n in counts.items() if n / len(versioned) >= LIVE_SHARE}


def recent_versions(counts: dict[str, int], k: int = RECENT_VERSIONS) -> set[str]:
    """The k newest versions with enough reviews so far."""
    sig = [v for v, n in counts.items() if n >= MIN_VERSION_REVIEWS]
    return set(sorted(sig, key=version_key)[-k:])


def past_release_start(oldest_page: list[Review], live: set[str]) -> bool:
    """True once a shard's oldest reviews are mostly on versions before the current ones."""
    versioned = [r for r in oldest_page if r.version]
    if not live or len(versioned) < 20:
        return False
    return sum(r.version in live for r in versioned) / len(versioned) < BOUNDARY_SHARE


@dataclass
class Scope:
    kind: Literal["versions", "period"]
    since: datetime
    versions: tuple[str, ...] = ()  # offered in the picker, newest first
    default: tuple[str, ...] = ()  # preselected (the latest version)
    widened: bool = False  # time window wider than asked, for lack of reviews
    _set: frozenset = field(default=frozenset(), repr=False, compare=False)

    def __post_init__(self):
        self._set = frozenset(self.versions)

    def includes(self, r: Review) -> bool:
        if self.kind == "versions":
            return r.version in self._set
        return r.at >= self.since

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "since": self.since.isoformat(),
            "versions": list(self.versions),
            "labels": _labels(self.versions),
            "default": list(self.default),
            "widened": self.widened,
        }


def _first_seen(dates: list[datetime]) -> datetime:
    dates = sorted(dates)
    return dates[int(START_PERCENTILE * len(dates))]


def choose(reviews: Iterable[Review], live: set[str] | None, floor: datetime, complete_from: datetime | None = None) -> Scope:
    """Pick the table's scope from the fetched reviews.

    `live`: versions with a real share of the newest reviews (the latest of
    them is preselected). `floor`: the time window's start when there's no
    version data. `complete_from`: the date from which every star rating was
    read completely (None = complete history); versions released before it
    were only partly read and aren't offered.
    """
    reviews = list(reviews)
    by_version: dict[str, list[datetime]] = {}
    for r in reviews:
        if r.version:
            by_version.setdefault(r.version, []).append(r.at)
    offered = []
    for v, dates in by_version.items():
        if len(dates) < MIN_VERSION_REVIEWS:
            continue
        if complete_from is None or _first_seen(dates) >= complete_from:
            offered.append(v)
    offered.sort(key=version_key, reverse=True)
    offered = offered[: RECENT_VERSIONS + 2]
    if offered:
        live_offered = [v for v in offered if live and v in live]
        latest = live_offered[0] if live_offered else offered[0]
        default = [latest]
        for v in offered[offered.index(latest) + 1 :]:
            if sum(len(by_version[d]) for d in default) >= MIN_DEFAULT_REVIEWS:
                break
            default.append(v)
        since = min(_first_seen(by_version[v]) for v in offered)
        return Scope("versions", since, tuple(offered), tuple(default))
    # No version data: a time window, as far back as the data goes within it.
    limit = max(floor, complete_from) if complete_from else floor
    oldest = min((r.at for r in reviews if r.at >= limit), default=limit)
    return Scope("period", oldest, widened=False)
