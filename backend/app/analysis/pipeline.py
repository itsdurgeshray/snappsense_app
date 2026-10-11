"""Turn fetched reviews into the report the dashboard renders.

Pure CPU work: runs in a worker thread so the event loop keeps streaming
progress.

Cost model, so huge apps stay fast and fit in a small server's memory:

* per-review work (features.py) is linear and done once per review, usually
  while the download is still running;
* everything else is bounded: the semantic space is fitted on a sample of at
  most FIT_SAMPLE reviews, clustering is fitted on a sample per category and
  then assigns every concern, and titles read a sample of each issue. Counts,
  shares, trends and review lists always use every review.

The feedback table only lists *concerns* — problems and feature requests a
product team should act on — from the reviews in the report's scope (by
default: the versions people use now, see scope.py). Trends use every
fetched review. Praise never appears in it, and the category
breakdown is computed from the same concerns, so every category shown there
has at least one row in the table.
"""

from __future__ import annotations

import re
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone

from ..models import SENTIMENTS, FetchResult, Review
from . import categorize, cluster, evidence, trends
from .features import Feat, extract, full_text
from .solutions import domain_for, match as match_play, suggest
from .titles import title as make_title

MAX_ISSUES = 20
# Bump when the report's meaning or shape changes: cached reports from older code are then ignored.
SCHEMA = 4
FIT_SAMPLE = 12000  # reviews used to learn the app's vocabulary / semantic space
MIN_FR_SIZE = 2  # a one-off request isn't a trend (unless it's all there is)
_STAR_DEFAULT = {1: "frustrated", 2: "angry", 3: "neutral", 4: "happy", 5: "delighted"}
# How much a category hurts the business, all else equal.
_SEVERITY = {"Crash": 1.3, "Transactional": 1.25, "Bug Report": 1.1, "Support": 1.0, "Performance": 1.0, "Pricing & Ads": 0.9, "UI/UX": 0.85, "Feature Request": 0.7}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _star_weights(sample: Counter, histogram: list[int] | None) -> dict[int, float]:
    n = sum(sample.values())
    if not histogram or not sum(histogram) or not n:
        return {s: 1.0 for s in range(1, 6)}
    h = sum(histogram)
    return {s: (histogram[s - 1] / h) / (sample[s] / n) if sample[s] else 1.0 for s in range(1, 6)}


def _priorities(rows: list[dict], weights: list[float]) -> None:
    """High / Medium / Low from impact (share of weighted concerns), anger and category severity."""
    total = sum(weights) or 1.0
    scores = []
    for row, w in zip(rows, weights):
        impact = w / total
        anger = max(0.0, min(1.0, (5 - row["avgRating"]) / 4))
        scores.append(impact * (0.5 + anger) * _SEVERITY.get(row["category"], 1.0))
        row["impact"] = round(100 * impact, 1)
    top = max(scores, default=0) or 1.0
    high_slots = 4
    for i in sorted(range(len(rows)), key=lambda i: -scores[i]):
        row, rel = rows[i], scores[i] / top
        level = "high" if rel >= 0.45 and row["count"] >= 5 and row["impact"] >= 5 and high_slots > 0 else "medium" if rel >= 0.15 or row["count"] >= 15 else "low"
        if row["category"] == "Feature Request" and level == "high" and row["count"] < 20:
            level = "medium"  # requests rarely outrank broken flows
        if level == "high":
            high_slots -= 1
        row["priority"] = level


def _merge_same_cause(issues: list[cluster.Issue], vocab: set[str], domain: str | None = None) -> list[cluster.Issue]:
    """Clusters that map to the same specific root cause become one row."""
    by_play: dict[str, cluster.Issue] = {}
    out: list[cluster.Issue] = []
    for issue in issues:
        play = match_play(issue, make_title(issue, vocab), domain)
        if play is None:
            out.append(issue)
            continue
        if play not in by_play:
            by_play[play] = issue
            out.append(issue)
            continue
        keep = by_play[play]
        rows = sorted(
            zip(keep.reviews + issue.reviews, keep.concerns + issue.concerns, keep.centrality + issue.centrality),
            key=lambda t: -t[2],
        )
        keep.reviews, keep.concerns, keep.centrality = [list(x) for x in zip(*rows)]
        keep.terms = keep.terms or issue.terms
    out.sort(key=lambda i: i.size, reverse=True)
    return out


def _sample(reviews: list[Review], n: int) -> list[Review]:
    """A uniform sample that is stable as reviews arrive: chosen by a hash of
    each review's id, so a refresh with a few new reviews keeps (almost) the
    same sample and the report doesn't shuffle."""
    return reviews if len(reviews) <= n else sorted(reviews, key=lambda r: zlib.crc32(r.id.encode()))[:n]


def _scope_dict(scope, scoped: list[Review], concerns_by_cat) -> dict | None:
    if scope is None:
        return None
    out = scope.to_dict()
    if scope.kind == "versions":
        # Reviews and complaints per version, for the picker and the table's summary line.
        totals = {v: {"reviews": 0, "concerns": 0, "since": None} for v in scope.versions}
        dates: dict[str, list] = {v: [] for v in scope.versions}
        for r in scoped:
            if r.version in totals:
                totals[r.version]["reviews"] += 1
                dates[r.version].append(r.at)
        for v, ds in dates.items():
            if ds:
                ds.sort()
                totals[v]["since"] = ds[int(0.02 * len(ds))].date().isoformat()  # release start, ignoring early betas
        for revs, _, _ in concerns_by_cat.values():
            for r in revs:
                if r.version in totals:
                    totals[r.version]["concerns"] += 1
        out["totals"] = totals
    return out


def analyze(
    fetch: FetchResult, now: datetime | None = None, feats: dict[str, Feat] | None = None
) -> tuple[dict, dict[str, list[dict]], list[tuple[str, cluster.Issue, str]]]:
    """Returns (report, reviews_by_issue_id, polish_input).

    `feats`: per-review results computed earlier (keyed by review id); any
    review missing from it is analysed here.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    reviews = [r for r in fetch.reviews if 1 <= r.rating <= 5]
    meta = fetch.meta
    feats = feats if feats is not None else {}

    # 1. Per-review sentiment, category and concern (cached per review)
    scope = fetch.scope
    labelled: list[tuple[Review, str]] = []
    scoped: list[Review] = []  # the reviews the feedback table is about
    sent_by_id: dict[str, str] = {}
    concerns_by_cat: dict[str, tuple[list[Review], list[str], list[str | None]]] = defaultdict(lambda: ([], [], []))
    for r in reviews:
        f = feats.get(r.id)
        if f is None:
            f = feats[r.id] = extract(r)
        labelled.append((r, f.sentiment))
        sent_by_id[r.id] = f.sentiment
        if scope is not None and not scope.includes(r):
            continue
        scoped.append(r)
        if f.concern is not None:
            revs, cons, frs = concerns_by_cat[f.category]
            revs.append(r)
            cons.append(f.concern)
            frs.append(f.feature)

    star_counts = Counter(r.rating for r in reviews)
    weights = _star_weights(star_counts, meta.histogram)

    # 2. All-time sentiment: the store's full star histogram, split per star by
    #    the sentiment mix we observed for that star in the text.
    per_star: dict[int, Counter] = defaultdict(Counter)
    for r, s in labelled:
        per_star[r.rating][s] += 1
    totals = {s: 0.0 for s in SENTIMENTS}
    if meta.histogram and sum(meta.histogram):
        for star in range(1, 6):
            h = meta.histogram[star - 1]
            mix = per_star.get(star)
            if mix and sum(mix.values()):
                n = sum(mix.values())
                for s, c in mix.items():
                    totals[s] += h * c / n
            else:
                totals[_STAR_DEFAULT[star]] += h
        total_reviews = sum(meta.histogram)
        totals_basis = "store_histogram"
    else:
        for r, s in labelled:
            totals[s] += weights[r.rating]
        total_reviews = len(labelled)
        totals_basis = "sample"

    # 3. Issues: cluster each category's concerns in a semantic space fitted
    #    on this app's own reviews.
    fit = _sample(reviews, FIT_SAMPLE)
    vocab_df = Counter(w for r in fit for w in set(re.findall(r"[a-z]+", r.text.lower())))
    vocab = {w for w, n in vocab_df.items() if n >= 3}  # words in 3+ reviews: anything else is likely a typo
    domain = domain_for(meta.genre)
    issues_by_cat: dict[str, list[cluster.Issue]] = {}
    if concerns_by_cat:
        embedder = cluster.Embedder([full_text(r) for r in fit], meta.name)
        for cat in categorize.ACTIONABLE:
            if cat not in concerns_by_cat:
                continue
            revs, cons, feats = concerns_by_cat[cat]
            found = cluster.cluster_category(cat, revs, cons, embedder, feats if cat == "Feature Request" else None)
            if cat == "Feature Request":
                recurring = [i for i in found if i.size >= MIN_FR_SIZE]
                found = recurring or found[:1]
            else:
                found = _merge_same_cause(found, vocab, domain)
            if found:
                issues_by_cat[cat] = found

    def weight(issue: cluster.Issue) -> float:
        # Plain mention counts: easy to explain, and not distorted by the
        # equal-per-star sampling (star weights are for all-time sentiment only).
        return float(issue.size)

    # Every category gets its biggest issue; remaining slots go by size.
    def pick(size) -> list[cluster.Issue]:
        live = {cat: [i for i in v if size(i) > 0] for cat, v in issues_by_cat.items()}
        top = [max(v, key=size) for v in live.values() if v]
        rest = sorted((i for v in live.values() for i in v if i not in top and size(i) >= 2), key=size, reverse=True)
        return top + rest[: max(0, MAX_ISSUES - len(top))]

    chosen: list[cluster.Issue] = pick(weight)
    versioned = scope is not None and scope.kind == "versions"
    if versioned:
        # The browser re-ranks rows for whichever versions are picked, so send
        # the top issues of every version (issues are clustered once, across them).
        for v in scope.versions:
            for issue in pick(lambda i, v=v: sum(r.version == v for r in i.reviews)):
                if issue not in chosen:
                    chosen.append(issue)
    chosen.sort(key=weight, reverse=True)

    # 4. Category breakdown from the same concerns the table shows.
    cat_weight = {cat: sum(weight(i) for i in v) for cat, v in issues_by_cat.items()}
    total_w = sum(cat_weight.values()) or 1.0
    categories = [
        {"label": cat, "share": round(100 * w / total_w, 1), "count": sum(i.size for i in issues_by_cat[cat])}
        for cat, w in sorted(cat_weight.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # 5. Rows + full review lists (served on demand by the API)
    baseline = evidence.Baseline(scoped)
    feedback: list[dict] = []
    issue_reviews: dict[str, list[dict]] = {}
    polish_input: list[tuple[str, cluster.Issue, str]] = []
    for idx, issue in enumerate(chosen):
        iid = f"{_slug(issue.category)}-{idx}"
        headline = make_title(issue, vocab)
        sents = Counter(sent_by_id[r.id] for r in issue.reviews)
        feedback.append({
            "id": iid,
            "category": issue.category,
            "feedback": headline,
            "solution": suggest(issue, headline, domain),
            "evidence": evidence.collect(issue.reviews, baseline, by_version=not versioned),
            "count": issue.size,
            "share": round(100 * issue.size / max(1, len(scoped)), 1),
            "sentiment": sents.most_common(1)[0][0],
            "avgRating": round(sum(r.rating for r in issue.reviews) / issue.size, 2),
            "latest": max(r.at for r in issue.reviews).date().isoformat(),
        })
        if versioned:
            # Per-version stats, so picking versions re-ranks the table instantly.
            by_v: dict[str, dict] = {}
            for r in issue.reviews:
                d = by_v.setdefault(r.version, {"n": 0, "stars": 0, "latest": "", "sent": {}})
                d["n"] += 1
                d["stars"] += r.rating
                day = r.at.date().isoformat()
                if day > d["latest"]:
                    d["latest"] = day
                s_ = sent_by_id[r.id]
                d["sent"][s_] = d["sent"].get(s_, 0) + 1
            feedback[-1]["byVersion"] = by_v
        issue_reviews[iid] = [
            {
                "text": r.text,
                "title": r.title or None,
                "rating": r.rating,
                "date": r.at.date().isoformat(),
                "thumbs": r.thumbs,
                "sentiment": sent_by_id[r.id],
                "concern": c,
                "version": r.version,
            }
            for r, c in zip(issue.reviews, issue.concerns)
        ]
        polish_input.append((iid, issue, headline))

    _priorities(feedback, [weight(i) for i in chosen])

    # 6. Trends
    trend = trends.build(labelled, fetch.coverage, meta.histogram, weights, now, fetch.trend_sample, fetch.trend_counts, fetch.trend_coverage, fetch.trend_sample_reach)

    exact_from = None
    if fetch.coverage is not None:
        cuts = [c for c in fetch.coverage.values() if c is not None]
        exact_from = max(cuts).isoformat() if cuts else "all"
    dates = [r.at for r in scoped]
    positive = totals["delighted"] + totals["happy"]
    tot = sum(totals.values()) or 1

    report = {
        "schema": SCHEMA,
        "store": meta.store,
        "appId": meta.app_id,
        "country": meta.country,
        "app": {
            "name": meta.name,
            "developer": meta.developer,
            "icon": meta.icon,
            "genre": meta.genre,
            "rating": round(meta.rating, 2) if meta.rating else None,
            "ratingsCount": meta.ratings_count,
            "installs": meta.installs,
            "url": meta.url,
        },
        "totals": {s: round(v) for s, v in totals.items()},
        # All-time star ratings straight from the store (exact). Falls back to
        # the analysed sample when a store gives no histogram.
        "ratings": {str(st): (meta.histogram[st - 1] if meta.histogram and sum(meta.histogram) else star_counts.get(st, 0)) for st in range(5, 0, -1)},
        "ratingsBasis": "store" if meta.histogram and sum(meta.histogram) else "sample",
        "totalReviews": total_reviews,
        "totalsBasis": totals_basis,
        "positiveShare": round(100 * positive / tot, 1),
        "categories": categories,
        "feedback": feedback,
        "trends": trend,
        "sample": {
            "analyzed": len(scoped),
            "fetched": len(reviews),
            "scope": _scope_dict(scope, scoped, concerns_by_cat),
            "concerns": sum(len(v[0]) for v in concerns_by_cat.values()),
            "oldest": min(dates).isoformat() if dates else None,
            "newest": max(dates).isoformat() if dates else None,
            "exactFrom": exact_from,
            "featuredOnly": "sample:featured" in fetch.notes,
            "complete": "complete" in fetch.notes,  # every review the store has (Play)
            "sources": fetch.sources,
        },
        "domain": domain,
    }
    return report, issue_reviews, polish_input
