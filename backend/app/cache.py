"""SQLite-backed report cache. Reads are ~0.1 ms, so they run inline."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DEPTH_RANK = {"quick": 0, "standard": 1, "deep": 2}


class ReportCache:
    def __init__(self, path: Path, ttl_seconds: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS reports (key TEXT PRIMARY KEY, ref TEXT NOT NULL, depth TEXT NOT NULL, created REAL NOT NULL, body TEXT NOT NULL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS reports_ref ON reports(ref)")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS issue_reviews (report TEXT NOT NULL, issue TEXT NOT NULL, created REAL NOT NULL, body TEXT NOT NULL, PRIMARY KEY (report, issue))"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY, created REAL NOT NULL, rating INTEGER, message TEXT NOT NULL, page TEXT)"
        )
        self._lock = threading.Lock()
        self.ttl = ttl_seconds

    def get(self, ref_key: str, depth: str) -> dict | None:
        """Freshest report for this app at the requested depth or deeper."""
        with self._lock:
            rows = self._db.execute(
                "SELECT depth, created, body FROM reports WHERE ref = ? AND created > ? ORDER BY created DESC",
                (ref_key, time.time() - self.ttl),
            ).fetchall()
        for d, created, body in rows:
            if DEPTH_RANK[d] >= DEPTH_RANK[depth]:
                report = json.loads(body)
                report["cachedAt"] = created
                return report
        return None

    def put(self, ref_key: str, depth: str, report: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO reports (key, ref, depth, created, body) VALUES (?, ?, ?, ?, ?)",
                (f"{ref_key}:{depth}", ref_key, depth, time.time(), json.dumps(report, separators=(",", ":"))),
            )

    def put_reviews(self, report_id: str, by_issue: dict[str, list[dict]]) -> None:
        now = time.time()
        with self._lock:
            self._db.execute("DELETE FROM issue_reviews WHERE report = ?", (report_id,))
            self._db.executemany(
                "INSERT INTO issue_reviews (report, issue, created, body) VALUES (?, ?, ?, ?)",
                [(report_id, iid, now, json.dumps(rows, separators=(",", ":"))) for iid, rows in by_issue.items()],
            )
            self._db.execute("DELETE FROM issue_reviews WHERE created < ?", (now - self.ttl,))

    def get_reviews(self, report_id: str, issue_id: str) -> list[dict] | None:
        with self._lock:
            row = self._db.execute("SELECT body FROM issue_reviews WHERE report = ? AND issue = ?", (report_id, issue_id)).fetchone()
        return json.loads(row[0]) if row else None

    def add_feedback(self, rating: int | None, message: str, page: str | None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO feedback (created, rating, message, page) VALUES (?, ?, ?, ?)", (time.time(), rating, message, page)
            )

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM reports WHERE created > ?", (time.time() - self.ttl,)).fetchone()[0]
