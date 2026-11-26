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
             "quantity": int|null, "serials": [str], "amount": number|null}}]}}
Rules: copy codes, models, serial numbers and QUANTITIES EXACTLY as printed; never change a quantity to match the
number of serials; never invent values (use null / []).
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
    """Read every page: text pages in bounded sections, scanned pages with vision in batches.
    Header fields come from the first part that has them; lines from all parts keep their source pages."""
    import asyncio
    from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
    from utils.afs_doc_sections import page_images, read_document
    from utils.ai_guardrails import sanitize_prompt
    from utils.database import EMERGENT_LLM_KEY
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "Document extraction is not configured.")
    doc = read_document("document.pdf", pdf, max_chars=6000)  # keeps each JSON reply well inside output limits
    label = DOC_TYPES[doc_type].replace(" (evidence only)", "")
    sem = asyncio.Semaphore(3)

    async def _ask(part: str, text: str = "", images: list | None = None):
        async with sem:
            chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"cm_qimp_{uuid.uuid4().hex[:8]}",
                           system_message="You extract structured data from business documents. Return ONLY valid JSON."
                           ).with_model("anthropic", "claude-haiku-4-5")
            msg = (UserMessage(text=_PROMPT.format(label=label, text="(scanned — read the attached pages)"),
                               file_contents=[ImageContent(image_base64=b) for b in images]) if images
                   else UserMessage(text=_PROMPT.format(label=label, text=sanitize_prompt(text, max_chars=len(text) + 1))))
            try:
                raw = await chat.send_message(msg)
            except Exception:  # noqa: BLE001
                return part, None
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
        try:
            out = json.loads(raw)
            return part, out if isinstance(out, dict) else None
        except ValueError:
            return part, None

    jobs = [_ask(s["label"], s["text"]) for s in doc["sections"]]
    jobs += [_ask(f"scanned pages {b[0]}–{b[-1]}", images=page_images(pdf, b)) for b in doc["vision_batches"]]
    if not jobs:
        raise HTTPException(422, "The document has no readable pages.")
    short: list = []
    results = list(await asyncio.gather(*jobs))
    expected_re = re.compile(r"\b(?:qty|quantity)\b", re.I)
    for i, sec in enumerate(doc["sections"]):
        want = sum(1 for t in sec["text"].splitlines() if expected_re.search(t))
        got = len((results[i][1] or {}).get("lines") or [])
        if want and got < want:  # AI dropped lines → re-read this part in halves once
            ls = sec["text"].splitlines()
            a, b = await asyncio.gather(_ask(sec["label"], "\n".join(ls[:len(ls) // 2])), _ask(sec["label"], "\n".join(ls[len(ls) // 2:])))
            if a[1] is not None and b[1] is not None:
                retry = {**a[1], "lines": (a[1].get("lines") or []) + (b[1].get("lines") or [])}
                if len(retry["lines"]) >= got:
                    results[i] = (sec["label"], retry)
            if len((results[i][1] or {}).get("lines") or []) < want:
                short.append(f"{sec['label']}: {want} quantity line(s) printed, {len((results[i][1] or {}).get('lines') or [])} read")
    ok = [(part, out) for part, out in results if out is not None]
    if not ok:
        raise HTTPException(422, "The document could not be read — check it is a clear invoice or delivery note.")
    merged: dict = {}
    lines: list = []
    for part, out in ok:
        for k, v in out.items():
            if k != "lines" and v not in (None, "", []) and merged.get(k) in (None, "", []):
                merged[k] = v
        lines += [{**ln, "source": part} for ln in out.get("lines") or [] if isinstance(ln, dict)]
    merged["lines"] = verify_quantities(lines, pdf)
    cov = doc["coverage"]
    failed = [part for part, out in results if out is None]
    merged["coverage"] = {**cov, "parts_total": len(results), "parts_read": len(ok), "parts_failed": failed + short,
                          "notes": (cov.get("notes") or []) + short, "complete": not failed and not short and not cov.get("unread")}
    return merged


_QTY_LABEL = re.compile(r"\b(?:qty|quantity)\b", re.I)
_QTY = re.compile(r"\b(?:qty|quantity|units?)\s*[:.=]?\s*(\d+(?:\.\d+)?)\b", re.I)


def verify_quantities(lines: list, pdf: bytes) -> list:
    """Check every AI-read quantity against the printed page text. The printed value wins; any change
    is recorded (quantity_ai → quantity). Scanned pages / unlabelled quantities stay 'unverified'."""
    from utils.afs_doc_sections import pdf_pages
    try:
        pages = pdf_pages(pdf)
    except Exception:  # noqa: BLE001
        return lines
    page_lines = {i: [t for t in txt.splitlines() if t.strip()] for i, txt in enumerate(pages, 1)}
    used: set = set()

    def _range(src: str) -> list:
        nums = [int(n) for n in re.findall(r"page (\d+)", src or "")]
        return list(range(min(nums), max(nums) + 1)) if nums else list(page_lines)

    for ln in lines:
        serials = [str(x).strip() for x in ln.get("serials") or [] if str(x).strip()]
        code = (ln.get("item_code") or "").strip()
        hit = None
        for pg in _range(ln.get("source", "")):
            for k, text in enumerate(page_lines.get(pg, [])):
                if (pg, k) in used:
                    continue
                if (serials and any(re.search(rf"(?<![\w-]){re.escape(sn)}(?![\w-])", text) for sn in serials)) or (
                        not serials and code and re.search(rf"(?<![\w-]){re.escape(code)}(?![\w-])", text)):
                    hit = (pg, k, text)
                    break
            if hit:
                break
        ai = ln.get("quantity")
        if not hit:  # scanned page / line not locatable — the coordinator must confirm the AI reading
            ln["qty_validation"] = "unverified"
            continue
        used.add(hit[:2])
        ln["source_text"] = hit[2].strip()[:300]
        m = _QTY.search(hit[2])
        if not m:
            if _QTY_LABEL.search(hit[2]):  # "Qty two", "Qty -" — a quantity is printed but unreadable
                ln["quantity_ai"], ln["quantity"], ln["qty_validation"] = ai, None, "invalid"
                continue
            nums = re.findall(r"(?<![\w.£,-])(\d{1,4})(?![\w.,%])", hit[2])
            if ai is not None and str(ai).isdigit() and str(int(ai)) in nums:
                ln["qty_validation"] = "column_match"  # unlabelled quantity column contains the same number
            else:
                ln["quantity_ai"], ln["quantity"], ln["qty_validation"] = ai, None, "missing"
            continue
        printed = float(m.group(1))
        ln["quantity_text"] = m.group(0)
        if printed != int(printed) or printed <= 0:
            ln["quantity"], ln["qty_validation"] = None, "invalid"
            continue
        try:
            same = ai is not None and float(ai) == printed
        except (TypeError, ValueError):
            same = False
        if not same:
            ln["quantity_ai"], ln["quantity"], ln["qty_validation"] = ai, int(printed), "corrected_from_source"
        else:
            ln["quantity"], ln["qty_validation"] = int(printed), "verified"
    return lines


_CI = {"locale": "en", "strength": 2}          # case-insensitive, index-backed
_PROJ = {"_id": 0, "id": 1, "name": 1, "legal_name": 1, "postcode": 1, "linked_organization_id": 1,
         "sage_account": 1, "sage_customer_reference": 1, "sage_customer_id": 1, "account_number": 1}
_SUFFIX = re.compile(r"[\s,.]+(ltd|limited|plc|llp)\.?$", re.I)


async def ensure_indexes() -> None:
    for keys in ([("organization_id", 1), ("sage_account", 1)], [("organization_id", 1), ("sage_customer_reference", 1)],
                 [("organization_id", 1), ("account_number", 1)], [("organization_id", 1), ("linked_organization_id", 1)],
                 [("organization_id", 1), ("postcode", 1)]):
        await db.crm2_companies.create_index(keys)
    await db.crm2_companies.create_index([("organization_id", 1), ("name", 1)], collation=_CI, name="org_name_ci")
    await db.crm2_companies.create_index([("organization_id", 1), ("legal_name", 1)], collation=_CI, name="org_legal_ci")
    await db.sites.create_index([("postcode", 1)])


def _name_variants(name: str) -> list:
    base = _SUFFIX.sub("", (name or "").strip()).strip()
    return list({v for v in (name.strip(), base, f"{base} Ltd", f"{base} Limited", f"{base} PLC") if v})


def _pc_variants(pc: str) -> list:
    p = _pc(pc)
    return list({p, f"{p[:-3]} {p[-3:]}"} if len(p) > 4 else {p}) if p else []


async def match_customer(org_id: str, hints: dict, limit: int = 8) -> dict:
    """Bounded, index-backed lookups in priority order: account reference →
    exact legal/trading name (+ postcode / site evidence) → candidates for the
    coordinator. Never fuzzy-selects, never creates, never merges."""
    ref = (hints.get("account_ref") or "").strip()
    name = (hints.get("customer_name") or "").strip()
    pcs = _pc_variants(hints.get("postcode"))
    base = {"organization_id": org_id, "archived": {"$ne": True}}
    if ref:
        hits = await db.crm2_companies.find({**base, "$or": [
            {"sage_account": ref}, {"sage_customer_reference": ref}, {"sage_customer_id": ref}, {"account_number": ref}]},
            _PROJ).limit(3).to_list(3)
        if len(hits) == 1:
            return {"status": "matched", "company": hits[0], "basis": f"account reference {ref}", "candidates": hits}
    pc_orgs = set()
    if pcs:
        pc_orgs = {x["organization_id"] for x in await db.sites.find({"postcode": {"$in": pcs}}, {"_id": 0, "organization_id": 1}).limit(200).to_list(200)}

    def has_pc(co):
        return bool(pcs) and (_pc(co.get("postcode")) in {_pc(p) for p in pcs} or co.get("linked_organization_id") in pc_orgs)
    exact = []
    if name:
        variants = _name_variants(name)
        exact = await db.crm2_companies.find({**base, "$or": [{"name": {"$in": variants}}, {"legal_name": {"$in": variants}}]},
                                             _PROJ).collation(_CI).limit(limit).to_list(limit)
    for co in exact:
        co["name_match"], co["postcode_match"] = "exact", has_pc(co)
    strong = [co for co in exact if co["postcode_match"]] if pcs else exact
    if len(strong) == 1 and (strong[0]["postcode_match"] or len(exact) == 1):
        basis = "legal name + postcode" if strong[0]["postcode_match"] else "exact legal name"
        return {"status": "matched", "company": strong[0], "basis": basis, "candidates": exact}
    # Review candidates: same postcode/site, or names starting with the document's first word.
    seen = {co["id"] for co in exact}
    cands = list(exact)
    extra_q = []
    if pcs:
        extra_q.append({"postcode": {"$in": pcs}})
        if pc_orgs:
            extra_q.append({"linked_organization_id": {"$in": list(pc_orgs)}})
    word = re.sub(r"[^A-Za-z0-9 ]", " ", _SUFFIX.sub("", name)).split()
    if word and len(word[0]) >= 3:
        rx = {"$regex": f"^{re.escape(word[0])}", "$options": "i"}
        extra_q += [{"name": rx}, {"legal_name": rx}]
    if extra_q:
        for co in await db.crm2_companies.find({**base, "$or": extra_q}, _PROJ).limit(limit * 3).to_list(limit * 3):
            if co["id"] in seen:
                continue
            seen.add(co["id"])
            co["name_match"], co["postcode_match"] = "similar", has_pc(co)
            cands.append(co)
    cands.sort(key=lambda x: (x["name_match"] != "exact", not x["postcode_match"]))
    return {"status": "review" if cands else "not_found", "company": None, "basis": None, "candidates": cands[:limit]}


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
    rgs = {r["name"]: r for r in await db.crm2_afs_rate_groups.find({"organization_id": org_id}, {"_id": 0}).to_list(200)}

    def tariff_ok(cfg):
        rg = rgs.get(cfg.get("rate_group") or "Standard Equipment") or {}
        return float(rg.get("standard_pct") or 0) > 0 or float(rg.get("fixed_uplift") or 0) > 0
    by_sku = {}
    for cfgs in idx.values():
        for cfg in cfgs:
            if cfg.get("reference_sku"):
                by_sku.setdefault(cfg["reference_sku"].strip().upper(), []).append(cfg)
    out = []
    for n, ln in enumerate(lines, start=1):
        code = (ln.get("item_code") or "").strip()
        # Never default or clamp: an unreadable quantity stays empty and blocks the line until confirmed.
        try:
            qty = int(ln["quantity"]) if ln.get("quantity") not in (None, "") and float(ln["quantity"]) == int(float(ln["quantity"])) else None
            qty = qty if qty and qty > 0 else None
        except (TypeError, ValueError):
            qty = None
        serials = [str(s).strip() for s in ln.get("serials") or [] if str(s).strip()]
        flags, cfg, basis = [], None, None
        product = await db.crm_products.find_one({"organization_id": org_id, "sku": code}, {"_id": 0}) if code else None
        cands = by_sku.get(code.upper(), []) if code else []
        if not cands and product and product.get("model"):
            cands = idx.get(product["model"].strip().lower(), [])
        options = []
        if cands:
            variants = {(c.get("model"), c.get("console_type") or "") for c in cands}
            if len(variants) > 1:  # never pick a variant for the coordinator
                flags.append("variant_review")
                options = [{"config_id": c["id"], "model": c.get("model"), "console_type": c.get("console_type") or ""}
                           for c in cands]
            else:
                from routes.crm_afs_onboarding import _rank_cfg
                cfg, basis = sorted(cands, key=_rank_cfg, reverse=True)[0], "exact product code"
        if not cands:
            cfg, _, _st = _match_row(idx, ln.get("model"), ln.get("make"))
            if cfg:
                basis = "model name"
                flags.append("model_match_only")
        desc = " ".join(str(x) for x in (ln.get("description"), ln.get("model")) if x)
        if not cfg and not options:
            cat = (product or {}).get("category") or ""
            flags.append("spare_part" if _SPARE.search(desc) or re.search(r"part|spare|accessor", cat, re.I)
                         else "unknown_code")
        status_txt = f"{(product or {}).get('status', '')} {(cfg or {}).get('approval_status', '')}".lower()
        if "discontinu" in status_txt:
            flags.append("discontinued")
        if qty is None:
            flags.append("quantity_unconfirmed")
        elif ln.get("qty_validation") == "corrected_from_source":
            flags.append("quantity_corrected")
        elif ln.get("qty_validation") == "unverified":
            flags.append("quantity_unverified")
        if serials and qty and len(serials) != qty:
            flags.append("serial_mismatch")
        if len(set(serials)) != len(serials):
            flags.append("duplicate_serials")
        commercial = None
        if cfg:  # pricing is a separate decision from identifying the machine
            pricing = await _annotate_asset(org_id, {"model": cfg.get("model"), "console_type": cfg.get("console_type") or ""})
            commercial = _commercial(pricing, cfg, tariff_ok(cfg))
            if commercial["status"] == "not_eligible":
                flags.append("unsupported")
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
        blocking = {"unknown_code", "spare_part", "already_covered", "variant_review", "serial_mismatch", "quantity_unconfirmed",
                    "quantity_unverified",
                    "duplicate_serials", "discontinued", "model_match_only", "unsupported"}
        ident_flags = set(flags) & (blocking - {"already_covered", "unsupported"})
        identification = ("matched" if cfg and not ident_flags else "spare_part" if "spare_part" in flags
                          else "unknown" if "unknown_code" in flags else "review")
        auto = bool(cfg) and basis == "exact product code" and not (set(flags) & blocking)
        out.append({
            "line_no": n, "item_code": code or None, "make": ln.get("make"), "model": ln.get("model"),
            "description": ln.get("description"), "quantity": qty, "serials": serials,
            "source": ln.get("source"), "source_text": ln.get("source_text"), "quantity_text": ln.get("quantity_text"),
            "quantity_ai": ln.get("quantity_ai"), "qty_validation": ln.get("qty_validation") or "unverified",
            "document_amount": ln.get("amount"),
            "matched": {"config_id": cfg.get("id"), "model": cfg.get("model"), "console_type": cfg.get("console_type") or "",
                        "reference_sku": cfg.get("reference_sku"), "basis": basis,
                        "pricing_status": (commercial or {}).get("pricing_status")} if cfg else None,
            "identification": identification, "commercial": commercial,
            "variant_options": options, "existing_equipment": existing, "flags": flags,
            "decision": "accepted" if auto else ("excluded" if set(flags) & {"spare_part", "already_covered", "unsupported"}
                                                 else "review"),
            "auto_accepted": auto, "needs_review": not auto,
        })
    return out


COMMERCIAL_LABELS = {
    "price_approved": "Machine matched — Price approved",
    "price_requires_approval": "Machine matched — Price requires approval",
    "price_held": "Machine matched — Price held",
    "tariff_missing": "Machine matched — Maintenance tariff missing",
    "supportability_review": "Machine matched — Supportability review required",
    "not_eligible": "Machine matched — Not eligible for maintenance",
}


def _commercial(pricing: dict, cfg: dict, tariff_ok: bool = True) -> dict:
    """Commercial readiness from the existing pricing engine's verdict (never a substitute price)."""
    st = pricing.get("pricing_status")
    approval = (cfg.get("approval_status") or "").lower()
    if st == "NOT_ELIGIBLE":
        key = "not_eligible"
    elif st == "SUPPORTABILITY_REVIEW":
        key = "supportability_review"
    elif "hold" in approval:
        key = "price_held"
    elif st in ("RRP_REQUIRED", "PROVISIONAL"):
        key = "price_requires_approval"
    elif not tariff_ok:
        key = "tariff_missing"
    else:
        key = "price_approved"
    return {"status": key, "label": COMMERCIAL_LABELS[key], "ready": key == "price_approved",
            "pricing_status": st, "approval_status": cfg.get("approval_status"),
            "eligible": key != "not_eligible"}


def summarise(lines: list) -> dict:
    inc = [ln for ln in lines if ln["decision"] != "excluded"]
    return {"lines": len(lines), "matched": sum(1 for ln in lines if ln.get("identification") == "matched"),
            "needs_identification": sum(1 for ln in lines if ln["decision"] == "review"),
            "commercially_ready": sum(1 for ln in inc if (ln.get("commercial") or {}).get("ready")),
            "price_approval_required": sum(1 for ln in inc if ln.get("commercial") and not ln["commercial"]["ready"]),
            "excluded": sum(1 for ln in lines if ln["decision"] == "excluded")}


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
