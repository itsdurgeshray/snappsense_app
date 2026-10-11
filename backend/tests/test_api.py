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
    calls = {"n": 0}

    async def fake_play(ref, depth, pool, progress):
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
    assert rv["count"] == row["count"] == len(rv["reviews"])
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
