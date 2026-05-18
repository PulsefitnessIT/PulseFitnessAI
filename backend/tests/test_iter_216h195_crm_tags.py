"""Iter 216h195 — Wave 2 dropdown audit coverage.

Tests the new ``GET /api/crm/v2/tags`` endpoint that surfaces an
aggregated tag vocabulary for the workflow builder + autocomplete.

The endpoint reads tags off ``crm_contacts``, ``crm_companies``, and
``crm_deals`` and ranks by frequency. Smoke-tests:

  1. Returns aggregated counts (most-used first).
  2. Empty trims out blank / whitespace tags.
  3. Same name across collections is counted once per occurrence.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_async_iter(items):
    """Return an async generator that yields `items` in order."""
    async def _gen(*_args, **_kwargs):
        for it in items:
            yield it

    class _Cursor:
        def find(self, *_a, **_k):
            return _Iter(items)

    class _Iter:
        def __init__(self, items):
            self._items = items

        def __aiter__(self):
            self._i = 0
            return self

        async def __anext__(self):
            if self._i >= len(self._items):
                raise StopAsyncIteration
            v = self._items[self._i]
            self._i += 1
            return v

        def limit(self, _n):
            return self

    return _Cursor()


def test_tags_endpoint_aggregates_by_frequency() -> None:
    from routes import crm_v2 as cv

    user = {"id": "u1", "organization_id": "org-1"}

    async def fake_visibility(_u, _kind):
        return {"organization_id": "org-1"}

    # Build collection stubs that yield tags off each doc.
    contacts = [{"tags": ["vip", "newsletter"]}, {"tags": ["vip"]}]
    companies = [{"tags": ["enterprise", "VIP"]}, {"tags": []}]
    deals = [{"tags": ["newsletter"]}, {"tags": None}]

    fake_db = MagicMock()
    fake_db.crm_contacts = _make_async_iter(contacts)
    fake_db.crm_companies = _make_async_iter(companies)
    fake_db.crm_deals = _make_async_iter(deals)

    with patch.object(cv, "compute_visibility", side_effect=fake_visibility), \
         patch.object(cv, "db", fake_db):
        result = _run(cv.list_crm_tags(user=user))

    tags = {t["name"]: t["count"] for t in result["tags"]}
    assert tags.get("vip") == 2          # exact case preserved
    assert tags.get("VIP") == 1          # case-sensitive (operators can fix later)
    assert tags.get("newsletter") == 2
    assert tags.get("enterprise") == 1
    # Most-used first
    assert result["tags"][0]["count"] >= result["tags"][-1]["count"]
    assert result["total"] == len(tags)


def test_tags_endpoint_skips_blanks_and_none() -> None:
    from routes import crm_v2 as cv

    user = {"id": "u1", "organization_id": "org-1"}

    async def fake_visibility(_u, _kind):
        return {"organization_id": "org-1"}

    contacts = [{"tags": ["", "  ", None, "real_tag"]}, {"tags": None}]
    companies = []
    deals = []

    fake_db = MagicMock()
    fake_db.crm_contacts = _make_async_iter(contacts)
    fake_db.crm_companies = _make_async_iter(companies)
    fake_db.crm_deals = _make_async_iter(deals)

    with patch.object(cv, "compute_visibility", side_effect=fake_visibility), \
         patch.object(cv, "db", fake_db):
        result = _run(cv.list_crm_tags(user=user))

    tags = [t["name"] for t in result["tags"]]
    assert tags == ["real_tag"]


def test_tags_endpoint_handles_empty_collections() -> None:
    from routes import crm_v2 as cv

    user = {"id": "u1", "organization_id": "org-1"}

    async def fake_visibility(_u, _kind):
        return {"organization_id": "org-1"}

    fake_db = MagicMock()
    fake_db.crm_contacts = _make_async_iter([])
    fake_db.crm_companies = _make_async_iter([])
    fake_db.crm_deals = _make_async_iter([])

    with patch.object(cv, "compute_visibility", side_effect=fake_visibility), \
         patch.object(cv, "db", fake_db):
        result = _run(cv.list_crm_tags(user=user))

    assert result["total"] == 0
    assert result["tags"] == []
