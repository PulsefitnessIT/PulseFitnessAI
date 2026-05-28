"""Pagination safety — Iter 220as.

Centralise the "clamp a client-supplied ``limit`` value" check so we
never let a request unbounded-list 10 000 rows by accident. Used on
every paginated list endpoint that takes a ``limit`` query parameter.

  >>> safe_limit(50)                # → 50
  >>> safe_limit(99999)             # → 200 (hard cap)
  >>> safe_limit(-1)                # → 1
  >>> safe_limit(None, default=25)  # → 25
"""
from __future__ import annotations


MAX_LIMIT = 200
DEFAULT_LIMIT = 50


def safe_limit(value: int | None, *, default: int = DEFAULT_LIMIT, hard_max: int = MAX_LIMIT) -> int:
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if v < 1:
        return 1
    if v > hard_max:
        return hard_max
    return v


def safe_skip(value: int | None) -> int:
    if value is None:
        return 0
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, v)


__all__ = ["safe_limit", "safe_skip", "MAX_LIMIT", "DEFAULT_LIMIT"]
