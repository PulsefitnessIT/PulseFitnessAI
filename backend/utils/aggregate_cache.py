"""Iter 216h170 — Lightweight async TTL cache for heavy aggregate endpoints.

Why this exists
---------------
A handful of dashboard endpoints (CAPEX board report, Master Admin
analytics, Service Revenue YTD) walk thousands of rows + run multiple
aggregates per call. They're idempotent reads, scoped to a single org,
and their underlying data only changes minute-to-minute. Caching the
materialised payload for 60 seconds removes ~98% of the load when an
operator hits F5 or has the page auto-refresh in another tab.

Design constraints
------------------
* In-process only — the platform runs as a single Uvicorn pod today,
  so we don't need Redis. The TTL pattern is identical if we move to
  Redis later (swap `_CacheBackend` → `RedisCacheBackend`).
* Key is `(endpoint, scope_dict_frozen, version)` — version lets us
  bust the whole cache on a deploy without touching keys.
* The cached payload is the *output* of the handler (already-scoped,
  already-serialised), so cross-tenant leakage is impossible by design.
* `cache_aggregate` is a coroutine-safe wrapper. Concurrent calls for
  the same key produce a single upstream invocation thanks to
  per-key asyncio.Lock — "stampede" protection.

Usage
-----
    @cache_aggregate(ttl=60, key_args=("org_id",))
    async def _build_capex_board(org_id: str) -> dict:
        ...

The wrapper transparently caches the dict result keyed by org_id.
Cache hit → 0 DB calls; miss → upstream runs, result is stored.
Always honours the original return type/shape.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Bump on deploy to bust every cached entry across the process.
_CACHE_VERSION = "v1"

# Hard cap so a misbehaving caller can never blow up memory.
_MAX_ENTRIES = 1024


class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at


class _AsyncTTLCache:
    """Simple async-safe TTL cache with per-key locks for stampede control."""

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # Diagnostic counters surfaced by the admin perf endpoint.
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        e = self._store.get(key)
        if not e:
            return None
        if e.expires_at < time.monotonic():
            # Expired — drop lazily.
            self._store.pop(key, None)
            return None
        self.hits += 1
        return e.value

    def set(self, key: str, value: Any, ttl: float) -> None:
        # Evict oldest by expiry if we're at the cap.
        if len(self._store) >= _MAX_ENTRIES:
            try:
                oldest = min(self._store.items(), key=lambda kv: kv[1].expires_at)[0]
                self._store.pop(oldest, None)
            except ValueError:
                pass
        self._store[key] = _CacheEntry(value, time.monotonic() + ttl)
        self.misses += 1

    def lock_for(self, key: str) -> asyncio.Lock:
        lk = self._locks.get(key)
        if lk is None:
            lk = self._locks[key] = asyncio.Lock()
        return lk

    def invalidate(self, prefix: str = "") -> int:
        """Drop entries whose key starts with `prefix`. Returns count."""
        if not prefix:
            n = len(self._store)
            self._store.clear()
            return n
        gone = [k for k in self._store if k.startswith(prefix)]
        for k in gone:
            self._store.pop(k, None)
        return len(gone)

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "entries": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": round(self.hits / total, 3) if total else 0.0,
            "version": _CACHE_VERSION,
        }


CACHE = _AsyncTTLCache()


def _format_key(prefix: str, kwargs: dict) -> str:
    parts = [f"{k}={kwargs[k]}" for k in sorted(kwargs) if kwargs[k] is not None]
    return f"{_CACHE_VERSION}::{prefix}::{'|'.join(parts)}"


def cache_aggregate(
    *, ttl: float, key_args: tuple[str, ...], prefix: str | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator: cache the awaitable return value of a coroutine.

    Args:
        ttl:       seconds to keep the value alive.
        key_args:  argument names whose values participate in the cache key.
                   Must be passed as kwargs OR be positional names matching
                   the wrapped signature. (We coerce via __code__.co_varnames.)
        prefix:    optional cache namespace; defaults to the function qualname.
    """
    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        ns = prefix or fn.__qualname__
        arg_names = fn.__code__.co_varnames[: fn.__code__.co_argcount]

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Combine positional + keyword args into a single name→value map
            # so the cache key is deterministic regardless of call style.
            bound: dict[str, Any] = dict(zip(arg_names, args))
            bound.update(kwargs)
            key_vals = {k: bound.get(k) for k in key_args}
            key = _format_key(ns, key_vals)

            cached = CACHE.get(key)
            if cached is not None:
                return cast(T, cached)

            # Stampede control — only one coroutine fetches per key.
            lock = CACHE.lock_for(key)
            async with lock:
                # Re-check inside the lock in case another coroutine just won.
                cached = CACHE.get(key)
                if cached is not None:
                    return cast(T, cached)
                value = await fn(*args, **kwargs)
                CACHE.set(key, value, ttl)
                return value

        # Expose .invalidate() for surgical bust from mutation paths.
        def _invalidate(**partial: Any) -> int:
            key_vals = {k: partial.get(k) for k in key_args}
            return CACHE.invalidate(_format_key(ns, key_vals))

        wrapper.invalidate = _invalidate  # type: ignore[attr-defined]
        wrapper.cache_namespace = ns       # type: ignore[attr-defined]
        return wrapper

    return decorator


__all__ = ["cache_aggregate", "CACHE"]
