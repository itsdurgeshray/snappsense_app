"""Sentiment over time, for a whole year, without analysing a whole year.

Each period's bar is the share of reviews in each sentiment (100% stacked),
so periods measured differently stay comparable:

* **exact**: Play runs count every review per day and star rating back as
  far as their time budget allows (only dates and ratings, no text). For
  those periods the star counts are exact, and each rating maps to
  sentiments with the mix observed in the analysed reviews. Apps of ordinary
  size get the whole year this way;
* **estimated**: for the biggest apps, older periods come from a thin,
  date-ordered segment of all reviews (one device type), calibrated per star
  against the exact window: true reviews ÷ segment reviews, per star. (We
  tried Play's "most relevant" feed first; it keeps old negative reviews far
  longer than old positive ones, which skewed older months.) A period needs
  every significant star rating in its sample;
* **empty**: too few reviews to say anything.

Sources without time-complete data (App Store public reviews) are treated
as a sample calibrated against the store's all-time star histogram.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from ..models import SENTIMENTS, Review

MIN_SAMPLE = 25  # sampled reviews a period needs for an estimate (thin periods widen toward this)
SHRINK = 4.0  # pseudo-reviews pulling thin star counts toward the surrounding star mix


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


def _per_star_factor(items: list[tuple[Review, str]], sample: list[tuple[datetime, int]], coverage: dict, data_end: datetime) -> dict[int, float]:
    """For each star: true reviews / sampled reviews, measured in the window where that star is complete.

    Multiplying a period's sampled count for a star by its factor estimates the
    true count; only the ratios between stars matter for shares.
    """
    true, seen = defaultdict(int), defaultdict(int)
    for r, _ in items:
        cut = coverage.get(r.rating)
        if cut is None or r.at >= cut:
            true[r.rating] += 1
    for at, star in sample:
        cut = coverage.get(star)
        if (cut is None or at >= cut) and at <= data_end:
            seen[star] += 1
    known = {st: true[st] / seen[st] for st in range(1, 6) if seen[st] >= 5 and true[st]}
    fallback = (sum(true[st] for st in known) / sum(seen[st] for st in known)) if known else 1.0
    return {st: known.get(st, fallback) for st in range(1, 6)}


def _from_counts(
    items: list[tuple[Review, str]],
    counts: dict[int, dict[str, int]],
    cut: dict[int, datetime | None],
    sample: list[tuple[datetime, int]] | None,
    histogram: list[int] | None,
    now: datetime,
    reach: dict[int, datetime | None] | None = None,
) -> dict[str, list[dict]]:
    """Trend from the completely read window (exact) plus the calibrated device sample (older periods).

    Each star rating is estimated on its own: where its sample reaches, from the
    sample (calibrated against the exact window); where it doesn't, its rate in
    the exact window is carried back. A period is only estimated when the
    dominant star ratings (half of all ratings) come from the sample: otherwise
    it would just repeat the recent mix, so it's left empty.
    """
    per_star: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r, s in items:
        per_star[r.rating][s] += 1
    mix = {star: {s: c / max(1, sum(d.values())) for s, c in d.items()} for star, d in per_star.items()}
    days = {st: [(datetime.fromisoformat(d), n) for d, n in counts.get(st, {}).items()] for st in range(1, 6)}
    data_end = max((d for st in days for d, _ in days[st]), default=now) + timedelta(days=1)
    cuts = [c for c in cut.values() if c is not None]
    exact_from = max(cuts) if cuts else datetime.min
    # Counts are per day: only whole days after the cut are complete.
    exact_day = datetime.min if exact_from == datetime.min else datetime(exact_from.year, exact_from.month, exact_from.day) + timedelta(days=1)

    def actual(b0: datetime, b1: datetime) -> dict[str, int]:
        """Sentiment of every analysed review in the period (they're complete inside the exact window)."""
        c = {s: 0 for s in SENTIMENTS}
        for r, s in items:
            if b0 <= r.at < b1:
                c[s] += 1
        return c

    def to_sentiment(stars: dict[int, float]) -> dict[str, float]:
        out = {s: 0.0 for s in SENTIMENTS}
        for st, n in stars.items():
            for s, p in mix.get(st, {}).items():
                out[s] += n * p
        return out

    # Calibration per star, in the exact window.
    sample = sample or []
    if reach is None:  # no reach given: treat each sampled star as complete
        reach = {st: None for _, st in sample}
    win_days = max(1.0, (data_end - exact_day).total_seconds() / 86400) if exact_day != datetime.min else 1.0
    true_w = {st: sum(n for d, n in days[st] if d >= exact_day) for st in range(1, 6)} if exact_day != datetime.min else {}
    rate_true = {st: true_w.get(st, 0) / win_days for st in range(1, 6)}
    by_star: dict[int, list[datetime]] = {st: [] for st in range(1, 6)}
    for at, st in sample:
        by_star[st].append(at)
    seen_w = {st: sum(1 for at in by_star[st] if at >= exact_day) for st in range(1, 6)}
    factor = {st: true_w[st] / seen_w[st] for st in range(1, 6) if seen_w.get(st, 0) >= 10 and true_w.get(st)}
    sampled_stars = [st for st in range(1, 6) if by_star[st] and st not in factor]
    if factor:
        # Too few sampled reviews in the exact window to calibrate a star on its own: use the common rate.
        common = sum(true_w[st] for st in factor) / sum(seen_w[st] for st in factor)
        factor.update({st: common for st in sampled_stars})
    elif sampled_stars and histogram and sum(histogram):
        # Nothing to calibrate against: match the sample's star mix to the store's all-time histogram.
        tot = sum(len(by_star[st]) for st in sampled_stars)
        factor = {st: (histogram[st - 1] / sum(histogram)) / (len(by_star[st]) / tot) for st in sampled_stars}

    # The dominant ratings: the fewest stars that make up half of all ratings.
    weights = list(histogram) if histogram and sum(histogram) else [true_w.get(st, 0) for st in range(1, 6)]
    total_w = sum(weights) or 1
    dominant: set[int] = set()
    acc = 0.0
    for st in sorted(range(1, 6), key=lambda st: -weights[st - 1]):
        dominant.add(st)
        acc += weights[st - 1] / total_w
        if acc >= 0.5:
            break
    first_sampled = min((min(by_star[st]) for st in factor if by_star[st]), default=None)

    def star_rate(st: int, b0: datetime, b1: datetime) -> tuple[float, bool]:
        """Reviews per day for one star in a period, and whether it came from the sample."""
        start = reach.get(st, datetime.max) if st in reach else datetime.max
        if st in factor and (start is None or start <= b0):
            floor_at = start or datetime.min
            for pad in (0, 7, 15, 30, 45):
                lo, hi = max(floor_at, b0 - timedelta(days=pad)), min(data_end, b1 + timedelta(days=pad))
                n = sum(1 for at in by_star[st] if lo <= at < hi)
                if n >= 5:
                    break
            span = max(1.0, (hi - lo).total_seconds() / 86400)
            return n / span * factor[st], True
        return rate_true.get(st, 0.0), False

    def estimate(b0: datetime, b1: datetime) -> tuple[dict[str, float], int] | None:
        if first_sampled is None or b1 <= first_sampled:
            return None  # nothing sampled this far back
        span = max(1.0, (b1 - b0).total_seconds() / 86400)
        vols, sampled = {}, set()
        for st in range(1, 6):
            rate, from_sample = star_rate(st, b0, b1)
            vols[st] = rate * span
            if from_sample:
                sampled.add(st)
        if not dominant <= sampled:
            return None  # the main ratings have no data here: don't repeat the recent mix
        sent = to_sentiment(vols)
        tot = sum(sent.values())
        if not tot:
            return None
        n = sum(1 for at, st in sample if b0 <= at < b1 and st in sampled)
        return {s: v / tot for s, v in sent.items()}, n

    out: dict[str, list[dict]] = {}
    for rng, bs in buckets(now).items():
        series = []
        for label, b0, b1 in bs:
            share = {s: 0.0 for s in SENTIMENTS}
            counts_out = None
            n = 0
            estimated = empty = False
            if b0 >= data_end:
                empty = True
            elif b0 >= exact_day:
                c = actual(b0, b1)
                n = sum(c.values())
                if n:
                    counts_out = c
                    share = {s: v / n for s, v in c.items()}
                else:
                    empty = True
            else:
                covered = (min(b1, data_end) - exact_day).total_seconds() / max(1.0, (min(b1, data_end) - b0).total_seconds()) if exact_day < b1 else 0.0
                est = estimate(b0, b1)
                part = actual(exact_day, b1) if exact_day < b1 else {}
                pn = sum(part.values())
                if covered >= 0.5 and pn:
                    share, n, estimated = {s: v / pn for s, v in part.items()}, pn, True
                elif est is not None:
                    (share, n), estimated = est, True
                else:
                    empty = True
            series.append({
                "label": label,
                "start": b0.isoformat(),
                "end": b1.isoformat(),
                "share": {s: round(v, 4) for s, v in share.items()},
                "counts": counts_out if counts_out is not None else ({s: 0 for s in SENTIMENTS} if empty else None),
                "n": n,
                "estimated": estimated,
                "empty": empty,
            })
        out[rng] = series
    return out


def build(
    items: list[tuple[Review, str]],
    coverage: dict[int, datetime | None] | None,
    histogram: list[int] | None,
    star_weights: dict[int, float],
    now: datetime,
    sample: list[tuple[datetime, int]] | None = None,
    counts: dict[int, dict[str, int]] | None = None,
    counts_cut: dict[int, datetime | None] | None = None,
    sample_reach: dict[int, datetime | None] | None = None,
) -> dict[str, list[dict]]:
    if counts is not None and counts_cut is not None:
        return _from_counts(items, counts, counts_cut, sample, histogram, now, sample_reach)
    # P(sentiment | star) from the analysed reviews: how each rating maps to sentiment.
    per_star: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r, s in items:
        per_star[r.rating][s] += 1
    mix = {star: {s: c / max(1, sum(d.values())) for s, c in d.items()} for star, d in per_star.items()}
    data_end = max((r.at for r, _ in items), default=now)

    if coverage is None:
        # No time-complete data: every review is a sample, calibrated to the store's histogram.
        exact_from = datetime.max
        sample = [(r.at, r.rating) for r, _ in items]
        factor = {s: star_weights.get(s, 1.0) for s in range(1, 6)}
    else:
        cuts = [c for c in coverage.values() if c is not None]
        exact_from = max(cuts) if cuts else datetime.min  # every star complete from here on
        sample = sample or []
        factor = _per_star_factor(items, sample, coverage, data_end)

    # Stars that matter: a period can only be estimated if its sample has each of them.
    hist_total = sum(histogram) if histogram else 0
    important = {st for st in range(1, 6) if hist_total and histogram[st - 1] / hist_total >= 0.05} or set(range(1, 6))

    def estimate(b0: datetime, b1: datetime) -> tuple[dict[str, float], int] | None:
        stars = defaultdict(int)
        for at, star in sample:
            if b0 <= at < b1:
                stars[star] += 1
        n = sum(stars.values())
        if n < MIN_SAMPLE or any(stars[st] < 3 for st in important if mix.get(st)):
            return None  # a star rating missing from the sample would skew the mix
        weighted = {st: v * factor.get(st, 1.0) for st, v in stars.items()}
        tot = sum(weighted.values()) or 1.0
        share = {s: 0.0 for s in SENTIMENTS}
        for st, w in weighted.items():
            for s, p in mix.get(st, {}).items():
                share[s] += (w / tot) * p
        return share, n

    def exact(b0: datetime, b1: datetime) -> tuple[dict[str, int], int]:
        c = {s: 0 for s in SENTIMENTS}
        for r, s in items:
            if b0 <= r.at < b1:
                c[s] += 1
        return c, sum(c.values())

    out: dict[str, list[dict]] = {}
    for rng, bs in buckets(now).items():
        series = []
        for label, b0, b1 in bs:
            share = {s: 0.0 for s in SENTIMENTS}
            counts = None
            n = 0
            estimated = empty = False
            if b0 >= data_end:
                empty = True  # the feed hasn't published reviews for this period yet
            elif b0 >= exact_from:
                counts, n = exact(b0, b1)
                empty = n == 0
                if n:
                    share = {s: v / n for s, v in counts.items()}
            else:
                # Part exact (the period ends inside the complete window), part not.
                part, pn = exact(max(b0, exact_from), b1) if exact_from < b1 else ({}, 0)
                covered = (min(b1, data_end) - max(b0, exact_from)).total_seconds() / max(1.0, (min(b1, data_end) - b0).total_seconds()) if exact_from < b1 else 0.0
                est = estimate(b0, b1)
                if covered >= 0.5 and pn >= MIN_SAMPLE or (est is None and pn):
                    share, n, estimated = {s: v / pn for s, v in part.items()}, pn, True
                elif est is not None:
                    (share, n), estimated = est, True
                else:
                    empty = True
            series.append({
                "label": label,
                "start": b0.isoformat(),
                "end": b1.isoformat(),
                "share": {s: round(v, 4) for s, v in share.items()},
                "counts": counts if counts is not None else ({s: 0 for s in SENTIMENTS} if empty else None),
                "n": n,
                "estimated": estimated,
                "empty": empty,
            })
        out[rng] = series
    return out
