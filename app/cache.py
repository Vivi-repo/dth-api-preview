"""
A tiny in-memory, per-process TTL cache.

This is deliberately simple: a dict of key -> (expiry time, value). It is
NOT shared across multiple server processes/workers, and it is wiped on
restart. For this project's scale (a demo API preview) that's the right
tradeoff -- it needs zero extra infrastructure (no Redis, no database) and
is trivial to reason about. A production deployment running multiple
worker processes would want a shared cache (e.g. Redis) instead, so that
all workers see the same cached data and only one of them has to ask
WordPress for it.
"""

import asyncio
import time
from typing import Any, Awaitable, Callable


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        # One lock per cache key, created lazily. Used to make sure that if
        # ten requests arrive at once for the same uncached data, only the
        # first one actually calls WordPress -- the other nine wait for it
        # and then reuse its result. Without this, a cache "miss" moment
        # (e.g. right after the TTL expires) could fire off many duplicate
        # upstream requests at once, which is exactly the kind of bursty
        # load we want to avoid as a considerate API consumer.
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self._store[key] = (time.monotonic() + ttl_seconds, value)

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def get_or_fetch(
        self, key: str, ttl_seconds: float, fetch: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Return the cached value for `key`, or call `fetch()` to produce
        one, cache it, and return it."""
        cached = self.get(key)
        if cached is not None:
            return cached

        async with self._lock_for(key):
            # Someone else may have already filled the cache while we were
            # waiting for the lock -- check again before doing the work.
            cached = self.get(key)
            if cached is not None:
                return cached

            value = await fetch()
            self.set(key, value, ttl_seconds)
            return value
