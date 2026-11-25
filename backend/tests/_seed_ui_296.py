# UI seed for iteration_296 retest; run with "seed" or "clean"
import os
import sys
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
ADMIN_ORG = "d19de469-645a-4b66-93b1-52455a643f5b"
ADMIN_ID = "1fedcc01-1f53-408a-bc48-017375348536"
SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
def now(d=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=d)).isoformat()
REPORT = {"work_completed": "TEST_ UI replaced drive belt", "further_work_required": "TEST_ UI check motor",
          "further_parts_required": [{"name": "TEST_ UI Drive belt long name", "qty": 2, "sku": "DB-9"}],
          "start_time": now(-90), "end_time": now(-10), "recorded_at": now()}
IDS = {"open": "TEST_u296_open", "locked": "TEST_u296_locked", "locked_un": "TEST_u296_lockun",
       "mod": "TEST_u296_mod", "ppm": "TEST_u296_ppm"}


def base(cid, org=ADMIN_ORG, eng=ADMIN_ID, **kw):
    d = {"id": cid, "organization_id": org, "reference": f"TEST-{cid[-6:].upper()}", "assigned_engineer_id": eng,
         "assigned_engineer_name": "Eng", "customer_name": "TEST_Customer", "title": "TEST_ UI fault",
         "created_at": now(-200), "updated_at": now(-100), "case_type": "repair", "priority": "p3",
         "safety_signoff_waived": True}
    d.update(kw)
    return d


def seed():
    clean()
    site = db.sites.find_one({"organization_id": "bfpo-mod-org"}, {"_id": 0, "id": 1, "name": 1})
    db.svc_cases.insert_many([
        base(IDS["open"], status="on_site"),
        base(IDS["locked"], status="closed", closed_at=now(-5), resolution_notes="TEST_ done", engineer_report=REPORT),
        base(IDS["locked_un"], status="closed", closed_at=now(-5), resolution_notes="TEST_ done", engineer_report=REPORT),
        base(IDS["mod"], org="bfpo-mod-org", eng="bfpo-eng-gib", status="closed", closed_at=now(-1),
             resolution_notes="TEST_ mod done", engineer_report=REPORT, site_id=site["id"], site_name=site["name"]),
    ])
    db.svc_time_entries.insert_one({"id": "TEST_u296_te", "case_id": IDS["open"], "organization_id": ADMIN_ORG,
                                    "category": "on_site", "duration_minutes": 60, "engineer_id": ADMIN_ID,
                                    "start_at": now(-70), "end_at": now(-10), "updated_at": now(-10), "created_at": now(-10)})
    db.svc_signatures.insert_many([
        {"id": "TEST_u296_sig1", "case_id": IDS["locked"], "organization_id": ADMIN_ORG, "signed_by_name": "TEST_ Locked Signer", "image_data": SIG,
         "signed_at": now(-6), "unavailable": False},
        {"id": "TEST_u296_sig2", "case_id": IDS["locked_un"], "organization_id": ADMIN_ORG, "unavailable": True, "unavailable_reason": "TEST_ customer away",
         "signed_at": now(-6)},
        {"id": "TEST_u296_sig3", "case_id": IDS["mod"], "organization_id": "bfpo-mod-org", "signed_by_name": "TEST_ MOD Signer", "image_data": SIG,
         "signed_at": now(-2), "unavailable": False},
        {"id": "TEST_u296_sig4", "ppm_service_id": IDS["ppm"], "case_id": None, "organization_id": "bfpo-mod-org", "signed_by_name": "TEST_ PPM Signer",
         "image_data": SIG, "signed_at": now(-2), "unavailable": False},
    ])
    db.bfpo_ppm_services.insert_one({"id": IDS["ppm"], "organization_id": "bfpo-mod-org", "reference": "TEST-U296PPM",
                                     "site_id": site["id"], "site_name": site["name"], "status": "completed",
                                     "assigned_engineer_id": "bfpo-eng-gib", "assigned_engineer_name": "Tomás Bianchi",
                                     "due_date": now()[:10], "created_at": now(1000), "completed_at": now(-2),
                                     "engineer_report": REPORT, "notes": "TEST_ ppm"})
    print(json.dumps({**IDS, "site": site}))


def clean():
    db.svc_cases.delete_many({"id": {"$in": list(IDS.values())}})
    db.svc_time_entries.delete_many({"id": "TEST_u296_te"})
    db.svc_signatures.delete_many({"id": {"$regex": "^TEST_u296_"}})
    db.svc_signatures.delete_many({"case_id": {"$in": list(IDS.values())}})
    db.bfpo_ppm_services.delete_many({"id": IDS["ppm"]})
    db.svc_case_events.delete_many({"case_id": {"$in": list(IDS.values())}})
    db.svc_engineer_invoices.delete_many({"case_id": {"$in": list(IDS.values())}})


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()
