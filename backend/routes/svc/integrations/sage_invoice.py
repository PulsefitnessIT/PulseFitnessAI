"""
Pulse Fitness Service Operations — Sage 200 invoice sync stub.

Iter 215dp.

Sage is the financial master (see SVC_FIELD_MAPPING.md §1). Phase 1
emits a draft invoice payload to `svc_sage_invoice_outbox` whenever a
case transitions to `closed` AND `cover_type=chargeable`. A worker
(TODO) drains the outbox and posts to Sage 200's invoice API.

Field mapping:
    Pulse Fitness case → Sage `SLInvoice`:
      SLCustomerAccountID  ← (CRM) `Company.sage_customer_id`
      InvoiceDate          ← case.closed_at (date part)
      Reference            ← case.reference
      Lines[].NominalCode  ← COVER_NOMINAL[cover_type]
      Lines[].Description  ← case.title
      Lines[].UnitNetAmount← computed from labour + parts (Phase 6)
"""
from datetime import datetime, timezone
import logging
import uuid

from utils.database import db
from routes.svc.integrations.sicon_sync import COVER_NOMINAL

logger = logging.getLogger(__name__)


def _to_sage_invoice(case: dict, *, sage_customer_id: str | None = None,
                     quote: dict | None = None) -> dict:
    """Translate a closed chargeable case to a Sage `SLInvoice` draft payload.

    If a `quote` is provided, its lines drive the invoice. Otherwise we
    emit a single placeholder line (Phase 1 behaviour) so finance can
    see the case landed but knows it needs a quote attached.
    """
    nominal_default = COVER_NOMINAL.get(case.get("cover_type"), "4010")
    if quote and quote.get("lines"):
        lines = [
            {
                "NominalCode": (line.get("nominal_code") or nominal_default),
                "Description": (line.get("description") or "Service work")[:200],
                "Quantity": float(line.get("qty") or 0),
                "UnitNetAmount": float(line.get("unit_amount") or 0),
                "TaxCode": (line.get("tax_code") or "T1"),
                "StockCode": (line.get("stock_code") or line.get("part_sku") or ""),
            }
            for line in (quote.get("lines") or [])
        ]
    else:
        lines = [
            {
                "NominalCode": nominal_default,
                "Description": case.get("title") or "Service work",
                "Quantity": 1,
                "UnitNetAmount": 0.0,
                "TaxCode": "T1",
            },
        ]
    return {
        "OurReference": case.get("id"),
        "SLCustomerAccountID": sage_customer_id or "",
        "InvoiceDate": (case.get("closed_at") or datetime.now(timezone.utc).isoformat())[:10],
        "Reference": case.get("reference"),
        "YourReference": case.get("customer_name") or "",
        "Notes": (case.get("title") or "")[:200],
        "Lines": lines,
        "QuoteReference": (quote or {}).get("reference") or "",
        "QuoteTotal": float((quote or {}).get("total") or 0),
    }


async def enqueue_invoice_for_case(case: dict, *, sage_customer_id: str | None = None,
                                   quote: dict | None = None,
                                   status: str = "pending") -> None:
    """Drop a draft Sage invoice on the outbox (idempotent per case).

    Phase 6 callers pass the approved `quote` doc so the invoice has
    real line values. They also bump status from 'pending' to 'ready'
    via the finalise endpoint when the operator commits.
    """
    if (case.get("cover_type") or "").lower() != "chargeable":
        return
    payload = _to_sage_invoice(case, sage_customer_id=sage_customer_id, quote=quote)
    try:
        await db.svc_sage_invoice_outbox.update_one(
            {"organization_id": case["organization_id"], "case_id": case["id"]},
            {
                "$set": {
                    "organization_id": case["organization_id"],
                    "case_id": case["id"],
                    "case_reference": case.get("reference"),
                    "quote_id": (quote or {}).get("id") or "",
                    "payload": payload,
                    "status": status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "attempts": 0,
                },
            },
            upsert=True,
        )
    except Exception as e:
        logger.warning("sage enqueue_invoice failed: %s", e)


# ─────────────────────────────────────────────────────────────────
# SLQuote — drafted at intake-time for chargeable cases (iter 215ed)
# ─────────────────────────────────────────────────────────────────

_DEFAULT_LABOUR_RATE = 65.0  # £/hr placeholder, finance to confirm
_DEFAULT_CALLOUT = 75.0      # £ placeholder for one-off callout

def _to_sage_quote(case: dict, *, sage_customer_id: str | None = None,
                    customer_po_number: str = "") -> dict:
    """Translate an intake-time chargeable case to a Sage `SLQuote` draft.

    Lines are seeded with a callout + placeholder labour estimate so the
    customer sees a coherent quote. The Service Desk operator can refine
    the lines via `/api/svc/billing/{case_id}/quote/auto-fill` later — at
    that point the regular svc_quotes flow takes over.
    """
    nominal_default = COVER_NOMINAL.get(case.get("cover_type"), "4010")
    lines = [
        {
            "NominalCode": nominal_default,
            "Description": f"Engineer callout — {case.get('asset_name') or case.get('title') or 'service work'}"[:200],
            "Quantity": 1,
            "UnitNetAmount": _DEFAULT_CALLOUT,
            "TaxCode": "T1",
        },
        {
            "NominalCode": nominal_default,
            "Description": "Labour — estimated 1h",
            "Quantity": 1,
            "UnitNetAmount": _DEFAULT_LABOUR_RATE,
            "TaxCode": "T1",
        },
    ]
    return {
        "OurReference": case.get("id"),
        "SLCustomerAccountID": sage_customer_id or "",
        "QuoteDate": (case.get("created_at") or datetime.now(timezone.utc).isoformat())[:10],
        "Reference": case.get("reference"),
        "YourReference": (customer_po_number or case.get("customer_name") or "")[:40],
        "Notes": ((case.get("description") or case.get("title") or "")[:300]),
        "CustomerPONumber": customer_po_number or "",
        "Lines": lines,
        "Status": "draft",
    }


async def enqueue_quote_for_case(case: dict, *, sage_customer_id: str | None = None,
                                   customer_po_number: str = "") -> dict | None:
    """Drop a draft Sage SLQuote on `svc_sage_quote_outbox` (idempotent per case).

    Triggered at intake when the operator marks a chargeable case as
    `quote_required=true`. Returns the outbox row dict (without `_id`)
    so the API caller can echo it back to the operator UI for an
    immediate "Quote drafted" confirmation toast.
    """
    if (case.get("cover_type") or "").lower() != "chargeable":
        return None
    payload = _to_sage_quote(case, sage_customer_id=sage_customer_id,
                              customer_po_number=customer_po_number)
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.svc_sage_quote_outbox.update_one(
            {"organization_id": case["organization_id"], "case_id": case["id"]},
            {
                "$set": {
                    "organization_id": case["organization_id"],
                    "case_id": case["id"],
                    "case_reference": case.get("reference"),
                    "customer_po_number": customer_po_number or "",
                    "payload": payload,
                    "status": "pending",
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "created_at": now,
                    "attempts": 0,
                },
            },
            upsert=True,
        )
        row = await db.svc_sage_quote_outbox.find_one(
            {"organization_id": case["organization_id"], "case_id": case["id"]},
            {"_id": 0},
        )
        return row
    except Exception as e:
        logger.warning("sage enqueue_quote failed: %s", e)
        return None


__all__ = ["enqueue_invoice_for_case", "enqueue_quote_for_case", "_to_sage_invoice", "_to_sage_quote"]
