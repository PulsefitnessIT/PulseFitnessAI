"""Iter 216h119 — One-click demo equipment seeder for MOD sites.

When the sales team bulk-imports a new MOD HQ for a live demo, every
child site is created with zero equipment. The estate overview then
shows a wall of "0 eq" pills which makes the demo look hollow. This
endpoint seeds a realistic 8-machine fleet (treadmills, rowers, bikes,
strength kit from Life Fitness / Concept 2 / Pulse Fitness / Technogym)
plus a sprinkle of historic faults into every empty `mod_site` under a
nominated parent HQ / branch.

Endpoint
────────
POST /api/master-admin/mod/populate-demo-equipment
     ?parent_org_id=...              # required — mod_org or mod_branch
     &machines_per_site=8            # 1-20 (default 8)
     &include_faults=true            # seeds 0-7 historic faults per machine

The endpoint is idempotent: sites that already have any equipment with
`imported_via=mod_demo_seed` are skipped. To re-seed a site, delete its
demo equipment first.

Authorisation: master admin only.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from routes.master_admin import require_master_admin
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


# Same fleet as the Demo Garrison demo so the visual matches the
# already-prepared sales narrative. Tuple: (display name, type,
# manufacturer, model, age in years, faults logged in last 12 months).
DEMO_MACHINES = [
    ("Treadmill — Life Fitness Integrity", "Treadmill", "Life Fitness", "Integrity X", 3, 0),
    ("Treadmill — Life Fitness Integrity", "Treadmill", "Life Fitness", "Integrity X", 8, 5),
    ("Rower — Concept2 RowErg",            "Rower",     "Concept 2",    "RowErg",     2, 0),
    ("Rower — Concept2 RowErg",            "Rower",     "Concept 2",    "RowErg",     6, 1),
    ("Bike — Wattbike Atom",               "Bike",      "Wattbike",     "Atom",       4, 2),
    ("Cable Cross — Technogym Selection",  "Strength",  "Technogym",    "Selection",  9, 4),
    ("Smith Machine — Pulse 350g",         "Strength",  "Pulse Fitness", "350g Smith", 10, 7),
    ("Functional Trainer — Pulse FT100",   "Strength",  "Pulse Fitness", "FT100",      5, 1),
]
DEMO_FAULT_TYPES = ["mechanical", "electrical", "wear", "safety", "cosmetic"]
REPLACEMENT_COST = {"Treadmill": 5500, "Rower": 1200, "Bike": 2800, "Strength": 4800}


async def _seed_site(
    site: dict,
    *,
    machines: int,
    include_faults: bool,
    now_dt: datetime,
) -> tuple[int, int]:
    """Insert `machines` × demo equipment + (optionally) faults for one site.

    Returns (equipment_created, faults_created).
    """
    site_id = site["id"]
    # Idempotent — never seed twice.
    existing = await db.equipment.count_documents({
        "organization_id": site_id, "imported_via": "mod_demo_seed",
    })
    if existing:
        return 0, 0

    eq_created = 0
    fa_created = 0
    fleet = DEMO_MACHINES[:max(1, min(machines, len(DEMO_MACHINES)))]
    now_iso = now_dt.isoformat()
    for idx, (name, etype, mfr, model, age_yrs, faults_12mo) in enumerate(fleet):
        purchase_iso = (now_dt - timedelta(days=int(age_yrs * 365))).isoformat()
        eq_id = str(uuid.uuid4())
        cost = REPLACEMENT_COST.get(etype, 3000)
        await db.equipment.insert_one({
            "id": eq_id,
            "organization_id": site_id,
            "name": name,
            "equipment_type": etype,
            "manufacturer": mfr,
            "model": model,
            "serial_number": f"{mfr[:3].upper()}-{site_id[:4].upper()}-{idx:03d}",
            "purchase_date": purchase_iso,
            "purchase_price": cost,
            "replacement_cost": cost,
            "status": "active" if faults_12mo < 6 else "out_of_service",
            "supplier": mfr,
            "created_at": now_iso,
            "imported_via": "mod_demo_seed",
        })
        eq_created += 1
        if not include_faults:
            continue
        for j in range(faults_12mo):
            offset_days = int((j + 1) * (365 / max(faults_12mo + 1, 1)))
            created_at = now_dt - timedelta(days=offset_days)
            ft = DEMO_FAULT_TYPES[j % len(DEMO_FAULT_TYPES)]
            await db.issues.insert_one({
                "id": str(uuid.uuid4()),
                "organization_id": site_id,
                "equipment_id": eq_id,
                "fault_type_mod": ft,
                "issue_description": f"Demo fault — {ft} reported at {site.get('name', 'site')}",
                "status": "closed" if offset_days > 30 else "open",
                "priority": "urgent" if ft == "safety" and j == 0 else "high" if j < 2 else "normal",
                "severity": "urgent" if ft == "safety" and j == 0 else "high" if j < 2 else "normal",
                "reporter_name": "Demo seed",
                "reporter_email": "demo@army.mod.local",
                "created_at": created_at.isoformat(),
                "imported_via": "mod_demo_seed",
            })
            fa_created += 1
    return eq_created, fa_created


@router.post("/master-admin/mod/populate-demo-equipment")
async def populate_demo_equipment(
    parent_org_id: str = Query(..., description="MOD parent — mod_org OR mod_branch"),
    machines_per_site: int = Query(8, ge=1, le=20),
    include_faults: bool = Query(True),
    user: dict = Depends(get_current_user),
) -> dict:
    """Seed demo equipment + faults into every empty MOD child site
    sharing `parent_org_id`'s `mod_root_id`. Idempotent."""
    require_master_admin(user)
    parent = await db.organizations.find_one(
        {"id": parent_org_id},
        {"_id": 0, "id": 1, "name": 1, "account_type": 1, "mod_root_id": 1, "mod_branch": 1},
    )
    if not parent:
        raise HTTPException(404, "Parent organisation not found")
    if parent.get("account_type") not in {"mod_org", "mod_branch"}:
        raise HTTPException(400, "Parent must be a MOD HQ (mod_org) or branch (mod_branch)")

    mod_root_id = parent.get("mod_root_id") or parent.get("id")
    site_query: dict = {
        "account_type": "mod_site",
        "mod_root_id": mod_root_id,
    }
    # Branch tier — scope to its own branch only.
    if parent["account_type"] == "mod_branch" and parent.get("mod_branch"):
        site_query["mod_branch"] = parent["mod_branch"]

    sites_cursor = db.organizations.find(
        site_query, {"_id": 0, "id": 1, "name": 1},
    )

    now_dt = datetime.now(timezone.utc)
    total_sites = 0
    skipped = 0
    eq_total = 0
    fa_total = 0
    per_site: list[dict] = []
    async for site in sites_cursor:
        total_sites += 1
        eq, fa = await _seed_site(
            site, machines=machines_per_site,
            include_faults=include_faults, now_dt=now_dt,
        )
        if eq == 0:
            skipped += 1
        else:
            eq_total += eq
            fa_total += fa
            per_site.append({"site_id": site["id"], "site_name": site.get("name"),
                             "equipment": eq, "faults": fa})

    return {
        "ok": True,
        "parent_org": {"id": parent_org_id, "name": parent.get("name"),
                       "type": parent["account_type"]},
        "scanned_sites": total_sites,
        "seeded_sites": total_sites - skipped,
        "skipped_already_seeded": skipped,
        "equipment_created": eq_total,
        "faults_created": fa_total,
        "per_site": per_site[:50],
    }


__all__ = ["router"]
