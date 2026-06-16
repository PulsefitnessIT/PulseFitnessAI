"""Pulse Fitness Master Admin — Unified Pending Review queue (Iter 220dh).

A single inbox for every item that needs Master-Admin action across
the platform. Reads from existing collections and reuses their
already-deployed approve / reject endpoints — no migrations, no
state-machine duplication.

Item kinds surfaced (today):
  * ``partner_application`` — new partner-engineer signups awaiting
    approval (legal-risk: an unverified contractor going live).
  * ``ptw_request``         — engineer-side Permit-to-Work requests
    in the ``requested`` state (Iter 220de).
  * ``parts_request``       — engineer-side parts requests in
    ``pending`` (existing admin queue).

Each row carries:
  * ``id``, ``kind``, ``title``, ``subtitle``, ``created_at``
  * ``link``        — Master-Admin deep link to the detail panel.
  * ``approve_url`` — POST-able URL to approve in-place from the inbox.
  * ``reject_url``  — POST-able URL to reject (where applicable).
  * ``organization_name`` for context.

Endpoints:
  GET /api/master-admin/pending-review        — paginated list.
  GET /api/master-admin/pending-review/count  — counts per kind, for
                                                the sidebar / dashboard badge.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(403, "Master admin required")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────
# Source projections
# ─────────────────────────────────────────────────────────────────
# Each helper returns a list of unified review rows. The shape is
# kept deliberately small so we don't bloat the inbox payload.


def _row(*, id: str, kind: str, title: str, subtitle: str,
        created_at: str, link: str, approve_url: Optional[str],
        reject_url: Optional[str],
        organization_id: str = "", organization_name: str = "") -> dict:
    return {
        "id": id,
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "created_at": created_at,
        "link": link,
        "approve_url": approve_url,
        "reject_url": reject_url,
        "organization_id": organization_id,
        "organization_name": organization_name,
    }


async def _partner_applications(limit: int = 50) -> list[dict]:
    rows = await db.partner_applications.find(
        {"status": {"$in": ["pending", "in_review"]}},
        {
            "_id": 0, "id": 1, "name": 1, "email": 1, "company": 1,
            "created_at": 1, "status": 1, "rate_card_hourly": 1,
        },
    ).sort("created_at", -1).limit(limit).to_list(limit)
    out = []
    for r in rows:
        out.append(_row(
            id=r["id"], kind="partner_application",
            title=f"Partner: {r.get('name') or r.get('email') or 'New applicant'}",
            subtitle=(r.get("company") or r.get("email") or ""),
            created_at=r.get("created_at") or _iso_now(),
            link=f"/admin/partners?application={r['id']}",
            approve_url=f"/api/partners/applications/{r['id']}/approve",
            reject_url=f"/api/partners/applications/{r['id']}/reject",
        ))
    return out


async def _ptw_requests(limit: int = 50) -> list[dict]:
    rows = await db.svc_ptw_requests.find(
        {"status": "requested"},
        {
            "_id": 0, "id": 1, "case_id": 1, "case_reference": 1,
            "template_name": 1, "hazard_category": 1, "requested_at": 1,
            "requested_by_name": 1, "organization_id": 1, "hazards_noted": 1,
        },
    ).sort("requested_at", -1).limit(limit).to_list(limit)
    if not rows:
        return []
    org_ids = {r.get("organization_id") for r in rows if r.get("organization_id")}
    orgs = {
        o["id"]: o.get("name", "")
        for o in await db.organizations.find(
            {"id": {"$in": list(org_ids)}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(50)
    }
    out = []
    for r in rows:
        out.append(_row(
            id=r["id"], kind="ptw_request",
            title=f"PTW: {r.get('template_name') or 'Permit'} · {r.get('case_reference') or r['case_id']}",
            subtitle=(
                f"{r.get('hazard_category', '')} · requested by "
                f"{r.get('requested_by_name', '')}"
            ),
            created_at=r.get("requested_at") or _iso_now(),
            link=f"/svc/case/{r['case_id']}",
            approve_url=f"/api/svc/admin/ptw-requests/{r['id']}/issue",
            reject_url=None,  # PTW has no reject endpoint today; admin cancels via case.
            organization_id=r.get("organization_id", ""),
            organization_name=orgs.get(r.get("organization_id", ""), ""),
        ))
    return out


async def _parts_requests(limit: int = 50) -> list[dict]:
    rows = await db.svc_parts_requests.find(
        {"status": "pending"},
        {
            "_id": 0, "id": 1, "case_id": 1, "case_reference": 1,
            "part_sku": 1, "part_name": 1, "qty": 1, "urgency": 1,
            "engineer_name": 1, "created_at": 1, "organization_id": 1,
        },
    ).sort("created_at", -1).limit(limit).to_list(limit)
    if not rows:
        return []
    org_ids = {r.get("organization_id") for r in rows if r.get("organization_id")}
    orgs = {
        o["id"]: o.get("name", "")
        for o in await db.organizations.find(
            {"id": {"$in": list(org_ids)}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(50)
    }
    out = []
    for r in rows:
        urgency = (r.get("urgency") or "normal").upper()
        out.append(_row(
            id=r["id"], kind="parts_request",
            title=f"Parts: {r.get('qty', 1)} × {r.get('part_sku') or 'SKU'}",
            subtitle=(
                f"{r.get('part_name', '')} · {urgency} · "
                f"case {r.get('case_reference') or r['case_id']}"
            ),
            created_at=r.get("created_at") or _iso_now(),
            link="/admin/parts-requests",
            approve_url=f"/api/admin/parts-requests/{r['id']}/approve",
            reject_url=f"/api/admin/parts-requests/{r['id']}/reject",
            organization_id=r.get("organization_id", ""),
            organization_name=orgs.get(r.get("organization_id", ""), ""),
        ))
    return out


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────


@router.get("/master-admin/pending-review")
async def list_pending_review(
    kind: Optional[str] = Query(
        default=None,
        description=(
            "Filter to a single kind: partner_application | ptw_request | "
            "parts_request. Default: all."
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    _require_master_admin(user)
    rows: list[dict] = []
    if kind in (None, "partner_application"):
        rows.extend(await _partner_applications(limit=limit))
    if kind in (None, "ptw_request"):
        rows.extend(await _ptw_requests(limit=limit))
    if kind in (None, "parts_request"):
        rows.extend(await _parts_requests(limit=limit))
    # Sort by created_at desc, ties broken by kind for stability.
    rows.sort(key=lambda r: (r.get("created_at") or "", r["kind"]), reverse=True)
    return {
        "items": rows[:limit],
        "total": len(rows),
        "kinds": ["partner_application", "ptw_request", "parts_request"],
    }


@router.get("/master-admin/pending-review/count")
async def pending_review_counts(user=Depends(get_current_user)):
    _require_master_admin(user)
    partner = await db.partner_applications.count_documents(
        {"status": {"$in": ["pending", "in_review"]}},
    )
    ptw = await db.svc_ptw_requests.count_documents({"status": "requested"})
    parts = await db.svc_parts_requests.count_documents({"status": "pending"})
    return {
        "total": partner + ptw + parts,
        "by_kind": {
            "partner_application": partner,
            "ptw_request": ptw,
            "parts_request": parts,
        },
    }


__all__ = ["router"]
