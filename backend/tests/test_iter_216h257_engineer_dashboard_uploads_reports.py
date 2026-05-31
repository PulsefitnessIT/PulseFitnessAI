"""Iter 216h257 — Engineer dashboard polish + photo upload fix + Analytics + report actions.

User feedback (production, Feb 20, 2026):
1. "Remove warning this month from dashboard" → Earnings hero card removed.
2. "Add an analytics button that will provide filtered stats" → new
   /api/svc/engineer/analytics endpoint + /svc/engineer/analytics page.
3. "Each stat button is interactive and goes to the page associated
   with the stat" → kpi-awaiting-customer + kpi-invoiced tiles now
   navigate to their respective lists.
4. "Adding photos/videos does not work" → MIME_VIDEOS wasn't in the
   global allow-list. /api/files/upload now uses a per-category
   allow-list that covers `service-media` (images + videos), and the
   engineer photo button now surfaces the real error detail instead of
   a generic "Upload failed".
5. "Send report directly from the complete screen or download the
   pdf" → ReportActionsCard on the Complete tab wires the existing
   /service-report.pdf + /service-report/email endpoints.
6. "Ability to convert a quote to an invoice" → endpoint already
   existed (`POST /api/svc/engineer/invoices/from-quote/{id}` accepts
   both sent + accepted). Surfaced the button for `sent` quotes too
   and renamed it "Convert to invoice".

(Stripe Connect not working is logged separately — needs the actual
error message from prod, the code path looks correct.)
"""
from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── 1. Earnings hero card removed ──────────────────────────────────

def test_earnings_hero_card_removed():
    import re
    src = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerHomeV2.js"
    ).read_text()
    # Strip JSX/JS comments + JSDoc so the docstring header doesn't trip us.
    stripped = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    stripped = re.sub(r"//.*", "", stripped)
    stripped = re.sub(r"\{/\*.*?\*/\}", "", stripped, flags=re.DOTALL)
    assert 'data-testid="engineer-home-earnings-card"' not in stripped
    assert "Earnings this month" not in stripped


# ─── 2. Analytics endpoint + page wired ─────────────────────────────

def test_analytics_endpoint_returns_kpi_breakdown():
    from routes.svc import engineer_quotes as eq

    fake = MagicMock()
    # svc_cases aggregate → counts per status
    case_chain = MagicMock()
    case_chain.to_list = AsyncMock(return_value=[
        {"_id": "scheduled", "n": 3},
        {"_id": "closed", "n": 5},
    ])
    fake.svc_cases = MagicMock()
    fake.svc_cases.aggregate = MagicMock(return_value=case_chain)
    fake.svc_cases.count_documents = AsyncMock(return_value=5)

    quote_chain = MagicMock()
    quote_chain.to_list = AsyncMock(return_value=[
        {"_id": "accepted", "n": 2, "total": 800},
        {"_id": "invoiced", "n": 1, "total": 300},
        {"_id": "sent",     "n": 4, "total": 600},
    ])
    accepted_chain = MagicMock()
    accepted_chain.to_list = AsyncMock(return_value=[{"_id": None, "avg": 400}])

    def _agg(_):
        # Order: case status agg, quote status agg, accepted-avg agg.
        return case_chain if _agg.call_n == 0 else (
            quote_chain if _agg.call_n == 1 else accepted_chain
        )

    fake.svc_engineer_quotes = MagicMock()
    call_order = {"i": 0}

    def _quote_agg(_):
        call_order["i"] += 1
        return quote_chain if call_order["i"] == 1 else accepted_chain

    fake.svc_engineer_quotes.aggregate = MagicMock(side_effect=_quote_agg)

    user = {"id": "u1", "organization_id": "org1", "role": "engineer", "email": "e@x"}

    with patch.object(eq, "db", fake), patch.object(eq, "_of", return_value={"organization_id": "org1"}):
        out = _run(eq.engineer_analytics(range="30d", user=user))

    assert out["range"] == "30d"
    assert out["cases"]["total"] == 8
    assert out["cases"]["completed"] == 5
    assert out["cases"]["by_status"]["closed"] == 5
    assert out["quotes"]["total"] == 7
    # earnings = 800 (accepted) + 300 (invoiced) = 1100
    assert out["quotes"]["earnings"] == 1100
    assert out["quotes"]["average_value"] == 400


def test_analytics_endpoint_rejects_bad_range():
    from routes.svc import engineer_quotes as eq
    from fastapi import HTTPException

    user = {"id": "u1", "organization_id": "org1"}
    with patch.object(eq, "_of", return_value={"organization_id": "org1"}):
        try:
            _run(eq.engineer_analytics(range="not-a-range", user=user))
            raise AssertionError("expected 400")
        except HTTPException as e:
            assert e.status_code == 400


def test_analytics_page_exists_and_route_wired():
    page = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerAnalyticsPage.js"
    ).read_text()
    assert "function EngineerAnalyticsPage" in page
    assert "/svc/engineer/analytics" in page
    for tid in (
        "analytics-range", "analytics-kpi-jobs",
        "analytics-kpi-completed", "analytics-kpi-earnings",
        "analytics-kpi-avg",
    ):
        # KPI component passes `testid` prop down (rendered as data-testid
        # at runtime). Range chips use data-testid directly. Either spelling
        # is valid in source.
        assert (
            f'testid="{tid}"' in page or f'data-testid="{tid}"' in page
        ), f"missing test id {tid}"

    routes = pathlib.Path("/app/frontend/src/routes/AppRoutes.js").read_text()
    assert "/svc/engineer/analytics" in routes
    assert "EngineerAnalyticsPage" in routes


# ─── 3. Stat tiles clickable ────────────────────────────────────────

def test_kpi_tiles_have_onclick_navigation():
    src = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerHomeV2.js"
    ).read_text()
    # Awaiting customer + invoiced now navigate.
    assert "/svc/engineer/quotes?status=sent" in src
    assert "/svc/engineer/invoices" in src


def test_dashboard_has_analytics_quickaction():
    src = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerHomeV2.js"
    ).read_text()
    assert 'testid="qa-analytics"' in src
    assert "/svc/engineer/analytics" in src


# ─── 4. Photo / video upload fix ────────────────────────────────────

def test_files_upload_allows_video_mime_for_service_media():
    """Ensure the per-category allow-list now exists and covers the
    engineer's `service-media` category with both images + videos."""
    src = pathlib.Path("/app/backend/routes/files.py").read_text()
    assert "MIME_VIDEOS" in src
    # Per-category branching present.
    assert 'category in ("service-media", "case-media", "engineer-media")' in src
    assert "MIME_IMAGES | MIME_VIDEOS" in src


def test_engineer_uploader_uses_service_media_and_surfaces_error():
    src = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerJobDetailV2.js"
    ).read_text()
    # Iter 220e9 — uploads now go through `chunkedUpload`, which
    # routes the same `service-media` category (string param instead
    # of querystring) and falls back to the legacy single-shot
    # endpoint for small files.
    assert "category: 'service-media'" in src
    assert "chunkedUpload" in src
    # No more silent generic "Upload failed".
    assert "err?.response?.data?.detail" in src


# ─── 5. Report actions on Complete tab ──────────────────────────────

def test_complete_tab_has_report_actions():
    src = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerJobDetailV2.js"
    ).read_text()
    assert "function ReportActionsCard" in src
    assert "/service-report.pdf" in src
    assert "/service-report/email" in src
    for tid in ("complete-report-card", "complete-report-download",
                "complete-report-email", "complete-report-email-to",
                "complete-report-note"):
        assert f'data-testid="{tid}"' in src


# ─── 6. Quote → invoice button visible for sent quotes ──────────────

def test_quote_builder_shows_convert_to_invoice_for_sent_and_accepted():
    src = pathlib.Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerQuoteBuilder.js"
    ).read_text()
    assert "form.status === 'accepted' || form.status === 'sent'" in src
    # Renamed label.
    assert "Convert to invoice" in src
