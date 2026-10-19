"""Per-user rate limits, so one account can't run up the AI bill or fill the disk.

Counts are kept in memory, per API process. With several processes each one
counts separately; a shared store (Redis) is on the roadmap for that.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import deque

from fastapi import HTTPException


def _limit(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


# (limit, window in seconds, what is being limited); 0 turns a limit off.
ASK_LIMITS = [
    (_limit("AFRISEARCH_ASK_PER_MINUTE", 20), 60, "questions per minute"),
    (_limit("AFRISEARCH_ASK_PER_DAY", 500), 86400, "questions per day"),
]
UPLOAD_LIMITS = [
    (_limit("AFRISEARCH_UPLOADS_PER_HOUR", 200), 3600, "uploaded files per hour"),
]

_events: dict[str, deque[float]] = {}
_lock = threading.Lock()


def check(key: str, rules: list[tuple[int, int, str]], cost: int = 1) -> None:
    """Record `cost` events for `key`, or raise 429 if that would break a rule."""
    now = time.monotonic()
    longest = max((window for limit, window, _ in rules if limit), default=0)
    with _lock:
        events = _events.setdefault(key, deque())
        while events and now - events[0] > longest:
            events.popleft()
        for limit, window, what in rules:
            if not limit:
                continue
            recent = [t for t in events if now - t <= window]
            if len(recent) + cost > limit:
                retry = max(1, math.ceil(window - (now - recent[0]))) if recent else window
                wait = f"{retry} seconds" if retry < 120 else f"{math.ceil(retry / 60)} minutes"
                raise HTTPException(
                    status_code=429,
                    detail=f"Limit reached: {limit} {what}. Please try again in {wait}.",
                    headers={"Retry-After": str(retry)},
                )
        events.extend([now] * cost)


def reset() -> None:
    with _lock:
        _events.clear()
