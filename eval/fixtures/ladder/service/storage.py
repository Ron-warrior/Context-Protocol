"""A tiny durable store. One file, no dependency, corruptible on purpose."""

from __future__ import annotations

import json
from pathlib import Path

SESSIONS_PATH = "sessions.db"


class StorageCorrupt(Exception):
    """Raised when the store cannot be parsed; the caller must not overwrite it."""


def load(root: Path) -> dict:
    path = root / SESSIONS_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise StorageCorrupt(f"{SESSIONS_PATH} is unreadable: {exc}") from exc


def save(root: Path, rows: dict) -> None:
    path = root / SESSIONS_PATH
    path.write_text(json.dumps(rows, sort_keys=True), encoding="utf-8")


class RateLimiter:
    """Per-user token bucket. Deliberately simple: one process, one dict."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.counts: dict[str, int] = {}

    def allow(self, user: str) -> bool:
        used = self.counts.get(user, 0)
        if used >= self.per_minute:
            return False
        self.counts[user] = used + 1
        return True
