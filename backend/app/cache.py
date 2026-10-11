"""SQLite-backed report cache. Reads are ~0.1 ms, so they run inline."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DEPTH_RANK = {"quick": 0, "standard": 1, "deep": 2, "all": 3}


class ReportCache:
    def __init__(self, path: Path, ttl_seconds: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS reports (key TEXT PRIMARY KEY, ref TEXT NOT NULL, depth TEXT NOT NULL, created REAL NOT NULL, body TEXT NOT NULL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS reports_ref ON reports(ref)")
        # One row per review per issue, so big issues can be paged, searched
        # and sorted in SQL instead of shipping thousands of reviews at once.
        self._db.execute("DROP TABLE IF EXISTS issue_reviews")
        if "version" not in [c[1] for c in self._db.execute("PRAGMA table_info(issue_rows)")]:
            self._db.execute("DROP TABLE IF EXISTS issue_rows")  # older layout: these rows expire within hours anyway
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS issue_rows (
                report TEXT NOT NULL, issue TEXT NOT NULL, pos INTEGER NOT NULL, created REAL NOT NULL,
                rating INTEGER NOT NULL, date TEXT NOT NULL, thumbs INTEGER NOT NULL, sentiment TEXT,
                title TEXT, text TEXT NOT NULL, concern TEXT, version TEXT,
                PRIMARY KEY (report, issue, pos)
            ) WITHOUT ROWID"""
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
        from .analysis.pipeline import SCHEMA

        for d, created, body in rows:
            if not body.startswith('{"schema":%d,' % SCHEMA):
                continue  # made by older code
            # "current" reports have their own scope; the sample depths can stand in for each other.
            if d == depth or (d in DEPTH_RANK and depth in DEPTH_RANK and DEPTH_RANK[d] >= DEPTH_RANK[depth]):
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
        rows = (
            (report_id, iid, pos, now, r["rating"], r["date"], r["thumbs"], r.get("sentiment"), r.get("title"), r["text"], r.get("concern"), r.get("version"))
            for iid, reviews in by_issue.items()
            for pos, r in enumerate(reviews)
        )
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.execute("DELETE FROM issue_rows WHERE report = ?", (report_id,))
                self._db.executemany("INSERT INTO issue_rows VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                self._db.execute("DELETE FROM issue_rows WHERE created < ?", (now - self.ttl,))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    _SORT = {"relevant": "pos", "newest": "date DESC, pos", "helpful": "thumbs DESC, pos"}

    def get_reviews(
        self, report_id: str, issue_id: str, offset: int = 0, limit: int = 50, query: str = "", stars: int | None = None, sort: str = "relevant",
        versions: list[str] | None = None,
    ) -> dict | None:
        """One page of an issue's reviews, plus totals for the filters. None if the issue is unknown/expired.

        `versions`: only reviews of these app versions (the table's version picker).
        """
        base = "FROM issue_rows WHERE report = ? AND issue = ?"
        args: list = [report_id, issue_id]
        if versions:
            base += f" AND version IN ({','.join('?' * len(versions))})"
            args += versions
        with self._lock:
            star_rows = self._db.execute(f"SELECT rating, COUNT(*) {base} GROUP BY rating", args).fetchall()
            if not star_rows and not self._db.execute("SELECT 1 FROM issue_rows WHERE report = ? AND issue = ? LIMIT 1", (report_id, issue_id)).fetchone():
                return None
            where, wargs = base, list(args)
            if stars:
                where += " AND rating = ?"
                wargs.append(stars)
            q = query.strip()
            if q:
                like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                where += " AND (text LIKE ? ESCAPE '\\' OR IFNULL(title, '') LIKE ? ESCAPE '\\')"
                wargs += [like, like]
            matched = self._db.execute(f"SELECT COUNT(*) {where}", wargs).fetchone()[0]
            rows = self._db.execute(
                f"SELECT rating, date, thumbs, sentiment, title, text, concern, version {where} ORDER BY {self._SORT.get(sort, 'pos')} LIMIT ? OFFSET ?",
                [*wargs, max(1, min(limit, 200)), max(0, offset)],
            ).fetchall()
        stars_count = {str(k): v for k, v in star_rows}
        return {
            "total": sum(stars_count.values()),
            "matched": matched,
            "stars": stars_count,
            "reviews": [
                {"rating": r, "date": d, "thumbs": t, "sentiment": s, "title": ti, "text": tx, "concern": c, "version": v}
                for r, d, t, s, ti, tx, c, v in rows
            ],
        }

    def add_feedback(self, rating: int | None, message: str, page: str | None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO feedback (created, rating, message, page) VALUES (?, ?, ?, ?)", (time.time(), rating, message, page)
            )

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM reports WHERE created > ?", (time.time() - self.ttl,)).fetchone()[0]
