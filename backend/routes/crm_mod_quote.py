"""MOD Automatic Quote Writer.

Generates quotes for MOD PTE (Physical Training Equipment) Service & Repair on
the Pulse Fitness paperwork, driven by the contracted Schedule of Rates (SOR)
and linked to the MOD equipment lists.

- Type A = all-inclusive 12-month service (per item / year, UK).
- Type B = ad-hoc call-out service & repair (per visit + £80 UK call-out).
- Type C / Repairs / Refurbishment = POA (custom price line required).

Contracted prices (Type A/B) are fixed and cannot be edited per-quote. A Type A
quote also spins up a MOD service contract that feeds MOD Service Operations.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit
from routes.crm_cpq import _now
from utils.mod_sor_data import build_seed_rate_card, price_for, match_equipment

router = APIRouter(prefix="/crm/mod-quote", tags=["CRM MOD Quote"])

_EDITABLE_PRICE_FIELDS = [
    "type_a_price", "type_b_price",
    "type_a_price_y2", "type_a_price_y3", "type_a_price_y4",
    "type_b_price_y2", "type_b_price_y3", "type_b_price_y4",
]

CONTRACT_LABELS = {
    "A": "Type A — All-Inclusive 12-Month Service, Repair & Maintenance (UK)",
    "B": "Type B — Ad-hoc Service & Repair Call-Out (UK)",
    "C": "Type C — Overseas Service / Repairs / Refurbishment (POA)",
}


def _is_admin(user: dict) -> bool:
    return user.get("role") in ("owner", "admin") or user.get("is_master_admin")


async def _ensure_rate_card() -> None:
    if await db.mod_sor_rate_card.count_documents({}) == 0:
        await db.mod_sor_rate_card.insert_many(build_seed_rate_card())


async def _rate_card_list() -> list[dict]:
    await _ensure_rate_card()
    cur = db.mod_sor_rate_card.find({}, {"_id": 0}).sort("sort_order", 1)
    return await cur.to_list(length=500)


# ── Rate card ──────────────────────────────────────────────────────

@router.get("/rate-card")
async def get_rate_card(user=Depends(get_crm_user)):
    return {"items": await _rate_card_list()}


@router.put("/rate-card/{item_id}")
async def update_rate_card_item(item_id: str, data: dict, user=Depends(get_crm_user)):
    if not _is_admin(user):
        raise HTTPException(403, "Only CRM admins can edit the SOR rate card")
    entry = await db.mod_sor_rate_card.find_one({"id": item_id}, {"_id": 0})
    if not entry:
        raise HTTPException(404, "Rate card line not found")
    update = {}
    for f in _EDITABLE_PRICE_FIELDS:
        if f in data:
            v = data[f]
            update[f] = (round(float(v), 2) if v not in (None, "") else None)
    if not update:
        raise HTTPException(400, "No editable price fields supplied")
    update["updated_at"] = _now()
    update["updated_by"] = user.get("full_name") or user.get("id")
    await db.mod_sor_rate_card.update_one({"id": item_id}, {"$set": update})
    await log_audit(user, "mod_rate_card", item_id, "updated", update)
    return await db.mod_sor_rate_card.find_one({"id": item_id}, {"_id": 0})


@router.post("/rate-card/reseed")
async def reseed_rate_card(user=Depends(get_crm_user)):
    """Reset the rate card to the canonical SOR (loses manual edits)."""
    if not _is_admin(user):
        raise HTTPException(403, "Only CRM admins can reseed the SOR rate card")
    await db.mod_sor_rate_card.delete_many({})
    await db.mod_sor_rate_card.insert_many(build_seed_rate_card())
    await log_audit(user, "mod_rate_card", "all", "reseeded", {})
    return {"items": await _rate_card_list()}


# ── MOD sites & equipment mapping ──────────────────────────────────

@router.get("/mod-sites")
async def list_mod_sites(user=Depends(get_crm_user)):
    """List MOD sites/estates that hold equipment we can quote against."""
    sites = []
    cur = db.organizations.find(
        {"account_type": {"$in": ["mod_site", "mod_org"]}},
        {"_id": 0, "id": 1, "name": 1, "account_type": 1, "mod_root_id": 1},
    ).sort("name", 1)
    for org in await cur.to_list(length=500):
        count = await db.equipment.count_documents({"organization_id": org["id"]})
        sites.append({
            "id": org["id"], "name": org["name"],
            "account_type": org.get("account_type"),
            "equipment_count": count,
        })
    return {"sites": sites}


@router.get("/equipment")
async def get_site_equipment(site_id: str, contract_type: str = "A", year: int = 1,
                             user=Depends(get_crm_user)):
    """Return a site's equipment auto-mapped onto the SOR rate card."""
    ct = (contract_type or "A").upper()
    rate_card = await _rate_card_list()
    by_id = {e["id"]: e for e in rate_card}
    cur = db.equipment.find(
        {"organization_id": site_id},
        {"_id": 0, "id": 1, "name": 1, "equipment_type": 1, "model": 1,
         "brand": 1, "serial_number": 1, "location": 1, "category": 1},
    ).sort("name", 1)
    equipment = await cur.to_list(length=2000)
    lines = []
    for eq in equipment:
        m = match_equipment(eq, rate_card, ct)
        rc = by_id.get(m["rate_card_id"]) if m["rate_card_id"] else None
        # Type C is overseas / POA — prices are quoted case-by-case, so we
        # surface the mapped label but leave the price for the user to enter.
        unit_price = None if ct == "C" else (price_for(rc, ct, year) if rc else None)
        lines.append({
            "equipment_id": eq.get("id"),
            "name": eq.get("name") or eq.get("equipment_type") or "Equipment",
            "equipment_type": eq.get("equipment_type"),
            "model": eq.get("model"),
            "serial_number": eq.get("serial_number"),
            "location": eq.get("location"),
            "rate_card_id": m["rate_card_id"],
            "rate_card_label": rc["label"] if rc else None,
            "matched": m["matched"],
            "confidence": m["confidence"],
            "unit_price": unit_price,
            "suggestions": m["suggestions"],
            "quantity": 1,
        })
    return {
        "site_id": site_id,
        "contract_type": ct,
        "year": year,
        "matched_count": sum(1 for l in lines if l["matched"]),
        "unmatched_count": sum(1 for l in lines if not l["matched"]),
        "lines": lines,
    }


@router.post("/ai-match")
async def ai_match_equipment(data: dict, user=Depends(get_crm_user)):
    """AI-assisted mapping of a single piece of equipment to the SOR rate card
    when the keyword matcher is unsure. Uses the Emergent universal LLM key."""
    equip = data.get("equipment") or {}
    rate_card = [e for e in await _rate_card_list() if e.get("kind") == "service"]
    catalogue = "\n".join(f'{e["id"]}: {e["label"]}' for e in rate_card)
    desc = " | ".join(str(equip.get(k, "")) for k in
                      ("name", "equipment_type", "model", "brand") if equip.get(k))
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        key = os.environ["EMERGENT_LLM_KEY"]
        chat = LlmChat(
            api_key=key,
            session_id=f"mod-match-{uuid.uuid4().hex[:8]}",
            system_message=(
                "You map a gym equipment item to exactly one MOD SOR service "
                "rate-card line. Reply with ONLY the rate_card id (e.g. sor-2). "
                "If nothing fits, reply NONE."
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        prompt = (
            f"Equipment: {desc}\n\nRate-card lines (id: label):\n{catalogue}\n\n"
            "Return the single best rate_card id only."
        )
        resp = await chat.send_message(UserMessage(text=prompt))
        answer = (resp or "").strip().split()[0].strip(".,:")
        match = next((e for e in rate_card if e["id"] == answer), None)
        if not match:
            return {"rate_card_id": None, "label": None, "source": "ai"}
        return {"rate_card_id": match["id"], "label": match["label"], "source": "ai"}
    except Exception as e:
        raise HTTPException(502, f"AI matching unavailable: {e}")


# ── Generate quote ─────────────────────────────────────────────────

@router.post("/generate")
async def generate_mod_quote(data: dict, user=Depends(get_crm_user)):
    ct = (data.get("contract_type") or "A").upper()
    if ct not in ("A", "B", "C"):
        raise HTTPException(400, "contract_type must be A, B or C")
    year = int(data.get("year", 1) or 1)
    site_id = data.get("site_id")
    site_name = data.get("site_name", "")
    rate_card = await _rate_card_list()
    by_id = {e["id"]: e for e in rate_card}

    lines: list[dict] = []
    # Informational header line stating the contract type (£0, non-priced).
    lines.append({
        "id": str(uuid.uuid4()),
        "description": f"MOD Contract {CONTRACT_LABELS.get(ct, ct)}",
        "product_name": f"Contract Type {ct}",
        "quantity": 1, "unit_price": 0, "discount": 0,
        "is_contract_header": True, "service_type": ct,
    })

    for raw in (data.get("lines") or []):
        rc = by_id.get(raw.get("rate_card_id"))
        qty = float(raw.get("quantity", 1) or 1)
        if rc and not rc.get("is_poa") and ct != "C":
            unit_price = price_for(rc, ct, year)
            if unit_price is None:
                continue
            desc = raw.get("description") or f'{rc["label"]} — {"Annual Service" if ct == "A" else "Ad-hoc Service"}'
            lines.append({
                "id": str(uuid.uuid4()),
                "description": desc,
                "product_name": rc["label"],
                "sku": rc.get("code_a") if ct == "A" else rc.get("code_b"),
                "quantity": qty, "unit_price": unit_price, "discount": 0,
                "sicon_ref": rc.get("sicon_ref_a") if ct == "A" else rc.get("sicon_ref_b"),
                "equipment_id": raw.get("equipment_id"),
                "serial_number": raw.get("serial_number"),
                "service_type": ct,
                "contracted": True,
            })
        else:
            # POA / Type C / custom-price line — price supplied by the user.
            unit_price = float(raw.get("unit_price", 0) or 0)
            lines.append({
                "id": str(uuid.uuid4()),
                "description": raw.get("description") or (rc["label"] if rc else "Custom line"),
                "product_name": (rc["label"] if rc else "Custom"),
                "sku": (rc.get("code_a") if rc else None),
                "quantity": qty, "unit_price": unit_price, "discount": 0,
                "sicon_ref": (rc.get("sicon_ref_a") if rc else None),
                "equipment_id": raw.get("equipment_id"),
                "service_type": "C" if (rc and rc.get("is_poa")) else ct,
                "is_poa": bool(rc and rc.get("is_poa")),
                "contracted": False,
            })

    # Type B: add UK call-out charges if requested.
    call_outs = int(data.get("call_out_count", 0) or 0)
    if ct == "B" and call_outs > 0:
        co = next((e for e in rate_card if e.get("kind") == "call_out"), None)
        if co:
            lines.append({
                "id": str(uuid.uuid4()),
                "description": "Call Out Charge — Type B / UK Only",
                "product_name": "Call Out Charge", "sku": co.get("code_b"),
                "sicon_ref": co.get("sicon_ref_b"),
                "quantity": call_outs, "unit_price": co.get("type_b_price"),
                "discount": 0, "service_type": "B", "contracted": True,
            })

    subtotal = round(sum(
        float(l["quantity"]) * float(l["unit_price"]) * (1 - float(l.get("discount", 0) or 0) / 100)
        for l in lines
    ), 2)
    vat_rate = float(data.get("vat_rate", 20) or 0)
    vat_amount = round(subtotal * vat_rate / 100, 2)
    total = round(subtotal + vat_amount, 2)

    quote_id = str(uuid.uuid4())
    quote_number = f"MOD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{quote_id[:4].upper()}"
    quote = {
        "id": quote_id,
        "organization_id": user.get("organization_id"),
        "quote_number": quote_number,
        "title": data.get("title") or f"MOD {site_name} — Contract Type {ct}",
        "company_id": data.get("company_id"),
        "company_name": data.get("company_name") or site_name,
        "contact_id": data.get("contact_id"),
        "contact_name": data.get("contact_name", ""),
        "opportunity_id": data.get("opportunity_id"),
        "status": "draft",
        "lines": lines,
        "subtotal": subtotal,
        "vat_rate": vat_rate, "vat_amount": vat_amount,
        "tax_rate": vat_rate, "tax_amount": vat_amount, "tax_label": "VAT",
        "total": total,
        "currency": "GBP",
        "notes": data.get("notes", ""),
        "valid_until": data.get("valid_until", ""),
        # MOD-specific metadata.
        "quote_kind": "mod_sor",
        "mod_contract_type": ct,
        "mod_contract_year": year,
        "mod_site_id": site_id,
        "mod_site_name": site_name,
        "version": 1,
        "created_by": user.get("full_name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.crm2_quotes.insert_one(quote)
    quote.pop("_id", None)
    await log_audit(user, "quote", quote_id, "mod_quote_created",
                    {"contract_type": ct, "site": site_name, "total": total})

    # Type A → provision a MOD service contract that feeds MOD Service Operations.
    contract = None
    if ct == "A":
        contract = {
            "id": str(uuid.uuid4()),
            "organization_id": user.get("organization_id"),
            "contract_type": "A",
            "status": "pending_activation",
            "quote_id": quote_id,
            "quote_number": quote_number,
            "mod_site_id": site_id,
            "mod_site_name": site_name,
            "annual_value": subtotal,
            "currency": "GBP",
            "start_date": data.get("start_date"),
            "term_months": 12,
            "equipment_count": sum(1 for li in lines if li.get("equipment_id")),
            "created_by": user["id"],
            "created_by_name": user.get("full_name", ""),
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.mod_service_contracts.insert_one(contract)
        contract.pop("_id", None)
        await log_audit(user, "mod_service_contract", contract["id"], "created",
                        {"site": site_name, "annual_value": subtotal})

    return {"quote": quote, "contract": contract}


@router.get("/contracts")
async def list_mod_contracts(user=Depends(get_crm_user)):
    """Type A service contracts generated by the quote writer (Service Ops feed)."""
    cur = db.mod_service_contracts.find(
        {"organization_id": user.get("organization_id")}, {"_id": 0},
    ).sort("created_at", -1)
    return {"contracts": await cur.to_list(length=500)}
