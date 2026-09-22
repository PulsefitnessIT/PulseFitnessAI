"""
Master-admin-level bulk import — equipment and customers.

The Service Portal (`/equipment/import-csv`) and CRM (`/import/contacts`)
already have CSV import endpoints, but they're locked to their respective
auth scopes. Pulse Master Admins manage the platform from the Master Admin
console and need a single home for bulk-loading data into a customer's
brand-new tenant — without having to flip portals or paste credentials.

This module exposes:

  • GET  /api/master-admin/bulk-import/templates/equipment  — CSV template
  • GET  /api/master-admin/bulk-import/templates/customers  — CSV template
  • POST /api/master-admin/bulk-import/equipment            — import equipment
  • POST /api/master-admin/bulk-import/customers            — import customers
  • POST /api/master-admin/bulk-import/sites                 — import sites (iter 216h53)
  • GET  /api/master-admin/bulk-import/templates/sites       — CSV template (passthrough)

Both POST endpoints accept an optional `organization_id` query param so the
admin can target the import at a specific Pulse customer's tenant.
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from utils.auth import get_current_user
from utils.database import db
from utils.default_supplier import PULSE_DEFAULT_SUPPLIER_NAME
from utils.file_validation import MIME_SPREADSHEETS, validate_upload

from routes.pulse_master_admin import _require_pulse_or_master, PULSE_VISIBLE_ACCOUNT_TYPES

logger = logging.getLogger(__name__)
router = APIRouter()


# ── CSV templates ────────────────────────────────────────────────────────

# Headers chosen to match the existing CSV importers' aliases so files
# downloaded from here drop straight into either path without remapping.
#
# Iter 216h50 — `site_name` is the FIRST column so equipment imported
# in bulk auto-links to a site that already exists in the target org.
# `unit_price` feeds the Capex replacement-cost model so reports reflect
# the actual purchase price rather than the equipment-type profile
# default. Pulse Fitness use Sicon's "Invoice Customer Ref" as the
# site reference, so we also accept that alias (resolved against the
# site's `invoice_customer_ref` field) when `site_name` is blank.
#
# Iter 216h51 — `supplier` column added. Resolves to a row in the
# `suppliers` collection within the same org so fault auto-emails route
# to the correct service-supplier email address. Matches first on name
# (case-insensitive), then on the supplier's `service_email` if the
# column happens to contain an email instead of a company name.
_EQUIPMENT_HEADERS = [
    "site_name",
    "customer_account_number",
    "supplier",
    "name", "equipment_type", "manufacturer", "model", "serial_number",
    "purchase_date", "warranty_expiry", "service_provider",
    "unit_price", "replacement_cost",
    "contract_number", "contract_start", "contract_end",
    "length", "width", "height", "location", "notes",
    # Sicon two-way-sync linkage — capture the Sicon Service equipment id
    # (and Sage stock ItemID) at migration time so the ongoing case/sync
    # engine can match each asset back to its Sicon master record without
    # a serial-number guess. Both optional; leave blank for non-Sicon kit.
    "sicon_equipment_id", "sage_item_id",
    # Iter 216h111 — MOD Force tag. Accepts Army/RAF/Navy (case-insensitive;
    # also accepts "British Army", "Royal Air Force", "Royal Navy" and the
    # short tokens "army"/"raf"/"navy"). Ignored for non-MOD rows so a
    # standard customer importing into a Pulse org can leave it blank.
    "mod_force",
]
_EQUIPMENT_EXAMPLE = [
    "Carshalton Sports Centre",
    "PULSENC01",
    "Pulse Fitness",
    "Treadmill — Cardio Bay 3", "Treadmill", "Life Fitness", "T7000", "LFT-2024-04958",
    "2024-01-15", "2027-01-15", "Pulse Fitness Service",
    "3450.00", "3800.00",
    "CON-2024-0142", "2024-01-15", "2029-01-14",
    "2.20", "0.95", "1.55", "Cardio Mezzanine", "Brand new — first install",
    "48213", "9920",  # sicon_equipment_id, sage_item_id (blank for non-Sicon kit)
    "",  # mod_force — leave blank for non-MOD customers
]

_CUSTOMER_HEADERS = [
    "customer_account_number",
    "first_name", "last_name", "email", "phone", "company", "title",
    "tags", "linkedin", "address",
]
_CUSTOMER_EXAMPLE = [
    "PULSENC01",
    "Sarah", "Johnson", "sarah.johnson@gymtest.com", "+447700900001",
    "Tottenham Green Leisure Centre", "Operations Manager",
    "active,key-account", "https://linkedin.com/in/sarah-johnson", "Tottenham, London N17",
]

# Contracts bulk import — maps to the CRM `crm2_contracts` collection.
# Lets onboarding load a customer's existing book of service contracts in
# one file (the Sicon Contracts API is push-only, so there is no auto-pull).
# `contract_number` is the dedupe key per org; `sicon_contract_id` is
# captured for the ongoing two-way sync.
_CONTRACT_HEADERS = [
    "customer_account_number",
    "contract_number", "title", "company_name",
    "type", "tier", "status",
    "start_date", "end_date", "renewal_date",
    "annual_value", "total_value", "billing_frequency",
    "sla_response_hours", "sla_resolution_hours",
    "auto_renew",
    "sicon_contract_id", "sage_reference",
]
_CONTRACT_EXAMPLE = [
    "PULSENC01",
    "CON-2024-0142", "Tottenham Green — Gold Service Cover", "Tottenham Green Leisure Centre",
    "service", "gold", "active",
    "2024-01-15", "2029-01-14", "2028-11-15",
    "12500.00", "62500.00", "annual",
    "4", "24",
    "true",
    "8841", "TOTTGRN01",
]


def _csv_response(headers: list[str], example: list[str], filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerow(example)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/master-admin/bulk-import/templates/equipment")
async def template_equipment(user: dict = Depends(get_current_user)) -> Response:
    _require_pulse_or_master(user)
    return _csv_response(_EQUIPMENT_HEADERS, _EQUIPMENT_EXAMPLE, "equipment-template.csv")


# Iter 216h108 — customer-facing aliases. Pulse Pro operators (owners
# & managers) need the SAME import flow as Master Admin without having
# to flip portals. The endpoints below delegate to the same logic but:
#   • require only `get_current_user` (not master-admin)
#   • force `organization_id` to the caller's own org — they can NEVER
#     write into another tenant
#   • share the exact same template + parser
@router.get("/account/import/equipment/template")
async def customer_template_equipment(user: dict = Depends(get_current_user)) -> Response:
    if not user.get("organization_id"):
        raise HTTPException(status_code=403, detail="No tenant context")
    return _csv_response(_EQUIPMENT_HEADERS, _EQUIPMENT_EXAMPLE, "equipment-template.csv")


@router.post("/account/import/equipment")
async def customer_bulk_import_equipment(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Pulse Pro customer-scoped bulk equipment import.

    Same parser + template as the Master Admin endpoint — but the
    target organisation is HARD-CODED to ``user.organization_id`` so
    customers can never write into another tenant.
    """
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="No tenant context")
    # Customer flow — bypass the master-admin permission check but
    # hard-pin the target org so customers can never write into
    # another tenant.
    return await _do_bulk_import_equipment(file, org_id, user, validate_org=False)


@router.get("/master-admin/bulk-import/templates/customers")
async def template_customers(user: dict = Depends(get_current_user)) -> Response:
    _require_pulse_or_master(user)
    return _csv_response(_CUSTOMER_HEADERS, _CUSTOMER_EXAMPLE, "customers-template.csv")


@router.get("/master-admin/bulk-import/templates/contracts")
async def template_contracts(user: dict = Depends(get_current_user)) -> Response:
    _require_pulse_or_master(user)
    return _csv_response(_CONTRACT_HEADERS, _CONTRACT_EXAMPLE, "contracts-template.csv")


# ── Importers ────────────────────────────────────────────────────────────


def _parse_decimal(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        return float(s.replace(",", "").strip())
    except ValueError:
        return None


def _parse_int(s: str) -> Optional[int]:
    if not s:
        return None
    try:
        return int(float(str(s).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def _normalize_contract_type(value: str) -> Optional[str]:
    """Coerce a free-text contract-type cell to a canonical 'A' | 'B' | 'C'.

    Accepts 'A', 'Type A', 'Contract A', 'type_a', 'A Contract' etc. (any case).
    MOD SOR defines three service tiers (Type A/B/C). Returns None when blank
    or unrecognised (e.g. the machine is still under warranty)."""
    s = (value or "").strip().upper()
    if not s:
        return None
    import re as _re
    m = _re.search(r"\b([ABC])\b", s) or _re.search(r"([ABC])", s)
    return m.group(1) if m else None



def _normalize(row: dict, *keys: str) -> str:
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            return v
    return ""


def _is_blank_row(row: dict) -> bool:
    """Iter 216h56 — Excel + Google Sheets CSV exports routinely append
    millions of empty trailing rows (one operator reported a 10 M-row
    file with 98 real records). Without this check every empty row was
    counted as `skipped` AND appended to `errors` ('missing required
    column'), exploding the response payload and making the operator
    think the import was broken.

    Returns True if every cell in the row is empty/whitespace.
    """
    return all(not (v and str(v).strip()) for v in row.values())


_PLACEHOLDER_SERIALS = {"", "UNKNOWN", "N/A", "NA", "TBC", "TBD", "NONE", "-", "0"}


def _is_real_serial(serial: str) -> bool:
    """True when a serial is a genuine unique identifier (not a blank /
    placeholder like UNKNOWN). Placeholder serials must NOT be used as a
    dedupe key or every "UNKNOWN" machine would collapse into one."""
    return bool(serial) and serial.strip().upper() not in _PLACEHOLDER_SERIALS


def _equipment_composite_key(site_id, name, model, manufacturer) -> str:
    """Fallback dedupe key for placeholder-serial equipment: the tuple of
    site + name + model + manufacturer (lower-cased). Stable across
    re-imports so the same machine enriches rather than duplicates."""
    parts = [
        (site_id or "").strip().lower(),
        (name or "").strip().lower(),
        (model or "").strip().lower(),
        (manufacturer or "").strip().lower(),
    ]
    return "|".join(parts)


# Equipment fields safe to back-fill on re-import (fill-if-empty only —
# never overwrite an operator-entered value with a blank or a fresh guess).
_EQUIPMENT_ENRICH_FIELDS = (
    "equipment_type", "manufacturer", "model", "serial_number",
    "purchase_date", "warranty_expiry", "sla_start", "sla_expiry",
    "contract_number", "contract_type", "contract_start_date", "contract_end_date",
    "service_provider", "supplier", "supplier_id", "supplier_email", "purchased_from",
    "location", "notes", "sicon_equipment_id", "sage_item_id",
    "length", "width", "height", "purchase_price", "purchase_cost", "replacement_cost",
    "site_id", "mod_force", "asset_number", "sub_location", "category",
    "mod_code", "classification", "qr_code", "manufacturing_date", "condition", "quantity",
)


def _build_enrich_update(existing: dict, new_doc: dict, fields) -> dict:
    """Return a $set dict of only the fields that are EMPTY on the existing
    doc but have a value in the freshly-parsed row — so a re-import fills
    gaps without clobbering existing data."""
    upd: dict = {}
    for k in fields:
        cur = existing.get(k)
        new = new_doc.get(k)
        cur_empty = cur is None or (isinstance(cur, str) and not cur.strip())
        new_has = new is not None and not (isinstance(new, str) and not new.strip())
        if cur_empty and new_has:
            upd[k] = new
    return upd


def _fill_if_empty(existing: dict, new_vals: dict) -> dict:
    """Generic fill-if-empty for sites re-import enrichment."""
    upd: dict = {}
    for k, new in new_vals.items():
        cur = existing.get(k)
        cur_empty = cur is None or (isinstance(cur, str) and not cur.strip())
        new_has = new is not None and not (isinstance(new, str) and not new.strip())
        if cur_empty and new_has:
            upd[k] = new
    return upd


async def _resolve_target_org(user: dict, organization_id: Optional[str]) -> str:
    """If the admin specified `organization_id`, validate it's a Pulse-visible
    customer. Otherwise default to the admin's own organization (only valid
    for the Pulse Fitness Master Admin who isn't tenant-scoped — Pulse admins must
    pick a target).

    Iter 216h111 — Master admins can also target MOD orgs (mod_site /
    mod_branch / mod_org), so a presenter can import equipment + sites
    against the Demo Garrison hierarchy from the Master Admin UI.
    """
    if organization_id:
        allowed_types = list(PULSE_VISIBLE_ACCOUNT_TYPES)
        if user.get("is_master_admin"):
            allowed_types += ["mod_site", "mod_branch", "mod_org"]
        org = await db.organizations.find_one(
            {"id": organization_id, "account_type": {"$in": allowed_types}},
            {"_id": 0, "id": 1},
        )
        if not org:
            raise HTTPException(status_code=404, detail="Target organization not found or not Pulse-visible")
        return organization_id
    if user.get("organization_id"):
        return user["organization_id"]
    raise HTTPException(
        status_code=400,
        detail="organization_id is required when importing as a platform admin (no tenant context).",
    )


# Common header aliases for the per-row customer account number column.
_ACCOUNT_HEADER_ALIASES = (
    "customer_account_number", "Customer Account Number", "customer_number",
    "Customer Number", "CustomerNumber", "CustomerNumberID", "account_number",
    "Account Number", "Account Code", "sage_customer_number", "Sage Customer Number",
    "sicon_customer_number",
)


async def _lookup_org_by_account_number(account_number: str) -> Optional[str]:
    """Resolve a customer-account-number string to a Pulse-visible org id.

    Matches against any of the org doc fields the rest of the platform
    populates (`customer_account_number`, `sage_customer_number`,
    `sicon_customer_number`). Returns ``None`` if no match found.

    Iter — sites fallback. Pulse Fitness stores Sicon's "Invoice Customer
    Ref" on each SITE (`invoice_customer_ref` / `sicon_customer_ref`) rather
    than on the org, so a sites-first onboarding leaves the org record with
    no account number. When the direct org lookup misses we therefore also
    look the code up against the sites and route to that site's org — this
    lets "auto-route by account number" work off the exact same value the
    operator already put on the sites CSV, with no org edit required.
    """
    code = (account_number or "").strip()
    if not code:
        return None
    visible = list(PULSE_VISIBLE_ACCOUNT_TYPES)
    org = await db.organizations.find_one(
        {
            "account_type": {"$in": visible},
            "$or": [
                {"customer_account_number": code},
                {"sage_customer_number": code},
                {"sicon_customer_number": code},
            ],
        },
        {"_id": 0, "id": 1},
    )
    if org:
        return org["id"]
    # Fallback — the account number may only live on the sites.
    site = await db.sites.find_one(
        {"$or": [{"invoice_customer_ref": code}, {"sicon_customer_ref": code}]},
        {"_id": 0, "organization_id": 1},
    )
    if site and site.get("organization_id"):
        parent = await db.organizations.find_one(
            {
                "id": site["organization_id"],
                "$or": [
                    {"account_type": {"$in": visible}},
                    {"account_type": {"$exists": False}},
                    {"account_type": None},
                ],
            },
            {"_id": 0, "id": 1},
        )
        if parent:
            return parent["id"]
    return None


async def _resolve_row_target_org(
    row: dict,
    default_org_id: Optional[str],
    cache: dict,
) -> tuple[Optional[str], Optional[str]]:
    """Per-row resolver — returns (target_org_id, error_or_none).

    If ``default_org_id`` was set on the request, every row goes there.
    Otherwise we look up by the row's `customer_account_number` column.
    A small in-flight cache means re-using the same code is one DB hit.
    """
    if default_org_id:
        return default_org_id, None
    code = _normalize(row, *_ACCOUNT_HEADER_ALIASES)
    if not code:
        return None, "Missing customer_account_number (and no target organisation specified)"
    if code in cache:
        return cache[code], None if cache[code] else f"Unknown customer_account_number '{code}'"
    org_id = await _lookup_org_by_account_number(code)
    cache[code] = org_id
    return org_id, None if org_id else f"Unknown customer_account_number '{code}'"


# Iter 216h50 — equipment-import site resolver. Matches on (in order):
#   1. Exact-match site name (case-insensitive)
#   2. Tolerant name — trailing generic suffix ("Fire Station", "Station",
#      "Leisure Centre" …) stripped from BOTH sides so an equipment CSV
#      that names sites "Bridgwater Fire Station" links to the site row
#      "Bridgwater" imported earlier. Only a trailing GENERIC word is
#      dropped, so distinct sites never collapse into one.
#   3. invoice_customer_ref / sicon_customer_ref equality
#   4. Returns (None, "site not found") so the row is reported, not silently inserted
#
# Longest-first so "fire station" is stripped before the bare "station".
_GENERIC_SITE_SUFFIXES = (
    "fire station", "ambulance station", "police station", "rescue station",
    "leisure centre", "leisure center", "sports centre", "sports center",
    "community centre", "community center", "fitness centre", "fitness center",
    "recreation centre", "recreation center", "health club",
    "fire & rescue", "fire and rescue",
    "station", "centre", "center", "gym", "club",
)


def _normalize_site_name(name: str) -> str:
    """Lower-case, collapse whitespace and strip ONE trailing generic
    suffix so tolerant matching can pair "Bridgwater Fire Station" with
    the site "Bridgwater"."""
    import re as _re
    s = _re.sub(r"\s+", " ", (name or "").strip().lower())
    if not s:
        return ""
    for suf in _GENERIC_SITE_SUFFIXES:
        if s == suf:
            continue
        if s.endswith(" " + suf):
            return s[: -(len(suf) + 1)].strip()
    return s


async def _site_index_for_org(org_id: str, cache: dict) -> dict:
    """Build (once, cached) an index of the org's sites so equipment rows
    resolve to a site by exact name, tolerant (suffix-stripped) name, or
    invoice_customer_ref. Shape: {by_name, by_norm, by_ref}."""
    if org_id in cache:
        return cache[org_id]
    by_name: dict = {}
    by_norm: dict = {}
    by_ref: dict = {}
    cursor = db.sites.find(
        {"organization_id": org_id},
        {"_id": 0, "id": 1, "name": 1, "invoice_customer_ref": 1, "sicon_customer_ref": 1},
    )
    async for s in cursor:
        sid = s.get("id")
        nm = (s.get("name") or "").strip().lower()
        if nm and nm not in by_name:
            by_name[nm] = sid
        norm = _normalize_site_name(s.get("name") or "")
        if norm and norm not in by_norm:
            by_norm[norm] = sid
        for ref_field in ("invoice_customer_ref", "sicon_customer_ref"):
            ref = (s.get(ref_field) or "").strip()
            if ref and ref not in by_ref:
                by_ref[ref] = sid
    idx = {"by_name": by_name, "by_norm": by_norm, "by_ref": by_ref}
    cache[org_id] = idx
    return idx


async def _resolve_site_for_org(
    site_name: str,
    invoice_customer_ref: str,
    org_id: str,
    cache: dict,
) -> tuple[Optional[str], Optional[str]]:
    """Resolve a site reference to a site_id within the org. Returns
    (site_id, error_or_none). Site name takes priority over the ref; if
    neither is supplied the row is allowed through with site_id=None so
    org-wide kit imports still work."""
    site_name = (site_name or "").strip()
    ref = (invoice_customer_ref or "").strip()
    if not site_name and not ref:
        return None, None  # site is genuinely optional
    idx = await _site_index_for_org(org_id, cache)
    site_id = None
    if site_name:
        site_id = idx["by_name"].get(site_name.lower())
        if not site_id:
            site_id = idx["by_norm"].get(_normalize_site_name(site_name))
    if not site_id and ref:
        site_id = idx["by_ref"].get(ref)
    return site_id, (None if site_id else f"Site '{site_name or ref}' not found in target org — import the sites first")


# Iter 216h51 — supplier resolver. The equipment import accepts a
# `supplier` column that maps to an existing row in db.suppliers within
# the same org. The match is fuzzy-by-design so spreadsheets with
# slightly different capitalisation (e.g. "Pulse Fitness" vs "Pulse
# Fitness Limited") still resolve. When matched, the supplier's id +
# email get baked onto the equipment doc so the auto-fault-email flow
# can route notifications to the right service-supplier inbox without
# a per-equipment lookup.
async def _resolve_supplier_for_org(
    supplier_name: str,
    org_id: str,
    cache: dict,
) -> Optional[dict]:
    """Return the matched supplier doc ({id, name, email, ...}) or None
    if either no supplier name was supplied OR no match was found.
    Result is cached per (org_id, lower(name))."""
    name = (supplier_name or "").strip()
    if not name:
        return None
    key = (org_id, name.lower())
    if key in cache:
        return cache[key]
    import re as _re
    safe = _re.escape(name)
    # 1) Exact (case-insensitive) name match.
    match = await db.suppliers.find_one(
        {"organization_id": org_id, "name": {"$regex": f"^{safe}$", "$options": "i"}},
        {"_id": 0},
    )
    # 2) Email match (if the CSV column accidentally has an email).
    if not match and "@" in name:
        match = await db.suppliers.find_one(
            {"organization_id": org_id, "service_email": name.lower()},
            {"_id": 0},
        )
        if not match:
            match = await db.suppliers.find_one(
                {"organization_id": org_id, "email": name.lower()},
                {"_id": 0},
            )
    # 3) Normalised name fallback ("Pulse Fitness Ltd." ⇄ "pulsefitness").
    if not match:
        # Cheap, since suppliers per org rarely > 50.
        normalised_target = _re.sub(r"[^a-z0-9]+", "", name.lower())
        for suffix in (" limited", " ltd.", " ltd", " plc", " inc", " inc.", " llc"):
            if normalised_target.endswith(_re.sub(r"[^a-z0-9]+", "", suffix)):
                normalised_target = normalised_target[: -len(_re.sub(r"[^a-z0-9]+", "", suffix))]
        cursor = db.suppliers.find(
            {"organization_id": org_id},
            {"_id": 0, "id": 1, "name": 1, "service_email": 1, "email": 1, "phone": 1},
        )
        async for sup in cursor:
            ssn = _re.sub(r"[^a-z0-9]+", "", (sup.get("name") or "").lower())
            if ssn and ssn == normalised_target:
                match = sup
                break
    cache[key] = match
    return match


# ── Import batches — one-click undo of the last bulk load ────────────────

async def _record_import_batch(
    *, batch_id: str, kind: str, user: dict, org_ids: list,
    inserted: int, updated: int, skipped: int,
    filename: Optional[str] = None, org_snapshots: Optional[dict] = None,
) -> None:
    """Persist an `import_batches` record so the run can be rolled back.

    `org_snapshots` (sites only) captures the org's head-office / account
    fields BEFORE the import so undo can restore them if this batch stamped
    them."""
    try:
        await db.import_batches.insert_one({
            "id": batch_id,
            "kind": kind,
            "organization_ids": [o for o in (org_ids or []) if o],
            "actor_email": user.get("email") or user.get("full_name") or "system",
            "filename": filename,
            "inserted_count": int(inserted or 0),
            "updated_count": int(updated or 0),
            "skipped_count": int(skipped or 0),
            "org_snapshots": org_snapshots or {},
            "undone": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:  # never fail the import over audit bookkeeping
        logger.warning(f"failed to record import batch {batch_id}: {exc}")


async def _ensure_crm_company_for_org(
    operator_org_id: str, customer_org_id: str, user: dict,
    account_number: Optional[str] = None,
) -> Optional[str]:
    """Master Admin → CRM bridge. Ensure a `crm2_companies` record exists in
    the OPERATOR's tenant (Pulse Fitness Ltd) for an imported customer org,
    so imported estates surface in the CRM as well as the Service Desk.
    Idempotent — matches an existing company by `linked_organization_id`
    then by name. Returns the crm2_companies id (or None if not applicable)."""
    if not operator_org_id or not customer_org_id or operator_org_id == customer_org_id:
        return None
    now = datetime.now(timezone.utc).isoformat()
    cust = await db.organizations.find_one({"id": customer_org_id}, {"_id": 0}) or {}
    name = (cust.get("name") or "").strip() or "Imported customer"
    acct = (account_number or cust.get("customer_account_number")
            or cust.get("sicon_customer_number") or "").strip()

    # Match an existing CRM company for this customer. Search by the customer
    # link ACROSS orgs first so estates previously mis-bridged into the wrong
    # tenant (e.g. the master-admin org) are re-pointed here rather than
    # duplicated.
    existing = await db.crm2_companies.find_one(
        {"linked_organization_id": customer_org_id, "created_via": "master_admin_bulk_import"},
        {"_id": 0, "id": 1},
    )
    if not existing:
        existing = await db.crm2_companies.find_one(
            {"organization_id": operator_org_id, "linked_organization_id": customer_org_id},
            {"_id": 0, "id": 1},
        )
    if not existing:
        from utils.security_plus import safe_regex
        existing = await db.crm2_companies.find_one(
            {"organization_id": operator_org_id, "name": safe_regex(f"^{name}$")},
            {"_id": 0, "id": 1},
        )
    if existing:
        upd = {"organization_id": operator_org_id, "linked_organization_id": customer_org_id,
               "type": "customer", "updated_at": now}
        if acct:
            upd["account_number"] = acct
        await db.crm2_companies.update_one({"id": existing["id"]}, {"$set": upd})
        return existing["id"]

    cid = str(uuid.uuid4())
    doc = {
        "id": cid, "organization_id": operator_org_id, "site_id": None,
        "name": name, "sector": cust.get("industry", ""), "type": "customer",
        "parent_id": None,
        "website": cust.get("website", ""), "phone": cust.get("phone", ""),
        "email": cust.get("primary_contact_email", ""),
        "address": cust.get("address", ""),
        "address_line1": cust.get("address_line1", ""), "address_line2": cust.get("address_line2", ""),
        "address_line3": cust.get("address_line3", ""),
        "city": cust.get("city", ""), "postcode": cust.get("postcode", ""),
        "county": cust.get("county", ""), "country": cust.get("country", "United Kingdom"),
        "company_number": "", "description": "", "directors": [],
        "account_owner_id": user.get("id"), "account_owner_name": user.get("full_name", ""),
        "sla_tier": "standard", "revenue_band": "", "status": "active",
        "tags": ["imported"], "notes": "", "territory_id": None,
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""), "region": "",
        "account_number": acct,
        "linked_organization_id": customer_org_id, "is_operator_company": False,
        "created_via": "master_admin_bulk_import",
        "created_at": now, "updated_at": now,
    }
    await db.crm2_companies.insert_one(doc)
    return cid


def _crm2_contact_doc(operator_org, company_id, company_name, c, user) -> dict:
    """Build a `crm2_contacts` doc for an imported customer person, linked to
    the customer's CRM company under the operator tenant."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()), "organization_id": operator_org, "site_id": None,
        "first_name": c.get("first_name", ""), "last_name": c.get("last_name", ""),
        "email": c.get("email", ""), "phone": c.get("phone", ""), "mobile": c.get("phone", ""),
        "job_title": c.get("title", ""),
        "company_id": company_id, "company_name": company_name or c.get("company_name", ""),
        "influence_types": [], "is_decision_maker": False, "is_champion": False,
        "buying_influence_level": "", "adoption_sentiment": "", "coverage_confidence": "",
        "reports_to_id": None, "personal_wins": "", "linkedin": c.get("linkedin_url", ""),
        "source": "master_admin_bulk_import", "status": "active", "tags": ["imported"],
        "lifecycle": "customer", "gdpr_consent": False, "gdpr_consent_date": None,
        "communication_preferences": {}, "opt_out_email": False, "opt_out_sms": False,
        "opt_out_phone": False, "opt_out_post": False, "opt_out_marketing": False,
        "opt_out_updated_at": None, "relationship_score": 0,
        "owner_id": user.get("id"), "owner_name": user.get("full_name", ""),
        "notes": "", "territory_id": None,
        "postcode": "", "county": "", "region": "", "country": "United Kingdom",
        "gdpr_erased": False, "created_at": now, "updated_at": now,
    }


async def _mirror_site_managers_to_crm(operator_org, company_id, company_name, site_contacts, user) -> int:
    """Pull each site's manager (from the sites CSV) into the operator CRM as
    a contact linked to the customer company AND tagged to that site. Dedupe
    by email across the operator tenant; emailless managers dedupe by
    (company, site, name). Idempotent across re-imports."""
    if not company_id or not site_contacts:
        return 0
    seen_emails = {
        (d.get("email") or "").lower()
        async for d in db.crm2_contacts.find(
            {"organization_id": operator_org, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1},
        ) if d.get("email")
    }
    made = 0
    for sc in site_contacts:
        name = (sc.get("name") or "").strip()
        email = (sc.get("email") or "").strip().lower()
        if not name and not email:
            continue
        if email and email in seen_emails:
            continue
        if not email:
            dup = await db.crm2_contacts.find_one(
                {"organization_id": operator_org, "company_id": company_id,
                 "customer_site_id": sc.get("site_id"), "first_name": name.split(" ")[0]},
                {"_id": 0, "id": 1},
            )
            if dup:
                continue
        parts = name.split(" ", 1)
        doc = _crm2_contact_doc(
            operator_org, company_id, company_name,
            {"first_name": parts[0] if parts else "", "last_name": parts[1] if len(parts) > 1 else "",
             "email": email, "phone": sc.get("phone", ""), "title": "Site Manager",
             "company_name": company_name},
            user,
        )
        doc["customer_site_id"] = sc.get("site_id")
        doc["customer_site_name"] = sc.get("site_name", "")
        doc["job_title"] = f"Site Manager — {sc.get('site_name', '')}".strip(" —")
        doc["tags"] = ["imported", "site-manager"]
        await db.crm2_contacts.insert_one(doc)
        if email:
            seen_emails.add(email)
        made += 1
    return made


async def _resolve_operator_org(user: dict) -> str:
    """The CRM tenant that imported estates must bridge into — ALWAYS the
    operator company (Pulse Fitness Ltd), never the master-admin super-user's
    own org. Master Admin imports were previously stamped with the importing
    admin's org, so bridged companies landed in the wrong CRM tenant and never
    surfaced in the CRM Companies list. Falls back to the user's org only if no
    operator company is flagged."""
    op = await db.organizations.find_one({"is_operator_company": True}, {"_id": 0, "id": 1})
    if op and op.get("id"):
        return op["id"]
    return user.get("organization_id") or user.get("service_org_id")


async def _bridge_import_to_crm(org_ids, user: dict) -> int:
    """Ensure a CRM company exists for each customer org touched by an import.
    `user.organization_id` is the operator tenant (Pulse Fitness Ltd)."""
    operator = await _resolve_operator_org(user)
    made = 0
    for oid in {o for o in (org_ids or []) if o}:
        try:
            if await _ensure_crm_company_for_org(operator, oid, user):
                made += 1
        except Exception as exc:  # never fail an import over the CRM mirror
            logger.warning(f"CRM bridge failed for org {oid}: {exc}")
    return made


def _is_pulse_visible_account_type(account_type) -> bool:
    """Pulse-visible customer-estate account types: the base visible set
    (pulse_pro/lite/mod/full) PLUS every MOD variant (mod_org/mod_site/
    mod_branch). Unset (None/"") is treated as visible for legacy estates.
    Fixes MOD estates being silently skipped by exact-match "mod" gates."""
    at = (account_type or "").lower()
    if not at:
        return True
    return at in PULSE_VISIBLE_ACCOUNT_TYPES or at.startswith("mod")


@router.post("/master-admin/bulk-import/backfill-crm")
async def backfill_crm_companies(user: dict = Depends(get_current_user)) -> dict:
    """Back-fill: ensure every already-imported customer estate has a CRM
    company in the Pulse Fitness Ltd tenant. Scans orgs that own sites or
    equipment AND every Pulse-visible estate (incl. MOD HQs without their own
    kit), skips the operator's own tenant, and is fully idempotent."""
    _require_pulse_or_master(user)
    operator = await _resolve_operator_org(user)
    site_orgs = await db.sites.distinct("organization_id")
    equip_orgs = await db.equipment.distinct("organization_id")
    candidate_ids = {o for o in (list(site_orgs) + list(equip_orgs)) if o and o != operator}
    # Also include any Pulse-visible customer estate (incl. MOD HQs/sites) even
    # if it owns no sites/equipment itself, so every onboarded company surfaces.
    async for org in db.organizations.find(
        {"is_operator_company": {"$ne": True}}, {"_id": 0, "id": 1, "account_type": 1}):
        oid = org.get("id")
        if oid and oid != operator and _is_pulse_visible_account_type(org.get("account_type")):
            candidate_ids.add(oid)
    made = 0
    checked = 0
    for oid in candidate_ids:
        org = await db.organizations.find_one(
            {"id": oid}, {"_id": 0, "id": 1, "account_type": 1},
        )
        if not org:
            continue
        if not _is_pulse_visible_account_type(org.get("account_type")):
            continue
        checked += 1
        try:
            if await _ensure_crm_company_for_org(operator, oid, user):
                made += 1
        except Exception as exc:
            logger.warning(f"CRM backfill failed for org {oid}: {exc}")
    # Now that customer estates are linked, surface any calibration
    # certificates from already-closed cases into their Documents.
    certs = {"scanned": 0, "published": 0}
    try:
        from utils.calibration_cert_publish import backfill_calibration_certificates
        certs = await backfill_calibration_certificates(operator)
    except Exception as exc:
        logger.warning(f"Calibration certificate backfill failed: {exc}")
    return {"success": True, "customers_linked": made, "orgs_checked": checked,
            "certificates_published": certs.get("published", 0)}


@router.get("/master-admin/bulk-import/batches")
async def list_import_batches(
    organization_id: Optional[str] = Query(None),
    limit: int = Query(10),
    user: dict = Depends(get_current_user),
) -> dict:
    """Recent bulk-import batches (newest first) for the Undo panel."""
    _require_pulse_or_master(user)
    q: dict = {"undone": {"$ne": True}}
    if organization_id:
        q["organization_ids"] = organization_id
    cap = max(1, min(int(limit or 10), 50))
    batches = await db.import_batches.find(q, {"_id": 0}).sort("created_at", -1).limit(cap).to_list(cap)
    return {"batches": batches}


@router.post("/master-admin/bulk-import/undo/{batch_id}")
async def undo_import_batch(batch_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Roll back a bulk import: delete every row this batch INSERTED and,
    for sites, restore the org's head-office / account snapshot. Enriched
    (fill-if-empty) updates are NOT reverted — reported in `note`."""
    _require_pulse_or_master(user)
    batch = await db.import_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")
    if batch.get("undone"):
        raise HTTPException(status_code=409, detail="This import has already been undone")

    kind = batch.get("kind")
    coll = {"equipment": db.equipment, "sites": db.sites}.get(kind)
    if coll is None:
        raise HTTPException(status_code=400, detail=f"Undo not supported for '{kind}' imports")

    res = await coll.delete_many({"import_batch_id": batch_id})
    removed = res.deleted_count

    # Sites — restore the org head-office/account snapshot + recount.
    if kind == "sites":
        for org_id, snap in (batch.get("org_snapshots") or {}).items():
            total = await db.sites.count_documents({"organization_id": org_id})
            restore = dict(snap or {})
            restore["site_count"] = total
            restore["is_multi_site"] = total > 1
            await db.organizations.update_one({"id": org_id}, {"$set": restore})

    await db.import_batches.update_one(
        {"id": batch_id},
        {"$set": {"undone": True, "undone_at": datetime.now(timezone.utc).isoformat(),
                  "undone_by": user.get("email", "system"), "removed_count": removed}},
    )
    try:
        from routes.master_admin import log_activity
        for oid in batch.get("organization_ids", []):
            await log_activity(
                "import_undone", f"Undid bulk {kind} import — removed {removed} row(s)",
                user.get("email", "system"), "organization", oid,
            )
    except Exception:
        pass

    note = None
    if batch.get("updated_count"):
        note = (f"{batch['updated_count']} existing row(s) were enriched (fields filled in) by this "
                f"import — those field updates are not reverted, only the {removed} newly-added row(s) were removed.")
    return {"success": True, "removed": removed, "kind": kind, "note": note}


async def _suggest_site_name(org_id: str, query: str, name_cache: dict) -> Optional[str]:
    """Closest existing site display-name for an unmatched query, so the
    operator can quickly fix a straggler (e.g. 'Airport Fire Station')."""
    if org_id not in name_cache:
        names = []
        cursor = db.sites.find({"organization_id": org_id}, {"_id": 0, "name": 1})
        async for s in cursor:
            nm = (s.get("name") or "").strip()
            if nm:
                names.append(nm)
        name_cache[org_id] = names
    names = name_cache[org_id]
    if not names:
        return None
    import difflib
    qn = _normalize_site_name(query)
    norm_map = {_normalize_site_name(n): n for n in names}
    hit = difflib.get_close_matches(qn, list(norm_map.keys()), n=1, cutoff=0.7)
    if hit:
        return norm_map[hit[0]]
    hit = difflib.get_close_matches(query.lower(), [n.lower() for n in names], n=1, cutoff=0.6)
    if hit:
        for n in names:
            if n.lower() == hit[0]:
                return n
    return None


@router.post("/master-admin/bulk-import/equipment/preview")
async def preview_equipment_sites(
    file: UploadFile = File(...),
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    """DRY-RUN — parse the equipment CSV and report which site names WOULD
    match a site (tolerant matching) and which would NOT, before anything is
    written. Lets the operator fix stragglers like 'Airport Fire Station'
    up front."""
    _require_pulse_or_master(user)
    default_org = await _resolve_target_org(user, organization_id) if organization_id else None

    contents = await file.read()
    validate_upload(file_bytes=contents, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=200 * 1024 * 1024)
    from utils.spreadsheet_import import iter_rows
    rows_iter = iter_rows(contents, file.filename)

    org_cache: dict = {}
    site_cache: dict = {}
    name_cache: dict = {}
    total = matched = no_site = 0
    unmatched_by_name: dict = {}
    account_issues: dict = {}

    for row in rows_iter:
        if _is_blank_row(row):
            continue
        total += 1
        target_org, _route_err = await _resolve_row_target_org(row, default_org, org_cache)
        if not target_org:
            code = _normalize(row, *_ACCOUNT_HEADER_ALIASES) or "(blank)"
            account_issues[code] = account_issues.get(code, 0) + 1
            continue
        site_name = _normalize(row, "site_name", "Site Name", "site")
        ref = _normalize(row, "invoice_customer_ref", "Invoice Customer Ref", "sicon_customer_ref", "customer_ref")
        if not site_name and not ref:
            no_site += 1
            continue
        site_id, _err = await _resolve_site_for_org(site_name, ref, target_org, site_cache)
        if site_id:
            matched += 1
        else:
            key = site_name or ref
            entry = unmatched_by_name.get(key)
            if not entry:
                entry = {
                    "site_name": key,
                    "rows": 0,
                    "organization_id": target_org,
                    "suggestion": await _suggest_site_name(target_org, key, name_cache),
                }
                unmatched_by_name[key] = entry
            entry["rows"] += 1

    unmatched_sites = sorted(unmatched_by_name.values(), key=lambda e: -e["rows"])
    unmatched_rows = sum(e["rows"] for e in unmatched_sites)
    return {
        "total_rows": total,
        "matched_rows": matched,
        "org_wide_rows": no_site,          # no site named → import as org-wide kit
        "unmatched_rows": unmatched_rows,
        "will_import": matched + no_site,
        "unmatched_sites": unmatched_sites,
        "unmatched_site_count": len(unmatched_sites),
        "account_number_issues": [
            {"account_number": k, "rows": v} for k, v in sorted(account_issues.items(), key=lambda kv: -kv[1])
        ],
        "target_org": default_org,
    }



@router.post("/master-admin/bulk-import/equipment")
async def bulk_import_equipment(
    file: UploadFile = File(...),
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    _require_pulse_or_master(user)
    return await _do_bulk_import_equipment(file, organization_id, user, validate_org=True)


async def _do_bulk_import_equipment(
    file: UploadFile,
    organization_id: Optional[str],
    user: dict,
    validate_org: bool = True,
    replace_existing: bool = False,
) -> dict:
    """Shared equipment-import core (Iter 216h108).

    Used by both the master-admin endpoint (validate_org=True so the
    operator can target any Pulse-visible customer) and the customer
    endpoint (validate_org=False — the caller passes their own
    organization_id so the Pulse-visibility check would always fail).

    `replace_existing`=True — a row whose serial already exists is UPDATED
    in place (matched by org+serial) instead of skipped, so a corrected
    re-import overwrites the old data rather than being rejected as a dup."""
    if validate_org:
        default_org = await _resolve_target_org(user, organization_id) if organization_id else None
    else:
        default_org = organization_id

    # Iter — import batch id so the whole run can be rolled back in one
    # click. Every INSERTED doc is tagged; enriched/updated docs are not
    # (their pre-import values can't be cleanly reconstructed).
    batch_id = str(uuid.uuid4())

    contents = await file.read()
    # Iter 216h55 — Pulse Fitness onboards ~500k equipment pieces in one
    # CSV (~120-150 MB). The middleware enforces 200 MB upstream so we
    # match that ceiling here. Smaller customers naturally pay nothing
    # extra — the cost is only on the actual byte size.
    validate_upload(file_bytes=contents, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=200 * 1024 * 1024)
    # Iter 216h108 — accept .xlsx as well as CSV via the shared helper.
    from utils.spreadsheet_import import iter_rows, parse_date_cell, get_pick, parse_force
    rows_iter = iter_rows(contents, file.filename)

    imported, skipped, errors = 0, 0, []
    updated = 0
    org_cache: dict = {}
    org_doc_cache: dict = {}  # Iter 216h111 — cache org docs for force validation
    site_cache: dict = {}
    supplier_cache: dict = {}
    # Iter 216h55 — per-org cache of existing serial numbers. One bulk
    # query on first hit per org replaces 500k per-row find_one calls
    # (~30 min → ~3 s on Pulse scale).
    serial_set_cache: dict = {}
    composite_set_cache: dict = {}
    org_breakdown: dict = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    # Iter 216h55 — batched inserts. 500 docs per insert_many call gives
    # the best throughput vs. memory trade-off on Pulse-scale imports.
    BATCH_SIZE = 500
    pending: list = []

    async def _flush_pending():
        if not pending:
            return
        try:
            await db.equipment.insert_many(pending, ordered=False)
        except Exception as exc:
            logger.warning(f"bulk insert_many failed, falling back row-by-row: {exc}")
            for d in pending:
                try:
                    await db.equipment.insert_one(d)
                except Exception as e2:
                    errors.append(f"DB insert failed for row id {d.get('id')}: {e2}")
        pending.clear()

    async def _serial_set_for(target_org: str) -> set:
        if target_org in serial_set_cache:
            return serial_set_cache[target_org]
        cursor = db.equipment.find(
            {"organization_id": target_org, "serial_number": {"$exists": True, "$ne": ""}},
            {"_id": 0, "serial_number": 1},
        )
        s = {doc["serial_number"] async for doc in cursor if doc.get("serial_number")}
        serial_set_cache[target_org] = s
        return s

    async def _composite_set_for(target_org: str) -> set:
        """Set of composite keys (site|name|model|manufacturer) for every
        existing equipment doc in the org — the dedupe key for
        placeholder-serial machines on re-import."""
        if target_org in composite_set_cache:
            return composite_set_cache[target_org]
        cursor = db.equipment.find(
            {"organization_id": target_org},
            {"_id": 0, "name": 1, "model": 1, "manufacturer": 1, "site_id": 1},
        )
        s = {
            _equipment_composite_key(d.get("site_id"), d.get("name"), d.get("model"), d.get("manufacturer"))
            async for d in cursor
        }
        composite_set_cache[target_org] = s
        return s

    for i, row in enumerate(rows_iter, start=2):  # +1 header, +1 1-indexed
        try:
            # Iter 216h56 — Excel/Sheets exports drag along millions of
            # empty trailing rows. Skip them silently so they don't
            # pollute `skipped` + `errors`.
            if _is_blank_row(row):
                continue
            target_org, route_err = await _resolve_row_target_org(row, default_org, org_cache)
            if not target_org:
                skipped += 1
                if route_err:
                    errors.append(f"Row {i}: {route_err}")
                continue
            name = _normalize(row, "name", "Name") or str(get_pick(row, "name", "")).strip()
            if not name:
                skipped += 1
                errors.append(f"Row {i}: missing required column 'name'")
                continue
            serial = _normalize(row, "serial_number", "Serial Number", "serial") or str(get_pick(row, "serial_number", "")).strip()
            # Dedupe decision is deferred until the full doc is built (we
            # need site_id / model / manufacturer for the placeholder-serial
            # composite key). `is_real` gates whether the serial alone is a
            # trustworthy unique key.
            is_real = _is_real_serial(serial)
            # Iter 216h50 — link to a pre-imported site by name (or by
            # Sicon "Invoice Customer Ref" fallback). Sites import runs
            # first during onboarding so by the time equipment lands the
            # site rows already exist.
            site_name = _normalize(row, "site_name", "Site Name", "site") or str(get_pick(row, "site_name", "")).strip()
            invoice_customer_ref = _normalize(
                row, "invoice_customer_ref", "Invoice Customer Ref",
                "sicon_customer_ref", "customer_ref",
            ) or str(get_pick(row, "invoice_customer_ref", "")).strip()
            site_id, site_err = await _resolve_site_for_org(site_name, invoice_customer_ref, target_org, site_cache)
            if (site_name or invoice_customer_ref) and not site_id:
                # The operator explicitly named a site that doesn't exist — surface
                # so they can re-run the sites import first.
                skipped += 1
                if site_err:
                    errors.append(f"Row {i}: {site_err}")
                continue
            unit_price_raw = _normalize(row, "unit_price", "Unit Price", "price", "Price") or str(get_pick(row, "unit_price", "")).strip()
            unit_price = _parse_decimal(unit_price_raw)
            replacement_cost_raw = _normalize(row, "replacement_cost", "Replacement Cost") or str(get_pick(row, "replacement_cost", "")).strip()
            replacement_cost = _parse_decimal(replacement_cost_raw)
            # ── Resolve target org (is_mod) BEFORE supplier so MOD imports
            # can default a blank supplier to the locked Pulse Fitness service
            # supplier (never the manufacturer). ──
            if target_org not in org_doc_cache:
                org_doc_cache[target_org] = await db.organizations.find_one(
                    {"id": target_org}, {"_id": 0, "is_mod": 1, "mod_force": 1},
                ) or {}
            is_mod_org = bool(org_doc_cache[target_org].get("is_mod"))
            # Iter — supplier defaulting. The SERVICE supplier is Pulse Fitness
            # by default (Pulse sells & services the MOD kit); it is NOT the
            # manufacturer. So:
            #   • a blank supplier on a MOD import  → "Pulse Fitness Ltd"
            #   • "Pulse Fitness" typed by the site → resolves to Pulse Fitness Ltd
            #   • non-MOD import, blank supplier     → manufacturer (legacy behaviour)
            # ── Service provider vs original supplier ──────────────────────
            # SERVICE PROVIDER = the company servicing/maintaining the kit
            # (routes faults; defaults to Pulse Fitness Ltd). PURCHASED FROM =
            # the original vendor the kit was bought from (MOD only — a lot of
            # legacy MOD kit wasn't supplied by Pulse). For MOD the servicing
            # company comes from the `service_provider` column; the `supplier`
            # column is treated as the original vendor.
            import re as _re_pf
            def _canon_pulse(v: str) -> str:
                return PULSE_DEFAULT_SUPPLIER_NAME if _re_pf.sub(r"[^a-z0-9]+", "", (v or "").lower()).startswith("pulsefitness") else v
            supplier_col = _normalize(row, "supplier", "Supplier") or str(get_pick(row, "supplier", "")).strip()
            service_col = _normalize(row, "service_provider", "Service Provider") or str(get_pick(row, "service_provider", "")).strip()
            purchased_from = None
            if is_mod_org:
                # Servicing company: service_provider col → else supplier col →
                # else the locked Pulse Fitness Ltd default.
                service_input = _canon_pulse(service_col) or _canon_pulse(supplier_col) or PULSE_DEFAULT_SUPPLIER_NAME
                supplier_input = service_input
                # Original vendor kept separately (blank unless supplied AND it
                # isn't just Pulse Fitness again).
                if supplier_col and _canon_pulse(supplier_col) != PULSE_DEFAULT_SUPPLIER_NAME:
                    purchased_from = supplier_col
            else:
                # Non-MOD unchanged: supplier col → manufacturer fallback.
                supplier_input = supplier_col or (
                    _normalize(row, "manufacturer") or str(get_pick(row, "manufacturer", "")).strip()
                )
                supplier_input = _canon_pulse(supplier_input) if supplier_input else supplier_input
            supplier_match = await _resolve_supplier_for_org(supplier_input, target_org, supplier_cache)
            # Iter 216h108 — robust date parsing. Excel serials (45979),
            # dd/mm/yyyy, ISO etc. all coerce to YYYY-MM-DD before
            # storage so downstream UIs render correctly.
            purchase_date_iso = parse_date_cell(
                get_pick(row, "purchase_date") or row.get("Purchase Date") or row.get("purchase_date") or row.get("Install Date") or row.get("install_date")
            )
            warranty_iso = parse_date_cell(
                get_pick(row, "warranty_expiry") or row.get("Warranty Expiry") or row.get("warranty_expiry") or row.get("Warranty Expiry Date")
            )
            contract_start_iso = parse_date_cell(get_pick(row, "contract_start"))
            contract_end_iso = parse_date_cell(get_pick(row, "contract_end"))
            # Iter 216h111 — MOD Force tag. Parse the row's Force value
            # (Army / RAF / Navy) and validate it against the target
            # org's `mod_force` if the org is MOD-flagged.
            row_force = parse_force(get_pick(row, "mod_force"))
            if target_org not in org_doc_cache:
                org_doc_cache[target_org] = await db.organizations.find_one(
                    {"id": target_org}, {"_id": 0, "is_mod": 1, "mod_force": 1},
                ) or {}
            target_org_doc = org_doc_cache[target_org]
            if target_org_doc.get("is_mod") and target_org_doc.get("mod_force"):
                expected = (target_org_doc.get("mod_force") or "").lower()
                if row_force and row_force != expected:
                    skipped += 1
                    errors.append(f"Row {i}: force '{row_force}' does not match the target org's force '{expected}'")
                    continue
                if not row_force:
                    row_force = expected
            doc = {
                "id": str(uuid.uuid4()),
                "organization_id": target_org,
                "user_id": user["id"],
                "name": name,
                "equipment_type": _normalize(row, "equipment_type", "Type", "Equipment Type") or str(get_pick(row, "equipment_type", "")).strip(),
                "manufacturer": _normalize(row, "manufacturer", "Manufacturer") or str(get_pick(row, "manufacturer", "")).strip(),
                "model": _normalize(row, "model", "Model") or str(get_pick(row, "model", "")).strip(),
                "serial_number": serial,
                "purchase_date": purchase_date_iso or None,
                "warranty_expiry": warranty_iso or None,
                "sla_start": contract_start_iso or None,
                "sla_expiry": contract_end_iso or None,
                "contract_number": str(get_pick(row, "contract_number", "")).strip() or None,
                "contract_type": _normalize_contract_type(
                    _normalize(row, "contract_type", "Contract Type", "Contract type")
                    or str(get_pick(row, "contract_type", "")).strip()
                ),
                "contract_start_date": contract_start_iso or None,
                "contract_end_date": contract_end_iso or None,
                "service_provider": _normalize(row, "service_provider", "Service Provider") or str(get_pick(row, "service_provider", "")).strip(),
                # Iter 216h51 — supplier resolved against suppliers col.
                # Store the canonical supplier name on the equipment doc
                # AND the supplier_id / supplier_email for fault routing.
                "supplier": (supplier_match or {}).get("name") or supplier_input,
                "supplier_id": (supplier_match or {}).get("id"),
                "purchased_from": purchased_from,
                "supplier_email": (
                    (supplier_match or {}).get("service_email")
                    or (supplier_match or {}).get("email")
                ),
                "location": _normalize(row, "location", "Location") or str(get_pick(row, "location", "")).strip(),
                "notes": _normalize(row, "notes", "Notes") or str(get_pick(row, "notes", "")).strip(),
                # Sicon/Sage round-trip refs (optional) — enable ongoing two-way sync.
                "sicon_equipment_id": _parse_int(_normalize(row, "sicon_equipment_id", "Sicon Equipment ID", "SiconEquipmentID") or str(get_pick(row, "sicon_equipment_id", "")).strip()),
                "sage_item_id": _parse_int(_normalize(row, "sage_item_id", "Sage Item ID", "ItemID") or str(get_pick(row, "sage_item_id", "")).strip()),
                "length": _parse_decimal(_normalize(row, "length", "Length") or str(get_pick(row, "length", "")).strip()),
                "width": _parse_decimal(_normalize(row, "width", "Width") or str(get_pick(row, "width", "")).strip()),
                "height": _parse_decimal(_normalize(row, "height", "Height") or str(get_pick(row, "height", "")).strip()),
                # Iter 216h50 — unit_price stored on both purchase_price
                # (ledger) and purchase_cost (canonical). replacement_cost
                # uses the dedicated column when supplied, else falls back
                # to the purchase price; Capex uses the equipment-type
                # profile when both are blank, so leaving them blank is safe.
                "purchase_price": unit_price,
                "purchase_cost": unit_price,
                "replacement_cost": replacement_cost or unit_price,
                "site_id": site_id,
                "status": "active",
                "manuals": [],
                "photos": [],
                "created_at": now_iso,
                "updated_at": now_iso,
                "imported_via": "bulk_csv",
                # Iter 216h111 — MOD Force tag (army/raf/navy or "")
                "mod_force": row_force or None,
                # MOD equipment onboarding — additional asset-register fields
                # (Iter — MOD onboarding). All optional; stored as None when
                # blank so commercial imports are unaffected.
                "asset_number": _normalize(row, "asset_number", "Asset Number", "nsn", "NSN", "asset_id", "Asset ID") or str(get_pick(row, "asset_number", "")).strip() or None,
                "sub_location": _normalize(row, "sub_location", "Sub Location", "room", "Room", "zone", "Zone") or str(get_pick(row, "sub_location", "")).strip() or None,
                "category": _normalize(row, "category", "Category") or str(get_pick(row, "category", "")).strip() or None,
                "mod_code": _normalize(row, "mod_code", "MOD Code", "MOD-Code") or str(get_pick(row, "mod_code", "")).strip() or None,
                "classification": _normalize(row, "classification", "Classification") or str(get_pick(row, "classification", "")).strip() or None,
                "qr_code": _normalize(row, "qr_code", "QR Code") or str(get_pick(row, "qr_code", "")).strip() or None,
                "manufacturing_date": parse_date_cell(get_pick(row, "manufacturing_date") or row.get("Manufacturing Date") or row.get("manufacturing_date")) or None,
                "condition": _normalize(row, "condition", "Condition") or str(get_pick(row, "condition", "")).strip() or None,
                "quantity": _parse_int(_normalize(row, "quantity", "Quantity", "qty", "Qty") or str(get_pick(row, "quantity", "")).strip()),
                "import_batch_id": batch_id,
            }
            # ── Dedupe + idempotent enrich (Iter — sites-first re-import) ──
            # Real serial → dedupe by serial. Placeholder serial (UNKNOWN /
            # blank) → dedupe by the site|name|model|manufacturer composite
            # so re-importing the same file ENRICHES gaps instead of
            # inserting duplicates. `replace_existing` keeps its full-
            # overwrite meaning for the MOD "replace" flow.
            match_query = None
            if is_real:
                existing_serials = await _serial_set_for(target_org)
                if serial in existing_serials:
                    match_query = {"organization_id": target_org, "serial_number": serial}
            else:
                comp = _equipment_composite_key(site_id, name, doc["model"], doc["manufacturer"])
                comp_set = await _composite_set_for(target_org)
                if comp in comp_set:
                    match_query = {
                        "organization_id": target_org, "name": name,
                        "model": doc["model"], "manufacturer": doc["manufacturer"],
                        "site_id": site_id,
                    }

            if match_query is not None:
                existing_doc = await db.equipment.find_one(match_query, {"_id": 0})
                if existing_doc is None:
                    # Match was only an as-yet-unflushed row from THIS same
                    # file (intra-file duplicate) — don't insert it twice.
                    skipped += 1
                    dup_of = f"serial '{serial}'" if is_real else "an identical machine"
                    errors.append(f"Row {i}: duplicate within file — {dup_of} already appears earlier; skipped")
                    continue
                if replace_existing:
                    upd = {k: v for k, v in doc.items()
                           if k not in ("id", "created_at", "manuals", "photos", "imported_via", "import_batch_id")}
                else:
                    upd = _build_enrich_update(existing_doc, doc, _EQUIPMENT_ENRICH_FIELDS)
                upd["updated_at"] = now_iso
                await db.equipment.update_one(
                    {"organization_id": target_org, "id": existing_doc["id"]},
                    {"$set": upd},
                )
                updated += 1
                org_breakdown[target_org] = org_breakdown.get(target_org, 0) + 1
                continue

            pending.append(doc)
            # Track this row's dedupe key so an intra-file duplicate is
            # caught. Real serials are unique, so a repeat within the file
            # is a data error → enrich. Placeholder-serial composites are
            # intentionally NOT added: two identical UNKNOWN-serial machines
            # listed in the same file are distinct assets and must both
            # insert; only PRE-EXISTING (already-in-DB) composites enrich.
            if is_real:
                serial_set_cache[target_org].add(serial)
            imported += 1
            org_breakdown[target_org] = org_breakdown.get(target_org, 0) + 1
            if len(pending) >= BATCH_SIZE:
                await _flush_pending()
        except Exception as exc:  # one bad row shouldn't kill the whole import
            errors.append(f"Row {i}: {exc}")

    # Flush the tail.
    await _flush_pending()

    # Audit — record the import against each affected org so it surfaces in
    # Master Admin → Org → Activity (previously imports were untracked).
    if org_breakdown:
        try:
            from routes.master_admin import log_activity
            actor = user.get("email") or user.get("full_name") or "system"
            for oid, cnt in org_breakdown.items():
                if oid and cnt:
                    await log_activity(
                        "equipment_imported",
                        f"Imported/updated {cnt} equipment item(s) via bulk import",
                        actor, "organization", oid,
                    )
        except Exception:
            pass

    # Record the batch so the run can be undone in one click.
    if imported > 0:
        await _record_import_batch(
            batch_id=batch_id, kind="equipment", user=user,
            org_ids=list(org_breakdown.keys()),
            inserted=imported, updated=updated, skipped=skipped,
            filename=getattr(file, "filename", None),
        )
    # Bridge imported customer estates into the Pulse Fitness Ltd CRM.
    await _bridge_import_to_crm(list(org_breakdown.keys()), user)

    return {
        "imported": imported, "skipped": skipped, "updated": updated,
        "errors": errors[:50], "error_count": len(errors),
        "organization_id": default_org,
        "batch_id": batch_id if imported > 0 else None,
        "org_breakdown": org_breakdown,
    }
async def bulk_import_customers(
    file: UploadFile = File(...),
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    _require_pulse_or_master(user)
    default_org = await _resolve_target_org(user, organization_id) if organization_id else None

    contents = await file.read()
    # Iter 216h55 — Pulse-scale CSVs can be ~150 MB. The middleware
    # enforces the upper cap, so we match here.
    validate_upload(file_bytes=contents, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=200 * 1024 * 1024)
    text = contents.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    imported, skipped, errors = 0, 0, []
    org_cache: dict = {}
    # Iter 216h55 — pre-loaded email set per target org, refilled lazily.
    email_set_cache: dict = {}
    org_breakdown: dict = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    # CRM v2 mirror — imported people also become crm2_contacts under the
    # operator tenant, linked to the customer's crm2_companies record.
    operator_org = await _resolve_operator_org(user)
    crm_company_by_org: dict = {}
    crm2_seen_emails = {
        (d.get("email") or "").lower()
        async for d in db.crm2_contacts.find(
            {"organization_id": operator_org, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1},
        ) if d.get("email")
    }
    pending_crm2: list = []

    async def _company_id_for(target_org: str) -> Optional[str]:
        if target_org in crm_company_by_org:
            return crm_company_by_org[target_org]
        cid = await _ensure_crm_company_for_org(operator_org, target_org, user)
        crm_company_by_org[target_org] = cid
        return cid

    BATCH_SIZE = 500
    pending: list = []

    async def _flush_pending():
        if pending:
            try:
                await db.crm_contacts.insert_many(pending, ordered=False)
            except Exception as exc:
                logger.warning(f"customers insert_many failed, falling back row-by-row: {exc}")
                for d in pending:
                    try:
                        await db.crm_contacts.insert_one(d)
                    except Exception as e2:
                        errors.append(f"DB insert failed for row id {d.get('id')}: {e2}")
            pending.clear()
        if pending_crm2:
            try:
                await db.crm2_contacts.insert_many(pending_crm2, ordered=False)
            except Exception as exc:
                logger.warning(f"crm2 contacts insert_many failed, falling back: {exc}")
                for d in pending_crm2:
                    try:
                        await db.crm2_contacts.insert_one(d)
                    except Exception:
                        pass
            pending_crm2.clear()

    async def _email_set_for(target_org: str) -> set:
        if target_org in email_set_cache:
            return email_set_cache[target_org]
        cursor = db.crm_contacts.find(
            {"organization_id": target_org, "email": {"$exists": True, "$ne": ""}},
            {"_id": 0, "email": 1},
        )
        s = {(doc.get("email") or "").lower() async for doc in cursor if doc.get("email")}
        email_set_cache[target_org] = s
        return s

    for i, row in enumerate(reader, start=2):
        try:
            # Iter 216h56 — skip blank trailing rows from Excel/Sheets exports.
            if _is_blank_row(row):
                continue
            target_org, route_err = await _resolve_row_target_org(row, default_org, org_cache)
            if not target_org:
                skipped += 1
                if route_err:
                    errors.append(f"Row {i}: {route_err}")
                continue
            email = _normalize(row, "email", "Email").lower()
            first_name = _normalize(row, "first_name", "First Name", "FirstName")
            last_name = _normalize(row, "last_name", "Last Name", "LastName")
            if not (email or first_name or last_name):
                skipped += 1
                errors.append(f"Row {i}: missing email, first_name and last_name — at least one is required")
                continue
            if email:
                existing_emails = await _email_set_for(target_org)
                if email in existing_emails:
                    skipped += 1
                    errors.append(f"Row {i}: duplicate — contact with email '{email}' already exists in this org")
                    continue
            doc = {
                "id": str(uuid.uuid4()),
                "organization_id": target_org,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": _normalize(row, "phone", "Phone"),
                "company_name": _normalize(row, "company", "Company", "company_name"),
                "title": _normalize(row, "title", "Title", "job_title"),
                "tags": [t.strip() for t in _normalize(row, "tags", "Tags").split(",") if t.strip()],
                "linkedin_url": _normalize(row, "linkedin", "LinkedIn"),
                "address": _normalize(row, "address", "Address"),
                "source": "csv_import",
                "is_customer": True,
                "lead_score": 0,
                "owner_id": user["id"],
                "company_id": None,
                "notes": "",
                "created_by": user["id"],
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            pending.append(doc)
            if email:
                email_set_cache[target_org].add(email)
            # Mirror the person into the operator's CRM (crm2_contacts),
            # linked to the customer company. Skip if importing into the
            # operator's own tenant, or a same-email contact already exists.
            if target_org != operator_org:
                cid = await _company_id_for(target_org)
                if not email or email not in crm2_seen_emails:
                    pending_crm2.append(_crm2_contact_doc(
                        operator_org, cid, doc.get("company_name", ""),
                        {"first_name": first_name, "last_name": last_name, "email": email,
                         "phone": doc.get("phone", ""), "title": doc.get("title", ""),
                         "linkedin_url": doc.get("linkedin_url", ""),
                         "company_name": doc.get("company_name", "")},
                        user,
                    ))
                    if email:
                        crm2_seen_emails.add(email)
            imported += 1
            org_breakdown[target_org] = org_breakdown.get(target_org, 0) + 1
            if len(pending) >= BATCH_SIZE:
                await _flush_pending()
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")

    await _flush_pending()

    # Bridge imported customer estates into the Pulse Fitness Ltd CRM.
    await _bridge_import_to_crm(list(org_breakdown.keys()), user)

    return {
        "imported": imported, "skipped": skipped,
        "errors": errors[:50], "error_count": len(errors),
        "organization_id": default_org,
        "org_breakdown": org_breakdown,
    }


# ── Contracts bulk import ────────────────────────────────────────────────

def _parse_bool(s: str) -> bool:
    return str(s or "").strip().lower() in ("1", "true", "yes", "y", "on")


@router.post("/master-admin/bulk-import/contracts")
async def bulk_import_contracts(
    file: UploadFile = File(...),
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    """Bulk-load a customer's existing service contracts into CRM
    (`crm2_contracts`). Idempotent on `contract_number` per org, batched
    for scale. Captures `sicon_contract_id` for the ongoing two-way sync."""
    _require_pulse_or_master(user)
    default_org = await _resolve_target_org(user, organization_id) if organization_id else None

    contents = await file.read()
    validate_upload(file_bytes=contents, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=200 * 1024 * 1024)
    from utils.spreadsheet_import import iter_rows, parse_date_cell, get_pick
    rows_iter = iter_rows(contents, file.filename)

    imported, skipped, errors = 0, 0, []
    org_cache: dict = {}
    company_cache: dict = {}       # (org, lower(name)) -> company doc
    number_set_cache: dict = {}    # org -> set(contract_number)
    org_breakdown: dict = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    BATCH_SIZE = 500
    pending: list = []

    async def _flush_pending():
        if not pending:
            return
        try:
            await db.crm2_contracts.insert_many(pending, ordered=False)
        except Exception as exc:
            logger.warning(f"contracts insert_many failed, falling back row-by-row: {exc}")
            for d in pending:
                try:
                    await db.crm2_contracts.insert_one(d)
                except Exception as e2:
                    errors.append(f"DB insert failed for row id {d.get('id')}: {e2}")
        pending.clear()

    async def _number_set_for(target_org: str) -> set:
        if target_org in number_set_cache:
            return number_set_cache[target_org]
        cursor = db.crm2_contracts.find(
            {"organization_id": target_org, "contract_number": {"$exists": True, "$ne": ""}},
            {"_id": 0, "contract_number": 1},
        )
        s = {(doc.get("contract_number") or "").lower() async for doc in cursor if doc.get("contract_number")}
        number_set_cache[target_org] = s
        return s

    async def _company_for(target_org: str, name: str) -> Optional[dict]:
        name = (name or "").strip()
        if not name:
            return None
        key = (target_org, name.lower())
        if key in company_cache:
            return company_cache[key]
        from utils.security_plus import safe_regex
        doc = await db.crm2_companies.find_one(
            {"organization_id": target_org, "name": safe_regex(f"^{name}$")}, {"_id": 0, "id": 1, "name": 1},
        )
        company_cache[key] = doc
        return doc

    for i, row in enumerate(rows_iter, start=2):
        try:
            if _is_blank_row(row):
                continue
            target_org, route_err = await _resolve_row_target_org(row, default_org, org_cache)
            if not target_org:
                skipped += 1
                if route_err:
                    errors.append(f"Row {i}: {route_err}")
                continue
            number = (_normalize(row, "contract_number", "Contract Number") or str(get_pick(row, "contract_number", "")).strip())
            title = _normalize(row, "title", "Title", "contract_title") or str(get_pick(row, "title", "")).strip()
            if not number and not title:
                skipped += 1
                errors.append(f"Row {i}: missing required column 'contract_number' (or 'title')")
                continue
            if number:
                existing = await _number_set_for(target_org)
                if number.lower() in existing:
                    skipped += 1
                    errors.append(f"Row {i}: duplicate — contract '{number}' already exists in this org")
                    continue
            company_name = _normalize(row, "company_name", "Company", "company") or str(get_pick(row, "company_name", "")).strip()
            company = await _company_for(target_org, company_name)
            doc = {
                "id": str(uuid.uuid4()),
                "organization_id": target_org,
                "contract_number": number or f"CTR-{str(uuid.uuid4())[:6].upper()}",
                "title": title or number,
                "type": (_normalize(row, "type", "Type") or str(get_pick(row, "type", "")).strip() or "service"),
                "tier": (_normalize(row, "tier", "Tier") or str(get_pick(row, "tier", "")).strip() or "silver").lower(),
                "status": (_normalize(row, "status", "Status") or str(get_pick(row, "status", "")).strip() or "active").lower(),
                "company_id": (company or {}).get("id", ""),
                "company_name": company_name or (company or {}).get("name", ""),
                "contact_id": "", "contact_name": "", "site_id": "",
                "opportunity_id": "", "quote_id": "", "order_id": "", "parent_contract_id": None,
                "start_date": parse_date_cell(get_pick(row, "start_date") or row.get("Start Date") or row.get("start_date")) or "",
                "end_date": parse_date_cell(get_pick(row, "end_date") or row.get("End Date") or row.get("end_date")) or "",
                "renewal_date": parse_date_cell(get_pick(row, "renewal_date") or row.get("Renewal Date") or row.get("renewal_date")) or "",
                "annual_value": _parse_decimal(_normalize(row, "annual_value", "Annual Value") or str(get_pick(row, "annual_value", "")).strip()) or 0.0,
                "total_value": _parse_decimal(_normalize(row, "total_value", "Total Value") or str(get_pick(row, "total_value", "")).strip()) or 0.0,
                "billing_frequency": (_normalize(row, "billing_frequency", "Billing Frequency") or str(get_pick(row, "billing_frequency", "")).strip() or "annual"),
                "auto_renew": _parse_bool(_normalize(row, "auto_renew", "Auto Renew") or str(get_pick(row, "auto_renew", "")).strip()),
                "renewal_notice_days": 90,
                "sla": {
                    "response_hours": _parse_decimal(_normalize(row, "sla_response_hours", "SLA Response Hours") or str(get_pick(row, "sla_response_hours", "")).strip()),
                    "resolution_hours": _parse_decimal(_normalize(row, "sla_resolution_hours", "SLA Resolution Hours") or str(get_pick(row, "sla_resolution_hours", "")).strip()),
                    "parts_included": False, "labour_included": True,
                    "visits_per_year": None, "preventive_maintenance": False,
                },
                "signature": None, "signed_by": None, "signed_at": None,
                "sicon_contract_id": _parse_int(_normalize(row, "sicon_contract_id", "Sicon Contract ID", "SiconContractID") or str(get_pick(row, "sicon_contract_id", "")).strip()),
                "sage_reference": _normalize(row, "sage_reference", "Sage Reference", "SageReference") or str(get_pick(row, "sage_reference", "")).strip() or None,
                "version": 1,
                "created_by": user.get("full_name", ""),
                "owner_id": user.get("id"),
                "owner_name": user.get("full_name", ""),
                "imported_via": "bulk_csv",
                "created_at": now_iso, "updated_at": now_iso,
            }
            pending.append(doc)
            if number:
                number_set_cache[target_org].add(number.lower())
            imported += 1
            org_breakdown[target_org] = org_breakdown.get(target_org, 0) + 1
            if len(pending) >= BATCH_SIZE:
                await _flush_pending()
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")

    await _flush_pending()

    return {
        "imported": imported, "skipped": skipped,
        "errors": errors[:50], "error_count": len(errors),
        "organization_id": default_org,
        "org_breakdown": org_breakdown,
    }


# ── Sites bulk import (Iter 216h53) ──────────────────────────────────────
#
# Lee uploaded a sites CSV via the equipment slot and the upload failed.
# This endpoint matches the same shape as the equipment + customers
# endpoints above so Master Admin → Bulk Imports has a third box for
# sites without forcing operators back into the multi-site wizard.

@router.get("/master-admin/bulk-import/templates/sites")
async def template_sites_passthrough(user: dict = Depends(get_current_user)) -> Response:
    """Returns the same template as /api/master-admin/sites/template.csv.
    Re-exposed under the bulk-import prefix so the AdminBulkImports UI
    can use a single template-download helper for every kind."""
    _require_pulse_or_master(user)
    from routes.sites_import import _SITE_CSV_HEADERS, _SITE_CSV_EXAMPLE_ROWS
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_SITE_CSV_HEADERS)
    for row in _SITE_CSV_EXAMPLE_ROWS:
        writer.writerow(row)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sites_template.csv"},
    )


@router.post("/master-admin/bulk-import/sites")
async def bulk_import_sites(
    organization_id: str = Query(..., description="Target organisation — sites are always org-scoped"),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Import a CSV of sites into a target customer org. Sites MUST be
    scoped to a single org (no `customer_account_number` column on the
    sites template), so the target is required upfront."""
    _require_pulse_or_master(user)
    org = await db.organizations.find_one(
        {"id": organization_id},
        {"_id": 0, "id": 1, "name": 1, "account_type": 1,
         "is_head_office": 1, "is_multi_site": 1, "site_count": 1,
         "customer_account_number": 1, "sicon_customer_number": 1},
    )
    if not org:
        raise HTTPException(status_code=404, detail="Target organisation not found")
    if not _is_pulse_visible_account_type(org.get("account_type")):
        raise HTTPException(status_code=403, detail="Org is not Pulse-visible")

    # Snapshot the org fields this import may stamp, so an Undo restores them.
    batch_id = str(uuid.uuid4())
    org_snapshot = {
        "is_head_office": org.get("is_head_office", False),
        "is_multi_site": org.get("is_multi_site", False),
        "site_count": org.get("site_count", 0),
        "customer_account_number": org.get("customer_account_number", ""),
        "sicon_customer_number": org.get("sicon_customer_number", ""),
    }

    blob = await file.read()
    # Iter 216h55 — match the new 200 MB platform-wide bulk-import cap.
    validate_upload(file_bytes=blob, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=200 * 1024 * 1024)
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = blob.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))

    imported, updated, skipped, errors = 0, 0, 0, []
    head_office_set = await db.sites.count_documents(
        {"organization_id": organization_id, "is_head_office": True},
    ) > 0
    now_iso = datetime.now(timezone.utc).isoformat()

    # Pre-load existing sites (id + enrichable fields) so a re-import of the
    # same estate ENRICHES gaps in place instead of skipping or duplicating.
    _site_enrich_fields = (
        "address", "address_line1", "address_line2", "address_line3",
        "city", "county", "postcode", "country", "phone", "email",
        "site_manager_name", "site_manager_email", "invoice_customer_ref",
        "default_location",
    )
    existing_by_name: dict = {}
    _pre_cursor = db.sites.find(
        {"organization_id": organization_id},
        {"_id": 0, "id": 1, "name": 1, "created_at": 1, **{f: 1 for f in _site_enrich_fields}},
    )
    async for d in _pre_cursor:
        key = (d.get("name") or "").lower().strip()
        if key and key not in existing_by_name:
            existing_by_name[key] = d

    first_site_id: Optional[str] = None      # first site touched this run (HQ fallback)
    account_ref: str = ""                    # first invoice_customer_ref seen (org stamp)
    site_contacts: list = []                 # site managers → CRM contacts

    BATCH_SIZE = 500
    pending: list = []

    async def _flush_pending():
        if not pending:
            return
        try:
            await db.sites.insert_many([d.copy() for d in pending], ordered=False)
        except Exception as exc:
            logger.warning(f"sites insert_many failed, falling back row-by-row: {exc}")
            for d in pending:
                try:
                    await db.sites.insert_one(d.copy())
                except Exception as e2:
                    errors.append(f"DB insert failed for row id {d.get('id')}: {e2}")
        pending.clear()

    for i, row in enumerate(reader, start=2):
        try:
            # Iter 216h56 — skip blank trailing rows from Excel/Sheets exports.
            if _is_blank_row(row):
                continue
            name = _normalize(row, "site_name", "name", "Site Name", "Name")
            if not name:
                skipped += 1
                errors.append(f"Row {i}: missing site_name")
                continue

            ref = _normalize(
                row, "invoice_customer_ref", "Invoice Customer Ref",
                "sicon_customer_ref", "customer_ref",
            )
            if ref and not account_ref:
                account_ref = ref

            new_vals = {
                "address": _normalize(row, "address_line1", "address", "Address"),
                "address_line1": _normalize(row, "address_line1", "address"),
                "address_line2": _normalize(row, "address_line2"),
                "address_line3": _normalize(row, "address_line3"),
                "city": _normalize(row, "city", "City"),
                "county": _normalize(row, "county", "County"),
                "postcode": _normalize(row, "postcode", "Postcode", "post_code"),
                "country": _normalize(row, "country", "Country") or "United Kingdom",
                "phone": _normalize(row, "phone", "Phone"),
                "email": _normalize(row, "email", "Email"),
                "site_manager_name": _normalize(row, "site_manager_name", "Site Manager"),
                "site_manager_email": _normalize(row, "site_manager_email"),
                "invoice_customer_ref": ref,
                "default_location": _normalize(row, "default_location") or "Main Floor",
            }

            key = name.lower().strip()
            existing = existing_by_name.get(key)
            _mgr_name = (new_vals.get("site_manager_name") or "").strip()
            _mgr_email = (new_vals.get("site_manager_email") or "").strip()
            if existing:
                # Re-import — fill only the empty fields, never overwrite.
                upd = _fill_if_empty(existing, new_vals)
                if upd:
                    upd["updated_at"] = now_iso
                    await db.sites.update_one(
                        {"organization_id": organization_id, "id": existing["id"]},
                        {"$set": upd},
                    )
                    existing.update(upd)
                updated += 1
                if first_site_id is None:
                    first_site_id = existing["id"]
                if _mgr_name or _mgr_email:
                    site_contacts.append({"site_id": existing["id"], "site_name": name,
                                          "name": _mgr_name, "email": _mgr_email, "phone": new_vals.get("phone", "")})
                continue

            is_hq_raw = _normalize(row, "is_head_office", "Is Head Office", "head_office")
            is_hq = is_hq_raw.lower() in {"yes", "true", "1", "y", "head office", "hq"}
            if is_hq and not head_office_set:
                head_office_set = True
            elif is_hq:
                is_hq = False  # Already an HQ on this org — downgrade.

            site_id = str(uuid.uuid4())
            doc = {
                "id": site_id,
                "organization_id": organization_id,
                "name": name,
                **new_vals,
                "is_head_office": is_hq,
                "import_batch_id": batch_id,
                "created_at": now_iso,
            }
            pending.append(doc)
            existing_by_name[key] = {"id": site_id, "name": name, **new_vals}
            if first_site_id is None:
                first_site_id = site_id
            if _mgr_name or _mgr_email:
                site_contacts.append({"site_id": site_id, "site_name": name,
                                      "name": _mgr_name, "email": _mgr_email, "phone": new_vals.get("phone", "")})
            imported += 1
            if len(pending) >= BATCH_SIZE:
                await _flush_pending()
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")

    await _flush_pending()

    # ── Post-import: stamp the org as a multi-site Head Office customer ──
    # so it surfaces under the "Head Offices" filter / badge, and link the
    # Sicon account number (which the CSV puts on the sites) onto the org
    # so equipment auto-route by account number resolves it.
    total_sites = await db.sites.count_documents({"organization_id": organization_id})
    org_updates: dict = {
        "is_head_office": True,
        "is_multi_site": total_sites > 1,
        "site_count": total_sites,
        "updated_at": now_iso,
    }
    if account_ref:
        fresh_org = await db.organizations.find_one(
            {"id": organization_id},
            {"_id": 0, "customer_account_number": 1, "sicon_customer_number": 1},
        ) or {}
        if not (fresh_org.get("customer_account_number") or "").strip():
            org_updates["customer_account_number"] = account_ref
        if not (fresh_org.get("sicon_customer_number") or "").strip():
            org_updates["sicon_customer_number"] = account_ref
    await db.organizations.update_one({"id": organization_id}, {"$set": org_updates})

    # Ensure a physical Head-Office SITE exists. Respect a pre-set HQ (either
    # an existing HQ site or one flagged in this CSV). Otherwise auto-designate
    # the first site so equipment/QRs have a corporate HQ to hang off.
    hq_exists = await db.sites.count_documents(
        {"organization_id": organization_id, "is_head_office": True},
    ) > 0
    head_office_site_id = None
    if not hq_exists:
        promote_id = first_site_id
        if not promote_id:
            earliest = await db.sites.find_one(
                {"organization_id": organization_id},
                {"_id": 0, "id": 1}, sort=[("created_at", 1)],
            )
            promote_id = (earliest or {}).get("id")
        if promote_id:
            await db.sites.update_one(
                {"organization_id": organization_id, "id": promote_id},
                {"$set": {"is_head_office": True, "updated_at": now_iso}},
            )
            head_office_site_id = promote_id
    else:
        hq = await db.sites.find_one(
            {"organization_id": organization_id, "is_head_office": True},
            {"_id": 0, "id": 1},
        )
        head_office_site_id = (hq or {}).get("id")

    if imported > 0:
        await _record_import_batch(
            batch_id=batch_id, kind="sites", user=user,
            org_ids=[organization_id],
            inserted=imported, updated=updated, skipped=skipped,
            filename=getattr(file, "filename", None),
            org_snapshots={organization_id: org_snapshot},
        )
    # Bridge this customer estate into the Pulse Fitness Ltd CRM.
    await _bridge_import_to_crm([organization_id], user)
    # Pull each site's manager into the CRM as a contact at that site.
    operator = await _resolve_operator_org(user)
    if site_contacts and operator and operator != organization_id:
        company_id = await _ensure_crm_company_for_org(operator, organization_id, user)
        cust = await db.organizations.find_one({"id": organization_id}, {"_id": 0, "name": 1}) or {}
        try:
            await _mirror_site_managers_to_crm(operator, company_id, cust.get("name", ""), site_contacts, user)
        except Exception as exc:
            logger.warning(f"site-manager CRM mirror failed for org {organization_id}: {exc}")

    return {
        "imported": imported, "updated": updated, "skipped": skipped,
        "errors": errors[:50], "error_count": len(errors),
        "organization_id": organization_id,
        "site_count": total_sites,
        "head_office_site_id": head_office_site_id,
        "customer_account_number": org_updates.get("customer_account_number") or account_ref or None,
        "batch_id": batch_id if imported > 0 else None,
        "org_breakdown": {organization_id: imported} if imported else {},
    }


__all__ = ["router"]
