"""Pre-release seed — realistic Service Desk PRODUCT customers + one full
case lifecycle, so the Master Admin → Service Desk customers console and the
case Lifecycle (cost-to-serve) timeline can be verified against real numbers
rather than empty state.

Seeds (idempotent — wipes prior SDDEMO_* rows first):
  • 5 `service_provider` orgs spanning the whole journey (paying, active trial,
    trial expiring, trial lapsed, onboarding-no-usage) → exercises every KPI
    + segment on the master console.
  • Per-org svc_cases with spread created_at so total/recent-7d counts are real.
  • ONE fully-worked case for "Peak Service Co" with equipment, labour time
    entries, mileage, allocated parts (with catalogue cost), an assigned
    engineer (pay rate), a paid invoice (labour/part/travel lines) and a
    resolved state_change event → all 8 lifecycle stages complete with a real
    cost-to-serve + margin.

Run (from /app/backend, env sourced): python scripts/seed_service_desk_demo.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

# ── Production safety guard (utils/seed_guard.py) — never seed a prod DB ──
import os as _sg_os, sys as _sg_sys  # noqa: E402
_sg_sys.path.insert(0, _sg_os.path.dirname(_sg_os.path.dirname(_sg_os.path.abspath(__file__))))
from utils.seed_guard import assert_seeding_allowed  # noqa: E402
assert_seeding_allowed(__file__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TAG = "SDDEMO_"
now = datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def days_ago(n: int) -> str:
    return iso(now - timedelta(days=n))


def days_ahead(n: int) -> str:
    return iso(now + timedelta(days=n))


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # ── Wipe prior demo rows so re-runs are clean ────────────────────
    for coll, key in [
        ("organizations", "id"), ("svc_cases", "id"), ("svc_case_events", "case_id"),
        ("equipment", "id"), ("svc_time_entries", "case_id"), ("svc_mileage_entries", "case_id"),
        ("svc_engineer_invoices", "case_id"), ("svc_engineers", "id"), ("parts", "id"),
        ("org_chart_nodes", "id"), ("users", "id"),
    ]:
        await db[coll].delete_many({key: {"$regex": f"^{TAG}"}})

    # ── 5 service-provider orgs across the lifecycle ─────────────────
    orgs = [
        {  # Paying + active this week
            "id": f"{TAG}org_peak", "name": "Peak Service Co",
            "account_type": "service_provider", "service_desk_brand": "Peak Service Co",
            "trial_status": "converted", "subscription_active": True, "subscription_tier": "pro",
            "service_ops_setup_complete": True, "created_at": days_ago(140),
        },
        {  # Active trial, using it
            "id": f"{TAG}org_fitfix", "name": "FitFix Engineers",
            "account_type": "service_provider", "service_desk_brand": "FitFix",
            "trial_status": "active", "trial_ends_at": days_ahead(18),
            "service_ops_setup_complete": True, "created_at": days_ago(12),
        },
        {  # Trial expiring within 7 days
            "id": f"{TAG}org_gymcare", "name": "GymCare Partners",
            "account_type": "service_provider", "service_desk_brand": "GymCare",
            "trial_status": "active", "trial_ends_at": days_ahead(5),
            "service_ops_setup_complete": True, "created_at": days_ago(22),
        },
        {  # Trial lapsed
            "id": f"{TAG}org_rundown", "name": "Rundown Repairs",
            "account_type": "service_provider", "service_desk_brand": "Rundown",
            "trial_status": "expired", "trial_ends_at": days_ago(9),
            "service_ops_setup_complete": True, "created_at": days_ago(48),
        },
        {  # Brand new, onboarding, no usage
            "id": f"{TAG}org_newstart", "name": "NewStart Servicing",
            "account_type": "service_provider", "service_desk_brand": "NewStart",
            "trial_status": "active", "trial_ends_at": days_ahead(21),
            "service_ops_setup_complete": False, "created_at": days_ago(3),
        },
    ]
    await db.organizations.insert_many(orgs)

    # ── Users + engineers so the console "users/engineers" columns fill ──
    users = []
    engineers_nodes = []
    for o in orgs:
        for i in range(2 if o["service_ops_setup_complete"] else 1):
            users.append({"id": f"{TAG}u_{o['id']}_{i}", "organization_id": o["id"],
                          "email": f"user{i}@{o['id']}.test", "created_at": o["created_at"]})
        if o["service_ops_setup_complete"]:
            engineers_nodes.append({"id": f"{TAG}en_{o['id']}", "organization_id": o["id"],
                                    "is_engineer": True, "name": "Field Engineer"})
    await db.users.insert_many(users)
    await db.org_chart_nodes.insert_many(engineers_nodes)

    # ── svc_cases per org (spread dates for real total + 7d counts) ──
    def mkcase(oid, n, age_days, status="closed"):
        cid = f"{TAG}case_{oid}_{n}"
        return {
            "id": cid, "organization_id": oid, "reference": f"SVC-{oid[-4:]}-{n:03d}",
            "title": f"Treadmill fault #{n}", "status": status, "priority": "p3",
            "case_type": "repair", "customer_name": "Anytime Fitness Ltd",
            "site_name": "City Centre Club", "created_at": days_ago(age_days),
            "updated_at": days_ago(max(0, age_days - 1)),
        }

    cases = []
    # Peak: paying, active this week
    cases += [mkcase(f"{TAG}org_peak", i, age) for i, age in enumerate([1, 3, 6, 20, 55, 90], 1)]
    # FitFix: active trial, recent usage
    cases += [mkcase(f"{TAG}org_fitfix", i, age) for i, age in enumerate([2, 5, 9], 1)]
    # GymCare: expiring trial, a little usage
    cases += [mkcase(f"{TAG}org_gymcare", i, age) for i, age in enumerate([4, 15], 1)]
    # Rundown: lapsed, old cases only
    cases += [mkcase(f"{TAG}org_rundown", i, age) for i, age in enumerate([40, 46], 1)]
    # NewStart: none (at-risk / no usage)
    await db.svc_cases.insert_many(cases)

    # ── FULL LIFECYCLE case for Peak Service Co ──────────────────────
    peak = f"{TAG}org_peak"
    life_id = f"{TAG}case_LIFECYCLE"
    asset_id = f"{TAG}eq_treadmill"
    eng_id = f"{TAG}eng_peak"
    part_sku = "TRD-BELT-88"

    await db.equipment.insert_one({
        "id": asset_id, "organization_id": peak, "name": "Life Fitness 95T Treadmill",
        "manufacturer": "Life Fitness", "model": "95T", "category": "Cardio",
        "serial_number": "LF95T-0099", "status": "operational",
        "site_name": "City Centre Club", "location": "Cardio Zone",
    })
    await db.svc_engineers.insert_one({
        "id": eng_id, "organization_id": peak, "name": "Dan Fielding",
        "payout": {"labour_rate_gbp": 32.0},
    })
    await db.parts.insert_one({
        "id": f"{TAG}part_belt", "organization_id": peak, "sku": part_sku,
        "name": "Running belt (95T)", "cost": 78.0,
    })

    created = now - timedelta(days=7)
    scheduled = now - timedelta(days=6, hours=2)
    resolved = now - timedelta(days=6)
    await db.svc_cases.insert_one({
        "id": life_id, "organization_id": peak, "reference": "SVC-PEAK-LIFE",
        "title": "Treadmill belt slipping under load", "status": "invoiced",
        "priority": "p2", "case_type": "repair", "source": "portal",
        "fault_code": "BELT-SLIP", "fault_category": "Drive",
        "customer_name": "Anytime Fitness Ltd", "customer_email": "ops@anytime.test",
        "site_name": "City Centre Club",
        "asset_id": asset_id, "asset_name": "Life Fitness 95T Treadmill",
        "assigned_engineer_id": eng_id, "assigned_engineer_name": "Dan Fielding",
        "scheduled_at": iso(scheduled), "created_at": iso(created),
        "updated_at": iso(resolved),
        "allocated_parts": [{"id": f"{TAG}ap1", "name": "Running belt (95T)",
                             "part_sku": part_sku, "qty": 1, "source": "van_stock",
                             "fulfilled": True}],
    })
    await db.svc_case_events.insert_one({
        "id": f"{TAG}ev_resolved", "case_id": life_id, "organization_id": peak,
        "type": "state_change", "from_state": "on_site", "to_state": "resolved",
        "at": iso(resolved), "actor_name": "Dan Fielding",
    })
    await db.svc_time_entries.insert_many([
        {"id": f"{TAG}t1", "case_id": life_id, "organization_id": peak,
         "category": "on_site", "duration_minutes": 95},
        {"id": f"{TAG}t2", "case_id": life_id, "organization_id": peak,
         "category": "travel", "duration_minutes": 40},
    ])
    await db.svc_mileage_entries.insert_one({
        "id": f"{TAG}m1", "case_id": life_id, "organization_id": peak, "miles": 24.0,
    })
    # Charge lines: labour 1.58h @ £75 = 118.75, part £145, travel 24mi @ £0.45 = 10.80
    await db.svc_engineer_invoices.insert_one({
        "id": f"{TAG}inv_life", "case_id": life_id, "organization_id": peak,
        "reference": "INV-PEAK-0001", "number": "INV-PEAK-0001", "status": "paid",
        "currency": "£", "total": 274.55,
        "created_at": iso(resolved), "sent_at": iso(resolved + timedelta(hours=2)),
        "paid_at": iso(resolved + timedelta(days=3)),
        "lines": [
            {"kind": "labour", "description": "On-site labour", "line_total": 118.75},
            {"kind": "part", "description": "Running belt (95T)", "line_total": 145.00},
            {"kind": "travel", "description": "Mileage 24mi", "line_total": 10.80},
        ],
    })

    print("Seeded Service Desk demo:")
    print(f"  • {len(orgs)} service_provider orgs (paying / active / expiring / lapsed / onboarding)")
    print(f"  • {len(cases)+1} svc_cases (incl. full lifecycle case '{life_id}' for {peak})")
    print(f"  • Lifecycle: asset {asset_id}, engineer £32/h, part cost £78, paid invoice £274.55")
    print(f"     → charge labour £118.75 / part £145 / travel £10.80; margin known over labour+parts")
    print(f"  Verify: Master Admin → Platform Tools → Service Desk customers; open case {life_id} → Lifecycle tab")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
