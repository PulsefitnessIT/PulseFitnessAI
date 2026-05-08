"""
GymAxis · Integrations Admin — health & outbox status.

Iter 215dy (Workstream D of revised Phase 8).

Read-only endpoints powering the `/admin/integrations` console. Returns
live counters for both the Sicon and Sage 200 outbox collections plus
config status (enabled / disabled / last test timestamp). Designed so
the UI lights up the moment credentials are configured — no backend
changes needed.

Endpoints (all under /api/integrations):
  GET  /health                     → { sicon, sage } summary
  GET  /sicon/outbox               → paginated outbox rows (admin only)
  GET  /sage/outbox                → paginated outbox rows (admin only)
  GET  /mapping/sections           → parsed mapping-doc TOC for the lineage UI

Auth: master_admin or super_admin only (uses the same auth pattern as
other admin-tier routes — relies on require_master_admin from utils).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user
from utils.sicon_outbox_worker import tick as sicon_tick, requeue_failed as sicon_requeue
from utils.sage_outbox_worker import tick as sage_tick, requeue_failed as sage_requeue

router = APIRouter(prefix="/integrations/admin", tags=["Integrations Admin"])

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

MAPPING_DOC = Path("/app/memory/INTEGRATION_FIELD_MAPPING.md")
LEGACY_DOC = Path("/app/memory/SVC_FIELD_MAPPING.md")

SICON_OUTBOX = "svc_sicon_outbox"
SAGE_INVOICE_OUTBOX = "svc_sage_invoice_outbox"
SAGE_PO_OUTBOX = "svc_sage_po_outbox"
SAGE_QUOTE_OUTBOX = "svc_sage_quote_outbox"
SICON_INBOX = "svc_sicon_inbox"


def _require_admin(user: dict[str, Any]) -> None:
    """Master/super/owner admin OR explicit is_master_admin flag."""
    if not user:
        raise HTTPException(status_code=403, detail="Master admin only")
    if user.get("is_master_admin") or user.get("account_type") == "gymaxis_admin":
        return
    role = user.get("role") or ""
    if role in {"master_admin", "super_admin", "owner_admin", "owner"}:
        return
    raise HTTPException(status_code=403, detail="Master admin only")


async def _outbox_summary(coll_name: str, success_status: list[str], failure_status: list[str]) -> dict[str, Any]:
    """Generic counters across an outbox collection."""
    coll = db[coll_name]
    if not (await db.list_collection_names()).__contains__(coll_name):
        return {
            "exists": False,
            "pending": 0, "in_flight": 0, "succeeded_24h": 0, "failed_24h": 0, "dead_letter": 0,
            "last_success_at": None, "last_failure_at": None,
            "last_success_per_kind": {},
        }
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    async def _count(q: dict[str, Any]) -> int:
        return await coll.count_documents(q)

    pending = await _count({"status": "pending"})
    in_flight = await _count({"status": "in_flight"})
    dead_letter = await _count({"status": "dead_letter"})
    succeeded_24h = await _count({"status": {"$in": success_status}, "updated_at": {"$gte": cutoff_24h}})
    failed_24h = await _count({"status": {"$in": failure_status}, "updated_at": {"$gte": cutoff_24h}})

    last_success_doc = await coll.find_one({"status": {"$in": success_status}}, sort=[("updated_at", -1)], projection={"_id": 0, "updated_at": 1})
    last_failure_doc = await coll.find_one({"status": {"$in": failure_status}}, sort=[("updated_at", -1)], projection={"_id": 0, "updated_at": 1, "error": 1})

    # last success per kind
    pipeline = [
        {"$match": {"status": {"$in": success_status}}},
        {"$sort": {"updated_at": -1}},
        {"$group": {"_id": "$kind", "at": {"$first": "$updated_at"}}},
    ]
    per_kind: dict[str, str] = {}
    async for row in coll.aggregate(pipeline):
        if row.get("_id"):
            at = row.get("at")
            per_kind[row["_id"]] = at.isoformat() if isinstance(at, datetime) else at

    return {
        "exists": True,
        "pending": pending,
        "in_flight": in_flight,
        "dead_letter": dead_letter,
        "succeeded_24h": succeeded_24h,
        "failed_24h": failed_24h,
        "last_success_at": (last_success_doc or {}).get("updated_at").isoformat() if last_success_doc and last_success_doc.get("updated_at") else None,
        "last_failure_at": (last_failure_doc or {}).get("updated_at").isoformat() if last_failure_doc and last_failure_doc.get("updated_at") else None,
        "last_failure_error": (last_failure_doc or {}).get("error"),
        "last_success_per_kind": per_kind,
    }


async def _config_summary_sicon() -> dict[str, Any]:
    """Look at the per-org sicon_config collection + env fallback."""
    cfg_doc = await db["sicon_config"].find_one({}, sort=[("updated_at", -1)], projection={"_id": 0, "username_enc": 0, "password_enc": 0})
    env_present = bool(os.environ.get("SICON_BASE_URL") and os.environ.get("SICON_USERNAME"))
    return {
        "configured": bool(cfg_doc and cfg_doc.get("base_url") and cfg_doc.get("enabled")),
        "env_fallback_present": env_present,
        "last_test_at": (cfg_doc or {}).get("last_test_at"),
        "last_test_ok": (cfg_doc or {}).get("last_test_ok"),
        "tenant_count": await db["sicon_config"].count_documents({"enabled": True}),
        "base_url": (cfg_doc or {}).get("base_url"),
    }


async def _config_summary_sage() -> dict[str, Any]:
    cfg_doc = await db["crm_integrations"].find_one({"type": "sage200"}, projection={"_id": 0, "client_secret": 0, "access_token": 0, "refresh_token": 0})
    env_present = bool(os.environ.get("SAGE_CLIENT_ID") and os.environ.get("SAGE_CLIENT_SECRET"))
    # Live readiness: existing CRM Sage flow stores access_token rather than an
    # explicit `enabled` flag, so we fall back to "has access_token + client_id"
    # as the live signal for legacy configs.
    has_access_token = await db["crm_integrations"].count_documents({"type": "sage200", "access_token": {"$exists": True, "$ne": ""}})
    configured = bool(cfg_doc and cfg_doc.get("client_id") and (cfg_doc.get("enabled") or has_access_token))
    return {
        "configured": configured,
        "env_fallback_present": env_present,
        "last_test_at": (cfg_doc or {}).get("last_test_at") or (cfg_doc or {}).get("last_sync"),
        "last_test_ok": (cfg_doc or {}).get("last_test_ok"),
        "tenant_count": await db["crm_integrations"].count_documents({"type": "sage200", "$or": [{"enabled": True}, {"access_token": {"$exists": True, "$ne": ""}}]}),
        "tier": (cfg_doc or {}).get("edition") or (cfg_doc or {}).get("tier"),
    }


async def _inbox_summary() -> dict[str, Any]:
    coll_names = await db.list_collection_names()
    if SICON_INBOX not in coll_names:
        return {"exists": False, "pending_merge": 0, "last_poll_at": None}
    coll = db[SICON_INBOX]
    pending = await coll.count_documents({"merged": {"$ne": True}})
    last = await coll.find_one({}, sort=[("polled_at", -1)], projection={"_id": 0, "polled_at": 1})
    last_at = (last or {}).get("polled_at")
    return {
        "exists": True,
        "pending_merge": pending,
        "last_poll_at": last_at.isoformat() if isinstance(last_at, datetime) else last_at,
    }


# ─────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────


@router.get("/health")
async def health(user: dict = Depends(get_current_user)):
    """One-shot snapshot powering the /admin/integrations dashboard."""
    _require_admin(user)
    sicon_cfg = await _config_summary_sicon()
    sage_cfg = await _config_summary_sage()
    sicon_outbox = await _outbox_summary(
        SICON_OUTBOX,
        success_status=["succeeded"],
        failure_status=["failed", "dead_letter"],
    )
    sage_invoice_outbox = await _outbox_summary(
        SAGE_INVOICE_OUTBOX,
        success_status=["posted", "submitted"],
        failure_status=["failed"],
    )
    sage_po_outbox = await _outbox_summary(
        SAGE_PO_OUTBOX,
        success_status=["posted", "submitted"],
        failure_status=["failed"],
    )
    sage_quote_outbox = await _outbox_summary(
        SAGE_QUOTE_OUTBOX,
        success_status=["posted", "submitted"],
        failure_status=["failed"],
    )
    # Combine for the top-line Sage card.
    sage_outbox = {
        "exists": sage_invoice_outbox["exists"] or sage_po_outbox["exists"] or sage_quote_outbox["exists"],
        "pending": sage_invoice_outbox["pending"] + sage_po_outbox["pending"] + sage_quote_outbox["pending"],
        "in_flight": sage_invoice_outbox["in_flight"] + sage_po_outbox["in_flight"] + sage_quote_outbox["in_flight"],
        "dead_letter": sage_invoice_outbox["dead_letter"] + sage_po_outbox["dead_letter"] + sage_quote_outbox["dead_letter"],
        "succeeded_24h": sage_invoice_outbox["succeeded_24h"] + sage_po_outbox["succeeded_24h"] + sage_quote_outbox["succeeded_24h"],
        "failed_24h": sage_invoice_outbox["failed_24h"] + sage_po_outbox["failed_24h"] + sage_quote_outbox["failed_24h"],
        "last_success_at": max(filter(None, [sage_invoice_outbox["last_success_at"], sage_po_outbox["last_success_at"], sage_quote_outbox["last_success_at"]]), default=None),
        "last_failure_at": max(filter(None, [sage_invoice_outbox["last_failure_at"], sage_po_outbox["last_failure_at"], sage_quote_outbox["last_failure_at"]]), default=None),
        "last_failure_error": (sage_invoice_outbox.get("last_failure_error")
                                or sage_po_outbox.get("last_failure_error")
                                or sage_quote_outbox.get("last_failure_error")),
        "last_success_per_kind": {
            **{f"invoice/{k}": v for k, v in sage_invoice_outbox["last_success_per_kind"].items()},
            **{f"po/{k}": v for k, v in sage_po_outbox["last_success_per_kind"].items()},
            **{f"quote/{k}": v for k, v in sage_quote_outbox["last_success_per_kind"].items()},
        },
        "by_outbox": {
            "invoice": sage_invoice_outbox,
            "po": sage_po_outbox,
            "quote": sage_quote_outbox,
        },
    }
    sicon_inbox = await _inbox_summary()
    now = datetime.now(timezone.utc)
    return {
        "generated_at": now.isoformat(),
        "sicon": {
            "config": sicon_cfg,
            "outbox": sicon_outbox,
            "inbox": sicon_inbox,
            "live": bool(sicon_cfg["configured"] or sicon_cfg["env_fallback_present"]),
        },
        "sage": {
            "config": sage_cfg,
            "outbox": sage_outbox,
            "live": bool(sage_cfg["configured"] or sage_cfg["env_fallback_present"]),
        },
    }


@router.get("/sicon/outbox")
async def sicon_outbox_rows(
    user: dict = Depends(get_current_user),
    status: str = Query("", description="filter by status (pending|in_flight|succeeded|failed|dead_letter)"),
    kind: str = Query(""),
    limit: int = Query(50, ge=1, le=500),
):
    _require_admin(user)
    coll_names = await db.list_collection_names()
    if SICON_OUTBOX not in coll_names:
        return {"rows": [], "count": 0, "exists": False}
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    if kind:
        q["kind"] = kind
    cursor = db[SICON_OUTBOX].find(q, projection={"_id": 0}).sort("updated_at", -1).limit(limit)
    rows: list[dict[str, Any]] = []
    async for r in cursor:
        # ISO-format datetimes for JSON
        for k in ("created_at", "updated_at"):
            v = r.get(k)
            if isinstance(v, datetime):
                r[k] = v.isoformat()
        rows.append(r)
    return {"rows": rows, "count": len(rows), "exists": True}


@router.get("/sage/outbox")
async def sage_outbox_rows(
    user: dict = Depends(get_current_user),
    status: str = Query(""),
    kind: str = Query(""),
    limit: int = Query(50, ge=1, le=500),
):
    _require_admin(user)
    coll_names = await db.list_collection_names()
    if (SAGE_INVOICE_OUTBOX not in coll_names
            and SAGE_PO_OUTBOX not in coll_names
            and SAGE_QUOTE_OUTBOX not in coll_names):
        return {"rows": [], "count": 0, "exists": False}
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    if kind:
        q["kind"] = kind
    rows: list[dict[str, Any]] = []
    for coll_name, source in (
        (SAGE_INVOICE_OUTBOX, "invoice"),
        (SAGE_PO_OUTBOX, "po"),
        (SAGE_QUOTE_OUTBOX, "quote"),
    ):
        if coll_name not in coll_names:
            continue
        cursor = db[coll_name].find(q, projection={"_id": 0}).sort("updated_at", -1).limit(limit)
        async for r in cursor:
            for k in ("created_at", "updated_at"):
                v = r.get(k)
                if isinstance(v, datetime):
                    r[k] = v.isoformat()
            r["_outbox_source"] = source
            rows.append(r)
    rows.sort(key=lambda r: r.get("updated_at") or r.get("created_at") or "", reverse=True)
    rows = rows[:limit]
    return {"rows": rows, "count": len(rows), "exists": True}


# ─────────────────────────────────────────────────────────────────
# Mapping doc TOC — for the lineage viewer
# ─────────────────────────────────────────────────────────────────

_MAPPING_CACHE: dict[str, Any] | None = None


def _parse_mapping_toc() -> dict[str, Any]:
    """Cheap parse of `## N. Title` headers from the master + legacy docs.

    Returns:
      {
        "master": [{"section": 1, "title": "...", "anchor": "..."}, ...],
        "legacy": [...],
        "modules": [{"name": "...", "sicon_summary": "...", "sage_summary": "...", "section_ref": "..."}, ...]
      }
    """
    global _MAPPING_CACHE
    if _MAPPING_CACHE is not None:
        return _MAPPING_CACHE

    def _toc(text: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in re.finditer(r"^##\s+(\d+(?:\s*[-\u2013]\s*\d+)?)\.\s+(.+)$", text, flags=re.M):
            num = m.group(1).strip()
            title = m.group(2).strip()
            anchor = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            out.append({"section": num, "title": title, "anchor": anchor})
        return out

    master_text = MAPPING_DOC.read_text(encoding="utf-8") if MAPPING_DOC.is_file() else ""
    legacy_text = LEGACY_DOC.read_text(encoding="utf-8") if LEGACY_DOC.is_file() else ""

    # Pull the integration matrix (## 0) module rows out as a structured list.
    modules: list[dict[str, Any]] = []
    matrix_match = re.search(r"##\s*0\.\s*Module integration matrix(.+?)(?:\n##\s|\Z)", master_text, flags=re.S)
    if matrix_match:
        for line in matrix_match.group(1).splitlines():
            if not line.startswith("|") or line.startswith("|---") or "Module" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 5:
                modules.append({
                    "module": cells[0],
                    "sicon_summary": cells[1],
                    "sage_summary": cells[2],
                    "direction": cells[3],
                    "section_ref": cells[4],
                })

    _MAPPING_CACHE = {
        "master": _toc(master_text),
        "legacy": _toc(legacy_text),
        "modules": modules,
        "generated_from": [str(MAPPING_DOC), str(LEGACY_DOC)],
    }
    return _MAPPING_CACHE


@router.get("/mapping/sections")
async def mapping_sections(user: dict = Depends(get_current_user)):
    _require_admin(user)
    return _parse_mapping_toc()


# ─────────────────────────────────────────────────────────────────
# Outbox drain controls (Phase 8 A · iter 215dz)
# ─────────────────────────────────────────────────────────────────


@router.post("/sicon/drain-now")
async def sicon_drain_now(
    user: dict = Depends(get_current_user),
    max_rows: int = Query(25, ge=1, le=500, description="batch size"),
):
    """Run one Sicon outbox drain pass against the live Sicon API.

    Honours the per-org `sicon_config.enabled` flag — orgs without
    credentials produce `skipped_no_config` and the row stays `pending`.
    """
    _require_admin(user)
    res = await sicon_tick(simulate=False, max_rows=max_rows)
    return res.__dict__


@router.post("/sicon/simulate-drain")
async def sicon_simulate_drain(
    user: dict = Depends(get_current_user),
    max_rows: int = Query(25, ge=1, le=500),
):
    """Demo-mode drain: every pending row transitions to `simulated_succeeded`.

    Used to show prospective customers how the outbox flushes WITHOUT touching
    a real Sicon endpoint. Live `succeeded` rows are unchanged.
    """
    _require_admin(user)
    res = await sicon_tick(simulate=True, max_rows=max_rows)
    return res.__dict__


@router.post("/sicon/requeue-failed")
async def sicon_requeue_failed(
    user: dict = Depends(get_current_user),
    include_dead_letter: bool = Query(False),
):
    """Move `failed` (and optionally `dead_letter`) rows back to `pending`."""
    _require_admin(user)
    n = await sicon_requeue(include_dead_letter=include_dead_letter)
    return {"ok": True, "requeued": n}


# ─── Sage drain controls (Phase 8 B · iter 215ea) ───


@router.post("/sage/drain-now")
async def sage_drain_now(
    user: dict = Depends(get_current_user),
    max_rows: int = Query(25, ge=1, le=500, description="batch size across both Sage outboxes"),
):
    """Run one Sage outbox drain pass against the live Sage 200 API.

    Drains both `svc_sage_invoice_outbox` (status=ready) and
    `svc_sage_po_outbox` (status=pending). Honours the per-org Sage 200
    config — orgs without an access_token produce `skipped_no_config`
    and the row stays at its eligible state.
    """
    _require_admin(user)
    res = await sage_tick(simulate=False, max_rows=max_rows)
    return res.__dict__


@router.post("/sage/simulate-drain")
async def sage_simulate_drain(
    user: dict = Depends(get_current_user),
    max_rows: int = Query(25, ge=1, le=500),
):
    """Demo drain — every eligible row transitions to `simulated_succeeded`.

    Used to demonstrate the Sage 200 flush path WITHOUT making any real API
    call. Real `posted` rows are unchanged.
    """
    _require_admin(user)
    res = await sage_tick(simulate=True, max_rows=max_rows)
    return res.__dict__


@router.post("/sage/requeue-failed")
async def sage_requeue_failed(
    user: dict = Depends(get_current_user),
    include_dead_letter: bool = Query(False),
):
    """Move Sage `failed` (and optionally `dead_letter`) rows back to their
    eligible state (invoice → ready, po → pending)."""
    _require_admin(user)
    n = await sage_requeue(include_dead_letter=include_dead_letter)
    return {"ok": True, "requeued": n}


__all__ = ["router"]
