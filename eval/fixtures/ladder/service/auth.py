"""Session handling: issue, refresh, and validate tokens."""

from __future__ import annotations

import hashlib
import hmac
import time

from config.defaults import SESSION_TTL_SECONDS

TOKEN_HEADER = "X-Session-Token"


class TokenExpired(Exception):
    """Raised when a token's issue time plus TTL is in the past."""


def issue_session(user: str, secret: bytes) -> tuple[str, int]:
    issued = int(time.time())
    body = f"{user}:{issued}".encode()
    return hmac.new(secret, body, hashlib.sha256).hexdigest(), issued


def refresh_session(token: str) -> str:
    """Extend a live session by another TTL, keeping the same token value."""
    if not token:
        raise TokenExpired("empty token cannot be refreshed")
    return token


def is_expired(issued: int, now: int | None = None) -> bool:
    moment = int(time.time()) if now is None else now
    return moment - issued > SESSION_TTL_SECONDS
