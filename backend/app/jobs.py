"""Analysis jobs: single-flight, progress streaming, progressive results.

A job publishes a sequence of events that any number of SSE subscribers can
replay and follow:

    progress  {stage: queued|meta|fetch|analyze|polish, ...}
    report    {report}            ← once ready; again if a local model polishes titles
    done      {}
    error     {code, message}

Two requests for the same app share one job, so a burst of users on a
trending app costs one fetch.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .analysis import polish
from .analysis.pipeline import analyze
from .cache import ReportCache
from .config import settings
from .links import AppRef
from .models import Depth
from .sources.appstore import fetch_appstore
from .sources.playstore import AppNotFound, fetch_play

log = logging.getLogger(__name__)

PROGRESS_INTERVAL = 0.12  # seconds between fetch-progress events
JOB_RETENTION = 15 * 60


@dataclass
class Job:
    id: str
    ref: AppRef
    depth: Depth
    status: str = "running"  # running | done | error
    events: list[tuple[str, dict]] = field(default_factory=list)
    report: dict | None = None
    error: dict | None = None
    created: float = field(default_factory=time.time)
    finished: float | None = None
    _cond: asyncio.Condition = field(default_factory=asyncio.Condition)

    async def publish(self, kind: str, data: dict, final_status: str | None = None) -> None:
        async with self._cond:
            self.events.append((kind, data))
            if final_status:  # set atomically with the terminal event so followers never miss it
                self.status = final_status
            self._cond.notify_all()

    async def follow(self, start: int = 0):
        """Yields (index, kind, data) from `start`, waiting for new events until the job ends."""
        i = start
        while True:
            async with self._cond:
                while i >= len(self.events) and self.status == "running":
                    try:
                        await asyncio.wait_for(self._cond.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                batch = self.events[i:]
            if not batch:
                if self.status != "running":
                    return
                yield i, "ping", {}
                continue
            for kind, data in batch:
                yield i, kind, data
                i += 1


class JobManager:
    def __init__(self, cache: ReportCache):
        self.cache = cache
        self.jobs: dict[str, Job] = {}
        self.active: dict[str, Job] = {}
        self.pool = ThreadPoolExecutor(max_workers=settings.fetch_workers, thread_name_prefix="fetch")
        self.cpu = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analyze")
        self.slots = asyncio.Semaphore(settings.max_concurrent_jobs)

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def start(self, ref: AppRef, depth: Depth, refresh: bool = False) -> tuple[Job | None, dict | None]:
        """Returns (job, cached_report). Exactly one of them is set."""
        self._prune()
        if not refresh:
            cached = self.cache.get(ref.key, depth)
            if cached:
                return None, cached
        key = f"{ref.key}:{depth}"
        if key in self.active:
            return self.active[key], None
        job = Job(id=uuid.uuid4().hex[:12], ref=ref, depth=depth)
        self.jobs[job.id] = job
        self.active[key] = job
        asyncio.create_task(self._run(job, key))
        return job, None

    async def _run(self, job: Job, key: str) -> None:
        t0 = time.perf_counter()
        loop = asyncio.get_running_loop()
        last = {"t": 0.0}

        def progress(ev: dict) -> None:
            # Called from the event loop (App Store) or via run_in_executor
            # callbacks on the loop (Play) — always on the loop thread.
            now = time.perf_counter()
            if ev.get("stage") == "fetch" and now - last["t"] < PROGRESS_INTERVAL:
                return
            last["t"] = now
            loop.create_task(job.publish("progress", ev))

        try:
            await job.publish("progress", {"stage": "queued"})
            async with self.slots:
                await job.publish("progress", {"stage": "fetch", "fetched": 0})
                if job.ref.store == "play":
                    fetched = await fetch_play(job.ref, job.depth, self.pool, progress)
                else:
                    fetched = await fetch_appstore(job.ref, job.depth, progress)
                t_fetch = time.perf_counter()
                if not fetched.reviews:
                    raise AppNotFound("This app has no public reviews to analyse yet.")

                await job.publish("progress", {"stage": "analyze", "reviews": len(fetched.reviews)})
                report, issue_reviews, polish_input = await loop.run_in_executor(self.cpu, analyze, fetched)
                t_analyze = time.perf_counter()

            report.update({
                "id": key,
                "depth": job.depth,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "timings": {"fetchMs": round(1000 * (t_fetch - t0)), "analyzeMs": round(1000 * (t_analyze - t_fetch))},
            })
            report["timings"]["totalMs"] = round(1000 * (t_analyze - t0))
            job.report = report
            self.cache.put_reviews(key, issue_reviews)
            self.cache.put(job.ref.key, job.depth, report)
            await job.publish("report", {"report": report})

            # Optional: a free local model (Ollama) rewrites titles; skipped if not running.
            if polish_input and await polish.available():
                await job.publish("progress", {"stage": "polish", "issues": len(polish_input)})
                t_p = time.perf_counter()
                titles = await polish.polish_titles(report["app"]["name"], polish_input)
                if titles:
                    report = {**report, "feedback": [{**f, "feedback": titles.get(f["id"], f["feedback"])} for f in report["feedback"]]}
                    report["timings"] = {**report["timings"], "polishMs": round(1000 * (time.perf_counter() - t_p)), "totalMs": round(1000 * (time.perf_counter() - t0))}
                    job.report = report
                    self.cache.put(job.ref.key, job.depth, report)
                    await job.publish("report", {"report": report})

            await job.publish("done", {}, final_status="done")
        except AppNotFound as e:
            await self._fail(job, "not_found", str(e))
        except Exception as e:  # never leave a subscriber hanging
            log.exception("job %s failed", job.id)
            await self._fail(job, "failed", f"Couldn't analyse this app right now ({type(e).__name__}). Please try again.")
        finally:
            job.finished = time.time()
            self.active.pop(key, None)

    async def _fail(self, job: Job, code: str, message: str) -> None:
        job.error = {"code": code, "message": message}
        await job.publish("error", job.error, final_status="error")

    def _prune(self) -> None:
        cutoff = time.time() - JOB_RETENTION
        for jid in [j.id for j in self.jobs.values() if j.finished and j.finished < cutoff]:
            self.jobs.pop(jid, None)

    def status(self, job: Job) -> dict[str, Any]:
        last_progress = next((d for k, d in reversed(job.events) if k == "progress"), None)
        return {"jobId": job.id, "status": job.status, "report": job.report, "error": job.error, "progress": last_progress}
