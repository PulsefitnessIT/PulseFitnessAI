"""CRM · Master Price List — secure backup + manual exports (Iter 220 P1).

Manual exports (CSV / Excel) and an automatic weekly backup of the live
Master Price List, with cost/margin protection, a secure expiring
download link (no public file access), export history + audit, retention
purge, and Resend email delivery of the secure link to authorised
recipients.

Collections:
  crm_price_exports        generated files (base64) + secure token + expiry
  crm_price_backup_config  per-org weekly backup schedule + options
"""
from __future__ import annotations

import base64
import csv
import io
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import openpyxl
from fastapi import APIRouter, Body, Depends, HTTPException, Response

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/price-list", tags=["CRM Price List · Backups"])

LINK_EXPIRY_DAYS = 7
DEFAULT_RETENTION_DAYS = 90
_BASE_URL = (os.environ.get("EMAIL_PUBLIC_BASE_URL") or os.environ.get("FRONTEND_URL") or "").rstrip("/")

# Header order; cost/margin inserted conditionally after Sell Price.
_BASE_HEADERS = [
    ("sku", "Product Code"), ("sage_code", "Sage Item Code"), ("name", "Name"),
    ("description", "Description"), ("category", "Category"), ("sub_category", "Sub-category"),
    ("supplier_name", "Supplier"), ("manufacturer", "Manufacturer"), ("model", "Model"),
    ("sell_price", "Sell Price"),
]
_TAIL_HEADERS = [
    ("currency", "Currency"), ("tax_rate", "VAT %"), ("warranty", "Warranty"),
    ("status", "Status"), ("active", "Active"), ("source_sheet", "Source Sheet"),
    ("source_row", "Source Row"), ("updated_at", "Last Updated"), ("updated_by", "Updated By"),
    ("imported_data", "Imported Data"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _is_approver(user: dict) -> bool:
    return (
        bool(user.get("is_master_admin"))
        or bool(user.get("is_pulse_admin"))
        or (user.get("role") or "").lower() in ("admin", "owner")
    )


def _columns(include_cost: bool, include_margin: bool) -> list[tuple[str, str]]:
    cols = list(_BASE_HEADERS)
    if include_cost:
        cols.append(("cost_price", "Cost Price"))
    if include_margin:
        cols.append(("markup_percent", "Margin %"))
    cols.extend(_TAIL_HEADERS)
    return cols


def _cell(prod: dict, key: str):
    if key == "active":
        return "No" if prod.get("active") is False else "Yes"
    if key == "imported_data":
        uf = prod.get("unmapped_fields") or []
        return "; ".join(f"{u.get('column')}={u.get('value')}" for u in uf[:40])
    return prod.get(key, "")


async def _build_rows(query: dict, include_cost: bool, include_margin: bool) -> tuple[list[str], list[list], int]:
    cols = _columns(include_cost, include_margin)
    headers = [label for _, label in cols]
    keys = [k for k, _ in cols]
    rows: list[list] = []
    cur = db.crm_products.find(query, {"_id": 0}).sort([("category", 1), ("sku", 1)])
    async for p in cur:
        rows.append([_cell(p, k) for k in keys])
    return headers, rows, len(rows)


def _to_csv(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def _to_xlsx(headers: list[str], rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Master Price List"
    ws.append(headers)
    for r in rows:
        ws.append(["" if v is None else v for v in r])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _scope_query(user: dict, scope: str, category: str) -> dict:
    q = {**_of(user)}
    if scope == "live":
        q["active"] = True
    elif scope == "archived":
        q["active"] = False
    elif scope == "category" and category:
        q["category"] = category
        q["active"] = True
    # "all" → no active filter
    return q


async def _generate_export(user: dict, *, export_type: str, scope: str, category: str,
                           fmt: str, include_cost: bool, include_margin: bool,
                           emailed_to: list[str] | None = None) -> dict:
    query = _scope_query(user, scope, category)
    headers, rows, count = await _build_rows(query, include_cost, include_margin)
    fmt = "xlsx" if fmt == "xlsx" else "csv"
    content = _to_xlsx(headers, rows) if fmt == "xlsx" else _to_csv(headers, rows)
    export_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    ts = datetime.now(timezone.utc)
    fname = f"price_list_{scope}_{ts:%Y%m%d_%H%M}.{fmt}"
    doc = {
        "id": export_id, "organization_id": user.get("organization_id"),
        "type": export_type, "scope": scope, "category": category or None,
        "format": fmt, "include_cost": include_cost, "include_margin": include_margin,
        "sensitive": include_cost or include_margin,
        "product_count": count, "size": len(content),
        "filename": fname, "content_b64": base64.b64encode(content).decode("ascii"),
        "token": token, "status": "ready",
        "expires_at": (ts + timedelta(days=LINK_EXPIRY_DAYS)).isoformat(),
        "emailed_to": emailed_to or [],
        "created_at": _now(), "created_by": user.get("id", ""), "created_by_name": user.get("full_name", ""),
    }
    await db.crm_price_exports.insert_one(dict(doc))
    doc.pop("_id", None)
    doc["download_url"] = f"{_BASE_URL}/api/crm/price-list/export/download/{export_id}?token={token}"
    doc.pop("content_b64", None)
    return doc


# ── Manual export ──────────────────────────────────────────────────


@router.post("/export")
async def manual_export(body: dict = Body(default={}), user=Depends(get_crm_user)) -> dict:
    """Generate a manual export. Cost/margin columns are only included for
    owners/admins; everyone else gets a cost/margin-free file."""
    approver = _is_approver(user)
    scope = body.get("scope", "live")
    if scope not in ("live", "archived", "all", "category"):
        raise HTTPException(422, "Invalid scope")
    fmt = body.get("format", "csv")
    include_cost = bool(body.get("include_cost")) and approver
    include_margin = bool(body.get("include_margin")) and approver
    doc = await _generate_export(
        user, export_type="manual", scope=scope, category=body.get("category", ""),
        fmt=fmt, include_cost=include_cost, include_margin=include_margin,
    )
    await log_audit(user, "price_list_export", doc["id"], "manual_export",
                    {"scope": scope, "format": doc["format"], "count": doc["product_count"], "sensitive": doc["sensitive"]})
    return {"export": doc}


@router.get("/export/download/{export_id}")
async def download_export(export_id: str, token: str = ""):
    """Token-gated download — no login required (the token is the secret).
    Enforces expiry and rejects mismatched tokens. No public listing."""
    doc = await db.crm_price_exports.find_one({"id": export_id}, {"_id": 0})
    if not doc or not token or not secrets.compare_digest(token, doc.get("token", "")):
        raise HTTPException(404, "Export not found")
    if doc.get("expires_at") and doc["expires_at"] < _now():
        raise HTTPException(410, "This download link has expired")
    content = base64.b64decode(doc["content_b64"])
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
             if doc["format"] == "xlsx" else "text/csv")
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{doc["filename"]}"'})


@router.get("/exports")
async def list_exports(user=Depends(get_crm_user)) -> dict:
    cur = db.crm_price_exports.find(
        _of(user), {"_id": 0, "content_b64": 0, "token": 0},
    ).sort("created_at", -1).limit(50)
    items = await cur.to_list(50)
    return {"exports": items}


@router.get("/export/{export_id}/link")
async def get_export_link(export_id: str, user=Depends(get_crm_user)) -> dict:
    """Return a fresh secure link for an export the user can access."""
    doc = await db.crm_price_exports.find_one({"id": export_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Export not found")
    if doc.get("expires_at") and doc["expires_at"] < _now():
        raise HTTPException(410, "This download link has expired")
    return {"download_url": f"{_BASE_URL}/api/crm/price-list/export/download/{export_id}?token={doc['token']}",
            "expires_at": doc.get("expires_at")}


# ── Weekly backup config + run ─────────────────────────────────────


def _default_config(org: str) -> dict:
    return {
        "organization_id": org, "enabled": False, "frequency": "weekly",
        "day_of_week": 0, "time": "06:00", "recipients": [],
        "file_format": "xlsx", "include_cost": True, "include_margin": True,
        "retention_days": DEFAULT_RETENTION_DAYS, "last_run_at": None, "next_run_at": None,
    }


def _compute_next_run(day_of_week: int, time_str: str) -> str:
    now = datetime.now(timezone.utc)
    try:
        hh, mm = (int(x) for x in time_str.split(":"))
    except Exception:
        hh, mm = 6, 0
    days_ahead = (day_of_week - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate.isoformat()


@router.get("/backup/config")
async def get_backup_config(user=Depends(get_crm_user)) -> dict:
    cfg = await db.crm_price_backup_config.find_one(_of(user), {"_id": 0})
    return {"config": cfg or _default_config(user.get("organization_id")), "is_approver": _is_approver(user)}


@router.put("/backup/config")
async def update_backup_config(body: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    if not _is_approver(user):
        raise HTTPException(403, "Only owners / admins can configure backups")
    cfg = await db.crm_price_backup_config.find_one(_of(user), {"_id": 0}) or _default_config(user.get("organization_id"))
    for k in ("enabled", "include_cost", "include_margin"):
        if k in body:
            cfg[k] = bool(body[k])
    if "day_of_week" in body:
        cfg["day_of_week"] = max(0, min(6, int(body["day_of_week"])))
    if "time" in body:
        cfg["time"] = str(body["time"])[:5]
    if "file_format" in body:
        cfg["file_format"] = "csv" if body["file_format"] == "csv" else "xlsx"
    if "retention_days" in body:
        cfg["retention_days"] = max(1, int(body["retention_days"]))
    if "recipients" in body:
        cfg["recipients"] = [str(r).strip() for r in (body["recipients"] or []) if str(r).strip()]
    cfg["next_run_at"] = _compute_next_run(cfg["day_of_week"], cfg["time"]) if cfg.get("enabled") else None
    cfg["updated_at"] = _now()
    cfg["updated_by"] = user.get("id", "")
    await db.crm_price_backup_config.update_one(_of(user), {"$set": {**_of(user), **cfg}}, upsert=True)
    await log_audit(user, "price_list_backup_config", user.get("organization_id"), "updated",
                    {"enabled": cfg["enabled"], "frequency": cfg["frequency"]})
    return {"config": cfg}


async def _run_backup_for(user: dict, cfg: dict) -> dict:
    doc = await _generate_export(
        user, export_type="backup", scope="live", category="",
        fmt=cfg.get("file_format", "xlsx"),
        include_cost=bool(cfg.get("include_cost")), include_margin=bool(cfg.get("include_margin")),
        emailed_to=cfg.get("recipients") or [],
    )
    # Email a secure link to authorised recipients (no raw sensitive data in the inbox).
    await _email_backup_link(user, doc, cfg)
    return doc


async def _email_backup_link(user: dict, doc: dict, cfg: dict) -> None:
    recipients = cfg.get("recipients") or []
    if not recipients:
        return
    from utils.email import send_email
    link = doc["download_url"]
    sensitive = doc.get("sensitive")
    html = f"""
    <div style="font-family:Arial,sans-serif;color:#1e293b">
      <h2 style="color:#0055FF">Master Price List — weekly backup</h2>
      <p>Your scheduled Master Price List backup is ready ({doc['product_count']} products, {doc['format'].upper()}).</p>
      {"<p style='color:#b45309'><strong>This file includes cost / margin data — handle securely.</strong></p>" if sensitive else ""}
      <p><a href="{link}" style="display:inline-block;background:#0055FF;color:#fff;padding:12px 28px;text-decoration:none;border-radius:6px;font-weight:bold">Download secure backup</a></p>
      <p style="color:#94a3b8;font-size:12px">This secure link expires on {doc['expires_at'][:10]}. Do not forward to unauthorised recipients.</p>
    </div>"""
    for to in recipients:
        try:
            await send_email(to=to, subject="Pulse Fitness — Master Price List weekly backup",
                             html=html, organization_id=user.get("organization_id"),
                             kind="price_list_backup", category="backup")
        except Exception:
            logger.exception("[price-backup] email to %s failed", to)


@router.post("/backup/run")
async def run_backup_now(user=Depends(get_crm_user)) -> dict:
    if not _is_approver(user):
        raise HTTPException(403, "Only owners / admins can run backups")
    cfg = await db.crm_price_backup_config.find_one(_of(user), {"_id": 0}) or _default_config(user.get("organization_id"))
    doc = await _run_backup_for(user, cfg)
    await db.crm_price_backup_config.update_one(_of(user), {"$set": {"last_run_at": _now()}}, upsert=True)
    await log_audit(user, "price_list_export", doc["id"], "backup_run",
                    {"count": doc["product_count"], "emailed": len(doc.get("emailed_to") or [])})
    return {"export": doc}


# ── Scheduler ──────────────────────────────────────────────────────


async def run_weekly_backup_loop(interval_minutes: int = 60) -> None:
    import asyncio
    logger.info("[price-backup] weekly backup loop started (%dm)", interval_minutes)
    while True:
        try:
            await run_due_backups()
            await purge_expired_exports()
        except Exception:
            logger.exception("[price-backup] loop error")
        await asyncio.sleep(interval_minutes * 60)


async def run_due_backups() -> dict:
    now = _now()
    due = await db.crm_price_backup_config.find(
        {"enabled": True, "next_run_at": {"$lte": now}}, {"_id": 0},
    ).to_list(200)
    ran = 0
    for cfg in due:
        org = cfg.get("organization_id")
        # impersonation context for export ownership
        owner = await db.crm_users.find_one({"organization_id": org, "role": {"$in": ["owner", "admin"]}}, {"_id": 0})
        actor = owner or {"organization_id": org, "id": "scheduler", "full_name": "Backup scheduler"}
        try:
            await _run_backup_for(actor, cfg)
            await db.crm_price_backup_config.update_one(
                {"organization_id": org},
                {"$set": {"last_run_at": now, "next_run_at": _compute_next_run(cfg.get("day_of_week", 0), cfg.get("time", "06:00"))}},
            )
            ran += 1
        except Exception:
            logger.exception("[price-backup] backup failed for org %s", org)
    if ran:
        logger.info("[price-backup] ran %d scheduled backup(s)", ran)
    return {"ran": ran, "due": len(due)}


async def purge_expired_exports() -> dict:
    """Delete export files past their org's retention window."""
    purged = 0
    cfgs = await db.crm_price_backup_config.find({}, {"_id": 0, "organization_id": 1, "retention_days": 1}).to_list(500)
    retention_by_org = {c["organization_id"]: c.get("retention_days", DEFAULT_RETENTION_DAYS) for c in cfgs}
    # default retention for orgs without config
    orgs = await db.crm_price_exports.distinct("organization_id")
    for org in orgs:
        days = retention_by_org.get(org, DEFAULT_RETENTION_DAYS)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        res = await db.crm_price_exports.delete_many({"organization_id": org, "created_at": {"$lt": cutoff}})
        purged += res.deleted_count
    if purged:
        logger.info("[price-backup] purged %d expired export(s)", purged)
    return {"purged": purged}


async def ensure_price_backup_indexes() -> None:
    try:
        await db.crm_price_exports.create_index([("organization_id", 1), ("created_at", -1)])
        await db.crm_price_exports.create_index([("id", 1)])
        await db.crm_price_backup_config.create_index([("organization_id", 1)], unique=True)
        await db.crm_price_backup_config.create_index([("enabled", 1), ("next_run_at", 1)])
    except Exception:
        logger.exception("ensure_price_backup_indexes failed (non-fatal)")
