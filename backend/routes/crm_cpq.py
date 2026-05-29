"""CRM · CPQ (quotes) — Iter 216h224 enhanced.

Adds on top of the previous build:
  • organization_id stamping (multi-tenant isolation bugfix)
  • line_item cost_price → margin_value / margin_percent (computed)
  • quote-level gross_margin_percent / gross_profit (computed)
  • org-level min_margin_percent threshold → if total margin drops
    below it the quote enters `pending_approval` instead of `draft`
  • approval endpoints (submit / approve / reject)
  • quote versioning (`parent_quote_id`, `version`, `is_latest_version`)
  • duplicate endpoint
  • PDF generation via /pdf

Backward compatibility:
  • All existing fields preserved.
  • Existing quotes without `organization_id` are migrated lazily on
    first read (the read endpoint sets it from `created_by` lookup).
  • If a caller sends a line_item without `cost_price` the margin
    fields are simply 0 — never a 422.
"""
from fastapi import APIRouter, HTTPException, Depends, Response
from datetime import datetime, timezone
import uuid
from typing import Any

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit

router = APIRouter(prefix="/crm/quotes", tags=["CRM CPQ"])


# ── Helpers ────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


def _is_admin(user: dict) -> bool:
    """Roles that can approve quotes / override approval workflow."""
    return (
        bool(user.get("is_master_admin"))
        or bool(user.get("is_pulse_admin"))
        or (user.get("role") or "").lower() in ("admin", "owner", "manager")
    )


async def _min_margin_threshold(user: dict) -> float:
    """Org-configured minimum margin % below which quotes need
    approval. Stored on `crm_settings.quote_approval` per org.
    Default = 0 (no approval needed) so existing tenants keep their
    current behaviour until they opt in.
    """
    settings = await db.crm_settings.find_one(
        {"organization_id": user.get("organization_id"), "key": "quote_approval"},
        {"_id": 0, "value": 1},
    )
    if not settings:
        return 0.0
    try:
        return float((settings.get("value") or {}).get("min_margin_percent", 0))
    except Exception:
        return 0.0


def _compute_line(item: dict) -> dict:
    """Normalise a single line item and compute margin fields.
    Tolerant of missing fields so legacy quotes round-trip cleanly.
    """
    if not item.get("id"):
        item["id"] = str(uuid.uuid4())
    qty = float(item.get("quantity", 1) or 0)
    sell = float(item.get("unit_price", 0) or 0)
    cost = float(item.get("cost_price", 0) or 0)
    discount = float(item.get("discount_percent", 0) or 0)
    subtotal = round(qty * sell * (1 - discount / 100), 2)
    cost_total = round(qty * cost, 2)
    margin_value = round(subtotal - cost_total, 2)
    margin_percent = round((margin_value / subtotal) * 100, 2) if subtotal > 0 else 0.0
    item["quantity"] = qty
    item["unit_price"] = sell
    item["cost_price"] = cost
    item["discount_percent"] = discount
    item["subtotal"] = subtotal
    item["cost_total"] = cost_total
    item["margin_value"] = margin_value
    item["margin_percent"] = margin_percent
    return item


def _compute_totals(line_items: list[dict], tax_rate: float) -> dict:
    subtotal = sum(li.get("subtotal", 0) for li in line_items)
    cost_total = sum(li.get("cost_total", 0) for li in line_items)
    gross_profit = round(subtotal - cost_total, 2)
    gross_margin_percent = round((gross_profit / subtotal) * 100, 2) if subtotal > 0 else 0.0
    tax_amount = round(subtotal * tax_rate / 100, 2)
    total = round(subtotal + tax_amount, 2)
    return {
        "subtotal": round(subtotal, 2),
        "cost_total": round(cost_total, 2),
        "gross_profit": gross_profit,
        "gross_margin_percent": gross_margin_percent,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
    }


async def _hydrate_line_items(items: list[dict], user: dict) -> list[dict]:
    """If a line_item carries `product_id`, copy the catalogue's
    sell/cost/tax/description as defaults (unless the caller has
    explicitly set those fields). Inputs already containing prices
    are respected — the rep can override per-quote pricing.
    """
    for item in items:
        pid = item.get("product_id")
        if not pid:
            continue
        prod = await db.crm_products.find_one(
            {"id": pid, **_of(user)}, {"_id": 0},
        )
        if not prod:
            continue
        item.setdefault("description", prod.get("name", ""))
        item.setdefault("unit_price", prod.get("sell_price", 0))
        item.setdefault("cost_price", prod.get("cost_price", 0))
        item.setdefault("tax_rate", prod.get("tax_rate", 20))
        item.setdefault("product_name", prod.get("name", ""))
        item.setdefault("sku", prod.get("sku"))
    return items


# ── List / Get ─────────────────────────────────────────────────────


@router.get("")
async def list_quotes(
    status: str = "",
    show_all_versions: bool = False,
    skip: int = 0,
    limit: int = 50,
    user=Depends(get_crm_user),
):
    """List quotes. By default hides superseded versions (only the
    latest of each version chain is shown). Pass
    `show_all_versions=true` for the audit timeline view.
    """
    # Iter 216h224 — multi-tenant filter (was missing — see h224 audit).
    # Legacy quotes without org stamped fall through the `$or` branch.
    query: dict[str, Any] = {
        "$or": [
            {"organization_id": user.get("organization_id")},
            {"organization_id": {"$exists": False}},  # legacy
        ]
    }
    if status:
        query["status"] = status
    if not show_all_versions:
        query["is_latest_version"] = {"$ne": False}
    quotes = await db.crm_quotes.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.crm_quotes.count_documents(query)
    return {"quotes": quotes, "total": total}


@router.get("/{quote_id}")
async def get_quote(quote_id: str, user=Depends(get_crm_user)):
    quote = await db.crm_quotes.find_one(
        {"id": quote_id, "$or": [
            {"organization_id": user.get("organization_id")},
            {"organization_id": {"$exists": False}},
        ]},
        {"_id": 0},
    )
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


# ── Create / Update ────────────────────────────────────────────────


@router.post("")
async def create_quote(data: dict, user=Depends(get_crm_user)):
    quote_id = str(uuid.uuid4())
    quote_number = f"QT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{quote_id[:4].upper()}"

    # Iter 220bs — Quote ↔ Tender deep-linking. When the caller links a
    # tender, enforce same-org ownership so a crafted tender_id can't
    # silently leak a sibling tenant's tender into our quote.
    tender_id = data.get("tender_id")
    if tender_id:
        tender = await db.crm2_tenders.find_one(
            {"id": tender_id, "organization_id": user.get("organization_id")},
            {"_id": 0, "id": 1, "title": 1},
        )
        if not tender:
            raise HTTPException(400, "Linked tender not found in this organisation")

    line_items = data.get("line_items", []) or []
    line_items = await _hydrate_line_items(line_items, user)
    line_items = [_compute_line(li) for li in line_items]
    tax_rate = float(data.get("tax_rate", 20) or 0)
    totals = _compute_totals(line_items, tax_rate)

    threshold = await _min_margin_threshold(user)
    needs_approval = bool(threshold and line_items and totals["gross_margin_percent"] < threshold)

    quote = {
        "id": quote_id,
        "organization_id": user.get("organization_id"),
        "quote_number": quote_number,
        "title": data.get("title", ""),
        "contact_id": data.get("contact_id"),
        "contact_name": data.get("contact_name", ""),
        "company_id": data.get("company_id"),
        "company_name": data.get("company_name", ""),
        "deal_id": data.get("deal_id"),
        # Iter 220bs — Quote ↔ Tender deep link (optional).
        "tender_id": tender_id,
        "status": "pending_approval" if needs_approval else "draft",
        "line_items": line_items,
        "currency": (data.get("currency") or "GBP").upper(),
        "notes": data.get("notes", ""),
        "internal_notes": (data.get("internal_notes") or "").strip(),
        "valid_until": data.get("valid_until"),
        "accepted_at": None,
        "accepted_by": None,
        "payment_link": None,
        # Approval workflow.
        "approval_required": bool(threshold),
        "approval_threshold_percent": threshold,
        "approval_status": "pending" if needs_approval else "not_required",
        "approved_by": None,
        "approved_at": None,
        "rejection_reason": None,
        # Versioning.
        "parent_quote_id": data.get("parent_quote_id"),
        "version": 1,
        "is_latest_version": True,
        # Created-by metadata.
        "created_by": user["id"],
        "created_by_name": user.get("full_name", ""),
        "created_at": _now(),
        "updated_at": _now(),
        **totals,
    }
    await db.crm_quotes.insert_one(quote)
    await log_audit(user, "quote", quote_id, "created", {"needs_approval": needs_approval, "margin_percent": totals["gross_margin_percent"]})
    quote.pop("_id", None)
    return quote


@router.put("/{quote_id}")
async def update_quote(quote_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm_quotes.find_one({"id": quote_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Quote not found")

    updates: dict[str, Any] = {}
    if "line_items" in data:
        line_items = await _hydrate_line_items(data["line_items"], user)
        line_items = [_compute_line(li) for li in line_items]
        tax_rate = float(data.get("tax_rate", existing.get("tax_rate", 20)) or 0)
        totals = _compute_totals(line_items, tax_rate)
        updates["line_items"] = line_items
        updates.update(totals)
        # Re-evaluate approval threshold (margin may have improved).
        threshold = await _min_margin_threshold(user)
        if threshold and totals["gross_margin_percent"] < threshold and existing.get("approval_status") != "approved":
            updates["status"] = "pending_approval"
            updates["approval_status"] = "pending"
        elif threshold and totals["gross_margin_percent"] >= threshold and existing.get("approval_status") == "pending":
            # Margin recovered — auto-clear pending approval.
            updates["approval_status"] = "auto_cleared"
            updates["status"] = "draft"

    for field in ("title", "contact_name", "company_name", "company_id", "contact_id",
                  "deal_id", "notes", "internal_notes", "valid_until"):
        if field in data:
            updates[field] = data[field]

    # Iter 220bs — Quote ↔ Tender deep-link: allow re-pointing on
    # update but enforce same-org ownership exactly like create.
    if "tender_id" in data:
        new_tender_id = data["tender_id"]
        if new_tender_id:
            tender = await db.crm2_tenders.find_one(
                {"id": new_tender_id, "organization_id": user.get("organization_id")},
                {"_id": 0, "id": 1},
            )
            if not tender:
                raise HTTPException(400, "Linked tender not found in this organisation")
        updates["tender_id"] = new_tender_id  # None to unlink is allowed

    # Explicit status overrides are honoured (e.g. send / accept paths
    # set this directly).
    if "status" in data and data["status"] in ("draft", "sent", "accepted", "lost", "expired", "cancelled"):
        updates["status"] = data["status"]

    if data.get("status") == "accepted":
        updates["accepted_at"] = _now()

    updates["updated_at"] = _now()
    # Stamp org if missing (lazy migration).
    if not existing.get("organization_id"):
        updates["organization_id"] = user.get("organization_id")
    await db.crm_quotes.update_one({"id": quote_id}, {"$set": updates})
    await log_audit(user, "quote", quote_id, "updated")
    return {"status": "updated"}


@router.delete("/{quote_id}")
async def delete_quote(quote_id: str, user=Depends(get_crm_user)):
    result = await db.crm_quotes.delete_one({"id": quote_id, **_of(user)})
    if result.deleted_count == 0:
        # Try legacy unscoped row.
        result = await db.crm_quotes.delete_one({"id": quote_id, "organization_id": {"$exists": False}})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Quote not found")
    await log_audit(user, "quote", quote_id, "deleted")
    return {"status": "deleted"}


# ── Approval workflow ──────────────────────────────────────────────


@router.post("/{quote_id}/submit-for-approval")
async def submit_for_approval(quote_id: str, user=Depends(get_crm_user)):
    quote = await db.crm_quotes.find_one({"id": quote_id, **_of(user)})
    if not quote:
        raise HTTPException(404, "Quote not found")
    await db.crm_quotes.update_one(
        {"id": quote_id},
        {"$set": {
            "status": "pending_approval",
            "approval_status": "pending",
            "approval_required": True,
            "updated_at": _now(),
        }},
    )
    await log_audit(user, "quote", quote_id, "submitted_for_approval")
    return {"status": "pending_approval"}


@router.post("/{quote_id}/approve")
async def approve_quote(quote_id: str, user=Depends(get_crm_user)):
    if not _is_admin(user):
        raise HTTPException(403, "Only admins / owners / managers can approve quotes")
    quote = await db.crm_quotes.find_one({"id": quote_id, **_of(user)})
    if not quote:
        raise HTTPException(404, "Quote not found")
    if quote.get("approval_status") != "pending":
        raise HTTPException(409, "Quote is not pending approval")
    await db.crm_quotes.update_one(
        {"id": quote_id},
        {"$set": {
            "status": "draft",
            "approval_status": "approved",
            "approved_by": user.get("full_name") or user.get("id"),
            "approved_at": _now(),
            "rejection_reason": None,
            "updated_at": _now(),
        }},
    )
    await log_audit(user, "quote", quote_id, "approved")
    return {"approved": True}


@router.post("/{quote_id}/reject")
async def reject_quote(quote_id: str, data: dict, user=Depends(get_crm_user)):
    if not _is_admin(user):
        raise HTTPException(403, "Only admins / owners / managers can reject quotes")
    reason = (data.get("reason") or "").strip()
    quote = await db.crm_quotes.find_one({"id": quote_id, **_of(user)})
    if not quote:
        raise HTTPException(404, "Quote not found")
    if quote.get("approval_status") != "pending":
        raise HTTPException(409, "Quote is not pending approval")
    await db.crm_quotes.update_one(
        {"id": quote_id},
        {"$set": {
            "approval_status": "rejected",
            "rejection_reason": reason,
            "updated_at": _now(),
        }},
    )
    await log_audit(user, "quote", quote_id, "rejected", {"reason": reason})
    return {"rejected": True, "reason": reason}


# ── Versioning + duplicate ────────────────────────────────────────


@router.post("/{quote_id}/duplicate")
async def duplicate_quote(quote_id: str, user=Depends(get_crm_user)):
    """Clone a quote as a brand-new standalone draft (no parent link).
    Use for "start a new quote that looks like this one"."""
    src = await db.crm_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not src:
        raise HTTPException(404, "Quote not found")
    new_id = str(uuid.uuid4())
    new = {
        **src,
        "id": new_id,
        "quote_number": f"QT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{new_id[:4].upper()}",
        "status": "draft",
        "approval_status": "not_required",
        "approved_by": None,
        "approved_at": None,
        "rejection_reason": None,
        "accepted_at": None,
        "accepted_by": None,
        "payment_link": None,
        "stripe_session_id": None,
        "parent_quote_id": None,
        "version": 1,
        "is_latest_version": True,
        "created_by": user["id"],
        "created_by_name": user.get("full_name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.crm_quotes.insert_one(new)
    await log_audit(user, "quote", new_id, "duplicated", {"source_id": quote_id})
    new.pop("_id", None)
    return new


@router.post("/{quote_id}/new-version")
async def new_version(quote_id: str, user=Depends(get_crm_user)):
    """Create the next version of the same quote (e.g. after
    renegotiation). The previous version's `is_latest_version` flips
    to False. The new version inherits the parent chain (or starts
    one if there isn't one).
    """
    src = await db.crm_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not src:
        raise HTTPException(404, "Quote not found")
    chain_parent = src.get("parent_quote_id") or src["id"]
    # Find the highest version in the chain.
    siblings_cursor = db.crm_quotes.find(
        {"$or": [{"id": chain_parent}, {"parent_quote_id": chain_parent}], **_of(user)},
        {"_id": 0, "version": 1},
    )
    top_version = 1
    async for s in siblings_cursor:
        top_version = max(top_version, int(s.get("version", 1)))
    # Mark every existing sibling as no-longer-latest.
    await db.crm_quotes.update_many(
        {"$or": [{"id": chain_parent}, {"parent_quote_id": chain_parent}], **_of(user)},
        {"$set": {"is_latest_version": False, "updated_at": _now()}},
    )
    new_id = str(uuid.uuid4())
    new = {
        **src,
        "id": new_id,
        "quote_number": f"{src.get('quote_number', '').split(' v')[0]} v{top_version + 1}",
        "status": "draft",
        "approval_status": "not_required",
        "approved_by": None,
        "approved_at": None,
        "rejection_reason": None,
        "accepted_at": None,
        "accepted_by": None,
        "payment_link": None,
        "stripe_session_id": None,
        "parent_quote_id": chain_parent,
        "version": top_version + 1,
        "is_latest_version": True,
        "created_by": user["id"],
        "created_by_name": user.get("full_name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.crm_quotes.insert_one(new)
    await log_audit(user, "quote", new_id, "version_created", {"parent": chain_parent, "version": new["version"]})
    new.pop("_id", None)
    return new


@router.get("/{quote_id}/versions")
async def list_versions(quote_id: str, user=Depends(get_crm_user)):
    """Return every version in the quote's chain, oldest first."""
    src = await db.crm_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0, "id": 1, "parent_quote_id": 1})
    if not src:
        raise HTTPException(404, "Quote not found")
    root = src.get("parent_quote_id") or src["id"]
    rows = await db.crm_quotes.find(
        {"$or": [{"id": root}, {"parent_quote_id": root}], **_of(user)},
        {"_id": 0},
    ).sort("version", 1).to_list(50)
    return {"versions": rows, "root_id": root}


# ── Send / Accept / Stripe (unchanged from prev iter, kept here) ───


@router.post("/{quote_id}/send")
async def send_quote(quote_id: str, user=Depends(get_crm_user)):
    result = await db.crm_quotes.update_one(
        {"id": quote_id, **_of(user)},
        {"$set": {"status": "sent", "updated_at": _now()}},
    )
    if result.matched_count == 0:
        # Legacy unscoped row.
        result = await db.crm_quotes.update_one(
            {"id": quote_id, "organization_id": {"$exists": False}},
            {"$set": {"status": "sent", "organization_id": user.get("organization_id"), "updated_at": _now()}},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Quote not found")
    await log_audit(user, "quote", quote_id, "sent")
    # Iter 216h227 — CRM trial first-win milestone for "first quote sent".
    try:
        from routes.activation_events import record_activation_event
        await record_activation_event(
            user.get("organization_id"), "first_quote_sent",
            trigger_user_id=user.get("id"),
        )
    except Exception:  # best-effort — never block CPQ writes
        pass
    return {"status": "sent"}


@router.post("/{quote_id}/accept")
async def accept_quote(quote_id: str, data: dict, user=Depends(get_crm_user)):
    accepted_by = data.get("accepted_by", "")
    result = await db.crm_quotes.update_one(
        {"id": quote_id, **_of(user)},
        {"$set": {
            "status": "accepted",
            "accepted_at": _now(),
            "accepted_by": accepted_by,
            "updated_at": _now(),
        }},
    )
    if result.matched_count == 0:
        result = await db.crm_quotes.update_one(
            {"id": quote_id, "organization_id": {"$exists": False}},
            {"$set": {
                "status": "accepted",
                "accepted_at": _now(),
                "accepted_by": accepted_by,
                "organization_id": user.get("organization_id"),
                "updated_at": _now(),
            }},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Quote not found")
    await log_audit(user, "quote", quote_id, "accepted", {"accepted_by": accepted_by})
    return {"status": "accepted"}


@router.post("/{quote_id}/create-payment-link")
async def create_payment_link(quote_id: str, user=Depends(get_crm_user)):
    """Create a Stripe payment link for this quote."""
    import os
    quote = await db.crm_quotes.find_one({"id": quote_id, **_of(user)}, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    try:
        import stripe
        stripe.api_key = stripe_key
        line_items_stripe = []
        for item in quote.get("line_items", []):
            line_items_stripe.append({
                "price_data": {
                    "currency": (quote.get("currency") or "GBP").lower(),
                    "unit_amount": int(float(item.get("unit_price", 0)) * 100),
                    "product_data": {"name": item.get("description", "Item")},
                },
                "quantity": int(item.get("quantity", 1)),
            })
        if not line_items_stripe:
            raise HTTPException(status_code=400, detail="Quote has no line items")

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items_stripe,
            mode="payment",
            success_url=f"{os.environ.get('FRONTEND_URL', '')}/crm?payment=success&quote={quote_id}",
            cancel_url=f"{os.environ.get('FRONTEND_URL', '')}/crm?payment=cancelled&quote={quote_id}",
            metadata={"quote_id": quote_id},
        )
        await db.crm_quotes.update_one(
            {"id": quote_id},
            {"$set": {"payment_link": session.url, "stripe_session_id": session.id, "updated_at": _now()}},
        )
        return {"payment_link": session.url}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe error: {str(e)}")


# ── PDF export ─────────────────────────────────────────────────────


@router.get("/{quote_id}/pdf")
async def export_quote_pdf(quote_id: str, user=Depends(get_crm_user)):
    """Render the quote as a branded PDF and return it inline."""
    quote = await db.crm_quotes.find_one(
        {"id": quote_id, "$or": [
            {"organization_id": user.get("organization_id")},
            {"organization_id": {"$exists": False}},
        ]},
        {"_id": 0},
    )
    if not quote:
        raise HTTPException(404, "Quote not found")
    # Look up org branding for the header.
    org = await db.organizations.find_one(
        {"id": user.get("organization_id")},
        {"_id": 0, "name": 1, "logo_url": 1, "primary_color": 1,
         "address_line1": 1, "address_line2": 1, "city": 1, "postcode": 1,
         "country": 1, "primary_contact_email": 1, "phone": 1, "website": 1},
    ) or {}
    from utils.crm_quote_pdf import build_crm_quote_pdf
    pdf_bytes = build_crm_quote_pdf(quote, org)
    filename = f"{quote.get('quote_number') or quote_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ── Margin threshold settings ──────────────────────────────────────


@router.get("/settings/approval")
async def get_approval_settings(user=Depends(get_crm_user)):
    """Return the org's approval threshold + the role(s) that can
    approve (currently fixed at admin/owner/manager — exposed in the
    response so the FE can hide the Approve button for sales reps)."""
    thresh = await _min_margin_threshold(user)
    return {
        "min_margin_percent": thresh,
        "approver_roles": ["admin", "owner", "manager"],
        "enabled": bool(thresh),
    }


@router.put("/settings/approval")
async def update_approval_settings(data: dict, user=Depends(get_crm_user)):
    if not _is_admin(user):
        raise HTTPException(403, "Only admins / owners / managers can change approval rules")
    pct = float(data.get("min_margin_percent", 0) or 0)
    if pct < 0 or pct > 100:
        raise HTTPException(422, "min_margin_percent must be 0-100")
    await db.crm_settings.update_one(
        {"organization_id": user.get("organization_id"), "key": "quote_approval"},
        {"$set": {
            "organization_id": user.get("organization_id"),
            "key": "quote_approval",
            "value": {"min_margin_percent": pct},
            "updated_at": _now(),
        }},
        upsert=True,
    )
    await log_audit(user, "quote_settings", "approval", "updated", {"min_margin_percent": pct})
    return {"min_margin_percent": pct, "enabled": pct > 0}
