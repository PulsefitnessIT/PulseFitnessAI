"""One-off 120k-equipment scale load test (read-side).

Seeds a dedicated throwaway org with 120,000 synthetic equipment rows, then
times the EXACT db operations the hot endpoints run today, so we fix from
evidence not guesses. Cleans up after itself unless KEEP=1.
"""
import asyncio, os, time, uuid, random
from datetime import datetime, timezone, timedelta

import sys
sys.path.insert(0, "/app/backend")
from utils.database import db

ORG = "loadtest-sicon-120k"
N = 120_000
TYPES = ["Treadmill", "Cross Trainer", "Rowing Machine", "Spin Bike", "Leg Press",
         "Chest Press", "Cable Machine", "Smith Machine", "Air Bike", "Stepper"]
MAKES = ["Life Fitness", "Technogym", "Precor", "Matrix", "Concept2", "Hammer Strength"]


def _now():
    return datetime.now(timezone.utc)


async def seed():
    existing = await db.equipment.count_documents({"organization_id": ORG})
    if existing >= N:
        print(f"[seed] already have {existing} rows, skipping insert")
        return
    if existing:
        await db.equipment.delete_many({"organization_id": ORG})
    print(f"[seed] inserting {N} equipment rows into org {ORG} ...")
    t0 = time.time()
    batch = []
    for i in range(N):
        site = f"site-{i % 40}"
        batch.append({
            "id": str(uuid.uuid4()),
            "organization_id": ORG,
            "serial_number": f"SN{i:07d}",
            "equipment_type": random.choice(TYPES),
            "manufacturer": random.choice(MAKES),
            "model": f"M{random.randint(100,999)}",
            "site_id": site,
            "sicon_equipment_id": f"SIC{i:07d}",
            "status": "active",
            "created_at": (_now() - timedelta(days=random.randint(0, 900))).isoformat(),
        })
        if len(batch) >= 10_000:
            await db.equipment.insert_many(batch, ordered=False)
            batch = []
            print(f"  inserted {i+1}/{N} ({time.time()-t0:.1f}s)")
    if batch:
        await db.equipment.insert_many(batch, ordered=False)
    print(f"[seed] done in {time.time()-t0:.1f}s")


async def timed(label, coro_factory):
    t0 = time.time()
    res = await coro_factory()
    dt = (time.time() - t0) * 1000
    n = len(res) if isinstance(res, list) else res
    print(f"  {label:<62} {dt:8.1f} ms   -> {n}")
    return dt, n


async def measure():
    print("\n[measure] BEFORE FIX — DB-layer cost of what each endpoint does today")
    orgf = {"organization_id": ORG}
    total = await db.equipment.count_documents(orgf)
    print(f"  (org has {total} equipment rows)\n")

    # A. GET /equipment today: find(orgf).to_list(2000)  -> SILENT truncation
    await timed("GET /equipment  find().to_list(2000)  [truncates!]",
                lambda: db.equipment.find(orgf, {"_id": 0}).to_list(2000))
    # count for a paginated contract
    await timed("count_documents(org)  [indexed]",
                lambda: db.equipment.count_documents(orgf))
    # B. Service Desk paginated (the GOOD pattern) find().skip().limit(50)
    await timed("GET /service-desk/equipment  skip(0).limit(50)",
                lambda: db.equipment.find(orgf, {"_id": 0}).skip(0).limit(50).to_list(50))
    await timed("GET /service-desk/equipment  skip(100000).limit(50) [deep page]",
                lambda: db.equipment.find(orgf, {"_id": 0}).skip(100000).limit(50).to_list(50))
    # C. Supplier rollup + analytics: to_list(50000)/to_list(5000) -> silent drop
    await timed("supplier-rollup  find().to_list(50000)  [drops ~70k!]",
                lambda: db.equipment.find(orgf, {"_id": 0}).to_list(50000))
    await timed("analytics/KPI  find().to_list(5000)  [drops ~115k!]",
                lambda: db.equipment.find(orgf, {"_id": 0}).to_list(5000))
    # D. Equipment free-text search: regex $or over unindexed fields -> COLLSCAN
    rx = {"$regex": "Tread", "$options": "i"}
    await timed("equipment search  $or regex type/make/model  [COLLSCAN]",
                lambda: db.equipment.find(
                    {**orgf, "$or": [{"equipment_type": rx}, {"manufacturer": rx}, {"model": rx}]},
                    {"_id": 0}).limit(200).to_list(200))

    # E. PPM backfill: iterate ALL equipment inline (one pass)
    t0 = time.time()
    cnt = 0
    async for _ in db.equipment.find(orgf, {"_id": 0, "id": 1}):
        cnt += 1
    print(f"  {'PPM backfill  full async iterate ALL equipment':<62} {(time.time()-t0)*1000:8.1f} ms   -> {cnt}")


async def main():
    await seed()
    await measure()
    if os.environ.get("KEEP") != "1":
        n = (await db.equipment.delete_many({"organization_id": ORG})).deleted_count
        print(f"\n[cleanup] removed {n} load-test rows (set KEEP=1 to retain)")
    else:
        print(f"\n[cleanup] KEEP=1 — retaining load-test org {ORG}")


if __name__ == "__main__":
    asyncio.run(main())
