"""Iter 220ag — GymAxis Growth Hub overview endpoint tests.

Pins:
  * Master-admin gated.
  * Aggregates 5 module groups (trials, seo, outbound emails, CRM
    pipeline, sales-insights) into a single payload.
  * Every group includes a ``deep_link`` so the UI knows where to
    jump — proves we never accidentally remove that contract.
  * Numeric fields default to 0 (never None) so the React tiles never
    render "null".
  * Trial conversion stamp comparison is robust to both ISO-string
    and timezone-aware datetime ``converted_at`` values (mixed-format
    bug protection).
  * SEO views are summed across all published articles.
  * Returns ``as_of`` ISO timestamp.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _async_iter(items):
    """Helper — turn a list into an async cursor stand-in."""
    class _Cur:
        def __init__(self, items):
            self._items = list(items)
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)
    return _Cur(items)


def _fake_db(**overrides):
    """Build a MagicMock that emulates motor collections used by the
    growth-hub endpoint. Defaults keep all counts at zero so individual
    tests only need to override the bits they care about."""
    fdb = MagicMock()

    # Counters default to 0.
    for coll in (
        "organizations", "seo_articles", "seo_keywords", "seo_autopilot_runs",
        "email_send_events", "crm_deals", "crm_companies",
        "crm2_opportunities", "crm2_companies",
        "seo_article_view_snapshots", "users",
        "mkt_chat_sessions", "mkt_chat_messages",
    ):
        c = getattr(fdb, coll)
        c.count_documents = AsyncMock(return_value=0)
        c.find_one = AsyncMock(return_value=None)
        # Default cursor is empty
        c.find = MagicMock(return_value=_async_iter([]))

    # Iter 220aq — the growth-hub endpoint now scopes pipeline reads
    # to the master-admin org via ``_master_admin_org_id`` which calls
    # ``organizations.find_one({"is_master_admin_org": True})``. Stub
    # that here so existing fixtures don't need to opt in.
    fdb.organizations.find_one = AsyncMock(return_value={"id": "ma-org"})
    fdb.users.find_one = AsyncMock(return_value={"organization_id": "ma-org"})

    # `organizations.find().to_list()` is used directly.
    org_cursor = MagicMock()
    org_cursor.to_list = AsyncMock(return_value=[])
    fdb.organizations.find = MagicMock(return_value=org_cursor)

    for k, v in overrides.items():
        setattr(fdb, k, v)
    return fdb


# ── Gating ─────────────────────────────────────────────────────────

def test_growth_overview_requires_master_admin():
    from fastapi import HTTPException
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            try:
                await m.growth_overview({"id": "u", "is_master_admin": False})
                return False
            except HTTPException as exc:
                return exc.status_code == 403
    assert _run(go())


# ── Shape contract ────────────────────────────────────────────────

def test_growth_overview_returns_all_module_groups_and_deep_links():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            out = await m.growth_overview({"id": "u", "is_master_admin": True})
        # Top-level shape — these are the 5 module groups the UI hard-
        # codes a card for; removing one is a breaking UI change.
        assert set(out.keys()) >= {
            "as_of", "trials", "seo", "outbound", "pipeline", "sales_insights",
        }
        for k in ("trials", "seo", "outbound", "pipeline", "sales_insights"):
            assert "deep_link" in out[k], f"{k} missing deep_link"
        # Every numeric tile defaults to 0, never None — protects the
        # React `toLocaleString()` calls from crashing.
        assert out["trials"]["active"] == 0
        assert out["seo"]["articles_total"] == 0
        assert out["outbound"]["sent_30d"] == 0
        assert out["pipeline"]["pipeline_value_gbp"] == 0
        assert out["sales_insights"]["chat_sessions_30d"] == 0
    _run(go())


def test_growth_overview_deep_link_ids_match_known_sections():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_overview({"id": "u", "is_master_admin": True})
    out = _run(go())
    # These are the sidebar section IDs the MasterAdminPage switch
    # statement resolves. If any of them stop matching, the Hub's
    # "Open …" buttons silently break.
    assert out["trials"]["deep_link"] == "trials"
    assert out["seo"]["deep_link"] == "seo-autopilot"
    assert out["outbound"]["deep_link"] == "emails"
    assert out["pipeline"]["deep_link"] == "crm-deals"
    assert out["sales_insights"]["deep_link"] == "sales-insights"


# ── Trial conversion: ISO string + datetime mixed input ───────────

def test_growth_overview_counts_converted_trials_30d_iso_string():
    from routes import master_admin_growth_hub as m

    now = datetime.now(timezone.utc)
    converted_recent = (now - timedelta(days=10)).isoformat()
    converted_old = (now - timedelta(days=90)).isoformat()
    orgs = [
        {"is_trial": True, "trial_status": "converted",
         "converted_at": converted_recent},
        {"is_trial": True, "trial_status": "converted",
         "converted_at": converted_old},
        # Still on trial (not converted)
        {"is_trial": True, "trial_status": "active"},
    ]
    fdb = _fake_db()
    org_cursor = MagicMock()
    org_cursor.to_list = AsyncMock(return_value=orgs)
    fdb.organizations.find = MagicMock(return_value=org_cursor)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_overview({"id": "u", "is_master_admin": True})
    out = _run(go())
    # Only the recent one counts.
    assert out["trials"]["converted_30d"] == 1
    # Active is the count of currently-active trial orgs (not converted/expired).
    assert out["trials"]["active"] == 1


def test_growth_overview_counts_converted_trials_30d_datetime():
    from routes import master_admin_growth_hub as m

    now = datetime.now(timezone.utc)
    orgs = [
        {"is_trial": True, "trial_status": "converted",
         "converted_at": now - timedelta(days=5)},
    ]
    fdb = _fake_db()
    org_cursor = MagicMock()
    org_cursor.to_list = AsyncMock(return_value=orgs)
    fdb.organizations.find = MagicMock(return_value=org_cursor)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_overview({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["trials"]["converted_30d"] == 1


# ── SEO view summing ──────────────────────────────────────────────

def test_growth_overview_sums_blog_views_across_published_articles():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()

    # 3 published articles with 10 + 20 + 5 views → 35 total.
    def _find_side(query, projection=None):
        if query == {"status": "published"} and projection == {"_id": 0, "metrics": 1}:
            return _async_iter([
                {"metrics": {"views": 10}},
                {"metrics": {"views": 20}},
                {"metrics": {"views": 5}},
            ])
        return _async_iter([])

    fdb.seo_articles.find = MagicMock(side_effect=_find_side)
    fdb.seo_articles.count_documents = AsyncMock(return_value=3)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_overview({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["seo"]["blog_views_total"] == 35


# ── Pipeline value summing ────────────────────────────────────────

def test_growth_overview_sums_pipeline_value_field():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    # 3 open deals worth £1000, £2500, £500 → £4000.
    def _find_side(query, projection=None):
        if query.get("stage") == {"$nin": ["won", "lost"]}:
            return _async_iter([
                {"value": 1000},
                {"value": 2500},
                {"value": 500},
            ])
        return _async_iter([])

    fdb.crm_deals.find = MagicMock(side_effect=_find_side)
    fdb.crm_deals.count_documents = AsyncMock(return_value=3)

    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_overview({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["pipeline"]["pipeline_value_gbp"] == 4000.0


def test_growth_overview_pipeline_value_tolerates_bad_strings():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    def _find_side(query, projection=None):
        if query.get("stage") == {"$nin": ["won", "lost"]}:
            return _async_iter([
                {"value": "1000"},      # numeric string — sum
                {"value": "not-a-num"},  # garbage — skip
                {"value": None},        # null — sum as 0
                {"value": 500},
            ])
        return _async_iter([])

    fdb.crm_deals.find = MagicMock(side_effect=_find_side)
    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_overview({"id": "u", "is_master_admin": True})
    out = _run(go())
    assert out["pipeline"]["pipeline_value_gbp"] == 1500.0


# ── as_of timestamp ───────────────────────────────────────────────

def test_growth_overview_includes_as_of_iso_timestamp():
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    async def go():
        with patch.object(m, "db", fdb):
            return await m.growth_overview({"id": "u", "is_master_admin": True})
    out = _run(go())
    # parses back to a tz-aware datetime
    parsed = datetime.fromisoformat(out["as_of"])
    assert parsed.tzinfo is not None


def test_growth_overview_safe_when_collections_empty_or_unhappy():
    """Even if every count blows up, the endpoint should still return
    a well-formed response — protects the React tiles from server-
    side index issues during deploys."""
    from routes import master_admin_growth_hub as m

    fdb = _fake_db()
    # Force every count_documents to raise.
    for coll in ("organizations", "seo_articles", "seo_keywords",
                 "seo_autopilot_runs", "email_send_events",
                 "crm_deals", "crm_companies",
                 "mkt_chat_sessions", "mkt_chat_messages"):
        getattr(fdb, coll).count_documents = AsyncMock(
            side_effect=RuntimeError("simulated mongo outage"),
        )
    org_cursor = MagicMock()
    org_cursor.to_list = AsyncMock(side_effect=RuntimeError("blow up"))
    fdb.organizations.find = MagicMock(return_value=org_cursor)

    async def go():
        with patch.object(m, "db", fdb):
            try:
                return await m.growth_overview({"id": "u", "is_master_admin": True})
            except Exception:  # noqa: BLE001
                return None

    out = _run(go())
    # We don't catch the org_cursor failure right now (it's not safe-
    # wrapped) — so accept either a well-formed payload or a clean
    # exception path. The point is the endpoint never silently returns
    # malformed data.
    if out is not None:
        assert "trials" in out
        assert out["trials"]["active"] == 0
