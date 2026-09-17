"""One-off importer: company fleet register spreadsheet -> db.vehicles.

Imports the Pulse Fitness Ltd fleet (from "Reg Company Cars Fuel Cards 2025.xlsx")
into the vehicle register, matching drivers to existing staff_members by name.
Idempotent: skips a registration that already exists (active) for the org.

Run:  cd /app/backend && set -a && . ./.env && set +a && python3 scripts/import_fleet_pulse_ltd.py /tmp/fleet.xlsx
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import openpyxl
from motor.motor_asyncio import AsyncIOMotorClient

ORG_ID = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"  # Pulse Fitness Ltd

VAN_KW = ("vivaro", "transit", "sprinter", "master", "dispatch", "expert", "caddy", "lcv")
LORRY_KW = ("18t", "17.5t")
NON_DRIVER = ("pool car", "pool van", "leased", "install", "pulse owned", "n/a", "")


def _iso(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    s = str(v).strip()
    return "" if s.lower() in ("n/a", "na", "") else s


def _clean(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("n/a", "na") else s


def classify(make, mtype):
    blob = f"{make} {mtype}".lower()
    if any(k in blob for k in LORRY_KW):
        return "lorry"
    if any(k in blob for k in VAN_KW):
        return "van"
    return "car"


def powertrain(make, mtype):
    blob = f"{make} {mtype}".lower()
    is_ev = ("tesla" in blob or "e-tron" in blob or "byd" in blob
             or "edrive" in blob or "e-drive" in blob)
    is_hybrid = any(k in blob for k in ("hybrid", "p300e", "p270e", "p460e",
                                        "ehybrid", "tfsi e", "e-hybrid", "phev"))
    return is_ev, is_hybrid


async def main(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))

    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    staff = await db.staff_members.find(
        {"organization_id": ORG_ID}, {"_id": 0, "id": 1, "full_name": 1}).to_list(5000)
    by_name = {(s.get("full_name") or "").strip().lower(): s["id"] for s in staff if s.get("full_name")}

    existing = set()
    async for v in db.vehicles.find({"organization_id": ORG_ID}, {"_id": 0, "reg_no": 1}):
        existing.add((v.get("reg_no") or "").strip().upper())

    department = "Management"  # top group has no header row
    created, skipped, unmatched = 0, 0, []
    now = datetime.now(timezone.utc).isoformat()

    for i, r in enumerate(rows):
        if i < 4:  # header rows
            continue
        model = _clean(r[0]) if len(r) > 0 else ""
        mtype = _clean(r[1]) if len(r) > 1 else ""
        reg = _clean(r[2]).upper() if len(r) > 2 else ""
        driver = _clean(r[3]) if len(r) > 3 else ""
        lease_company = _clean(r[4]) if len(r) > 4 else ""
        lease_end = _iso(r[6]) if len(r) > 6 else ""
        fuel_card = _clean(r[7]) if len(r) > 7 else ""
        mot_due = _iso(r[11]) if len(r) > 11 else ""

        # Section header row (a department name with no registration).
        if model and not reg and not mtype:
            department = model
            continue
        if not model and not reg:
            continue
        if not reg:
            continue
        if reg in existing:
            skipped += 1
            continue

        make_model = f"{model} {mtype}".strip()
        vt = classify(model, mtype)
        is_ev, is_hybrid = powertrain(model, mtype)

        sid = by_name.get(driver.strip().lower())
        driver_ids = [sid] if sid else []
        driver_label = "" if sid else (driver if driver.strip().lower() not in NON_DRIVER else driver)
        if not sid and driver:
            unmatched.append(f"{reg} → '{driver}'")

        doc = {
            "id": str(uuid.uuid4()), "organization_id": ORG_ID, "active": True,
            "reg_no": reg, "make_model": make_model,
            "vehicle_type": vt, "check_type": vt, "is_ev": is_ev, "is_hybrid": is_hybrid,
            "provider": lease_company,
            "driver_staff_ids": driver_ids,
            "primary_driver_staff_id": sid,
            "driver_label": driver_label,
            "odometer": "",
            "service_record": ({"mot_due": mot_due} if mot_due else {}),
            "notes": "",
            "fleet_department": department,
            "lease_company": lease_company,
            "lease_end_date": lease_end,
            "fuel_card_number": fuel_card,
            "dart": "", "congestion": "", "m6_toll": "",
            "created_at": now,
        }
        await db.vehicles.insert_one(doc)
        existing.add(reg)
        created += 1

    print(f"Imported {created} vehicle(s), skipped {skipped} existing.")
    print(f"Unmatched drivers ({len(unmatched)}): " + "; ".join(unmatched))


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fleet.xlsx"
    asyncio.run(main(p))
