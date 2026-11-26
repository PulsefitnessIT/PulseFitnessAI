"""Parsing + classification for Sage 200 customer-account and Sicon customer-contact exports.

Pure functions (no DB): read a workbook/CSV, find the header row, separate template
metadata / example rows from genuine records, and turn each genuine row into a typed,
validated record with every source field classified.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime

MAX_ROWS = 50000  # documented supported capacity per file; larger files are rejected, never truncated

# ---------------------------------------------------------------- Sage field catalogue (115 fields)
_SAGE_ACCOUNT = ["AccountNumber", "AccountName", "ShortName", "AccountBalance", "CreditLimit", "CurrencyISOCode",
                 "SYSExchangeRateType", "CountryCode", "TaxCode", "TaxRegistrationNumber", "MonthsToKeepTransactionsFor",
                 "DefaultOrderPriority", "FinanceCharge", "DefaultNominalAccountNumber", "DefaultNominalCostCentre",
                 "DefaultNominalDepartment", "SYSAccountType", "EarlySettlementDiscountPercent",
                 "DaysEarlySettlementDiscountApplies", "PaymentTermsInDays", "SYSPaymentTermsBasis",
                 "UseConsolidatedBilling", "InvoiceLineDiscountPercent", "InvoiceDiscountPercent",
                 "SendCopyStatementToBranch", "AccountIsOnHold", "ValueOfCurrentOrdersInSOP", "DateOfLastTransaction",
                 "EuroAccountNumberCopiedFromTo", "DateEuroAccountCopied"]
_SAGE_COMMS = ["MainTelephoneCountryCode", "MainTelephoneAreaCode", "MainTelephoneSubscriberNumber",
               "MainFaxCountryCode", "MainFaxAreaCode", "MainFaxSubscriberNumber", "MainWebsite"]
_SAGE_ADDRESS = ["AddressLine1", "AddressLine2", "AddressLine3", "AddressLine4", "City", "County", "Country", "PostCode"]
_SAGE_CONTACT = ["ContactSalutation", "ContactFirstName", "ContactMiddleName", "ContactLastName",
                 "ContactTelephoneCountryCode", "ContactTelephoneAreaCode", "ContactTelephoneSubscriberNumber",
                 "ContactFaxCountryCode", "ContactFaxAreaCode", "ContactFaxSubscriberNumber",
                 "ContactMobileCountryCode", "ContactMobileAreaCode", "ContactMobileSubscriberNumber",
                 "ContactWebsite", "ContactEmail"]
_SAGE_EXTRA = ["DateFinanceChargeLastRun", "AssociatedOfficeType", "AssociatedHeadOfficeAccountNum", "TradingTerms",
               "CreditReference", "CreditBureau", "CreditPosition", "TermsAgreed", "AccountOpened", "LastCreditReview",
               "NextCreditReview", "ApplicationDate", "DateReceived", "Memo", "ActiveStatus"]
_SAGE_ANALYSIS = [f"Analysis{k}\\{i}" for i in range(1, 21) for k in ("Name", "Value")]
SAGE_FIELDS = _SAGE_ACCOUNT + _SAGE_COMMS + _SAGE_ADDRESS + _SAGE_CONTACT + _SAGE_EXTRA + _SAGE_ANALYSIS

# Classification of every Sage field: visible (organisation info), contact, reference (matching/status
# metadata kept on the org), internal (staff-only restricted record), excluded (not stored).
_VISIBLE = {"AccountName", "ShortName", "CurrencyISOCode", "CountryCode", "MainWebsite", *_SAGE_COMMS, *_SAGE_ADDRESS}
_REFERENCE = {"AccountNumber", "AssociatedOfficeType", "AssociatedHeadOfficeAccountNum", "ActiveStatus", "AccountOpened"}
_EXCLUDED = {"SYSExchangeRateType", "MonthsToKeepTransactionsFor", "EuroAccountNumberCopiedFromTo", "DateEuroAccountCopied"}


def sage_field_class(f: str) -> str:
    if f in _VISIBLE:
        return "customer_visible"
    if f in _SAGE_CONTACT:
        return "business_contact"
    if f in _REFERENCE:
        return "source_reference"
    if f in _EXCLUDED:
        return "excluded"
    return "restricted_internal"


SICON_FIELDS = ["MetaDataDescription", "CustomerCode", "IsDefaultContact", "Salutation", "FirstName", "MiddleName",
                "LastName", "TelephoneCountryCode", "TelephoneAreaCode", "TelephoneNumber", "IsDefaultTelephoneNumber",
                "MobileCountryCode", "MobileAreaCode", "MobileNumber", "IsDefaultMobileNumber", "FaxCountryCode",
                "FaxAreaCode", "FaxNumber", "IsDefaultFax", "Email", "IsDefaultEmail", "Website", "IsDefaultWebsite",
                "ContactRole", "ContactRolePreferred"]

ACCOUNT_REF_ALIASES = {"accountnumber", "account number", "account_number", "customercode", "customer code",
                       "customer_code", "customer account number", "customer_account_number", "sage_customer_number",
                       "sicon_customer_number", "account no", "account ref", "account reference", "sage account"}

_SAGE_META_LABELS = ("description", "format", "field length", "pre-requisites", "mandatory/optional", "can create",
                     "can update", "name in application", "database/field name")
_SICON_META = {"description", "mandatory", "default value", "max length", "comments"}
_SICON_SAMPLE = {"sample data"}
# Sample accounts shipped inside Sage's own template — matched on number AND name together so a
# genuine customer that happens to share an account number is never excluded.
_SAGE_TEMPLATE_SAMPLES = {("1032", "p. leverage fabrics ltd"), ("1038", "modern metal finishers"), ("1039", "studio seven designs"), ("1040", "miller electricals ltd"), ("1041", "wallace office equipment"), ("1042", "marcel legrand caste"), ("1043", "viking plywood & timber"), ("1048", "stand builders ltd")}
GENERIC_LOCALPARTS = {"info", "reception", "accounts", "admin", "office", "sales", "enquiries", "enquiry", "hello",
                      "contact", "mail", "gym", "leisure", "finance", "purchasing", "support", "bookings", "team"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


# ---------------------------------------------------------------- reading
def _fmt_number(v: float, fmt: str = "") -> str:
    if v == int(v):
        s = str(int(v))
        zeros = re.fullmatch(r"0+", (fmt or "").strip().strip('"'))
        return s.zfill(len(zeros.group(0))) if zeros else s
    return repr(v).rstrip("0").rstrip(".") if "e" not in repr(v) else str(v)


def _read_xls(raw: bytes) -> list[dict]:
    import xlrd
    try:
        book = xlrd.open_workbook(file_contents=raw, formatting_info=True)
    except NotImplementedError:
        book = xlrd.open_workbook(file_contents=raw)
    out = []
    for sh in book.sheets():
        rows = []
        for r in range(min(sh.nrows, MAX_ROWS + 50)):
            row = []
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_NUMBER:
                    fmt = ""
                    try:
                        fmt = book.format_map[book.xf_list[cell.xf_index].format_key].format_str
                    except Exception:  # noqa: BLE001 — formatting info is optional
                        pass
                    row.append(_fmt_number(cell.value, fmt))
                elif cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        row.append(xlrd.xldate_as_datetime(cell.value, book.datemode).date().isoformat())
                    except Exception:  # noqa: BLE001
                        row.append(str(cell.value))
                elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    row.append("TRUE" if cell.value else "FALSE")
                else:
                    row.append(str(cell.value or "").strip())
            rows.append(row)
        out.append({"name": sh.name, "rows": rows, "physical_rows": sh.nrows})
    return out


def _read_xlsx(raw: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        rows, n = [], 0
        for row in ws.iter_rows():
            n += 1
            if n > MAX_ROWS + 50:
                continue
            vals = []
            for cell in row:
                v = cell.value
                if v is None:
                    vals.append("")
                elif isinstance(v, bool):
                    vals.append("TRUE" if v else "FALSE")
                elif isinstance(v, (int, float)):
                    vals.append(_fmt_number(float(v), getattr(cell, "number_format", "")))
                elif isinstance(v, datetime):
                    vals.append(v.date().isoformat())
                else:
                    vals.append(str(v).strip())
            rows.append(vals)
        out.append({"name": ws.title, "rows": rows, "physical_rows": n})
    return out


def _read_csv(raw: bytes) -> list[dict]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    rows = [[(c or "").strip() for c in r] for r in csv.reader(io.StringIO(text))]
    return [{"name": "CSV", "rows": rows[:MAX_ROWS + 50], "physical_rows": len(rows)}]


def read_sheets(raw: bytes, filename: str) -> tuple[str, list[dict]]:
    name = (filename or "").lower()
    if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls", _read_xls(raw)
    if raw[:2] == b"PK":
        return "xlsx", _read_xlsx(raw)
    if name.endswith((".xls", ".xlsx")):
        raise ValueError("The file is not a readable Excel workbook — re-save it from Excel or export as CSV.")
    return "csv", _read_csv(raw)


def checksum(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------- detection
def _norm(h: str) -> str:
    return re.sub(r"\s+", "", (h or "")).lower()


def _find_header(rows: list[list[str]], required: tuple[str, ...]) -> tuple[int, int]:
    """(header_row_index, first_data_column) — first_data_column skips Sage's leading descriptive column."""
    req = {_norm(r) for r in required}
    for i, row in enumerate(rows[:40]):
        cells = [_norm(c) for c in row]
        if req <= set(cells):
            first = 1 if cells and cells[0] in ("fieldintemplate:", "fieldintemplate") else 0
            return i, first
    return -1, 0


def detect(sheets: list[dict], sheet_override: str | None = None, header_override: int | None = None) -> dict:
    """Identify the source format, header row and the role of every row (metadata / example / genuine)."""
    cands = [s for s in sheets if not sheet_override or s["name"] == sheet_override]
    if sheet_override and not cands:
        raise ValueError(f"Worksheet '{sheet_override}' not found")
    for fmt, req in (("sage_accounts", ("AccountNumber", "AccountName")), ("sicon_contacts", ("CustomerCode", "FirstName"))):
        for sh in cands:
            hi, first = _find_header(sh["rows"], req)
            if header_override is not None:
                hi = header_override
            if hi < 0:
                continue
            return _classify_rows(fmt, sh, hi, first)
    return {"format": "unknown", "sheets": [s["name"] for s in sheets]}


def _classify_rows(fmt: str, sh: dict, hi: int, first: int) -> dict:
    rows = sh["rows"]
    headers = [c.strip() for c in rows[hi][first:]]
    known = SAGE_FIELDS if fmt == "sage_accounts" else SICON_FIELDS
    kn = {_norm(k): k for k in known}
    colmap = {}
    for j, h in enumerate(headers):
        k = kn.get(_norm(h)) or (("AccountNumber" if fmt == "sage_accounts" else "CustomerCode")
                                 if h.strip().lower() in ACCOUNT_REF_ALIASES else None)
        if k and k not in colmap.values():
            colmap[j + first] = k
    unrecognised = [h for j, h in enumerate(headers) if h and (j + first) not in colmap]
    roles, template_mode, in_examples, gap_after_examples = [], first == 1, False, False
    for i in range(hi + 1, len(rows)):
        row = rows[i]
        vals = [c for c in row[first:] if c]
        label = (row[0] if row else "").strip().lower().rstrip(":")
        if not vals:
            if in_examples:
                in_examples, gap_after_examples = False, True
            roles.append((i, "blank"))
            continue
        if fmt == "sage_accounts":
            if template_mode and label in _SAGE_META_LABELS:
                roles.append((i, "metadata"))
            elif template_mode and label == "examples":
                in_examples = True
                roles.append((i, "example"))
            elif in_examples:
                roles.append((i, "example"))
            elif gap_after_examples:
                roles.append((i, "uncertain"))  # rows after the example block — admin must confirm the range
            else:
                roles.append((i, "genuine"))
        else:
            md = (row[0] if row else "").strip().lower() if _norm(rows[hi][0]) == "metadatadescription" else ""
            roles.append((i, "metadata" if md in _SICON_META else "example" if md in _SICON_SAMPLE else "genuine"))
    records = []
    for i, role in roles:
        if role == "blank":
            continue
        rec = {k: (rows[i][j] if j < len(rows[i]) else "") for j, k in colmap.items()}
        if fmt == "sage_accounts" and role in ("genuine", "uncertain") and \
                ((rec.get("AccountNumber") or "").strip(), (rec.get("AccountName") or "").strip().lower()) in _SAGE_TEMPLATE_SAMPLES:
            role = "suspected_example"  # matches Sage's own sample (number + name) — excluded unless the admin includes it
        records.append({"row": i + 1, "role": role, "values": rec})
    counts = {r: sum(1 for x in records if x["role"] == r) for r in ("metadata", "example", "genuine", "uncertain", "suspected_example")}
    if sh["physical_rows"] > MAX_ROWS + hi + 50:
        raise ValueError(f"This file has {sh['physical_rows']} rows. The supported maximum is {MAX_ROWS:,} records per "
                         f"file — split it into smaller files.")
    return {"format": fmt, "worksheet": sh["name"], "header_row": hi + 1,
            "leading_metadata_column": first == 1, "fields_recognised": len(colmap), "fields_total": len(known),
            "unrecognised_fields": unrecognised,
            "excluded_fields": [k for k in colmap.values() if fmt == "sage_accounts" and sage_field_class(k) == "excluded"],
            "physical_rows": sh["physical_rows"], "counts": counts,
            "requires_range_confirmation": counts["uncertain"] > 0 or counts["suspected_example"] > 0, "records": records}


# ---------------------------------------------------------------- record building
def _clean_ref(v: str) -> str:
    return re.sub(r"\s+", "", str(v or "")).upper()


def _phone(cc: str, area: str, num: str) -> dict:
    """Keep the source parts; only produce a display number when it can be read reliably."""
    cc, area, num = (str(x or "").strip() for x in (cc, area, num))
    src = {"country_code": cc, "area_code": area, "number": num}
    if not (cc or area or num):
        return {}
    d_cc, d_area, d_num = (re.sub(r"\D", "", x) for x in (cc, area, num))
    if d_area and d_num.startswith(d_area.lstrip("0")) or d_area and d_num.startswith(d_area):
        d_area = ""  # subscriber number already includes the area code
    if d_num and len(d_area) > len(d_num) and d_area.endswith(d_num):
        d_num, d_area = d_area, ""  # full number typed into the area-code box and repeated
    if len(d_area) >= 9 and not d_num:
        d_num, d_area = d_area, ""  # whole number typed into the area-code box
    national = (d_area + d_num) if d_area else d_num
    display, reliable = "", False
    if national and 6 <= len(national.lstrip("0")) + len(d_cc) <= 15:
        if d_cc and d_cc != "44":
            display, reliable = f"+{d_cc} {national.lstrip('0')}", True
        elif d_cc == "44" or national.startswith("0"):
            display, reliable = ("0" + national.lstrip("0")) if len(national.lstrip("0")) in (9, 10) else national, \
                len(national.lstrip("0")) in (9, 10)
        else:
            display = national
    return {**src, "display": display, "reliable": reliable}


def _email(v: str) -> tuple[str, str | None]:
    e = str(v or "").strip()
    if not e:
        return "", None
    if not _EMAIL.match(e):
        return "", f"Invalid email '{e[:60]}' — not used"
    return e.lower(), None


def is_generic_email(e: str) -> bool:
    return bool(e) and e.split("@")[0].split("+")[0] in GENERIC_LOCALPARTS


def _date(v: str) -> str:
    v = str(v or "").strip()
    if not v:
        return ""
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(v[:10], f).date().isoformat()
        except ValueError:
            continue
    return v


def _limit(errs: list, rec: dict, field: str, n: int, label: str):
    v = str(rec.get(field) or "")
    if len(v) > n:
        errs.append(f"{label} is {len(v)} characters (Sage maximum {n}) — correct it in Sage and re-export")


def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:24]


def build_sage_record(values: dict) -> dict:
    v = {k: str(values.get(k) or "").strip() for k in SAGE_FIELDS}
    errs, warns = [], []
    ref = _clean_ref(v["AccountNumber"])
    if not ref:
        errs.append("AccountNumber is missing")
    _limit(errs, {"a": ref}, "a", 8, "AccountNumber")
    if not v["AccountName"]:
        errs.append("AccountName is missing")
    for f, n in (("AccountName", 60), ("ShortName", 8), ("PostCode", 10), ("Country", 2), ("CountryCode", 2),
                 ("AssociatedHeadOfficeAccountNum", 8), ("ContactEmail", 227)):
        _limit(errs, v, f, n, f)
    cur = v["CurrencyISOCode"].upper()
    if cur and not re.fullmatch(r"[A-Z]{3}", cur):
        errs.append(f"CurrencyISOCode '{cur}' is not a 3-letter ISO code")
    email, ew = _email(v["ContactEmail"])
    if ew:
        warns.append(ew)
    office = v["AssociatedOfficeType"] or "0"
    office_type = {"0": "independent", "1": "branch", "2": "head_office", "3": "independent_no_statement",
                   "4": "head_office_no_statement"}.get(office.split(".")[0])
    if office_type is None:
        warns.append(f"Unknown AssociatedOfficeType '{office}' — treated as independent")
        office_type = "independent"
    hidden = v["ActiveStatus"].split(".")[0] == "1"
    on_hold = v["AccountIsOnHold"].split(".")[0] == "1" or v["AccountIsOnHold"].lower() in ("true", "yes")
    if v["ActiveStatus"] not in ("", "0", "1"):
        warns.append(f"Uncertain ActiveStatus '{v['ActiveStatus']}'")
    contact = {"salutation": v["ContactSalutation"], "first_name": v["ContactFirstName"],
               "middle_name": v["ContactMiddleName"], "last_name": v["ContactLastName"],
               "telephone": _phone(v["ContactTelephoneCountryCode"], v["ContactTelephoneAreaCode"], v["ContactTelephoneSubscriberNumber"]),
               "fax": _phone(v["ContactFaxCountryCode"], v["ContactFaxAreaCode"], v["ContactFaxSubscriberNumber"]),
               "mobile": _phone(v["ContactMobileCountryCode"], v["ContactMobileAreaCode"], v["ContactMobileSubscriberNumber"]),
               "website": v["ContactWebsite"], "email": email, "email_source": v["ContactEmail"], "role": "Sage primary contact",
               "is_default": True}
    for k in ("telephone", "mobile", "fax"):
        if contact[k] and not contact[k].get("reliable") and contact[k].get("number"):
            warns.append(f"Contact {k} parts could not be combined reliably — kept as entered")
    has_contact = any([contact["first_name"], contact["last_name"], email, contact["telephone"].get("number"),
                       contact["mobile"].get("number")])
    org = {"name": v["AccountName"], "short_name": v["ShortName"], "currency": cur, "sage_country_code": v["CountryCode"].upper(),
           "website": v["MainWebsite"],
           "phone": _phone(v["MainTelephoneCountryCode"], v["MainTelephoneAreaCode"], v["MainTelephoneSubscriberNumber"]),
           "fax": _phone(v["MainFaxCountryCode"], v["MainFaxAreaCode"], v["MainFaxSubscriberNumber"]),
           "address_line1": v["AddressLine1"], "address_line2": v["AddressLine2"], "address_line3": v["AddressLine3"],
           "address_line4": v["AddressLine4"], "city": v["City"], "county": v["County"],
           "address_country_code": v["Country"].upper(), "postcode": v["PostCode"].upper()}
    internal = {k: v[k] for k in SAGE_FIELDS if sage_field_class(k) == "restricted_internal" and not k.startswith("Analysis") and v[k]}
    for k in ("DateOfLastTransaction", "DateFinanceChargeLastRun", "TermsAgreed", "LastCreditReview", "NextCreditReview",
              "ApplicationDate", "DateReceived"):
        if k in internal:
            internal[k] = _date(internal[k])
    analysis = [{"index": i, "name": v[f"AnalysisName\\{i}"], "value": v[f"AnalysisValue\\{i}"]}
                for i in range(1, 21) if v[f"AnalysisName\\{i}"] or v[f"AnalysisValue\\{i}"]]
    return {"account_ref": ref, "org": org, "contact": contact if has_contact else None,
            "status": {"hidden": hidden, "on_hold": on_hold, "active_status_source": v["ActiveStatus"],
                       "on_hold_source": v["AccountIsOnHold"], "account_opened": _date(v["AccountOpened"])},
            "office_type": office_type, "head_office_ref": _clean_ref(v["AssociatedHeadOfficeAccountNum"]),
            "internal": internal, "analysis": analysis, "errors": errs, "warnings": warns,
            "fingerprint": fingerprint(v)}


def _flag(v: str) -> bool:
    return str(v or "").strip().lower() in ("true", "1", "yes", "y")


def build_sicon_record(values: dict) -> dict:
    v = {k: str(values.get(k) or "").strip() for k in SICON_FIELDS}
    errs, warns = [], []
    ref = _clean_ref(v["CustomerCode"])
    if not ref:
        errs.append("CustomerCode is missing")
    elif len(ref) > 8:
        errs.append(f"CustomerCode is {len(ref)} characters (maximum 8)")
    email, ew = _email(v["Email"])
    if ew:
        warns.append(ew)
    c = {"salutation": v["Salutation"], "first_name": v["FirstName"], "middle_name": v["MiddleName"],
         "last_name": v["LastName"], "telephone": _phone(v["TelephoneCountryCode"], v["TelephoneAreaCode"], v["TelephoneNumber"]),
         "mobile": _phone(v["MobileCountryCode"], v["MobileAreaCode"], v["MobileNumber"]),
         "fax": _phone(v["FaxCountryCode"], v["FaxAreaCode"], v["FaxNumber"]), "website": v["Website"],
         "email": email, "email_source": v["Email"], "role": v["ContactRole"], "is_default": _flag(v["IsDefaultContact"]),
         # Source preferences only — never consent to marketing or permission to log in.
         "preferences": {"default_telephone": _flag(v["IsDefaultTelephoneNumber"]), "default_mobile": _flag(v["IsDefaultMobileNumber"]),
                         "default_fax": _flag(v["IsDefaultFax"]), "default_email": _flag(v["IsDefaultEmail"]),
                         "default_website": _flag(v["IsDefaultWebsite"]), "role_preferred": _flag(v["ContactRolePreferred"])}}
    if not any([c["first_name"], c["last_name"], email, c["telephone"].get("number"), c["mobile"].get("number")]):
        errs.append("No name, email or telephone — nothing meaningful to import")
    return {"account_ref": ref, "contact": c, "errors": errs, "warnings": warns, "fingerprint": fingerprint(v)}


def contact_identity(c: dict) -> dict:
    name = " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x).strip().lower()
    nums = {re.sub(r"\D", "", (c.get(k) or {}).get("number", "") or "")[-9:] for k in ("telephone", "mobile")} - {""}
    email = c.get("email") or ""
    return {"name": name, "email": "" if is_generic_email(email) else email, "generic_email": email if is_generic_email(email) else "",
            "numbers": sorted(nums)}


def match_contact(c: dict, existing: list[dict]) -> tuple[str, dict | None]:
    """Account-scoped, conservative: ('new'|'same'|'update'|'ambiguous', existing_doc)."""
    me = contact_identity(c)
    fp = fingerprint({k: c.get(k) for k in ("salutation", "first_name", "middle_name", "last_name", "email", "telephone",
                                            "mobile", "fax", "website", "role")})
    hits = []
    for e in existing:
        if fp in (e.get("source_fingerprints") or []):
            return "same", e
        them = e.get("identity") or {}
        same_name = bool(me["name"]) and me["name"] == them.get("name")
        same_email = bool(me["email"]) and me["email"] == them.get("email")
        shared_num = bool(set(me["numbers"]) & set(them.get("numbers") or []))
        conflicting_email = bool(me["email"] and them.get("email") and me["email"] != them.get("email"))
        if same_name and (same_email or shared_num or not conflicting_email) or same_email and not me["name"]:
            hits.append(("update", e))
        elif same_email and them.get("name") and me["name"] != them.get("name"):
            hits.append(("ambiguous", e))  # same personal email, different name
        elif same_name and conflicting_email:
            hits.append(("ambiguous", e))
    if not hits:
        if not me["name"] and not me["email"] and me["generic_email"]:
            for e in existing:  # nameless contact on a generic mailbox: same mailbox = same record
                if not (e.get("identity") or {}).get("name") and (e.get("identity") or {}).get("generic_email") == me["generic_email"]:
                    return "update", e
        return "new", None
    if len(hits) > 1 or hits[0][0] == "ambiguous":
        return "ambiguous", hits[0][1]
    return hits[0]


def contact_fp(c: dict) -> str:
    return fingerprint({k: c.get(k) for k in ("salutation", "first_name", "middle_name", "last_name", "email", "telephone",
                                              "mobile", "fax", "website", "role")})
