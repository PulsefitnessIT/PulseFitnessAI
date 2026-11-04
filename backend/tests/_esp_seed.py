import asyncio, sys, uuid
sys.path.insert(0, '/app/backend')
from dotenv import load_dotenv; load_dotenv('/app/backend/.env')
from utils.auth import hash_password
UID, CASE, OTHER = "esp-test-eng-1", "esp-test-case-1", "esp-test-case-other"
async def main(mode):
    from utils.database import db
    if mode == "clean":
        await db.users.delete_many({"id": UID}); await db.svc_engineers.delete_many({"id": UID})
        await db.svc_cases.delete_many({"id": {"$in": [CASE, OTHER]}}); return
    row = await db.suppliers.find_one({"estate_supplier_id": {"$exists": True, "$ne": None}}, {"_id": 0})
    site = await db.organizations.find_one({"id": row["organization_id"]}, {"_id": 0, "id": 1, "name": 1})
    await db.organizations.update_one({"id": site["id"]}, {"$set": {"service_supplier_id": row["id"]}})
    await db.users.update_one({"id": UID}, {"$set": {
        "id": UID, "organization_id": "bfpo-mod-org", "email": "esp.test.eng@example.com", "username": "esp.test.eng@example.com",
        "full_name": "ESP Test Engineer", "role": "engineer", "bfpo_role": "engineer", "account_type": "mod_site",
        "is_mod_user": True, "is_active": True, "is_mod_bfpo": True, "mod_estate_supplier_id": row["estate_supplier_id"],
        "provider_name": row.get("name"), "bfpo_site_ids": [], "bfpo_territory_ids": [],
        "created_via": "external_provider_onboarding", "password": hash_password("EspTest123!"),
        "must_change_password": False}}, upsert=True)
    base = {"organization_id": "bfpo-mod-org", "status": "new", "priority": "p2", "bfpo": True,
            "assigned_engineer_id": None, "territory_id": None, "created_at": "2026-11-01T10:00:00+00:00"}
    await db.svc_cases.update_one({"id": CASE}, {"$set": {**base, "id": CASE, "reference": "ESP-TEST-1",
        "title": "Fault — Treadmill", "site_id": site["id"], "site_name": site["name"]}}, upsert=True)
    await db.svc_cases.update_one({"id": OTHER}, {"$set": {**base, "id": OTHER, "reference": "ESP-TEST-OTHER",
        "title": "Other site fault", "site_id": "some-other-site", "site_name": "Other"}}, upsert=True)
    print("site", site["name"], "provider", row.get("name"))
asyncio.run(main(sys.argv[1]))
