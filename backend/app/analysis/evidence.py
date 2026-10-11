"""Evidence that makes a fix specific to *this* app: where and when it hurts.

Every signal is computed from the reviews themselves, compared against the
app's whole sample so we only call out real concentrations:

* app version   — "Concentrated on v9.16 (74% of mentions vs 38% overall)"
* device / OS   — "Often on Samsung devices (9 mentions)"
* update blame  — "31% blame a recent update"
* recency       — "Rising: 58% of mentions in the last 3 days" (only when
                   the sample covers enough history to say so)
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta

from ..models import Review

_DEVICES = [
    ("Samsung", r"\b(samsung|galaxy)\b"),
    ("Pixel", r"\bpixel\b"),
    ("Xiaomi/Redmi", r"\b(xiaomi|redmi|poco|mi \d+)\b"),
    ("OnePlus", r"\b(one ?plus)\b"),
    ("Oppo", r"\boppo\b"),
    ("Vivo", r"\bvivo\b"),
    ("Realme", r"\brealme\b"),
    ("Motorola", r"\b(motorola|moto [a-z]?\d+)\b"),
    ("Huawei", r"\bhuawei\b"),
    ("Nothing Phone", r"\bnothing phone\b"),
    ("iPhone", r"\biphone\b"),
    ("iPad", r"\bipad\b"),
    ("tablets", r"\btablets?\b"),
    ("Android Auto/CarPlay", r"\b(android auto|carplay)\b"),
    ("smart TVs", r"\b(smart ?tv|android tv|fire ?stick|chromecast)\b"),
    ("smartwatches", r"\b(wear ?os|smart ?watch|galaxy watch|apple watch)\b"),
]
_DEVICES_RX = [(name, re.compile(p, re.I)) for name, p in _DEVICES]
_OS_RX = re.compile(r"\b(android|ios)\s?(\d{1,2})\b", re.I)
_UPDATE_RX = re.compile(r"\b(update|updated|new version|latest version|recent version)\b", re.I)


def _short_version(v: str) -> str:
    parts = v.split(".")
    return ".".join(parts[:3]) if len(parts) > 3 else v


class Baseline:
    """App-wide distributions the evidence is compared against."""

    def __init__(self, reviews: list[Review]):
        versions = [r.version for r in reviews if r.version]
        self.version_share = {v: n / len(versions) for v, n in Counter(versions).items()} if versions else {}
        self.newest = max((r.at for r in reviews), default=None)
        self.oldest = min((r.at for r in reviews), default=None)


def collect(reviews: list[Review], base: Baseline, limit: int = 2, by_version: bool = True) -> list[str]:
    """`by_version`: report version concentration (off when the table itself is picked by version)."""
    found: list[tuple[float, str]] = []  # (strength, text)
    n = len(reviews)
    if n < 3:
        return []

    # 1. App version concentration (Google Play includes the version per review)
    versions = [r.version for r in reviews if r.version]
    if by_version and len(versions) >= 6 and base.version_share:
        v, c = Counter(versions).most_common(1)[0]
        p, q = c / len(versions), base.version_share.get(v, 0)
        if p >= 0.3 and q > 0 and p >= 1.25 * q:
            found.append((p / q, f"Concentrated on v{_short_version(v)} ({round(100 * p)}% of mentions vs {round(100 * q)}% overall)"))

    # 2. Devices and OS versions named in the text
    texts = [f"{r.title} {r.text}" for r in reviews]
    dev = Counter(name for t in texts for name, rx in _DEVICES_RX if rx.search(t))
    if dev:
        name, c = dev.most_common(1)[0]
        if c >= 3 and c / n >= 0.08:
            label = name if name in {"tablets", "smart TVs", "smartwatches", "Android Auto/CarPlay"} else f"{name} devices"
            found.append((1 + c / n * 5, f"Often on {label} ({c} mentions)"))
    os_hits = Counter(f"{m.group(1).capitalize() if m.group(1).lower() == 'android' else 'iOS'} {m.group(2)}" for t in texts for m in [_OS_RX.search(t)] if m)
    if os_hits:
        name, c = os_hits.most_common(1)[0]
        if c >= 3 and c / n >= 0.06:
            found.append((1 + c / n * 5, f"Reported on {name} ({c} mentions)"))

    # 3. Blamed on an update
    upd = sum(bool(_UPDATE_RX.search(t)) for t in texts)
    if upd >= 4 and upd / n >= 0.25:
        found.append((1 + upd / n * 3, f"{round(100 * upd / n)}% blame a recent update"))

    # 4. Recency — only meaningful when the sample spans well beyond the window
    if base.newest and base.oldest and base.newest - base.oldest >= timedelta(days=12) and n >= 8:
        cut = base.newest - timedelta(days=3)
        recent = sum(r.at >= cut for r in reviews)
        span_share = 3 / max(3, (base.newest - base.oldest).days)
        p = recent / n
        if p >= 0.5 and p >= 2.5 * span_share:
            found.append((1 + p * 2, f"Rising: {round(100 * p)}% of mentions in the last 3 days"))

    found.sort(key=lambda t: -t[0])
    return [text for _, text in found[:limit]]

