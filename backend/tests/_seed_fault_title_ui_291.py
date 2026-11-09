# Iter 291 UI seed/cleanup for fault-title checks. Usage: python _seed_fault_title_ui_291.py seed|clean
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
ORGS = {"TEST_ui291_pro": "pulse_pro", "TEST_ui291_gym": "gym"}
N = 5


def seed():
    clean()
    for oid, at in ORGS.items():
        db.organizations.insert_one({"id": oid, "name": f"TEST_ UI291 {at}", "account_type": at, "created_at": NOW})
        db.users.insert_one({"id": f"{oid}_user", "email": f"{oid.lower()}@example.test", "full_name": "TEST UI User",
                             "password": hash_password(PW), "role": "owner", "organization_id": oid, "active": True,
                             "account_type": at, "must_change_password": False, "password_changed_at": NOW,
                             "created_at": NOW})
        eqs = [
            ("eq1", "MNLPNN020100194", "Lat Pulldown", "Technogym", "MNLPNN0", "Strength"),
            ("eq2", "DJK04D22000131", "Self-Powered Treadmill", "Technogym", "SKILLMILL", "Treadmill"),
            ("eq3", "LEGACY-SN-0003", "Rower", "Concept2", "Model D", "Rower"),
        ]
        for k, sn, name, mk, md, et in eqs:
            db.equipment.insert_one({"id": f"{oid}_{k}", "organization_id": oid, "serial_number": sn, "name": name,
                                     "manufacturer": mk, "model": md, "equipment_type": et, "created_at": NOW})
        base = {"organization_id": oid, "status": "open", "severity": "medium", "created_at": NOW,
                "issue_description": "TEST_ cable fraying"}
        issues = [
            {"id": f"{oid}_i1", "serial_number": "MNLPNN020100194", "machine_type": "", "supplier": "Inda"},
            {"id": f"{oid}_i2", "serial_number": "DJK04D22000131", "machine_type": "Treadmill", "supplier": "Inda", "supplier_ref": "R-77"},
            {"id": f"{oid}_i3", "machine_name": "LEGACY-SN-0003", "machine_type": ""},
            {"id": f"{oid}_i4", "serial_number": "SN-ORPHAN-4", "machine_type": "Cross Trainer", "supplier": "Inda"},
            {"id": f"{oid}_i5", "serial_number": "SN-ORPHAN-5-LONGSERIALVALUEXXXXXXXXXXXX", "machine_type": ""},
        ]
        for i in issues:
            db.issues.insert_one({**base, **i})
        db.supplier_cases.insert_one({"id": f"{oid}_case1", "issue_id": f"{oid}_i2", "token": f"{oid}_tok",
                                      "supplier_name": "Inda Fitness", "supplier_email": "inda@example.test",
                                      "current_status": "open", "created_at": NOW})
    print("seeded")


def clean():
    ids = list(ORGS)
    db.users.delete_many({"id": {"$in": [f"{o}_user" for o in ids]}})
    db.organizations.delete_many({"id": {"$in": ids}})
    db.equipment.delete_many({"id": {"$in": [f"{o}_{k}" for o in ids for k in ("eq1", "eq2", "eq3")]}})
    db.issues.delete_many({"id": {"$in": [f"{o}_i{n}" for o in ids for n in range(1, N + 1)]}})
    db.supplier_cases.delete_many({"id": {"$in": [f"{o}_case1" for o in ids]}})
    print("cleaned")


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()
