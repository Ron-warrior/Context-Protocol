"""Bounded retries with exponential backoff."""

from __future__ import annotations

import time

MAX_ATTEMPTS = 5
BACKOFF_BASE_S = 0.4


class RetryExhausted(Exception):
    """Raised after the final attempt fails."""


def backoff_delay(attempt: int) -> float:
    """Seconds to sleep before attempt N, growing geometrically."""
    return BACKOFF_BASE_S * (2 ** max(0, attempt - 1))


def with_retries(call):
    """Call `call` until it stops raising, or MAX_ATTEMPTS is spent."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return call()
        except OSError:
            if attempt == MAX_ATTEMPTS:
                raise RetryExhausted(f"gave up after {attempt} attempts")
            time.sleep(backoff_delay(attempt))
    raise RetryExhausted("unreachable")
