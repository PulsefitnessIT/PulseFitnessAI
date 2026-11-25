"""Iter324 UI seed/cleanup: `python tests/_ui324_setup.py setup|cleanup` (ids in /tmp/ui324.json)."""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from tests.conftest import _test_backend_url  # noqa: E402

API = f"{_test_backend_url().rstrip('/')}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
F = "/tmp/ui324.json"
SITE = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"


def sess(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


def setup():
    mgr = sess("modsales.manager@pulsedemo.test", "ModSales123!")
    rep = sess("modsales.rep@pulsedemo.test", "ModSales123!")
    out = {"eng": [], "cases": [], "groups": []}

    def eng(name, terr):
        r = mgr.post(f"{API}/bfpo/staff/engineers", json={"full_name": name, "email": f"{name.lower().replace(' ', '_')}@example.test",
                     "bfpo_role": "engineer", "password_mode": "temp", "temp_password": "TestEng123!", "bfpo_territory_ids": terr})
        r.raise_for_status()
        out["eng"].append(r.json()["member"]["id"])
        return r.json()["member"]["id"]
    dangle = eng("TEST_ui324 Dangle", ["terr-cyp"])
    DB.users.update_one({"id": dangle}, {"$push": {"bfpo_site_ids": "site-deleted-ui324"}})
    leaver = eng("TEST_ui324 Leaver", ["terr-cyp"])
    eng("TEST_ui324 Gib", ["terr-gib"])
    cid = f"TEST_ui324_case_{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc).isoformat()
    DB.svc_cases.insert_one({"id": cid, "organization_id": "bfpo-mod-org", "bfpo": True, "reference": "TEST-UI324",
                             "title": "TEST_ ui324 job", "status": "assigned", "priority": "p3", "territory_id": "terr-cyp",
                             "site_id": "site-cyp-1", "site_name": "TEST site", "assigned_engineer_id": leaver,
                             "created_at": now, "updated_at": now})
    out["cases"].append(cid)
    rows = [{"row_id": "r1", "rate_card_id": "sor-2", "qty": 1, "coverage": "A", "label": ""}]
    cust = {"site_id": SITE, "name": "MOD Test Site", "contact_name": "TEST_UI324 Officer",
            "contact_email": "test_ui324@example.test", "address_lines": ["Faslane"]}
    g = rep.post(f"{API}/mod-ops/quotes/groups", json={"customer": cust, "rows": rows, "options": ["A"],
                                                        "idempotency_key": f"TEST_ui324_{uuid.uuid4()}"}).json()
    out["groups"].append(g["id"])
    rep.post(f"{API}/mod-ops/quotes/groups/{g['id']}/submit")
    mgr.post(f"{API}/mod-ops/quotes/groups/{g['id']}/approve", json={"approve": True, "exceptions": []})
    rep.post(f"{API}/mod-ops/quotes/groups/{g['id']}/publish", json={"quote_ids": [q["id"] for q in g["quotes"]]}).raise_for_status()
    DB.mod_quote_groups.update_one({"id": g["id"]}, {"$set": {"chase_schedule.0.due": "2026-01-01"}})
    print(mgr.post(f"{API}/mod-ops/quotes/followups/run").json())
    out.update(dangle=dangle, leaver=leaver, case=cid, group=g["id"])
    json.dump(out, open(F, "w"))
    print(out)


def cleanup():
    out = json.load(open(F))
    for e in out["eng"]:
        DB.users.delete_one({"id": e})
        DB.svc_engineers.delete_many({"id": e})
        DB.bfpo_invites.delete_many({"user_id": e})
    for c in out["cases"]:
        DB.svc_cases.delete_one({"id": c})
        for col in ("svc_case_events", "svc_events", "case_events"):
            DB[col].delete_many({"case_id": c})
    for gid in out["groups"]:
        DB.crm2_quotes.delete_many({"mod_group_id": gid})
        for col in ("mod_quote_events", "mod_quote_authorisations", "mod_quote_followups", "mod_quote_handovers"):
            DB[col].delete_many({"group_id": gid})
        DB.crm2_activities.delete_many({"mod_group_id": gid})
        DB.crm2_opportunities.delete_many({"mod_group_id": gid})
        DB.mod_quote_groups.delete_one({"id": gid})
    print("cleaned", out)


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else cleanup()
