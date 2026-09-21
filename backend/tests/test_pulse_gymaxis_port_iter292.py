"""Iter 292 — Pulse × GymAxis port regression tests.

Coverage:
  1) Preventative Maintenance  /api/svc/pm/*
  2) Orbit 4 setup             /api/svc/orbit4/*
  3) Case lifecycle timeline   /api/svc/cases/{case_id}/lifecycle
  4) Master-admin console      /api/master-admin/service-desk/customers
  5) Branding sweep            no 'GymAxis' text in ported responses
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://aftersales-engine.preview.emergentagent.com").rstrip("/")
BYPASS = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "test-bypass-secret-for-ci-runs-only-2026")

MASTER = ("admin@pulsefitness.com", "C2s9yJ3YAhydB4d34-Bykg")
OWNER = ("owner@isodemo.com", "IsoDemo123!")


def _login(email, password):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-RateLimit-Bypass": BYPASS},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    d = r.json()
    return d.get("token") or d.get("access_token")


@pytest.fixture(scope="module")
def master_token():
    return _login(*MASTER)


@pytest.fixture(scope="module")
def owner_token():
    # owner@isodemo needs is_service_desk=true to access desk routes.
    # Try to flip the flag via mongo before returning the token.
    t = _login(*OWNER)
    try:
        from pymongo import MongoClient
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if mongo_url and db_name:
            client = MongoClient(mongo_url)
            client[db_name].users.update_one(
                {"email": OWNER[0]},
                {"$set": {"is_service_desk": True}},
            )
            client.close()
            # Re-login so JWT reflects the new claim (if encoded there).
            t = _login(*OWNER)
    except Exception as e:  # noqa: BLE001
        print(f"is_service_desk flip skipped: {e}")
    return t


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "X-RateLimit-Bypass": BYPASS}


def _mongo():
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def seeded_equipment():
    """Insert a TEST equipment doc for iso-demo-org (idempotent)."""
    db = _mongo()
    eid = "TEST_eq_iter292"
    db.equipment.update_one(
        {"id": eid},
        {"$set": {
            "id": eid,
            "organization_id": "iso-demo-org",
            "name": "TEST Iter292 Treadmill",
            "equipment_type": "treadmill",
            "site_id": "iso-demo-site-a",
            "site_name": "Demo Head Office",
        }},
        upsert=True,
    )
    yield eid
    db.equipment.delete_one({"id": eid})
    db.ppm_schedules.delete_many({"equipment_id": eid})
    db.ppm_tasks.delete_many({"equipment_id": eid})


@pytest.fixture(scope="module")
def seeded_case():
    """Insert a TEST svc_case doc for lifecycle test (idempotent)."""
    db = _mongo()
    cid = "TEST_case_iter292"
    db.svc_cases.update_one(
        {"id": cid},
        {"$set": {
            "id": cid,
            "organization_id": "iso-demo-org",
            "status": "open",
            "created_at": "2026-01-01T00:00:00+00:00",
            "reference": "TEST-CASE-292",
        }},
        upsert=True,
    )
    yield cid
    db.svc_cases.delete_one({"id": cid})



# ── 1) Preventative Maintenance ────────────────────────────────────────────
class TestPreventativeMaintenance:
    def test_list_schedules(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/svc/pm/schedules", headers=_h(owner_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # accept list or {items:[]} shape
        assert isinstance(data, (list, dict))

    def test_create_schedule_annual(self, owner_token, seeded_equipment):
        payload = {
            "equipment_id": seeded_equipment,
            "frequency": "annual",
            "next_pm": "2026-06-01",
        }
        r = requests.post(f"{BASE_URL}/api/svc/pm/schedules", json=payload,
                          headers=_h(owner_token), timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
        created = r.json()
        assert "id" in created
        assert created.get("frequency") == "annual"
        # persistence: GET list should include it
        lst = requests.get(f"{BASE_URL}/api/svc/pm/schedules",
                           headers=_h(owner_token), timeout=30).json()
        items = lst if isinstance(lst, list) else lst.get("items", lst.get("schedules", []))
        assert any(s.get("id") == created["id"] for s in items), "schedule did not persist"
        # store for confirm test
        pytest.pm_created_id = created["id"]

    def test_create_schedule_invalid_freq_rejected(self, owner_token, seeded_equipment):
        payload = {
            "equipment_id": seeded_equipment,
            "frequency": "daily",  # not in accepted set per pm.py
            "next_pm": "2026-06-01",
        }
        r = requests.post(f"{BASE_URL}/api/svc/pm/schedules", json=payload,
                          headers=_h(owner_token), timeout=30)
        # code only accepts quarterly/biannual/annual — daily/weekly/monthly/yearly should 400
        assert r.status_code == 400, f"expected 400 for freq=daily, got {r.status_code} {r.text[:200]}"

    def test_due(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/svc/pm/due", headers=_h(owner_token), timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_confirm_schedule(self, owner_token):
        sid = getattr(pytest, "pm_created_id", None)
        if not sid:
            pytest.skip("no PM created")
        r = requests.post(f"{BASE_URL}/api/svc/pm/schedules/{sid}/confirm",
                          headers=_h(owner_token), timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"


# ── 2) Orbit 4 setup ───────────────────────────────────────────────────────
class TestOrbit4:
    def test_get_connection(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/svc/orbit4/connection",
                         headers=_h(owner_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "connection_key" in d or "id" in d
        assert "webhook_path" in d

    def test_put_connection_and_token_redacted(self, owner_token):
        secret = f"orbit4-TEST-token-{uuid.uuid4().hex}"
        r = requests.put(
            f"{BASE_URL}/api/svc/orbit4/connection",
            json={"api_token": secret, "enabled": True},
            headers=_h(owner_token), timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # Plaintext token MUST NOT be in the response body.
        assert secret not in str(d), "api_token leaked in PUT response!"
        # Fetch again and confirm redaction / no plaintext
        r2 = requests.get(f"{BASE_URL}/api/svc/orbit4/connection",
                          headers=_h(owner_token), timeout=30)
        d2 = r2.json()
        assert secret not in str(d2), "api_token leaked in GET response!"
        tok_field = d2.get("api_token")
        # Redaction should be a mask or falsy — not the raw secret
        assert tok_field != secret

    def test_activity(self, owner_token):
        r = requests.get(f"{BASE_URL}/api/svc/orbit4/connection/activity",
                         headers=_h(owner_token), timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_engineer_mapping_put(self, owner_token):
        # Endpoint accepts arbitrary engineer_id; verify it does not 500.
        r = requests.put(
            f"{BASE_URL}/api/svc/orbit4/engineers/TEST_eng_{uuid.uuid4().hex[:6]}",
            json={"orbit4_engineer_id": "orbit4-eng-1"},
            headers=_h(owner_token), timeout=30,
        )
        assert r.status_code in (200, 201, 404), f"{r.status_code} {r.text[:200]}"


# ── 3) Case lifecycle ──────────────────────────────────────────────────────
class TestCaseLifecycle:
    def test_nonexistent_case_returns_404(self, owner_token):
        r = requests.get(
            f"{BASE_URL}/api/svc/cases/does-not-exist-{uuid.uuid4().hex[:6]}/lifecycle",
            headers=_h(owner_token), timeout=30,
        )
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_real_case_lifecycle(self, owner_token, seeded_case):
        r = requests.get(f"{BASE_URL}/api/svc/cases/{seeded_case}/lifecycle",
                         headers=_h(owner_token), timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # Expect at least labour_hours/parts_count/cost/resolved fields
        assert "cost" in d or "cost_total" in d or "labour_hours" in d or "stages" in d, f"unexpected lifecycle shape: {list(d)[:10]}"
        assert d.get("case_id") == seeded_case


# ── 4) Master-Admin console ────────────────────────────────────────────────
class TestMasterAdminServiceDeskCustomers:
    def test_master_admin_can_list(self, master_token):
        r = requests.get(
            f"{BASE_URL}/api/master-admin/service-desk/customers",
            headers=_h(master_token), timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # returns a dict with a list somewhere (customers/items/orgs)
        assert isinstance(d, dict) or isinstance(d, list)
        if isinstance(d, dict):
            found = any(isinstance(v, list) for v in d.values())
            assert found, f"expected a list somewhere: {list(d)[:6]}"

    def test_non_master_forbidden(self, owner_token):
        r = requests.get(
            f"{BASE_URL}/api/master-admin/service-desk/customers",
            headers=_h(owner_token), timeout=30,
        )
        assert r.status_code in (401, 403), f"non-master must be forbidden, got {r.status_code}"


# ── 5) Branding sweep ──────────────────────────────────────────────────────
class TestBrandingScrub:
    """No visible 'GymAxis' branding should leak through the ported responses."""

    @pytest.mark.parametrize("path,who", [
        ("/api/svc/pm/schedules", "owner"),
        ("/api/svc/pm/due", "owner"),
        ("/api/svc/orbit4/connection", "owner"),
        ("/api/svc/orbit4/connection/activity", "owner"),
        ("/api/master-admin/service-desk/customers", "master"),
    ])
    def test_no_gymaxis_text(self, path, who, owner_token, master_token):
        tok = master_token if who == "master" else owner_token
        r = requests.get(f"{BASE_URL}{path}", headers=_h(tok), timeout=30)
        assert r.status_code == 200, f"setup: {path} → {r.status_code}"
        body = r.text.lower()
        assert "gymaxis" not in body, f"'GymAxis' appears in {path}!"
        assert "gym-axis" not in body, f"'gym-axis' appears in {path}!"
