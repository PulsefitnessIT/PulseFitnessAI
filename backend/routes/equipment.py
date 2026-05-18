from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response
from datetime import datetime, timezone
from typing import Dict, Any
import uuid
import csv
import io
import logging

import os
from utils.database import db, EMERGENT_LLM_KEY, APP_NAME, put_object, get_object
from utils.auth import get_current_user, get_organization_filter, apply_site_lock

# Backend-side base URL for building absolute, browser-loadable public URLs.
# Prefer backend-native FRONTEND_URL; fall back to REACT_APP_BACKEND_URL for local/dev.
_FRONTEND_URL = (
    os.environ.get("FRONTEND_URL")
    or os.environ.get("REACT_APP_BACKEND_URL")
    or ""
).replace("/api", "").rstrip("/")


def _public_photo_url(equipment_id: str) -> str:
    """Return an absolute URL that serves the equipment's main photo."""
    base = _FRONTEND_URL or ""
    return f"{base}/api/public/equipment/{equipment_id}/photo"


def _public_photo_gallery_url(equipment_id: str, photo_id: str) -> str:
    """Return an absolute URL that serves a specific gallery photo."""
    base = _FRONTEND_URL or ""
    return f"{base}/api/public/equipment/{equipment_id}/photos/{photo_id}"
from utils.helpers import get_equipment_stats, get_bulk_equipment_stats
from models.schemas import EquipmentCreate
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)
router = APIRouter()


def _compute_display_name(equip: dict) -> str:
    """Return a short, readable name for UI — first comma-split chunk or first 40 chars."""
    name = (equip.get("name") or "").strip()
    if not name:
        return (equip.get("equipment_type") or "Equipment").title()
    # Take content before the first comma or opening bracket
    for sep in [",", "("]:
        if sep in name:
            short = name.split(sep, 1)[0].strip()
            if len(short) >= 4:
                return short
    if len(name) <= 40:
        return name
    return name[:37].rstrip() + "…"


@router.post("/equipment")
async def create_equipment(equipment: EquipmentCreate, user: dict = Depends(get_current_user)) -> dict:
    payload = equipment.model_dump()
    # Iter 216bn — Pulse Fitness Lite / Pro orgs default supplier to
    # "Pulse Fitness" with the official service email when the operator
    # didn't pick one. Lee's request: customers on these plans almost
    # always service through Pulse Fitness's depot, so manual entry is
    # noise. They can still override per-equipment.
    org_id = user.get("organization_id")
    if org_id and not (payload.get("supplier") or "").strip():
        try:
            org = await db.organizations.find_one(
                {"id": org_id}, {"_id": 0, "account_type": 1},
            )
            if (org or {}).get("account_type") in ("lite", "pulse_pro"):
                payload["supplier"] = "Pulse Fitness"
                if not (payload.get("supplier_email") or "").strip():
                    payload["supplier_email"] = "service.dept@pulsefitness.com"
        except Exception as exc:
            logger.warning("[equipment] supplier default lookup failed: %s", exc)
    equipment_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "organization_id": org_id,
        **payload,
        "manuals": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.equipment.insert_one(equipment_doc)
    equipment_doc.pop('_id', None)

    # Iter 216bn — auto-attach any pre-existing spec sheet (and its hero
    # image) for this model/name. Best-effort, fail silent. Lee's
    # request: when a customer adds a Pulse Fitness machine, the spec
    # sheet + photo from Master's catalogue should appear automatically.
    try:
        from routes.spec_sheets import auto_match_equipment_to_specs
        match = await auto_match_equipment_to_specs(equipment_doc)
        if match:
            await db.equipment.update_one(
                {"id": equipment_doc["id"]},
                {"$set": {**match, "spec_sheet_attached_at": datetime.now(timezone.utc).isoformat()}},
            )
            equipment_doc.update(match)
    except Exception as exc:
        logger.warning("[equipment] spec-sheet auto-match failed: %s", exc)
    # Activation event — best-effort, idempotent per org.
    if user.get('organization_id'):
        try:
            from routes.activation_events import record_activation_event
            await record_activation_event(
                user['organization_id'], 'first_equipment_added',
                trigger_user_id=user.get('id'),
                payload={"equipment_id": equipment_doc['id']},
            )
        except Exception:
            pass
    stats = await get_equipment_stats(equipment_doc['id'], user)
    equipment_doc['stats'] = stats
    return equipment_doc


@router.get("/equipment")
async def get_all_equipment(
    user: dict = Depends(get_current_user), site_id: str = None
) -> dict:
    # Iter 216h120 — MOD HQ tiers need to drill into a child site (each
    # child is its own organisation, equipment lives under
    # organization_id=child_id) or roll the entire estate up. The
    # generic get_organization_filter / apply_site_lock pair only knows
    # the user's own org and silently returned 0 rows for any HQ user
    # — see the All Operations Sites "0 eq" regression.
    from utils.mod_scope import resolve_mod_query_filter
    org_filter = await resolve_mod_query_filter(user, site_id)

    # Iter 216h194 — Craig's regression: equipment added via the
    # OnboardingWizard pre-216h194 had no `site_id`, so the per-site
    # filter excluded it and the list showed "No equipment found"
    # immediately after onboarding. Lazily backfill: if the active
    # filter asks for `site_id=<X>` AND there are rows in the same org
    # with no site_id AND the org has exactly one active site, tag
    # those legacy rows with that single site. Idempotent — once a
    # row carries `site_id`, subsequent loads skip the heal.
    org_id = user.get("organization_id")
    if site_id and org_id and not user.get("_mod_scope_ids"):
        org_sites = await db.sites.find(
            {"organization_id": org_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1},
        ).to_list(2)
        if len(org_sites) == 1 and org_sites[0].get("id") == site_id:
            await db.equipment.update_many(
                {"organization_id": org_id, "site_id": {"$exists": False}},
                {"$set": {"site_id": site_id, "site_id_backfilled_at": datetime.now(timezone.utc).isoformat()}},
            )

    equipment_list = await db.equipment.find(org_filter, {"_id": 0}).sort("created_at", -1).to_list(2000)
    bulk_stats = await get_bulk_equipment_stats(equipment_list, org_filter)
    for equip in equipment_list:
        equip['stats'] = bulk_stats.get(equip['id'], {})
        if 'manuals' not in equip:
            equip['manuals'] = []
        equip['display_name'] = _compute_display_name(equip)
    return {"equipment": equipment_list}


@router.get("/equipment/export/csv")
async def export_equipment_csv(user: dict = Depends(get_current_user)) -> Response:
    org_filter = get_organization_filter(user)
    equipment_list = await db.equipment.find(org_filter, {"_id": 0}).to_list(500)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name", "Type", "Manufacturer", "Model", "Serial Number",
        "Purchase Date", "Warranty Expiry", "Length (m)", "Width (m)", "Height (m)", "Notes",
    ])
    for equip in equipment_list:
        writer.writerow([
            equip.get('name', ''), equip.get('equipment_type', ''),
            equip.get('manufacturer', ''), equip.get('model', ''),
            equip.get('serial_number', ''), equip.get('purchase_date', ''),
            equip.get('warranty_expiry', ''), equip.get('length', ''),
            equip.get('width', ''), equip.get('height', ''), equip.get('notes', '')
        ])
    csv_content = output.getvalue()
    return Response(content=csv_content, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=equipment_export.csv"})


@router.get("/equipment/template/csv")
async def get_equipment_csv_template() -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name", "Type", "Manufacturer", "Model", "Serial Number",
        "Purchase Date (YYYY-MM-DD)", "Warranty Expiry (YYYY-MM-DD)",
        "Length (m)", "Width (m)", "Height (m)", "Notes",
    ])
    writer.writerow([
        "Treadmill Pro 9000", "Treadmill", "Life Fitness", "95T Discover SE3",
        "LF-TM-001", "2024-01-15", "2027-01-15", "2.1", "0.9", "1.6", "Main cardio area",
    ])
    csv_content = output.getvalue()
    return Response(content=csv_content, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=equipment_template.csv"})


def _safe_float(value: str) -> float | None:
    """Parse a trimmed string to float, or return None."""
    stripped = value.strip() if value else ""
    return float(stripped) if stripped else None


def _parse_csv_row(row: dict, field_map: dict, user: dict) -> dict:
    """Build an equipment document from a single CSV row."""
    return {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "organization_id": user.get('organization_id'),
        "name": row.get(field_map['name'], '').strip(),
        "equipment_type": row.get(field_map['type'], '').strip(),
        "manufacturer": row.get(field_map.get('manufacturer', 'manufacturer'), '').strip() or None,
        "model": row.get(field_map.get('model', 'model'), '').strip() or None,
        "serial_number": row.get(field_map.get('serial', 'serial_number'), '').strip() or None,
        "purchase_date": row.get(field_map.get('purchase_date', 'purchase_date'), '').strip() or None,
        "warranty_expiry": row.get(field_map.get('warranty', 'warranty_expiry'), '').strip() or None,
        "length": _safe_float(row.get(field_map.get('length', 'length'), '')),
        "width": _safe_float(row.get(field_map.get('width', 'width'), '')),
        "height": _safe_float(row.get(field_map.get('height', 'height'), '')),
        "notes": row.get(field_map.get('notes', 'notes'), '').strip() or None,
        "service_provider": row.get(field_map.get('service_provider', 'service_provider'), '').strip() or None,
        "manuals": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _import_csv_rows(reader: csv.DictReader, user: dict, field_map: dict) -> dict:
    """Shared CSV import logic for both endpoint variants."""
    imported = 0
    errors: list[str] = []
    for idx, row in enumerate(reader, start=2):
        try:
            doc = _parse_csv_row(row, field_map, user)
            if not doc["name"] or not doc["equipment_type"]:
                errors.append(f"Row {idx}: Name and Type are required")
                continue
            await db.equipment.insert_one(doc)
            imported += 1
        except Exception as e:
            errors.append(f"Row {idx}: {e!s}")
    return {"imported": imported, "errors": errors, "total_rows": imported + len(errors)}


# Field mappings for the two CSV formats
_CSV_FIELDS_TITLE = {
    'name': 'Name', 'type': 'Type', 'manufacturer': 'Manufacturer',
    'model': 'Model', 'serial': 'Serial Number', 'purchase_date': 'Purchase Date',
    'warranty': 'Warranty Expiry', 'length': 'Length (m)', 'width': 'Width (m)',
    'height': 'Height (m)', 'notes': 'Notes', 'service_provider': 'Service Provider',
}
_CSV_FIELDS_SNAKE = {
    'name': 'name', 'type': 'equipment_type', 'manufacturer': 'manufacturer',
    'model': 'model', 'serial': 'serial_number', 'purchase_date': 'purchase_date',
    'warranty': 'warranty_expiry', 'length': 'length', 'width': 'width',
    'height': 'height', 'notes': 'notes', 'service_provider': 'service_provider',
}


@router.post("/equipment/import/csv")
async def import_equipment_csv_slash(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    from utils.file_validation import validate_upload, MIME_SPREADSHEETS
    contents = await file.read()
    validate_upload(file_bytes=contents, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=10 * 1024 * 1024)
    reader = csv.DictReader(io.StringIO(contents.decode('utf-8')))
    return await _import_csv_rows(reader, user, _CSV_FIELDS_TITLE)


@router.post("/equipment/import-csv")
async def import_equipment_csv_dash(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    from utils.file_validation import validate_upload, MIME_SPREADSHEETS
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be CSV format")
    content = await file.read()
    validate_upload(file_bytes=content, filename=file.filename, allowed=MIME_SPREADSHEETS, max_size=10 * 1024 * 1024)
    reader = csv.DictReader(io.StringIO(content.decode('utf-8')))
    return await _import_csv_rows(reader, user, _CSV_FIELDS_SNAKE)


@router.get("/equipment/csv-template")
async def get_csv_template() -> Response:
    template = (
        "name,equipment_type,manufacturer,model,serial_number,"
        "purchase_date,warranty_expiry,service_provider,length,width,height,notes\n"
        "Treadmill 1,Treadmill,Life Fitness,T5-Go,SN123456,"
        "2024-01-15,2027-01-15,Pulse Fitness,2.5,1.5,1.8,Main cardio area\n"
    )
    return Response(content=template, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=equipment_template.csv"})


LIFESPAN_THRESHOLDS = {
    'treadmill': (2555, 3650), 'running machine': (2555, 3650),
    'bike': (3650, 5475), 'exercise bike': (3650, 5475), 'cycle': (3650, 5475),
}


def _check_warranty_alert(stats: dict) -> tuple[str | None, str | None, list[str]]:
    """Check warranty-related alerts."""
    days = stats.get('warranty_days_remaining')
    if not days:
        return None, None, []
    if days < 0:
        return "critical", "Warranty expired", ["Consider extended warranty or replacement plan"]
    if days < 30:
        return "warning", f"Warranty expiring in {days} days", ["Review warranty renewal options"]
    return None, None, []


def _check_lifespan_alert(stats: dict, equip_type: str) -> tuple[str | None, str | None, list[str]]:
    """Check equipment lifespan alerts."""
    days = stats.get('days_in_service')
    if not days:
        return None, None, []
    key = equip_type.lower()
    for type_key, (warn_days, crit_days) in LIFESPAN_THRESHOLDS.items():
        if type_key in key:
            if days > crit_days:
                return "critical", "Equipment exceeds recommended lifespan", ["Schedule replacement evaluation"]
            if days > warn_days:
                return "warning", "Equipment approaching end of lifespan", ["Increase maintenance frequency"]
            break
    return None, None, []


def _check_fault_frequency_alert(stats: dict) -> tuple[str | None, str | None, list[str]]:
    """Check fault frequency alerts."""
    if stats.get('total_issues', 0) > 5 and stats.get('open_issues', 0) > 2:
        return "critical", "High issue frequency detected", ["Consider replacement if repair costs exceed 50% of new equipment value"]
    return None, None, []


def _merge_alert_level(current: str | None, new: str | None) -> str | None:
    """Critical always wins over warning; new critical upgrades a warning."""
    if current is None:
        return new
    if new == "critical" and current == "warning":
        return new
    return current


@router.get("/equipment/manufacturers")
async def list_manufacturers() -> dict:
    """Return the curated list of fitness-equipment manufacturers used to
    populate the Add/Edit Equipment dropdowns. Sourced from
    ``utils.equipment_image_lookup.MANUFACTURER_DOMAINS`` so the same list
    powers both the dropdown and the auto image-lookup.

    Aliases (e.g. "matrix" + "matrix fitness") collapse to one canonical
    display label per domain via the override map below, falling back to a
    title-cased version of the longest alias. Sorted alphabetically.
    The frontend appends an "Other" option at submit time.
    """
    from utils.equipment_image_lookup import MANUFACTURER_DOMAINS  # local import keeps cold-start light

    # Hand-curated display overrides for brands where simple title-case
    # produces the wrong casing (acronyms, run-on words, numerals).
    OVERRIDES = {
        "lifefitness.com": "Life Fitness",
        "matrixfitness.com": "Matrix Fitness",
        "bhfitness.com": "BH Fitness",
        "concept2.com": "Concept2",
        "onepeloton.com": "Peloton",
        "octanefitness.com": "Octane Fitness",
        "powerplate.com": "Power Plate",
        "schwinnfitness.com": "Schwinn",
        "bodysolid.com": "Body Solid",
        "freemotionfitness.com": "Freemotion",
        "jacobsladderexercise.com": "Jacobs Ladder",
        "trueformrunner.com": "Trueform",
        "originfitness.com": "Origin Fitness",
        "watsongym.com": "Watson Gym Equipment",
        "hoistfitness.com": "Hoist Fitness",
        "indigofitness.com": "Indigo Fitness",
        "physicalcompany.co.uk": "Physical Company",
        "jordanfitness.com": "Jordan Fitness",
        "wattbike.com": "Wattbike",
        "zivafitness.com": "Ziva",
        "panatta.com": "Panatta",
        "gymnova.com": "Gymnova",
        "eleiko.com": "Eleiko",
        "primalstrength.com": "Primal Strength",
        "exigouk.co.uk": "Exigo",
        "forceusa.com": "Force USA",
        "fringesport.com": "Fringe Sport",
        "yorkfitness.com": "York Fitness",
        "tunturi.com": "Tunturi",
        "kettlersport.com": "Kettler",
        "stagescycling.com": "Stages Cycling",
        "spiritfitness.com": "Spirit Fitness",
        "torquefitness.com": "Torque Fitness",
        "truefitness.com": "True Fitness",
        "vasatrainer.com": "Vasa",
        "pulsefitness.com": "Pulse Fitness",
        "technogym.com": "Technogym",
        "precor.com": "Precor",
        "cybexintl.com": "Cybex",
        "startrac.com": "Star Trac",
        "hammerstrength.com": "Hammer Strength",
        "woodway.com": "Woodway",
        "nautilus.com": "Nautilus",
        "stairmaster.com": "StairMaster",
        "escapefitness.com": "Escape Fitness",
        "keiser.com": "Keiser",
        "assaultfitness.com": "Assault Fitness",
        "roguefitness.com": "Rogue Fitness",
        "solefitness.com": "Sole Fitness",
        "bowflex.com": "Bowflex",
    }

    by_domain: dict[str, str] = {}
    for raw_name, domain in MANUFACTURER_DOMAINS.items():
        display = OVERRIDES.get(domain) or raw_name.title()
        existing = by_domain.get(domain)
        # Lock-in override; otherwise prefer the longer alias.
        if existing is None or (domain not in OVERRIDES and len(display) > len(existing)):
            by_domain[domain] = display
    items = [
        {"name": name, "domain": domain}
        for domain, name in by_domain.items()
    ]
    items.sort(key=lambda r: r["name"].lower())
    return {"manufacturers": items, "count": len(items)}


@router.get("/equipment/lifecycle-alerts")
async def get_lifecycle_alerts(user: dict = Depends(get_current_user)) -> dict:
    equipment_list = await db.equipment.find({"user_id": user['id']}, {"_id": 0}).to_list(200)
    alerts = []
    for equip in equipment_list:
        stats = await get_equipment_stats(equip['id'], user['id'])
        alert_level = None
        alert_message = None
        recommendations: list[str] = []

        for level, message, recs in (
            _check_warranty_alert(stats),
            _check_lifespan_alert(stats, equip.get('equipment_type', '')),
            _check_fault_frequency_alert(stats),
        ):
            if not level:
                continue
            new_level = _merge_alert_level(alert_level, level)
            if new_level != alert_level:
                alert_level = new_level
                alert_message = message
            recommendations.extend(recs)

        if alert_level:
            alerts.append({
                "equipment_id": equip['id'], "equipment_name": equip['name'],
                "equipment_type": equip['equipment_type'], "alert_level": alert_level,
                "message": alert_message, "recommendations": recommendations, "stats": stats,
            })
    return {
        "alerts": alerts,
        "critical_count": len([a for a in alerts if a['alert_level'] == 'critical']),
        "warning_count": len([a for a in alerts if a['alert_level'] == 'warning']),
    }


@router.get("/equipment/{equipment_id}")
async def get_equipment(equipment_id: str, user: dict = Depends(get_current_user)) -> dict:
    org_filter = get_organization_filter(user)
    equipment = await db.equipment.find_one({"id": equipment_id, **org_filter}, {"_id": 0})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    # Iter 216bl — site-locked staff are refused access to equipment
    # outside their allowed sites. After the org filter so existence
    # isn't leaked across orgs.
    role = (user.get("role") or "").lower()
    is_priv = (
        role in ("owner", "manager", "master_admin", "master")
        or bool(user.get("is_master_admin"))
    )
    allowed = user.get("allowed_site_ids") or []
    if not is_priv and allowed and equipment.get("site_id") and equipment["site_id"] not in allowed:
        raise HTTPException(status_code=403, detail="You do not have access to that site")
    equipment['stats'] = await get_equipment_stats(equipment_id, user)
    issue_filter = get_organization_filter(user)
    if equipment.get('serial_number'):
        issue_filter["serial_number"] = equipment['serial_number']
    else:
        issue_filter["serial_number"] = equipment.get('name', '')
    issues = await db.issues.find(issue_filter, {"_id": 0}).to_list(50)
    equipment['issues'] = issues
    audits = await db.audits.find({"equipment_id": equipment_id}, {"_id": 0}).sort("created_at", -1).to_list(20)
    equipment['audits'] = audits
    if 'manuals' not in equipment:
        equipment['manuals'] = []
    equipment['display_name'] = _compute_display_name(equipment)
    return equipment


@router.patch("/equipment/{equipment_id}")
async def update_equipment(equipment_id: str, data: Dict[str, Any], user: dict = Depends(get_current_user)) -> dict:
    """Update equipment with partial data - accepts any subset of fields"""
    org_filter = get_organization_filter(user)

    # Only allow updating specific fields
    allowed_fields = {
        "name", "equipment_type", "manufacturer", "model", "serial_number",
        "purchase_date", "warranty_expiry", "length", "width", "height", "notes",
        "location", "sla_response_time", "sla_contract_ref", "sla_expiry", "photo_url",
        "replacement_cost", "expected_lifespan_years",
        # Supplier reassignment — restricted below to owner/manager roles.
        "supplier",
        # Iter 216h114 — also persist the supplier id when assigning so
        # fault-routing prefers the direct link over name lookups.
        "supplier_id",
        # Iter 216h49 — owners/managers can now move kit between sites
        # directly via PATCH. Also gated below.
        "site_id",
    }
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Supplier changes are a commercial decision — gated to owners/managers
    # (and master admins for impersonation). Staff may edit every other field.
    if ("supplier" in update_data or "supplier_id" in update_data) and user.get("role") not in (
        "owner", "manager", "master_admin",
    ):
        raise HTTPException(
            status_code=403,
            detail="Only owners and managers can change the supplier on equipment",
        )

    # Iter 216h49 — site moves are an organisational decision and must
    # also be gated. Non-privileged staff cannot transfer kit between sites.
    if "site_id" in update_data and user.get("role") not in (
        "owner", "manager", "master_admin",
    ) and not user.get("is_master_admin"):
        raise HTTPException(
            status_code=403,
            detail="Only owners and managers can move equipment between sites",
        )

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Capture the previous supplier value so we can detect a real change
    # before dispatching a reassignment notification.
    previous_supplier = None
    if "supplier" in update_data:
        existing_doc = await db.equipment.find_one(
            {"id": equipment_id, **org_filter},
            {"_id": 0, "supplier": 1, "organization_id": 1, "name": 1,
             "equipment_type": 1, "serial_number": 1, "location": 1, "id": 1},
        )
        previous_supplier = (existing_doc or {}).get("supplier") or ""

    result = await db.equipment.update_one(
        {"id": equipment_id, **org_filter},
        {"$set": update_data}
    )
    if result.modified_count == 0:
        # Check if equipment exists
        exists = await db.equipment.find_one({"id": equipment_id, **org_filter})
        if not exists:
            raise HTTPException(status_code=404, detail="Equipment not found")

    # Optionally notify the newly-assigned supplier. Owner/manager asked for it
    # explicitly via `notify_supplier=True` in the body; no-op otherwise.
    notify_flag = bool(data.get("notify_supplier"))
    new_supplier_name = (update_data.get("supplier") or "").strip()
    supplier_changed = new_supplier_name and new_supplier_name != (previous_supplier or "")
    notified = False
    if notify_flag and supplier_changed:
        notified = await _dispatch_single_equipment_reassignment(
            equipment_id, new_supplier_name, user.get("organization_id"), org_filter,
        )

    return {"success": True, "notified_supplier": notified}


async def _dispatch_single_equipment_reassignment(
    equipment_id: str, new_supplier_name: str, organization_id: str, org_filter: dict,
) -> bool:
    """Fire the supplier reassignment email for one equipment row. Small
    helper kept under cc 10 and isolated from the main PATCH handler.
    Returns True when an email was actually dispatched, False otherwise."""
    supplier_doc = await db.suppliers.find_one(
        {"organization_id": organization_id, "name": new_supplier_name},
        {"_id": 0},
    )
    equipment_doc = await db.equipment.find_one(
        {"id": equipment_id, **org_filter},
        {"_id": 0},
    )
    if not supplier_doc or not equipment_doc:
        return False
    from routes.supplier_portal import send_supplier_reassignment_email
    return await send_supplier_reassignment_email(
        supplier_doc, organization_id, [equipment_doc],
    )


@router.delete("/equipment/{equipment_id}")
async def delete_equipment(equipment_id: str, user: dict = Depends(get_current_user)) -> dict:
    # Iter 216h49 — was previously scoped to {user_id: user['id']} which
    # meant only the original uploader could delete the kit. Lee
    # (org owner) reported he couldn't delete kit created by other staff.
    # Switch to org-scoped (with owner/manager gate) so any privileged
    # operator within the org can retire a piece of kit.
    if user.get("role") not in ("owner", "manager", "master_admin") and not user.get("is_master_admin"):
        raise HTTPException(
            status_code=403,
            detail="Only owners and managers can delete equipment",
        )
    org_filter = get_organization_filter(user)
    # Capture before delete for audit trail
    doc = await db.equipment.find_one(
        {"id": equipment_id, **org_filter},
        {"_id": 0, "name": 1, "serial_number": 1, "organization_id": 1, "site_id": 1},
    )
    result = await db.equipment.delete_one({"id": equipment_id, **org_filter})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Equipment not found")
    from utils.security_plus import audit_required
    await audit_required("security_audit_log", {
        "event": "equipment.deleted", "actor_id": user["id"], "actor_email": user.get("email"),
        "org_id": (doc or {}).get("organization_id"),
        "site_id": (doc or {}).get("site_id"),
        "equipment_id": equipment_id, "equipment_name": (doc or {}).get("name"),
        "serial_number": (doc or {}).get("serial_number"),
    })
    return {"success": True}


@router.post("/equipment/{equipment_id}/move")
async def move_equipment_site(
    equipment_id: str,
    body: Dict[str, Any],
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216h49 — Move a piece of equipment to a different site within
    the same organisation. Owner/manager only (master admin also allowed
    so platform staff can reorganise without impersonation).

    Body: { "site_id": "<target site id>" }

    Validates that the target site belongs to the same org as the
    equipment, persists the move with an audit-log entry, and returns
    the updated equipment row.
    """
    if user.get("role") not in ("owner", "manager", "master_admin") and not user.get("is_master_admin"):
        raise HTTPException(
            status_code=403,
            detail="Only owners and managers can move equipment between sites",
        )
    target_site_id = (body.get("site_id") or "").strip()
    if not target_site_id:
        raise HTTPException(status_code=400, detail="site_id is required")

    org_filter = get_organization_filter(user)
    equipment = await db.equipment.find_one(
        {"id": equipment_id, **org_filter},
        {"_id": 0, "id": 1, "name": 1, "site_id": 1, "organization_id": 1, "serial_number": 1},
    )
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    target_site = await db.sites.find_one(
        {"id": target_site_id, "organization_id": equipment.get("organization_id")},
        {"_id": 0, "id": 1, "name": 1},
    )
    if not target_site:
        raise HTTPException(
            status_code=404,
            detail="Target site not found on this organisation",
        )

    previous_site_id = equipment.get("site_id")
    if previous_site_id == target_site_id:
        return {"success": True, "moved": False, "equipment_id": equipment_id}

    await db.equipment.update_one(
        {"id": equipment_id},
        {"$set": {
            "site_id": target_site_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    # Linked issues travel with the equipment so the per-site dashboards
    # reconcile correctly. Suppliers / contracts stay org-scoped.
    await db.issues.update_many(
        {"equipment_id": equipment_id},
        {"$set": {"site_id": target_site_id}},
    )

    from utils.security_plus import audit_required
    await audit_required("security_audit_log", {
        "event": "equipment.moved",
        "actor_id": user["id"],
        "actor_email": user.get("email"),
        "org_id": equipment.get("organization_id"),
        "equipment_id": equipment_id,
        "equipment_name": equipment.get("name"),
        "serial_number": equipment.get("serial_number"),
        "from_site_id": previous_site_id,
        "to_site_id": target_site_id,
        "to_site_name": target_site.get("name"),
    })

    return {
        "success": True,
        "moved": True,
        "equipment_id": equipment_id,
        "from_site_id": previous_site_id,
        "to_site_id": target_site_id,
        "to_site_name": target_site.get("name"),
    }


@router.get("/equipment/{equipment_id}/stats")
async def get_equipment_statistics(equipment_id: str, user: dict = Depends(get_current_user)) -> dict:
    stats = await get_equipment_stats(equipment_id, user)
    return stats


@router.post("/equipment/{equipment_id}/manual")
async def upload_equipment_manual(equipment_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    from utils.file_validation import validate_upload, MIME_OFFICE
    equipment = await db.equipment.find_one({"id": equipment_id, "user_id": user['id']}, {"_id": 0})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    path = f"{APP_NAME}/equipment/{user['id']}/{equipment_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    ct = validate_upload(file_bytes=data, filename=file.filename, allowed=MIME_OFFICE, max_size=30 * 1024 * 1024)

    # Compress PDFs before storage
    if ext.lower() == "pdf":
        from utils.pdf_compress import compress_pdf
        data = compress_pdf(data)

    result = put_object(path, data, ct)

    manual_doc = {
        "id": str(uuid.uuid4()),
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": ct,
        "size": result["size"],
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }
    await db.equipment.update_one({"id": equipment_id}, {"$push": {"manuals": manual_doc}})
    return manual_doc


@router.get("/equipment/{equipment_id}/manual/{manual_id}")
async def get_equipment_manual(equipment_id: str, manual_id: str, user: dict = Depends(get_current_user)):
    """Stream the manual back inline so it can be embedded in an iframe viewer.
    Requires the same org-scope as listing the equipment.
    """
    from fastapi.responses import Response
    from utils.database import get_object
    org_id = user.get("organization_id")
    eq = await db.equipment.find_one(
        {"id": equipment_id, "$or": [{"user_id": user["id"]}, {"organization_id": org_id}]},
        {"_id": 0, "manuals": 1},
    )
    if not eq:
        raise HTTPException(404, "Equipment not found")
    manual = next((m for m in (eq.get("manuals") or []) if m.get("id") == manual_id), None)
    if not manual:
        raise HTTPException(404, "Manual not found")
    try:
        body, content_type = get_object(manual["storage_path"])
    except Exception:
        raise HTTPException(404, "Manual file is missing from storage")
    fname = manual.get("original_filename", "manual")
    return Response(
        content=body,
        media_type=manual.get("content_type") or content_type or "application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{fname}"',
            "Cache-Control": "private, max-age=60",
        },
    )


def _build_prediction_context(equipment: dict, issues: list, stats: dict) -> str:
    """Build the prompt context for predictive maintenance AI."""
    issue_lines = "\n".join(
        f"- {i['issue_description']} (Severity: {i['severity']}, Status: {i['status']})"
        for i in issues[:10]
    )
    return (
        f"Analyze maintenance patterns for this gym equipment:\n\n"
        f"Equipment Details:\n"
        f"- Type: {equipment['equipment_type']}\n"
        f"- Manufacturer: {equipment.get('manufacturer', 'Unknown')}\n"
        f"- Model: {equipment.get('model', 'Unknown')}\n"
        f"- Days in Service: {stats.get('days_in_service', 'Unknown')}\n"
        f"- Total Issues: {stats.get('total_issues', 0)}\n"
        f"- Open Issues: {stats.get('open_issues', 0)}\n\n"
        f"Recent Issues:\n{issue_lines}\n\n"
        f"Based on this data, provide:\n"
        f"1. Predicted maintenance needs in next 30/60/90 days\n"
        f"2. Parts likely to need replacement\n"
        f"3. Preventive actions to reduce future issues\n"
        f"4. Cost-benefit analysis of repair vs replace\n"
        f"5. Specific maintenance schedule recommendations"
    )


@router.post("/equipment/{equipment_id}/predictive-maintenance")
async def get_predictive_maintenance(equipment_id: str, user: dict = Depends(get_current_user)) -> dict:
    equipment = await db.equipment.find_one({"id": equipment_id, "user_id": user['id']}, {"_id": 0})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    issues = await db.issues.find({"user_id": user['id'], "machine_name": equipment['name']}, {"_id": 0}).to_list(100)
    stats = await get_equipment_stats(equipment_id, user['id'])

    session_id = f"predictive_{equipment_id}_{datetime.now().timestamp()}"
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message="You are an expert in gym equipment maintenance and predictive analytics. Provide detailed, actionable maintenance predictions."
    ).with_model("openai", "gpt-5.2")

    prediction = await chat.send_message(
        UserMessage(text=_build_prediction_context(equipment, issues, stats))
    )

    created_at = datetime.now(timezone.utc).isoformat()
    await db.predictive_maintenance.insert_one({
        "id": str(uuid.uuid4()),
        "equipment_id": equipment_id,
        "user_id": user['id'],
        "prediction": prediction,
        "created_at": created_at,
    })

    return {"equipment": equipment, "stats": stats, "prediction": prediction, "generated_at": created_at}


@router.post("/equipment/{equipment_id}/photo")
async def upload_equipment_main_photo(equipment_id: str, file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    from utils.file_validation import validate_upload, MIME_IMAGES
    org_filter = get_organization_filter(user)
    equipment = await db.equipment.find_one({"id": equipment_id, **org_filter})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    data = await file.read()
    ct = validate_upload(file_bytes=data, filename=file.filename, allowed=MIME_IMAGES, max_size=25 * 1024 * 1024)
    path = f"{APP_NAME}/equipment-photos/{equipment_id}/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, ct)

    # Storage returns {path, size, etag} (no URL). Persist the storage key separately
    # and expose an absolute, browser-loadable URL that proxies back through our API.
    storage_path = result.get("path", path)
    photo_url = _public_photo_url(equipment_id)
    await db.equipment.update_one(
        {"id": equipment_id},
        {"$set": {
            "photo_url": photo_url,
            "photo_path": storage_path,
            "photo_content_type": ct,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"photo_url": photo_url}


def _parse_date_remaining(date_str: str | None) -> tuple[bool, int | None]:
    """Parse an ISO date string and return (is_active, days_remaining)."""
    if not date_str:
        return False, None
    try:
        parsed = datetime.fromisoformat(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        days = (parsed - datetime.now(timezone.utc)).days
        return days > 0, days
    except (ValueError, TypeError):
        return False, None


def _format_remaining(days: int) -> str:
    """Format a number of remaining days as a human-readable string."""
    if days >= 365:
        years = days // 365
        remainder = days % 365
        return f"{years}y {remainder}d remaining" if remainder else f"{years}y remaining"
    return f"{days}d remaining"


def _determine_coverage(
    warranty_active: bool,
    warranty_days: int | None,
    contract_active: bool,
    contract_days: int | None,
) -> tuple[bool, str, str]:
    """Return (covered, coverage_type, label) based on warranty/contract state."""
    if warranty_active and warranty_days is not None:
        return True, "warranty", f"Under Warranty — {_format_remaining(warranty_days)}"
    if contract_active and contract_days is not None:
        return True, "contract", f"Under Contract — {_format_remaining(contract_days)}"
    return False, "none", "No Warranty / Contract"


@router.get("/equipment/{equipment_id}/coverage")
async def get_equipment_coverage(equipment_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Return warranty/contract coverage status for a piece of equipment.

    Iter 216h198 — Phase 2 of the Ops↔CRM↔ServiceDesk link. Response is
    now a superset of the legacy shape: the original
    ``warranty_active`` / ``contract_active`` fields are kept (existing
    callers + audit reports rely on them) and we add CRM-side aftersales
    contract data so the Operations equipment-detail panel can render
    "Covered by Contract #GAX-202605-XYZ until 31/12/2027 — Full
    coverage (parts + labour)" inline.
    """
    org_filter = get_organization_filter(user)
    equipment = await db.equipment.find_one({"id": equipment_id, **org_filter}, {"_id": 0})
    if not equipment and user.get("is_master_admin"):
        equipment = await db.equipment.find_one({"id": equipment_id}, {"_id": 0})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    warranty_active, warranty_days = _parse_date_remaining(equipment.get("warranty_expiry"))
    contract_active, contract_days = _parse_date_remaining(equipment.get("sla_expiry"))
    covered, coverage_type, coverage_label = _determine_coverage(
        warranty_active, warranty_days, contract_active, contract_days,
    )

    # CRM aftersales contract layer.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from datetime import timedelta as _td
    cutoff_90d = (datetime.now(timezone.utc) + _td(days=90)).strftime("%Y-%m-%d")
    assets = await db.crm2_contract_assets.find({"asset_id": equipment_id}, {"_id": 0}).to_list(200)
    contract_ids = list({a.get("contract_id") for a in assets if a.get("contract_id")})
    contracts = await db.crm2_contracts.find(
        {"id": {"$in": contract_ids}}, {"_id": 0},
    ).to_list(200) if contract_ids else []
    contracts_by_id = {c.get("id"): c for c in contracts}

    crm_rows = []
    try:
        from routes.crm_contracts import CONTRACT_TIERS as _TIERS
        tier_order = {t["id"]: i for i, t in enumerate(_TIERS)}
    except Exception:
        tier_order = {}

    def _days_until(date_str: str):
        if not date_str:
            return None
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return max(0, (d - datetime.now(timezone.utc)).days)
        except ValueError:
            return None

    for a in assets:
        contract = contracts_by_id.get(a.get("contract_id"))
        if not contract:
            continue
        end = contract.get("end_date", "")
        if end and end < today:
            continue
        if contract.get("status") not in {"active", "signed", "expiring"}:
            continue
        crm_rows.append({
            "contract_id": contract.get("id"),
            "contract_number": contract.get("contract_number"),
            "contract_title": contract.get("title"),
            "tier": contract.get("tier"),
            "coverage_type": a.get("coverage_type", "full"),
            "start_date": contract.get("start_date"),
            "end_date": end,
            "exclusions": a.get("exclusions", ""),
            "expiring_soon": bool(end and end <= cutoff_90d),
            "days_until_expiry": _days_until(end),
            "_rank": tier_order.get(contract.get("tier", ""), -1),
        })

    crm_rows.sort(key=lambda r: (r["_rank"], r.get("end_date") or ""), reverse=True)
    best = dict(crm_rows[0]) if crm_rows else None
    if best:
        best.pop("_rank", None)
    for r in crm_rows:
        r.pop("_rank", None)

    return {
        "equipment_id": equipment_id,
        "equipment_name": equipment.get("name", ""),
        "covered": covered or bool(best),
        "type": coverage_type,
        "label": coverage_label,
        "warranty_active": warranty_active,
        "warranty_days_remaining": warranty_days,
        "warranty_expiry": equipment.get("warranty_expiry"),
        "contract_active": contract_active,
        "contract_days_remaining": contract_days,
        "sla_contract_ref": equipment.get("sla_contract_ref"),
        "sla_expiry": equipment.get("sla_expiry"),
        "supplier": equipment.get("manufacturer", ""),
        # Iter 216h198 — CRM aftersales contract layer.
        "crm_coverage": {
            "has_coverage": bool(best),
            "best": best,
            "all_contracts": crm_rows,
        },
    }


# ── Equipment Photos ──────────────────────────────────────────────

@router.post("/equipment/{equipment_id}/photos")
async def upload_equipment_photo(
    equipment_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """Upload a photo to an equipment item. Managers and owners only."""
    from utils.file_validation import validate_upload, MIME_IMAGES
    role = user.get("role", "staff")
    if role not in ("owner", "manager") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Only managers and owners can upload photos")

    org_filter = get_organization_filter(user)
    equipment = await db.equipment.find_one({"id": equipment_id, **org_filter}, {"_id": 0})
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    content = await file.read()
    ct = validate_upload(file_bytes=content, filename=file.filename, allowed=MIME_IMAGES, max_size=10 * 1024 * 1024)

    photo_id = str(uuid.uuid4())
    key = f"{APP_NAME}/equipment-photos/{equipment_id}/gallery/{photo_id}.{(file.filename.rsplit('.', 1)[-1] if '.' in file.filename else 'jpg')}"
    result = put_object(key, content, ct)
    storage_path = result.get("path", key) if isinstance(result, dict) else key
    url = _public_photo_gallery_url(equipment_id, photo_id)

    photo_doc = {
        "id": photo_id,
        "url": url,
        "storage_path": storage_path,
        "filename": file.filename,
        "content_type": ct,
        "size": len(content),
        "uploaded_by": user["id"],
        "uploaded_by_name": user.get("full_name", ""),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.equipment.update_one(
        {"id": equipment_id},
        {"$push": {"photos": photo_doc}},
    )

    return {"photo": photo_doc}


@router.delete("/equipment/{equipment_id}/photos/{photo_id}")
async def delete_equipment_photo(
    equipment_id: str,
    photo_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Delete a photo from equipment. Managers and owners only."""
    role = user.get("role", "staff")
    if role not in ("owner", "manager") and not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Only managers and owners can delete photos")

    org_filter = get_organization_filter(user)
    result = await db.equipment.update_one(
        {"id": equipment_id, **org_filter},
        {"$pull": {"photos": {"id": photo_id}}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Photo not found")

    return {"message": "Photo deleted"}



# ═════════════════════ Manufacturer Image AI Fallback ═════════════════════

from utils.equipment_image_lookup import lookup_equipment_image  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/equipment/{equipment_id}/lookup-image")
async def auto_lookup_equipment_image(
    equipment_id: str,
    verify: bool = True,
    force: bool = False,
    user: dict = Depends(get_current_user),
) -> dict:
    """Search the manufacturer website for a product photo and, if found +
    verified by GPT-4o-mini, attach it to the equipment as `auto_image_url`."""
    org_filter = get_organization_filter(user)
    eq = await db.equipment.find_one({"id": equipment_id, **org_filter}, {"_id": 0})
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")

    if not force and eq.get("auto_image_url"):
        return {"ok": True, "already_present": True, "image_url": eq["auto_image_url"]}

    manufacturer = eq.get("manufacturer") or eq.get("supplier") or ""
    result = await lookup_equipment_image(
        manufacturer=manufacturer,
        name=eq.get("name"),
        equipment_type=eq.get("equipment_type"),
        verify=verify,
    )
    if not result or not result.get("image_url"):
        return {"ok": False, "message": "No matching product image found on manufacturer site"}

    update = {
        "auto_image_url": result["image_url"],
        "auto_image_source_url": result.get("source_url"),
        "auto_image_verified": bool(result.get("verified")),
        "auto_image_looked_up_at": _now_iso(),
    }
    # Only set photo_source = 'auto' when the equipment has no uploaded photo.
    if not eq.get("photo_url"):
        update["photo_source"] = "auto"
    await db.equipment.update_one({"id": equipment_id}, {"$set": update})
    return {"ok": True, **result}


@router.post("/equipment/lookup-images/batch")
async def batch_lookup_equipment_images(
    limit: int = 50,
    user: dict = Depends(get_current_user),
) -> dict:
    """Backfill missing manufacturer images across the org, in one request.

    Processes up to ``limit`` equipment that currently have no photo_url and
    no auto_image_url. Returns a summary; skipped entries have a reason."""
    org_filter = get_organization_filter(user)
    limit = max(1, min(int(limit), 200))
    cursor = db.equipment.find({
        **org_filter,
        "photo_url": {"$in": [None, ""]},
        "auto_image_url": {"$in": [None, ""]},
    }, {"_id": 0}).limit(limit)
    items = await cursor.to_list(limit)

    processed: list[dict] = []
    matched = 0
    skipped = 0
    for eq in items:
        try:
            manufacturer = eq.get("manufacturer") or eq.get("supplier") or ""
            result = await lookup_equipment_image(
                manufacturer=manufacturer,
                name=eq.get("name"),
                equipment_type=eq.get("equipment_type"),
                verify=True,
            )
            if result and result.get("image_url"):
                await db.equipment.update_one(
                    {"id": eq["id"]},
                    {"$set": {
                        "auto_image_url": result["image_url"],
                        "auto_image_source_url": result.get("source_url"),
                        "auto_image_verified": bool(result.get("verified")),
                        "auto_image_looked_up_at": _now_iso(),
                        "photo_source": "auto" if not eq.get("photo_url") else eq.get("photo_source"),
                    }},
                )
                matched += 1
                processed.append({"id": eq["id"], "name": eq.get("name"), "status": "matched", "verified": result.get("verified")})
            else:
                skipped += 1
                processed.append({"id": eq["id"], "name": eq.get("name"), "status": "no_match"})
        except Exception as exc:
            logger.warning("Image lookup failed for %s: %s", eq.get("id"), exc)
            skipped += 1
            processed.append({"id": eq["id"], "name": eq.get("name"), "status": "error", "error": str(exc)})

    return {
        "ok": True,
        "total_examined": len(items),
        "matched": matched,
        "skipped": skipped,
        "results": processed,
    }


@router.delete("/equipment/{equipment_id}/auto-image")
async def clear_auto_image(equipment_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Allow an operator to reject an auto-found image."""
    org_filter = get_organization_filter(user)
    result = await db.equipment.update_one(
        {"id": equipment_id, **org_filter},
        {"$unset": {
            "auto_image_url": "",
            "auto_image_source_url": "",
            "auto_image_verified": "",
            "auto_image_looked_up_at": "",
        }, "$set": {"photo_source": "none"}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return {"ok": True}



# ── Public photo serving (no auth) ────────────────────────────────
# Storage blobs require X-Storage-Key which the browser can't send, so we proxy
# photos through the backend. These endpoints are public so QR-scan pages and
# marketing embeds can load equipment photos without a JWT.

@router.get("/public/equipment/{equipment_id}/photo")
async def public_equipment_main_photo(equipment_id: str):
    eq = await db.equipment.find_one({"id": equipment_id}, {"_id": 0})
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")

    # Prefer explicit storage path; legacy records may still have a raw storage
    # key stashed in photo_url.
    path = eq.get("photo_path")
    if not path:
        legacy = eq.get("photo_url") or ""
        if legacy and not legacy.startswith("http") and "/" in legacy:
            path = legacy
    if not path:
        raise HTTPException(status_code=404, detail="No photo")
    try:
        data, content_type = get_object(path)
    except Exception as exc:
        logger.warning("Failed to load equipment photo %s: %s", equipment_id, exc)
        raise HTTPException(status_code=404, detail="Photo not available") from exc
    return Response(
        content=data,
        media_type=eq.get("photo_content_type") or content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=600"},
    )


@router.get("/public/equipment/{equipment_id}/photos/{photo_id}")
async def public_equipment_gallery_photo(equipment_id: str, photo_id: str):
    eq = await db.equipment.find_one(
        {"id": equipment_id, "photos.id": photo_id},
        {"_id": 0, "photos.$": 1},
    )
    if not eq or not eq.get("photos"):
        raise HTTPException(status_code=404, detail="Photo not found")
    photo = eq["photos"][0]
    path = photo.get("storage_path")
    if not path:
        # Legacy: stored url itself may have been a storage key
        legacy = photo.get("url") or ""
        if legacy and not legacy.startswith("http") and "/" in legacy:
            path = legacy
    if not path:
        raise HTTPException(status_code=404, detail="No photo data")
    try:
        data, content_type = get_object(path)
    except Exception as exc:
        logger.warning("Failed to load gallery photo %s/%s: %s", equipment_id, photo_id, exc)
        raise HTTPException(status_code=404, detail="Photo not available") from exc
    return Response(
        content=data,
        media_type=photo.get("content_type") or content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=600"},
    )

