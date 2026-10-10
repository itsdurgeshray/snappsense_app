"""Five-level sentiment from review text (VADER) blended with the star rating.

Stars alone miss "5 stars but it crashes daily"; text alone misreads sarcasm
and terse reviews. Blending both is cheap (~20µs per review) and robust.
"""

from __future__ import annotations

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from ..models import SENTIMENTS

_analyzer = SentimentIntensityAnalyzer()

TEXT_WEIGHT = 0.45


def score(text: str, rating: int) -> float:
    """Blended polarity in [-1, 1]."""
    compound = _analyzer.polarity_scores(text[:1200])["compound"] if text else 0.0
    if not rating:
        return compound
    stars = (rating - 3) / 2  # 1★ → -1, 3★ → 0, 5★ → 1
    return (1 - TEXT_WEIGHT) * stars + TEXT_WEIGHT * compound


def label(polarity: float) -> str:
    if polarity >= 0.6:
        return SENTIMENTS[0]  # delighted
    if polarity >= 0.2:
        return SENTIMENTS[1]  # happy
    if polarity > -0.2:
        return SENTIMENTS[2]  # neutral
    if polarity > -0.6:
        return SENTIMENTS[3]  # angry
    return SENTIMENTS[4]  # frustrated
