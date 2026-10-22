import threading
import time
from collections import defaultdict, deque
from typing import Deque, DefaultDict


class SimpleRateLimiter:
    """Very small in-memory token-bucket style limiter for public routes.

    This intentionally avoids extra dependencies while providing a real guardrail
    for abusive traffic on the public API surface.
    """

    def __init__(self, *, limit: int, window_seconds: int):
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self._buckets: DefaultDict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.limit:
                return False

            bucket.append(now)
            return True


_LIMITS = {
    "chat": SimpleRateLimiter(limit=30, window_seconds=60),
    "ws": SimpleRateLimiter(limit=10, window_seconds=60),
    "sessions": SimpleRateLimiter(limit=20, window_seconds=60),
    "voice": SimpleRateLimiter(limit=10, window_seconds=60),
    "whatsapp": SimpleRateLimiter(limit=5, window_seconds=60),
    "default": SimpleRateLimiter(limit=60, window_seconds=60),
}


def _client_key(request_or_host: object) -> str:
    if hasattr(request_or_host, "headers"):
        forwarded = (request_or_host.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            return f"ip:{forwarded}"
        client = getattr(request_or_host.client, "host", None)
        return f"ip:{client or 'unknown'}"
    return f"ip:{str(request_or_host or 'unknown')}"


def check_rate_limit(path: str, client: object) -> bool:
    key = _client_key(client)
    route = "default"
    normalized = (path or "").lower()
    if "/ws/" in normalized:
        route = "ws"
    elif "/api/chat" in normalized:
        route = "chat"
    elif "/api/voice" in normalized:
        route = "voice"
    elif "/api/sessions" in normalized or "/api/ledger" in normalized:
        route = "sessions"
    elif "/api/whatsapp" in normalized:
        route = "whatsapp"
    return _LIMITS[route].allow(key)
