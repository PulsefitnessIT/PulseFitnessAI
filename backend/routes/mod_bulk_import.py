"""MOD bulk-import pipeline (Iter 216h117) — provision many MOD sites in
one CSV upload.

Use case: a new MOD Head Office signs the contract and needs us to spin
up 1,000+ child gyms (one per garrison / station / barracks) along with
their shared kiosk logins. Doing this through the single-site UI would
take an analyst a week. This endpoint does it in seconds and returns a
CSV with the generated credentials for distribution.

Endpoints
─────────
  GET  /api/master-admin/mod/bulk-import/template
        → Download the canonical CSV header set + 2 example rows.

  POST /api/master-admin/mod/bulk-import?parent_org_id=...&notify=true
        → Multipart CSV upload. Returns a JSON summary AND can email each
          row's credentials to its `primary_contact_email` when
          `notify=true`.

  GET  /api/master-admin/mod/bulk-import/export-credentials?import_id=...
        → Download the credentials CSV from a previous run (passwords are
          stored hashed by then, so this only works in the 10 minutes
          immediately after the import while the plaintext cache lives
          in `mod_bulk_imports.rows`).

Required CSV columns (case-insensitive):
  site_name             — display name (e.g. "Vimy Lines Gym")
  mod_branch            — branch grouping (e.g. "Catterick Garrison")
                          REQUIRED only when parent is a mod_org;
                          ignored when parent is a mod_branch.
  mod_force             — army | raf | navy (case-insensitive aliases
                          accepted: "British Army", "Royal Air Force",
                          "Royal Navy"). Optional — inherited from parent
                          if blank.
  postcode              — Royal Mail postcode for the gym.
  primary_contact_email — emails the credentials to this address if
                          `notify=true`.
  address               — free-text full address line.

Optional columns:
  site_code             — slug used as the username prefix. Generated
                          from `site_name` when blank.
  primary_contact_name  — used in the credential email.

Authorisation
─────────────
Master admin ONLY. Creating organisations is platform-critical and the
HQ tier could otherwise spin up sites outside their scope.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from passlib.context import CryptContext

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email
from utils.mod_password_rotation import mint_site_password

logger = logging.getLogger(__name__)
router = APIRouter()

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


_CANONICAL_HEADERS = [
    "site_name",
    "mod_branch",
    "mod_force",
    "country",
    "region",
    "service_supplier",
    "postcode",
    "primary_contact_email",
    "address",
    "site_code",
    "primary_contact_name",
]

_EXAMPLE_ROWS = [
    [
        "Vimy Lines Gym", "Catterick Garrison", "army",
        "United Kingdom", "North Yorkshire", "",
        "DL9 3PS", "vimy.lead@army.mod.local",
        "Vimy Lines, Catterick Garrison, North Yorkshire DL9 3PS",
        "vimy-lines", "Sgt. Daniel Hayes",
    ],
    [
        "RAF Akrotiri Gym", "Cyprus", "raf",
        "Cyprus", "Akrotiri", "Cyprus Fitness Services Ltd",
        "", "akrotiri.lead@raf.mod.local",
        "RAF Akrotiri, Western Sovereign Base Area, Cyprus",
        "raf-akrotiri", "Cpl. Jane Reed",
    ],
]

# Countries treated as "UK" — everything else is an overseas base that
# needs an external service supplier (Pulse still notified of faults).
_UK_NAMES = {"united kingdom", "uk", "gb", "great britain", "england",
             "scotland", "wales", "northern ireland"}


def _is_overseas(country: str) -> bool:
    return (country or "").strip().lower() not in _UK_NAMES

_FORCE_ALIASES = {
    "army": "army", "british army": "army",
    "raf": "raf", "royal air force": "raf",
    "navy": "navy", "royal navy": "navy",
}


def _normalise_force(value: str) -> Optional[str]:
    if not value:
        return None
    return _FORCE_ALIASES.get(value.strip().lower())


def _slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or f"mod-site-{uuid.uuid4().hex[:6]}"


def _csv_response(headers: list[str], rows: list[list[str]], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/master-admin/mod/bulk-import/template")
async def mod_bulk_import_template(user: dict = Depends(get_current_user)) -> Response:
    """Download the canonical MOD bulk-import CSV template."""
    require_master_admin(user)
    return _csv_response(_CANONICAL_HEADERS, _EXAMPLE_ROWS, "mod_sites_template.csv")


@router.post("/master-admin/mod/bulk-import")
async def mod_bulk_import(
    file: UploadFile = File(...),
    parent_org_id: str = Query(..., description="MOD parent org — `mod_org` or `mod_branch`"),
    notify: bool = Query(False, description="Email credentials to each row's primary_contact_email"),
    user: dict = Depends(get_current_user),
) -> dict:
    """Provision N MOD sites under a parent HQ / branch in one CSV upload.

    Returns a JSON payload with per-row credentials. Plaintext passwords
    are persisted in `mod_bulk_imports.rows` for 10 minutes (NOT the
    canonical store — bcrypt hashes remain in `users.password`).
    """
    require_master_admin(user)
    parent = await db.organizations.find_one(
        {"id": parent_org_id},
        {"_id": 0, "id": 1, "name": 1, "account_type": 1,
         "mod_root_id": 1, "mod_branch": 1, "mod_force": 1, "mod_estate_id": 1},
    )
    if not parent:
        raise HTTPException(404, "Parent organisation not found")
    parent_type = parent.get("account_type")
    if parent_type not in {"mod_org", "mod_branch"}:
        raise HTTPException(400, "Parent must be a MOD HQ (mod_org) or branch (mod_branch)")

    blob = await file.read()
    if not blob:
        raise HTTPException(400, "Empty file")
    if len(blob) > 5 * 1024 * 1024:
        raise HTTPException(413, "CSV too large (5MB max)")
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = blob.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "site_name" not in {(h or "").strip().lower() for h in reader.fieldnames}:
        raise HTTPException(400, "Missing required column: site_name")

    # Map case-insensitive headers → canonical names for row lookup.
    header_map = {(h or "").strip().lower(): h for h in reader.fieldnames}

    def cell(row: dict, key: str) -> str:
        actual = header_map.get(key)
        if not actual:
            return ""
        return (row.get(actual) or "").strip()

    now_iso = datetime.now(timezone.utc).isoformat()
    import_id = str(uuid.uuid4())
    inherited_force = parent.get("mod_force")
    inherited_branch = parent.get("mod_branch") if parent_type == "mod_branch" else None
    mod_root_id = parent.get("mod_root_id") or parent.get("id")
    mod_estate_id = parent.get("mod_estate_id")

    # Preload the estate's external supplier registry (name → doc) so CSV
    # rows can reference an overseas service supplier by name.
    estate_suppliers: dict[str, dict] = {}
    if mod_estate_id:
        async for s in db.mod_estate_suppliers.find(
            {"mod_estate_id": mod_estate_id}, {"_id": 0},
        ):
            estate_suppliers[(s.get("name") or "").strip().lower()] = s

    # Pre-load existing site names under the same root for de-dupe.
    existing_cursor = db.organizations.find(
        {"account_type": "mod_site", "mod_root_id": mod_root_id},
        {"_id": 0, "name": 1},
    )
    existing_names: set[str] = set()
    async for d in existing_cursor:
        if d.get("name"):
            existing_names.add(d["name"].strip().lower())

    # Pre-load existing usernames for collision avoidance.
    used_usernames: set[str] = set()

    created_rows: list[dict] = []
    errors: list[str] = []
    skipped = 0

    for i, raw in enumerate(reader, start=2):
        try:
            site_name = cell(raw, "site_name")
            if not site_name:
                continue  # blank trailing row
            if site_name.strip().lower() in existing_names:
                skipped += 1
                errors.append(f"Row {i}: '{site_name}' already exists — skipped")
                continue

            force = _normalise_force(cell(raw, "mod_force")) or inherited_force
            if not force:
                skipped += 1
                errors.append(f"Row {i}: missing mod_force (Army / RAF / Navy)")
                continue

            branch = inherited_branch or cell(raw, "mod_branch").strip()
            if parent_type == "mod_org" and not branch:
                skipped += 1
                errors.append(f"Row {i}: missing mod_branch (required when importing under a mod_org)")
                continue

            site_code = cell(raw, "site_code") or _slugify(site_name)
            postcode = cell(raw, "postcode")
            address = cell(raw, "address")
            contact_email = cell(raw, "primary_contact_email")
            contact_name = cell(raw, "primary_contact_name")
            country = cell(raw, "country") or "United Kingdom"
            region = cell(raw, "region")
            overseas = _is_overseas(country)
            supplier_name_in = cell(raw, "service_supplier")

            # Resolve the external supplier for overseas sites against the
            # estate registry. UK sites are Pulse-serviced (no supplier).
            site_supplier_id = None
            site_supplier_name = None
            if overseas:
                if supplier_name_in:
                    est_sup = estate_suppliers.get(supplier_name_in.strip().lower())
                    if est_sup:
                        site_supplier_name = est_sup["name"]
                    else:
                        errors.append(
                            f"Row {i}: overseas supplier '{supplier_name_in}' not found in the "
                            f"estate registry — site created without a supplier assigned"
                        )
                else:
                    errors.append(
                        f"Row {i}: overseas site '{site_name}' has no service_supplier — "
                        f"created but no supplier assigned (Pulse still notified of faults)"
                    )
            serviced_by = "external_supplier" if overseas else "pulse_fitness"

            # ── Create the mod_site org ──
            site_id = str(uuid.uuid4())
            if overseas and site_supplier_name:
                # Instantiate the supplier into the site's own directory so the
                # existing MOD fault routing (_resolve_equipment_supplier) resolves it.
                est_sup = estate_suppliers.get(supplier_name_in.strip().lower())
                site_supplier_id = str(uuid.uuid4())
                await db.suppliers.insert_one({
                    "id": site_supplier_id,
                    "organization_id": site_id,
                    "name": est_sup["name"],
                    "contact_name": est_sup.get("contact_name", ""),
                    "email": est_sup.get("email", ""),
                    "phone": est_sup.get("phone", ""),
                    "manufacturer_keywords": est_sup.get("manufacturer_keywords", []),
                    "notes": est_sup.get("notes", ""),
                    "estate_supplier_id": est_sup.get("id"),
                    "created_at": now_iso,
                })
            await db.organizations.insert_one({
                "id": site_id, "name": site_name,
                "account_type": "mod_site",
                "subscription_tier": "mod_site",
                "portal_type": "service_portal",
                "enabled_modules": ["service_portal"],
                "status": "active", "created_at": now_iso,
                "is_mod": True, "mod_force": force,
                "mod_root_id": mod_root_id, "mod_branch": branch or None,
                "mod_estate_id": mod_estate_id,
                "site_code": site_code,
                "company_code": site_code.upper(),
                "country": country,
                "region": region or None,
                "is_overseas": overseas,
                "serviced_by": serviced_by,
                "service_supplier": site_supplier_name,
                "service_supplier_id": site_supplier_id,
                "postcode": postcode or None,
                "address": address or None,
                "primary_contact_email": contact_email or None,
                "primary_contact_name": contact_name or None,
                "created_via": "mod_bulk_import",
                "bulk_import_id": import_id,
            })
            existing_names.add(site_name.strip().lower())

            # ── Mint shared site login ──
            base_username = _slugify(site_code)
            username = base_username
            # Collision check across DB + this batch.
            attempt = 0
            while (
                username in used_usernames
                or await db.users.find_one({"username": username}, {"_id": 0, "id": 1})
            ):
                attempt += 1
                username = f"{base_username}-{uuid.uuid4().hex[:4]}"
                if attempt > 5:
                    break
            used_usernames.add(username)

            password = mint_site_password(username)
            placeholder_email = f"{username}@mod.site.local"
            if await db.users.find_one({"email": placeholder_email}, {"_id": 0, "id": 1}):
                placeholder_email = f"{username}+{uuid.uuid4().hex[:6]}@mod.site.local"
            await db.users.insert_one({
                "id": str(uuid.uuid4()),
                "username": username,
                "email": placeholder_email,
                "password": pwd_ctx.hash(password),
                "full_name": site_name,
                "role": "owner",
                "account_type": "mod_site",
                "organization_id": site_id,
                "is_site_account": True,
                "is_mod_user": True,
                "mod_force": force,
                "password_updated_at": now_iso,
                "created_at": now_iso,
                "created_by": user.get("id"),
                "created_via": "mod_bulk_import",
                "bulk_import_id": import_id,
            })

            row_record = {
                "site_id": site_id,
                "site_name": site_name,
                "site_code": site_code,
                "username": username,
                "password": password,
                "branch": branch or None,
                "force": force,
                "country": country,
                "region": region or None,
                "serviced_by": serviced_by,
                "service_supplier": site_supplier_name,
                "contact_email": contact_email or None,
                "contact_name": contact_name or None,
                "postcode": postcode or None,
                "notified": False,
            }

            # ── Optional credential email ──
            if notify and contact_email:
                try:
                    html = _credentials_email_html(site_name, username, password, contact_name or "Team")
                    subject = f"[MOD site login] {site_name} — your credentials"
                    await send_email(contact_email, subject, html)
                    row_record["notified"] = True
                except Exception as e:  # pragma: no cover
                    logger.warning("MOD bulk-import notify email failed for %s: %s", contact_email, e)

            created_rows.append(row_record)
        except Exception as exc:  # pragma: no cover
            errors.append(f"Row {i}: {exc}")
            logger.exception("MOD bulk-import row failed: %s", exc)

    # Persist the import run for credential CSV export (10 min ttl).
    await db.mod_bulk_imports.insert_one({
        "id": import_id,
        "parent_org_id": parent_org_id,
        "parent_org_name": parent.get("name"),
        "imported": len(created_rows),
        "skipped": skipped,
        "error_count": len(errors),
        "errors": errors[:100],
        "rows": created_rows,
        "created_by": user.get("id"),
        "created_at": now_iso,
        # Plaintext passwords expire 10 minutes after the import.
        "credentials_expire_at": (
            datetime.now(timezone.utc).timestamp() + 600
        ),
    })

    return {
        "ok": True,
        "import_id": import_id,
        "parent_org": {"id": parent_org_id, "name": parent.get("name"), "type": parent_type},
        "imported": len(created_rows),
        "skipped": skipped,
        "error_count": len(errors),
        "errors": errors[:50],
        "credentials": [
            {
                "site_name": r["site_name"],
                "site_code": r["site_code"],
                "username": r["username"],
                "password": r["password"],
                "notified": r["notified"],
            }
            for r in created_rows
        ],
        "note": (
            "Plaintext credentials are returned ONCE. Download the CSV "
            "via /master-admin/mod/bulk-import/export-credentials?import_id="
            f"{import_id} within 10 minutes — passwords are bcrypt-hashed "
            "in the canonical store and cannot be recovered after that."
        ),
    }


@router.get("/master-admin/mod/bulk-import/export-credentials")
async def mod_bulk_import_export_credentials(
    import_id: str = Query(...),
    user: dict = Depends(get_current_user),
) -> Response:
    """Return the credentials CSV for a recent import. Plaintext passwords
    are only available within 10 minutes of the import."""
    require_master_admin(user)
    run = await db.mod_bulk_imports.find_one({"id": import_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Import not found")
    expires = run.get("credentials_expire_at") or 0
    if datetime.now(timezone.utc).timestamp() > expires:
        raise HTTPException(410, "Plaintext credentials have expired — rotate per site via the HQ provisioning UI.")
    rows = [
        [r.get("site_name"), r.get("site_code"), r.get("username"),
         r.get("password"), r.get("branch") or "", r.get("force"),
         r.get("country") or "", r.get("region") or "", r.get("serviced_by") or "",
         r.get("service_supplier") or "",
         r.get("contact_email") or "", "yes" if r.get("notified") else "no"]
        for r in run.get("rows", [])
    ]
    return _csv_response(
        ["site_name", "site_code", "username", "password", "branch", "force",
         "country", "region", "serviced_by", "service_supplier",
         "contact_email", "notified"],
        rows,
        f"mod_sites_credentials_{import_id[:8]}.csv",
    )


def _credentials_email_html(site_name: str, username: str, password: str, contact: str) -> str:
    return f"""<div style="font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:0 auto;background:#ffffff;color:#1B1D1D;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
  <div style="background:#1B1D1D;padding:20px 28px;border-bottom:3px solid #19CDFF;">
    <div style="color:#19CDFF;font-size:11px;font-weight:800;letter-spacing:0.25em;text-transform:uppercase;">Pulse Fitness · MOD Service Portal</div>
    <h1 style="color:#fff;margin:8px 0 0 0;font-size:20px;">{site_name}</h1>
  </div>
  <div style="padding:22px 28px;">
    <p>Hello {contact},</p>
    <p>Your MOD Service Portal site login has been provisioned. Use the credentials below to sign in at <a href="/MODService" style="color:#19CDFF;">/MODService</a>.</p>
    <table style="margin-top:14px;border-collapse:collapse;">
      <tr><td style="padding:8px 14px;background:#F5F7F8;border:1px solid #E5E7EB;color:#6E7476;font-size:11px;font-weight:800;text-transform:uppercase;">Username</td>
          <td style="padding:8px 14px;background:#F5F7F8;border:1px solid #E5E7EB;font-weight:700;"><code>{username}</code></td></tr>
      <tr><td style="padding:8px 14px;background:#0A0B10;color:#19CDFF;border:1px solid #0A0B10;font-size:11px;font-weight:800;text-transform:uppercase;">Site code</td>
          <td style="padding:8px 14px;background:#0A0B10;color:#fff;border:1px solid #0A0B10;font-family:ui-monospace,Menlo,monospace;font-weight:700;">{password}</td></tr>
    </table>
    <p style="color:#6E7476;font-size:13px;margin-top:18px;">This password is shown once. Please change it on first sign-in via the Profile menu, or contact your HQ to rotate it.</p>
  </div>
</div>"""


__all__ = ["router"]
