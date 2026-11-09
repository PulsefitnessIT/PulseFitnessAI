# Iter 291: GET /api/issues legacy machine_name backfill now runs before equipment enrichment.
# Seeds TEST_ rows directly in test_database; removed by id at teardown. No email sent.
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
load_dotenv(os.path.join(BACKEND_DIR, ".env"))
from utils.auth import hash_password  # noqa: E402


def _base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip()
    return url.rstrip("/")


BASE_URL = _base_url()
RUN = uuid.uuid4().hex[:6]
NOW = datetime.now(timezone.utc).isoformat()
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ORG = f"TEST_org_legacy_{RUN}"
ORG_B = f"TEST_org_legacyB_{RUN}"
UID = f"TEST_user_legacy_{RUN}"
EMAIL = f"test_legacy_{RUN}@example.test"
PW = "TestLegacy#2026x"
SN = f"MNLPNN0{RUN}"
SN_B = f"SNB{RUN}"
EQ = [f"TEST_eq_legacy_{RUN}", f"TEST_eq_legacyB_{RUN}"]
I = {k: f"TEST_i_{k}_{RUN}" for k in ("legacy", "both", "cross", "nomatch")}


@pytest.fixture(scope="module")
def token():
    db.organizations.insert_many([
        {"id": ORG, "name": f"TEST_ legacy {RUN}", "account_type": "gym", "created_at": NOW},
        {"id": ORG_B, "name": f"TEST_ legacyB {RUN}", "account_type": "gym", "created_at": NOW}])
    db.users.insert_one({"id": UID, "email": EMAIL, "full_name": "TEST Legacy", "password": hash_password(PW),
                         "role": "owner", "organization_id": ORG, "active": True, "account_type": "gym",
                         "must_change_password": False, "password_changed_at": NOW, "created_at": NOW})
    db.equipment.insert_many([
        {"id": EQ[0], "organization_id": ORG, "serial_number": SN, "name": "Lat Pulldown",
         "manufacturer": "Technogym", "model": "MNLPNN0", "equipment_type": "Strength"},
        {"id": EQ[1], "organization_id": ORG_B, "serial_number": SN_B, "name": "Other",
         "manufacturer": "Matrix", "model": "T7", "equipment_type": "Treadmill"}])
    base = {"organization_id": ORG, "status": "open", "severity": "medium", "created_at": NOW,
            "issue_description": "TEST_ legacy"}
    db.issues.insert_many([
        {**base, "id": I["legacy"], "machine_name": SN, "machine_type": ""},
        {**base, "id": I["both"], "machine_name": "ignored", "serial_number": SN, "machine_type": ""},
        {**base, "id": I["cross"], "machine_name": SN_B, "machine_type": ""},
        {**base, "id": I["nomatch"], "machine_name": f"NOPE{RUN}", "machine_type": ""}])
    h = {}
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    if secret:
        h["X-RateLimit-Bypass"] = secret
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PW}, headers=h, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text[:200]}")
    yield r.json().get("token") or r.json().get("access_token")
    db.issues.delete_many({"id": {"$in": list(I.values())}})
    db.equipment.delete_many({"id": {"$in": EQ}})
    db.users.delete_many({"id": UID})
    db.organizations.delete_many({"id": {"$in": [ORG, ORG_B]}})


def _issues(token):
    r = requests.get(f"{BASE_URL}/api/issues", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    return {i["id"]: i for i in r.json()["issues"]}


def test_legacy_machine_name_gets_make_model(token):
    i = _issues(token)[I["legacy"]]
    assert i["serial_number"] == SN
    assert i["equipment_make"] == "Technogym"
    assert i["equipment_model"] == "MNLPNN0"
    assert i["equipment_name"] == "Lat Pulldown"
    assert i["equipment_type"] == "Strength"


def test_existing_serial_not_overwritten(token):
    i = _issues(token)[I["both"]]
    assert i["serial_number"] == SN
    assert i["equipment_make"] == "Technogym"


def test_legacy_cross_org_no_leak(token):
    i = _issues(token)[I["cross"]]
    assert i["serial_number"] == SN_B
    assert "equipment_make" not in i and "equipment_model" not in i


def test_legacy_no_match(token):
    i = _issues(token)[I["nomatch"]]
    assert i["serial_number"] == f"NOPE{RUN}"
    assert "equipment_make" not in i


def test_backfill_not_persisted(token):
    _issues(token)
    raw = db.issues.find_one({"id": I["legacy"]}, {"_id": 0})
    assert "serial_number" not in raw and "equipment_make" not in raw
