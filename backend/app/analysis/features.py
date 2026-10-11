"""Per-review analysis: sentiment, category and the concern it states.

This is the only stage whose cost grows with every review, so it is kept
independent of everything else:

* it runs on each page of reviews as soon as it arrives, overlapping with the
  rest of the download;
* its results are small and are stored with the review, so a later run only
  analyses reviews it hasn't seen before.

Everything after it (clustering, titles, priorities) works on these results
and is bounded by sampling, so its cost stays roughly flat as apps grow.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Review
from . import categorize, sentiment

# Bump when the rules below change, so stored results are recomputed.
VERSION = 1


@dataclass(slots=True)
class Feat:
    sentiment: str
    category: str
    concern: str | None = None  # set only when the review needs product action
    feature: str | None = None  # the requested feature (Feature Request only)


def full_text(r: Review) -> str:
    return f"{r.title}. {r.text}" if r.title else r.text


def extract(r: Review) -> Feat:
    text = full_text(r)
    s = sentiment.label(sentiment.score(text, r.rating))
    cat = categorize.classify(text, s)
    f = Feat(s, cat)
    if cat not in categorize.ACTIONABLE:
        return f
    if cat == "Feature Request":
        feature = categorize.feature_request(text)
        if feature is not None:
            f.concern, f.feature = categorize.concern(text, cat), feature
        return f
    c = categorize.concern(text, cat)
    if s in ("angry", "frustrated") or (categorize._NEGATIVE_CUE.search(c) and categorize._polarity(c) <= 0.2):
        f.concern = c
    return f


def extract_many(reviews: list[Review]) -> list[Feat]:
    return [extract(r) for r in reviews]
