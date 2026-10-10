"""Rule-based feedback taxonomy.

Regexes are deliberate: they run at ~200k reviews/s, are fully explainable and
need no model warm-up. Each category scores its matches; the highest score
wins, ties broken by priority (most severe first).
"""

from __future__ import annotations

import re

ACTIONABLE = (
    "Crash",
    "Transactional",
    "Bug Report",
    "Performance",
    "Support",
    "Pricing & Ads",
    "UI/UX",
    "Feature Request",
)
PRAISE = "Praise"
OTHER = "Other"

_RULES: dict[str, list[tuple[str, float]]] = {
    "Crash": [
        (r"\bcrash(es|ed|ing)?\b", 3), (r"force (close|stop)", 3), (r"(keeps|kept) (closing|stopping)", 3),
        (r"\b(app )?(closes|shuts) (down|automatically|itself)\b", 2.5), (r"\bfreez(e|es|ing)\b|\bfroze\b", 2.5),
        (r"\b(hangs|hanging)\b", 2), (r"(won'?t|doesn'?t|does not|not) (open|opening|launch|load(ing)? at all)", 2.5),
        (r"\b(black|white|blank) screen\b", 2.5),
    ],
    "Transactional": [
        (r"\brefund(s|ed)?\b", 3), (r"\b(money|amount) (was |got |is )?(deducted|debited|stuck|lost)\b", 3.5),
        (r"\b(deducted|debited)\b", 2.5), (r"\bcharged (twice|me|double)\b", 3), (r"\bpayment(s)?\b", 2),
        (r"\btransaction(s)?\b", 2), (r"\border(s|ed)?\b", 1.5), (r"\bdeliver(y|ed|ies)\b", 1.5),
        (r"\b(cancel+ed|cancel+ation)\b", 1.5), (r"\b(upi|wallet|cash on delivery|cod)\b", 1.5), (r"\breturn(s|ed)? (request|policy|pickup)\b", 2),
    ],
    "Support": [
        (r"customer (care|service|support)", 3), (r"\bsupport (team|staff|agent)s?\b", 2.5), (r"\bhelpline\b", 2.5),
        (r"\b(no|never) (response|reply|replied|responded)\b", 2), (r"\bchat ?bot\b", 1.5), (r"\b(contact|reach) (them|anyone|support)\b", 2),
    ],
    "Bug Report": [
        (r"\bbug(s|gy)?\b", 2.5), (r"\bglitch(es|y)?\b", 2.5), (r"\berror(s)?\b", 2), (r"\bnot working\b", 2),
        (r"\b(doesn'?t|does not|isn'?t|is not|won'?t|didn'?t) work", 2), (r"\bbroken\b", 2),
        (r"\b(log ?in|sign ?in|otp|verification code|password)\b", 1.5), (r"\b(unable|can'?t|cannot) (to )?\w+", 1),
        (r"\bfail(s|ed|ing|ure)?\b", 1.5), (r"\bstuck\b", 1.5), (r"\bissue(s)?\b|\bproblem(s)?\b", 0.75),
        (r"\bnotification(s)? (not|don'?t|doesn'?t)\b", 2),
    ],
    "Performance": [
        (r"\bslow(ly|er|est)?\b", 2.5), (r"\blag(s|gy|ging)?\b", 2.5), (r"\b(takes|took) (forever|ages|too long)\b", 2.5),
        (r"\bloading\b", 1.5), (r"\bbattery\b", 2.5), (r"\b(heat(s|ing)?|overheat\w*)\b", 2), (r"\b(storage|space|heavy|size)\b", 1),
        (r"\b(data usage|uses too much data)\b", 2),
    ],
    "Pricing & Ads": [
        (r"\bads\b|\badvert\w*|\badvertisement\w*", 3), (r"\bsubscription(s)?\b", 2), (r"\b(premium|paywall|pay to)\b", 2),
        (r"\b(too )?expensive\b|\boverpriced\b|\bprice(s|y)?\b", 2), (r"\bin-?app purchase\w*\b", 2), (r"\bfree (version|trial)\b", 1.5),
    ],
    "UI/UX": [
        (r"\b(ui|ux|interface|layout|design)\b", 2), (r"\bnavigat\w*\b", 2), (r"\bconfus\w*\b", 2), (r"\bclutter\w*\b", 2),
        (r"\bfont(s)?\b|\btext (is )?too small\b", 2), (r"\bdark (mode|theme)\b", 1.5), (r"\bhard to (find|use|navigate)\b", 2.5),
        (r"\b(new|latest|recent) update\b", 1), (r"\bold (version|ui|design)\b", 1.5), (r"\buser.?friendly\b", 1.5),
    ],
    "Feature Request": [
        (r"\bplease (add|bring|make|give|include|allow)\b", 3), (r"\b(would|it'?d) (be|love) (nice|great|good|awesome|helpful)\b", 3),
        (r"\bi wish\b|\bwish (there|it|you)\b", 3), (r"\bshould (have|add|include|allow)\b", 2.5), (r"\b(add|need) (a|an|the|more|option|feature)\b", 2),
        (r"\boption to\b|\bability to\b|\bfeature request\b", 2.5), (r"\b(allow|let) (us|me|users)\b", 2), (r"\bsuggest(ion)?\b", 1.5),
    ],
}

_COMPILED = {cat: [(re.compile(p, re.I), w) for p, w in rules] for cat, rules in _RULES.items()}
# One combined pattern per category: a cheap pre-check so the individual rules
# only run for categories that can match at all (same results, ~4× faster).
_ANY = {cat: re.compile("|".join(f"(?:{p})" for p, _ in rules), re.I) for cat, rules in _RULES.items()}
_PRIORITY = {c: i for i, c in enumerate(ACTIONABLE)}
# A happy review needs a clear problem signal (e.g. "refund" + "deducted",
# or "crash") before it counts as a report rather than praise.
POSITIVE_THRESHOLD = 3.5


def classify(text: str, sentiment: str) -> str:
    scores: dict[str, float] = {}
    for cat, rules in _COMPILED.items():
        if not _ANY[cat].search(text):
            continue
        s = sum(w for rx, w in rules if rx.search(text))
        if s:
            scores[cat] = s
    positive = sentiment in ("delighted", "happy")

    if positive:
        # Happy users mentioning "update" or "order" are praising, not reporting.
        if "Feature Request" in scores and scores["Feature Request"] >= 2:
            return "Feature Request"
        strong = {c: s for c, s in scores.items() if s >= POSITIVE_THRESHOLD}
        if not strong:
            return PRAISE
        scores = strong

    if not scores:
        return OTHER
    return max(scores, key=lambda c: (scores[c], -_PRIORITY[c]))


# ---------------------------------------------------------------------------
# Concern extraction: the part of a review that states the problem/request.
# ---------------------------------------------------------------------------

_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+|\s+[-–—]\s+|(?<=\S),\s*(?:but|however|though)\s+", re.I)
_NEGATIVE_CUE = re.compile(
    r"\b(not|no|never|can'?t|cannot|couldn'?t|won'?t|doesn'?t|didn'?t|isn'?t|wasn'?t|unable|fail\w*|error\w*|crash\w*|"
    r"bug\w*|issue\w*|problem\w*|slow|lag\w*|stuck|wrong|missing|lost|broken|worst|bad|poor|annoying|useless|"
    r"refund\w*|deducted|delay\w*|late|too many|waste)\b",
    re.I,
)


def sentences(text: str) -> list[str]:
    return [s.strip(" .,!?-") for s in _SENTENCES.split(text) if s and len(s.strip()) > 2]


def concern(text: str, category: str) -> str:
    """The sentence that best expresses this review's `category` concern.

    Prefers sentences that match the category *and* read as a complaint, so
    "Fast delivery. But my refund is still pending" yields the refund part.
    """
    sents = [re.sub(r"^(?:but|and|also|however|though|so)\s+", "", s, flags=re.I) for s in sentences(text)] or [text]
    rules = _COMPILED.get(category)
    if not rules or len(sents) == 1:
        return sents[0]
    cue = _REQUEST if category == "Feature Request" else _NEGATIVE_CUE

    def score(s: str) -> float:
        return sum(w for rx, w in rules if rx.search(s)) + (2.0 if cue.search(s) else 0.0)

    scored = [(score(s), -i, s) for i, s in enumerate(sents)]
    best = max(scored)
    return best[2] if best[0] > 0 else sents[0]


_REQUEST = re.compile(
    r"\b(?:please\s+|pls\s+|plz\s+|kindly\s+)?"
    r"(?:add(?:ing)?|bring(?:\s+back)?|introduce|include|provide|give\s+(?:us|me|an?)?|"
    r"(?:we|i)\s+(?:need|want)|wish\s+(?:there\s+(?:was|were|is|would\s+be)|i\s+could|you\s+(?:would|could|had)|it\s+had|for)?|"
    r"would\s+(?:love|like)\s+(?:to\s+(?:see|have)|it\s+if)?|(?:an?\s+)?(?:option|ability|feature|way|setting)\s+to|"
    r"allow\s+(?:us|me|users|people)\s+to|let\s+(?:us|me|users)|should\s+(?:have|add|include|allow|let)|"
    r"hope\s+(?:you|they)\s+(?:add|bring)|(?:needs?|missing)\s+(?:an?|the)?)\s+"
    r"(?P<f>[^.!?\n]{3,90})",
    re.I,
)
_FEATURE_STOP = re.compile(
    r"(?:,|\s(?:so\s+that|so|because|since|but|as\s+(?:it|well|i)|which|when|where|while|for\s+(?:me|us|users)|"
    r"thank\w*|thanx|plz|please|otherwise|then|and\s+(?:it|i|also|please|then))\b).*$",
    re.I,
)
_LEAD = re.compile(r"^(?:a|an|the|some|more|any|back|in|on|to|that|this|(?:feature|option|way|ability|setting|button)\s+(?:of|for|to|that))\s+", re.I)


_SARCASM = re.compile(r"\b(?:wish|could|would)\s+(?:i\s+)?(?:could\s+)?(?:give|rate|put|say|write)\b.{0,30}\b(?:star|stars|zero|0|negative|minus|less|more)\b", re.I)

_NOT_A_REQUEST = re.compile(
    r"(?:n'?t|not|never|no|best|good|great|only|better|easy|perfect|nice)\s+(?:\w+\s+){0,2}$", re.I
)


# A requested feature must name something; these can't start or carry one.
_WEAK_START = {
    "it", "me", "us", "them", "this", "that", "these", "those", "much", "more", "like", "not", "so", "very", "really", "all",
    "everything", "anything", "something", "back", "up", "out", "one", "any", "some", "such", "you", "your", "i", "my", "he",
    "she", "they", "we", "him", "her", "their", "what", "why", "how", "here", "there", "just", "even", "too", "also", "its",
    "say", "tell", "go", "know", "do", "be", "get", "make", "think", "feel", "try", "see", "hear", "stay", "come",
}
_WEAK_WORDS = {"more", "much", "really", "very", "thing", "things", "stuff", "something", "anything", "everything", "please", "thanks", "soon", "possible", "time", "again", "better"}


def feature_request(text: str) -> str | None:
    """The thing a review is asking for, e.g. 'dark mode', 'download songs offline'."""
    if _SARCASM.search(text):
        return None
    m = next((m for m in _REQUEST.finditer(text) if not _NOT_A_REQUEST.search(text[max(0, m.start() - 30): m.start()])), None)
    if not m:
        return None
    phrase = _FEATURE_STOP.sub("", " " + m.group("f")).strip(" ,;:-'\"")
    for _ in range(3):
        phrase = _LEAD.sub("", phrase)
    words = phrase.split()
    if not words:
        return None
    phrase = " ".join(words[:7]).lower().strip(" ,;:-")
    first = phrase.split()[0]
    content = [w for w in re.findall(r"[a-z]+", phrase) if len(w) >= 4 and w not in _WEAK_WORDS]
    if first in _WEAK_START or not content:
        return None
    return phrase


def is_concern(text: str, category: str, sentiment: str) -> bool:
    """Should this review count as something the product team must act on?"""
    if category not in ACTIONABLE:
        return False
    if category == "Feature Request":
        return feature_request(text) is not None
    if sentiment in ("angry", "frustrated"):
        return True
    # Neutral or happy reviewers only count when the concern itself states a
    # problem ("love it, but it crashes on login"), not a mention ("good delivery")
    # and not praise that happens to contain "not" ("…not subscribed, still very good").
    c = concern(text, category)
    return bool(_NEGATIVE_CUE.search(c)) and _polarity(c) <= 0.2


def _polarity(text: str) -> float:
    from .sentiment import _analyzer  # local import keeps module load order simple

    return _analyzer.polarity_scores(text)["compound"]
