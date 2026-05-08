"""
GymAxis Service Operations — Customer Comms Hub.

Iter 215dv (Phase 7b).

Three flows on top of the existing Resend integration (utils/email.py):

  • Email templates (svc_email_templates) — operators edit per-org
    Mustache-style templates with `{{var}}` placeholders. Defaults are
    seeded for the four most common operations:
        case_logged          customer-facing
        engineer_en_route    customer-facing
        case_completed       customer-facing
        supplier_po          supplier-facing PO email

  • Customer status updates — POST /api/svc/comms/case/{case_id}/notify
    sends a templated email to the customer using the merged
    case context. Logs to svc_case_events (type='comm') so the
    timeline shows it.

  • Supplier PO send — POST /api/svc/comms/po/{po_id}/send fills the
    'supplier_po' template, attaches a plain-text PO summary, sends to
    po.supplier_email, and writes a movement-style audit row.

  • Send history — GET /api/svc/comms/log returns the recent
    svc_comms_log rows (filterable by case/po/template).
"""
__integration_fields__ = {
    # svc_email_templates (per-org operator-editable templates)
    "templates.id":         "gymaxis_only: local uuid",
    "templates.organization_id": "gymaxis_only: tenant scoping",
    "templates.key":        "gymaxis_only: stable slug (case_logged | engineer_en_route | case_completed | supplier_po)",
    "templates.audience":   "gymaxis_only: customer | supplier | engineer (drives recipient resolution)",
    "templates.subject":    "gymaxis_only: rendered email subject (Mustache {{var}})",
    "templates.body_html":  "gymaxis_only: rendered email body (Mustache {{var}})",
    "templates.is_default": "gymaxis_only: seeded default flag",
    "templates.active":     "gymaxis_only: send-blocked switch",
    # svc_comms_log (every send attempt)
    "log.id":               "gymaxis_only: local uuid",
    "log.kind":             "gymaxis_only: case_notify | po_send | manual",
    "log.to":               "gymaxis_only: recipient email (Resend)",
    "log.subject":          "gymaxis_only: rendered subject",
    "log.template_key":     "gymaxis_only: which template was used",
    "log.case_id":          "sicon: ServiceCallID (back-reference for cross-system search) · GymAxis → Sicon (timeline only)",
    "log.po_id":            "sage: POPOrderID (back-reference; PO email is also referenced from Sage outbox) · gymaxis_only otherwise",
    "log.ok":               "gymaxis_only: send success flag from Resend",
    "log.error":            "gymaxis_only: provider error string (truncated 500 chars)",
    "log.actor_id":         "gymaxis_only: who triggered the send (audit)",
    "log.at":               "gymaxis_only: timestamp",
    # Side-effect: case timeline event written via append_event(type='comm')
    "case_event.comm.body":  "sicon: TrackingNote (when push_event runs on the case) · GymAxis → Sicon",
    "case_event.comm.extra": "sicon: TrackingNote.Metadata (template_key / to / log_id) · GymAxis → Sicon",
    # Side-effect: PO supplier_email_sent_at flag written on success
    "po.supplier_email_sent_at": "sage: POPOrder.NotifiedAt (when SLContract / POPOrder wiring lands) · GymAxis → Sage",
}

from datetime import datetime, timezone
from typing import Optional
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.database import db
from utils.auth import get_current_user
from utils.email import send_email
from utils.svc_state import append_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/svc/comms", tags=["Service Ops · Comms Hub"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return {"organization_id": org}


def _strip(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


# ─────────────────────────────────────────────────────────────────
# Default templates seeded on first read
# ─────────────────────────────────────────────────────────────────

_DEFAULTS: list[dict] = [
    {
        "key": "case_logged",
        "audience": "customer",
        "subject": "We've logged your service case {{reference}}",
        "body_html": (
            "<p>Hi {{customer_name}},</p>"
            "<p>Thanks for getting in touch. We've logged a service case for "
            "<strong>{{site_name}}</strong>:</p>"
            "<p><strong>Reference:</strong> {{reference}}<br>"
            "<strong>Issue:</strong> {{title}}<br>"
            "<strong>Priority:</strong> {{priority_label}}</p>"
            "<p>An engineer will be assigned shortly. We'll email you again "
            "as soon as we have an ETA.</p>"
            "<p>— The GymAxis service desk</p>"
        ),
    },
    {
        "key": "engineer_en_route",
        "audience": "customer",
        "subject": "Your engineer is on the way — {{reference}}",
        "body_html": (
            "<p>Hi {{customer_name}},</p>"
            "<p><strong>{{engineer_name}}</strong> is on the way to "
            "<strong>{{site_name}}</strong> for case <strong>{{reference}}</strong>.</p>"
            "<p>Estimated arrival: <strong>{{scheduled_label}}</strong>.</p>"
            "<p>If you need to reach us, reply to this email or call the desk.</p>"
            "<p>— The GymAxis service desk</p>"
        ),
    },
    {
        "key": "case_completed",
        "audience": "customer",
        "subject": "Service complete — {{reference}}",
        "body_html": (
            "<p>Hi {{customer_name}},</p>"
            "<p>We've completed the service for <strong>{{title}}</strong> at "
            "<strong>{{site_name}}</strong>.</p>"
            "<p><strong>Summary:</strong> {{summary}}</p>"
            "<p>If anything still isn't right, reply to this email and we'll "
            "get someone back to you.</p>"
            "<p>— The GymAxis service desk</p>"
        ),
    },
    {
        "key": "supplier_po",
        "audience": "supplier",
        "subject": "Purchase order {{po_reference}} — {{org_name}}",
        "body_html": (
            "<p>Hi,</p>"
            "<p>Please find our purchase order <strong>{{po_reference}}</strong> "
            "below. Confirm receipt and ship to the warehouse address on file.</p>"
            "<p><strong>Supplier:</strong> {{supplier}}<br>"
            "<strong>Lines:</strong> {{line_count}}<br>"
            "<strong>Total:</strong> £{{total}}</p>"
            "<pre style='font-family: ui-monospace, monospace; font-size: 12px; "
            "background: #f8fafc; padding: 12px; border-radius: 8px;'>{{lines_text}}</pre>"
            "<p>{{notes}}</p>"
            "<p>— {{org_name}}</p>"
        ),
    },
]


async def _ensure_defaults(of: dict) -> None:
    """Lazy-seed default templates the first time an org touches the hub."""
    existing = await db.svc_email_templates.find(of, {"_id": 0, "key": 1}).to_list(20)
    have = {t["key"] for t in existing}
    to_add = [t for t in _DEFAULTS if t["key"] not in have]
    if not to_add:
        return
    for t in to_add:
        await db.svc_email_templates.insert_one({
            "id": str(uuid.uuid4()),
            **of,
            **t,
            "is_default": True,
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
        })


# ─────────────────────────────────────────────────────────────────
# Template CRUD
# ─────────────────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(user=Depends(get_current_user)):
    of = _of(user)
    await _ensure_defaults(of)
    rows = await db.svc_email_templates.find(of, {"_id": 0}).sort("key", 1).to_list(50)
    return {"templates": rows, "count": len(rows)}


@router.put("/templates/{key}")
async def update_template(key: str, data: dict, user=Depends(get_current_user)):
    """Update or create a template by stable key."""
    of = _of(user)
    if not key:
        raise HTTPException(400, "key required")
    audience = ((data or {}).get("audience") or "customer").lower()
    if audience not in ("customer", "supplier", "engineer"):
        raise HTTPException(400, "audience must be customer | supplier | engineer")
    subject = ((data or {}).get("subject") or "").strip()
    body = ((data or {}).get("body_html") or "").strip()
    if not subject or not body:
        raise HTTPException(400, "subject and body_html required")
    await db.svc_email_templates.update_one(
        {**of, "key": key},
        {
            "$set": {
                "subject": subject,
                "body_html": body,
                "audience": audience,
                "active": bool((data or {}).get("active", True)),
                "updated_at": _now(),
                "updated_by_id": user["id"],
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                **of,
                "key": key,
                "is_default": False,
                "created_at": _now(),
            },
        },
        upsert=True,
    )
    row = await db.svc_email_templates.find_one({**of, "key": key}, {"_id": 0})
    return row


@router.post("/templates/{key}/reset")
async def reset_template(key: str, user=Depends(get_current_user)):
    of = _of(user)
    default = next((d for d in _DEFAULTS if d["key"] == key), None)
    if not default:
        raise HTTPException(404, "No default template with that key")
    await db.svc_email_templates.update_one(
        {**of, "key": key},
        {"$set": {**default, "is_default": True, "active": True, "updated_at": _now()}},
        upsert=True,
    )
    return await db.svc_email_templates.find_one({**of, "key": key}, {"_id": 0})


# ─────────────────────────────────────────────────────────────────
# Render helper
# ─────────────────────────────────────────────────────────────────

_VAR = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def _render(template: str, ctx: dict) -> str:
    def lookup(name: str) -> str:
        cur = ctx
        for part in name.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return ""
        return "" if cur is None else str(cur)
    return _VAR.sub(lambda m: lookup(m.group(1)), template or "")


async def _log_send(*, of: dict, kind: str, to: str, subject: str,
                    template_key: str, ok: bool, error: str | None,
                    case_id: str = "", po_id: str = "",
                    actor: dict | None = None) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        **of,
        "kind": kind,                   # case_notify | po_send | manual
        "to": to,
        "subject": subject,
        "template_key": template_key,
        "case_id": case_id,
        "po_id": po_id,
        "ok": ok,
        "error": (error or "")[:500],
        "actor_id": (actor or {}).get("id", "") if actor else "",
        "actor_name": (actor or {}).get("full_name", "") or (actor or {}).get("email", ""),
        "at": _now(),
    }
    try:
        await db.svc_comms_log.insert_one(row)
    except Exception as e:
        logger.warning("comms log write failed: %s", e)
    row.pop("_id", None)
    return row


# ─────────────────────────────────────────────────────────────────
# Case → customer notify
# ─────────────────────────────────────────────────────────────────

_PRIORITY_LABEL = {
    "p1": "P1 — Critical (same-day)", "p2": "P2 — High",
    "p3": "P3 — Standard", "p4": "P4 — Low",
}


@router.post("/case/{case_id}/notify")
async def notify_case(case_id: str, data: dict, user=Depends(get_current_user)):
    """Send a customer-facing email for a case using a saved template.

    Body: {template_key, override_subject?, override_body_html?, to?}
    """
    of = _of(user)
    case = await db.svc_cases.find_one({"id": case_id, **of}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    key = ((data or {}).get("template_key") or "case_logged").strip()
    template = await db.svc_email_templates.find_one({**of, "key": key}, {"_id": 0})
    if not template:
        await _ensure_defaults(of)
        template = await db.svc_email_templates.find_one({**of, "key": key}, {"_id": 0})
    if not template:
        raise HTTPException(404, f"Template {key!r} not found")
    to = (data or {}).get("to") or case.get("customer_email") or ""
    if not to or "@" not in to:
        raise HTTPException(400, "No customer email — set one on the case or pass `to` in the body")

    ctx = {
        **case,
        "priority_label": _PRIORITY_LABEL.get(case.get("priority", "p3"), case.get("priority", "p3")),
        "scheduled_label": case.get("scheduled_at") or "to be confirmed",
        "engineer_name": case.get("assigned_engineer_name") or "Our engineer",
        "summary": (data or {}).get("summary_override") or "",
    }
    subject = _render((data or {}).get("override_subject") or template["subject"], ctx)
    body = _render((data or {}).get("override_body_html") or template["body_html"], ctx)

    ok = await send_email(to=to, subject=subject, html=body)
    log = await _log_send(of=of, kind="case_notify", to=to, subject=subject,
                          template_key=key, ok=ok, error=None if ok else "send_email returned False",
                          case_id=case_id, actor=user)
    if ok:
        await append_event(
            case_id=case_id, organization_id=of["organization_id"],
            event_type="comm", actor=user,
            body=f"Email sent: {subject}",
            extra={"template_key": key, "to": to, "log_id": log["id"], "visibility": "internal"},
        )
    return {"ok": ok, "log": log}


# ─────────────────────────────────────────────────────────────────
# Supplier PO send
# ─────────────────────────────────────────────────────────────────

def _po_lines_text(po: dict) -> str:
    lines = po.get("lines") or []
    if not lines:
        return "(no lines)"
    out = []
    for line in lines:
        out.append(
            f"{(line.get('part_sku') or '').ljust(14)}"
            f" qty {int(line.get('qty') or 0):>4}"
            f" @ £{float(line.get('unit_cost') or 0):>8.2f}"
            f"  {line.get('part_name') or line.get('description') or ''}"
        )
    return "\n".join(out)


@router.post("/po/{po_id}/send")
async def send_po(po_id: str, data: dict, user=Depends(get_current_user)):
    """Email a submitted PO to the supplier."""
    of = _of(user)
    po = await db.svc_purchase_orders.find_one({**of, "id": po_id}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO not found")
    if po.get("status") not in ("submitted", "draft"):
        raise HTTPException(409, "Only draft or submitted POs may be emailed")
    to = ((data or {}).get("to") or po.get("supplier_email") or "").strip()
    if not to or "@" not in to:
        raise HTTPException(400, "Supplier email is missing — set it on the PO or pass `to`")

    template = await db.svc_email_templates.find_one({**of, "key": "supplier_po"}, {"_id": 0})
    if not template:
        await _ensure_defaults(of)
        template = await db.svc_email_templates.find_one({**of, "key": "supplier_po"}, {"_id": 0})

    org = await db.organizations.find_one({"id": of["organization_id"]}, {"_id": 0, "name": 1})
    ctx = {
        **po,
        "po_reference": po.get("reference") or "",
        "supplier": po.get("supplier") or "",
        "line_count": len(po.get("lines") or []),
        "total": f"{float(po.get('total') or 0):.2f}",
        "lines_text": _po_lines_text(po),
        "notes": po.get("notes") or "",
        "org_name": (org or {}).get("name") or "GymAxis",
    }
    subject = _render((data or {}).get("override_subject") or template["subject"], ctx)
    body = _render((data or {}).get("override_body_html") or template["body_html"], ctx)

    ok = await send_email(to=to, subject=subject, html=body)
    log = await _log_send(of=of, kind="po_send", to=to, subject=subject,
                          template_key="supplier_po", ok=ok,
                          error=None if ok else "send_email returned False",
                          po_id=po_id, actor=user)
    if ok:
        # Mark the PO as sent so the operator UI shows the send timestamp.
        await db.svc_purchase_orders.update_one(
            {"id": po_id},
            {"$set": {"supplier_email_sent_at": _now(), "updated_at": _now()}},
        )
    return {"ok": ok, "log": log}


# ─────────────────────────────────────────────────────────────────
# Log read
# ─────────────────────────────────────────────────────────────────

@router.get("/log")
async def comms_log(
    case_id: Optional[str] = Query(None),
    po_id: Optional[str] = Query(None),
    template_key: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(get_current_user),
):
    of = _of(user)
    q: dict = {**of}
    if case_id:
        q["case_id"] = case_id
    if po_id:
        q["po_id"] = po_id
    if template_key:
        q["template_key"] = template_key
    rows = await db.svc_comms_log.find(q, {"_id": 0}).sort("at", -1).limit(limit).to_list(limit)
    return {"events": rows, "count": len(rows)}


__all__ = ["router"]
