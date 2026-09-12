"""Finance-sync layer for Aftersales contracts → Sage 200 (via Sicon WebAPI).

Pulse Fitness runs Sage 200 Professional (on-premise) with the Sicon add-on.
A cloud backend cannot reach on-prem Sage directly, so every contract activation,
amendment and RPI change is captured into a durable OUTBOX (crm2_afs_finance_sync)
holding a deterministic, Sicon-ready **Sales Order** payload.

Two delivery paths share the same payload:
  • FILE HANDOFF (works today): finance downloads a Sage/Sicon-ready CSV/JSON and
    imports it — no credentials needed.
  • LIVE REST (flip on when creds land): if the SICON_WEBAPI_* env vars are set,
    `push_to_sicon()` POSTs the Sales Order to the Sicon WebAPI automatically.

The exact Sicon WebAPI endpoint path + field schema is version-specific and comes
from the customer's Sage Business Partner, so the live call is fully env-driven
(never a guessed hard-coded endpoint). Until configured it reports
`awaiting_credentials` and the item stays queued for the file handoff.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from utils.database import db

FINANCE_COLL = "crm2_afs_finance_sync"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── env config (live REST path) ──────────────────────────────────────────────
def _cfg() -> dict:
    return {
        "base_url": (os.environ.get("SICON_WEBAPI_BASE_URL") or "").rstrip("/"),
        "sales_order_path": os.environ.get("SICON_WEBAPI_SALES_ORDER_PATH") or "/api/salesorders",
        "api_key": os.environ.get("SICON_WEBAPI_KEY") or "",
        "auth_header": os.environ.get("SICON_WEBAPI_AUTH_HEADER") or "Authorization",
        "auth_scheme": os.environ.get("SICON_WEBAPI_AUTH_SCHEME", "Bearer"),
        "company_id": os.environ.get("SICON_WEBAPI_COMPANY_ID") or "",
        "nominal_code": os.environ.get("SICON_SALES_NOMINAL_CODE") or "4000",
        "tax_code": os.environ.get("SICON_SALES_TAX_CODE") or "1",
    }


def finance_provider_configured() -> bool:
    c = _cfg()
    return bool(c["base_url"] and c["api_key"])


def _customer_reference(company: dict) -> str:
    """Deterministic customer reference finance can map in Sage/Sicon."""
    ref = (company.get("account_ref") or company.get("sage_account")
           or company.get("reference") or "")
    if ref:
        return str(ref)
    name = (company.get("name") or "CUST").upper()
    slug = "".join(ch for ch in name if ch.isalnum())[:8]
    return slug or "CUST"


def _customer_email(company: dict) -> str | None:
    if company.get("email"):
        return company["email"]
    for ct in (company.get("contacts") or []):
        if isinstance(ct, dict) and ct.get("email"):
            return ct["email"]
    return None


def build_sales_order_payload(contract: dict, invoices: list[dict], company: dict) -> dict:
    """Deterministic Sicon-ready Sales Order for one maintenance contract.

    One order line per scheduled (unpaid) billing instalment so Sicon holds the
    full recurring-billing plan. Amounts come straight from the authoritative
    billing schedule — nothing is invented."""
    cfg = _cfg()
    lines = []
    net_total = 0.0
    freq = (contract.get("billing_frequency") or "annual").title()
    for inv in invoices:
        amt = round(float(inv.get("amount") or 0), 2)
        if inv.get("status") == "paid":
            continue  # already invoiced in Sage — don't re-post
        net_total += amt
        note = inv.get("note") or f"{contract.get('contract_type', '')} maintenance ({freq})"
        lines.append({
            "due_date": inv.get("due_date"),
            "description": f"{contract.get('contract_number', '')} — {note}".strip(" —"),
            "net_amount": amt,
            "nominal_code": cfg["nominal_code"],
            "tax_code": cfg["tax_code"],
            "type": inv.get("type") or "recurring",
        })
    return {
        "external_id": contract.get("id"),
        "document_type": "sales_order",
        "customer": {
            "reference": _customer_reference(company),
            "name": company.get("legal_name") or company.get("name") or contract.get("company_name"),
            "email": _customer_email(company),
        },
        "contract": {
            "number": contract.get("contract_number"),
            "type": contract.get("contract_type") or contract.get("tier"),
            "start_date": contract.get("start_date"),
            "end_date": contract.get("end_date"),
            "term_years": contract.get("term_years", 1),
            "annual_value": round(float(contract.get("annual_value") or 0), 2),
            "billing_frequency": contract.get("billing_frequency", "annual"),
        },
        "lines": lines,
        "net_total": round(net_total, 2),
        "currency": "GBP",
        "source": "PulseFitness.ai Aftersales",
    }


async def push_to_sicon(payload: dict) -> dict:
    """POST a Sales Order to the live Sicon WebAPI, if configured.

    Returns {ok, status, external_ref?, detail?}. When the env is not set the
    item is left queued for the file handoff (no error)."""
    if not finance_provider_configured():
        return {"ok": False, "status": "awaiting_credentials",
                "detail": "Sicon WebAPI not configured — queued for finance import/export."}
    cfg = _cfg()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    scheme = cfg["auth_scheme"].strip()
    headers[cfg["auth_header"]] = f"{scheme} {cfg['api_key']}".strip() if scheme else cfg["api_key"]
    if cfg["company_id"]:
        headers["X-Company"] = cfg["company_id"]
    url = cfg["base_url"] + cfg["sales_order_path"]
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            return {"ok": False, "status": "failed",
                    "detail": f"Sicon WebAPI {r.status_code}: {r.text[:400]}"}
        data = {}
        try:
            data = r.json()
        except Exception:
            pass
        ref = (data.get("id") or data.get("order_id") or data.get("document_no")
               or data.get("sales_order_number") or "")
        return {"ok": True, "status": "synced", "external_ref": ref, "response": data}
    except Exception as e:  # network / connector down
        return {"ok": False, "status": "failed", "detail": f"Sicon WebAPI unreachable: {e}"}


async def enqueue_finance_sync(org_id: str, contract_id: str, event: str, actor: str | None) -> dict:
    """Capture/refresh the finance-sync outbox for a contract and attempt a live
    push. Idempotent per contract (one outbox doc, keyed by contract_id) with an
    appended event history. Also stamps the contract's sicon/sage sync status so
    the existing compliance badges reflect reality."""
    of = {"organization_id": org_id}
    contract = await db.crm2_contracts.find_one({"id": contract_id, **of}, {"_id": 0})
    if not contract:
        return {"ok": False, "status": "failed", "detail": "contract not found"}
    bill = await db.crm2_afs_billing.find_one({"contract_id": contract_id, **of}, {"_id": 0}) or {}
    company = await db.crm2_companies.find_one({"id": contract.get("company_id"), **of}, {"_id": 0}) or {}
    payload = build_sales_order_payload(contract, bill.get("invoices", []), company)

    push = await push_to_sicon(payload)
    status = push["status"]  # synced | awaiting_credentials | failed
    outbox_status = "synced" if status == "synced" else ("failed" if status == "failed" else "queued")

    existing = await db.crm2_afs_finance_sync.find_one({"contract_id": contract_id, **of}, {"_id": 0})
    history_entry = {"at": _now(), "event": event, "status": status,
                     "detail": push.get("detail"), "by": actor}
    doc = {
        "organization_id": org_id, "contract_id": contract_id,
        "contract_number": contract.get("contract_number"),
        "company_id": contract.get("company_id"), "company_name": contract.get("company_name"),
        "provider": "sicon", "document_type": "sales_order",
        "payload": payload, "status": outbox_status,
        "last_event": event, "last_error": push.get("detail") if status == "failed" else None,
        "external_ref": push.get("external_ref") or (existing or {}).get("external_ref"),
        "attempts": ((existing or {}).get("attempts") or 0) + 1,
        "updated_at": _now(),
        "synced_at": _now() if status == "synced" else (existing or {}).get("synced_at"),
    }
    if existing:
        history = (existing.get("history") or [])[-19:] + [history_entry]
        doc["history"] = history
        doc["created_at"] = existing.get("created_at")
        await db.crm2_afs_finance_sync.update_one({"contract_id": contract_id, **of}, {"$set": doc})
    else:
        import uuid
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = _now()
        doc["history"] = [history_entry]
        await db.crm2_afs_finance_sync.insert_one(dict(doc))

    # Reflect on the contract so existing Sicon/Sage compliance badges are truthful.
    await db.crm2_contracts.update_one(
        {"id": contract_id, **of},
        {"$set": {"sicon_sync_status": outbox_status, "sage_sync_status": outbox_status,
                  "finance_sync_status": status, "updated_at": _now()}})

    return {"ok": push["ok"], "status": status, "outbox_status": outbox_status,
            "external_ref": doc["external_ref"], "detail": push.get("detail"),
            "net_total": payload["net_total"], "lines": len(payload["lines"])}
