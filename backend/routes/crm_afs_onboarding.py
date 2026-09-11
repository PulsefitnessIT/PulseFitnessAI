"""
Aftersales Estate Onboarding Importer
=====================================
Turn a messy inherited customer workbook (or invoice/agreement) into a clean
Pulse estate + draft maintenance contracts. Built for the reality that a new
customer's data (e.g. Wiltshire Council: 707 assets, 17 sites, mixed makes,
"Worn away" serials, missing costs) is confusing and not yet on the system.

Pipeline (manage-by-exception, nothing commits until the queue is cleared):
  upload → detect sheets + header row → column mapping → clean/normalise →
  deterministic model match against the Pulse config master → DUAL pricing
  (inherited cost carried forward vs Pulse-engine price, side by side) →
  exception queue → commit (customer org + CRM company + sites + equipment
  register + grouped DRAFT contracts, with equipment cover linked).

Pricing is 100% deterministic — reuses the same engine as the quoter. The
importer never invents a price: unmatched/RRP-less assets price to 0 (Pulse)
and fall back to the inherited cost, flagged for review.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import base64
import io
import re
import uuid

from utils.database import db
from routes.crm_auth import get_crm_user
from utils.crm_audit import record_audit
from routes.crm_aftersales import _compute_quote, _PUBLIC

router = APIRouter(prefix="/crm/v2/aftersales/onboarding", tags=["Aftersales Onboarding"])


def _id():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc).isoformat()


def _org(user):
    return user.get("organization_id") or "__none__"


def _of(user):
    return {"organization_id": _org(user)}


# ── Canonical fields we map a messy sheet onto ──────────────────────────────
CANON_FIELDS = [
    "site_code", "site_name", "description", "make", "model", "serial",
    "install_date", "warranty_end", "warranty_status", "contract_start",
    "annual_cost", "monthly_cost", "notes",
]

# Keyword hints for deterministic auto-mapping of arbitrary headers.
_MAP_HINTS = {
    "site_code": ["site code", "site no", "site id", "location code"],
    "site_name": ["site name", "site", "location", "centre", "facility"],
    "description": ["equipment description", "description", "asset", "equipment", "item"],
    "make": ["make", "manufacturer", "brand", "supplier"],
    "model": ["model", "model code", "type", "product"],
    "serial": ["serial", "serial number", "s/n", "sn"],
    "install_date": ["install date", "installation", "installed", "date installed"],
    "warranty_end": ["warranty end", "warranty expiry", "warranty exp", "end of warranty"],
    "warranty_status": ["warranty status", "status", "cover", "contract status"],
    "contract_start": ["contract start", "contract from", "start date", "cover start"],
    "annual_cost": ["annual contract cost", "annual cost", "annual value", "per annum", "yearly"],
    "monthly_cost": ["monthly contract cost", "monthly cost", "per month", "monthly"],
    "notes": ["notes", "comments", "note", "remark"],
}

_BAD_SERIAL = {"", "worn away", "n/a", "na", "none", "unknown", "tbc", "-", "worn"}


def _score_header(values):
    """How many mapping keywords a candidate header row hits."""
    joined = [str(v).strip().lower() for v in values if v not in (None, "")]
    score = 0
    for hints in _MAP_HINTS.values():
        if any(any(h == cell or h in cell for h in hints) for cell in joined):
            score += 1
    return score


def _auto_map(headers):
    """Best-effort map header labels → canonical fields (editable in UI)."""
    used, cmap = set(), {}
    hl = [(i, str(h).strip().lower()) for i, h in enumerate(headers) if h not in (None, "")]
    for field, hints in _MAP_HINTS.items():
        best = None
        for i, cell in hl:
            if i in used:
                continue
            if any(cell == h for h in hints):        # exact first
                best = i; break
        if best is None:
            for i, cell in hl:
                if i in used:
                    continue
                if any(h in cell for h in hints):     # contains
                    best = i; break
        if best is not None:
            cmap[field] = best
            used.add(best)
    return cmap


def _read_workbook(data: bytes):
    import openpyxl
    return openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)


def _sheet_meta(ws):
    rows = list(ws.iter_rows(min_row=1, max_row=min(8, ws.max_row or 1), values_only=True))
    best_row, best_score = 1, -1
    for idx, r in enumerate(rows, start=1):
        s = _score_header(r or [])
        if s > best_score:
            best_score, best_row = s, idx
    headers = [("" if v is None else str(v)) for v in (rows[best_row - 1] if rows else [])]
    return {"name": ws.title, "n_rows": (ws.max_row or 0), "n_cols": (ws.max_column or 0),
            "header_row": best_row, "headers": headers, "header_score": best_score}


# ══════════════════════════════════════════════════════════════════════════
# 1) ANALYZE — upload a workbook, detect sheets + header row + suggested map
# ══════════════════════════════════════════════════════════════════════════
@router.post("/analyze")
async def analyze(file: UploadFile = File(...), user=Depends(get_crm_user)):
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 20MB).")
    try:
        wb = _read_workbook(raw)
    except Exception as e:
        raise HTTPException(400, f"Could not read the workbook: {e}")
    sheets = [_sheet_meta(ws) for ws in wb.worksheets]
    if not sheets:
        raise HTTPException(400, "No sheets found in the workbook.")
    # Suggested sheet = the one with the most rows AND a recognisable header.
    suggested = max(sheets, key=lambda s: (s["header_score"], s["n_rows"]))
    cmap = _auto_map(suggested["headers"])
    # sample rows from the suggested sheet (just below the header row)
    ws = wb[suggested["name"]]
    sample = []
    for r in ws.iter_rows(min_row=suggested["header_row"] + 1,
                          max_row=suggested["header_row"] + 3, values_only=True):
        sample.append([("" if v is None else str(v)[:40]) for v in r])

    doc = {
        "id": _id(), "organization_id": _org(user), "created_by": user.get("email"),
        "created_at": _now(), "updated_at": _now(), "status": "draft",
        "source": "spreadsheet", "filename": file.filename,
        "file_b64": base64.b64encode(raw).decode("ascii"),
        "sheets": [{k: v for k, v in s.items() if k != "headers"} | {"headers": s["headers"]} for s in sheets],
        "suggested_sheet": suggested["name"], "column_map": cmap,
    }
    await db.crm2_afs_onboarding.insert_one(dict(doc))
    doc.pop("file_b64", None); doc.pop("_id", None)
    return {"import_id": doc["id"], "filename": file.filename, "sheets": doc["sheets"],
            "suggested_sheet": suggested["name"], "suggested_header_row": suggested["header_row"],
            "column_map": cmap, "sample_rows": sample, "canon_fields": CANON_FIELDS}


# ══════════════════════════════════════════════════════════════════════════
# 2) BUILD — parse chosen sheet with the map, clean, match, dual-price, group
# ══════════════════════════════════════════════════════════════════════════
def _norm_model_tokens(s):
    s = (str(s) if s is not None else "").strip()
    if not s:
        return []
    toks = [s]
    base = re.split(r"[-/ ]", s)[0].strip()
    if base and base.lower() != s.lower():
        toks.append(base)
    return toks


async def _config_index(org_id):
    idx = {}
    async for c in db.crm2_afs_service_configs.find({"organization_id": org_id}, _PUBLIC):
        m = (c.get("model") or "").strip().lower()
        if m:
            idx.setdefault(m, []).append(c)
    return idx


def _rank_cfg(c):
    rrp = c.get("manual_rrp_override") or c.get("rrp_snapshot") or 0
    hold = "hold" in (c.get("approval_status", "") or "").lower()
    approved = "provisional" not in (c.get("approval_status", "") or "").lower() and not hold
    return (1 if rrp > 0 else 0, 1 if not hold else 0, 1 if approved else 0, rrp)


def _match_row(idx, model_raw, make_raw):
    """Deterministic match: try model tokens then make tokens (columns are
    often swapped in inherited sheets). Returns (cfg, matched_code, status)."""
    for src in (model_raw, make_raw):
        for tok in _norm_model_tokens(src):
            cands = idx.get(tok.lower())
            if cands:
                cfg = sorted(cands, key=_rank_cfg, reverse=True)[0]
                rrp = cfg.get("manual_rrp_override") or cfg.get("rrp_snapshot") or 0
                return cfg, cfg.get("model"), ("MATCHED" if rrp > 0 else "RRP_REQUIRED")
    return None, None, "NOT_MATCHED"


def _num(v):
    if v in (None, ""):
        return None
    try:
        return round(float(str(v).replace("£", "").replace(",", "").strip()), 2)
    except (ValueError, TypeError):
        return None


def _str(v):
    return "" if v in (None,) else str(v).strip()


def _date10(v):
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    return s[:10] if s else None


def _clean_row(vals, cmap):
    def g(field):
        i = cmap.get(field)
        return vals[i] if (i is not None and i < len(vals)) else None
    serial = _str(g("serial"))
    return {
        "site_code": _str(g("site_code")),
        "site_name": _str(g("site_name")) or "Unassigned site",
        "description": _str(g("description")),
        "make": _str(g("make")),
        "model": _str(g("model")),
        "serial": serial,
        "install_date": _date10(g("install_date")),
        "warranty_end": _date10(g("warranty_end")),
        "warranty_status": _str(g("warranty_status")),
        "contract_start": _date10(g("contract_start")),
        "annual_cost": _num(g("annual_cost")),
        "monthly_cost": _num(g("monthly_cost")),
        "notes": _str(g("notes")),
    }


def _row_exceptions(clean, status):
    ex = []
    if (clean["serial"] or "").strip().lower() in _BAD_SERIAL:
        ex.append("missing_serial")
    if status == "NOT_MATCHED":
        ex.append("unmatched_model")
    if status == "RRP_REQUIRED":
        ex.append("no_pulse_price")
    if clean["annual_cost"] in (None, 0) and status == "NOT_MATCHED":
        ex.append("missing_cost")
    if not clean["make"] and not clean["model"]:
        ex.append("blank_make_model")
    return ex


class BuildIn(BaseModel):
    sheet_name: str
    header_row: int = 2
    column_map: Dict[str, int]
    customer_name: str
    contract_type: str = "gold"
    pricing_level: str = "standard"
    grouping: str = "per_site"  # per_site | master | per_status


@router.post("/{import_id}/build")
async def build(import_id: str, body: BuildIn, user=Depends(get_crm_user)):
    of = _of(user)
    org_id = _org(user)
    doc = await db.crm2_afs_onboarding.find_one({"id": import_id, **of})
    if not doc:
        raise HTTPException(404, "Import not found")
    if "site_name" not in body.column_map and "site_code" not in body.column_map:
        raise HTTPException(400, "Map at least a Site name or Site code column.")
    if "model" not in body.column_map and "description" not in body.column_map:
        raise HTTPException(400, "Map at least a Model or Equipment description column.")

    wb = _read_workbook(base64.b64decode(doc["file_b64"]))
    if body.sheet_name not in wb.sheetnames:
        raise HTTPException(400, "Sheet not found in the uploaded file.")
    ws = wb[body.sheet_name]

    idx = await _config_index(org_id)
    rows, lines = [], []
    for vals in ws.iter_rows(min_row=body.header_row + 1, values_only=True):
        vals = list(vals)
        if not any(v not in (None, "") for v in vals[:14]):
            continue
        clean = _clean_row(vals, body.column_map)
        if not clean["description"] and not clean["model"] and not clean["make"]:
            continue
        cfg, matched_code, status = _match_row(idx, clean["model"], clean["make"])
        rows.append({
            "index": len(rows), "clean": clean,
            "match": {"config_id": (cfg or {}).get("id"), "matched_code": matched_code,
                      "pricing_status": status,
                      "config_name": (cfg or {}).get("display_name") or (cfg or {}).get("service_name")},
            "inherited": {"annual": clean["annual_cost"],
                          "monthly": clean["monthly_cost"] or (round(clean["annual_cost"] / 12, 2) if clean["annual_cost"] else None)},
            "pulse": {"annual": 0.0},
            "exceptions": _row_exceptions(clean, status),
            "include": True,
            "chosen_price": "inherited",  # default: administer at the price they already pay
        })
        lines.append({"config_id": (cfg or {}).get("id"), "qty": 1} if cfg else {"model": "__none__", "qty": 1})

    # Deterministic Pulse pricing in ONE engine call (per-asset annual = gold line × tier factor).
    if lines:
        quote = await _compute_quote(org_id, lines, contract_type=body.contract_type,
                                     pricing_level=body.pricing_level)
        factor = float(quote["summary"].get("contract_factor", 1.0) or 1.0)
        for r, pl in zip(rows, quote["lines"]):
            r["pulse"]["annual"] = round(float(pl.get("annual_line_gold", 0) or 0) * factor, 2)
            # If Pulse can't price it, default the chosen price to the inherited cost.
            if r["pulse"]["annual"] <= 0 and r["inherited"]["annual"]:
                r["chosen_price"] = "inherited"
            elif r["pulse"]["annual"] > 0 and r["chosen_price"] == "inherited" and not r["inherited"]["annual"]:
                r["chosen_price"] = "pulse"

    summary = _summarise(rows)
    await db.crm2_afs_onboarding.update_one({"id": import_id, **of}, {"$set": {
        "status": "reviewed", "sheet_name": body.sheet_name, "header_row": body.header_row,
        "column_map": body.column_map, "customer_name": body.customer_name.strip(),
        "contract_type": body.contract_type, "pricing_level": body.pricing_level,
        "grouping": body.grouping, "rows": rows, "summary": summary, "updated_at": _now()}})
    await record_audit(entity_type="afs_onboarding", entity_id=import_id, action="build", user=user,
                       extra={"rows": len(rows), "customer": body.customer_name})
    return {"import_id": import_id, "customer_name": body.customer_name.strip(),
            "grouping": body.grouping, "summary": summary, "rows": rows}


def _row_value(r):
    """The annual value that will carry into the contract for this row."""
    if not r.get("include"):
        return 0.0
    if r.get("chosen_price") == "pulse" and r["pulse"]["annual"] > 0:
        return r["pulse"]["annual"]
    return float(r["inherited"]["annual"] or 0)


def _summarise(rows):
    inc = [r for r in rows if r.get("include")]
    sites = {}
    for r in rows:
        sites.setdefault(r["clean"]["site_name"], 0)
        sites[r["clean"]["site_name"]] += 1
    def cnt(ex):
        return sum(1 for r in rows if ex in r["exceptions"])
    matched = sum(1 for r in rows if r["match"]["pricing_status"] == "MATCHED")
    return {
        "total_rows": len(rows), "included": len(inc), "sites": len(sites),
        "site_counts": sites,
        "matched": matched, "unmatched": cnt("unmatched_model"),
        "missing_serial": cnt("missing_serial"), "missing_cost": cnt("missing_cost"),
        "no_pulse_price": cnt("no_pulse_price"),
        "exceptions_total": sum(1 for r in rows if r["exceptions"]),
        "inherited_annual": round(sum(float(r["inherited"]["annual"] or 0) for r in inc), 2),
        "pulse_annual": round(sum(r["pulse"]["annual"] for r in inc), 2),
        "chosen_annual": round(sum(_row_value(r) for r in rows), 2),
        "on_contract": sum(1 for r in inc if "contract" in (r["clean"]["warranty_status"] or "").lower()),
        "under_warranty": sum(1 for r in inc if "warranty" in (r["clean"]["warranty_status"] or "").lower()),
    }


# ══════════════════════════════════════════════════════════════════════════
# 3) PATCH ROWS — resolve exceptions (fix serial / cost / match / include)
# ══════════════════════════════════════════════════════════════════════════
class RowUpdate(BaseModel):
    index: int
    serial: Optional[str] = None
    annual_cost: Optional[float] = None
    monthly_cost: Optional[float] = None
    include: Optional[bool] = None
    chosen_price: Optional[str] = None       # inherited | pulse
    config_id: Optional[str] = None          # manual model match


class PatchIn(BaseModel):
    updates: List[RowUpdate]


@router.patch("/{import_id}/rows")
async def patch_rows(import_id: str, body: PatchIn, user=Depends(get_crm_user)):
    of = _of(user)
    org_id = _org(user)
    doc = await db.crm2_afs_onboarding.find_one({"id": import_id, **of})
    if not doc:
        raise HTTPException(404, "Import not found")
    rows = doc.get("rows", [])
    by_index = {r["index"]: r for r in rows}
    reprice = []
    for u in body.updates:
        r = by_index.get(u.index)
        if not r:
            continue
        if u.serial is not None:
            r["clean"]["serial"] = u.serial.strip()
        if u.annual_cost is not None:
            r["inherited"]["annual"] = round(float(u.annual_cost), 2)
            r["inherited"]["monthly"] = round(float(u.annual_cost) / 12, 2)
        if u.monthly_cost is not None:
            r["inherited"]["monthly"] = round(float(u.monthly_cost), 2)
            r["inherited"]["annual"] = round(float(u.monthly_cost) * 12, 2)
        if u.include is not None:
            r["include"] = bool(u.include)
        if u.chosen_price in ("inherited", "pulse"):
            r["chosen_price"] = u.chosen_price
        if u.config_id is not None:
            cfg = await db.crm2_afs_service_configs.find_one({"id": u.config_id, **of}, _PUBLIC)
            if cfg:
                rrp = cfg.get("manual_rrp_override") or cfg.get("rrp_snapshot") or 0
                r["match"] = {"config_id": cfg["id"], "matched_code": cfg.get("model"),
                              "pricing_status": "MATCHED" if rrp > 0 else "RRP_REQUIRED",
                              "config_name": cfg.get("display_name") or cfg.get("service_name")}
                reprice.append(r)
        r["exceptions"] = _row_exceptions(r["clean"], r["match"]["pricing_status"])

    if reprice:
        quote = await _compute_quote(org_id, [{"config_id": r["match"]["config_id"], "qty": 1} for r in reprice],
                                     contract_type=doc.get("contract_type", "gold"),
                                     pricing_level=doc.get("pricing_level", "standard"))
        factor = float(quote["summary"].get("contract_factor", 1.0) or 1.0)
        for r, pl in zip(reprice, quote["lines"]):
            r["pulse"]["annual"] = round(float(pl.get("annual_line_gold", 0) or 0) * factor, 2)

    summary = _summarise(rows)
    await db.crm2_afs_onboarding.update_one({"id": import_id, **of},
                                            {"$set": {"rows": rows, "summary": summary, "updated_at": _now()}})
    return {"summary": summary, "rows": rows}


# ══════════════════════════════════════════════════════════════════════════
# 4) COMMIT — create customer org + CRM company + sites + equipment register
#             + grouped DRAFT contracts (inherited/Pulse chosen value), cover
# ══════════════════════════════════════════════════════════════════════════
_OPERATOR_COMPANY = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"  # Pulse Fitness Ltd


def _group_key(r, grouping):
    if grouping == "master":
        return "__all__"
    if grouping == "per_status":
        st = (r["clean"]["warranty_status"] or "").lower()
        return "contract" if "contract" in st else ("warranty" if "warranty" in st else "other")
    return r["clean"]["site_name"] or "Unassigned site"


@router.post("/{import_id}/commit")
async def commit(import_id: str, user=Depends(get_crm_user)):
    of = _of(user)
    op_org = _org(user)
    doc = await db.crm2_afs_onboarding.find_one({"id": import_id, **of})
    if not doc:
        raise HTTPException(404, "Import not found")
    if doc.get("status") == "committed":
        raise HTTPException(409, "This import has already been committed.")
    rows = [r for r in doc.get("rows", []) if r.get("include")]
    if not rows:
        raise HTTPException(400, "No rows selected to import.")
    customer = (doc.get("customer_name") or "Imported customer").strip()
    grouping = doc.get("grouping", "per_site")
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    # 1) Customer platform org (lite, operations only) — holds sites + equipment.
    cust_org_id = _id()
    await db.organizations.insert_one({
        "id": cust_org_id, "name": customer, "account_type": "lite",
        "enabled_modules": ["operations"], "created_via": "afs_estate_onboarding",
        "created_at": _now(), "updated_at": _now()})

    # 2) CRM company mirror (scoped to the operator org) linked to the new org.
    crm_company_id = _id()
    await db.crm2_companies.insert_one({
        "id": crm_company_id, "organization_id": op_org, "name": customer,
        "type": "customer", "linked_organization_id": cust_org_id,
        "is_operator_company": False, "created_via": "afs_estate_onboarding",
        "created_at": _now(), "updated_at": _now()})

    # 3) Sites (one per distinct site name) under the customer org.
    site_ids = {}
    for r in rows:
        sn = r["clean"]["site_name"] or "Unassigned site"
        if sn not in site_ids:
            sid = _id()
            site_ids[sn] = sid
            await db.sites.insert_one({
                "id": sid, "organization_id": cust_org_id, "name": sn,
                "site_code": r["clean"]["site_code"] or None, "status": "active",
                "created_via": "afs_estate_onboarding", "created_at": _now(), "updated_at": _now()})

    # 4) Equipment register rows.
    for r in rows:
        c = r["clean"]
        eid = _id()
        r["_equipment_id"] = eid
        await db.equipment.insert_one({
            "id": eid, "organization_id": cust_org_id,
            "site_id": site_ids.get(c["site_name"]),
            "name": c["description"] or c["model"] or "Equipment",
            "model": c["model"] or None, "model_code": r["match"]["matched_code"] or c["model"] or None,
            "make": c["make"] or None, "serial_number": c["serial"] or None,
            "install_date": c["install_date"], "warranty_expiry": c["warranty_end"],
            "source": "afs_estate_onboarding", "contract_cover": None,
            "created_at": _now(), "updated_at": _now()})

    # 5) Grouped DRAFT contracts, carrying the chosen (inherited/Pulse) value.
    groups: Dict[str, List[dict]] = {}
    for r in rows:
        groups.setdefault(_group_key(r, grouping), []).append(r)

    contract_ids = []
    seq = 0
    for gkey, grp in groups.items():
        annual = round(sum(_row_value(r) for r in grp), 2)
        seq += 1
        cid = _id()
        num = f"PF-MA-IMP-{now.strftime('%y%m')}-{seq:02d}"
        title = customer if grouping == "master" else (
            f"{customer} — {gkey.title()}" if grouping == "per_status" else f"{customer} — {gkey}")
        starts = sorted([r["clean"]["contract_start"] for r in grp if r["clean"]["contract_start"]])
        start_date = starts[0] if starts else today
        end_date = (datetime.fromisoformat(start_date) + timedelta(days=365)).strftime("%Y-%m-%d")
        await db.crm2_contracts.insert_one({
            "id": cid, "organization_id": op_org, "contract_number": num,
            "company_id": crm_company_id, "company_name": customer, "title": title,
            "linked_organization_id": cust_org_id,
            "contract_type": doc.get("contract_type", "gold"), "tier": doc.get("contract_type", "gold"),
            "annual_value": annual, "total_value": round(annual, 2),
            "billing_frequency": "monthly", "status": "draft",
            "start_date": start_date, "end_date": end_date,
            "source": "afs_estate_onboarding", "source_import_id": import_id,
            "customer_type": "commercial", "created_at": _now(), "updated_at": _now()})
        # Link equipment cover to this contract.
        cover_ids = [r["_equipment_id"] for r in grp]
        await db.equipment.update_many(
            {"id": {"$in": cover_ids}, "organization_id": cust_org_id},
            {"$set": {"contract_cover": {"contract_id": cid, "contract_number": num,
                                         "tier": doc.get("contract_type", "gold")}, "updated_at": _now()}})
        contract_ids.append({"id": cid, "contract_number": num, "title": title,
                             "annual_value": annual, "assets": len(grp)})

    committed = {"customer_org_id": cust_org_id, "crm_company_id": crm_company_id,
                 "sites": len(site_ids), "equipment": len(rows), "contracts": contract_ids}
    await db.crm2_afs_onboarding.update_one({"id": import_id, **of}, {"$set": {
        "status": "committed", "committed": committed, "committed_at": _now(), "updated_at": _now()}})
    await record_audit(entity_type="afs_onboarding", entity_id=import_id, action="commit", user=user,
                       extra={"customer": customer, "contracts": len(contract_ids), "equipment": len(rows)})
    return {"import_id": import_id, "committed": committed}


# ── list / read (no file_b64 / rows in the list) ───────────────────────────
@router.get("/imports")
async def list_imports(user=Depends(get_crm_user)):
    docs = await db.crm2_afs_onboarding.find(
        _of(user), {"_id": 0, "file_b64": 0, "rows": 0, "sheets": 0}).sort("created_at", -1).to_list(100)
    return {"imports": docs}


@router.get("/{import_id}")
async def get_import(import_id: str, user=Depends(get_crm_user)):
    doc = await db.crm2_afs_onboarding.find_one({"id": import_id, **_of(user)}, {"_id": 0, "file_b64": 0})
    if not doc:
        raise HTTPException(404, "Import not found")
    return doc


# ── config search (for manual model match in the exception queue) ───────────
@router.get("/util/config-search")
async def config_search(q: str = "", limit: int = 20, user=Depends(get_crm_user)):
    of = _of(user)
    query = {**of}
    if q.strip():
        query["$or"] = [{"model": {"$regex": re.escape(q.strip()), "$options": "i"}},
                        {"display_name": {"$regex": re.escape(q.strip()), "$options": "i"}},
                        {"service_name": {"$regex": re.escape(q.strip()), "$options": "i"}}]
    cfgs = await db.crm2_afs_service_configs.find(
        query, {"_id": 0, "id": 1, "model": 1, "console_type": 1, "display_name": 1,
                "service_name": 1, "rrp_snapshot": 1, "manual_rrp_override": 1}).limit(max(1, min(limit, 50))).to_list(50)
    return {"configs": cfgs}
