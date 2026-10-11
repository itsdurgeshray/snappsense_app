"""Every review we've fetched and analysed, per app (SQLite).

Reports expire after a few hours, but reviews don't change much: keeping them
(with their per-review analysis) means a refresh, a deeper analysis or an
"all reviews" run only fetches and analyses what's new. When the store grows
past `max_reviews`, the apps used least recently are dropped first.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .analysis.features import VERSION as FEAT_VERSION, Feat
from .models import Review

Coverage = dict[int, datetime | None]


class ReviewStore:
    def __init__(self, path: Path, max_reviews: int, per_app: int = 60_000):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS reviews (
                app TEXT NOT NULL, id TEXT NOT NULL, rating INTEGER NOT NULL, at TEXT NOT NULL,
                title TEXT NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL, thumbs INTEGER NOT NULL, version TEXT,
                fv INTEGER, sentiment TEXT, category TEXT, concern TEXT, feature TEXT,
                PRIMARY KEY (app, id)
            ) WITHOUT ROWID"""
        )
        self._db.execute("CREATE TABLE IF NOT EXISTS apps (app TEXT PRIMARY KEY, used REAL NOT NULL, coverage TEXT)")
        self._db.execute("CREATE INDEX IF NOT EXISTS reviews_app_at ON reviews(app, at)")
        self._lock = threading.Lock()
        self.max_reviews = max_reviews
        self.per_app = per_app  # newest reviews kept per app (and the most ever loaded into memory)

    def load(self, app: str) -> tuple[list[Review], dict[str, Feat], Coverage | None]:
        """An app's newest stored reviews (at most `per_app`), their analysis (if current) and the Play coverage they represent."""
        reviews: list[Review] = []
        feats: dict[str, Feat] = {}
        intern = sys.intern
        with self._lock:
            # Streamed row by row: no second full copy of the app's reviews in memory.
            for rid, rating, at, title, text, source, thumbs, version, fv, s, cat, concern, feature in self._db.execute(
                "SELECT id, rating, at, title, text, source, thumbs, version, fv, sentiment, category, concern, feature FROM reviews WHERE app = ? ORDER BY at DESC LIMIT ?",
                (app, self.per_app),
            ):
                reviews.append(Review(
                    id=rid, text=text, rating=rating, at=datetime.fromisoformat(at), title=title,
                    source=intern(source), thumbs=thumbs, version=intern(version) if version else None,
                ))
                if fv == FEAT_VERSION:
                    feats[rid] = Feat(intern(s), intern(cat), concern, feature)
            state = self._db.execute("SELECT coverage FROM apps WHERE app = ?", (app,)).fetchone()
            self._db.execute("UPDATE apps SET used = ? WHERE app = ?", (time.time(), app))
        coverage = None
        if state and state[0]:
            coverage = {int(k): (datetime.fromisoformat(v) if v else None) for k, v in json.loads(state[0]).items()}
        return reviews, feats, coverage

    def save(self, app: str, reviews: list[Review], feats: dict[str, Feat], coverage: Coverage | None = None) -> None:
        rows = []
        for r in reviews:
            f = feats.get(r.id)
            rows.append((
                app, r.id, r.rating, r.at.isoformat(), r.title, r.text, r.source, r.thumbs, r.version,
                FEAT_VERSION if f else None, f.sentiment if f else None, f.category if f else None, f.concern if f else None, f.feature if f else None,
            ))
        cov = json.dumps({str(k): (v.isoformat() if v else None) for k, v in coverage.items()}) if coverage is not None else None
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.executemany("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
                self._db.execute(
                    "INSERT INTO apps (app, used, coverage) VALUES (?, ?, ?) ON CONFLICT(app) DO UPDATE SET used = excluded.used, coverage = COALESCE(excluded.coverage, apps.coverage)",
                    (app, time.time(), cov),
                )
                # Keep each app's newest `per_app` reviews; older ones no longer match the stored coverage.
                cut = self._db.execute("SELECT at FROM reviews WHERE app = ? ORDER BY at DESC LIMIT 1 OFFSET ?", (app, self.per_app)).fetchone()
                if cut:
                    self._db.execute("DELETE FROM reviews WHERE app = ? AND at <= ?", (app, cut[0]))
                    # Each star is now only complete back to the cut.
                    row = self._db.execute("SELECT coverage FROM apps WHERE app = ?", (app,)).fetchone()
                    if row and row[0]:
                        trimmed = {k: (max(v, cut[0]) if v else cut[0]) for k, v in json.loads(row[0]).items()}
                        self._db.execute("UPDATE apps SET coverage = ? WHERE app = ?", (json.dumps(trimmed), app))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        self._prune()

    def count(self, app: str | None = None) -> int:
        with self._lock:
            if app:
                return self._db.execute("SELECT COUNT(*) FROM reviews WHERE app = ?", (app,)).fetchone()[0]
            return self._db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]

    def _prune(self) -> None:
        """Drop the least recently used apps until the store fits its budget (the newest app always stays)."""
        with self._lock:
            total = self._db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
            if total <= self.max_reviews:
                return
            apps = self._db.execute("SELECT app FROM apps ORDER BY used ASC").fetchall()
            for (app,) in apps[:-1]:
                n = self._db.execute("SELECT COUNT(*) FROM reviews WHERE app = ?", (app,)).fetchone()[0]
                self._db.execute("DELETE FROM reviews WHERE app = ?", (app,))
                self._db.execute("DELETE FROM apps WHERE app = ?", (app,))
                total -= n
                if total <= self.max_reviews:
                    break
