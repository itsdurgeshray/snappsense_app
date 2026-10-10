from app.analysis import categorize, sentiment, trends
from app.analysis.pipeline import analyze
from app.models import SENTIMENTS

from .factories import NOW, make_fetch


def lab(text, stars):
    return sentiment.label(sentiment.score(text, stars))


def test_sentiment_blends_text_and_stars():
    assert lab("Love it! Best app ever", 5) == "delighted"
    assert lab("Charged twice, worst support, total scam", 1) == "frustrated"
    assert lab("It's okay", 3) == "neutral"
    # Five stars but furious text should not read as delighted.
    assert lab("Terrible, crashes constantly and lost my data", 5) != "delighted"


def test_categories():
    cases = {
        "App crashes every time I open the cart": "Crash",
        "Money deducted but order not placed": "Transactional",
        "Please add dark mode": "Feature Request",
        "So slow and drains battery": "Performance",
        "Too many ads": "Pricing & Ads",
        "Customer care never replies": "Support",
        "Can't login, OTP never arrives": "Bug Report",
        "Navigation is confusing, hard to find orders": "UI/UX",
    }
    for text, cat in cases.items():
        assert categorize.classify(text, "angry") == cat, text


def test_positive_reviews_are_praise_unless_requesting():
    assert categorize.classify("Love the fast delivery and easy orders", "delighted") == "Praise"
    assert categorize.classify("Great app, please add a wishlist", "happy") == "Feature Request"


def test_report_shape_and_totals_follow_histogram():
    f = make_fetch()
    report, by_issue, _ = analyze(f, now=NOW)
    assert report["totalReviews"] == sum(f.meta.histogram)
    assert set(report["totals"]) == set(SENTIMENTS)
    assert abs(sum(report["totals"].values()) - report["totalReviews"]) <= 5
    # 5★ dominates the histogram, so the all-time mix must be mostly positive.
    assert report["positiveShare"] > 60
    assert report["feedback"] and set(by_issue) == {f["id"] for f in report["feedback"]}
    assert {"id", "category", "feedback", "solution", "count"} <= set(report["feedback"][0])
    # The modal lists every review behind a row.
    assert all(len(by_issue[f["id"]]) == f["count"] for f in report["feedback"])
    assert abs(sum(c["share"] for c in report["categories"]) - 100) < 1
    assert set(report["trends"]) == {"1w", "1m", "3m", "6m", "1y"}


def test_trends_exact_inside_full_coverage():
    f = make_fetch(per_star=200, hours_per_review={s: 1 for s in range(1, 6)})
    report, _, _ = analyze(f, now=NOW)
    week = report["trends"]["1w"]
    # 200 h of coverage for every star: the 6 complete past days are exact.
    full_days = [b for b in week[:-1] if not b["empty"]]
    assert full_days and all(not b["estimated"] for b in full_days[1:])
    assert all(sum(b["counts"].values()) == 24 * 5 for b in full_days[1:])


def test_trends_never_invent_far_history():
    f = make_fetch(per_star=10, hours_per_review={s: 1 for s in range(1, 6)})
    report, _, _ = analyze(f, now=NOW)
    oldest = report["trends"]["1y"][0]
    assert oldest["empty"] and sum(oldest["counts"].values()) == 0


def test_sample_sources_are_flagged_estimated():
    f = make_fetch(coverage=False)
    report, _, _ = analyze(f, now=NOW)
    assert all(b["estimated"] for b in report["trends"]["1w"])


def test_buckets_cover_ranges():
    b = trends.buckets(NOW)
    assert [len(b[k]) for k in ("1w", "1m", "3m", "6m", "1y")] == [7, 6, 13, 6, 12]
    assert b["1y"][-1][0] == "Oct"


def test_table_lists_only_concerns_never_praise():
    report, by_issue, _ = analyze(make_fetch(), now=NOW)
    praise = {"Love it! Best shopping app", "Amazing deals and super fast", "Excellent service, very happy", "Nice deals, fast delivery", "Works well mostly"}
    for rows in by_issue.values():
        assert not praise & {r["text"] for r in rows}


def test_every_breakdown_category_has_a_table_row():
    report, _, _ = analyze(make_fetch(), now=NOW)
    assert {c["label"] for c in report["categories"]} == {f["category"] for f in report["feedback"]}


def test_distinct_feature_requests_get_separate_rows():
    from app.models import Review
    from datetime import timedelta

    f = make_fetch(per_star=6)
    extra = ["Please add dark mode", "Would love a dark mode option", "Please add dark mode for night use",
             "Please add a sleep timer", "I wish there was a sleep timer", "Please add sleep timer feature"]
    f.reviews += [Review(id=f"fr{i}", text=t, rating=4, at=NOW - timedelta(hours=i)) for i, t in enumerate(extra)]
    report, _, _ = analyze(f, now=NOW)
    fr = [x["feedback"].lower() for x in report["feedback"] if x["category"] == "Feature Request"]
    assert any("dark mode" in t for t in fr) and any("sleep timer" in t for t in fr)


def test_feature_request_extraction_rejects_complaints_and_sarcasm():
    assert categorize.feature_request("Please add dark mode") == "dark mode"
    assert categorize.feature_request("I wish there was an option to download songs offline") == "download songs offline"
    assert categorize.feature_request("it wouldn't let me log in") is None
    assert categorize.feature_request("this is the best option to buy") is None
    assert categorize.feature_request("I wish I could give this zero stars") is None


def test_titles_are_one_liners():
    report, _, _ = analyze(make_fetch(), now=NOW)
    for row in report["feedback"]:
        assert 0 < len(row["feedback"]) <= 80 and "\n" not in row["feedback"]


def test_neutral_mentions_are_not_concerns():
    assert not categorize.is_concern("good delivery", "Transactional", "neutral")
    assert categorize.is_concern("delivery was late again", "Transactional", "neutral")


def test_rows_have_priority_impact_and_evidence_fields():
    report, _, _ = analyze(make_fetch(), now=NOW)
    for row in report["feedback"]:
        assert row["priority"] in {"high", "medium", "low"}
        assert 0 < row["impact"] <= 100 and isinstance(row["evidence"], list)
    assert sum(r["priority"] == "high" for r in report["feedback"]) <= 4


def test_version_concentration_evidence():
    from datetime import timedelta
    from app.analysis import evidence
    from app.models import Review

    base_reviews = [Review(id=f"b{i}", text="fine", rating=4, at=NOW - timedelta(hours=i), version="2.0" if i % 2 else "2.1") for i in range(100)]
    issue = [Review(id=f"i{i}", text="crashes on launch", rating=1, at=NOW - timedelta(hours=i), version="2.1") for i in range(10)]
    out = evidence.collect(issue, evidence.Baseline(base_reviews + issue))
    assert out and "v2.1" in out[0]


def test_device_evidence():
    from datetime import timedelta
    from app.analysis import evidence
    from app.models import Review

    issue = [Review(id=f"i{i}", text=f"Keeps crashing on my Samsung Galaxy S{20 + i}", rating=1, at=NOW - timedelta(hours=i)) for i in range(6)]
    assert any("Samsung" in e for e in evidence.collect(issue, evidence.Baseline(issue)))


def test_domain_playbook_is_preferred():
    from app.analysis.cluster import Issue
    from app.analysis.solutions import domain_for, suggest
    from app.models import Review

    texts = ["songs keep buffering and stop playing", "music stops playing every minute", "playback keeps buffering on wifi"] * 3
    issue = Issue("Bug Report", [Review(id=str(i), text=t, rating=1, at=NOW) for i, t in enumerate(texts)], texts, centrality=[1.0] * len(texts))
    assert domain_for("Music & Audio") == "streaming"
    assert "bitrate" in suggest(issue, "Songs keep buffering", "streaming")
    assert "bitrate" not in suggest(issue, "Songs keep buffering", None)


def test_praise_containing_not_is_not_a_concern():
    text = "This is best even I have not subscription it's experience is very good"
    assert not categorize.is_concern(text, "Pricing & Ads", "delighted")
    assert categorize.is_concern("Love it, but it crashes on login every time", "Crash", "happy")


def test_all_time_ratings_come_from_store_histogram():
    f = make_fetch()
    report, _, _ = analyze(f, now=NOW)
    assert report["ratingsBasis"] == "store"
    assert [report["ratings"][str(s)] for s in (1, 2, 3, 4, 5)] == f.meta.histogram
