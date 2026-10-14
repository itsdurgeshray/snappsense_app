"""Runtime settings, read once from the environment (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Cache
    cache_path: Path = field(default_factory=lambda: Path(os.environ.get("SNAPPSENSE_CACHE_PATH", ROOT / "data" / "cache.db")))
    cache_ttl_seconds: int = field(default_factory=lambda: _int("SNAPPSENSE_CACHE_TTL", 6 * 3600))

    # Concurrency
    max_concurrent_jobs: int = field(default_factory=lambda: _int("SNAPPSENSE_MAX_JOBS", 4))
    fetch_workers: int = field(default_factory=lambda: _int("SNAPPSENSE_FETCH_WORKERS", 24))
    # Analyses read up to ~30k reviews and peak near 400 MB, so on a 512 MB
    # server they run one at a time (others wait their turn). Raise with RAM.
    max_full_jobs: int = field(default_factory=lambda: _int("SNAPPSENSE_MAX_FULL_JOBS", 1))

    # "All reviews" limits. Apps with fewer reviews than max_reviews are read
    # completely; bigger ones get their newest max_reviews. Measured peak
    # memory is ~155 MB + ~3 MB per 1,000 reviews (100k → 450 MB), so the
    # default (~300 MB) fits a 512 MB server; raise it on bigger machines.
    max_reviews: int = field(default_factory=lambda: _int("SNAPPSENSE_MAX_REVIEWS", 50_000))
    # Default reports cover the versions people use now (scope.py), never more
    # than `period_days` back; without version data, the last `period_days`.
    period_days: int = field(default_factory=lambda: _int("SNAPPSENSE_PERIOD_DAYS", 90))
    # Google Play page size and parallel requests. Bigger is faster but each
    # in-flight page costs memory; lower them on small servers.
    play_page: int = field(default_factory=lambda: _int("SNAPPSENSE_PLAY_PAGE", 4500))
    play_inflight: int = field(default_factory=lambda: _int("SNAPPSENSE_PLAY_INFLIGHT", 3))

    # Sentiment trends reach back this far.
    trend_days: int = field(default_factory=lambda: _int("SNAPPSENSE_TREND_DAYS", 365))
    # Seconds (from the start of a run) the trend sample may take, and its parallel requests.
    trend_budget_seconds: int = field(default_factory=lambda: _int("SNAPPSENSE_TREND_BUDGET", 35))
    trend_lanes: int = field(default_factory=lambda: _int("SNAPPSENSE_TREND_LANES", 5))
    # Review ceiling for those runs (most apps need far fewer).
    current_max_reviews: int = field(default_factory=lambda: _int("SNAPPSENSE_CURRENT_MAX", 20_000))
    fetch_budget_seconds: int = field(default_factory=lambda: _int("SNAPPSENSE_FETCH_BUDGET", 300))

    # Review store: every analysed review is kept so later runs (refresh,
    # deeper analysis) only fetch and analyse what's new.
    store_path: Path = field(default_factory=lambda: Path(os.environ.get("SNAPPSENSE_STORE_PATH", ROOT / "data" / "reviews.db")))
    store_max_reviews: int = field(default_factory=lambda: _int("SNAPPSENSE_STORE_MAX", 1_000_000))

    # Optional free local model (Ollama) to polish issue titles. Auto-detected;
    # set SNAPPSENSE_LOCAL_MODEL= (empty) to disable.
    local_model: str = field(default_factory=lambda: os.environ.get("SNAPPSENSE_LOCAL_MODEL", "qwen2.5:3b"))
    local_model_url: str = field(default_factory=lambda: os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"))
    local_model_timeout: float = field(default_factory=lambda: float(os.environ.get("SNAPPSENSE_LOCAL_MODEL_TIMEOUT", 30)))

    # App Store Connect (optional; only for apps the key's team owns)
    asc_issuer_id: str | None = field(default_factory=lambda: os.environ.get("ASC_ISSUER_ID"))
    asc_key_id: str | None = field(default_factory=lambda: os.environ.get("ASC_KEY_ID"))
    asc_private_key_path: str | None = field(default_factory=lambda: os.environ.get("ASC_PRIVATE_KEY_PATH"))

    # Exact origins, comma-separated; spaces and trailing slashes are ignored.
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip().rstrip("/")
            for o in os.environ.get("SNAPPSENSE_CORS", "http://localhost:5179,http://127.0.0.1:5179").split(",")
            if o.strip()
        ]
    )
    # Optional pattern, e.g. to allow every Vercel preview deployment.
    cors_origin_regex: str | None = field(default_factory=lambda: os.environ.get("SNAPPSENSE_CORS_REGEX") or None)

    @property
    def asc_enabled(self) -> bool:
        return bool(self.asc_issuer_id and self.asc_key_id and self.asc_private_key_path)


settings = Settings()
