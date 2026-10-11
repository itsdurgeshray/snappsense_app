from datetime import datetime, timedelta

from app.models import AppMeta, FetchResult, Review

NOW = datetime(2026, 10, 10, 12, 0)

TEXTS = {
    1: ["App crashes every time I open the cart", "Money deducted but order not placed, refund pending", "Can't login, OTP never arrives"],
    2: ["Very slow and drains battery", "Too many ads, subscription overpriced", "Customer care never replies"],
    3: ["It's okay. Search is confusing to navigate", "Please add dark mode to the app", "Delivery was late this time"],
    4: ["Good app, please add a wishlist feature", "Works well mostly", "Nice deals, fast delivery"],
    5: ["Love it! Best shopping app", "Amazing deals and super fast", "Excellent service, very happy"],
}


def make_fetch(per_star: int = 30, hours_per_review: dict[int, float] | None = None, coverage: bool = True, histogram=None) -> FetchResult:
    hours_per_review = hours_per_review or {1: 6, 2: 6, 3: 4, 4: 2, 5: 1}
    reviews = []
    cov = {}
    for star in range(1, 6):
        for i in range(per_star):
            at = NOW - timedelta(hours=hours_per_review[star] * (i + 1))
            reviews.append(Review(id=f"r{star}-{i}", text=TEXTS[star][i % 3], rating=star, at=at))
        cov[star] = NOW - timedelta(hours=hours_per_review[star] * per_star)
    meta = AppMeta(store="play", app_id="com.example.shop", country="us", name="Example Shop", histogram=histogram or [100, 50, 80, 200, 600])
    return FetchResult(meta=meta, reviews=reviews, sources=["test"], coverage=cov if coverage else None)


def as_page(fake_reviews):
    """Adapt a fake of google_play_scraper.reviews() to playstore.gp_page (plain tokens, any page size)."""
    from types import SimpleNamespace

    def page(app_id, lang, country, sort, count, star, token, device=None):
        if device is not None:  # a device segment: a thin, date-ordered slice (every 20th review)
            items, nxt = fake_reviews(app_id, lang, country, sort, 10**7, star, None)
            items = items[::20]
            start = token or 0
            return items[start : start + count], (None if start + count >= len(items) else start + count)
        items, nxt = fake_reviews(app_id, lang, country, sort, count, star, SimpleNamespace(pos=token) if token is not None else None)
        return items, (None if nxt.token is None else nxt.pos)

    return page
