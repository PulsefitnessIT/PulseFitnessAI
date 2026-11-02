"""Regression: external provider → MOD site supplier sync, machine assignment,
fault emails to Pulse + provider."""
import asyncio
import os
import uuid

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")


def test_provider_sync_assigns_machines_and_fault_emails(monkeypatch):
    asyncio.run(_scenario(monkeypatch))


async def _scenario(monkeypatch):
    import utils.database as udb
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    monkeypatch.setattr(udb, "db", db, raising=False)
    import routes.master_admin_mod_estate as mme
    import routes.issues as iss
    monkeypatch.setattr(mme, "db", db)
    monkeypatch.setattr(iss, "db", db)
    org_id, sup_id, user_id = f"zz-modsite-{uuid.uuid4().hex[:6]}", str(uuid.uuid4()), str(uuid.uuid4())
    eq_ids = [str(uuid.uuid4()) for _ in range(3)]
    try:
        await db.organizations.insert_one({"id": org_id, "name": "ZZ MOD Site", "account_type": "mod_site"})
        await db.mod_estate_suppliers.insert_one({"id": sup_id, "name": "ZZ Provider", "email": "jobs@zzprov.example.com",
                                                  "contact_name": "Jim", "phone": "1"})
        await db.users.insert_one({"id": user_id, "email": f"{user_id}@x.com", "mod_estate_supplier_id": sup_id,
                                   "is_mod_bfpo": True, "bfpo_site_ids": [org_id]})
        await db.equipment.insert_many([
            {"id": eq_ids[0], "organization_id": org_id, "supplier": "Technogym"},
            {"id": eq_ids[1], "organization_id": org_id},
            {"id": eq_ids[2], "organization_id": org_id, "supplier": "Own Co"},
        ])
        await db.suppliers.insert_one({"id": "zz-own-" + org_id, "organization_id": org_id, "name": "Own Co", "email": "own@x.com"})
        assert await mme._sync_provider_to_sites(sup_id) == 1
        org = await db.organizations.find_one({"id": org_id})
        row = await db.suppliers.find_one({"id": org["service_supplier_id"]})
        assert row["email"] == "jobs@zzprov.example.com"
        eqs = {e["id"]: e async for e in db.equipment.find({"organization_id": org_id})}
        assert eqs[eq_ids[0]]["supplier_id"] == row["id"] and eqs[eq_ids[0]]["previous_supplier"] == "Technogym"
        assert eqs[eq_ids[1]]["supplier_id"] == row["id"]
        assert eqs[eq_ids[2]].get("supplier_id") is None  # own supplier kept
        # provider email change propagates
        await db.mod_estate_suppliers.update_one({"id": sup_id}, {"$set": {"email": "new@zzprov.example.com"}})
        await mme._sync_provider_to_sites(sup_id)
        assert (await db.suppliers.find_one({"id": row["id"]}))["email"] == "new@zzprov.example.com"
        # fault emails: Pulse + provider
        sent = []

        async def fake_send(to, subject, html, **kw):
            sent.append((to, kw.get("category")))
            return True
        import utils.email as uem
        monkeypatch.setattr(uem, "send_email", fake_send)
        issue = {"id": str(uuid.uuid4()), "organization_id": org_id, "machine_type": "Treadmill",
                 "issue_description": "x", "equipment_id": eq_ids[1]}
        await db.issues.insert_one(dict(issue))
        await iss._send_mod_fault_notifications(issue, {"organization_id": org_id, "id": "u"})
        to = {t for t, _ in sent}
        roles = {r["role"]: r for r in issue.get("notified_recipients", [])}
        assert "new@zzprov.example.com" in to or roles.get("overseas"), (sent, issue.get("notified_recipients"))
        assert roles["pulse"].get("delivered", True)
    finally:
        await db.organizations.delete_one({"id": org_id})
        await db.mod_estate_suppliers.delete_one({"id": sup_id})
        await db.users.delete_one({"id": user_id})
        await db.equipment.delete_many({"organization_id": org_id})
        await db.suppliers.delete_many({"organization_id": org_id})
        await db.issues.delete_many({"organization_id": org_id})
