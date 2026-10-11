"""Group the concerns of one category into distinct, recurring issues.

We cluster the *concern sentence* of each review (the part that states the
problem), not the whole review — "fast delivery, but refund still pending"
belongs with refunds, not delivery. Feature requests are clustered on the
extracted feature itself ("dark mode", "download songs offline") so two
different requests never share a row.

Short complaints rarely share exact words ("late delivery" vs "order
delayed"), so concerns are compared in a small semantic space (LSA) fitted
on the app's own reviews: words that co-occur in this app's reviews end up
close together. Everything is free, local and takes well under a second.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from ..models import Review

_DOMAIN_STOP = {
    "app", "apps", "application", "please", "pls", "plz", "good", "bad", "nice", "best", "worst", "great", "love", "like",
    "really", "just", "use", "using", "used", "time", "times", "make", "dont", "don", "doesnt", "didnt", "cant", "im", "ive",
    "isn", "wasn", "ok", "okay", "thing", "things", "star", "stars", "rating", "give", "also", "even", "still", "get", "got",
    "one", "every", "much", "many", "lot", "would", "could", "want", "need", "know", "think", "always", "now", "day", "days",
    "way", "very", "sir", "team", "guys",
}
# Romanized Hindi/Urdu filler common in Indian-market reviews.
_HINGLISH = {
    "hai", "hain", "ka", "ki", "ke", "ko", "se", "me", "mein", "kar", "karo", "kare", "karna", "kiya", "nahi", "nhi", "nahin",
    "bhi", "ho", "hota", "hoti", "ye", "yeh", "aur", "tha", "thi", "raha", "rahi", "rahe", "wala", "wali", "kya", "koi",
    "bahut", "bhut", "bhai", "ji", "ek", "par", "pe", "na", "ab", "jab", "tak", "liye", "diya", "de", "do", "mera",
    "meri", "mujhe", "aap", "apna", "sab", "gaya", "gya", "hua", "huwa", "kuch", "bekar", "bakwas", "accha", "acha",
}
STOP_WORDS = ENGLISH_STOP_WORDS | _DOMAIN_STOP | _HINGLISH
_TOKEN = r"(?u)\b[a-zA-Z][a-zA-Z]+\b"

MAX_ISSUES_PER_CATEGORY = 6
KMEANS_FIT = 4000  # concerns per category used to find the clusters; the rest are assigned
FR_FIT = 1500  # distinct feature phrases clustered pairwise (memory grows with the square)
MERGE_SIMILARITY = 0.8  # centroids closer than this are the same issue
FR_DISTANCE = 0.85  # feature phrases: cosine distance for "same feature"


@dataclass
class Issue:
    category: str
    reviews: list[Review]
    concerns: list[str]  # aligned with reviews
    terms: list[str] = field(default_factory=list)
    feature: str | None = None  # for feature requests
    centrality: list[float] = field(default_factory=list)  # aligned with reviews

    @property
    def size(self) -> int:
        return len(self.reviews)


# Canonical forms so different words for the same thing land together.
_CANON = [
    (re.compile(r"\bcustomer\s+(?:care|service|services|support|executive)s?\b|\bhelp\s*line\b|\bsupport\s+(?:team|staff)\b|\bcall\s+cent(?:er|re)\b", re.I), "customersupport"),
    (re.compile(r"\b(?:late|later|latee+|delay(?:ed|s)?|delaying)\b", re.I), "late"),
    (re.compile(r"\brefund(?:s|ed|ing)?\b", re.I), "refund"),
    (re.compile(r"\b(?:advert\w*|ads?)\b", re.I), "ads"),
    (re.compile(r"\b(?:log\s*in|sign\s*in|login)\b", re.I), "login"),
    (re.compile(r"\b(?:crash\w*|force\s+clos\w*)\b", re.I), "crash"),
    (re.compile(r"\b(?:lag\w*|slow\w*|sluggish)\b", re.I), "slow"),
    (re.compile(r"\b(?:deducted|debited|charged)\b", re.I), "deducted"),
    (re.compile(r"\b(?:cancel+(?:ed|ation|ing)?)\b", re.I), "cancelled"),
]


def canon(text: str) -> str:
    for rx, rep in _CANON:
        text = rx.sub(rep, text)
    return text


class Embedder:
    """TF-IDF → LSA, fitted once per report on all of the app's review text."""

    def __init__(self, corpus: list[str], app_name: str = ""):
        from sklearn.decomposition import TruncatedSVD

        extra = {w for w in re.findall(r"[a-z]+", app_name.lower()) if len(w) > 2}
        docs = [canon(t) for t in corpus] or ["empty"]
        X = None
        for min_df, max_df in ((2, 0.5), (1, 1.0)):  # small apps: relax pruning
            self.vec = TfidfVectorizer(
                stop_words=sorted(STOP_WORDS | extra), token_pattern=_TOKEN, ngram_range=(1, 2),
                min_df=min_df, max_df=max_df, max_features=20000, sublinear_tf=True,
            )
            try:
                X = self.vec.fit_transform(docs)
                break
            except ValueError:
                continue
        self.vocab = np.array(self.vec.get_feature_names_out()) if X is not None else np.array([])
        k = min(120, X.shape[1] - 1, X.shape[0] - 1) if X is not None else 0
        self.svd = TruncatedSVD(n_components=k, random_state=0, algorithm="randomized", n_iter=4).fit(X) if k >= 2 else None

    def tfidf(self, texts: list[str]):
        from scipy.sparse import csr_matrix

        if not len(self.vocab):
            return csr_matrix((len(texts), 1))
        return self.vec.transform([canon(t) for t in texts])

    def embed(self, texts: list[str]) -> np.ndarray:
        T = self.tfidf(texts)
        Z = self.svd.transform(T) if self.svd is not None else T.toarray()
        n = np.linalg.norm(Z, axis=1, keepdims=True)
        return Z / np.where(n == 0, 1, n)


def _top_terms(weights: np.ndarray, vocab: np.ndarray, n: int = 4) -> list[str]:
    out: list[str] = []
    for i in np.argsort(weights)[::-1][:30]:
        if weights[i] <= 0:
            break
        term = str(vocab[i])
        if any(term in t or t in term for t in out):
            continue
        out.append(term)
        if len(out) == n:
            break
    return out


def _k_for(n: int) -> int:
    return max(1, min(MAX_ISSUES_PER_CATEGORY, round(np.sqrt(n / 3))))


def _merge_close(labels: np.ndarray, Z: np.ndarray) -> np.ndarray:
    """Merge clusters whose centroids are near-identical."""
    while True:
        ids = sorted(set(labels.tolist()))
        if len(ids) < 2:
            return labels
        C = np.vstack([Z[labels == c].mean(axis=0) for c in ids])
        C /= np.where(np.linalg.norm(C, axis=1, keepdims=True) == 0, 1, np.linalg.norm(C, axis=1, keepdims=True))
        S = C @ C.T
        np.fill_diagonal(S, -1)
        i, j = np.unravel_index(S.argmax(), S.shape)
        if S[i, j] < MERGE_SIMILARITY:
            return labels
        labels = np.where(labels == ids[j], ids[i], labels)


def cluster_category(
    category: str,
    reviews: list[Review],
    concerns: list[str],
    embedder: Embedder,
    features: list[str | None] | None = None,
) -> list[Issue]:
    """`concerns[i]` is the concern sentence for `reviews[i]`; `features[i]` the requested feature (Feature Request only)."""
    if not reviews:
        return []
    is_fr = category == "Feature Request" and features is not None
    texts = [f or c for f, c in zip(features, concerns)] if is_fr else concerns

    if is_fr:
        labels, Z = _cluster_features(texts)
    else:
        Z = embedder.embed(texts)
        k = min(_k_for(len(texts)), len(texts))
        if k <= 1:
            labels = np.zeros(len(texts), dtype=int)
        else:
            from sklearn.cluster import KMeans

            km = KMeans(n_clusters=k, n_init=5, random_state=0)
            if len(texts) > KMEANS_FIT:  # fit on a sample, then place every concern
                # Stable sample (by review id), so refreshes don't reshuffle the issues.
                fit = np.argsort([zlib.crc32(r.id.encode()) for r in reviews], kind="stable")[:KMEANS_FIT]
                labels = km.fit(Z[fit]).predict(Z)
            else:
                labels = km.fit_predict(Z)
            labels = _merge_close(labels, Z)

    T = embedder.tfidf(texts)
    issues: list[Issue] = []
    for c in sorted(set(labels.tolist())):
        idx = np.where(labels == c)[0]
        Zc = Z[idx]  # dense, or sparse for very large feature-request sets
        centroid = np.asarray(Zc.mean(axis=0)).ravel()
        sims = np.asarray(Zc @ centroid).ravel() / (np.linalg.norm(centroid) or 1)
        order = idx[np.argsort(-sims)]
        issue = Issue(
            category,
            [reviews[i] for i in order],
            [concerns[i] for i in order],
            terms=_top_terms(np.asarray(T[idx].mean(axis=0)).ravel(), embedder.vocab),
            centrality=np.sort(sims)[::-1].tolist(),
        )
        if is_fr:
            issue.feature = _representative_feature([texts[i] for i in order])
        issues.append(issue)

    issues.sort(key=lambda i: i.size, reverse=True)
    return issues


_SYNONYMS = {"theme": "mode", "themes": "mode", "songs": "song", "videos": "video", "podcasts": "podcast", "playlists": "playlist", "colours": "color", "colors": "color", "colour": "color"}


def _cluster_features(phrases: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Group requested features by their own words: 'dark mode' ≠ 'sleep timer'.

    Pairwise clustering needs memory that grows with the square of its input,
    so it runs on distinct phrases only (most requests repeat a few phrasings),
    capped at the FR_FIT most common; rarer phrasings join the nearest group
    if they're close enough, otherwise stay on their own.
    """
    norm = [" ".join(_SYNONYMS.get(w, w.rstrip("s") if len(w) > 3 else w) for w in re.findall(r"[a-z]+", p.lower())) for p in phrases]
    counts: dict[str, int] = {}
    for p in norm:
        counts[p] = counts.get(p, 0) + 1
    uniq = sorted(counts, key=lambda p: -counts[p])
    vec = TfidfVectorizer(stop_words=sorted(STOP_WORDS), token_pattern=_TOKEN, ngram_range=(1, 2), sublinear_tf=True)
    try:
        U = vec.fit_transform(uniq)
    except ValueError:
        return np.zeros(len(phrases), dtype=int), np.zeros((len(phrases), 1))
    from sklearn.preprocessing import normalize

    U = normalize(U)
    head = min(len(uniq), FR_FIT)
    if head < 2:
        ulabels = np.zeros(len(uniq), dtype=int)
    else:
        ulabels = np.empty(len(uniq), dtype=int)
        # Cosine distances from one sparse product: far cheaper than scipy's
        # dense pairwise pass. Empty phrases are at distance 1 from everything.
        D = 1.0 - (U[:head] @ U[:head].T).toarray()
        np.clip(D, 0.0, 1.0, out=D)
        np.fill_diagonal(D, 0.0)
        ulabels[:head] = AgglomerativeClustering(n_clusters=None, distance_threshold=FR_DISTANCE, metric="precomputed", linkage="average").fit_predict(D)
        if head < len(uniq):
            ids = np.unique(ulabels[:head])
            C = normalize(np.vstack([np.asarray(U[:head][ulabels[:head] == c].mean(axis=0)) for c in ids]))
            sims = U[head:] @ C.T
            best = sims.argmax(axis=1)
            near = sims[np.arange(sims.shape[0]), best] >= 1 - FR_DISTANCE
            fresh = np.arange(head, len(uniq)) + ulabels.max() + 1  # unmatched: their own group
            ulabels[head:] = np.where(near, ids[best], fresh)
    index = {p: i for i, p in enumerate(uniq)}
    rows = np.fromiter((index[p] for p in norm), dtype=int, count=len(norm))
    X = U[rows].toarray() if U.shape[1] * len(norm) <= 4_000_000 else U[rows]
    return ulabels[rows], X


def _representative_feature(phrases: list[str]) -> str:
    """The most common short phrasing among the most central requests."""
    head = phrases[: max(5, len(phrases) // 2)]
    counts: dict[str, int] = {}
    for p in head:
        key = " ".join(p.split()[:5])
        counts[key] = counts.get(key, 0) + 1
    return max(counts, key=lambda k: (counts[k], -len(k)))
