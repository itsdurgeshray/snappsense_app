"""Analysis jobs: single-flight, progress streaming, progressive results.

A job publishes a sequence of events that any number of SSE subscribers can
replay and follow:

    progress  {stage: queued|meta|fetch|analyze|polish, ...}
    report    {report}            ← partial reports during long runs, then the final one
    done      {}
    error     {code, message}

Two requests for the same app share one job, so a burst of users on a
trending app costs one fetch.

Large runs ("all reviews") are built to stay fast and small:

* each page of reviews is analysed as soon as it arrives, while the rest
  downloads (per-review analysis is the only cost that grows with size);
* reviews already in the review store skip both download and analysis;
* partial reports are published at milestones, so the dashboard appears
  within seconds and fills in while the run continues;
* only one such run executes at a time, so memory stays bounded.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .analysis import polish
from .analysis.features import Feat, extract_many
from .analysis.pipeline import analyze
from .cache import ReportCache
from .config import settings
from .links import AppRef
from .models import AppMeta, Depth, FetchResult, Review
from .sources.appstore import fetch_appstore
from .sources.playstore import AppNotFound, fetch_play, target_for
from .store import ReviewStore

log = logging.getLogger(__name__)

PROGRESS_INTERVAL = 0.12  # seconds between fetch-progress events
JOB_RETENTION = 15 * 60
CHUNK = 2000  # reviews analysed per step while downloading
MILESTONES = (4000, 15000, 40000)  # partial reports during long runs (while still downloading)
PARTIAL_AFTER = 2.5  # seconds: runs that finish faster (e.g. from the store) skip partials
PARTIAL_GAP = 8.0  # seconds between partial reports
PARTIAL_UNTIL = 0.6  # no partial once this share of the limit is in: the final report is close


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
    def __init__(self, cache: ReportCache, store: ReviewStore | None = None):
        self.cache = cache
        self.store = store
        self.jobs: dict[str, Job] = {}
        self.active: dict[str, Job] = {}
        self.pool = ThreadPoolExecutor(max_workers=settings.fetch_workers, thread_name_prefix="fetch")
        self.cpu = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analyze")
        self.io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="store")
        self.slots = asyncio.Semaphore(settings.max_concurrent_jobs)
        self.full_slots = asyncio.Semaphore(settings.max_full_jobs)
        self.all_slots = asyncio.Semaphore(1)  # "all reviews" runs are the biggest: one at a time

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

        heavy = job.depth in ("all", "current")
        try:
            await job.publish("progress", {"stage": "queued"})
            async with self.slots, (self.full_slots if heavy else _NoLock()), (self.all_slots if job.depth == "all" else _NoLock()):
                await job.publish("progress", {"stage": "fetch", "fetched": 0})
                fetched, feats, dirty = await self._fetch_and_extract(job, key, progress)
                t_fetch = time.perf_counter()
                if not fetched.reviews:
                    raise AppNotFound("This app has no public reviews to analyse yet.")

                await job.publish("progress", {"stage": "analyze", "reviews": len(fetched.reviews)})
                report, issue_reviews, polish_input = await loop.run_in_executor(self.cpu, lambda: analyze(fetched, feats=feats))
                t_analyze = time.perf_counter()
                if self.store:  # remember reviews + analysis for the next run (off the event loop)
                    new = [r for r in fetched.reviews if r.id in dirty]
                    loop.run_in_executor(self.io, self._save, job.ref.key, new, feats, fetched.store_coverage)

            report.update({
                "id": key,
                "depth": job.depth,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "timings": {"fetchMs": round(1000 * (t_fetch - t0)), "analyzeMs": round(1000 * (t_analyze - t_fetch))},
            })
            report["timings"]["totalMs"] = round(1000 * (t_analyze - t0))
            job.report = report
            await loop.run_in_executor(self.io, self.cache.put_reviews, key, issue_reviews)
            self.cache.put(job.ref.key, job.depth, report)
            del issue_reviews, fetched, feats
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
            if heavy:
                gc.collect()  # hand the memory of a big run back before the next one

    async def _fetch_and_extract(self, job: Job, key: str, progress) -> tuple[FetchResult, dict[str, Feat], set[str]]:
        """Downloads reviews while analysing each page as it arrives.

        Returns (fetch result, per-review analysis by id, ids that are new or
        changed since the store last saw them).
        """
        loop = asyncio.get_running_loop()
        known: dict[str, Review] = {}
        feats: dict[str, Feat] = {}
        prior = None
        if self.store:
            stored, feats, prior = await loop.run_in_executor(self.io, self.store.load, job.ref.key)
            known = {r.id: r for r in stored}
            del stored

        pending: list[Review] = []
        seen: list[Review] = []
        dirty: set[str] = set()
        wake = asyncio.Event()
        meta_box: list[AppMeta] = []
        # Partial reports only for explicit "all reviews" runs; everything else
        # shows one complete report straight from the loading screen.
        milestones = list(MILESTONES) if job.depth == "all" else []
        limit = target_for(job.depth) if job.ref.store == "play" else None
        started = last_report = time.perf_counter()

        def on_page(batch: list[Review]) -> None:
            pending.extend(batch)
            wake.set()

        if job.ref.store == "play":
            fetch = asyncio.create_task(
                fetch_play(job.ref, job.depth, self.pool, progress, on_page=on_page, known=known, prior=prior, on_meta=meta_box.append)
            )
        else:
            fetch = asyncio.create_task(fetch_appstore(job.ref, job.depth, progress, on_page=on_page))
        fetch.add_done_callback(lambda _: wake.set())

        while True:
            await wake.wait()
            wake.clear()
            while pending:
                chunk, pending[:] = pending[:CHUNK], pending[CHUNK:]
                todo = []
                for r in chunk:
                    old = known.get(r.id)
                    if old is None or old.text != r.text or old.rating != r.rating:
                        dirty.add(r.id)
                        feats.pop(r.id, None)
                    if r.id not in feats:
                        todo.append(r)
                if todo:
                    for r, f in zip(todo, await loop.run_in_executor(self.cpu, extract_many, todo)):
                        feats[r.id] = f
                        dirty.add(r.id)
                seen.extend(chunk)
                if milestones and len(seen) >= milestones[0] and meta_box and not fetch.done():
                    while milestones and len(seen) >= milestones[0]:
                        milestones.pop(0)
                    near_end = limit is not None and len(seen) >= PARTIAL_UNTIL * limit
                    first = job.report is None
                    slow = time.perf_counter() - started >= PARTIAL_AFTER
                    if slow and not near_end and (first or time.perf_counter() - last_report >= PARTIAL_GAP):
                        await self._partial(job, key, meta_box[0], list(seen), feats)
                        last_report = time.perf_counter()
            if fetch.done() and not pending:
                break
        known.clear()
        result = fetch.result()
        dirty.update(r.id for r in result.reviews if r.id not in feats)  # e.g. App Store Connect history, analysed at the end
        return result, feats, dirty

    def _save(self, app: str, reviews: list[Review], feats: dict[str, Feat], coverage) -> None:
        try:
            self.store.save(app, reviews, feats, coverage)
        except Exception:  # the store is an optimisation: never fail a job over it
            log.exception("couldn't store reviews for %s", app)

    async def _partial(self, job: Job, key: str, meta: AppMeta, reviews: list[Review], feats: dict[str, Feat]) -> None:
        """A report from the reviews analysed so far, while the download continues."""
        loop = asyncio.get_running_loop()
        snapshot = FetchResult(meta=meta, reviews=reviews, sources=[], notes=["partial"])
        report, issue_reviews, _ = await loop.run_in_executor(self.cpu, lambda: analyze(snapshot, feats=feats))
        report.update({
            "id": key,
            "depth": job.depth,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "partial": {"analyzed": len(reviews), "limit": target_for(job.depth) if job.ref.store == "play" else None},
        })
        await loop.run_in_executor(self.io, self.cache.put_reviews, key, issue_reviews)
        job.report = report
        await job.publish("report", {"report": report})

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


class _NoLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False
