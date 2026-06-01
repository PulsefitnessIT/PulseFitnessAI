"""Iter 220ea·33 — Legacy report import + generation (Engineer App).

A wizard-driven tool: engineers enter the customer, bulk-upload historic
PDF/CSV/XLSX reports (each tagged with its own date + job number), Gemini
extracts the machines + per-machine custom fields, the engineer reviews,
then we generate a beautiful branded PDF and save it against the customer
(creating the customer record if they're new).

Scope: works for org engineers AND orgless partner engineers — keyed by
``scope = organization_id or "eng:<user_id>"``.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Response
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from utils.database import db
from utils.legacy_extract import extract_legacy_report
from utils.legacy_report_pdf import build_legacy_pdf

router = APIRouter(prefix="/svc/legacy", tags=["legacy-reports"])
logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB per legacy file


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope(user: dict) -> str:
    return user.get("organization_id") or f"eng:{user['id']}"


async def _fetch_logo_bytes(url: str | None) -> bytes | None:
    if not url:
        return None
    if url.startswith("data:"):
        try:
            import base64
            return base64.b64decode(url.split(",", 1)[1])
        except Exception:
            return None
    full = url
    if url.startswith("/"):
        base = os.environ.get("INTERNAL_BACKEND_URL", "http://localhost:8001")
        full = f"{base.rstrip('/')}{url}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(full)
            r.raise_for_status()
            return r.content
    except Exception as exc:  # noqa: BLE001
        logger.warning("[legacy] logo fetch failed %s: %s", url, exc)
        return None


# ── Customers ────────────────────────────────────────────────────────

class CustomerInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    site_name: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    contact_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=80)


@router.get("/customers/search")
async def search_customers(q: str = "", user: dict = Depends(get_current_user)):
    scope = _scope(user)
    query: dict = {"organization_id": scope}
    if q.strip():
        query["name"] = {"$regex": q.strip(), "$options": "i"}
    cur = db.svc_engineer_customers.find(query, {"_id": 0}).sort("updated_at", -1).limit(20)
    rows = await cur.to_list(20)
    return {"customers": [{
        "id": c["id"], "name": c.get("name"), "site_name": c.get("site_name"),
        "address": c.get("site_address"), "email": c.get("email"), "phone": c.get("phone"),
        "contact_name": c.get("contact_name"),
    } for c in rows]}


async def _upsert_customer(scope: str, engineer_id: str, c: dict) -> dict:
    """Find an existing scope customer by name (case-insensitive) or create one."""
    name = (c.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Customer name is required")
    existing = await db.svc_engineer_customers.find_one(
        {"organization_id": scope, "name": {"$regex": f"^{name}$", "$options": "i"}}, {"_id": 0})
    if existing:
        return existing
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": scope,
        "engineer_id": engineer_id,
        "name": name,
        "site_name": (c.get("site_name") or "").strip() or None,
        "site_address": (c.get("address") or "").strip() or None,
        "contact_name": (c.get("contact_name") or "").strip() or None,
        "email": (c.get("email") or "").strip() or None,
        "phone": (c.get("phone") or "").strip() or None,
        "source": "legacy_import",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_engineer_customers.insert_one(doc)
    return doc


@router.post("/customers")
async def create_customer(payload: CustomerInput, user: dict = Depends(get_current_user)):
    cust = await _upsert_customer(_scope(user), user["id"], payload.model_dump())
    return {"customer": {k: cust.get(k) for k in
            ("id", "name", "site_name", "site_address", "contact_name", "email", "phone")}}


# ── Extraction ───────────────────────────────────────────────────────

@router.post("/extract")
async def extract_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Run Gemini extraction on one uploaded legacy file. Returns the
    structured machines + detected customer hints for review (not saved)."""
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(413, "File too large — keep each file under 15 MB")
    ext = (file.filename or "").lower().rsplit(".", 1)[-1] if "." in (file.filename or "") else ""
    if ext not in ("pdf", "csv", "xlsx", "xls"):
        raise HTTPException(415, "Unsupported file type — upload a PDF, CSV or XLSX")
    try:
        data = await extract_legacy_report(raw, file.filename or "report")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        logger.exception("[legacy] extraction failed")
        raise HTTPException(502, "AI extraction failed — please try again")
    data["filename"] = file.filename
    return data


# ── Reports ──────────────────────────────────────────────────────────

class CustomField(BaseModel):
    label: str = Field(..., max_length=120)
    value: str = Field(default="", max_length=500)


class Machine(BaseModel):
    name: str = Field(default="Machine", max_length=160)
    model: str | None = Field(default=None, max_length=160)
    serial: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=80)
    work_done: str | None = Field(default=None, max_length=4000)
    custom_fields: list[CustomField] = Field(default_factory=list)


class Visit(BaseModel):
    service_date: str | None = Field(default=None, max_length=40)
    job_number: str | None = Field(default=None, max_length=80)
    summary: str | None = Field(default=None, max_length=2000)
    filename: str | None = Field(default=None, max_length=300)
    machines: list[Machine] = Field(default_factory=list)


class SaveReport(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    customer_id: str | None = Field(default=None, max_length=64)
    customer: CustomerInput | None = None
    visits: list[Visit] = Field(default_factory=list)


@router.post("/reports")
async def save_report(payload: SaveReport, user: dict = Depends(get_current_user)):
    scope = _scope(user)
    if not payload.visits:
        raise HTTPException(400, "Add at least one imported file/visit")

    # Resolve or create the customer.
    if payload.customer_id:
        cust_doc = await db.svc_engineer_customers.find_one(
            {"id": payload.customer_id, "organization_id": scope}, {"_id": 0})
        if not cust_doc:
            raise HTTPException(404, "Customer not found")
    elif payload.customer:
        cust_doc = await _upsert_customer(scope, user["id"], payload.customer.model_dump())
    else:
        raise HTTPException(400, "Select an existing customer or enter new customer details")

    customer_snapshot = {
        "name": cust_doc.get("name"),
        "site_name": cust_doc.get("site_name"),
        "address": cust_doc.get("site_address"),
        "contact_name": cust_doc.get("contact_name"),
        "email": cust_doc.get("email"),
        "phone": cust_doc.get("phone"),
    }
    machine_count = sum(len(v.machines) for v in payload.visits)
    report = {
        "id": str(uuid.uuid4()),
        "scope": scope,
        "engineer_id": user["id"],
        "customer_id": cust_doc["id"],
        "customer": customer_snapshot,
        "title": (payload.title or "").strip() or f"Service report — {customer_snapshot['name']}",
        "visits": [v.model_dump() for v in payload.visits],
        "visit_count": len(payload.visits),
        "machine_count": machine_count,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.svc_legacy_reports.insert_one(report)
    report.pop("_id", None)
    return {"report": report}


@router.get("/reports")
async def list_reports(customer_id: str | None = None, user: dict = Depends(get_current_user)):
    query: dict = {"scope": _scope(user)}
    if customer_id:
        query["customer_id"] = customer_id
    cur = db.svc_legacy_reports.find(
        query, {"_id": 0, "visits": 0}).sort("created_at", -1).limit(200)
    return {"reports": await cur.to_list(200)}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, user: dict = Depends(get_current_user)):
    r = await db.svc_legacy_reports.find_one(
        {"id": report_id, "scope": _scope(user)}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Report not found")
    return {"report": r}


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str, user: dict = Depends(get_current_user)):
    res = await db.svc_legacy_reports.delete_one({"id": report_id, "scope": _scope(user)})
    if not res.deleted_count:
        raise HTTPException(404, "Report not found")
    return {"ok": True}


@router.get("/reports/{report_id}/pdf")
async def report_pdf(report_id: str, user: dict = Depends(get_current_user)):
    r = await db.svc_legacy_reports.find_one(
        {"id": report_id, "scope": _scope(user)}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Report not found")

    branding = (user.get("branding") or {}).copy()
    if not branding.get("company_name"):
        branding["company_name"] = user.get("full_name") or ""
    logo_bytes = await _fetch_logo_bytes(branding.get("logo_url"))
    try:
        pdf = build_legacy_pdf(r, branding, logo_bytes)
    except Exception:
        logger.exception("[legacy] PDF build failed")
        raise HTTPException(500, "Could not generate the PDF")

    safe = (r.get("customer", {}).get("name") or "report").replace(" ", "_")[:40]
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{safe}_service_report.pdf"'})


__all__ = ["router"]
