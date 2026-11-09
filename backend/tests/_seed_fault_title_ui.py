# Seed/cleanup TEST_ui_ data for fault-title UI checks. Usage: python _seed_fault_title_ui.py seed|clean
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
ORGS = {"TEST_ui_org_pro": "pulse_pro", "TEST_ui_org_gym": "gym"}


def seed():
    clean()
    for oid, at in ORGS.items():
        db.organizations.insert_one({"id": oid, "name": f"TEST_ UI {at}", "account_type": at, "created_at": NOW})
        db.users.insert_one({"id": f"{oid}_user", "email": f"{oid.lower()}@example.test", "full_name": "TEST UI User",
                             "password": hash_password(PW), "role": "owner", "organization_id": oid, "active": True,
                             "account_type": at, "must_change_password": False, "password_changed_at": NOW,
                             "created_at": NOW})
        eqs = [
            ("eq1", "SN-LF95T-0001", "Treadmill 1", "Life Fitness", "95T", "Treadmill"),
            ("eq2", "SN-LFINT-0002", "Bike 2", "Life Fitness", "Life Fitness Integrity Bike", "Bike"),
            ("eq3", "SN-NAMEONLY-3", "Rower by the window", "", "", "Rower"),
        ]
        for k, sn, name, mk, md, et in eqs:
            db.equipment.insert_one({"id": f"{oid}_{k}", "organization_id": oid, "serial_number": sn, "name": name,
                                     "manufacturer": mk, "model": md, "equipment_type": et, "created_at": NOW})
        base = {"organization_id": oid, "status": "open", "severity": "medium", "created_at": NOW,
                "issue_description": "TEST_ belt slipping"}
        issues = [
            {"id": f"{oid}_i1", "serial_number": "SN-LF95T-0001", "machine_type": "Treadmill"},
            {"id": f"{oid}_i2", "serial_number": "SN-LFINT-0002", "machine_type": "Bike"},
            {"id": f"{oid}_i3", "serial_number": "SN-NAMEONLY-3", "machine_type": ""},
            {"id": f"{oid}_i4", "serial_number": "SN-ORPHAN-4", "machine_type": "Cross Trainer"},
            {"id": f"{oid}_i5", "serial_number": "SN-ORPHAN-5-LONGSERIALVALUE", "machine_type": ""},
        ]
        for i in issues:
            db.issues.insert_one({**base, **i})
        db.supplier_cases.insert_one({"id": f"{oid}_case1", "issue_id": f"{oid}_i1", "token": f"{oid}_tok",
                                      "supplier_name": "Inda Fitness", "supplier_email": "inda@example.test",
                                      "current_status": "open", "created_at": NOW})
    print("seeded")


def clean():
    ids = list(ORGS)
    db.users.delete_many({"id": {"$in": [f"{o}_user" for o in ids]}})
    db.organizations.delete_many({"id": {"$in": ids}})
    db.equipment.delete_many({"id": {"$in": [f"{o}_{k}" for o in ids for k in ("eq1", "eq2", "eq3")]}})
    db.issues.delete_many({"id": {"$in": [f"{o}_i{n}" for o in ids for n in range(1, 6)]}})
    db.supplier_cases.delete_many({"id": {"$in": [f"{o}_case1" for o in ids]}})
    print("cleaned")


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()
