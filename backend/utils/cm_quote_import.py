"""Build Quote — start a maintenance quote from a sales invoice, delivery note or
an existing maintenance invoice. Reuses the onboarding AI extractor pattern,
the Aftersales service-config index / pricing annotation and the existing
customer + equipment records. Never creates customers; equipment is created
only for confirmed lines, keyed so retries reuse the same records.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from utils.database import db

DOC_TYPES = {"sales_invoice": "Sales invoice", "delivery_note": "Delivery note",
             "maintenance_invoice": "Maintenance invoice (evidence only)"}
_SPARE = re.compile(r"\b(part|spare|belt|cable|kit|accessor|console only|pcb|motor|deck|bolt|warranty ext)", re.I)

_PROMPT = """Extract this {label} for gym / fitness equipment as JSON:
{{"customer_name": str|null, "account_ref": str|null, "postcode": str|null, "site_name": str|null,
 "site_address": str|null, "document_ref": str|null, "document_date": "YYYY-MM-DD"|null,
 "lines": [{{"item_code": str|null, "make": str|null, "model": str|null, "description": str|null,
             "quantity": int, "serials": [str], "amount": number|null}}]}}
Rules: copy codes, models and serial numbers EXACTLY as printed; never invent values (use null / []).
"account_ref" is the customer's account number on the document (e.g. Sage A/C). "postcode" is the
customer's delivery/site postcode. One line per product row; include parts and accessories as their
own lines (do not drop them). Exclude carriage, VAT, subtotal and total rows. Return ONLY JSON.
TEXT:
{text}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    s = re.sub(r"\b(ltd|limited|plc|llp|the|uk|group|co|company)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _pc(s) -> str:
    return re.sub(r"\s", "", (s or "").upper())


async def extract_document(pdf: bytes, doc_type: str) -> dict:
    from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
    from routes.equipment_import import _extract_pdf_text, _pdf_to_image_base64s
    from utils.ai_guardrails import sanitize_prompt
    from utils.database import EMERGENT_LLM_KEY
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "Document extraction is not configured.")
    try:
        text = _extract_pdf_text(pdf)
    except HTTPException:
        text = ""
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"cm_qimp_{uuid.uuid4().hex[:8]}",
                   system_message="You extract structured data from business documents. Return ONLY valid JSON."
                   ).with_model("anthropic", "claude-haiku-4-5")
    label = DOC_TYPES[doc_type].replace(" (evidence only)", "")
    if text and len(text) >= 50:
        raw = await chat.send_message(UserMessage(text=_PROMPT.format(label=label, text=sanitize_prompt(text, max_chars=60000))))
    else:
        raw = await chat.send_message(UserMessage(text=_PROMPT.format(label=label, text="(scanned — read the attached pages)"),
                                                  file_contents=[ImageContent(image_base64=b) for b in _pdf_to_image_base64s(pdf)]))
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    try:
        out = json.loads(raw)
    except ValueError:
        raise HTTPException(422, "The document could not be read — check it is a clear invoice or delivery note.")
    out["lines"] = [ln for ln in out.get("lines") or [] if isinstance(ln, dict)]
    return out


async def match_customer(org_id: str, hints: dict) -> dict:
    """Verified references first (account ref, legal name + postcode); otherwise
    return candidates for the coordinator. Never creates a customer."""
    ref = (hints.get("account_ref") or "").strip()
    name, pc = _norm(hints.get("customer_name")), _pc(hints.get("postcode"))
    proj = {"_id": 0, "id": 1, "name": 1, "legal_name": 1, "postcode": 1, "linked_organization_id": 1,
            "sage_account": 1, "sage_customer_reference": 1, "account_number": 1}
    if ref:
        hits = await db.crm2_companies.find({"organization_id": org_id, "$or": [
            {"sage_account": ref}, {"sage_customer_reference": ref}, {"account_number": ref}]}, proj).to_list(5)
        if len(hits) == 1:
            return {"status": "matched", "company": hits[0], "basis": f"account reference {ref}", "candidates": hits}
    cands, seen = [], set()
    async for co in db.crm2_companies.find({"organization_id": org_id, "archived": {"$ne": True}}, proj):
        n1, n2 = _norm(co.get("name")), _norm(co.get("legal_name"))
        exact = bool(name) and name in (n1, n2)
        similar = bool(name) and not exact and any(n and (name in n or n in name) for n in (n1, n2))
        pcs = {_pc(co.get("postcode"))}
        if pc and co.get("linked_organization_id"):
            async for st in db.sites.find({"organization_id": co["linked_organization_id"]}, {"_id": 0, "postcode": 1}):
                pcs.add(_pc(st.get("postcode")))
        pc_hit = bool(pc) and pc in pcs
        if (exact or similar or pc_hit) and co["id"] not in seen:
            seen.add(co["id"])
            cands.append({**co, "name_match": "exact" if exact else "similar" if similar else "none",
                          "postcode_match": pc_hit})
    strong = [x for x in cands if x["name_match"] == "exact" and (x["postcode_match"] or not pc)]
    cands.sort(key=lambda x: (x["name_match"] != "exact", not x["postcode_match"]))
    if len(strong) == 1 and (strong[0]["postcode_match"] or len([x for x in cands if x["name_match"] == "exact"]) == 1):
        basis = "legal name + postcode" if strong[0]["postcode_match"] else "exact legal name"
        return {"status": "matched", "company": strong[0], "basis": basis, "candidates": cands[:8]}
    return {"status": "review" if cands else "not_found", "company": None, "basis": None, "candidates": cands[:8]}


async def _active_contract_ids(org_id: str, ids: set) -> set:
    if not ids:
        return set()
    rows = await db.crm2_contracts.find({"organization_id": org_id, "id": {"$in": list(ids)}, "status": "active"},
                                        {"_id": 0, "id": 1}).to_list(None)
    return {r["id"] for r in rows}


async def match_lines(org_id: str, lines: list, doc_type: str, linked_org: str | None) -> list:
    from routes.crm_aftersales import _annotate_asset
    from routes.crm_afs_onboarding import _config_index, _match_row
    idx = await _config_index(org_id)
    by_sku = {}
    for cfgs in idx.values():
        for cfg in cfgs:
            if cfg.get("reference_sku"):
                by_sku.setdefault(cfg["reference_sku"].strip().upper(), []).append(cfg)
    out = []
    for n, ln in enumerate(lines, start=1):
        code = (ln.get("item_code") or "").strip()
        qty = ln.get("quantity") or 1
        try:
            qty = max(1, min(int(qty), 200))
        except (TypeError, ValueError):
            qty = 1
        serials = [str(s).strip() for s in ln.get("serials") or [] if str(s).strip()]
        flags, cfg, basis = [], None, None
        product = await db.crm_products.find_one({"organization_id": org_id, "sku": code}, {"_id": 0}) if code else None
        cands = by_sku.get(code.upper(), []) if code else []
        if not cands and product and product.get("model"):
            cands = idx.get(product["model"].strip().lower(), [])
        if cands:
            variants = {(c.get("model"), c.get("console_type") or "") for c in cands}
            if len(variants) > 1:
                flags.append("variant_review")
            from routes.crm_afs_onboarding import _rank_cfg
            cfg, basis = sorted(cands, key=_rank_cfg, reverse=True)[0], "exact product code"
        else:
            cfg, _, _st = _match_row(idx, ln.get("model"), ln.get("make"))
            if cfg:
                basis = "model name"
                flags.append("model_match_only")
        desc = " ".join(str(x) for x in (ln.get("description"), ln.get("model")) if x)
        if not cfg:
            cat = (product or {}).get("category") or ""
            flags.append("spare_part" if _SPARE.search(desc) or re.search(r"part|spare|accessor", cat, re.I)
                         else "unknown_code")
        status_txt = f"{(product or {}).get('status', '')} {(cfg or {}).get('approval_status', '')}".lower()
        if "discontinu" in status_txt:
            flags.append("discontinued")
        if serials and len(serials) != qty:
            flags.append("serial_mismatch")
        if len(set(serials)) != len(serials):
            flags.append("duplicate_serials")
        pricing = None
        if cfg:
            pricing = await _annotate_asset(org_id, {"model": cfg.get("model"), "console_type": cfg.get("console_type") or ""})
            if pricing["pricing_status"] != "SUPPORTED":
                flags.append({"RRP_REQUIRED": "no_approved_price", "PROVISIONAL": "price_provisional",
                              "NOT_ELIGIBLE": "unsupported", "SUPPORTABILITY_REVIEW": "unsupported"}.get(
                                  pricing["pricing_status"], "no_approved_price"))
        existing, covered = [], []
        if linked_org and serials:
            async for eq in db.equipment.find({"organization_id": linked_org, "serial_number": {"$in": serials}},
                                              {"_id": 0, "id": 1, "serial_number": 1, "contract_cover": 1}):
                existing.append({"id": eq["id"], "serial_number": eq["serial_number"]})
                cid = (eq.get("contract_cover") or {}).get("contract_id")
                if cid:
                    covered.append(cid)
        if covered and await _active_contract_ids(org_id, set(covered)):
            flags.append("already_covered")
        if doc_type == "maintenance_invoice":
            flags.append("evidence_only_price")
        blocking = {"unknown_code", "spare_part", "already_covered", "variant_review", "serial_mismatch",
                    "duplicate_serials", "discontinued", "model_match_only", "unsupported"}
        auto = bool(cfg) and basis == "exact product code" and not (set(flags) & blocking)
        out.append({
            "line_no": n, "item_code": code or None, "make": ln.get("make"), "model": ln.get("model"),
            "description": ln.get("description"), "quantity": qty, "serials": serials,
            "document_amount": ln.get("amount"),
            "matched": {"config_id": cfg.get("id"), "model": cfg.get("model"), "console_type": cfg.get("console_type") or "",
                        "reference_sku": cfg.get("reference_sku"), "basis": basis,
                        "pricing_status": (pricing or {}).get("pricing_status")} if cfg else None,
            "existing_equipment": existing, "flags": flags,
            "decision": "accepted" if auto else ("excluded" if set(flags) & {"spare_part", "already_covered"}
                                                 else "review"),
            "auto_accepted": auto, "needs_review": not auto,
        })
    return out


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
