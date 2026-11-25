"""Iter323 UI fixtures: TEST_ engineers + TEST_ jobs for the MOD Ops Engineers / allocation UI. usage: setup | clean"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient  # noqa: E402

DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
MOD_SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
STATE = "/tmp/ui323.json"


def setup():
    now = datetime.now(timezone.utc).isoformat()
    out = {"eng": {}, "cases": []}
    specs = {"sites": ([], [MOD_SITE]), "terr": (["terr-cyp"], []), "missing": (["terr-gib"], ["site-deleted-xyz"])}
    for k, (t, s) in specs.items():
        uid = f"TEST_ui323_{k}_{uuid.uuid4().hex[:6]}"
        DB.users.insert_one({"id": uid, "organization_id": "bfpo-mod-org", "email": f"{uid.lower()}@example.test",
                             "full_name": f"TEST_UI {k} engineer", "role": "engineer", "bfpo_role": "engineer",
                             "bfpo_territory_ids": t, "bfpo_site_ids": s, "is_active": True, "account_type": "mod_site",
                             "is_mod_user": True, "is_mod_bfpo": True, "mod_estate_supplier_id": "pulse-inhouse-mod",
                             "created_at": now})
        out["eng"][k] = uid
    for terr, site, assigned in (("terr-falk", "site-falk-1", None), ("terr-cyp", "site-cyp-1", out["eng"]["terr"])):
        cid = f"TEST_ui323_case_{uuid.uuid4().hex[:6]}"
        DB.svc_cases.insert_one({"id": cid, "organization_id": "bfpo-mod-org", "bfpo": True, "reference": f"TEST-{cid[-6:]}",
                                 "title": "TEST_UI coverage job", "status": "assigned" if assigned else "new", "priority": "p3",
                                 "territory_id": terr, "site_id": site, "site_name": "TEST UI site",
                                 "assigned_engineer_id": assigned, "assigned_engineer_name": "TEST_UI terr engineer" if assigned else None,
                                 "created_at": now, "updated_at": now})
        out["cases"].append(cid)
    json.dump(out, open(STATE, "w"))
    print(json.dumps(out))


def clean():
    st = json.load(open(STATE))
    for uid in st["eng"].values():
        DB.users.delete_one({"id": uid})
    for cid in st["cases"]:
        DB.svc_cases.delete_one({"id": cid})
        DB.svc_case_events.delete_many({"case_id": cid})
    print("cleaned", st)


if __name__ == "__main__":
    {"setup": setup, "clean": clean}[sys.argv[1]]()
