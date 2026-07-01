"""
Tests for freshly ported GymAxis→Pulse features (Jan 2026):
- AI Scheduling (Service Desk)
- Membership Dunning
- Revenue Autopilot
- GDPR tools
- Machine Manuals
- Equipment Transfers (router presence)
- Regression: CRM Tenders + Master Admin routing
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to frontend/.env parse
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass

ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"crm login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok
    return tok


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- AI Scheduling ---
class TestAIScheduling:
    def test_board(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/svc/scheduling/board", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        j = r.json()
        assert isinstance(j, dict)

    def test_settings(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/svc/scheduling/settings", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"

    def test_proposals(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/svc/scheduling/proposals", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"

    def test_reports(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/svc/scheduling/reports", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"

    def test_duration_insights(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/svc/scheduling/duration-insights", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"


# --- Membership Dunning ---
class TestMembershipDunning:
    def test_summary(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/dunning/summary", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"

    def test_at_risk(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/dunning/at-risk", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"


# --- Revenue Autopilot ---
class TestRevenueAutopilot:
    def test_overview(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/autopilot/revenue/overview", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"

    def test_settings(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/autopilot/revenue/settings", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"

    def test_actions(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/autopilot/revenue/actions", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"


# --- GDPR ---
class TestGDPR:
    def test_search_with_q(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/gdpr/search", params={"q": "test"},
                         headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"

    def test_search_no_q(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/gdpr/search", headers=_h(admin_token), timeout=30)
        # 200 or 422 acceptable; not 500
        assert r.status_code in (200, 400, 422), f"{r.status_code} {r.text[:400]}"

    def test_erasures(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/gdpr/erasures", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"


# --- Machine Manuals ---
class TestMachineManuals:
    def test_list(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/machine-manuals", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        j = r.json()
        assert "manuals" in j, j


# --- Equipment Transfers ---
class TestEquipmentTransfers:
    def test_router_registered(self, admin_token):
        # /operations/equipment-transfers is the operator inbox list route.
        r = requests.get(f"{BASE_URL}/api/operations/equipment-transfers", headers=_h(admin_token), timeout=30)
        assert r.status_code != 404, f"router not registered: {r.status_code} {r.text[:200]}"
        # Expect a 2xx or auth/scope-based rejection (401/403), never 404 / 500
        assert r.status_code < 500, f"server error: {r.status_code} {r.text[:400]}"


# --- Regression: CRM Tenders ---
class TestCRMRegression:
    def test_crm_tenders(self, crm_token):
        r = requests.get(f"{BASE_URL}/api/crm/v2/tenders", headers=_h(crm_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
