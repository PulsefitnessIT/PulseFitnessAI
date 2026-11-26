"""Setup/verify/cleanup helper for the Estate Onboarding UI retest. usage: setup|verify|cleanup TAG"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import openpyxl
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
MDB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
cmd, TAG = sys.argv[1], sys.argv[2]
NAME = f"TEST_UI{TAG} Kestrel Leisure"
NEW = f"TEST_UI{TAG} Brand Unique Quasar"
STATE = f"/tmp/ui_afs_{TAG}.json"


def sheet(path, name):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Site Name", "Description", "Make", "Model", "Serial Number", "Contract Start"])
    ws.append([f"{name} Main", "Treadmill", "Life Fitness", "95T", f"SNUI{uuid.uuid4().hex[:6]}", "2026-01-01"])
    wb.save(path)


if cmd == "setup":
    from utils.customer_identity import lite_org_doc
    oid = f"TEST_UI{TAG}_org"
    d = lite_org_doc(oid, {"name": NAME}, ref="", company="", source="test", job_id=None)
    MDB.organizations.insert_one(d)
    cid = f"TEST_UI{TAG}_crm"
    MDB.crm2_companies.insert_one({"id": cid, "organization_id": OP, "name": NAME, "type": "customer",
                                   "created_at": datetime.now(timezone.utc).isoformat()})
    sheet(f"/tmp/ui_afs_{TAG}_1.xlsx", NAME)
    sheet(f"/tmp/ui_afs_{TAG}_2.xlsx", NEW)
    json.dump({"org": oid, "crm": cid}, open(STATE, "w"))
    print("setup", oid, cid)
elif cmd == "verify":
    s = json.load(open(STATE))
    print("crm linked:", MDB.crm2_companies.find_one({"id": s["crm"]}).get("linked_organization_id"))
    print("crm count same name:", MDB.crm2_companies.count_documents({"organization_id": OP, "name": NAME}))
    for i in MDB.crm2_afs_onboarding.find({"customer_name": {"$in": [NAME, NEW]}}, {"id": 1, "customer_name": 1, "status": 1, "committed": 1}):
        c = i.get("committed") or {}
        print("import", i["customer_name"], i.get("status"), c.get("customer_org_id"), c.get("crm_company_id"))
else:
    s = json.load(open(STATE))
    imps = list(MDB.crm2_afs_onboarding.find({"customer_name": {"$in": [NAME, NEW]}}, {"id": 1, "committed": 1}))
    orgs = [s["org"]]
    crm = {s["crm"]}
    for i in imps:
        c = i.get("committed") or {}
        if c.get("crm_company_id"):
            crm.add(c["crm_company_id"])
        o = c.get("customer_org_id")
        if o and o not in orgs and MDB.organizations.find_one({"id": o, "name": {"$regex": f"^TEST_UI{TAG}"}}):
            orgs.append(o)
    site_ids = [x["id"] for x in MDB.sites.find({"organization_id": {"$in": orgs}}, {"id": 1})]
    for coll in MDB.list_collection_names():
        MDB[coll].delete_many({"organization_id": {"$in": orgs}})
        if site_ids:
            MDB[coll].delete_many({"site_id": {"$in": site_ids}})
    ids = [i["id"] for i in imps]
    MDB.crm2_contracts.delete_many({"source_import_id": {"$in": ids}})
    crm |= {f"tenant-{o}" for o in orgs}
    MDB.crm2_companies.delete_many({"id": {"$in": list(crm)}})
    MDB.crm2_afs_onboarding.delete_many({"id": {"$in": ids}})
    MDB.customer_account_refs.delete_many({"org_id": {"$in": orgs}})
    MDB.organizations.delete_many({"id": {"$in": orgs}})
    print("cleaned", orgs, len(ids))
