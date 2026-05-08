from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import uuid

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit

router = APIRouter(prefix="/crm/quotes", tags=["CRM CPQ"])


@router.get("")
async def list_quotes(status: str = "", skip: int = 0, limit: int = 50, user=Depends(get_crm_user)):
    query = {}
    if status:
        query["status"] = status
    quotes = await db.crm_quotes.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.crm_quotes.count_documents(query)
    return {"quotes": quotes, "total": total}


@router.post("")
async def create_quote(data: dict, user=Depends(get_crm_user)):
    quote_id = str(uuid.uuid4())
    quote_number = f"QT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{quote_id[:4].upper()}"

    line_items = data.get("line_items", [])
    for i, item in enumerate(line_items):
        item["id"] = str(uuid.uuid4())
        qty = float(item.get("quantity", 1))
        price = float(item.get("unit_price", 0))
        discount = float(item.get("discount_percent", 0))
        item["subtotal"] = round(qty * price * (1 - discount / 100), 2)
        line_items[i] = item

    subtotal = sum(item["subtotal"] for item in line_items)
    tax_rate = float(data.get("tax_rate", 20))
    tax_amount = round(subtotal * tax_rate / 100, 2)
    total = round(subtotal + tax_amount, 2)

    quote = {
        "id": quote_id,
        "quote_number": quote_number,
        "title": data.get("title", ""),
        "contact_id": data.get("contact_id"),
        "contact_name": data.get("contact_name", ""),
        "company_name": data.get("company_name", ""),
        "deal_id": data.get("deal_id"),
        "status": "draft",
        "line_items": line_items,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "currency": "GBP",
        "notes": data.get("notes", ""),
        "valid_until": data.get("valid_until"),
        "accepted_at": None,
        "accepted_by": None,
        "payment_link": None,
        "created_by": user["id"],
        "created_by_name": user["full_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.crm_quotes.insert_one(quote)
    await log_audit(user, "quote", quote_id, "created")
    quote.pop("_id", None)
    return quote


@router.get("/{quote_id}")
async def get_quote(quote_id: str, user=Depends(get_crm_user)):
    quote = await db.crm_quotes.find_one({"id": quote_id}, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


@router.put("/{quote_id}")
async def update_quote(quote_id: str, data: dict, user=Depends(get_crm_user)):
    existing = await db.crm_quotes.find_one({"id": quote_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Quote not found")

    updates = {}
    if "line_items" in data:
        line_items = data["line_items"]
        for i, item in enumerate(line_items):
            if not item.get("id"):
                item["id"] = str(uuid.uuid4())
            qty = float(item.get("quantity", 1))
            price = float(item.get("unit_price", 0))
            discount = float(item.get("discount_percent", 0))
            item["subtotal"] = round(qty * price * (1 - discount / 100), 2)
            line_items[i] = item
        updates["line_items"] = line_items
        subtotal = sum(item["subtotal"] for item in line_items)
        tax_rate = float(data.get("tax_rate", existing.get("tax_rate", 20)))
        updates["subtotal"] = subtotal
        updates["tax_rate"] = tax_rate
        updates["tax_amount"] = round(subtotal * tax_rate / 100, 2)
        updates["total"] = round(subtotal + updates["tax_amount"], 2)

    for field in ("title", "contact_name", "company_name", "notes", "valid_until", "status"):
        if field in data:
            updates[field] = data[field]

    if "status" in data and data["status"] == "accepted":
        updates["accepted_at"] = datetime.now(timezone.utc).isoformat()

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.crm_quotes.update_one({"id": quote_id}, {"$set": updates})
    await log_audit(user, "quote", quote_id, "updated")
    return {"status": "updated"}


@router.delete("/{quote_id}")
async def delete_quote(quote_id: str, user=Depends(get_crm_user)):
    result = await db.crm_quotes.delete_one({"id": quote_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Quote not found")
    await log_audit(user, "quote", quote_id, "deleted")
    return {"status": "deleted"}


@router.post("/{quote_id}/send")
async def send_quote(quote_id: str, user=Depends(get_crm_user)):
    """Mark quote as sent."""
    result = await db.crm_quotes.update_one(
        {"id": quote_id},
        {"$set": {"status": "sent", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Quote not found")
    await log_audit(user, "quote", quote_id, "sent")
    return {"status": "sent"}


@router.post("/{quote_id}/accept")
async def accept_quote(quote_id: str, data: dict, user=Depends(get_crm_user)):
    """Accept quote with digital signature."""
    accepted_by = data.get("accepted_by", "")
    result = await db.crm_quotes.update_one(
        {"id": quote_id},
        {"$set": {
            "status": "accepted",
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "accepted_by": accepted_by,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Quote not found")
    await log_audit(user, "quote", quote_id, "accepted", {"accepted_by": accepted_by})
    return {"status": "accepted"}


@router.post("/{quote_id}/create-payment-link")
async def create_payment_link(quote_id: str, user=Depends(get_crm_user)):
    """Create a Stripe payment link for this quote."""
    import os
    quote = await db.crm_quotes.find_one({"id": quote_id}, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    try:
        import stripe
        stripe.api_key = stripe_key

        # Create a payment link via Stripe Checkout
        line_items_stripe = []
        for item in quote.get("line_items", []):
            line_items_stripe.append({
                "price_data": {
                    "currency": "gbp",
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
            {"$set": {"payment_link": session.url, "stripe_session_id": session.id, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

        return {"payment_link": session.url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe error: {str(e)}")
