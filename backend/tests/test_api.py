import time

import pytest
from fastapi.testclient import TestClient

from app import jobs as jobs_module
from app import main
from app.sources.playstore import AppNotFound

from .factories import make_fetch


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings.__class__, "cache_path", property(lambda self: tmp_path / "c.db"), raising=False)
    monkeypatch.setattr(main.settings.__class__, "store_path", property(lambda self: tmp_path / "r.db"), raising=False)
    calls = {"n": 0}

    async def fake_play(ref, depth, pool, progress, **kw):
        calls["n"] += 1
        if ref.app_id == "com.missing.app":
            raise AppNotFound("No Google Play app with id “com.missing.app”.")
        progress({"stage": "meta", "name": "Example Shop"})
        progress({"stage": "fetch", "fetched": 150, "target": 150})
        return make_fetch()

    monkeypatch.setattr(jobs_module, "fetch_play", fake_play)
    with TestClient(main.app) as c:
        c.calls = calls
        yield c


def _events(client, job_id):
    with client.stream("GET", f"/api/jobs/{job_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        kinds = [line.split(": ", 1)[1] for line in r.iter_lines() if line.startswith("event: ")]
    return kinds


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True and body["localModel"] is None


def test_bad_link_is_400(client):
    r = client.post("/api/analyze", json={"url": "https://example.com"})
    assert r.status_code == 400 and "supported" in r.json()["detail"]


def test_full_flow_then_cache(client):
    r = client.post("/api/analyze", json={"url": "com.example.shop"}).json()
    assert r["status"] == "running" and r["jobId"]
    kinds = _events(client, r["jobId"])
    assert kinds[0] == "progress" and "report" in kinds and kinds[-1] == "done"

    status = client.get(f"/api/jobs/{r['jobId']}").json()
    assert status["status"] == "done" and status["report"]["app"]["name"] == "Example Shop"

    t = time.perf_counter()
    again = client.post("/api/analyze", json={"url": "com.example.shop"}).json()
    assert again["cached"] is True and again["report"]["appId"] == "com.example.shop"
    assert time.perf_counter() - t < 0.2
    assert client.calls["n"] == 1  # served from cache, no second fetch

    row = again["report"]["feedback"][0]
    rv = client.get("/api/reviews", params={"report": again["report"]["id"], "issue": row["id"]}).json()
    assert rv["total"] == rv["matched"] == row["count"] == sum(rv["stars"].values())
    assert len(rv["reviews"]) == min(50, row["count"])
    # paging, rating filter and search run on the server
    page2 = client.get("/api/reviews", params={"report": again["report"]["id"], "issue": row["id"], "limit": 2, "offset": 2}).json()
    assert page2["reviews"] == rv["reviews"][2:4]
    star = int(next(iter(rv["stars"])))
    only = client.get("/api/reviews", params={"report": again["report"]["id"], "issue": row["id"], "stars": star}).json()
    assert only["matched"] == rv["stars"][str(star)] and all(r["rating"] == star for r in only["reviews"])
    word = rv["reviews"][0]["text"].split()[0]
    hit = client.get("/api/reviews", params={"report": again["report"]["id"], "issue": row["id"], "q": word.upper()}).json()
    assert 0 < hit["matched"] <= rv["total"] and all(word.lower() in (r["text"] + (r["title"] or "")).lower() for r in hit["reviews"])
    none = client.get("/api/reviews", params={"report": again["report"]["id"], "issue": row["id"], "q": "%_zzz"}).json()
    assert none["matched"] == 0
    assert client.get("/api/reviews", params={"report": "nope", "issue": "x"}).status_code == 404


def test_concurrent_requests_share_one_job(client):
    a = client.post("/api/analyze", json={"url": "com.example.shop", "refresh": True}).json()
    b = client.post("/api/analyze", json={"url": "com.example.shop", "refresh": True}).json()
    assert a["jobId"] == b["jobId"]
    _events(client, a["jobId"])


def test_not_found_streams_error(client):
    r = client.post("/api/analyze", json={"url": "com.missing.app"}).json()
    kinds = _events(client, r["jobId"])
    assert kinds[-1] == "error"
    assert client.get(f"/api/jobs/{r['jobId']}").json()["error"]["code"] == "not_found"


def test_event_stream_is_not_compressed(client):
    r = client.post("/api/analyze", json={"url": "com.example.shop", "refresh": True}).json()
    with client.stream("GET", f"/api/jobs/{r['jobId']}/events", headers={"Accept-Encoding": "gzip"}) as resp:
        assert "gzip" not in resp.headers.get("content-encoding", "")
        list(resp.iter_lines())


def test_feedback(client):
    assert client.post("/api/feedback", json={"rating": 4, "message": "Love it", "page": "/"}).status_code == 204
    assert client.post("/api/feedback", json={"message": "   "}).status_code == 400
    assert client.post("/api/feedback", json={"rating": 9}).status_code == 422


def test_all_reviews_run_streams_partial_reports_then_reuses_the_store(tmp_path, monkeypatch):
    """Pages are analysed as they arrive, a partial report appears before the
    download finishes, and a second run only analyses reviews it hasn't seen."""
    import asyncio
    import json

    from app.analysis import features

    monkeypatch.setattr(main.settings.__class__, "cache_path", property(lambda self: tmp_path / "c.db"), raising=False)
    monkeypatch.setattr(main.settings.__class__, "store_path", property(lambda self: tmp_path / "r.db"), raising=False)
    monkeypatch.setattr(jobs_module, "MILESTONES", (300,))
    monkeypatch.setattr(jobs_module, "PARTIAL_AFTER", 0.0)
    full = make_fetch(per_star=200)  # 1,000 reviews

    async def fake_play(ref, depth, pool, progress, on_page=None, on_meta=None, known=None, prior=None, **kw):
        on_meta(full.meta)
        progress({"stage": "meta", "name": full.meta.name})
        for i in range(0, len(full.reviews), 100):  # ten pages, with time to analyse between them
            on_page(full.reviews[i : i + 100])
            await asyncio.sleep(0.05)
        return full

    analysed = {"n": 0}
    real = features.extract_many

    def counting(reviews):
        analysed["n"] += len(reviews)
        return real(reviews)

    monkeypatch.setattr(jobs_module, "fetch_play", fake_play)
    monkeypatch.setattr(jobs_module, "extract_many", counting)
    with TestClient(main.app) as c:
        r = c.post("/api/analyze", json={"url": "com.example.shop", "depth": "all"}).json()
        with c.stream("GET", f"/api/jobs/{r['jobId']}/events") as s:
            lines = list(s.iter_lines())
        events = [(lines[i].split(": ", 1)[1], json.loads(lines[i + 1].split(": ", 1)[1])) for i in range(len(lines) - 1) if lines[i].startswith("event: ")]
        reports = [d["report"] for k, d in events if k == "report"]
        assert len(reports) >= 2 and reports[0]["partial"]["analyzed"] < 1000 and "partial" not in reports[-1]
        assert reports[-1]["sample"]["analyzed"] == 1000 and analysed["n"] == 1000

        # The partial report's review lists are served too.
        assert events[-1][0] == "done"

        # Second run (forced refresh): everything comes from the store, nothing is re-analysed.
        c.app.state.jobs.io.submit(lambda: None).result()  # wait for the store write
        r2 = c.post("/api/analyze", json={"url": "com.example.shop", "depth": "all", "refresh": True}).json()
        with c.stream("GET", f"/api/jobs/{r2['jobId']}/events") as s:
            list(s.iter_lines())
        assert analysed["n"] == 1000


def test_issue_reviews_filter_by_version(tmp_path):
    from app.cache import ReportCache

    cache = ReportCache(tmp_path / "c.db", 3600)
    rows = [{"rating": 1 + i % 5, "date": "2026-10-01", "thumbs": 0, "text": f"review {i}", "version": "2.0" if i % 3 else "1.0"} for i in range(30)]
    cache.put_reviews("rep", {"bug-0": rows})
    both = cache.get_reviews("rep", "bug-0")
    new = cache.get_reviews("rep", "bug-0", versions=["2.0"])
    assert both["total"] == 30 and new["total"] == 20 and all(r["version"] == "2.0" for r in new["reviews"])
    assert cache.get_reviews("rep", "bug-0", versions=["9.9"])["total"] == 0  # known issue, no reviews on that version
    assert cache.get_reviews("rep", "nope", versions=["2.0"]) is None


def test_health_ping_for_uptime_monitors(client):
    assert client.get("/health").json() == {"ok": True}
    assert client.head("/health").status_code == 200
