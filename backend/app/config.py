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

    # Optional free local model (Ollama) to polish issue titles. Auto-detected;
    # set SNAPPSENSE_LOCAL_MODEL= (empty) to disable.
    local_model: str = field(default_factory=lambda: os.environ.get("SNAPPSENSE_LOCAL_MODEL", "qwen2.5:3b"))
    local_model_url: str = field(default_factory=lambda: os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"))
    local_model_timeout: float = field(default_factory=lambda: float(os.environ.get("SNAPPSENSE_LOCAL_MODEL_TIMEOUT", 30)))

    # App Store Connect (optional; only for apps the key's team owns)
    asc_issuer_id: str | None = field(default_factory=lambda: os.environ.get("ASC_ISSUER_ID"))
    asc_key_id: str | None = field(default_factory=lambda: os.environ.get("ASC_KEY_ID"))
    asc_private_key_path: str | None = field(default_factory=lambda: os.environ.get("ASC_PRIVATE_KEY_PATH"))

    cors_origins: list[str] = field(
        default_factory=lambda: os.environ.get("SNAPPSENSE_CORS", "http://localhost:5179,http://127.0.0.1:5179").split(",")
    )

    @property
    def asc_enabled(self) -> bool:
        return bool(self.asc_issuer_id and self.asc_key_id and self.asc_private_key_path)


settings = Settings()
