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
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, Form

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit
from routes.crm_cpq import _now
from utils.mod_sor_data import build_seed_rate_card, price_for, match_equipment, match_by_mod_code, normalise_mod_code
from utils.dealer_parts_ai import spreadsheet_rows
from utils.brand_urls import app_url_for_org

router = APIRouter(prefix="/crm/mod-quote", tags=["CRM MOD Quote"])
# Public, token-authenticated e-sign surface (no CRM login required).
public_router = APIRouter(prefix="/public/mod-quote", tags=["Public Quote E-Sign"])

ESIGN_TTL_DAYS = int(os.environ.get("QUOTE_ESIGN_TTL_DAYS", "30"))

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


async def require_operator_crm_user(user=Depends(get_crm_user)):
    """Gate the MOD Quote Writer to Pulse Fitness Ltd (the operator company)
    and Pulse platform admins ONLY.

    MOD quoting deliberately reads across MOD *site* organisations — which are
    separate tenants — so Pulse can quote service/repair for the whole estate.
    That cross-tenant reach must never be exposed to an ordinary customer
    tenant (e.g. a leisure operator), which would leak MOD customer and
    equipment data (a GDPR breach). Authorisation is decided by the
    authoritative ``is_operator_company`` flag on the caller's org, not by a
    name/brand heuristic.
    """
    if (user.get("is_master_admin") or user.get("is_pulse_admin")
            or user.get("role") == "pulse_master_admin"):
        return user
    org_id = user.get("organization_id")
    if org_id:
        org = await db.organizations.find_one(
            {"id": org_id}, {"_id": 0, "is_operator_company": 1})
        if org and org.get("is_operator_company"):
            return user
    raise HTTPException(403, "MOD quoting is restricted to Pulse Fitness.")


async def _ensure_rate_card() -> None:
    if await db.mod_sor_rate_card.count_documents({}) == 0:
        await db.mod_sor_rate_card.insert_many(build_seed_rate_card())


async def _rate_card_list() -> list[dict]:
    await _ensure_rate_card()
    cur = db.mod_sor_rate_card.find({}, {"_id": 0}).sort("sort_order", 1)
    return await cur.to_list(length=500)


# ── Rate card ──────────────────────────────────────────────────────

@router.get("/rate-card")
async def get_rate_card(user=Depends(require_operator_crm_user)):
    return {"items": await _rate_card_list()}


@router.put("/rate-card/{item_id}")
async def update_rate_card_item(item_id: str, data: dict, user=Depends(require_operator_crm_user)):
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
async def reseed_rate_card(user=Depends(require_operator_crm_user), confirm: bool = False):
    """Reset the rate card to the built-in SCAFFOLD.

    ⚠️ The built-in card ships only PLACEHOLDER prices — the real contracted
    prices live in the database. Reseeding OVERWRITES any live pricing with
    placeholders, so it is blocked once a card exists unless ?confirm=true is
    passed explicitly (protects production pricing from an accidental reset)."""
    if not _is_admin(user):
        raise HTTPException(403, "Only CRM admins can reseed the SOR rate card")
    existing = await db.mod_sor_rate_card.count_documents({})
    if existing > 0 and not confirm:
        raise HTTPException(
            409,
            "A rate card already exists. Reseeding installs PLACEHOLDER pricing "
            "and will overwrite the live card. Re-send with confirm=true only if "
            "you are sure — the real contracted prices are NOT restored from code.",
        )
    await db.mod_sor_rate_card.delete_many({})
    await db.mod_sor_rate_card.insert_many(build_seed_rate_card())
    await log_audit(user, "mod_rate_card", "all", "reseeded", {"confirm": confirm})
    return {"items": await _rate_card_list()}


# ── MOD sites & equipment mapping ──────────────────────────────────

@router.get("/mod-sites")
async def list_mod_sites(user=Depends(require_operator_crm_user)):
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
                             user=Depends(require_operator_crm_user)):
    """Return a site's equipment auto-mapped onto the SOR rate card."""
    ct = (contract_type or "A").upper()
    rate_card = await _rate_card_list()
    by_id = {e["id"]: e for e in rate_card}
    cur = db.equipment.find(
        {"organization_id": site_id},
        {"_id": 0, "id": 1, "name": 1, "equipment_type": 1, "model": 1,
         "brand": 1, "serial_number": 1, "location": 1, "category": 1,
         "mod_code": 1, "contract_type": 1},
    ).sort("name", 1)
    equipment = await cur.to_list(length=2000)
    lines = []
    for eq in equipment:
        # Each machine carries its OWN service tier (Type A/B/C, set at import).
        # That drives its SOR rate card + TL line automatically; the site-wide
        # `contract_type` param is only a fallback for kit with no tier set.
        eq_ct = (eq.get("contract_type") or "").upper()
        line_ct = eq_ct if eq_ct in ("A", "B", "C") else ct
        ct_source = "equipment" if eq_ct in ("A", "B", "C") else "default"
        # MOD Code is authoritative: an imported "MOD Code" deterministically
        # identifies the SOR/TL line, so a Service Quote pre-fills with zero
        # manual matching. Fall back to fuzzy keyword matching only when there's
        # no (recognised) MOD code.
        mod_raw = eq.get("mod_code")
        mod_norm = normalise_mod_code(mod_raw) if mod_raw else ""
        rc = None
        matched = False
        confidence = 0.0
        suggestions: list = []
        source = None
        if mod_norm:
            rc_mod = match_by_mod_code(mod_norm, rate_card)
            if rc_mod:
                rc = rc_mod
                matched = True
                confidence = 1.0
                source = "mod_code"
        if rc is None:
            m = match_equipment(eq, rate_card, line_ct)
            rc = by_id.get(m["rate_card_id"]) if m["rate_card_id"] else None
            matched = m["matched"]
            confidence = m["confidence"]
            suggestions = m["suggestions"]
            source = "keyword" if matched else None
        # Type C is overseas / POA — prices are quoted case-by-case, so we
        # surface the mapped label but leave the price (and TL) for the user.
        unit_price = None if line_ct == "C" else (price_for(rc, line_ct, year) if rc else None)
        if not rc:
            tl_number = None
        elif line_ct == "A":
            tl_number = rc.get("code_a")
        elif line_ct == "B":
            tl_number = rc.get("code_b")
        else:  # Type C — overseas, priced on application, no fixed TL line
            tl_number = None
        lines.append({
            "equipment_id": eq.get("id"),
            "name": eq.get("name") or eq.get("equipment_type") or "Equipment",
            "equipment_type": eq.get("equipment_type"),
            "model": eq.get("model"),
            "serial_number": eq.get("serial_number"),
            "location": eq.get("location"),
            "mod_code": mod_norm or (mod_raw or ""),
            "contract_type": line_ct,
            "contract_type_source": ct_source,
            "rate_card_id": rc["id"] if rc else None,
            "rate_card_label": rc["label"] if rc else None,
            "tl_number": tl_number,
            "matched": matched,
            "confidence": confidence,
            "source": source,
            "unit_price": unit_price,
            "suggestions": suggestions,
            "quantity": 1,
        })
    return {
        "site_id": site_id,
        "contract_type": ct,
        "year": year,
        "matched_count": sum(1 for l in lines if l["matched"]),
        "mod_code_matched_count": sum(1 for l in lines if l["source"] == "mod_code"),
        "unmatched_count": sum(1 for l in lines if not l["matched"]),
        "per_machine_type_count": sum(1 for l in lines if l["contract_type_source"] == "equipment"),
        "mixed_contract_types": len({l["contract_type"] for l in lines}) > 1,
        "lines": lines,
    }


@router.post("/ai-match")
async def ai_match_equipment(data: dict, user=Depends(require_operator_crm_user)):
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


# ── Spreadsheet import → AI recognition ────────────────────────────

def _norm_code(v) -> str:
    return "".join(ch for ch in str(v or "").upper() if ch.isalnum())


def _grid_to_text(rows: list[list], max_rows: int = 80, max_cols: int = 12) -> str:
    out = []
    for r in rows:
        cells = [("" if c is None else str(c)).strip()[:60] for c in list(r)[:max_cols]]
        if any(cells):
            out.append(" | ".join(cells))
        if len(out) >= max_rows:
            break
    return "\n".join(out)


async def _recognise_items(grid_text: str) -> dict:
    """Ask the LLM to read an arbitrary MOD asset-register grid and return
    normalised equipment items {description, code, quantity}."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    key = os.environ["EMERGENT_LLM_KEY"]
    chat = LlmChat(
        api_key=key,
        session_id=f"mod-import-{uuid.uuid4().hex[:8]}",
        system_message=(
            "You read raw spreadsheets exported from MOD site gym asset registers. "
            "There is NO fixed template: column order and headings vary, some files "
            "have no headings, and rows may include totals, notes or blanks. "
            "Identify every row that represents a single physical training equipment "
            "ITEM. For each, extract: description (the machine name/type/model exactly "
            "as written), code (any Pulse/asset/product/SOR code shown for that row, else ''), "
            "mod_code (the value in a column headed 'MOD Code'/'MOD-Code', or ANY token on "
            "the row that starts with 'MOD-' such as MOD-UBIKE or MOD-STRENGTH; else ''), "
            "and quantity (a whole number; if a quantity column exists use it, otherwise "
            "1 per asset row). Ignore header rows, subtotals, totals, section titles and "
            "blank rows. Never invent machines, codes or quantities. "
            "Respond with STRICT JSON only: "
            '{"items":[{"description":"","code":"","mod_code":"","quantity":1}],"note":""}'
        ),
    ).with_model("anthropic", "claude-sonnet-4-6")
    prompt = f"Spreadsheet contents (row by row, cells separated by ' | '):\n\n{grid_text}\n\nReturn the JSON now."
    raw = (await chat.send_message(UserMessage(text=prompt))).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):]
    import json as _json
    try:
        start, end = raw.find("{"), raw.rfind("}")
        data = _json.loads(raw[start:end + 1])
    except Exception:
        data = {"items": [], "note": "Could not interpret the file automatically."}
    items = data.get("items") or []
    clean = []
    for it in items:
        desc = str(it.get("description", "")).strip()
        if not desc:
            continue
        try:
            qty = int(float(it.get("quantity", 1) or 1))
        except Exception:
            qty = 1
        clean.append({"description": desc, "code": str(it.get("code", "")).strip(),
                      "mod_code": str(it.get("mod_code", "")).strip(),
                      "quantity": max(qty, 1)})
    return {"items": clean, "note": str(data.get("note", "")).strip()}


def _match_recognised(item: dict, rate_card: list[dict], ct: str, year: int) -> dict:
    """Match a recognised item to a rate-card line. Priority:
    1. Explicit MOD Code on the row (deterministic — trust it).
    2. Direct Pulse/SOR code hit.
    3. Keyword/description matching. Never drops the row."""
    import re as _re
    services = [e for e in rate_card if e.get("kind") == "service"]
    rc = None
    confidence = 0.0
    source = "unmatched"
    suggestions = []

    # 1 — MOD Code (from its own column, or any MOD- token on the row).
    mod_raw = (item.get("mod_code") or "").strip()
    if not mod_raw:
        blob = f"{item.get('code', '')} {item.get('description', '')}".upper()
        m = _re.search(r"MOD[-\s]?[A-Z0-9]+", blob)
        if m:
            mod_raw = m.group(0)
    mod_code = normalise_mod_code(mod_raw)
    if mod_code:
        rc_mod = match_by_mod_code(mod_code, rate_card)
        if rc_mod is not None:
            rc, confidence, source = rc_mod, 0.98, "mod_code"

    # 2 — direct Pulse/SOR code hit.
    if rc is None:
        code_n = _norm_code(item.get("code"))
        if code_n:
            for e in services:
                if code_n in (_norm_code(e.get("code_a")), _norm_code(e.get("code_b"))):
                    rc, confidence, source = e, 0.99, "code"
                    break

    # 3 — keyword/description matching.
    if rc is None:
        m = match_equipment(
            {"name": item.get("description", ""), "equipment_type": item.get("description", "")},
            rate_card, ct,
        )
        suggestions = m.get("suggestions") or []
        if m.get("rate_card_id"):
            rc = next((e for e in services if e["id"] == m["rate_card_id"]), None)
            confidence = float(m.get("confidence") or 0.0)
            source = "keyword"

    unit_price = None
    if rc and ct != "C" and not rc.get("is_poa"):
        unit_price = price_for(rc, ct, year)
    matched = rc is not None and confidence >= 0.5
    return {
        "description": item.get("description", ""),
        "source_code": item.get("code", ""),
        "mod_code": mod_code or item.get("mod_code", ""),
        "quantity": item.get("quantity", 1),
        "rate_card_id": rc["id"] if rc else None,
        "rate_card_label": rc["label"] if rc else None,
        "matched_code": (rc.get("code_a") if ct == "A" else rc.get("code_b")) if rc else None,
        "unit_price": unit_price,
        "confidence": round(confidence, 2),
        "matched": matched,
        "needs_review": (rc is None) or (confidence < 0.5),
        "source": source,
        "suggestions": suggestions,
    }


@router.post("/import-spreadsheet")
async def import_spreadsheet(
    file: UploadFile | None = File(None),
    pasted_text: str = Form(""),
    contract_type: str = Form("A"),
    year: int = Form(1),
    user=Depends(require_operator_crm_user),
):
    """Drag-and-drop a MOD asset spreadsheet (or paste from Excel). The AI reads
    the arbitrary layout, recognises machines / codes / quantities, matches them
    to the SOR rate card and returns proposed lines for operator review."""
    ct = (contract_type or "A").upper()
    if ct not in ("A", "B", "C"):
        raise HTTPException(400, "contract_type must be A, B or C")
    year = int(year or 1)

    rows: list[list] = []
    if file is not None:
        content = await file.read()
        name = (file.filename or "").lower()
        if not name.endswith((".xlsx", ".xls", ".csv")):
            raise HTTPException(400, "Please upload a .xlsx, .xls or .csv file (or paste the rows).")
        try:
            rows = list(spreadsheet_rows(content, file.filename or ""))
        except Exception as exc:
            raise HTTPException(
                400,
                f"Could not read that file ({exc}). If it is an older .xls, please re-save as .xlsx or CSV, or paste the rows instead.",
            )
    elif pasted_text.strip():
        import csv as _csv
        delim = "\t" if "\t" in pasted_text else ","
        rows = [r for r in _csv.reader(pasted_text.splitlines(), delimiter=delim)]
    else:
        raise HTTPException(400, "Attach a spreadsheet file or paste the rows to import.")

    grid_text = _grid_to_text(rows)
    if not grid_text.strip():
        raise HTTPException(400, "The file/paste appears to be empty.")

    try:
        recognised = await _recognise_items(grid_text)
    except Exception as exc:
        raise HTTPException(502, f"AI recognition unavailable: {exc}")

    rate_card = await _rate_card_list()
    lines = [_match_recognised(it, rate_card, ct, year) for it in recognised["items"]]

    await log_audit(user, "mod_quote_import", file.filename if file else "pasted",
                    "recognised", {"rows": len(rows), "items": len(lines), "contract_type": ct})
    return {
        "contract_type": ct,
        "year": year,
        "source_rows": len(rows),
        "recognised_count": len(lines),
        "matched_count": sum(1 for l in lines if l["matched"]),
        "needs_review_count": sum(1 for l in lines if l["needs_review"]),
        "note": recognised.get("note", ""),
        "lines": lines,
    }


# ── Generate quote ─────────────────────────────────────────────────

@router.post("/generate")
async def generate_mod_quote(data: dict, user=Depends(require_operator_crm_user)):
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
        # Each machine may carry its own service tier (Type A/B/C from its
        # record); fall back to the quote-level contract type when absent.
        line_ct = (raw.get("contract_type") or ct).upper()
        if line_ct not in ("A", "B", "C"):
            line_ct = ct
        if rc and not rc.get("is_poa") and line_ct != "C":
            unit_price = price_for(rc, line_ct, year)
            if unit_price is None:
                continue
            desc = raw.get("description") or f'{rc["label"]} — {"Annual Service" if line_ct == "A" else "Ad-hoc Service"}'
            lines.append({
                "id": str(uuid.uuid4()),
                "description": desc,
                "product_name": rc["label"],
                "sku": rc.get("code_a") if line_ct == "A" else rc.get("code_b"),
                "quantity": qty, "unit_price": unit_price, "discount": 0,
                "sicon_ref": rc.get("sicon_ref_a") if line_ct == "A" else rc.get("sicon_ref_b"),
                "equipment_id": raw.get("equipment_id"),
                "serial_number": raw.get("serial_number"),
                "service_type": line_ct,
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
                "service_type": "C" if (rc and rc.get("is_poa")) else line_ct,
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


@router.get("/{quote_id}/pdf")
async def mod_quote_pdf_authenticated(quote_id: str, user=Depends(require_operator_crm_user)):
    """Render the live MOD quote PDF (with TL numbers) for the owning operator —
    used by the wizard's in-app preview BEFORE sending to Leidos."""
    from fastapi import Response
    from utils.crm_quote_pdf import render_quote_pdf
    quote = await db.crm2_quotes.find_one(
        {"id": quote_id, "organization_id": user.get("organization_id")}, {"_id": 0})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    pdf_bytes = await render_quote_pdf(quote, organization_id=quote.get("organization_id"))
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{quote.get("quote_number", "mod-quote")}.pdf"'})

async def list_mod_contracts(user=Depends(require_operator_crm_user)):
    """Type A service contracts generated by the quote writer (Service Ops feed)."""
    cur = db.mod_service_contracts.find(
        {"organization_id": user.get("organization_id")}, {"_id": 0},
    ).sort("created_at", -1)
    return {"contracts": await cur.to_list(length=500)}


# ── Send for e-signature (secure public link) ──────────────────────

async def _quote_org_branding(org_id: str | None) -> dict:
    org = await db.organizations.find_one(
        {"id": org_id},
        {"_id": 0, "name": 1, "account_type": 1, "logo_url": 1, "brand_color": 1, "branding": 1},
    ) if org_id else None
    org = org or {}
    branding = org.get("branding") or {}
    return {
        "org_name": org.get("name") or "Pulse Fitness",
        "logo_url": org.get("logo_url") or branding.get("logo_url"),
        "brand_color": org.get("brand_color") or branding.get("primary_color") or "#0055FF",
        "account_type": org.get("account_type"),
        "_org": org,
    }


@router.post("/{quote_id}/send-esign")
async def send_quote_for_esign(quote_id: str, data: dict, user=Depends(require_operator_crm_user)):
    """Email the MOD/customer contact a secure link to view and e-sign the
    quote. Returns the link so it also works in preview (email disabled)."""
    quote = await db.crm2_quotes.find_one(
        {"id": quote_id, "organization_id": user.get("organization_id")}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "Quote not found")

    to_addr = (data.get("to") or "").strip().lower()
    if not to_addr and quote.get("contact_id"):
        contact = await db.crm2_contacts.find_one(
            {"id": quote["contact_id"], "organization_id": user.get("organization_id")},
            {"_id": 0, "email": 1})
        to_addr = ((contact or {}).get("email") or "").strip().lower()
    if not to_addr:
        raise HTTPException(400, "No recipient email — pass `to` or link a contact with an email.")

    token = quote.get("esign_token") or uuid.uuid4().hex
    expires = (datetime.now(timezone.utc) + timedelta(days=ESIGN_TTL_DAYS)).isoformat()
    await db.crm2_quotes.update_one({"id": quote_id}, {"$set": {
        "esign_token": token,
        "esign_status": "sent",
        "esign_sent_to": to_addr,
        "esign_sent_at": _now(),
        "esign_expires_at": expires,
        "status": "sent" if quote.get("status") in (None, "", "draft", "approved") else quote.get("status"),
        "updated_at": _now(),
    }})

    brand = await _quote_org_branding(quote.get("organization_id"))
    base = app_url_for_org(brand["_org"])
    link = f"{base}/quote/sign/{token}"

    # Best-effort branded email (Resend disabled in preview → link still returned).
    emailed = False
    try:
        from utils import email_templates as et
        from utils.email import send_email
        ct = quote.get("mod_contract_type")
        eyebrow = f"Quote {quote.get('quote_number', '')}"
        body = (
            et.paragraph(f'Hi,')
            + et.paragraph(
                f'{et.esc(brand["org_name"])} has sent you a quote'
                + (f' for a MOD Contract Type {ct}' if ct else '')
                + f' &mdash; <strong>{et.esc(quote.get("title") or quote.get("quote_number"))}</strong>.')
            + et.info_card(
                et.paragraph(f'<strong>Total:</strong> &pound;{float(quote.get("total") or 0):,.2f} '
                             f'(inc. VAT)', size="15px", margin="0")
                + et.paragraph(f'Valid until: {et.esc(quote.get("valid_until") or "on request")}',
                               color=et.TEXT_MUTED, size="13px", margin="6px 0 0"),
                bg="#F8FAFC", accent=brand["brand_color"])
            + et.paragraph('Review the full quote and sign it online using the secure button below.')
            + et.bulletproof_button(link, "View & Sign Quote", brand["brand_color"],
                                    testid="quote-esign-cta"))
        html = et.email_shell(
            title=f"Quote {quote.get('quote_number', '')} — ready to sign",
            eyebrow=eyebrow, body_html=body, brand_color=brand["brand_color"],
            logo_url=brand["logo_url"], org_name=brand["org_name"],
            platform_footer="Sent via Pulse Fitness", preheader="Your quote is ready to view and sign.")
        await send_email(to=to_addr, subject=f"Quote {quote.get('quote_number', '')} — ready to sign",
                         html=html, organization_id=quote.get("organization_id"), kind="crm_quote_esign")
        emailed = True
    except Exception:
        emailed = False

    await db.crm2_activities.insert_one({
        "id": str(uuid.uuid4()), "organization_id": user.get("organization_id"),
        "type": "system", "subject": f"Quote {quote.get('quote_number', '')} sent for e-signature",
        "body": f"Secure link sent to {to_addr}", "quote_id": quote_id,
        "company_id": quote.get("company_id"), "contact_id": quote.get("contact_id"),
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    })
    await log_audit(user, "quote", quote_id, "sent_for_esign", {"to": to_addr})
    return {"ok": True, "to": to_addr, "link": link, "emailed": emailed}


# ── Public token endpoints (no auth) ───────────────────────────────

def _public_quote_view(quote: dict, brand: dict) -> dict:
    return {
        "id": quote.get("id"),
        "quote_number": quote.get("quote_number"),
        "title": quote.get("title"),
        "status": quote.get("status"),
        "esign_status": quote.get("esign_status"),
        "mod_contract_type": quote.get("mod_contract_type"),
        "mod_site_name": quote.get("mod_site_name"),
        "company_name": quote.get("company_name"),
        "currency": quote.get("currency", "GBP"),
        "lines": [
            {k: l.get(k) for k in ("description", "product_name", "quantity",
                                    "unit_price", "discount", "sku", "service_type")}
            for l in (quote.get("lines") or [])
        ],
        "subtotal": quote.get("subtotal"),
        "vat_rate": quote.get("vat_rate", quote.get("tax_rate", 20)),
        "vat_amount": quote.get("vat_amount", quote.get("tax_amount", 0)),
        "total": quote.get("total"),
        "notes": quote.get("notes"),
        "valid_until": quote.get("valid_until"),
        "signer_name": quote.get("signer_name"),
        "signed_at": quote.get("signed_at"),
        "org_name": brand["org_name"],
        "logo_url": brand["logo_url"],
        "brand_color": brand["brand_color"],
    }


async def _load_quote_by_token(token: str) -> dict:
    quote = await db.crm2_quotes.find_one({"esign_token": token}, {"_id": 0})
    if not quote:
        raise HTTPException(404, "This quote link is invalid or has been withdrawn.")
    exp = quote.get("esign_expires_at")
    if exp and exp < datetime.now(timezone.utc).isoformat():
        raise HTTPException(410, "This quote link has expired. Please request a new one.")
    return quote


@public_router.get("/{token}")
async def public_view_quote(token: str):
    quote = await _load_quote_by_token(token)
    brand = await _quote_org_branding(quote.get("organization_id"))
    return _public_quote_view(quote, brand)


async def apply_quote_signature(quote: dict, signer_name: str, signature: str,
                                signed_ip: str | None = None, via: str = "public_link") -> dict:
    """Shared accept/sign logic used by both the public e-sign link and the
    in-portal (authenticated) MOD signing flow."""
    if quote.get("esign_status") == "signed" or quote.get("status") == "accepted":
        raise HTTPException(409, "This quote has already been signed.")
    signature = (signature or "").strip()
    signer_name = (signer_name or "").strip()
    if not signature or not signer_name:
        raise HTTPException(400, "Signature and signer name are required.")
    signed_at = _now()
    await db.crm2_quotes.update_one({"id": quote["id"]}, {"$set": {
        "signature": signature,
        "signer_name": signer_name,
        "signed_at": signed_at,
        "signed_ip": signed_ip,
        "signed_via": via,
        "status": "accepted",
        "esign_status": "signed",
        "updated_at": signed_at,
    }})
    org_id = quote.get("organization_id")
    await db.crm2_notifications.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "type": "approval", "title": "Quote Signed",
        "message": f"Quote {quote.get('quote_number', '')} was e-signed by {signer_name}",
        "entity_type": "quote", "entity_id": quote["id"], "read": False, "created_at": signed_at,
    })
    await db.crm2_activities.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org_id,
        "type": "system", "subject": f"Quote {quote.get('quote_number', '')} e-signed & accepted",
        "body": f"Signed by {signer_name}", "quote_id": quote["id"],
        "company_id": quote.get("company_id"), "contact_id": quote.get("contact_id"),
        "created_at": signed_at, "updated_at": signed_at,
    })
    # If this is a Type A MOD quote, activate its linked service contract and
    # auto-schedule its annual service visit (pending confirmation by the
    # Pulse Fitness MOD Service team).
    if quote.get("mod_contract_type") == "A":
        contract = await db.mod_service_contracts.find_one(
            {"quote_id": quote["id"]}, {"_id": 0, "start_date": 1, "annual_visit": 1})
        set_fields = {"status": "active", "activated_at": signed_at, "updated_at": signed_at}
        if contract is not None and not contract.get("annual_visit"):
            proposed = (contract.get("start_date") or signed_at)[:10]
            set_fields["annual_visit"] = {
                "status": "pending_confirmation",
                "proposed_date": proposed,
                "scheduled_date": None,
                "engineer": None,
                "notes": None,
                "confirmed_by": None,
                "confirmed_at": None,
                "created_at": signed_at,
            }
        await db.mod_service_contracts.update_one(
            {"quote_id": quote["id"]}, {"$set": set_fields})
    try:
        from utils.comms_conversions import record_conversion
        await record_conversion(org_id, quote.get("esign_sent_to"), "quote_accepted",
                                value_gbp=float(quote.get("total") or 0),
                                source="crm_quote_esign", meta={"quote_id": quote["id"]})
    except Exception:
        pass
    return {"success": True, "status": "accepted", "signer": signer_name, "signed_at": signed_at}


@public_router.post("/{token}/sign")
async def public_sign_quote(token: str, data: dict, request: Request):
    quote = await _load_quote_by_token(token)
    return await apply_quote_signature(
        quote, data.get("signer_name"), data.get("signature"),
        signed_ip=(request.client.host if request.client else None), via="public_link")


@public_router.get("/{token}/pdf")
async def public_quote_pdf(token: str):
    from fastapi.responses import Response
    quote = await _load_quote_by_token(token)
    try:
        from utils.crm_quote_pdf import render_quote_pdf
        pdf_bytes = await render_quote_pdf(quote, organization_id=quote.get("organization_id"))
    except Exception as exc:
        raise HTTPException(500, f"Could not generate PDF: {exc}") from exc
    filename = (quote.get("quote_number") or "quote") + ".pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})
