"""Operations · Request a Part.

Operator-facing (Lite + Pro + Full) workflow that mirrors Log-a-Fault but
for spare parts. An operator picks one or more machines, sees each
machine's cover (warranty / contract / chargeable), lists the parts
required (helped by exploded drawings + optional AI photo ID), attaches
photos, then submits. On submit a branded **Supplier Parts Card** is
emailed to the supplier (default parts@pulsefitness.com, editable) with a
secure token link. The supplier acknowledges, quotes, invoices, allocates
and despatches from that public card — every step lands on the request's
timeline, which the operator watches from the Parts Request detail page
(just like the fault detail page). Requests can also be pushed to the
Service Desk as a case.

Collections
-----------
* ``parts_requests``               — one doc per request (machines[] · parts[])
* ``parts_request_events``         — immutable timeline
* ``parts_request_attachments``    — part photos (object storage)
* ``parts_request_supplier_cards`` — token-scoped supplier card per request
* ``exploded_drawings``            — admin-uploaded diagrams (manufacturer/model)
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File as FastAPIFile, Form, Request
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from utils.database import db, put_object, get_object, APP_NAME
from utils.auth import get_current_user
from utils.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Parts Requests"])

REQS = "parts_requests"
EVENTS = "parts_request_events"
ATTACH = "parts_request_attachments"
CARDS = "parts_request_supplier_cards"
DRAWINGS = "exploded_drawings"

DEFAULT_SUPPLIER_EMAIL = os.environ.get("PARTS_DEFAULT_SUPPLIER_EMAIL", "parts@pulsefitness.com")
_MAX_BYTES = 25 * 1024 * 1024
FRONTEND_URL = os.environ.get("FRONTEND_URL", os.environ.get("REACT_APP_BACKEND_URL", ""))

# Shared lifecycle (operator + supplier see the same track).
STATUSES = [
    {"key": "draft", "label": "Draft"},
    {"key": "submitted", "label": "Sent to Supplier"},
    {"key": "acknowledged", "label": "Acknowledged"},
    {"key": "quoted", "label": "Quote Provided"},
    {"key": "invoiced", "label": "Invoiced"},
    {"key": "allocated", "label": "Parts Allocated"},
    {"key": "despatched", "label": "Despatched"},
    {"key": "completed", "label": "Completed"},
    {"key": "cancelled", "label": "Cancelled"},
]
_STATUS_KEYS = {s["key"] for s in STATUSES}
_SUPPLIER_ACTIONS = {"acknowledge", "quote", "invoice", "allocate", "despatch", "complete", "comment"}
_ACTION_STATUS = {
    "acknowledge": "acknowledged", "quote": "quoted", "invoice": "invoiced",
    "allocate": "allocated", "despatch": "despatched", "complete": "completed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    return {"organization_id": org or "__none__"}


def _actor_name(user: dict) -> str:
    return user.get("full_name") or user.get("email") or "User"


async def _reference(org_id: str) -> str:
    n = await db[REQS].count_documents({"organization_id": org_id})
    return f"PR-{n + 1:05d}"


async def _event(request_id: str, actor: str, role: str, action: str,
                 note: str = "", meta: dict | None = None):
    await db[EVENTS].insert_one({
        "id": _id(), "request_id": request_id, "actor": actor, "actor_role": role,
        "action": action, "note": note, "meta": meta or {}, "at": _now(),
    })


async def _compute_cover(serial_number: str | None, org_id: str | None) -> dict:
    from routes.issues import _resolve_coverage_for_issue
    meta = await _resolve_coverage_for_issue(serial_number=serial_number, organization_id=org_id)
    return {
        "cover_type": meta.get("cover_type", "chargeable"),
        "coverage_status": meta.get("coverage_status", "uncovered"),
        "warranty_active": meta.get("warranty_active", False),
        "warranty_expiry": meta.get("warranty_expiry"),
        "contract_number": meta.get("contract_number", ""),
        "contract_tier": meta.get("contract_tier", ""),
        "contract_end_date": meta.get("contract_end_date", ""),
        "equipment_id": meta.get("equipment_id", ""),
        "equipment_site_id": meta.get("equipment_site_id"),
    }


async def _normalise_machines(machines: list[dict], org_id: str) -> list[dict]:
    out = []
    for m in machines or []:
        serial = (m.get("serial_number") or "").strip()
        cover = await _compute_cover(serial, org_id) if serial else {
            "cover_type": "chargeable", "coverage_status": "uncovered", "warranty_active": False,
            "warranty_expiry": None, "contract_number": "", "contract_tier": "",
            "contract_end_date": "", "equipment_id": m.get("equipment_id") or "", "equipment_site_id": None,
        }
        parts = []
        for p in (m.get("parts") or []):
            if not (p.get("part_name") or p.get("part_number")):
                continue
            parts.append({
                "id": p.get("id") or _id(),
                "part_name": (p.get("part_name") or "").strip(),
                "part_number": (p.get("part_number") or "").strip(),
                "qty": int(p.get("qty") or 1),
                "notes": (p.get("notes") or "").strip(),
                "drawing_id": p.get("drawing_id") or None,
            })
        out.append({
            "machine_index": len(out),
            "equipment_id": cover.get("equipment_id") or m.get("equipment_id") or "",
            "machine_name": (m.get("machine_name") or "").strip(),
            "serial_number": serial,
            "manufacturer": (m.get("manufacturer") or "").strip(),
            "model": (m.get("model") or "").strip(),
            "equipment_type": (m.get("equipment_type") or "").strip(),
            "cover_type": cover["cover_type"],
            "coverage_status": cover["coverage_status"],
            "warranty_expiry": cover["warranty_expiry"],
            "contract_number": cover["contract_number"],
            "contract_tier": cover["contract_tier"],
            "contract_end_date": cover["contract_end_date"],
            "parts": parts,
        })
    return out


def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


# ── Meta / lookups ──────────────────────────────────────────────────

@router.get("/parts-requests/meta")
async def parts_meta(user=Depends(get_current_user)):
    return {"statuses": STATUSES, "default_supplier_email": DEFAULT_SUPPLIER_EMAIL}


@router.get("/parts-requests/coverage")
async def coverage(serial_number: str = "", user=Depends(get_current_user)):
    if not serial_number.strip():
        raise HTTPException(400, "serial_number required")
    return await _compute_cover(serial_number, user.get("organization_id"))


@router.get("/parts-requests/equipment-search")
async def equipment_search(q: str = "", user=Depends(get_current_user)):
    query: dict = {**_of(user)}
    if q.strip():
        rx = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [{"name": rx}, {"serial_number": rx}, {"manufacturer": rx}, {"model": rx}]
    docs = await db.equipment.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "serial_number": 1, "manufacturer": 1,
         "model": 1, "equipment_type": 1, "supplier_name": 1, "location": 1},
    ).sort("name", 1).to_list(100)
    return {"equipment": docs}


# ── Exploded drawings ───────────────────────────────────────────────

@router.get("/exploded-drawings")
async def list_drawings(manufacturer: str = "", model: str = "", q: str = "",
                        user=Depends(get_current_user)):
    org = user.get("organization_id")
    # Org-owned OR globally-published (organization_id = null) drawings.
    query: dict = {"is_deleted": {"$ne": True},
                   "$or": [{"organization_id": org}, {"organization_id": None}]}
    filters = []
    if manufacturer.strip():
        filters.append({"manufacturer": {"$regex": manufacturer.strip(), "$options": "i"}})
    if model.strip():
        filters.append({"model": {"$regex": model.strip(), "$options": "i"}})
    if q.strip():
        rx = {"$regex": q.strip(), "$options": "i"}
        filters.append({"$or": [{"title": rx}, {"manufacturer": rx}, {"model": rx},
                                {"equipment_type": rx}]})
    if filters:
        query["$and"] = filters
    docs = await db[DRAWINGS].find(
        query, {"_id": 0, "storage_path": 0}
    ).sort("created_at", -1).to_list(200)
    return {"drawings": docs}


@router.post("/exploded-drawings")
async def upload_drawing(
    manufacturer: str = Form(""), model: str = Form(""), equipment_type: str = Form(""),
    title: str = Form(""), is_global: bool = Form(False),
    file: UploadFile = FastAPIFile(...), user=Depends(get_current_user),
):
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(413, "File too large (max 25MB)")
    is_master = bool(user.get("is_master_admin") or user.get("is_pulse_admin"))
    org = None if (is_global and is_master) else user.get("organization_id")
    did = _id()
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    path = f"{APP_NAME}/exploded-drawings/{did}.{ext}"
    ct = file.content_type or "application/octet-stream"
    result = await run_in_threadpool(put_object, path, content, ct)
    doc = {
        "id": did, "organization_id": org,
        "manufacturer": manufacturer.strip(), "model": model.strip(),
        "equipment_type": equipment_type.strip(),
        "title": title.strip() or (f"{manufacturer} {model}".strip() or file.filename),
        "original_filename": file.filename, "content_type": ct, "size": len(content),
        "storage_path": result.get("path", path), "is_global": bool(org is None),
        "is_deleted": False, "created_by": user.get("id"),
        "created_by_name": _actor_name(user), "created_at": _now(),
    }
    await db[DRAWINGS].insert_one(dict(doc))
    doc.pop("storage_path", None)
    return doc


@router.get("/exploded-drawings/{drawing_id}/file")
async def drawing_file(drawing_id: str, user=Depends(get_current_user)):
    org = user.get("organization_id")
    doc = await db[DRAWINGS].find_one(
        {"id": drawing_id, "is_deleted": {"$ne": True},
         "$or": [{"organization_id": org}, {"organization_id": None}]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Drawing not found")
    data, ct = await run_in_threadpool(get_object, doc["storage_path"])
    return Response(content=data, media_type=doc.get("content_type") or ct,
                    headers={"Content-Disposition": f'inline; filename="{doc.get("original_filename", "drawing")}"'})


@router.delete("/exploded-drawings/{drawing_id}")
async def delete_drawing(drawing_id: str, user=Depends(get_current_user)):
    org = user.get("organization_id")
    is_master = bool(user.get("is_master_admin") or user.get("is_pulse_admin"))
    q = {"id": drawing_id}
    if not is_master:
        q["organization_id"] = org
    res = await db[DRAWINGS].update_one(q, {"$set": {"is_deleted": True, "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Drawing not found")
    return {"success": True}


# ── Request CRUD ────────────────────────────────────────────────────

class RequestPayload(BaseModel):
    site_id: str | None = None
    supplier_name: str | None = None
    supplier_email: str | None = None
    notes: str | None = None
    machines: list[dict] = []


@router.get("/parts-requests")
async def list_requests(status: str | None = None, user=Depends(get_current_user)):
    q = {**_of(user)}
    if status:
        q["status"] = status
    docs = await db[REQS].find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    for d in docs:
        d["machine_count"] = len(d.get("machines") or [])
        d["part_count"] = sum(len(m.get("parts") or []) for m in (d.get("machines") or []))
    return {"requests": docs, "total": len(docs)}


@router.post("/parts-requests")
async def create_request(payload: RequestPayload, user=Depends(get_current_user)):
    org = user.get("organization_id")
    if not org:
        raise HTTPException(400, "No organisation context")
    machines = await _normalise_machines(payload.machines, org)
    doc = {
        "id": _id(), "reference": await _reference(org), "organization_id": org,
        "site_id": payload.site_id,
        "supplier_name": (payload.supplier_name or "").strip(),
        "supplier_email": (payload.supplier_email or DEFAULT_SUPPLIER_EMAIL).strip(),
        "notes": (payload.notes or "").strip(),
        "machines": machines, "status": "draft",
        "quote": None, "invoice": None, "despatch": None,
        "supplier_card_token": None, "sent_to_service_desk": False, "service_desk_case_id": None,
        "created_by": user.get("id"), "created_by_name": _actor_name(user),
        "created_at": _now(), "updated_at": _now(),
    }
    await db[REQS].insert_one(dict(doc))
    await _event(doc["id"], _actor_name(user), "operator", "created",
                 note=f"Parts request {doc['reference']} created")
    return _clean(dict(doc))


async def _load(request_id: str, user: dict) -> dict:
    doc = await db[REQS].find_one({"id": request_id, **_of(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Parts request not found")
    return doc


@router.get("/parts-requests/{request_id}")
async def get_request(request_id: str, user=Depends(get_current_user)):
    doc = await _load(request_id, user)
    events = await db[EVENTS].find({"request_id": request_id}, {"_id": 0}).sort("at", 1).to_list(500)
    atts = await db[ATTACH].find(
        {"request_id": request_id, "is_deleted": {"$ne": True}},
        {"_id": 0, "storage_path": 0}).sort("created_at", 1).to_list(500)
    doc["events"] = events
    doc["attachments"] = atts
    return doc


@router.put("/parts-requests/{request_id}")
async def update_request(request_id: str, payload: RequestPayload, user=Depends(get_current_user)):
    doc = await _load(request_id, user)
    if doc.get("status") not in ("draft",):
        raise HTTPException(400, "Only draft requests can be edited")
    updates = {"updated_at": _now()}
    if payload.machines is not None:
        updates["machines"] = await _normalise_machines(payload.machines, user.get("organization_id"))
    if payload.supplier_email is not None:
        updates["supplier_email"] = (payload.supplier_email or DEFAULT_SUPPLIER_EMAIL).strip()
    if payload.supplier_name is not None:
        updates["supplier_name"] = payload.supplier_name.strip()
    if payload.notes is not None:
        updates["notes"] = payload.notes.strip()
    if payload.site_id is not None:
        updates["site_id"] = payload.site_id
    await db[REQS].update_one({"id": request_id}, {"$set": updates})
    return _clean({**doc, **updates})


@router.post("/parts-requests/{request_id}/cancel")
async def cancel_request(request_id: str, user=Depends(get_current_user)):
    doc = await _load(request_id, user)
    if doc.get("status") in ("completed", "cancelled"):
        raise HTTPException(400, "Request is already closed")
    await db[REQS].update_one({"id": request_id}, {"$set": {"status": "cancelled", "updated_at": _now()}})
    await _event(request_id, _actor_name(user), "operator", "cancelled", note="Request cancelled")
    return {"success": True, "status": "cancelled"}


@router.post("/parts-requests/{request_id}/mark-received")
async def mark_received(request_id: str, user=Depends(get_current_user)):
    doc = await _load(request_id, user)
    await db[REQS].update_one({"id": request_id}, {"$set": {"status": "completed", "updated_at": _now()}})
    await _event(request_id, _actor_name(user), "operator", "received",
                 note="Parts received — request completed")
    return {"success": True, "status": "completed"}


# ── Attachments (object storage) ────────────────────────────────────

@router.post("/parts-requests/{request_id}/attachments")
async def upload_attachment(
    request_id: str, machine_index: int = 0, description: str = "",
    visible_to_supplier: bool = True,
    file: UploadFile = FastAPIFile(...), user=Depends(get_current_user),
):
    await _load(request_id, user)
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(413, "File too large (max 25MB)")
    aid = _id()
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    path = f"{APP_NAME}/parts-requests/{request_id}/{aid}.{ext}"
    ct = file.content_type or "application/octet-stream"
    result = await run_in_threadpool(put_object, path, content, ct)
    att = {
        "id": aid, "request_id": request_id, "organization_id": user.get("organization_id"),
        "machine_index": machine_index, "description": description,
        "original_filename": file.filename, "content_type": ct, "size": len(content),
        "storage_path": result.get("path", path), "visible_to_supplier": visible_to_supplier,
        "is_deleted": False, "uploaded_by": user.get("id"), "uploaded_by_name": _actor_name(user),
        "source": "operator", "created_at": _now(),
    }
    await db[ATTACH].insert_one(dict(att))
    await db[REQS].update_one({"id": request_id}, {"$set": {"updated_at": _now()}})
    att.pop("storage_path", None)
    return att


@router.get("/parts-requests/{request_id}/attachments/{attachment_id}/download")
async def download_attachment(request_id: str, attachment_id: str, user=Depends(get_current_user)):
    await _load(request_id, user)
    att = await db[ATTACH].find_one({"id": attachment_id, "request_id": request_id}, {"_id": 0})
    if not att:
        raise HTTPException(404, "Attachment not found")
    data, ct = await run_in_threadpool(get_object, att["storage_path"])
    return Response(content=data, media_type=att.get("content_type") or ct,
                    headers={"Content-Disposition": f'inline; filename="{att.get("original_filename", "file")}"'})


@router.delete("/parts-requests/{request_id}/attachments/{attachment_id}")
async def delete_attachment(request_id: str, attachment_id: str, user=Depends(get_current_user)):
    await _load(request_id, user)
    res = await db[ATTACH].update_one(
        {"id": attachment_id, "request_id": request_id}, {"$set": {"is_deleted": True}})
    if not res.matched_count:
        raise HTTPException(404, "Attachment not found")
    return {"success": True}


# ── AI part identification ──────────────────────────────────────────

@router.post("/parts-requests/{request_id}/ai-identify")
async def ai_identify(request_id: str, body: dict, user=Depends(get_current_user)):
    import base64
    await _load(request_id, user)
    attachment_id = body.get("attachment_id")
    if not attachment_id:
        raise HTTPException(400, "attachment_id required")
    att = await db[ATTACH].find_one({"id": attachment_id, "request_id": request_id}, {"_id": 0})
    if not att:
        raise HTTPException(404, "Attachment not found")
    data, _ = await run_in_threadpool(get_object, att["storage_path"])
    image_b64 = base64.b64encode(data).decode("utf-8")
    from utils.parts_ai import identify_part
    result = await identify_part(
        image_b64, machine_type=body.get("machine_type", ""),
        manufacturer=body.get("manufacturer", ""), model=body.get("model", ""),
        notes=body.get("notes", ""))
    if result.get("available"):
        await _event(request_id, _actor_name(user), "operator", "ai_identify",
                     note=f"AI suggested {len(result.get('suggestions') or [])} part(s)")
    return result


# ── Submit → supplier card + email ──────────────────────────────────

def _cover_label(m: dict) -> str:
    cs = m.get("coverage_status")
    if cs == "covered_contract":
        return f"Contract{(' · ' + m['contract_tier']) if m.get('contract_tier') else ''}"
    if cs == "covered_warranty":
        return "Under warranty"
    return "Chargeable"


def _card_url(token: str) -> str:
    base = (FRONTEND_URL or "").rstrip("/")
    return f"{base}/parts-card/{token}"


def _build_card_email_html(req: dict, org_name: str, token: str) -> str:
    machines = req.get("machines") or []
    rows = ""
    for m in machines:
        parts = "".join(
            f'<li style="margin:2px 0;">{p.get("qty",1)}× {p.get("part_name") or "—"}'
            f'{(" (" + p["part_number"] + ")") if p.get("part_number") else ""}'
            f'{(" — " + p["notes"]) if p.get("notes") else ""}</li>'
            for p in (m.get("parts") or [])
        ) or '<li style="color:#6B7280;">(no specific parts listed)</li>'
        rows += (
            f'<div style="margin:0 0 12px;padding:12px 14px;border:1px solid #E5E7EB;border-radius:8px;">'
            f'<p style="margin:0;font-size:14px;font-weight:600;color:#111;">{m.get("machine_name") or m.get("equipment_type") or "Machine"}'
            f'{(" · " + m["manufacturer"]) if m.get("manufacturer") else ""}{(" " + m["model"]) if m.get("model") else ""}</p>'
            f'<p style="margin:2px 0 6px;font-size:12px;color:#6B7280;">Serial: {m.get("serial_number") or "—"} · '
            f'<span style="font-weight:600;color:#0369A1;">{_cover_label(m)}</span></p>'
            f'<ul style="margin:0;padding:0 0 0 18px;font-size:13px;color:#111;">{parts}</ul></div>'
        )
    url = _card_url(token)
    return f'''
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;background:#fff;border:1px solid #E5E7EB;border-radius:14px;overflow:hidden;">
  <div style="background:#0A0A0A;padding:22px 28px;">
    <h1 style="color:#fff;font-size:18px;margin:0;">Parts Request {req.get('reference','')}</h1>
    <p style="color:#cbd5e1;font-size:12px;margin:4px 0 0;">from {org_name} · via Pulse Fitness</p>
  </div>
  <div style="padding:24px 28px;">
    <p style="color:#111;font-size:14px;line-height:1.6;margin:0 0 14px;">
      {org_name} has requested the parts below. Please review, then acknowledge,
      quote, allocate and despatch using the secure link.</p>
    {rows}
    {('<p style="font-size:13px;color:#374151;margin:12px 0 0;"><strong>Notes:</strong> ' + req["notes"] + '</p>') if req.get("notes") else ''}
    <div style="text-align:center;margin:22px 0 6px;">
      <a href="{url}" style="display:inline-block;background:#0055FF;color:#fff;text-decoration:none;padding:12px 26px;border-radius:999px;font-size:14px;font-weight:600;">Open Parts Request</a>
    </div>
    <p style="text-align:center;font-size:11px;color:#9CA3AF;margin:8px 0 0;">Or paste this link: {url}</p>
  </div>
  <div style="padding:14px 28px;background:#F9FAFB;border-top:1px solid #E5E7EB;">
    <p style="margin:0;font-size:11px;color:#6B7280;">Sent via Pulse Fitness — Equipment Maintenance Platform</p>
  </div>
</div>'''


class SubmitPayload(BaseModel):
    supplier_email: str | None = None
    supplier_name: str | None = None
    send_to_service_desk: bool = False


@router.post("/parts-requests/{request_id}/submit")
async def submit_request(request_id: str, payload: SubmitPayload, user=Depends(get_current_user)):
    doc = await _load(request_id, user)
    if doc.get("status") not in ("draft", "submitted"):
        raise HTTPException(400, "This request has already progressed")
    if not (doc.get("machines") or []):
        raise HTTPException(400, "Add at least one machine before submitting")
    supplier_email = (payload.supplier_email or doc.get("supplier_email") or DEFAULT_SUPPLIER_EMAIL).strip()
    supplier_name = (payload.supplier_name or doc.get("supplier_name") or "").strip()

    token = doc.get("supplier_card_token") or _id()
    await db[CARDS].update_one(
        {"request_id": request_id},
        {"$set": {"request_id": request_id, "token": token,
                  "organization_id": user.get("organization_id"),
                  "supplier_email": supplier_email, "supplier_name": supplier_name,
                  "updated_at": _now()},
         "$setOnInsert": {"id": _id(), "created_at": _now()}},
        upsert=True)

    org = await db.organizations.find_one({"id": user.get("organization_id")},
                                          {"_id": 0, "name": 1}) or {}
    org_name = org.get("name") or "Your Gym"
    html = _build_card_email_html(doc, org_name, token)
    sent = await send_email(
        supplier_email, f"Parts Request {doc.get('reference','')} — {org_name}",
        html, organization_id=user.get("organization_id"), kind="parts_request",
        category="service")

    updates = {"status": "submitted", "supplier_email": supplier_email,
               "supplier_name": supplier_name, "supplier_card_token": token,
               "submitted_at": _now(), "updated_at": _now()}
    await db[REQS].update_one({"id": request_id}, {"$set": updates})
    await _event(request_id, _actor_name(user), "operator", "submitted",
                 note=f"Sent to supplier {supplier_email}" + ("" if sent else " (email not dispatched — check email config)"),
                 meta={"supplier_email": supplier_email, "email_sent": bool(sent)})

    sd = None
    if payload.send_to_service_desk:
        sd = await _push_to_service_desk(request_id, user)
    return {"success": True, "status": "submitted", "email_sent": bool(sent),
            "supplier_card_url": _card_url(token), "service_desk": sd}


# ── Service Desk push ───────────────────────────────────────────────

async def _push_to_service_desk(request_id: str, user: dict) -> dict:
    doc = await _load(request_id, user)
    if doc.get("service_desk_case_id"):
        return {"created": False, "case_id": doc["service_desk_case_id"], "note": "already linked"}
    machines = doc.get("machines") or []
    first = machines[0] if machines else {}
    lines = [f"Parts request {doc.get('reference')} — {len(machines)} machine(s)."]
    for m in machines:
        parts = ", ".join(f"{p.get('qty',1)}× {p.get('part_name') or p.get('part_number') or '?'}"
                          for p in (m.get("parts") or [])) or "(no parts listed)"
        lines.append(f"• {m.get('machine_name') or m.get('equipment_type') or 'Machine'} "
                     f"[{m.get('serial_number') or 'no serial'}] — {parts} ({_cover_label(m)})")
    description = "\n".join(lines)
    try:
        from routes.svc.intake import _create_case as _svc_create_case
        payload = {
            "title": f"Parts request {doc.get('reference')}",
            "description": description, "priority": "medium",
            "cover_type": first.get("cover_type") or "chargeable",
            "case_type": "parts",
            "asset_id": first.get("equipment_id") or "",
            "asset_name": first.get("machine_name") or first.get("equipment_type") or "",
            "equipment_ids": [m.get("equipment_id") for m in machines if m.get("equipment_id")],
            "equipment_serials": [m.get("serial_number") for m in machines if m.get("serial_number")],
            "contract_id": "",
            "customer_name": user.get("full_name") or "",
            "customer_email": user.get("email") or "",
            "source_meta": {"parts_request_id": request_id, "channel": "parts_request",
                            "reference": doc.get("reference")},
        }
        case = await _svc_create_case(payload=payload, source="parts_request", user=user)
        case_id = (case or {}).get("id") if isinstance(case, dict) else None
        await db[REQS].update_one({"id": request_id},
                                  {"$set": {"sent_to_service_desk": True,
                                            "service_desk_case_id": case_id, "updated_at": _now()}})
        await _event(request_id, _actor_name(user), "operator", "service_desk",
                     note="Pushed to Service Desk", meta={"case_id": case_id})
        return {"created": True, "case_id": case_id}
    except Exception as e:
        logger.warning(f"parts request → service desk failed: {e}")
        await _event(request_id, _actor_name(user), "operator", "service_desk_failed",
                     note="Service Desk push failed")
        return {"created": False, "error": str(e)}


@router.post("/parts-requests/{request_id}/service-desk")
async def push_service_desk(request_id: str, user=Depends(get_current_user)):
    return await _push_to_service_desk(request_id, user)


# ── Public supplier card (token, no auth) ───────────────────────────

async def _load_card(token: str) -> tuple[dict, dict]:
    card = await db[CARDS].find_one({"token": token}, {"_id": 0})
    if not card:
        raise HTTPException(404, "Card not found or link expired")
    req = await db[REQS].find_one({"id": card["request_id"]}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Parts request not found")
    return card, req


@router.get("/parts-card/{token}")
async def supplier_card(token: str, request: Request):
    from utils.security_plus import rate_limit_async
    ip = request.client.host if request.client else "unknown"
    await rate_limit_async(f"parts_card_ip:{ip}", max_requests=120, window_seconds=300)
    card, req = await _load_card(token)
    org = await db.organizations.find_one({"id": req.get("organization_id")},
                                          {"_id": 0, "name": 1}) or {}
    events = await db[EVENTS].find({"request_id": req["id"]}, {"_id": 0}).sort("at", 1).to_list(500)
    atts = await db[ATTACH].find(
        {"request_id": req["id"], "is_deleted": {"$ne": True}, "visible_to_supplier": True},
        {"_id": 0, "storage_path": 0}).sort("created_at", 1).to_list(500)
    for m in (req.get("machines") or []):
        m["cover_label"] = _cover_label(m)
    return {
        "reference": req.get("reference"), "status": req.get("status"),
        "organization_name": org.get("name") or req.get("supplier_name") or "",
        "supplier_name": card.get("supplier_name"), "supplier_email": card.get("supplier_email"),
        "machines": req.get("machines") or [], "notes": req.get("notes"),
        "quote": req.get("quote"), "invoice": req.get("invoice"), "despatch": req.get("despatch"),
        "attachments": [{**a, "url": f"/api/parts-card/{token}/attachments/{a['id']}"} for a in atts],
        "events": events, "statuses": STATUSES,
    }


@router.get("/parts-card/{token}/attachments/{attachment_id}")
async def supplier_card_attachment(token: str, attachment_id: str):
    card, req = await _load_card(token)
    att = await db[ATTACH].find_one(
        {"id": attachment_id, "request_id": req["id"], "visible_to_supplier": True}, {"_id": 0})
    if not att:
        raise HTTPException(404, "Attachment not found")
    data, ct = await run_in_threadpool(get_object, att["storage_path"])
    return Response(content=data, media_type=att.get("content_type") or ct)


@router.post("/parts-card/{token}/update")
async def supplier_card_update(token: str, body: dict):
    card, req = await _load_card(token)
    action = (body.get("action") or "").strip()
    if action not in _SUPPLIER_ACTIONS:
        raise HTTPException(400, f"Invalid action. One of: {', '.join(sorted(_SUPPLIER_ACTIONS))}")
    if req.get("status") in ("cancelled",):
        raise HTTPException(400, "This request has been cancelled")
    supplier = card.get("supplier_name") or card.get("supplier_email") or "Supplier"
    note = (body.get("note") or "").strip()
    updates: dict = {"updated_at": _now()}
    meta: dict = {}

    if action == "quote":
        quote = {"amount": body.get("amount"), "currency": body.get("currency") or "GBP",
                 "notes": note, "at": _now()}
        updates["quote"] = quote
        meta = {"amount": quote["amount"], "currency": quote["currency"]}
    elif action == "invoice":
        invoice = {"amount": body.get("amount"), "currency": body.get("currency") or "GBP",
                   "invoice_number": body.get("invoice_number") or "", "notes": note, "at": _now()}
        updates["invoice"] = invoice
        meta = {"amount": invoice["amount"], "invoice_number": invoice["invoice_number"]}
    elif action == "despatch":
        despatch = {"carrier": body.get("carrier") or "", "tracking": body.get("tracking") or "",
                    "eta": body.get("eta") or "", "notes": note, "at": _now()}
        updates["despatch"] = despatch
        meta = {"carrier": despatch["carrier"], "tracking": despatch["tracking"]}

    if action in _ACTION_STATUS:
        updates["status"] = _ACTION_STATUS[action]
    await db[REQS].update_one({"id": req["id"]}, {"$set": updates})
    await _event(req["id"], supplier, "supplier", action, note=note, meta=meta)
    return {"success": True, "status": updates.get("status", req.get("status"))}
