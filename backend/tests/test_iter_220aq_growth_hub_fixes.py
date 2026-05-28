"""Iter 220aq — Growth Hub deep-links + pipeline scoping + SEO domain.

Three bug fixes pinned:

1. **Growth Hub Open buttons** routed through ``jump(sectionId)``
   where ``sectionId`` was a CRM key (``crm-deals``, ``crm-companies``)
   that didn't exist as a Master Admin section, so the content went
   blank. Fix: redirect those keys to ``/crm?tab=<x>``. UI-only — no
   backend coverage here; smoke-tested manually + the deep-link map
   lives in JS.

2. **Pipeline £ tile aggregated all tenants** — the master-admin
   self-promo Growth Hub was summing every customer's CRM deals
   globally. Confirmed bug: a £50k deal in any tenant bled into the
   ``pipeline_value_gbp`` field. Fix: scope to the master-admin org
   and union both ``crm_deals`` + ``crm2_opportunities``.

3. **SEO Autopilot hallucinated wrong domain** — published article
   in production used ``gymaxis.io`` instead of ``gymaxisai.com``.
   Fix: explicit URL constraint in the prompt + a ``_scrub_brand_domain``
   safety net that rewrites known bad domains to the canonical URL
   on both the article and its distribution snippets.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── SEO domain scrub ──────────────────────────────────────────────


def test_scrub_rewrites_gymaxis_io_to_gymaxisai():
    from routes.marketing.seo_autopilot import _scrub_brand_domain
    assert _scrub_brand_domain("Visit gymaxis.io today!") == "Visit https://gymaxisai.com today!"
    assert _scrub_brand_domain("https://gymaxis.io/demo") == "https://gymaxisai.com/demo"
    assert _scrub_brand_domain("https://www.gymaxis.io/pricing") == "https://gymaxisai.com/pricing"


def test_scrub_handles_other_bad_variants():
    from routes.marketing.seo_autopilot import _scrub_brand_domain
    for bad in ("gym-axis.com", "gymaxis.co.uk", "gymaxis.net", "gymaxis.app", "gymaxis.co"):
        out = _scrub_brand_domain(f"Try {bad} for more")
        assert "gymaxisai.com" in out, f"{bad} not scrubbed: {out}"
        assert bad not in out, f"{bad} still present: {out}"


def test_scrub_preserves_correct_domain():
    from routes.marketing.seo_autopilot import _scrub_brand_domain
    # The canonical URL must NOT be re-rewritten or doubled up.
    assert _scrub_brand_domain("https://gymaxisai.com/demo-request") == "https://gymaxisai.com/demo-request"
    assert _scrub_brand_domain("Read more at gymaxisai.com").count("gymaxisai.com") == 1


def test_scrub_handles_none_and_empty():
    from routes.marketing.seo_autopilot import _scrub_brand_domain
    assert _scrub_brand_domain(None) == ""
    assert _scrub_brand_domain("") == ""


def test_scrub_collapses_double_protocol():
    from routes.marketing.seo_autopilot import _scrub_brand_domain
    # Even if the LLM emits ``https://https://gymaxis.io`` (which
    # happens occasionally) the result must be a single clean URL.
    out = _scrub_brand_domain("Visit https://https://gymaxis.io now")
    assert "https://https://" not in out
    assert "gymaxisai.com" in out


# ── Growth Hub pipeline scoping ───────────────────────────────────


def test_growth_overview_scopes_pipeline_to_master_admin_org():
    """Pin the bug fix: a £50k deal in another tenant must NOT
    contribute to the master-admin Growth Hub pipeline_value_gbp."""
    from routes import master_admin_growth_hub as m

    fdb = MagicMock()
    # Stub out everything the endpoint touches so we can isolate the
    # pipeline branch.
    fdb.organizations.find = MagicMock()
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=[])
    fdb.organizations.find.return_value = cur

    # _safe_count + _sum_value_field both call .count_documents /
    # .find — we capture the queries to assert they include
    # organization_id.
    seen_queries: list[tuple[str, dict]] = []

    async def fake_count(coll, query):
        seen_queries.append(("count", query))
        return 0

    async def fake_sum(coll, query, field="value"):
        seen_queries.append(("sum", query))
        return 0.0

    async def fake_ma_org():
        return "ma-org-1"

    # SEO articles & email events stubs.
    def _empty_cursor(*_a, **_k):
        c = MagicMock()
        c.to_list = AsyncMock(return_value=[])

        async def _aiter():
            if False:
                yield None
        c.__aiter__ = lambda self: _aiter()
        return c

    fdb.seo_articles.find = _empty_cursor
    fdb.seo_autopilot_runs.find_one = AsyncMock(return_value=None)

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_safe_count", fake_count), \
             patch.object(m, "_sum_value_field", fake_sum), \
             patch.object(m, "_master_admin_org_id", fake_ma_org), \
             patch.object(m, "require_master_admin", lambda _u: None):
            return await m.growth_overview(user={"id": "u-1", "is_master_admin": True})

    out = _run(go())
    # Every pipeline-related query must carry organization_id=ma-org-1.
    pipeline_qs = [q for (_op, q) in seen_queries if "stage" in q or any(
        k in q for k in ("$nin", "$in")
    )]
    # At least one must mention master-admin org. (We scope BOTH crm_deals
    # and crm2_opportunities, so multiple queries are expected.)
    org_scoped = [q for q in pipeline_qs if q.get("organization_id") == "ma-org-1"]
    assert len(org_scoped) >= 4, (
        f"Expected ≥4 pipeline queries scoped to master-admin org, "
        f"got {len(org_scoped)} (all queries: {seen_queries})"
    )
    # And the response keys are intact.
    assert "pipeline" in out
    assert "deep_link" in out["pipeline"]
    assert out["pipeline"]["deep_link"] == "crm-deals"


def test_growth_overview_unions_crm_deals_and_crm2_opportunities():
    """Make sure the pipeline count is the union of v1 + v2 collections."""
    from routes import master_admin_growth_hub as m

    fdb = MagicMock()
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=[])
    fdb.organizations.find = MagicMock(return_value=cur)
    fdb.seo_autopilot_runs.find_one = AsyncMock(return_value=None)

    def _empty_cursor(*_a, **_k):
        c = MagicMock()

        async def _aiter():
            if False:
                yield None
        c.__aiter__ = lambda self: _aiter()
        return c
    fdb.seo_articles.find = _empty_cursor

    # Return 3 for crm_deals open count and 5 for crm2_opportunities open count.
    call_log: list[tuple[str, dict]] = []

    async def fake_count(coll, query):
        call_log.append((getattr(coll, "_extract_mock_name", lambda: str(coll))(), query))
        # We tag the mock with its coll name via _mock_name; simpler:
        # rely on argument order — first 2 are open counts.
        if "$nin" in query.get("stage", {}):
            stages = query["stage"]["$nin"]
            if "won" in stages:
                return 3   # crm_deals open
            if "closed_won" in stages:
                return 5   # crm2_opportunities open
        return 0

    async def fake_sum(coll, query, field="value"):
        if "$nin" in query.get("stage", {}):
            stages = query["stage"]["$nin"]
            if "won" in stages:
                return 7_000.0
            if "closed_won" in stages:
                return 43_000.0
        return 0.0

    async def fake_ma_org():
        return "ma-org-1"

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_safe_count", fake_count), \
             patch.object(m, "_sum_value_field", fake_sum), \
             patch.object(m, "_master_admin_org_id", fake_ma_org), \
             patch.object(m, "require_master_admin", lambda _u: None):
            return await m.growth_overview(user={"id": "u-1", "is_master_admin": True})

    out = _run(go())
    assert out["pipeline"]["deals_open"] == 8  # 3 + 5
    assert out["pipeline"]["pipeline_value_gbp"] == 50_000.0  # 7k + 43k


# ── Growth Hub sparkline scoping ──────────────────────────────────


def test_growth_sparklines_scopes_deals_to_master_admin_org():
    from routes import master_admin_growth_hub as m

    fdb = MagicMock()

    # Stub out non-deal collections — return empty buckets.
    async def fake_bucket(coll, *, date_field, query=None, is_iso_string=False):
        return {}

    async def fake_snap(_views):
        return None

    async def fake_series():
        return []

    async def fake_ma_org():
        return "ma-org-1"

    captured: list[dict] = []

    async def capturing_bucket(coll, *, date_field, query=None, is_iso_string=False):
        captured.append(query or {})
        return {}

    def _empty_cursor(*_a, **_k):
        c = MagicMock()

        async def _aiter():
            if False:
                yield None
        c.__aiter__ = lambda self: _aiter()
        return c
    fdb.seo_articles.find = _empty_cursor

    async def go():
        with patch.object(m, "db", fdb), \
             patch.object(m, "_bucket_count_by_day", capturing_bucket), \
             patch.object(m, "_snapshot_blog_views_today", fake_snap), \
             patch.object(m, "_blog_views_series", fake_series), \
             patch.object(m, "_master_admin_org_id", fake_ma_org), \
             patch.object(m, "require_master_admin", lambda _u: None):
            return await m.growth_sparklines(user={"id": "u-1", "is_master_admin": True})

    out = _run(go())
    # We expect at least two of the captured queries to carry
    # organization_id=ma-org-1 (deals v1 + deals v2).
    org_scoped = [q for q in captured if q.get("organization_id") == "ma-org-1"]
    assert len(org_scoped) >= 2, (
        f"Expected ≥2 deal-bucket queries scoped to master-admin org, "
        f"got {len(org_scoped)} (all: {captured})"
    )
    assert "deals_created" in out["series"]
