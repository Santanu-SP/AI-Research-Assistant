"""In-process sliding-window rate limiter.

This keeps abuse in check without adding Redis to local development. The
counters live in each worker process, so with N API processes the effective
limit is N times higher; swap ``RateLimiter`` for a shared store before
scaling out horizontally.
"""

from collections import deque
from threading import Lock
from time import monotonic

from fastapi import Request

from app.core.errors import AppError


class RateLimiter:
    def __init__(self, *, max_keys: int = 50_000) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._max_keys = max_keys

    def hit(self, key: str, *, limit: int, window_seconds: float) -> float | None:
        """Record one hit. Return seconds to wait when over the limit."""

        now = monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self._max_keys:
                    self._evict(now)
                hits = deque()
                self._hits[key] = hits
            while hits and now - hits[0] >= window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return max(0.0, window_seconds - (now - hits[0]))
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _evict(self, now: float, horizon: float = 3600.0) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or now - hits[-1] > horizon]
        for key in stale:
            del self._hits[key]
        if len(self._hits) >= self._max_keys:
            # Still full: drop the oldest half rather than grow without bound.
            for key in list(self._hits)[: self._max_keys // 2]:
                del self._hits[key]


def client_ip(request: Request) -> str:
    settings = request.app.state.settings
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(
    request: Request,
    bucket: str,
    *,
    key: str,
    limit: int,
    window_seconds: float,
) -> None:
    settings = request.app.state.settings
    if not settings.rate_limit_enabled:
        return
    limiter: RateLimiter = request.app.state.rate_limiter
    retry_after = limiter.hit(f"{bucket}:{key}", limit=limit, window_seconds=window_seconds)
    if retry_after is not None:
        raise AppError(
            "Too many requests. Please wait and try again.",
            status_code=429,
            code="rate_limited",
            headers={"Retry-After": str(max(1, int(retry_after + 0.999)))},
        )
