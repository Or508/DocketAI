"""Per-address limits on the routes a stranger can reach: login, the signer portal, intake, verify.

State lives in this process's memory. That is enough for one API process; several processes each
keep their own counts, so a shared limiter (Redis, or the reverse proxy) belongs in front of them.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass

from fastapi import Request

from app.domain.certificate import clean_ip

# The Next.js proxies send the visitor's address in one of these. The API is private behind them,
# so a header here was set by a proxy, never by the browser.
_CLIENT_IP_HEADERS = ("x-client-ip", "x-office-client-ip", "x-portal-client-ip")


def client_ip(request: Request) -> str:
    for name in _CLIENT_IP_HEADERS:
        cleaned = clean_ip(request.headers.get(name))
        if cleaned:
            return cleaned
    return request.client.host if request.client else "unknown"


class SlidingWindow:
    """How many hits each key had within the last `window` seconds."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float) -> float | None:
        """Count one hit. Returns None if allowed, or the seconds until the next hit would be."""
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return max(hits[0] + window - now, 0.0)
            hits.append(now)
            if len(self._hits) > 50_000:
                self._prune(now, window)
            return None

    def _prune(self, now: float, window: float) -> None:
        for key in [key for key, hits in self._hits.items() if not hits or hits[-1] <= now - window]:
            del self._hits[key]

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


@dataclass
class _Failures:
    count: int = 0
    locked_until: float = 0.0
    last: float = 0.0


class LoginThrottle:
    """Wrong logins per (account, address). Locks that pair only, never the whole account."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._pairs: dict[tuple[str, str], _Failures] = {}
        self._lock = threading.Lock()

    def locked(self, email: str, ip: str) -> bool:
        with self._lock:
            entry = self._pairs.get((email, ip))
            return entry is not None and entry.locked_until > self._clock()

    def fail(self, email: str, ip: str, max_failures: int, lock_seconds: float) -> None:
        now = self._clock()
        with self._lock:
            entry = self._pairs.setdefault((email, ip), _Failures())
            # A quiet spell as long as the lock starts the count again.
            if now - entry.last > lock_seconds:
                entry.count = 0
            entry.count += 1
            entry.last = now
            if entry.count >= max_failures:
                entry.locked_until = now + lock_seconds
                entry.count = 0
            if len(self._pairs) > 50_000:
                for key in [key for key, item in self._pairs.items() if now - item.last > lock_seconds]:
                    del self._pairs[key]

    def succeed(self, email: str, ip: str) -> None:
        with self._lock:
            self._pairs.pop((email, ip), None)

    def clear(self) -> None:
        with self._lock:
            self._pairs.clear()


REQUESTS = SlidingWindow()
LOGINS = LoginThrottle()


def _bucket(method: str, path: str) -> str | None:
    if method == "POST" and path == "/auth/login":
        return "login"
    if path == "/portal" or path.startswith(("/portal/", "/intake/", "/verify/")):
        return "public"
    return None


def check_request(request: Request, settings) -> float | None:
    """None if this request may go on, or the seconds the caller should wait."""
    if not settings.rate_limit_enabled:
        return None
    bucket = _bucket(request.method, request.url.path)
    if bucket is None:
        return None
    if bucket == "login":
        limit, window = settings.login_rate_limit, settings.login_rate_window_seconds
    else:
        limit, window = settings.public_rate_limit, settings.public_rate_window_seconds
    wait = REQUESTS.hit(f"{bucket}:{client_ip(request)}", limit, window)
    return None if wait is None else float(max(1, math.ceil(wait)))


def reset() -> None:
    REQUESTS.clear()
    LOGINS.clear()
