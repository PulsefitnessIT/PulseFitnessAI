"""
Iter 216h173 — Frontend code-splitting smoke test.

Pure-frontend refactor (React.lazy + Suspense on the 5 largest pages
and ~50 admin panels). This module just sanity-checks that the
perf utilities the Master Admin Integration Health panel depends on
remain importable so we don't ship a green diff that silently breaks
the perf telemetry surface.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_perf_modules_still_importable():
    """The utils that back the Master Admin Integration Health panel
    must remain import-safe so the panel never 500s after the lazy-
    loading refactor."""
    from utils import aggregate_cache, safe_paginate, slow_request_log
    assert hasattr(aggregate_cache, 'cache_aggregate')
    assert hasattr(safe_paginate, 'safe_to_list')
    # slow_request_log exposes either get_slow_request_stats or a
    # SlowRequestLog class — either is fine.
    assert hasattr(slow_request_log, 'SlowRequestRing') or hasattr(
        slow_request_log, 'SlowRequestLogMiddleware'
    )
