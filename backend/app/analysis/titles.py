"""One-line, insightful titles for each issue — without any paid AI.

Problems: pick the clearest *real* concern sentence from the most central
reviews of the cluster, then tidy it into a headline ("My money got deducted
but order was not placed!!" → "Money deducted but order not placed").

Feature requests: phrase the extracted feature as an action
("dark mode" → "Add dark mode", "download songs offline" → "Let users
download songs offline").
"""

from __future__ import annotations

import re

from .cluster import Issue
from .sentiment import _analyzer

MAX_LEN = 78
CANDIDATES = 30

_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿️‍]+")
_HINGLISH = re.compile(
    r"\b(hai|hain|nahi|nhi|kya|kar|karo|raha|rahi|bhi|mera|meri|mujhe|aap|wala|gaya|gya|bekar|bakwas|kuch|sab|ho|tha)\b", re.I
)
_FIRST_PERSON = re.compile(r"\b(i|i'm|im|i've|me|my|mine|we|our)\b", re.I)
_PROBLEM_WORD = re.compile(
    r"\b(not|no|never|can'?t|cannot|won'?t|doesn'?t|didn'?t|isn'?t|unable|fail\w*|error|crash\w*|bug\w*|slow|lag\w*|stuck|"
    r"late|delay\w*|refund|deducted|charged|missing|wrong|broken|too many|expensive|confusing|hard to|freez\w*|drain\w*)\b",
    re.I,
)

# Leading filler that says nothing about *what* is wrong.
_LEAD_FILLER = [
    re.compile(r"^(?:hi|hello|hey|dear|sir|madam|team|guys|bro|pls|please|kindly)\b[\s,.:!-]*", re.I),
    re.compile(
        r"^(?:(?:very|so|too|really|extremely|the|most|this is (?:the|a)|this|such an?|what an?)\s+)*"
        r"(?:bad|worst|poor|pathetic|useless|terrible|horrible|disappointing|frustrating|irritating|annoying|rubbish|trash|waste(?: of time)?)\s+"
        r"(?:app|application|experience|service|platform)\b[\s,.:!-]*",
        re.I,
    ),
    re.compile(r"^(?:i\s+am|i'm|im|i\s+was|we\s+are)\s+(?:very\s+|so\s+|really\s+)?(?:disappointed|upset|unhappy|frustrated|angry|fed up|tired)(?:\s+(?:with|because|that|as))?[\s,.:!-]*", re.I),
    re.compile(r"^(?:but|and|also|however|though|so|actually|honestly|basically|now|then|recently|lately)\b[\s,]*", re.I),
    re.compile(r"^(?:it'?s|its|this is|that'?s|that is)\s+(?:so\s+|very\s+|really\s+|just\s+)?(?:bad|annoying|terrible|horrible|frustrating|ridiculous|awful|sad|unfair|disappointing)\b[\s,.:!-]*", re.I),
    re.compile(r"^(?:great|good|nice|love(?:ly)?|awesome|amazing|okay|ok|decent|fine)\s+(?:app|application|service)?\s*(?:but|,)\s*", re.I),
    re.compile(r"^(?:the\s+)?(?:only|main|biggest)\s+(?:issue|problem|thing)\s+(?:is|was)(?:\s+that)?[\s,:]*", re.I),
]
_REWRITES = [
    (re.compile(r"^(?:i|we)\s+(?:am|are|was|were|'m)\s+(?:not\s+able|unable)\s+to\b", re.I), "Unable to"),
    (re.compile(r"^(?:i|we)\s+(?:can'?t|cannot|could\s*n[o']?t|couldn'?t)\b", re.I), "Can't"),
    (re.compile(r"^(?:i|we)\s+(?:did\s*n[o']?t|didn'?t|have\s+not|haven'?t|never)\s+(?:get|got|receive[d]?)\b", re.I), "Didn't receive"),
    (re.compile(r"^(?:i|we)\s+(?:keep|kept)\s+getting\b", re.I), "Keeps showing"),
    (re.compile(r"^(?:my|our)\s+", re.I), ""),
    (re.compile(r"\b(?:got|has been|have been|was|is|are|were)\s+(deducted|debited|cancelled|canceled|delayed|blocked|banned|charged)\b", re.I), r"\1"),
    (re.compile(r"\bwas not\b|\bwasn'?t\b", re.I), "not"),
    (re.compile(r"\s{2,}"), " "),
]

_VERB_START = {
    "see", "change", "download", "play", "skip", "edit", "delete", "sort", "filter", "track", "pay", "choose", "select", "save",
    "share", "hide", "block", "cancel", "return", "customize", "customise", "upload", "watch", "listen", "search", "turn", "switch",
    "use", "login", "log", "remove", "disable", "enable", "set", "schedule", "repeat", "shuffle", "export", "import", "sync",
    "compare", "rate", "reply", "mute", "pin", "archive", "transfer", "add", "manually", "go", "view", "create", "make", "control",
    "keep", "run", "report", "get", "have", "know", "show", "give", "send", "write", "read", "speak", "learn", "practice", "connect",
    "invite", "follow", "unfollow", "message", "call", "opt", "pause", "resume", "restore", "recover", "reset", "move", "organize",
    "organise", "group", "split", "merge", "print", "scan", "translate", "zoom", "record", "stream", "cast", "lock", "unlock",
}


def _tidy(s: str) -> str:
    s = _EMOJI.sub("", s)
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"([!?.,])\1+", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip(" -–—:;,.!?'\"()“”‘’")
    if s.count("“") + s.count("”") == 1 or s.count('"') == 1:  # unbalanced quote mark
        s = re.sub(r"[“”\"]", "", s)
    for _ in range(3):
        before = s
        for rx in _LEAD_FILLER:
            s = rx.sub("", s).strip(" -–—:;,.!?")
        if s == before:
            break
    for rx, rep in _REWRITES:
        s = rx.sub(rep, s).strip()
    if s.isupper():
        s = s.lower()
    if len(s) > MAX_LEN:
        cut = s[:MAX_LEN]
        # Prefer ending at a clause boundary, else a word boundary.
        m = re.search(r"^(.{25,}?)(?:,|;| but | because | so | and | when | which )", cut)
        s = m.group(1) if m else cut.rsplit(" ", 1)[0]
        s = s.rstrip(" ,;:-")
    s = re.sub(r"\b(?:and|or|but|because|so|the|a|an|to|of|in|on|with|when)$", "", s, flags=re.I).strip(" ,;:-")
    return s[:1].upper() + s[1:] if s else s


def _tidy_untruncated(s: str) -> str:
    s = _EMOJI.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _ngrams(text: str) -> set[str]:
    words = [w for w in re.findall(r"[a-z']+", text.lower())]
    grams = set()
    for n in (2, 3):
        for i in range(len(words) - n + 1):
            g = words[i : i + n]
            if sum(w not in _STOP for w in g) >= 1:
                grams.add(" ".join(g))
    return grams


_STOP = {"the", "a", "an", "is", "it", "to", "of", "and", "i", "my", "in", "on", "for", "this", "that", "be", "was", "are", "me", "you", "your", "app"}
_LEADING_WEAK = re.compile(r"^(?:not|before|after|even|still|because|if|when|since|ever since|they|it|this|that|there|which|who|those|these|you)\b", re.I)
_IMPERATIVE_FIX = re.compile(
    r"^(?:(?:could|can|would|will)\s+you\s+|please\s+|pls\s+|do\s+|kindly\s+)*(?:fix|solve|resolve|rectify|sort out|look into|check)\b"
    r"|^how can (?:so many|lots of|there be)|^(?:why|what) (?:is|are) (?:there|this)",
    re.I,
)
# Words that say *that* something is wrong, not *what*.
_GENERIC = {
    "app", "apps", "application", "fix", "bug", "bugs", "problem", "problems", "issue", "issues", "update", "updates", "working",
    "work", "works", "not", "bad", "worst", "poor", "good", "great", "very", "really", "please", "this", "that", "there", "thing",
    "things", "everything", "anything", "something", "time", "times", "even", "still", "just", "dont", "doesn", "didn", "isn",
    "can't", "cant", "all", "some", "every", "way", "lot", "much", "more", "use", "using", "used", "experience", "service",
}


def _score(raw: str, tidy: str, centrality: float, consensus: float = 0.0, rare: float = 0.0, truncated: bool = False, relevance: float = 1.0) -> float:
    words = tidy.split()
    n = len(words)
    if n < 3 or not re.search(r"[a-zA-Z]{3}", tidy):
        return -1.0
    letters = sum(c.isascii() and c.isalpha() for c in tidy)
    if letters / max(1, len(tidy.replace(" ", ""))) < 0.85 or _HINGLISH.search(tidy):
        return -1.0
    length = 1.0 if 4 <= n <= 12 else 0.75 if n <= 16 else 0.5
    clarity = 1.0
    clarity *= 1.25 if _PROBLEM_WORD.search(tidy) else 0.8
    clarity *= 0.85 if _FIRST_PERSON.search(tidy) else 1.0
    clarity *= 0.7 if re.search(r"\d{4,}|#\w+|order id|\?", raw, re.I) else 1.0
    clarity *= 0.8 if len(raw) > 160 else 1.0
    clarity *= 0.75 if _LEADING_WEAK.search(tidy) else 1.0
    clarity *= 0.3 if _IMPERATIVE_FIX.search(tidy) else 1.0
    specific = [w for w in re.findall(r"[a-z']+", tidy.lower()) if len(w) > 2 and w not in _GENERIC and w not in _STOP]
    clarity *= 0.35 if not specific else 0.8 if len(specific) == 1 else 1.0
    clarity *= 0.8 if truncated else 1.0
    clarity *= 0.4 + min(1.0, 2.5 * relevance)  # its specific words must be common in the cluster
    # A concern's headline must read as a concern, never as praise.
    polarity = _analyzer.polarity_scores(tidy)["compound"]
    clarity *= 0.1 if polarity > 0.3 and not _PROBLEM_WORD.search(tidy) else 0.6 if polarity > 0.3 else 1.0
    clarity *= max(0.3, 1.0 - 1.5 * rare)  # misspellings / one-off words
    return max(0.05, centrality) * length * clarity * (0.6 + 2.0 * min(consensus, 0.5))


def problem_title(issue: Issue, vocab: set[str] | None = None) -> str:
    """`vocab`: words seen in several of the app's reviews (anything else is likely a typo)."""
    # How many members use each 2–3 word phrase: titles should say what most users say.
    df: dict[str, int] = {}
    wdf: dict[str, int] = {}
    for c in issue.concerns:
        for g in _ngrams(c):
            df[g] = df.get(g, 0) + 1
        for w in set(re.findall(r"[a-z']+", c.lower())):
            wdf[w] = wdf.get(w, 0) + 1
    size = max(1, issue.size)

    best, best_score = "", -1.0
    for concern, cen in list(zip(issue.concerns, issue.centrality))[:CANDIDATES]:
        tidy = _tidy(concern)
        grams = _ngrams(tidy)
        consensus = max((df.get(g, 0) for g in grams), default=0) / size if size >= 4 else 0.25
        words = [w for w in re.findall(r"[a-z]+", tidy.lower()) if len(w) > 2]
        rare = (sum(w not in vocab for w in words) / len(words)) if vocab and words else 0.0
        specific = [w for w in set(re.findall(r"[a-z']+", tidy.lower())) if len(w) > 2 and w not in _GENERIC and w not in _STOP]
        relevance = (sum(wdf.get(w, 0) for w in specific) / len(specific) / size) if specific and size >= 6 else 0.4
        sc = _score(concern, tidy, cen, consensus, rare, truncated=len(_tidy_untruncated(concern)) > MAX_LEN, relevance=relevance)
        if sc > best_score:
            best, best_score = tidy, sc
    if best_score > 0:
        return best
    # Nothing clean enough: fall back to the cluster's key terms.
    terms = [t for t in issue.terms if not t.isdigit()][:2]
    return f"{issue.category}: {' & '.join(terms)}" if terms else issue.category


def feature_title(issue: Issue) -> str:
    phrase = _EMOJI.sub("", issue.feature or "").strip(" '\"")
    phrase = re.sub(r"\b(?:feature|option|button|setting)s?\s+(?:to|in|on|for)\s+the\s+app\b|\b(?:in|to|on|for)\s+(?:the|this)\s+app\b|\b(?:feature|option)\s*$", "", phrase, flags=re.I)
    for _ in range(2):
        phrase = re.sub(r"\s+(?:in|on|to|for|of|the|a|an|my|our|your|me|us|it|this|that|and|or|with)$", "", phrase.strip(), flags=re.I).strip(" ,'\"")
    phrase = re.sub(r"\b(?:my|our)\b", "their", phrase, flags=re.I)
    if not phrase:
        return problem_title(issue)
    phrase = re.split(r"\s*[—–-]\s+|\s*[—–]\s*", phrase)[0].strip()
    first = phrase.split()[0].lower() if phrase else ""
    if re.search(r"\b(users|people|everyone)\b", phrase):
        title = f"Add a way to {phrase}"
    elif first in _VERB_START or first.endswith("ing"):
        title = f"Let users {phrase}"
    else:
        title = f"Add {phrase}"
    return title if len(title) <= MAX_LEN else title[:MAX_LEN].rsplit(" ", 1)[0]


def title(issue: Issue, vocab: set[str] | None = None) -> str:
    return feature_title(issue) if issue.feature else problem_title(issue, vocab)
