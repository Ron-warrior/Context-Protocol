"""Request dispatch and the mapping from exceptions to status codes."""

from __future__ import annotations

from config.defaults import MAX_BODY_MB, NOT_FOUND_CODE
from service.auth import TokenExpired
from service.retry import RetryExhausted
from service.storage import StorageCorrupt

ROUTES = {
    "/session": "issue_session",
    "/session/refresh": "refresh_session",
    "/health": "health",
}


def resolve(path: str) -> str:
    handler = ROUTES.get(path)
    if handler is None:
        raise LookupError(f"no route for {path}")
    return handler


def status_for(exc: Exception) -> int:
    """The single place that decides what a failure looks like on the wire."""
    if isinstance(exc, LookupError):
        return NOT_FOUND_CODE
    if isinstance(exc, TokenExpired):
        return 401
    if isinstance(exc, StorageCorrupt):
        return 500
    if isinstance(exc, RetryExhausted):
        return 503
    return 500


def body_limit_bytes() -> int:
    return MAX_BODY_MB * 1024 * 1024
