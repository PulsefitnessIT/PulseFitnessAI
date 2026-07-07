"""
Master Admin · Pulse Fitness sub-router.

Iter 216h180 — Extracted from `routes/master_admin.py` as phase 4 of
the 4,283 LoC → 5-6 focused routers decomposition.

Owns the Pulse-specific surface (Pulse is the in-house Pulse Fitness brand
that owns + operates ~200 sites and uses Pulse Fitness for itself):

    GET    /master-admin/pulse-stats          — fleet-wide rollup across all Pulse sites
    GET    /master-admin/pulse-equipment-kits — standard equipment kit catalogue
    POST   /master-admin/onboard-pulse-site   — full multi-step Pulse site onboarding

Also owns the static `PULSE_EQUIPMENT_KITS` catalogue and the onboarding
helper trio (`_create_onboard_users`, `_create_kit_equipment`,
`_create_manual_equipment`, `_create_onboard_equipment`,
`_validate_onboard_data`) — these are private to this surface.

Shared helpers (`require_master_admin`, `log_activity`,
`merge_address`, `_parse_onboard_date`) are imported FROM
`routes.master_admin` because they're used by ~12 other modules
and must stay there.
"""
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user, hash_password as _hash_password
from utils.database import db
from routes.master_admin import (
    _parse_onboard_date,
    log_activity,
    merge_address,
    require_master_admin,
)


router = APIRouter()


# ───────────── /pulse-stats — fleet rollup ─────────────

async def _collect_org_site_stats(org: dict) -> dict:
    """Collect stats for a single Pulse organization."""
    org_id = org["id"]
    user_count = await db.users.count_documents({"organization_id": org_id})
    equip_count = await db.equipment.count_documents({"organization_id": org_id})
    issue_count = await db.issues.count_documents({"organization_id": org_id})
    open_count = await db.issues.count_documents({"organization_id": org_id, "status": "open"})
    resolved_count = await db.issues.count_documents({"organization_id": org_id, "status": {"$in": ["resolved", "closed"]}})
    file_count = await db.files.count_documents({"organization_id": org_id})
    owner = await db.users.find_one({"organization_id": org_id, "role": "owner"}, {"_id": 0, "email": 1, "full_name": 1, "last_login": 1})
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recent_faults = await db.issues.count_documents({"organization_id": org_id, "created_at": {"$gte": thirty_days_ago}})
    price = 79 if org.get("account_type") == "pulse_pro" else 29

    return {
        "id": org_id, "name": org["name"], "account_type": org.get("account_type", "lite"),
        "status": org.get("status", "active"), "subscription_tier": org.get("subscription_tier", "free"),
        "user_count": user_count, "equipment_count": equip_count,
        "total_faults": issue_count, "open_faults": open_count, "resolved_faults": resolved_count,
        "recent_faults_30d": recent_faults, "file_count": file_count, "monthly_cost": price,
        "owner_email": (owner or {}).get("email", ""), "owner_name": (owner or {}).get("full_name", ""),
        "last_owner_login": (owner or {}).get("last_login", ""), "created_at": org.get("created_at", ""),
    }


def _aggregate_pulse_totals(sites: list) -> dict:
    """Sum the 5 counter fields across all site dicts."""
    keys = ("user_count", "equipment_count", "total_faults", "open_faults", "file_count")
    return {k: sum(s.get(k, 0) for s in sites) for k in keys}


@router.get("/master-admin/pulse-stats")
async def get_pulse_stats(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    pulse_orgs = await db.organizations.find({"account_type": {"$in": ["lite", "pulse_pro"]}}, {"_id": 0}).to_list(500)

    sites = [await _collect_org_site_stats(org) for org in pulse_orgs]
    lite_count = sum(1 for s in sites if s["account_type"] == "lite")
    pro_count = sum(1 for s in sites if s["account_type"] == "pulse_pro")
    totals = _aggregate_pulse_totals(sites)

    return {
        "total_sites": len(sites), "lite_sites": lite_count, "pro_sites": pro_count,
        "total_users": totals["user_count"],
        "total_equipment": totals["equipment_count"],
        "total_faults": totals["total_faults"],
        "open_faults": totals["open_faults"],
        "total_files": totals["file_count"],
        "mrr": (lite_count * 29) + (pro_count * 79),
        "sites": sites,
    }


# ─── Pulse Fitness Standard Equipment Kits ───
PULSE_EQUIPMENT_KITS = {
    "cardio_starter": {
        "name": "Cardio Starter Kit",
        "items": [
            {"name": "Treadmill", "equipment_type": "Treadmill", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Cross Trainer", "equipment_type": "Cross Trainer", "manufacturer": "Pulse Fitness", "quantity": 3},
            {"name": "Exercise Bike", "equipment_type": "Exercise Bike", "manufacturer": "Pulse Fitness", "quantity": 3},
            {"name": "Rowing Machine", "equipment_type": "Rowing Machine", "manufacturer": "Pulse Fitness", "quantity": 2},
        ],
    },
    "cardio_full": {
        "name": "Cardio Full Kit",
        "items": [
            {"name": "Treadmill", "equipment_type": "Treadmill", "manufacturer": "Pulse Fitness", "quantity": 8},
            {"name": "Cross Trainer", "equipment_type": "Cross Trainer", "manufacturer": "Pulse Fitness", "quantity": 5},
            {"name": "Exercise Bike", "equipment_type": "Exercise Bike", "manufacturer": "Pulse Fitness", "quantity": 5},
            {"name": "Spin Bike", "equipment_type": "Spin Bike", "manufacturer": "Pulse Fitness", "quantity": 6},
            {"name": "Rowing Machine", "equipment_type": "Rowing Machine", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Stairclimber", "equipment_type": "Stairclimber", "manufacturer": "Pulse Fitness", "quantity": 2},
        ],
    },
    "strength_starter": {
        "name": "Strength Starter Kit",
        "items": [
            {"name": "Cable Machine", "equipment_type": "Cable Machine", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Smith Machine", "equipment_type": "Smith Machine", "manufacturer": "Pulse Fitness", "quantity": 1},
            {"name": "Leg Press", "equipment_type": "Leg Press", "manufacturer": "Pulse Fitness", "quantity": 1},
            {"name": "Chest Press", "equipment_type": "Chest Press", "manufacturer": "Pulse Fitness", "quantity": 1},
            {"name": "Lat Pulldown", "equipment_type": "Lat Pulldown", "manufacturer": "Pulse Fitness", "quantity": 1},
            {"name": "Bench", "equipment_type": "Bench", "manufacturer": "Pulse Fitness", "quantity": 3},
        ],
    },
    "strength_full": {
        "name": "Strength Full Kit",
        "items": [
            {"name": "Cable Machine", "equipment_type": "Cable Machine", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Smith Machine", "equipment_type": "Smith Machine", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Leg Press", "equipment_type": "Leg Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Chest Press", "equipment_type": "Chest Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Shoulder Press", "equipment_type": "Shoulder Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Lat Pulldown", "equipment_type": "Lat Pulldown", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Functional Trainer", "equipment_type": "Functional Trainer", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Power Rack", "equipment_type": "Power Rack", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Bench", "equipment_type": "Bench", "manufacturer": "Pulse Fitness", "quantity": 6},
        ],
    },
    "complete_gym": {
        "name": "Complete Gym Package",
        "items": [
            {"name": "Treadmill", "equipment_type": "Treadmill", "manufacturer": "Pulse Fitness", "quantity": 8},
            {"name": "Cross Trainer", "equipment_type": "Cross Trainer", "manufacturer": "Pulse Fitness", "quantity": 5},
            {"name": "Exercise Bike", "equipment_type": "Exercise Bike", "manufacturer": "Pulse Fitness", "quantity": 5},
            {"name": "Spin Bike", "equipment_type": "Spin Bike", "manufacturer": "Pulse Fitness", "quantity": 6},
            {"name": "Rowing Machine", "equipment_type": "Rowing Machine", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Stairclimber", "equipment_type": "Stairclimber", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Cable Machine", "equipment_type": "Cable Machine", "manufacturer": "Pulse Fitness", "quantity": 4},
            {"name": "Smith Machine", "equipment_type": "Smith Machine", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Leg Press", "equipment_type": "Leg Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Chest Press", "equipment_type": "Chest Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Shoulder Press", "equipment_type": "Shoulder Press", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Lat Pulldown", "equipment_type": "Lat Pulldown", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Functional Trainer", "equipment_type": "Functional Trainer", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Power Rack", "equipment_type": "Power Rack", "manufacturer": "Pulse Fitness", "quantity": 2},
            {"name": "Bench", "equipment_type": "Bench", "manufacturer": "Pulse Fitness", "quantity": 6},
        ],
    },
}


@router.get("/master-admin/pulse-equipment-kits")
async def get_pulse_equipment_kits(user: dict = Depends(get_current_user)):
    require_master_admin(user)
    kits = {}
    for kit_id, kit in PULSE_EQUIPMENT_KITS.items():
        total = sum(i["quantity"] for i in kit["items"])
        kits[kit_id] = {"name": kit["name"], "total_items": total, "items": kit["items"]}
    return {"kits": kits}


# ───────────── /onboard-pulse-site — multi-step onboarding ─────────────

async def _create_onboard_users(data: dict, config: dict) -> list[dict]:
    """Create owner + additional users for the onboarded site.
    config keys: org_id, owner_id, owner_email, owner_name, owner_password, now, account_type
    """
    org_id = config["org_id"]
    owner_doc = {
        "id": config["owner_id"], "email": config["owner_email"],
        "password": _hash_password(config["owner_password"]), "full_name": config["owner_name"],
        "organization_id": org_id, "role": "owner", "account_type": config["account_type"],
        "created_at": config["now"],
    }
    await db.users.insert_one(owner_doc)
    created = [{"id": config["owner_id"], "email": config["owner_email"], "name": config["owner_name"], "role": "owner"}]

    for u in data.get("users", []):
        u_email = u.get("email", "").strip().lower()
        u_name = u.get("name", "").strip()
        u_password = u.get("password", "").strip()
        if not u_email or not u_name or not u_password:
            continue
        if await db.users.find_one({"email": u_email}, {"_id": 0, "id": 1}):
            continue
        u_id = str(uuid.uuid4())
        u_role = u.get("role", "staff")
        user_doc = {
            "id": u_id, "email": u_email,
            "password": _hash_password(u_password), "full_name": u_name,
            "organization_id": org_id,
            "role": u_role if u_role in ("manager", "staff") else "staff",
            "account_type": config["account_type"], "created_at": config["now"],
        }
        await db.users.insert_one(user_doc)
        created.append({"id": u_id, "email": u_email, "name": u_name, "role": user_doc["role"]})
    return created


async def _create_kit_equipment(kit: dict, org_id: str, owner_id: str, location: str, now: str, site_id: str | None = None) -> int:
    """Create equipment from a predefined kit. Returns count created."""
    count = 0
    for item in kit["items"]:
        for i in range(item["quantity"]):
            equip_doc = {
                "id": str(uuid.uuid4()), "user_id": owner_id, "organization_id": org_id,
                "name": f"{item['name']} {i+1}" if item["quantity"] > 1 else item["name"],
                "equipment_type": item["equipment_type"],
                "manufacturer": item.get("manufacturer", "Pulse Fitness"),
                "model": item.get("model"), "serial_number": None,
                "location": location,
                "manuals": [], "photos": [], "created_at": now, "updated_at": now,
                **({"site_id": site_id} if site_id else {}),
            }
            await db.equipment.insert_one(equip_doc)
            count += 1
    return count


async def _create_manual_equipment(eq_list: list, org_id: str, owner_id: str, default_location: str, now: str, site_id: str | None = None) -> int:
    """Create equipment from a manual list. Returns count created."""
    count = 0
    for eq in eq_list:
        eq_name = eq.get("name", "").strip()
        eq_type = eq.get("equipment_type", "").strip()
        if not eq_name or not eq_type:
            continue
        equip_doc = {
            "id": str(uuid.uuid4()), "user_id": owner_id, "organization_id": org_id,
            "name": eq_name, "equipment_type": eq_type,
            "manufacturer": eq.get("manufacturer", "Pulse Fitness"), "model": eq.get("model"),
            "serial_number": eq.get("serial_number"),
            "location": eq.get("location", default_location),
            "purchase_date": _parse_onboard_date(eq.get("install_date") or eq.get("purchase_date") or ""),
            "purchase_price": eq.get("unit_price", 0),
            "warranty_expiry": _parse_onboard_date(eq.get("warranty_expiry", "")),
            "warranty_code": eq.get("warranty_code", ""),
            "sla_level": eq.get("sla_name", "") or eq.get("sla_level", ""),
            "status": "operational", "condition": "excellent",
            "manuals": [], "photos": [], "created_at": now, "updated_at": now,
            **({"site_id": site_id} if site_id else {}),
        }
        await db.equipment.insert_one(equip_doc)
        count += 1
    return count


async def _create_onboard_equipment(data: dict, org_id: str, owner_id: str, now: str, site_id: str | None = None) -> int:
    """Create equipment from kit and/or manual list. Returns count created."""
    count = 0
    default_location = data.get("default_location", "Main Floor")
    equipment_kit = data.get("equipment_kit")
    if equipment_kit and equipment_kit in PULSE_EQUIPMENT_KITS:
        count += await _create_kit_equipment(PULSE_EQUIPMENT_KITS[equipment_kit], org_id, owner_id, default_location, now, site_id)
    count += await _create_manual_equipment(data.get("equipment", []), org_id, owner_id, default_location, now, site_id)
    return count


async def _validate_onboard_data(data: dict) -> tuple[str, str, str, str, str]:
    """Validate and extract onboarding data. Returns (site_name, tier, email, name, password)."""
    site_name = data.get("site_name", "").strip()
    tier = data.get("tier", "lite")
    if tier not in ("lite", "pro"):
        raise HTTPException(status_code=400, detail="Tier must be 'lite' or 'pro'")
    if not site_name:
        raise HTTPException(status_code=400, detail="Site name is required")
    email = data.get("owner_email", "").strip().lower()
    name = data.get("owner_name", "").strip()
    password = data.get("owner_password", "").strip()
    if not email or not name or not password:
        raise HTTPException(status_code=400, detail="Owner email, name, and password are required")
    if await db.users.find_one({"email": email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Email {email} already in use")
    return site_name, tier, email, name, password


@router.post("/master-admin/onboard-pulse-site")
async def onboard_pulse_site(data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    """Full Pulse Fitness site onboarding."""
    require_master_admin(user)
    site_name, tier, owner_email, owner_name, owner_password = await _validate_onboard_data(data)

    org_id, owner_id = str(uuid.uuid4()), str(uuid.uuid4())
    company_code = str(uuid.uuid4())[:8].upper()
    account_type = f"pulse_{tier}"
    now = datetime.now(timezone.utc).isoformat()

    # Iter 215en — accept the structured 8-field address alongside the
    # legacy single-line `address`. We auto-compose the legacy field so
    # downstream Sage / Sicon outboxes keep working unchanged.
    org_addr = merge_address(data)
    site_addr = merge_address({**data, "address": data.get("site_address") or data.get("address", "")})

    await db.organizations.insert_one({
        "id": org_id, "name": site_name, "company_code": company_code, "owner_id": owner_id,
        "created_at": now, "subscription_tier": tier, "account_type": account_type,
        "address": org_addr["address"],
        "address_line1": org_addr["address_line1"],
        "address_line2": org_addr["address_line2"],
        "address_line3": org_addr["address_line3"],
        "city": org_addr["city"],
        "county": org_addr["county"],
        "postcode": org_addr["postcode"],
        "country": org_addr["country"],
        "contact_person": owner_name, "email": owner_email,
        "phone": data.get("phone", ""), "branding": {"primary_color": "#66ccff", "company_name": "Pulse Fitness"},
    })

    site_id = str(uuid.uuid4())
    await db.sites.insert_one({
        "id": site_id, "organization_id": org_id,
        "name": data.get("site_address_name", site_name),
        "address": site_addr["address"],
        "address_line1": site_addr["address_line1"],
        "address_line2": site_addr["address_line2"],
        "address_line3": site_addr["address_line3"],
        "city": site_addr["city"],
        "county": site_addr["county"],
        "postcode": site_addr["postcode"],
        "country": site_addr["country"],
        "created_at": now,
    })

    created_users = await _create_onboard_users(data, {
        "org_id": org_id, "owner_id": owner_id, "owner_email": owner_email,
        "owner_name": owner_name, "owner_password": owner_password,
        "now": now, "account_type": account_type,
    })
    created_equipment = await _create_onboard_equipment(data, org_id, owner_id, now, site_id)

    await log_activity("pulse_site_onboarded", f"Onboarded Pulse {tier.upper()} site: {site_name}", user.get("email", ""), "organization", org_id)
    return {
        "success": True,
        "organization": {"id": org_id, "name": site_name, "company_code": company_code, "tier": tier, "account_type": account_type},
        "site": {"id": site_id, "name": data.get("site_address_name", site_name)},
        "users": created_users, "equipment_count": created_equipment,
    }
