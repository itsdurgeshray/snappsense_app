"""The fast VADER must score exactly like stock VADER."""

import random

from vaderSentiment.vaderSentiment import BOOSTER_DICT, NEGATE, SPECIAL_CASES, SentimentIntensityAnalyzer

from app.analysis.sentiment import FastAnalyzer

from .factories import TEXTS

EDGE = [
    "", "   ", "I don't love it", "not bad at all", "kind of good", "never so happy", "the shit 😍😍 great", "At least it works",
    "at least it works", "no good no bad", "VERY GOOD but slow", "it is not the bomb", "Without doubt the best", "cut the mustard",
    "Great app!!!!! but CRASHES", "Is it good??? no", "no, or nor bad", "least favourite", "very least good", "this is kind of bad",
    "😡😡😡", "good 👍 app", "yeah right, great update", "bad ass app", "sort of okay", "It's not that it isn't good",
]


def _random_texts(n: int) -> list[str]:
    an = SentimentIntensityAnalyzer()
    rng = random.Random(7)
    lex = rng.sample(sorted(an.lexicon), 600)
    pool = lex + sorted(BOOSTER_DICT) + NEGATE + sorted(SPECIAL_CASES) + ["but", "no", "so", "this", "never", "without", "doubt", "least", "at", "very", "kind", "of", "or", "nor", "😍", "👍", "!", "?"]
    out = []
    for _ in range(n):
        words = [rng.choice(pool) for _ in range(rng.randint(1, 30))]
        words = [w.upper() if rng.random() < 0.1 else w for w in words]
        out.append(" ".join(words) + rng.choice(["", ".", "!", "!!!", "?", "??"]))
    return out


def test_fast_vader_matches_stock_exactly():
    stock, fast = SentimentIntensityAnalyzer(), FastAnalyzer()
    texts = EDGE + [t for ts in TEXTS.values() for t in ts] + _random_texts(4000)
    mismatches = [t for t in texts if stock.polarity_scores(t) != fast.polarity_scores(t)]
    assert not mismatches, mismatches[:5]
