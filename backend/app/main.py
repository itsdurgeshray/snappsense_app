"""Snappsense API.

    POST /api/analyze              start (or reuse) an analysis → job id or cached report
    GET  /api/jobs/{id}            current job state
    GET  /api/jobs/{id}/events     live progress + results (Server-Sent Events)
    GET  /api/reviews?report=…&issue=…   every review behind one feedback row
    GET  /api/resolve?url=…        validate/parse a store link
    POST /api/feedback             store a "Give feedback" message
    GET  /api/health               service status
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .analysis import polish
from .cache import ReportCache
from .config import settings
from .jobs import JobManager
from .links import AppRef, LinkError, parse_link

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("snappsense")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.jobs = JobManager(ReportCache(settings.cache_path, settings.cache_ttl_seconds))
    yield
    app.state.jobs.pool.shutdown(wait=False, cancel_futures=True)
    app.state.jobs.cpu.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Snappsense API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
class SelectiveGZip(GZipMiddleware):
    """Gzip everything except the live event stream: compression buffers SSE
    until the response ends, which would freeze progress in the browser."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].endswith("/events"):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


app.add_middleware(SelectiveGZip, minimum_size=1024)


class AnalyzeBody(BaseModel):
    url: str | None = Field(None, description="Google Play or App Store link")
    store: Literal["play", "app"] | None = None
    appId: str | None = None
    country: str | None = None
    depth: Literal["quick", "standard", "deep"] = "standard"
    refresh: bool = False


def _ref(body: AnalyzeBody) -> AppRef:
    try:
        if body.url:
            return parse_link(body.url, body.country)
        if body.store and body.appId:
            ref = parse_link(body.appId, body.country)
            if ref.store != body.store:
                raise LinkError("The app id doesn't match the selected store.")
            return ref
    except LinkError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    raise HTTPException(status_code=400, detail="Send a store link (url) or store + appId.")


class FeedbackBody(BaseModel):
    rating: int | None = Field(None, ge=1, le=5)
    message: str = Field("", max_length=2000)
    page: str | None = Field(None, max_length=300)


@app.post("/api/feedback", status_code=204)
async def feedback(body: FeedbackBody, request: Request):
    message = body.message.strip()
    if body.rating is None and not message:
        raise HTTPException(status_code=400, detail="Add a rating or a message.")
    jobs: JobManager = request.app.state.jobs
    jobs.cache.add_feedback(body.rating, message, body.page)
    # Also logged, so it shows up in the hosting dashboard's logs.
    log.info("feedback rating=%s page=%s message=%r", body.rating, body.page, message)


@app.get("/api/health")
async def health(request: Request):
    jobs: JobManager = request.app.state.jobs
    return {
        "ok": True,
        "localModel": settings.local_model if await polish.available() else None,
        "appStoreConnect": settings.asc_enabled,
        "cachedReports": jobs.cache.count(),
        "activeJobs": len(jobs.active),
    }


@app.get("/api/resolve")
async def resolve(url: str, country: str | None = None):
    try:
        ref = parse_link(url, country)
    except LinkError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"store": ref.store, "appId": ref.app_id, "country": ref.country}


@app.post("/api/analyze")
async def analyze(body: AnalyzeBody, request: Request):
    ref = _ref(body)
    jobs: JobManager = request.app.state.jobs
    job, cached = jobs.start(ref, body.depth, refresh=body.refresh)
    base = {"store": ref.store, "appId": ref.app_id, "country": ref.country}
    if cached:
        return {**base, "status": "done", "cached": True, "report": cached}
    return {**base, "status": job.status, "cached": False, "jobId": job.id, "report": job.report}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str, request: Request):
    job = request.app.state.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return request.app.state.jobs.status(job)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    job = request.app.state.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    start = int(request.headers.get("last-event-id", -1)) + 1

    async def stream():
        yield "retry: 1500\n\n"
        async for i, kind, data in job.follow(start):
            if await request.is_disconnected():
                return
            if kind == "ping":
                yield ": ping\n\n"
                continue
            yield f"id: {i}\nevent: {kind}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"
            if kind in ("done", "error"):
                return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.get("/api/reviews")
async def issue_reviews(report: str, issue: str, request: Request):
    rows = request.app.state.jobs.cache.get_reviews(report, issue)
    if rows is None:
        raise HTTPException(status_code=404, detail="These reviews have expired — reload the report.")
    return {"issue": issue, "count": len(rows), "reviews": rows}
