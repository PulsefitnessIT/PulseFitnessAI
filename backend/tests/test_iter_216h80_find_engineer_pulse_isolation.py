"""Iter 216h80 — Find an Engineer widget + Pulse Fitness isolation.

Anti-bleed-through invariants (CRITICAL):
  • Pulse customers cannot apply as Partner Engineers
  • Pulse customers cannot search the find-an-engineer widget
  • Pulse customers cannot create engineer-grants
  • Pulse orgs cannot have referrals attached on signup
  • Pulse orgs' Operations invoices do NOT trigger commission accrual

Widget behaviour:
  • Only `verified_partner` / `strategic_partner` partners surface
  • Engineer email/phone NEVER appear in the response
  • Postcode outcode-prefix match drives `in_area` ranking
  • Request-contact creates an audit-trailed `partner_contact_requests` row
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or os.environ.get("TEST_API_URL")
    or "https://service-ops-hub-6.preview.emergentagent.com"
).rstrip("/")

OPERATOR_EMAIL = "e1.agent@gymaxisai.com"
OPERATOR_PASSWORD = "E1Agent123!"
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"
E1_PARTNER_ID = "40c2b861-6f04-4377-894b-0507055bff79"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=10)
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def op_headers(): return _login(OPERATOR_EMAIL, OPERATOR_PASSWORD)
@pytest.fixture(scope="module")
def admin_headers(): return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def db():
    client = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
    return client[os.environ.get("DB_NAME") or "test_database"]


@pytest.fixture
def verified_partner(db, admin_headers):
    """Ensure the E1 partner is at verified_partner level for the duration."""
    db.partner_engineers.update_one(
        {"id": E1_PARTNER_ID}, {"$set": {"level": "verified_partner", "status": "approved"}},
    )
    yield E1_PARTNER_ID
    db.partner_engineers.update_one(
        {"id": E1_PARTNER_ID}, {"$set": {"level": "engineer_partner"}},
    )


# ─── Widget behaviour ────────────────────────────────────────────────────────


class TestFindEngineersWidget:
    def test_search_returns_verified_only(self, db, op_headers, verified_partner):
        r = requests.get(f"{BASE_URL}/api/partners/find-engineers",
                         params={"postcode": "SW1A 1AA"}, headers=op_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        for eng in body["engineers"]:
            assert eng["level"] in ("verified_partner", "strategic_partner")
            # MUST NOT leak commercial / contact data
            assert "email" not in eng
            assert "phone" not in eng
            assert "active_referral_count" not in eng

    def test_in_area_match_on_outcode_prefix(self, op_headers, verified_partner):
        # Partner postcode is SW1A 1AA — search SW1A and SW2 differently
        r1 = requests.get(f"{BASE_URL}/api/partners/find-engineers",
                          params={"postcode": "SW1A 1AA"}, headers=op_headers, timeout=10)
        assert r1.status_code == 200
        engineers = r1.json()["engineers"]
        target = next((e for e in engineers if e["id"] == E1_PARTNER_ID), None)
        assert target and target["in_area"] is True
        # Different outcode (SW2 vs SW1A — share first 2 chars 'SW' so still in_area)
        r2 = requests.get(f"{BASE_URL}/api/partners/find-engineers",
                          params={"postcode": "M1 1AA"}, headers=op_headers, timeout=10)
        target_m = next((e for e in r2.json()["engineers"] if e["id"] == E1_PARTNER_ID), None)
        # E1 has 30km radius which is <75 (nationwide threshold), so absent
        assert target_m is None or target_m.get("in_area") is False

    def test_unverified_partner_does_not_surface(self, db, op_headers):
        # Temporarily demote E1 → should not appear
        db.partner_engineers.update_one(
            {"id": E1_PARTNER_ID}, {"$set": {"level": "engineer_partner"}},
        )
        r = requests.get(f"{BASE_URL}/api/partners/find-engineers",
                         params={"postcode": "SW1A 1AA"}, headers=op_headers, timeout=10)
        ids = [e["id"] for e in r.json()["engineers"]]
        assert E1_PARTNER_ID not in ids
        # restore handled by verified_partner fixture next test

    def test_request_contact_creates_audit_row(self, db, op_headers, verified_partner):
        r = requests.post(f"{BASE_URL}/api/partners/find-engineers/{E1_PARTNER_ID}/request-contact",
                          json={"note": "Cardio bike down — urgent"},
                          headers=op_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["request"]["partner_id"] == E1_PARTNER_ID
        assert body["request"]["status"] == "new"
        rid = body["request"]["id"]
        # Cleanup
        db.partner_contact_requests.delete_many({"id": rid})

    def test_request_contact_for_unverified_404(self, db, op_headers):
        db.partner_engineers.update_one(
            {"id": E1_PARTNER_ID}, {"$set": {"level": "engineer_partner"}},
        )
        r = requests.post(f"{BASE_URL}/api/partners/find-engineers/{E1_PARTNER_ID}/request-contact",
                          json={"note": "test"}, headers=op_headers, timeout=10)
        assert r.status_code == 404

    def test_missing_postcode_400(self, op_headers):
        r = requests.get(f"{BASE_URL}/api/partners/find-engineers",
                         headers=op_headers, timeout=10)
        assert r.status_code == 422  # FastAPI Query(...) validation


# ─── Pulse Fitness isolation — CRITICAL anti-bleed-through guard ───────


@pytest.fixture
def pulse_user(db):
    """Spin up a temporary user marked as a Pulse account_type for the
    duration of the test, then clean up."""
    import bcrypt
    user_id = f"pulse-test-{uuid.uuid4()}"
    org_id = f"pulse-org-{uuid.uuid4()}"
    pw_hash = bcrypt.hashpw(b"PulseUser123!", bcrypt.gensalt()).decode()
    db.users.insert_one({
        "id": user_id, "email": f"{user_id}@pulse.test",
        "password": pw_hash, "full_name": "Pulse Test User",
        "account_type": "pulse_pro", "organization_id": org_id,
        "subscription_active": True,
    })
    db.organizations.insert_one({
        "id": org_id, "name": "Pulse Test Gym",
        "account_type": "pulse_pro", "brand": "pulse",
    })
    # Login
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": f"{user_id}@pulse.test", "password": "PulseUser123!"},
                      timeout=10)
    token = r.json()["token"]
    yield {"headers": {"Authorization": f"Bearer {token}"}, "user_id": user_id, "org_id": org_id}
    db.users.delete_many({"id": user_id})
    db.organizations.delete_many({"id": org_id})


class TestPulseIsolation:
    def test_pulse_user_cannot_apply_as_partner(self, pulse_user):
        r = requests.post(f"{BASE_URL}/api/partners/apply",
                          json={"full_name": "Pulse Hijacker", "service_postcode": "M1 1AA",
                                "terms_accepted": True},
                          headers=pulse_user["headers"], timeout=10)
        assert r.status_code == 403
        assert "gymaxis" in r.text.lower()

    def test_pulse_user_cannot_search_engineers(self, pulse_user):
        r = requests.get(f"{BASE_URL}/api/partners/find-engineers",
                         params={"postcode": "SW1A 1AA"},
                         headers=pulse_user["headers"], timeout=10)
        assert r.status_code == 403

    def test_pulse_user_cannot_create_grants(self, pulse_user):
        r = requests.post(f"{BASE_URL}/api/customer-engineer-grants",
                          json={"engineer_email": OPERATOR_EMAIL, "case_ids": []},
                          headers=pulse_user["headers"], timeout=10)
        assert r.status_code == 403

    def test_pulse_org_signup_does_not_attach_referral(self, db, pulse_user, verified_partner):
        """Helper-level: attach_referral_to_org must short-circuit for
        Pulse orgs. We invoke it via a subprocess so each test gets a
        fresh Motor event loop binding."""
        import subprocess
        org_id = pulse_user["org_id"]
        script = f"""
import asyncio, json, sys
sys.path.insert(0, '/app/backend')
from routes.partners import attach_referral_to_org
result = asyncio.run(attach_referral_to_org(
    organization_id='{org_id}', ref_code='AGQZKPAP',
))
print(json.dumps({{'result': result}}))
"""
        env = {**os.environ}
        proc = subprocess.run(
            ["python3", "-c", script], capture_output=True, text=True, timeout=15, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        out = proc.stdout.strip().splitlines()[-1]
        import json
        assert json.loads(out)["result"] is None  # blocked for Pulse orgs

    def test_pulse_org_invoice_does_not_accrue_commission(self, db, pulse_user, verified_partner):
        """Helper-level: accrue_commission_on_invoice_paid must return
        None for Pulse orgs even when legacy referred_by data is present.
        Subprocess isolates the Motor loop."""
        import subprocess
        import json
        org_id = pulse_user["org_id"]
        cus_id = f"cus_pulse_{uuid.uuid4()}"
        invoice_id = f"in_pulse_{uuid.uuid4()}"
        db.organizations.update_one(
            {"id": org_id},
            {"$set": {"stripe_customer_id": cus_id,
                      "referred_by_partner_id": E1_PARTNER_ID,
                      "account_type": "pulse_pro", "brand": "pulse"}},
        )
        script = f"""
import asyncio, json, sys
sys.path.insert(0, '/app/backend')
from routes.partners import accrue_commission_on_invoice_paid
invoice = {{
    'id': '{invoice_id}', 'customer': '{cus_id}', 'amount_paid': 6900,
    'lines': {{'data': [{{'description': 'GymAxis Operations'}}]}}
}}
result = asyncio.run(accrue_commission_on_invoice_paid(invoice))
print(json.dumps({{'result': result}}))
"""
        env = {**os.environ}
        proc = subprocess.run(
            ["python3", "-c", script], capture_output=True, text=True, timeout=15, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        out = proc.stdout.strip().splitlines()[-1]
        assert json.loads(out)["result"] is None
        # Belt-and-braces — ledger has zero rows for this invoice
        assert db.partner_commission_ledger.find_one({"source_invoice_id": invoice_id}) is None
