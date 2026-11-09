# Iter 293 UI seed/cleanup for supplier delivered/undelivered badge. Usage: python _seed_supplier_badge_ui_293.py seed|clean
# No emails are sent: rows are inserted directly in the DB.
import os, sys
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from utils.auth import hash_password

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
NOW = datetime.now(timezone.utc).isoformat()
PW = "TestUiFault#2026"
ORGS = {"TEST_ui293_pro": "pulse_pro", "TEST_ui293_gym": "gym"}
# (suffix, delivered_to or MISSING)
MISSING = object()
CASES = [("ok", ["inda@example.test"]), ("bad", []), ("legacy", MISSING), ("other", ["someone@else.test"])]


def seed():
    clean()
    for oid, at in ORGS.items():
        db.organizations.insert_one({"id": oid, "name": f"TEST_ UI293 {at}", "account_type": at, "created_at": NOW})
        db.users.insert_one({"id": f"{oid}_user", "email": f"{oid.lower()}@example.test", "full_name": "TEST UI User",
                             "password": hash_password(PW), "role": "owner", "organization_id": oid, "active": True,
                             "account_type": at, "must_change_password": False, "password_changed_at": NOW,
                             "created_at": NOW})
        db.equipment.insert_one({"id": f"{oid}_eq1", "organization_id": oid, "serial_number": "DJK04D22000131",
                                 "name": "Self-Powered Treadmill", "manufacturer": "Technogym", "model": "SKILLMILL",
                                 "equipment_type": "Treadmill", "created_at": NOW})
        for suf, dt in CASES:
            iid = f"{oid}_i_{suf}"
            doc = {"id": iid, "organization_id": oid, "status": "open", "severity": "medium", "created_at": NOW,
                   "issue_description": f"TEST_ belt slipping {suf}", "serial_number": "DJK04D22000131",
                   "machine_type": "Treadmill", "supplier": "Inda",
                   "auto_dispatched_supplier_name": "Inda Fitness", "auto_dispatched_supplier_email": "inda@example.test"}
            if dt is not MISSING:
                doc["auto_dispatch_delivered_to"] = dt
            db.issues.insert_one(doc)
            db.supplier_cases.insert_one({"id": f"{iid}_case", "issue_id": iid, "token": f"{iid}_tok",
                                          "supplier_name": "Inda Fitness", "supplier_email": "inda@example.test",
                                          "current_status": "open", "created_at": NOW})
    print("seeded")


def clean():
    ids = list(ORGS)
    iids = [f"{o}_i_{s}" for o in ids for s, _ in CASES]
    db.users.delete_many({"id": {"$in": [f"{o}_user" for o in ids]}})
    db.organizations.delete_many({"id": {"$in": ids}})
    db.equipment.delete_many({"id": {"$in": [f"{o}_eq1" for o in ids]}})
    db.issues.delete_many({"id": {"$in": iids}})
    db.supplier_cases.delete_many({"id": {"$in": [f"{i}_case" for i in iids]}})
    left = db.issues.count_documents({"id": {"$in": iids}}) + db.supplier_cases.count_documents({"issue_id": {"$in": iids}})
    print("cleaned, left:", left)


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()
