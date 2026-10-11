"""Five-level sentiment from review text (VADER) blended with the star rating.

Stars alone miss "5 stars but it crashes daily"; text alone misreads sarcasm
and terse reviews. Blending both is cheap (~20µs per review) and robust.
"""

from __future__ import annotations

from vaderSentiment.vaderSentiment import (
    BOOSTER_DICT,
    C_INCR,
    N_SCALAR,
    NEGATE,
    SPECIAL_CASES,
    SentimentIntensityAnalyzer,
    SentiText,
)

from ..models import SENTIMENTS

_NEGATE = frozenset(NEGATE)


class FastAnalyzer(SentimentIntensityAnalyzer):
    """VADER with identical scores, minus its quadratic hot spots.

    Stock VADER lower-cases the whole review again for every word it checks
    (negation and idiom look-backs), so cost grows with the square of review
    length, and it rebuilds the text one character at a time to swap emojis.
    Here each review is lower-cased once and ASCII text skips the emoji pass.
    Verified score-for-score against stock VADER on 50k real reviews
    (tests/test_sentiment_parity.py).
    """

    def polarity_scores(self, text):
        if not text.isascii():  # emojis are never ASCII
            out, prev_space = [], True
            for ch in text:
                if ch in self.emojis:
                    if not prev_space:
                        out.append(" ")
                    out.append(self.emojis[ch])
                    prev_space = False
                else:
                    out.append(ch)
                    prev_space = ch == " "
            text = "".join(out)
        text = text.strip()
        st = SentiText(text)
        words = st.words_and_emoticons
        lower = [w.lower() for w in words]
        lex = self.lexicon
        cap_diff = st.is_cap_diff
        n = len(words)
        sentiments = []
        for i in range(n):
            lw = lower[i]
            if lw in BOOSTER_DICT or (lw == "kind" and i < n - 1 and lower[i + 1] == "of"):
                sentiments.append(0)
                continue
            sentiments.append(self._valence(words, lower, i, cap_diff, lex))
        sentiments = self._but_check(words, sentiments)
        return self.score_valence(sentiments, text)

    @staticmethod
    def _valence(words, lower, i, cap_diff, lex):
        lw = lower[i]
        if lw not in lex:
            return 0
        valence = lex[lw]
        n = len(words)
        if lw == "no" and i != n - 1 and lower[i + 1] in lex:
            valence = 0.0
        if (i > 0 and lower[i - 1] == "no") or (i > 1 and lower[i - 2] == "no") or (i > 2 and lower[i - 3] == "no" and lower[i - 1] in ("or", "nor")):
            valence = lex[lw] * N_SCALAR
        if words[i].isupper() and cap_diff:
            valence = valence + C_INCR if valence > 0 else valence - C_INCR
        for start_i in range(3):
            j = i - (start_i + 1)
            if i > start_i and lower[j] not in lex:
                s = 0.0
                if lower[j] in BOOSTER_DICT:
                    s = BOOSTER_DICT[lower[j]]
                    if valence < 0:
                        s *= -1
                    if words[j].isupper() and cap_diff:
                        s = s + C_INCR if valence > 0 else s - C_INCR
                if start_i == 1 and s != 0:
                    s = s * 0.95
                if start_i == 2 and s != 0:
                    s = s * 0.9
                valence = valence + s
                valence = _negation(valence, lower, start_i, i)
                if start_i == 2:
                    valence = _idioms(valence, lower, i)
        # "least" check
        if i > 1 and lower[i - 1] not in lex and lower[i - 1] == "least":
            if lower[i - 2] != "at" and lower[i - 2] != "very":
                valence = valence * N_SCALAR
        elif i > 0 and lower[i - 1] not in lex and lower[i - 1] == "least":
            valence = valence * N_SCALAR
        return valence


def _negated(word: str) -> bool:
    return word in _NEGATE or "n't" in word


def _negation(valence, lower, start_i, i):
    if start_i == 0:
        if _negated(lower[i - 1]):
            valence = valence * N_SCALAR
    elif start_i == 1:
        if lower[i - 2] == "never" and lower[i - 1] in ("so", "this"):
            valence = valence * 1.25
        elif lower[i - 2] == "without" and lower[i - 1] == "doubt":
            pass
        elif _negated(lower[i - 2]):
            valence = valence * N_SCALAR
    else:
        if (lower[i - 3] == "never" and lower[i - 2] in ("so", "this")) or lower[i - 1] in ("so", "this"):
            valence = valence * 1.25
        elif lower[i - 3] == "without" and (lower[i - 2] == "doubt" or lower[i - 1] == "doubt"):
            pass
        elif _negated(lower[i - 3]):
            valence = valence * N_SCALAR
    return valence


def _idioms(valence, lower, i):
    w0, w1, w2, w3 = lower[i], lower[i - 1], lower[i - 2], lower[i - 3]
    for seq in (f"{w1} {w0}", f"{w2} {w1} {w0}", f"{w2} {w1}", f"{w3} {w2} {w1}", f"{w3} {w2}"):
        if seq in SPECIAL_CASES:
            valence = SPECIAL_CASES[seq]
            break
    n = len(lower)
    if n - 1 > i:
        seq = f"{w0} {lower[i + 1]}"
        if seq in SPECIAL_CASES:
            valence = SPECIAL_CASES[seq]
    if n - 1 > i + 1:
        seq = f"{w0} {lower[i + 1]} {lower[i + 2]}"
        if seq in SPECIAL_CASES:
            valence = SPECIAL_CASES[seq]
    for seq in (f"{w3} {w2} {w1}", f"{w3} {w2}", f"{w2} {w1}"):
        if seq in BOOSTER_DICT:
            valence = valence + BOOSTER_DICT[seq]
    return valence


_analyzer = FastAnalyzer()

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
