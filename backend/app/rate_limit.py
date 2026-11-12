"""Rate limiting: cap how many requests one IP address can make in a time window.

Why bother once there is a login? Login is exactly what needs it: without a limit, a script
could try thousands of passwords a minute. Other limits stop one client from using this
server to hammer websites ("Check now") or spam your Discord ("Send test alert").

How the sliding window works: for each IP we keep the times of its recent requests. To
decide on a new request, we forget the ones older than the window and count the rest.

Limits of this simple version:
- The counts live in this process's memory, so a restart clears them.
- Behind a reverse proxy every request appears to come from the proxy's IP. We deliberately
  don't trust the X-Forwarded-For header, because any client can fake it.
"""

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

# Past this many tracked IPs we sweep out idle ones, so memory can't grow without limit.
_MAX_TRACKED_KEYS = 10_000

# Every limiter ever created, so the tests can start each one from zero.
_ALL_LIMITERS: list["SlidingWindowLimiter"] = []


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        # Plain `def` endpoints run in worker threads, so two can arrive here at once.
        self._lock = threading.Lock()
        _ALL_LIMITERS.append(self)

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()
        return hits

    def check(self, key: str) -> None:
        """Raise 429 if `key` has used up its limit. Doesn't count this request."""
        now = time.monotonic()
        with self._lock:
            hits = self._recent(key, now)
            if len(hits) >= self.limit:
                retry_after = math.ceil(hits[0] + self.window_seconds - now)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

    def record(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) >= _MAX_TRACKED_KEYS:
                self._sweep(now)
            self._hits[key].append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _sweep(self, now: float) -> None:
        for key in list(self._hits):
            if not self._recent(key, now):
                del self._hits[key]


def reset_all_limiters() -> None:
    """Forget every count. Used by the tests, so one test's requests can't block the next."""
    for limiter in _ALL_LIMITERS:
        with limiter._lock:
            limiter._hits.clear()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class RateLimit:
    """A FastAPI dependency: `Depends(RateLimit(10, 60))` allows 10 requests a minute."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limiter = SlidingWindowLimiter(limit, window_seconds)

    def __call__(self, request: Request) -> None:
        key = client_ip(request)
        self.limiter.check(key)
        self.limiter.record(key)
