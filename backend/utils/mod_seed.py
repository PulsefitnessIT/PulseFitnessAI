"""One-shot MOD demo seed — idempotent.

Creates the full MOD hierarchy so the portal is demo-able out of the box:

  • 1 root `mod_org`         — Ministry of Defence
  • 3 `mod_branch` orgs      — Army / Navy / RAF (for division-level PRO)
  • 3 `mod_site` orgs        — one per branch, each with 5 staff + 12 equip

Login convention:

  • Site-tier (LITE)     — kebab-case username (e.g. `raf-brizenorton`),
                           NO email. Shared per-site credential.
  • Division-tier (PRO)  — proper email (`raf@mod.gov.uk`, etc.) so the
                           branch-facilities officer can oversee all sites
                           in their branch.
  • Organisation-tier    — `modestates@mod.gov.uk` (bonus demo account) —
                           sees every site across all branches.

Runs at server startup via `server.py` — safe to call repeatedly.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from passlib.context import CryptContext

from utils.database import db

logger = logging.getLogger(__name__)

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


MOD_ORG_ID = "mod-root-uk"


SITES = [
    {
        "code": "raf-brizenorton",          # ← also the login username (no @)
        "branch": "RAF",
        "name": "RAF Brize Norton Gym",
        "password": "BrizeNorton2026!",
        "address": "RAF Brize Norton, Carterton OX18 3LX",
        "access_notes": "Sign in at Main Gate. Escort required past barrier. PTI office is at the rear of the cardio hall.",
        "escort_required": True,
        "oncall_phone": "+44 7700 900110",
        "staff": [
            ("Sgt J Hughes",   "PTI",           "j.hughes@mod.gov.uk",   "+44 7700 900111"),
            ("Cpl L Baker",    "Duty Manager",  "l.baker@mod.gov.uk",    "+44 7700 900112"),
            ("Lt R Owen",      "Ops Officer",   "r.owen@mod.gov.uk",     "+44 7700 900113"),
            ("Fl Lt A Patel",  "Facilities",    "a.patel@mod.gov.uk",    "+44 7700 900114"),
            ("FS D Mitchell",  "Gym Corporal",  "d.mitchell@mod.gov.uk", "+44 7700 900115"),
        ],
    },
    {
        "code": "army-catterick",
        "branch": "Army",
        "name": "Catterick Garrison Gym",
        "password": "Catterick2026!",
        "address": "Catterick Garrison, Richmond DL9 3LR",
        "access_notes": "Main gate pass required. Parking behind Somme Barracks.",
        "escort_required": False,
        "oncall_phone": "+44 7700 900210",
        "staff": [
            ("Sgt M Khan",     "PTI",           "m.khan@army.mod.gov.uk",  "+44 7700 900211"),
            ("Cpl S Walsh",    "Duty Manager",  "s.walsh@army.mod.gov.uk", "+44 7700 900212"),
            ("WO2 E Clarke",   "Gym SNCO",      "e.clarke@army.mod.gov.uk","+44 7700 900213"),
            ("Pte K Moss",     "PTI Assistant", "k.moss@army.mod.gov.uk",  "+44 7700 900214"),
            ("Maj T Greene",   "CO Rep",        "t.greene@army.mod.gov.uk","+44 7700 900215"),
        ],
    },
    {
        "code": "navy-raleigh",
        "branch": "Navy",
        "name": "HMS Raleigh Gym",
        "password": "Raleigh2026!",
        "address": "HMS Raleigh, Torpoint, Cornwall PL11 2PD",
        "access_notes": "Main gate, visitor pass from Guard Room. Gym is building 4A.",
        "escort_required": True,
        "oncall_phone": "+44 7700 900310",
        "staff": [
            ("CPO N Shaw",     "Chief PTI",     "n.shaw@royalnavy.mod.uk",  "+44 7700 900311"),
            ("PO R Davies",    "Duty Manager",  "r.davies@royalnavy.mod.uk","+44 7700 900312"),
            ("Lt G Abiola",    "Training Ofc",  "g.abiola@royalnavy.mod.uk","+44 7700 900313"),
            ("Lt Cdr H Reilly","Base Facilities","h.reilly@royalnavy.mod.uk","+44 7700 900314"),
            ("AB J Lane",      "PTI Assistant", "j.lane@royalnavy.mod.uk",  "+44 7700 900315"),
        ],
    },
]


# Division-tier (branch PRO) and organisation-tier oversight accounts.
# These ARE real email-based logins — the user typed them on the question.
BRANCH_PRO_USERS = [
    {
        "branch": "RAF",
        "email": "raf@mod.gov.uk",
        "password": "RafEstates2026!",
        "full_name": "RAF Estates Facilities",
    },
    {
        "branch": "Army",
        "email": "army@mod.gov.uk",
        "password": "ArmyEstates2026!",
        "full_name": "Army Estates Facilities",
    },
    {
        "branch": "Navy",
        "email": "navy@mod.gov.uk",
        "password": "NavyEstates2026!",
        "full_name": "Navy Estates Facilities",
    },
]

ORG_PRO_USER = {
    "email": "modestates@mod.gov.uk",
    "password": "ModEstates2026!",
    "full_name": "MOD Estates — Head of PT",
}


EQUIPMENT_SEED = [
    ("Treadmill TM-01", "Treadmill",     "Life Fitness", "95T"),
    ("Treadmill TM-02", "Treadmill",     "Life Fitness", "95T"),
    ("Treadmill TM-03", "Treadmill",     "Life Fitness", "95T"),
    ("Rower RB-01",     "Rower",         "Concept 2",    "RowErg"),
    ("Rower RB-02",     "Rower",         "Concept 2",    "RowErg"),
    ("Bike UB-01",      "Upright Bike",  "Technogym",    "Artis Bike"),
    ("Bike UB-02",      "Upright Bike",  "Technogym",    "Artis Bike"),
    ("Elliptical EL-01","Elliptical",    "Precor",       "EFX 885"),
    ("Elliptical EL-02","Elliptical",    "Precor",       "EFX 885"),
    ("Smith ST-01",     "Smith Machine", "Hammer Strength","HDSM"),
    ("Cable CBL-01",    "Cable Stack",   "Matrix",       "G3 S40"),
    ("Bench BP-01",     "Bench Press",   "Rogue Fitness","Monster Utility"),
]


async def seed_mod_demo() -> None:
    """Create/ensure the MOD demo tree exists. Idempotent."""
    if os.environ.get("MOD_DEMO_SEED_DISABLED", "").lower() in {"1", "true", "yes"}:
        return

    now = datetime.now(timezone.utc).isoformat()

    # Cleanup pass: remove any legacy MOD site orgs that used the old
    # `foo.bar` dot-code convention before we switched to kebab-case.
    # We detect them by site_code containing a '.' and cascade-delete the
    # tied users / staff / equipment so branch PRO totals stay accurate.
    await _cleanup_legacy_mod_sites()

    # 1) Root organisation
    existing_root = await db.organizations.find_one({"id": MOD_ORG_ID})
    if not existing_root:
        await db.organizations.insert_one({
            "id": MOD_ORG_ID,
            "name": "Ministry of Defence",
            "account_type": "mod_org",
            "is_mod_root": True,
            "mod_root_id": MOD_ORG_ID,
            "created_at": now,
            "subscription_tier": "pro",
        })
        logger.info("MOD demo: created root organisation")

    # 2) Branch organisations (one per branch) for division-tier PRO users.
    for branch in ("Army", "Navy", "RAF"):
        branch_id = f"mod-branch-{branch.lower()}"
        if not await db.organizations.find_one({"id": branch_id}):
            await db.organizations.insert_one({
                "id": branch_id,
                "name": f"{branch} Estates",
                "account_type": "mod_branch",
                "mod_root_id": MOD_ORG_ID,
                "mod_branch": branch,
                "subscription_tier": "pro",
                "created_at": now,
            })

    # 3) Per-site orgs + logins + staff + equipment
    for site in SITES:
        site_id = f"mod-site-{site['code']}"
        if await db.organizations.find_one({"id": site_id}):
            # Migrate any pre-existing email-based site login to the new
            # kebab-case username scheme so old tokens keep working while
            # new users get the clean no-@ login.
            await _migrate_site_login_to_username(site_id, site)
            continue
        await db.organizations.insert_one({
            "id": site_id,
            "name": site["name"],
            "account_type": "mod_site",
            "mod_root_id": MOD_ORG_ID,
            "mod_branch": site["branch"],
            "site_code": site["code"],
            "address": site["address"],
            "access_notes": site["access_notes"],
            "escort_required": site["escort_required"],
            "oncall_phone": site["oncall_phone"],
            "subscription_tier": "lite",
            "created_at": now,
        })

        # Login user — username-based (no email). Internal synthetic email
        # is stored for audit-log continuity but the user never types it.
        synthetic_email = f"{site['code']}@site.mod.local"
        await db.users.insert_one({
            "id": f"mod-user-{site['code']}",
            "username": site["code"],          # ← what they actually type
            "email": synthetic_email,          # audit-only
            "password": pwd_ctx.hash(site["password"]),
            "full_name": site["name"],
            "organization_id": site_id,
            "role": "owner",
            "account_type": "mod_site",
            "mod_site_code": site["code"],
            "is_username_login": True,
            "created_at": now,
            "password_updated_at": now,
        })

        # Staff
        for name, role, email, phone in site["staff"]:
            await db.mod_site_staff.insert_one({
                "id": str(uuid.uuid4()),
                "site_id": site_id,
                "name": name, "role": role, "email": email,
                "email_lc": email.lower(),
                "phone": phone,
                "is_active": True, "fault_count": 0, "last_reported_at": None,
                "created_at": now, "updated_at": now,
            })

        # Equipment
        for idx, (ename, etype, manu, model) in enumerate(EQUIPMENT_SEED):
            await db.equipment.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": site_id,
                "name": ename,
                "machine_type": etype,
                "category": etype,
                "manufacturer": manu,
                "model_number": model,
                "serial_number": f"{site['code'].upper().replace('-', '.')}-{etype[:2].upper()}-{idx:03d}",
                "status": "working",
                "location": f"{site['name']} · Main Hall",
                "last_checked_at": now,
                "created_at": now,
            })
        logger.info("MOD demo: seeded site %s", site["name"])

    # 4) Branch PRO users (division oversight — real email-based logins).
    for bp in BRANCH_PRO_USERS:
        branch_id = f"mod-branch-{bp['branch'].lower()}"
        if await db.users.find_one({"email": bp["email"].lower()}):
            continue
        await db.users.insert_one({
            "id": f"mod-pro-{bp['branch'].lower()}",
            "email": bp["email"].lower(),
            "password": pwd_ctx.hash(bp["password"]),
            "full_name": bp["full_name"],
            "organization_id": branch_id,
            "role": "owner",
            "account_type": "mod_branch",
            "mod_branch": bp["branch"],
            "created_at": now,
            "password_updated_at": now,
        })
        logger.info("MOD demo: seeded branch PRO user %s", bp["email"])

    # 5) Organisation-level PRO user (whole-estate view).
    if not await db.users.find_one({"email": ORG_PRO_USER["email"].lower()}):
        await db.users.insert_one({
            "id": "mod-pro-estates",
            "email": ORG_PRO_USER["email"].lower(),
            "password": pwd_ctx.hash(ORG_PRO_USER["password"]),
            "full_name": ORG_PRO_USER["full_name"],
            "organization_id": MOD_ORG_ID,
            "role": "owner",
            "account_type": "mod_org",
            "created_at": now,
            "password_updated_at": now,
        })
        logger.info("MOD demo: seeded organisation PRO user %s", ORG_PRO_USER["email"])


async def _cleanup_legacy_mod_sites() -> None:
    """One-shot: delete MOD site orgs + users + staff + equipment that were
    seeded under the old `raf.brizenorton`-style dot convention."""
    legacy_sites = await db.organizations.find(
        {"account_type": "mod_site", "site_code": {"$regex": r"\."}},
        {"_id": 0, "id": 1, "site_code": 1},
    ).to_list(50)
    if not legacy_sites:
        return
    for ls in legacy_sites:
        sid = ls["id"]
        await db.users.delete_many({"organization_id": sid})
        await db.mod_site_staff.delete_many({"site_id": sid})
        await db.equipment.delete_many({"organization_id": sid})
        await db.issues.delete_many({"organization_id": sid})
        await db.mod_audit_log.delete_many({"site_id": sid})
        await db.organizations.delete_one({"id": sid})
        logger.info("MOD demo: purged legacy site %s", ls.get("site_code"))


async def _migrate_site_login_to_username(site_id: str, site: dict) -> None:
    """Flip existing email-based MOD site user to the new username scheme."""
    # Only touch users tied to this MOD site
    existing = await db.users.find_one({"organization_id": site_id, "account_type": "mod_site"})
    if not existing:
        return
    needs_update = (
        existing.get("username") != site["code"]
        or not existing.get("is_username_login")
    )
    if not needs_update:
        return
    synthetic_email = f"{site['code']}@site.mod.local"
    await db.users.update_one(
        {"id": existing["id"]},
        {"$set": {
            "username": site["code"],
            "email": synthetic_email,
            "is_username_login": True,
            "mod_site_code": site["code"],
        }},
    )
    logger.info("MOD demo: migrated site login %s → %s", existing.get("email"), site["code"])


async def ensure_mod_indexes() -> None:
    await db.mod_site_staff.create_index([("site_id", 1), ("last_reported_at", -1)])
    await db.mod_site_staff.create_index([("site_id", 1), ("email_lc", 1)], unique=False)
    await db.mod_audit_log.create_index([("site_id", 1), ("created_at", -1)])
    await db.issues.create_index([("mod_site_id", 1), ("status", 1), ("created_at", -1)])
    await db.issues.create_index([("organization_id", 1), ("equipment_id", 1), ("created_at", -1)])
    await db.organizations.create_index([("account_type", 1), ("mod_root_id", 1)])
    # Sparse unique on username so multiple NULLs don't collide.
    await db.users.create_index(
        [("username", 1)],
        unique=True,
        partialFilterExpression={"username": {"$type": "string"}},
    )
