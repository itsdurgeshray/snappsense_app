"""Sentiment over time, aware of how much of each period we actually saw.

Play shards are time-complete back to a per-star cutoff (see playstore.py).
For every bucket and star rating:

* fully covered   → exact counts
* partly covered  → counts scaled by the covered fraction
* not covered     → extrapolated from that star's own observed review rate,
                    but only within a bounded horizon of its coverage

Coverage runs from each star's cutoff to the newest review seen (the Play feed
lags real time by hours). A bucket with any star that can be neither counted
nor extrapolated is returned empty rather than invented.
Sources without time completeness (App Store featured reviews) fall back to
histogram-weighted sample counts, flagged as estimated.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from ..models import SENTIMENTS, Review

MIN_FRACTION = 0.15
HORIZON_FACTOR = 10  # extrapolate up to 10× a star's observed span…
MIN_HORIZON = timedelta(days=7)  # …and never less than a week


def _month_start(d: datetime, back: int) -> datetime:
    y, m = d.year, d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return datetime(y, m, 1)


def buckets(now: datetime) -> dict[str, list[tuple[str, datetime, datetime]]]:
    today = datetime(now.year, now.month, now.day) + timedelta(days=1)
    out: dict[str, list[tuple[str, datetime, datetime]]] = {}
    out["1w"] = [((today - timedelta(days=7 - i)).strftime("%a"), today - timedelta(days=7 - i), today - timedelta(days=6 - i)) for i in range(7)]
    out["1m"] = [((today - timedelta(days=30 - 5 * i)).strftime("%b %-d"), today - timedelta(days=30 - 5 * i), today - timedelta(days=25 - 5 * i)) for i in range(6)]
    out["3m"] = [((today - timedelta(weeks=13 - i)).strftime("%b %-d"), today - timedelta(weeks=13 - i), today - timedelta(weeks=12 - i)) for i in range(13)]
    for key, n in (("6m", 6), ("1y", 12)):
        out[key] = [
            (_month_start(now, n - 1 - i).strftime("%b"), _month_start(now, n - 1 - i), _month_start(now, n - 2 - i) if i < n - 1 else today)
            for i in range(n)
        ]
    return out


def build(
    items: list[tuple[Review, str]],
    coverage: dict[int, datetime | None] | None,
    histogram: list[int] | None,
    star_weights: dict[int, float],
    now: datetime,
) -> dict[str, list[dict]]:
    # P(sentiment | star) across the whole sample — used for imputation.
    per_star: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r, s in items:
        per_star[r.rating][s] += 1
    p_sent = {
        star: {s: c / max(1, sum(d.values())) for s, c in d.items()} for star, d in per_star.items()
    }
    data_end = max((r.at for r, _ in items), default=now)
    # Observed review rate per star (reviews/second) over its covered span.
    rate: dict[int, float] = {}
    horizon: dict[int, datetime] = {}
    if coverage is not None:
        n_star = defaultdict(int)
        for r, _ in items:
            if coverage.get(r.rating) is None or r.at >= coverage[r.rating]:
                n_star[r.rating] += 1
        for star in range(1, 6):
            cut = coverage.get(star)
            if cut is None:
                continue
            span = max(3600.0, (data_end - cut).total_seconds())
            rate[star] = n_star[star] / span
            horizon[star] = cut - max(MIN_HORIZON, timedelta(seconds=span * HORIZON_FACTOR))

    out: dict[str, list[dict]] = {}
    for rng, bs in buckets(now).items():
        series = []
        for label, b0, b1 in bs:
            raw: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
            for r, s in items:
                if b0 <= r.at < b1:
                    raw[r.rating][s] += 1

            counts = {s: 0.0 for s in SENTIMENTS}
            estimated = False
            empty = False

            if coverage is None:
                # Not time-complete: weight by star so the mix matches the store.
                for star, d in raw.items():
                    for s, c in d.items():
                        counts[s] += c * star_weights.get(star, 1.0)
                estimated = True
                empty = not raw
            elif b0 >= data_end:
                empty = True  # the feed hasn't published reviews for this period yet
            else:
                span = (b1 - b0).total_seconds()
                for star in range(1, 6):
                    cut = coverage.get(star)
                    lo = b0 if cut is None else max(b0, cut)
                    hi = min(b1, data_end) if cut is not None else b1
                    frac = max(0.0, (hi - lo).total_seconds() / span)
                    if frac >= 0.999 or (cut is None and b1 > data_end):
                        for s, c in raw[star].items():
                            counts[s] += c
                        if b1 > data_end:
                            estimated = True  # current, still-filling period
                    elif frac >= MIN_FRACTION:
                        for s, c in raw[star].items():
                            counts[s] += c / frac
                        estimated = True
                    elif star in rate and b1 > horizon[star]:
                        n = rate[star] * span
                        for s, p in p_sent.get(star, {}).items():
                            counts[s] += n * p
                        estimated = True
                    else:
                        empty = True
                        break
                if empty:
                    counts = {s: 0.0 for s in SENTIMENTS}

            series.append({
                "label": label,
                "start": b0.isoformat(),
                "end": b1.isoformat(),
                "counts": {s: round(v) for s, v in counts.items()},
                "estimated": estimated,
                "empty": empty,
            })
        out[rng] = series
    return out
