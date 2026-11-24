"""Maintenance Master bridge — stage the multi-customer workbook, reconcile it with
CRM, commit approved rows into the existing ``crm2_contracts`` (no new contract
store), keep every source value + row reference, and prepare deferred Sicon sync.

Nothing here creates PPM visits, billing, invoices, emails or Sicon writes.
"""
from __future__ import annotations

import io
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from utils.database import db

CONTRACT_SHEETS = ("Maintenance Database", "Expired")
EVIDENCE_SHEETS = ("Service Planner", "Sicon Contracts")
HELD_SHEETS = ("MOD",)  # staged + previewed; MOD Operations keeps ownership
FIELDS = {
    "Customer / site": "customer_name", "Site notes": "site_notes", "Sage Checked and Updated": "sage_checked",
    "Sales region": "sales_region", "Sales manager": "sales_manager", "County": "county",
    "Site account": "site_account", "Invoice account": "invoice_account", "Contract number": "contract_number",
    "Start date": "start_date", "Expiry date": "end_date", "Contract term": "contract_term",
    "Contract / warranty type": "contract_type", "Invoice Code": "invoice_code",
    "Beds and belts covered": "beds_belts_covered", "Upholstery covered": "upholstery_covered",
    "Services per year": "visits_per_year", "Last service recorded": "last_service_date",
    "Payment frequency": "payment_frequency", "Original amount (£)": "original_amount",
    "Contract amount (£)": "contract_amount", "Paid by Direct Debit": "direct_debit",
    "Payment notes": "payment_notes", "Invoice numbers": "invoice_numbers", "Comments": "comments",
    "Next action date": "next_action_date", "Next action": "next_action", "Upholstery colour": "upholstery_colour",
    "Renewal status": "renewal_status", "Contract coordinator": "coordinator_name", "Record ID": "record_id",
}
DATE_FIELDS = {"start_date", "end_date", "last_service_date", "next_action_date"}
# Contract fields coordinators may edit (and that a later workbook may update when unedited).
EDITABLE = ("customer_name", "start_date", "end_date", "contract_term", "contract_type", "visits_per_year",
            "payment_frequency", "original_amount", "contract_amount", "annual_value", "direct_debit",
            "payment_notes", "invoice_numbers", "comments", "next_action_date", "next_action", "renewal_status",
            "coordinator_name", "sales_region", "site_account", "invoice_account", "invoice_code",
            "beds_belts_covered", "upholstery_covered", "upholstery_colour", "site_notes",
            "sicon_contract_id", "sage_account_ref")
SYNC_STATES = ("not_reconciled", "awaiting_customer_mapping", "awaiting_sicon_matching", "ready_for_sync",
               "changes_pending", "sync_failed", "synced_verified")
_REC = re.compile(r"^(MAIN|PF|Q\d)-\d+$")
_REF = re.compile(r"\b[A-Z]{0,2}\d{3,8}[A-Z]?\d*\b")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def bucket() -> AsyncIOMotorGridFSBucket:
    return AsyncIOMotorGridFSBucket(db, bucket_name="mm_workbooks")


def norm_date(v):
    """ISO date or None — never guesses; returns (iso, raw_if_unparsed)."""
    if v in (None, ""):
        return None, None
    if isinstance(v, datetime):
        return v.date().isoformat(), None
    if isinstance(v, date):
        return v.isoformat(), None
    if isinstance(v, (int, float)) and 20000 < v < 80000:
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat(), None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s[:11].strip(), fmt).date().isoformat(), None
        except ValueError:
            continue
    return None, s


def num(v):
    try:
        return round(float(str(v).replace("£", "").replace(",", "").strip()), 2) if v not in (None, "") else None
    except ValueError:
        return None


def clean(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, timedelta):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if not isinstance(v, (str, int, float, bool)):
        return str(v)
    return v


def account_refs(*vals) -> list:
    out = []
    for v in vals:
        for t in _REF.findall(str(v or "").upper()):
            if t not in out:
                out.append(t)
    return out


def contract_status(start, end, today: str) -> str:
    if not start or not end:
        return "uncertain"
    if end < today:
        return "expired"
    return "future" if start > today else "active"


def map_row(headers: list, values: tuple) -> dict:
    """All source cells kept (by header or column letter) + mapped fields."""
    from openpyxl.utils import get_column_letter
    raw, mapped, unparsed = {}, {}, {}
    for i, v in enumerate(values):
        if v in (None, ""):
            continue
        h = headers[i] if i < len(headers) and headers[i] else f"col_{get_column_letter(i + 1)}"
        raw[h] = clean(v)
        f = FIELDS.get(h)
        if not f and isinstance(v, str) and _REC.match(v.strip()):
            f = "record_id"
        if not f:
            continue
        if f in DATE_FIELDS:
            iso, bad = norm_date(v)
            mapped[f] = iso
            if bad:
                unparsed[f] = bad
        elif f in ("original_amount", "contract_amount"):
            mapped[f] = num(v)
            if mapped[f] is None:
                unparsed[f] = str(v)
        else:
            mapped[f] = str(clean(v)).strip()
    if (mapped.get("contract_number") or "").strip().lower() in ("0", "n/a", "?", "tbc", "-", "none"):
        mapped["contract_number"] = ""
    return {"raw": raw, "mapped": mapped, "unparsed": unparsed}


def annual_value(m: dict):
    """Only when the source states an annual amount — never annualised by guesswork."""
    freq = (m.get("payment_frequency") or "").lower()
    if m.get("contract_amount") is not None and freq.startswith("annual"):
        return m["contract_amount"]
    return None


def parse_workbook(blob: bytes) -> dict:
    """Read every sheet (values only); returns staged rows + per-sheet inventory."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    sheets, rows = [], []
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True)
        headers = [str(h).strip() if h not in (None, "") else "" for h in (next(it, ()) or ())]
        while headers and not headers[-1]:
            headers.pop()
        n = 0
        role = ("contract" if ws.title in CONTRACT_SHEETS else "evidence" if ws.title in EVIDENCE_SHEETS
                else "held" if ws.title in HELD_SHEETS else "reference")
        for r_i, vals in enumerate(it, start=2):
            if not any(v not in (None, "") for v in vals[:60]):
                continue
            n += 1
            if role in ("contract", "evidence", "held"):
                rows.append({"sheet": ws.title, "row": r_i, "role": role, **map_row(headers, vals[:max(len(headers), 60)])})
        sheets.append({"name": ws.title, "state": ws.sheet_state, "role": role, "rows": n,
                       "headers": [h for h in headers if h], "unmapped_headers": [h for h in headers if h and h not in FIELDS]})
    return {"sheets": sheets, "rows": rows}


def record_key(sheet: str, m: dict) -> str:
    """Stable across re-uploads: Record ID when present, else sheet+contract number+start."""
    if m.get("record_id"):
        return m["record_id"]
    return f"{sheet}|{m.get('contract_number') or '?'}|{m.get('start_date') or '?'}|{(m.get('customer_name') or '')[:40]}"


async def company_index(org_id: str) -> dict:
    by_ref, by_name = {}, {}
    async for c in db.crm2_companies.find({"organization_id": org_id, "archived": {"$ne": True}},
                                          {"_id": 0, "id": 1, "name": 1, "legal_name": 1, "sage_account": 1,
                                           "sage_customer_reference": 1, "account_number": 1}):
        for k in ("sage_account", "sage_customer_reference", "account_number"):
            for t in account_refs(c.get(k)):
                by_ref.setdefault(t, {})[c["id"]] = c
        for n in {c.get("name"), c.get("legal_name")}:
            if n:
                by_name.setdefault(n.strip().lower(), {})[c["id"]] = c
    return {"ref": by_ref, "name": by_name}


def match_company(idx: dict, m: dict) -> dict:
    refs = account_refs(m.get("site_account"), m.get("invoice_account"))
    hits = {}
    for t in refs:
        hits.update(idx["ref"].get(t, {}))
    if len(hits) == 1:
        c = next(iter(hits.values()))
        return {"status": "matched", "company_id": c["id"], "company_name": c.get("name"), "basis": "account reference"}
    if len(hits) > 1:
        return {"status": "ambiguous", "candidates": [{"id": c["id"], "name": c.get("name"),
                                                       "ref": c.get("sage_account") or c.get("account_number")} for c in hits.values()],
                "basis": "several customers share these account references"}
    named = idx["name"].get((m.get("customer_name") or "").strip().lower(), {})
    if named:  # a name is supporting evidence only
        return {"status": "name_only", "candidates": [{"id": c["id"], "name": c.get("name"),
                                                       "ref": c.get("sage_account") or c.get("account_number")} for c in named.values()],
                "basis": "name matches but no account reference confirms it"}
    return {"status": "new", "refs": refs}


def diff_fields(contract: dict, m: dict) -> dict:
    out = {}
    m = {**m, "annual_value": annual_value(m)} if "contract_amount" in m else m
    for f in EDITABLE:
        if f not in m:
            continue
        cur = current(contract, f)
        if str(cur or "") != str(m.get(f) or ""):
            out[f] = {"crm": cur, "source": m.get(f)}
    return out


def edited_fields(contract: dict) -> set:
    base = contract.get("mm_baseline") or {}
    return {f for f in base if str(current(contract, f) or "") != str(base.get(f) or "")}


def current(contract: dict, f: str):
    if f in ("start_date", "end_date", "annual_value", "coordinator_name", "visits_per_year", "payment_frequency",
             "direct_debit", "sicon_contract_id", "sage_account_ref"):
        return contract.get(f)
    return (contract.get("mm") or {}).get(f)


def classify(m: dict, cust: dict, existing: dict | None, dup: bool, today: str) -> tuple[str, list]:
    problems = []
    if not m.get("contract_number"):
        problems.append("contract number missing")
    if not m.get("start_date") or not m.get("end_date"):
        problems.append("start or expiry date missing")
    if (m.get("contract_type") or "").lower().startswith("contract") and m.get("contract_amount") is None:
        problems.append("contract amount missing")
    if dup:
        return "duplicate_overlap", problems + ["contract number appears on more than one live row"]
    if existing:
        if existing.get("_overlap"):
            return "duplicate_overlap", problems + [existing["_overlap"]]
        d = diff_fields(existing, m)
        return ("matched_unchanged" if not d else "matched_differences"), problems
    if problems:
        return "missing_information", problems
    if cust["status"] in ("ambiguous", "name_only"):
        return "requires_review", [cust["basis"]]
    return "new_contract", []


def sicon_state(contract: dict) -> str:
    s = contract.get("sicon_sync") or {}
    if s.get("state") == "synced_verified" and s.get("last_synced_revision") != contract.get("revision"):
        return "changes_pending"
    if s.get("state") in ("sync_failed", "synced_verified", "ready_for_sync"):
        return s["state"]
    if not contract.get("sage_account_ref"):
        return "awaiting_customer_mapping"
    if not contract.get("sicon_contract_id"):
        return "awaiting_sicon_matching"
    return "not_reconciled" if not s.get("identity_verified") else "ready_for_sync"


def new_contract_doc(org_id: str, upload: dict, row: dict, company: dict, actor: str, today: str) -> dict:
    m = row["mapped"]
    status = contract_status(m.get("start_date"), m.get("end_date"), today)
    sage = (account_refs(m.get("invoice_account")) or account_refs(m.get("site_account")) or [None])[0]
    ev = row.get("evidence") or {}
    doc = {
        "id": str(uuid.uuid4()), "organization_id": org_id, "company_id": company["id"],
        "company_name": company.get("name"), "title": m.get("customer_name") or company.get("name"),
        "contract_number": m.get("contract_number"),
        "status": {"active": "active", "expired": "expired", "future": "pending_start"}.get(status, "draft"),
        "start_date": m.get("start_date"), "end_date": m.get("end_date"),
        "annual_value": annual_value(m), "payment_frequency": m.get("payment_frequency"),
        "visits_per_year": int(float(m["visits_per_year"])) if (m.get("visits_per_year") or "").replace(".", "", 1).isdigit() else None,
        "direct_debit": m.get("direct_debit"), "coordinator_name": m.get("coordinator_name"),
        "sicon_contract_id": ev.get("sicon_contract_id"), "sage_account_ref": sage,
        "source": "maintenance_master", "historical_import": True, "mm_record_key": row["record_key"],
        "mm": {k: v for k, v in m.items()}, "mm_status": status,
        "mm_source": {"upload_id": upload["id"], "sha256": upload["sha256"], "filename": upload["filename"],
                      "sheet": row["sheet"], "row": row["row"], "record_id": m.get("record_id"), "raw": row["raw"]},
        "mm_service_history": ev.get("service") or None,
        "revision": 1, "created_by": actor, "created_at": _now(), "updated_at": _now(),
    }
    doc["mm_baseline"] = {f: current(doc, f) for f in EDITABLE}
    doc["sicon_sync"] = {"state": None, "sicon_contract_id": ev.get("sicon_contract_id"),
                         "sicon_line_ids": ev.get("sicon_line_ids") or [], "identity_verified": False,
                         "last_synced_revision": None, "source": "maintenance_master_sicon_sheet" if ev.get("sicon_contract_id") else None}
    doc["sicon_sync"]["state"] = sicon_state(doc)
    return doc
