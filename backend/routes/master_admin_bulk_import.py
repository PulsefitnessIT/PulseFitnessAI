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
_EQUIPMENT_HEADERS = [
    "site_name",
    "customer_account_number",
    "name", "equipment_type", "manufacturer", "model", "serial_number",
    "purchase_date", "warranty_expiry", "service_provider",
    "unit_price",
    "length", "width", "height", "location", "notes",
]
_EQUIPMENT_EXAMPLE = [
    "Carshalton Sports Centre",
    "PULSENC01",
    "Treadmill — Cardio Bay 3", "Treadmill", "Life Fitness", "T7000", "LFT-2024-04958",
    "2024-01-15", "2027-01-15", "Pulse Fitness Service",
    "3450.00",
    "2.20", "0.95", "1.55", "Cardio Mezzanine", "Brand new — first install",
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


@router.get("/master-admin/bulk-import/templates/customers")
async def template_customers(user: dict = Depends(get_current_user)) -> Response:
    _require_pulse_or_master(user)
    return _csv_response(_CUSTOMER_HEADERS, _CUSTOMER_EXAMPLE, "customers-template.csv")


# ── Importers ────────────────────────────────────────────────────────────


def _parse_decimal(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        return float(s.replace(",", "").strip())
    except ValueError:
        return None


def _normalize(row: dict, *keys: str) -> str:
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            return v
    return ""


async def _resolve_target_org(user: dict, organization_id: Optional[str]) -> str:
    """If the admin specified `organization_id`, validate it's a Pulse-visible
    customer. Otherwise default to the admin's own organization (only valid
    for the GymAxis Master Admin who isn't tenant-scoped — Pulse admins must
    pick a target)."""
    if organization_id:
        org = await db.organizations.find_one(
            {"id": organization_id, "account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES}},
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
    """
    code = (account_number or "").strip()
    if not code:
        return None
    org = await db.organizations.find_one(
        {
            "account_type": {"$in": PULSE_VISIBLE_ACCOUNT_TYPES},
            "$or": [
                {"customer_account_number": code},
                {"sage_customer_number": code},
                {"sicon_customer_number": code},
            ],
        },
        {"_id": 0, "id": 1},
    )
    return org["id"] if org else None


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
#   2. invoice_customer_ref / sicon_customer_ref equality
#   3. Returns (None, "site not found") so the row is reported, not silently inserted
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
    cache_key = (org_id, site_name.lower(), ref.lower())
    if cache_key in cache:
        cached = cache[cache_key]
        return cached, (None if cached else f"Site '{site_name or ref}' not found in target org")
    query: dict = {"organization_id": org_id}
    if site_name:
        import re as _re
        query["name"] = {"$regex": f"^{_re.escape(site_name)}$", "$options": "i"}
    elif ref:
        query["invoice_customer_ref"] = ref
    site = await db.sites.find_one(query, {"_id": 0, "id": 1})
    site_id = site["id"] if site else None
    # If name-search failed and a ref was supplied, fall back to ref.
    if not site_id and site_name and ref:
        site = await db.sites.find_one(
            {"organization_id": org_id, "invoice_customer_ref": ref},
            {"_id": 0, "id": 1},
        )
        site_id = site["id"] if site else None
    cache[cache_key] = site_id
    return site_id, (None if site_id else f"Site '{site_name or ref}' not found in target org — import the sites first")


@router.post("/master-admin/bulk-import/equipment")
async def bulk_import_equipment(
    file: UploadFile = File(...),
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    _require_pulse_or_master(user)
    # Validate the optional default if supplied; per-row resolver kicks in when None.
    default_org = await _resolve_target_org(user, organization_id) if organization_id else None

    contents = await file.read()
    validate_upload(file_bytes=contents, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=10 * 1024 * 1024)
    text = contents.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    imported, skipped, errors = 0, 0, []
    org_cache: dict = {}
    site_cache: dict = {}
    org_breakdown: dict = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for i, row in enumerate(reader, start=2):  # +1 header, +1 1-indexed
        try:
            target_org, route_err = await _resolve_row_target_org(row, default_org, org_cache)
            if not target_org:
                skipped += 1
                if route_err:
                    errors.append(f"Row {i}: {route_err}")
                continue
            name = _normalize(row, "name", "Name")
            if not name:
                skipped += 1
                continue
            serial = _normalize(row, "serial_number", "Serial Number", "serial")
            if serial:
                exists = await db.equipment.find_one(
                    {"organization_id": target_org, "serial_number": serial}, {"_id": 0, "id": 1},
                )
                if exists:
                    skipped += 1
                    continue
            # Iter 216h50 — link to a pre-imported site by name (or by
            # Sicon "Invoice Customer Ref" fallback). Sites import runs
            # first during onboarding so by the time equipment lands the
            # site rows already exist.
            site_name = _normalize(row, "site_name", "Site Name", "site")
            invoice_customer_ref = _normalize(
                row, "invoice_customer_ref", "Invoice Customer Ref",
                "sicon_customer_ref", "customer_ref",
            )
            site_id, site_err = await _resolve_site_for_org(site_name, invoice_customer_ref, target_org, site_cache)
            if (site_name or invoice_customer_ref) and not site_id:
                # The operator explicitly named a site that doesn't exist — surface
                # so they can re-run the sites import first.
                skipped += 1
                if site_err:
                    errors.append(f"Row {i}: {site_err}")
                continue
            unit_price = _parse_decimal(_normalize(row, "unit_price", "Unit Price", "price", "Price"))
            doc = {
                "id": str(uuid.uuid4()),
                "organization_id": target_org,
                "user_id": user["id"],
                "name": name,
                "equipment_type": _normalize(row, "equipment_type", "Type", "Equipment Type"),
                "manufacturer": _normalize(row, "manufacturer", "Manufacturer"),
                "model": _normalize(row, "model", "Model"),
                "serial_number": serial,
                "purchase_date": _normalize(row, "purchase_date", "Purchase Date") or None,
                "warranty_expiry": _normalize(row, "warranty_expiry", "Warranty Expiry") or None,
                "service_provider": _normalize(row, "service_provider", "Service Provider"),
                "supplier": _normalize(row, "supplier", "Supplier") or _normalize(row, "manufacturer"),
                "location": _normalize(row, "location", "Location"),
                "notes": _normalize(row, "notes", "Notes"),
                "length": _parse_decimal(_normalize(row, "length", "Length")),
                "width": _parse_decimal(_normalize(row, "width", "Width")),
                "height": _parse_decimal(_normalize(row, "height", "Height")),
                # Iter 216h50 — unit_price stored on both purchase_price
                # (ledger) and replacement_cost (capex feeder). Capex
                # falls back to the equipment-type profile when this is
                # None, so leaving the column blank is safe.
                "purchase_price": unit_price,
                "replacement_cost": unit_price,
                "site_id": site_id,
                "status": "active",
                "manuals": [],
                "photos": [],
                "created_at": now_iso,
                "updated_at": now_iso,
                "imported_via": "bulk_csv",
            }
            await db.equipment.insert_one(doc)
            imported += 1
            org_breakdown[target_org] = org_breakdown.get(target_org, 0) + 1
        except Exception as exc:  # one bad row shouldn't kill the whole import
            errors.append(f"Row {i}: {exc}")
    return {
        "imported": imported, "skipped": skipped, "errors": errors[:10],
        "organization_id": default_org,
        "org_breakdown": org_breakdown,
    }


@router.post("/master-admin/bulk-import/customers")
async def bulk_import_customers(
    file: UploadFile = File(...),
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    _require_pulse_or_master(user)
    default_org = await _resolve_target_org(user, organization_id) if organization_id else None

    contents = await file.read()
    validate_upload(file_bytes=contents, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=10 * 1024 * 1024)
    text = contents.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    imported, skipped, errors = 0, 0, []
    org_cache: dict = {}
    org_breakdown: dict = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for i, row in enumerate(reader, start=2):
        try:
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
                continue
            if email:
                exists = await db.crm_contacts.find_one(
                    {"email": email, "organization_id": target_org}, {"_id": 0, "id": 1},
                )
                if exists:
                    skipped += 1
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
            await db.crm_contacts.insert_one(doc)
            imported += 1
            org_breakdown[target_org] = org_breakdown.get(target_org, 0) + 1
        except Exception as exc:
            errors.append(f"Row {i}: {exc}")
    return {
        "imported": imported, "skipped": skipped, "errors": errors[:10],
        "organization_id": default_org,
        "org_breakdown": org_breakdown,
    }


__all__ = ["router"]
