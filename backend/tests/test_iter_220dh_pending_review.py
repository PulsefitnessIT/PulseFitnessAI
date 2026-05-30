"""Iter 220dh — Master-Admin unified Pending Review queue.

Pins:

  * ``GET /api/master-admin/pending-review/count`` returns total +
    by-kind buckets for ``partner_application``, ``ptw_request``,
    ``parts_request``. Master-admin gate enforced.
  * ``GET /api/master-admin/pending-review`` returns unified rows
    with ``approve_url`` / ``reject_url`` deep-links to the existing
    per-domain endpoints (no duplicated state machines).
  * ``kind`` filter narrows to a single source.
  * Frontend ``PendingReviewPanel`` mounted + sidebar badge wired.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _master_admin():
    return {
        "id": "admin-1", "is_master_admin": True,
        "email": "a@x.test", "full_name": "Admin",
    }


def _regular_user():
    return {"id": "u-1", "is_master_admin": False, "role": "manager"}


def _chain(rows):
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=list(rows))
    return cur


def _fake_db(*, partners=None, ptws=None, parts=None, orgs=None):
    fdb = MagicMock()
    fdb.partner_applications.find = MagicMock(
        return_value=_chain(partners or []),
    )
    fdb.partner_applications.count_documents = AsyncMock(
        return_value=len(partners or []),
    )
    fdb.svc_ptw_requests.find = MagicMock(return_value=_chain(ptws or []))
    fdb.svc_ptw_requests.count_documents = AsyncMock(
        return_value=len(ptws or []),
    )
    fdb.svc_parts_requests.find = MagicMock(return_value=_chain(parts or []))
    fdb.svc_parts_requests.count_documents = AsyncMock(
        return_value=len(parts or []),
    )
    fdb.organizations.find = MagicMock(return_value=_chain(orgs or []))
    return fdb


# ── 1 · Auth gate ────────────────────────────────────────────────


def test_pending_review_requires_master_admin():
    import pytest
    from fastapi import HTTPException

    async def run():
        from routes.master_admin_pending_review import list_pending_review
        return await list_pending_review(user=_regular_user(), kind=None, limit=10)

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 403


def test_count_requires_master_admin():
    import pytest
    from fastapi import HTTPException

    async def run():
        from routes.master_admin_pending_review import pending_review_counts
        return await pending_review_counts(user=_regular_user())

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 403


# ── 2 · Counts ───────────────────────────────────────────────────


def test_count_returns_total_and_by_kind():
    fdb = _fake_db()
    fdb.partner_applications.count_documents = AsyncMock(return_value=5)
    fdb.svc_ptw_requests.count_documents = AsyncMock(return_value=2)
    fdb.svc_parts_requests.count_documents = AsyncMock(return_value=3)

    async def run():
        with patch("routes.master_admin_pending_review.db", fdb):
            from routes.master_admin_pending_review import pending_review_counts
            return await pending_review_counts(user=_master_admin())

    out = _run(run())
    assert out["total"] == 10
    assert out["by_kind"] == {
        "partner_application": 5,
        "ptw_request": 2,
        "parts_request": 3,
    }


def test_count_partner_filter_uses_pending_and_in_review_statuses():
    """Belt-and-braces: pin that we count BOTH ``pending`` and
    ``in_review`` partner applications. A regression dropping
    ``in_review`` would silently leak items past the admin."""
    fdb = _fake_db()
    fdb.partner_applications.count_documents = AsyncMock(return_value=1)
    fdb.svc_ptw_requests.count_documents = AsyncMock(return_value=0)
    fdb.svc_parts_requests.count_documents = AsyncMock(return_value=0)

    async def run():
        with patch("routes.master_admin_pending_review.db", fdb):
            from routes.master_admin_pending_review import pending_review_counts
            await pending_review_counts(user=_master_admin())

    _run(run())
    flt = fdb.partner_applications.count_documents.await_args.args[0]
    assert flt["status"]["$in"] == ["pending", "in_review"]


# ── 3 · List unified ─────────────────────────────────────────────


def test_list_returns_all_three_kinds_unified_and_sorted():
    partners = [{
        "id": "p1", "name": "Acme", "email": "a@x.test", "company": "Acme Co",
        "created_at": "2026-05-30T10:00:00Z", "status": "pending",
    }]
    ptws = [{
        "id": "w1", "case_id": "c1", "case_reference": "GA-100",
        "template_name": "Hot Work", "hazard_category": "hot_work",
        "requested_at": "2026-05-30T11:00:00Z",
        "requested_by_name": "Eng One", "organization_id": "org-1",
    }]
    parts = [{
        "id": "x1", "case_id": "c2", "case_reference": "GA-101",
        "part_sku": "BELT-1", "part_name": "Belt", "qty": 2,
        "urgency": "high",
        "engineer_name": "Eng One",
        "created_at": "2026-05-30T12:00:00Z",
        "organization_id": "org-1",
    }]
    orgs = [{"id": "org-1", "name": "Pulse Fitness"}]
    fdb = _fake_db(partners=partners, ptws=ptws, parts=parts, orgs=orgs)

    async def run():
        with patch("routes.master_admin_pending_review.db", fdb):
            from routes.master_admin_pending_review import list_pending_review
            return await list_pending_review(user=_master_admin(), kind=None, limit=10)

    out = _run(run())
    assert out["total"] == 3
    kinds = [r["kind"] for r in out["items"]]
    assert set(kinds) == {"partner_application", "ptw_request", "parts_request"}
    # Sorted newest-first: parts (12:00) > ptw (11:00) > partner (10:00).
    assert out["items"][0]["id"] == "x1"
    assert out["items"][-1]["id"] == "p1"
    # PTW + parts rows are stamped with the org name.
    ptw_row = next(r for r in out["items"] if r["kind"] == "ptw_request")
    assert ptw_row["organization_name"] == "Pulse Fitness"


def test_list_kind_filter_partners_only():
    partners = [{
        "id": "p1", "name": "Acme", "created_at": "2026-05-30T10:00:00Z",
    }]
    fdb = _fake_db(partners=partners, ptws=[], parts=[])

    async def run():
        with patch("routes.master_admin_pending_review.db", fdb):
            from routes.master_admin_pending_review import list_pending_review
            return await list_pending_review(
                user=_master_admin(), kind="partner_application", limit=10,
            )

    out = _run(run())
    assert all(r["kind"] == "partner_application" for r in out["items"])
    assert len(out["items"]) == 1


def test_row_shape_carries_approve_and_reject_urls():
    partners = [{
        "id": "p1", "name": "Acme", "created_at": "2026-05-30T10:00:00Z",
    }]
    ptws = [{
        "id": "w1", "case_id": "c1", "template_name": "Hot",
        "requested_at": "2026-05-30T11:00:00Z",
    }]
    parts = [{
        "id": "x1", "case_id": "c2", "part_sku": "BELT",
        "qty": 1, "created_at": "2026-05-30T12:00:00Z",
    }]
    fdb = _fake_db(partners=partners, ptws=ptws, parts=parts)

    async def run():
        with patch("routes.master_admin_pending_review.db", fdb):
            from routes.master_admin_pending_review import list_pending_review
            return await list_pending_review(user=_master_admin(), kind=None, limit=10)

    out = _run(run())
    by_id = {r["id"]: r for r in out["items"]}
    # Partner application has both endpoints.
    assert by_id["p1"]["approve_url"].endswith("/p1/approve")
    assert by_id["p1"]["reject_url"].endswith("/p1/reject")
    # PTW has approve (issue) only — no reject path today.
    assert by_id["w1"]["approve_url"].endswith("/w1/issue")
    assert by_id["w1"]["reject_url"] is None
    # Parts request has both.
    assert by_id["x1"]["approve_url"].endswith("/x1/approve")
    assert by_id["x1"]["reject_url"].endswith("/x1/reject")


def test_list_empty_state():
    fdb = _fake_db()

    async def run():
        with patch("routes.master_admin_pending_review.db", fdb):
            from routes.master_admin_pending_review import list_pending_review
            return await list_pending_review(user=_master_admin(), kind=None, limit=10)

    out = _run(run())
    assert out["total"] == 0
    assert out["items"] == []
    assert "partner_application" in out["kinds"]


# ── 4 · Frontend wiring ──────────────────────────────────────────


def test_frontend_panel_mounted_and_routed():
    page = Path("/app/frontend/src/pages/MasterAdminPage.js").read_text()
    panel = Path("/app/frontend/src/pages/MasterAdmin/PendingReviewPanel.js").read_text()
    sidebar = Path("/app/frontend/src/pages/MasterAdmin/AdminSidebar.js").read_text()
    cfg = Path("/app/frontend/src/pages/MasterAdmin/SidebarConfig.js").read_text()

    # Routed.
    assert "PendingReviewPanel" in page
    assert "case 'pending-review':" in page
    # Sub-tab + group mapping.
    assert "'pending-review'" in cfg
    assert "'pending-review':" in cfg
    # Sidebar badge polls the count endpoint and renders.
    assert "/master-admin/pending-review/count" in sidebar
    assert "sidebar-pending-review-badge" in sidebar
    # Panel test IDs.
    for tid in (
        "pending-review-panel", "pending-review-total",
        "pending-review-refresh", "pending-review-filters",
        "pending-review-list", "pending-review-empty",
        "pending-review-reject-modal", "pending-review-reject-reason",
        "pending-review-reject-submit",
    ):
        assert f'data-testid="{tid}"' in panel, f"missing test-id: {tid}"
    # Filter test IDs are template-passed via prop.
    assert "pending-review-filter-all" in panel
    for kind in ("partner_application", "ptw_request", "parts_request"):
        assert f"pending-review-filter-${{k}}" in panel or f"pending-review-filter-{kind}" in panel
