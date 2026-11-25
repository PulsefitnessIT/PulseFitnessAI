# UI seed for iteration_297 (Book follow-up from case drawer); run with "seed" or "clean"
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
def now(d=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=d)).isoformat()
CID, REF = "TEST_u297_case", "TEST-U297FU"
REPORT = {"work_completed": "TEST_ UI replaced belt", "further_work_required": "TEST_ UI motor needs replacing",
          "further_parts_required": [{"name": "TEST_ UI Motor", "qty": 1, "sku": "MTR-1"}],
          "start_time": now(-90), "end_time": now(-10), "recorded_at": now()}


def seed():
    clean()
    db.svc_cases.insert_one({"id": CID, "organization_id": ADMIN_ORG, "reference": REF, "status": "closed",
                             "assigned_engineer_id": ADMIN_ID, "assigned_engineer_name": "Eng", "customer_name": "TEST_Customer",
                             "title": "TEST_ UI treadmill fault", "created_at": now(-200), "updated_at": now(-1), "closed_at": now(-5),
                             "case_type": "repair", "priority": "p3", "resolution_notes": "TEST_ done", "engineer_report": REPORT})
    db.svc_parts_requests.insert_one({"id": "TEST_u297_pr", "organization_id": ADMIN_ORG, "case_id": CID, "case_reference": REF,
                                      "source": "further_parts_required", "origin_case_id": CID, "status": "pending",
                                      "part_name": "TEST_ UI Motor", "part_sku": "MTR-1", "qty": 1, "created_at": now()})
    print(json.dumps({"id": CID, "ref": REF}))


def clean():
    new_ids = [c["id"] for c in db.svc_cases.find({"follow_up_of": CID}, {"id": 1})]
    db.svc_cases.delete_many({"id": {"$in": [CID, *new_ids]}})
    db.svc_case_events.delete_many({"case_id": {"$in": [CID, *new_ids]}})
    db.svc_parts_requests.delete_many({"origin_case_id": CID})
    print("cleaned", new_ids)


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()
