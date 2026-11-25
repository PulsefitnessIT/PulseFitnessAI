"""MOD Operations quotation engine: Schedule B import, Type A/B/Mix line building, totals."""
from __future__ import annotations

import io
import re
from decimal import ROUND_HALF_UP, Decimal

HEADER_A = {"item_code": "CON-MOD-001", "description": "Type A: 1 Year Fully Inclusive MOD Aftersales Maintenance Contract"}
HEADER_B = {"item_code": "CON-MOD-002", "description": "Type B: One-Off Service or Repair."}
QUOTE_TYPES = ("A", "B", "AB")
TYPE_LABELS = {"A": "Type A — Fully Inclusive Maintenance", "B": "Type B — One-Off Service or Repair",
               "AB": "Type A/B Mix — Combined Coverage"}
CARDIO_TYPES = ("treadmill", "cross trainer", "rowing", "rowers", "bike", "stepper", "climber", "wave",
                "hand bike", "spinning", "grappler")

# Sage printed SOR references verified from issued quotations QT9410/QT9411/QT9412 (20/11/2026).
HISTORICAL_PRINTED_REFS = {
    "1B": ("SER100146", "Call Out Charge - Type B Only"),
    "2A": ("SER100201", "Treadmill - Type A Service"), "2B": ("SER100202", "Treadmill - Type B Service"),
    "4A": ("SER100189", "Rowing Machine - Type A Service"), "4B": ("SER100190", "Rowing Machine - Type B Service"),
    "5A": ("SER100144", "Benches - Type A Service"), "5B": ("SER100145", "Benches - Type B Service"),
    "8A": ("SER100151", "Cross Trainer, Non Powered - Type A Service"),
    "8B": ("SER100152", "Cross Trainer, Non Powered - Type B Service"),
    "18A": ("SER100203", "Upright Bike, Non Powered - Type A Service"),
    "18B": ("SER100204", "Upright Bike, Non Powered - Type B Service"),
    "20A": ("SER100191", "SingleStation Strength Machine - Type A Service"),
    "20B": ("SER100192", "SingleStation Strength Machine - Type B Service"),
    "23A": ("SER100167", "Multigym, 2 Station - Type A Service"),
    "23B": ("SER100168", "Multigym, 2 Station - Type B Service"),
}


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().rstrip(",").strip()


def parse_schedule_b(content: bytes) -> dict:
    """Read the LSLDC0223 Schedule B 'Tender SOR' sheet: one row per A/B rate entry."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    ws = wb["Tender SOR"] if "Tender SOR" in wb.sheetnames else wb.worksheets[0]
    header_row, cols = None, {}
    for r in range(1, min(ws.max_row, 30) + 1):
        vals = [str(c.value or "").strip().lower() for c in ws[r]]
        if any(v.startswith("unique identifier") for v in vals):
            header_row = r
            for i, v in enumerate(vals):
                if v.startswith("unique identifier"):
                    cols["uid"] = i
                elif v.startswith("item description"):
                    cols["name"] = i
                elif v.startswith("sage item code"):
                    cols["sage"] = i
                elif v.startswith("tl number"):
                    cols["tl"] = i
                elif v.startswith("extended item description"):
                    cols["ext"] = i
                elif v.startswith("unit of measure"):
                    cols["uom"] = i
            break
    if header_row is None:
        raise ValueError("Could not find the 'Unique Identifier' header row in the Tender SOR sheet")
    for r in range(header_row, header_row + 3):
        for i, c in enumerate(ws[r]):
            if str(c.value or "").strip().lower() == "year 1 price":
                cols["price"] = i
    if "price" not in cols:
        raise ValueError("Could not find the 'Year 1 Price' column")
    entries, issues = [], []
    for r in ws.iter_rows(min_row=header_row + 1, values_only=True):
        uid = str(r[cols["uid"]] or "").strip()
        m = re.fullmatch(r"(\d+)([A-Z]+)", uid)
        if not m:
            continue
        raw_price = r[cols["price"]]
        price = None if raw_price in (None, "", "POA") else float(raw_price)
        sfx = m.group(2)
        entries.append({
            "uid": uid, "item_no": m.group(1),
            "service_type": sfx if sfx in ("A", "B") else ("C" if sfx == "C" else sfx),
            "name": _clean_name(r[cols["name"]]),
            "sage_code": str(r[cols["sage"]] or "").strip(),
            "tl_ref": str(r[cols["tl"]] or "").strip(),
            "extended_description": _clean_name(r[cols.get("ext", cols["name"])]),
            "uom": str(r[cols["uom"]] or "Each").strip() if "uom" in cols else "Each",
            "price": price, "is_poa": price is None,
        })
    by_sage: dict[str, list[str]] = {}
    for e in entries:
        by_sage.setdefault(e["sage_code"], []).append(e["uid"])
    for code, uids in by_sage.items():
        if len(uids) > 1:
            issues.append({"kind": "duplicate_sage_code", "sage_code": code, "uids": uids,
                           "message": f"Sage item code {code} is used by {', '.join(uids)} — explicit mapping required"})
    for e in entries:
        e["ambiguous_sage_code"] = len(by_sage.get(e["sage_code"], [])) > 1
        hist = HISTORICAL_PRINTED_REFS.get(e["uid"])
        if hist and hist[0] != e["tl_ref"]:
            issues.append({"kind": "reference_conflict", "uid": e["uid"], "schedule_b_ref": e["tl_ref"],
                           "printed_ref": hist[0],
                           "message": f"{e['uid']}: Schedule B lists {e['tl_ref']} but issued quotations print {hist[0]}"})
    return {"sheet": ws.title, "entries": entries, "issues": issues}


def diff_against_card(entries: list[dict], card: list[dict]) -> list[dict]:
    by_item = {str(c.get("item_no")): c for c in card}
    out = []
    for e in entries:
        cur = by_item.get(e["item_no"])
        t = e["service_type"].lower() if e["service_type"] in ("A", "B") else "b"
        old = cur.get(f"type_{t}_price") if cur else None
        out.append({**e, "rate_card_id": cur["id"] if cur else None, "current_price": old,
                    "change": "new" if not cur else ("same" if old == e["price"] else "changed")})
    return out


def apply_entry(card_entry: dict, e: dict, approval: dict | None = None) -> dict:
    """Return the $set for one Schedule B row onto its rate-card entry.

    Verification is per service type: only the imported type's rate is (re)verified."""
    t = e["service_type"]
    key = "a" if t == "A" else "b"
    hist = HISTORICAL_PRINTED_REFS.get(e["uid"])
    if hist:
        printed_ref, printed_desc, src = hist[0], f"{hist[0]} - {hist[1]}", "issued_quotation"
    else:
        tail = "Type B Only" if card_entry.get("kind") == "call_out" else f"Type {t} Service"
        printed_ref, printed_desc, src = e["tl_ref"], f"{e['tl_ref']} - {e['name']} - {tail}", "schedule_b_unverified"
    upd = {
        f"sage_code_{key}": e["sage_code"], f"schedule_b_uid_{key}": e["uid"],
        f"tl_ref_{key}": e["tl_ref"], f"printed_ref_{key}": printed_ref,
        f"printed_desc_{key}": printed_desc, f"printed_ref_source_{key}": src,
        f"ambiguous_sage_code_{key}": e["ambiguous_sage_code"], "uom": e.get("uom") or "Each",
    }
    if e["is_poa"]:
        upd[f"poa_{key}"] = True
        upd[f"type_{key}_price"] = None
        upd[f"price_status_{key}"] = "poa"
    else:
        upd[f"poa_{key}"] = False
        upd[f"type_{key}_price"] = e["price"]
        upd[f"price_status_{key}"] = "verified" if approval else "unverified"
    upd[f"rate_{key}"] = {
        "amount": e["price"], "currency": "GBP", "source": (approval or {}).get("source"),
        "schedule_b_uid": e["uid"], "schedule_b_ref": e["tl_ref"], "sage_code": e["sage_code"],
        "printed_ref": printed_ref, "printed_ref_source": src,
        "effective_from": (approval or {}).get("effective_from"), "expires_on": (approval or {}).get("expires_on"),
        "status": upd[f"price_status_{key}"], "approved_by": (approval or {}).get("approved_by"),
        "approved_at": (approval or {}).get("approved_at"), "version": (approval or {}).get("version"),
    }
    return upd


def rate_is_verified(entry: dict, key: str, on_date: str) -> bool:
    """A rate is customer-ready only if its own type was approved and is in its rate period."""
    rate = entry.get(f"rate_{key}") or {}
    if entry.get(f"price_status_{key}") != "verified" or rate.get("status") != "verified":
        return False
    if rate.get("amount") is None or float(rate["amount"]) != float(entry.get(f"type_{key}_price") or -1):
        return False
    if rate.get("effective_from") and rate["effective_from"] > on_date:
        return False
    return not (rate.get("expires_on") and rate["expires_on"] < on_date)


def suggest_coverage(entry: dict | None) -> str:
    name = (entry or {}).get("equipment_type", "").lower()
    return "A" if any(k in name for k in CARDIO_TYPES) else "B"


def _row_line(row: dict, entry: dict, t: str, on_date: str) -> tuple[dict | None, str | None]:
    key = t.lower()
    price = entry.get(f"type_{key}_price")
    if entry.get(f"poa_{key}") or (entry.get("is_poa") and price is None) or price is None:
        return None, f"{row.get('description') or entry.get('label')}: Type {t} is price-on-application — no quotable rate"
    desc = entry.get(f"printed_desc_{key}") or f"{entry.get(f'tl_ref_{key}') or ''} - {entry.get('label')} - Type {t} Service"
    if row.get("label"):
        desc = f"{desc} ({row['label']})"
    qty = int(row.get("qty") or 0)
    return {
        "item_code": entry.get(f"sage_code_{key}") or entry.get(f"code_{key}"),
        "description": desc, "qty": qty, "unit": entry.get("uom") or "Each",
        "unit_price": float(money(price)), "total": float(money(price) * qty),
        "coverage": t, "rate_card_id": entry["id"], "row_id": row.get("row_id"),
        "schedule_b_uid": entry.get(f"schedule_b_uid_{key}"), "printed_ref": entry.get(f"printed_ref_{key}"),
        "price_status": "verified" if rate_is_verified(entry, key, on_date) else (entry.get(f"price_status_{key}") or "unverified"),
        "rate_version": (entry.get(f"rate_{key}") or {}).get("version"),
        "printed_ref_source": entry.get(f"printed_ref_source_{key}") or "unmapped",
    }, None


def build_quote(rows: list[dict], qtype: str, card_by_id: dict, callout_qty: int = 1, vat_rate: float = 20.0,
                on_date: str | None = None) -> dict:
    """Lines + totals for one quote option. Header lines follow QT9410/QT9411/QT9412."""
    from datetime import date
    on_date = on_date or date.today().isoformat()
    qtype = qtype.upper()
    lines, issues, excluded = [], [], []

    def hdr(h):
        lines.append({**h, "qty": 1, "unit": "Each", "unit_price": 0.0, "total": 0.0, "special": True})

    if qtype in ("A", "AB"):
        hdr(HEADER_A)
    if qtype in ("B", "AB"):
        hdr(HEADER_B)
    if qtype == "B" and callout_qty:
        co = next((e for e in card_by_id.values() if e.get("kind") == "call_out"), None)
        if not co or co.get("type_b_price") is None:
            issues.append("Type B call-out has no approved price")
        else:
            line, err = _row_line({"qty": callout_qty}, co, "B", on_date)
            if err:
                issues.append(err)
            else:
                lines.append({**line, "kind": "call_out"})
    for row in rows:
        qty = row.get("qty")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
            issues.append(f"{row.get('description')}: quantity must be a whole number of 0 or more")
            continue
        if qty == 0:
            excluded.append(row.get("description") or "(blank row)")
            continue
        entry = card_by_id.get(row.get("rate_card_id"))
        if not entry:
            issues.append(f"{row.get('description')}: not matched to a Schedule of Rates entry")
            continue
        t = qtype if qtype in ("A", "B") else (row.get("coverage") or "").upper()
        if t not in ("A", "B"):
            issues.append(f"{row.get('description')}: choose Type A or Type B coverage")
            continue
        line, err = _row_line(row, entry, t, on_date)
        if err:
            issues.append(err)
        else:
            lines.append(line)
    for i, ln in enumerate(lines, 1):
        ln["line_no"] = i
    net = sum((money(ln["total"]) for ln in lines), Decimal("0"))
    vat = money(net * Decimal(str(vat_rate)) / 100)
    unverified = [{"line_no": ln["line_no"], "item_code": ln["item_code"], "description": ln["description"],
                   "unit_price": ln["unit_price"], "coverage": ln.get("coverage")}
                  for ln in lines if not ln.get("special") and ln.get("price_status") != "verified"]
    return {"quote_type": qtype, "lines": lines, "net": float(net), "vat_rate": vat_rate, "vat": float(vat),
            "gross": float(net + vat), "issues": issues, "unverified_lines": unverified, "excluded_rows": excluded}


def parse_equipment_file(filename: str, content: bytes) -> list[dict]:
    """Read description/quantity(/code/serial/location) rows from CSV or Excel."""
    import csv
    name = (filename or "").lower()
    rows: list[list] = []
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        rows = [r for r in csv.reader(io.StringIO(text))]
    else:
        import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(content), data_only=True).worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr_idx, cols = None, {}
    for i, r in enumerate(rows[:15]):
        low = [str(c or "").strip().lower() for c in r]
        if any(k in v for v in low for k in ("description", "equipment", "item", "name")):
            hdr_idx = i
            for j, v in enumerate(low):
                if "desc" in v or v in ("equipment", "item", "name", "equipment type") and "desc" not in cols:
                    cols.setdefault("desc", j)
                if v.startswith("qty") or "quantity" in v:
                    cols.setdefault("qty", j)
                if "mod code" in v or "item code" in v or v == "code":
                    cols.setdefault("code", j)
                if "serial" in v or v in ("asset id", "equipment id"):
                    cols.setdefault("serial", j)
                if "location" in v or v == "site":
                    cols.setdefault("location", j)
            break
    if hdr_idx is None or "desc" not in cols:
        raise ValueError("No 'Description' column found — the first rows must contain column headings")
    out = []
    for r in rows[hdr_idx + 1:]:
        def g(k):
            j = cols.get(k)
            return str(r[j]).strip() if j is not None and j < len(r) and r[j] not in (None, "") else ""
        desc = g("desc")
        if not desc:
            continue
        try:
            qty = int(float(g("qty") or 1))
        except ValueError:
            qty = 1
        out.append({"description": desc, "qty": qty, "mod_code": g("code"), "serial": g("serial"), "location": g("location")})
    return out
