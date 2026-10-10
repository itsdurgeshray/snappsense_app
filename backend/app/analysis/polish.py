"""Optional title polishing with a free, local model (Ollama).

If an Ollama server is running (https://ollama.com — free, runs on your own
machine, nothing leaves it), issue titles are rewritten into crisper
one-liners. Otherwise the extracted titles are used as-is. No paid API.
"""

from __future__ import annotations

import json
import logging

import httpx

from ..config import settings
from .cluster import Issue

log = logging.getLogger(__name__)

_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "title": {"type": "string"}},
                "required": ["id", "title"],
            },
        }
    },
    "required": ["issues"],
}

_SYSTEM = (
    "You write one-line issue titles for a product team from app-store reviews. "
    "For each issue, write a title of 4 to 10 words that states the specific problem or request most of its reviews share, "
    "in plain neutral language (e.g. \"Money deducted but order not placed\", \"Too many unskippable ads in free tier\"). "
    "No quotes, no emoji, no first person, no trailing period. Return every id exactly once."
)


async def available() -> bool:
    if not settings.local_model:
        return False
    try:
        async with httpx.AsyncClient(timeout=0.6) as c:
            r = await c.get(f"{settings.local_model_url}/api/tags")
        names = {m.get("name", "") for m in r.json().get("models", [])}
        return any(n == settings.local_model or n.split(":")[0] == settings.local_model for n in names)
    except (httpx.HTTPError, ValueError):
        return False


async def polish_titles(app_name: str, issues: list[tuple[str, Issue, str]]) -> dict[str, str] | None:
    """issues: (id, issue, current_title). Returns {id: new_title} or None."""
    if not issues:
        return None
    blocks = []
    for iid, issue, current in issues:
        samples = "\n".join(f"  - {c[:220]}" for c in issue.concerns[:6])
        blocks.append(f'id: {iid}\ncategory: {issue.category}\nreviews: {issue.size}\ndraft title: {current}\nsample complaints:\n{samples}')
    body = {
        "model": settings.local_model,
        "stream": False,
        "format": _SCHEMA,
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"App: {app_name}\n\n" + "\n\n".join(blocks)},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=settings.local_model_timeout) as c:
            r = await c.post(f"{settings.local_model_url}/api/chat", json=body)
            r.raise_for_status()
        data = json.loads(r.json()["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.info("local title polish skipped: %s", e)
        return None
    valid = {iid for iid, _, _ in issues}
    out = {}
    for x in data.get("issues", []):
        t = str(x.get("title", "")).strip().strip('"').rstrip(".")
        if x.get("id") in valid and 3 <= len(t.split()) <= 14:
            out[x["id"]] = t[:1].upper() + t[1:]
    return out or None
