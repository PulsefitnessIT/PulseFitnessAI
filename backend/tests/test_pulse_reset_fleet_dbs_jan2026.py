"""Backend tests for Pulse Fitness iteration:
1. Password reset flow branches (/api/auth/reset-password)
2. DBS fields on HR profile (PATCH /api/staffing/hr/profile/{id})
3. Fleet Manager endpoint (/api/vehicles) - 45 vehicles + new fields
"""
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

# Read frontend/.env for REACT_APP_BACKEND_URL (public URL used by user)
_BE = ""
with open("/app/frontend/.env") as _f:
    for _l in _f:
        if _l.startswith("REACT_APP_BACKEND_URL="):
            _BE = _l.split("=", 1)[1].strip().strip('"')
BASE_URL = _BE.rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"

# Read backend env for direct DB access (token seeding)
MONGO_URL = None
DB_NAME = None
with open("/app/backend/.env") as f:
    for line in f:
        if line.startswith("MONGO_URL="):
            MONGO_URL = line.split("=", 1)[1].strip().strip('"')
        if line.startswith("DB_NAME="):
            DB_NAME = line.split("=", 1)[1].strip().strip('"')

_client = MongoClient(MONGO_URL)
_db = _client[DB_NAME]

OWNER_EMAIL = "portal@pulsefitness.ltd"
OWNER_PASSWORD = "PulseFleet123!"


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_user():
    u = _db.users.find_one({"email": OWNER_EMAIL})
    assert u, "owner user not found in DB"
    return u


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─────────────────── Password reset branches ───────────────────

class TestPasswordReset:
    def _mint_token(self, user_id, email, *, used=False, expired=False, unknown_user=False):
        tok = secrets.token_urlsafe(24)
        exp = datetime.now(timezone.utc) + timedelta(hours=-1 if expired else 24)
        _db.password_reset_tokens.insert_one({
            "token": tok,
            "user_id": ("nonexistent-" + str(uuid.uuid4())) if unknown_user else user_id,
            "email": email,
            "expires_at": exp.isoformat(),
            "used": used,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return tok

    def test_a_fresh_token_redeems_and_login_works(self, owner_user):
        # Create a disposable test user so we don't nuke owner password
        uid = str(uuid.uuid4())
        email = f"test_reset_{uid[:8]}@pulse-test.local"
        from passlib.context import CryptContext
        pw_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        _db.users.insert_one({
            "id": uid, "email": email, "full_name": "Reset Test",
            "password": pw_ctx.hash("OldPassword123!"),
            "organization_id": owner_user.get("organization_id"),
            "role": "staff", "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            tok = self._mint_token(uid, email)
            new_pw = "FreshReset99!Xy"
            r = requests.post(f"{BASE_URL}/api/auth/reset-password",
                              json={"token": tok, "password": new_pw})
            assert r.status_code == 200, r.text
            # Login with new password
            r2 = requests.post(f"{BASE_URL}/api/auth/login",
                               json={"email": email, "password": new_pw})
            assert r2.status_code == 200, f"login after reset failed: {r2.text}"
            # Token now marked used
            doc = _db.password_reset_tokens.find_one({"token": tok})
            assert doc["used"] is True
        finally:
            _db.users.delete_one({"id": uid})
            _db.password_reset_tokens.delete_many({"user_id": uid})

    def test_b_reused_token_returns_400(self, owner_user):
        uid = str(uuid.uuid4())
        email = f"test_reset_{uid[:8]}@pulse-test.local"
        tok = self._mint_token(uid, email, used=True)
        try:
            r = requests.post(f"{BASE_URL}/api/auth/reset-password",
                              json={"token": tok, "password": "NewPassword123!Xy"})
            assert r.status_code == 400
            assert "already been used or was replaced" in r.text, r.text
        finally:
            _db.password_reset_tokens.delete_one({"token": tok})

    def test_c_bogus_token_returns_400(self):
        r = requests.post(f"{BASE_URL}/api/auth/reset-password",
                          json={"token": "bogus-does-not-exist-xyz", "password": "NewPassword123!Xy"})
        assert r.status_code == 400
        assert "This reset link is invalid" in r.text, r.text

    def test_d_expired_token_returns_400(self):
        uid = str(uuid.uuid4())
        email = f"test_reset_{uid[:8]}@pulse-test.local"
        tok = self._mint_token(uid, email, expired=True)
        try:
            r = requests.post(f"{BASE_URL}/api/auth/reset-password",
                              json={"token": tok, "password": "NewPassword123!Xy"})
            assert r.status_code == 400
            assert "expired" in r.text.lower(), r.text
        finally:
            _db.password_reset_tokens.delete_one({"token": tok})

    def test_e_email_fallback_when_user_id_stale(self, owner_user):
        # Create disposable user; mint token with a stale user_id but the correct email
        uid = str(uuid.uuid4())
        email = f"test_reset_fallback_{uid[:8]}@pulse-test.local"
        from passlib.context import CryptContext
        pw_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        _db.users.insert_one({
            "id": uid, "email": email, "full_name": "Fallback Test",
            "password": pw_ctx.hash("OldPassword123!"),
            "organization_id": owner_user.get("organization_id"),
            "role": "staff", "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            tok = self._mint_token(uid, email, unknown_user=True)  # user_id no longer resolves
            new_pw = "FallbackReset99!Xy"
            r = requests.post(f"{BASE_URL}/api/auth/reset-password",
                              json={"token": tok, "password": new_pw})
            assert r.status_code == 200, r.text
            r2 = requests.post(f"{BASE_URL}/api/auth/login",
                               json={"email": email, "password": new_pw})
            assert r2.status_code == 200, f"email fallback login failed: {r2.text}"
        finally:
            _db.users.delete_one({"id": uid})
            _db.password_reset_tokens.delete_many({"email": email})


# ─────────────────── DBS profile fields ───────────────────

class TestDbsFields:
    def test_patch_and_get_dbs(self, owner_token, owner_user):
        org = owner_user.get("organization_id")
        staff = _db.staff_members.find_one({"organization_id": org})
        if not staff:
            pytest.skip("No staff members in Pulse Fitness Ltd to test DBS")
        sid = staff["id"]
        dbs_no = f"TEST_DBS_{uuid.uuid4().hex[:6]}"
        exp = "2027-06-30"
        r = requests.patch(f"{BASE_URL}/api/staffing/hr/profile/{sid}",
                           json={"dbs_number": dbs_no, "dbs_expiry_date": exp},
                           headers=_headers(owner_token))
        assert r.status_code == 200, r.text
        g = requests.get(f"{BASE_URL}/api/staffing/hr/profile/{sid}",
                         headers=_headers(owner_token))
        assert g.status_code == 200, g.text
        body = g.json()
        # profile might be nested; check top-level or under 'profile'
        blob = body.get("profile", body)
        assert blob.get("dbs_number") == dbs_no, body
        assert blob.get("dbs_expiry_date") == exp, body


# ─────────────────── Fleet Manager ───────────────────

class TestFleetManager:
    def test_list_45_vehicles_with_new_fields(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/vehicles", headers=_headers(owner_token))
        assert r.status_code == 200, r.text
        vs = r.json().get("vehicles", [])
        assert len(vs) >= 45, f"expected >=45 vehicles, got {len(vs)}"
        keys = set(vs[0].keys())
        expected = {"fleet_department", "lease_company", "lease_end_date",
                    "fuel_card_number", "dart", "congestion", "m6_toll",
                    "driver_label", "service_record"}
        missing = expected - keys
        assert not missing, f"missing fields on vehicle: {missing}; got {sorted(keys)}"

    def test_create_and_patch_vehicle_persists_new_fields(self, owner_token):
        reg = f"TEST{uuid.uuid4().hex[:4].upper()}"
        payload = {
            "reg_no": reg, "make_model": "Ford Transit", "vehicle_type": "van",
            "fleet_department": "Installations", "lease_company": "LEX Auto Lease",
            "lease_end_date": "2026-12-31", "fuel_card_number": "FC-12345",
            "dart": "DART-1", "congestion": "CC-2", "m6_toll": "M6-3",
            "driver_label": "Pool", "service_record": {"mot_due": "2026-11-01"},
        }
        r = requests.post(f"{BASE_URL}/api/vehicles", json=payload,
                          headers=_headers(owner_token))
        assert r.status_code == 200, r.text
        created = r.json()
        vid = created["id"]
        try:
            assert created["fleet_department"] == "Installations"
            assert created["lease_company"] == "LEX Auto Lease"
            assert created["service_record"].get("mot_due") == "2026-11-01"

            # PATCH updates
            payload["lease_company"] = "Vanarama"
            payload["service_record"]["mot_due"] = "2027-01-15"
            p = requests.patch(f"{BASE_URL}/api/vehicles/{vid}", json=payload,
                               headers=_headers(owner_token))
            assert p.status_code == 200, p.text

            # verify via list
            r2 = requests.get(f"{BASE_URL}/api/vehicles", headers=_headers(owner_token))
            match = [v for v in r2.json()["vehicles"] if v["id"] == vid]
            assert match, "vehicle vanished after patch"
            assert match[0]["lease_company"] == "Vanarama"
            assert match[0]["service_record"].get("mot_due") == "2027-01-15"
        finally:
            _db.vehicles.delete_one({"id": vid})
