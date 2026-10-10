"""Parse Google Play / App Store links (or bare identifiers) into a store + app id."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .models import Store

_PKG = re.compile(r"^[a-zA-Z][\w]*(\.[a-zA-Z_][\w]*)+$")
_APPLE_ID = re.compile(r"(?:^|/|\bid)(\d{6,12})(?:$|[/?#])")
_COUNTRY = re.compile(r"^[a-z]{2}$")


class LinkError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AppRef:
    store: Store
    app_id: str
    country: str

    @property
    def key(self) -> str:
        return f"{self.store}:{self.app_id}:{self.country}"


def parse_link(raw: str, country: str | None = None) -> AppRef:
    value = (raw or "").strip()
    if not value:
        raise LinkError("Paste a Google Play or App Store link.")

    # Bare identifiers: a Java-style package is Play, a long number is Apple.
    if _PKG.match(value):
        return AppRef("play", value, _cc(country, "us"))
    if value.isdigit() and 6 <= len(value) <= 12:
        return AppRef("app", value, _cc(country, "us"))
    if re.fullmatch(r"id\d{6,12}", value):
        return AppRef("app", value[2:], _cc(country, "us"))

    url = urlparse(value if "://" in value else f"https://{value}")
    host = (url.hostname or "").lower()

    if host.endswith("play.google.com"):
        q = parse_qs(url.query)
        pkg = (q.get("id") or [""])[0]
        if not _PKG.match(pkg):
            raise LinkError("That Play Store link has no valid app id (…details?id=com.example.app).")
        return AppRef("play", pkg, _cc(country or (q.get("gl") or [None])[0], "us"))

    if host in {"apps.apple.com", "itunes.apple.com"}:
        m = _APPLE_ID.search(url.path + "/")
        if not m:
            raise LinkError("That App Store link has no app id (…/id123456789).")
        seg = [s for s in url.path.split("/") if s]
        path_cc = seg[0].lower() if seg and _COUNTRY.match(seg[0].lower()) else None
        return AppRef("app", m.group(1), _cc(country or path_cc, "us"))

    raise LinkError("Only Google Play and Apple App Store links are supported.")


def _cc(value: str | None, default: str) -> str:
    v = (value or "").strip().lower()
    return v if _COUNTRY.match(v) else default
