"""Pre-release verification for Service Desk: PM frequencies, Master Admin console, Lifecycle 404."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://aftersales-engine-1.preview.emergentagent.com").rstrip("/")

OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASS = "IsoDemo123!"
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASS = "C2s9yJ3YAhydB4d34-Bykg"


def _login(email, password, retries=2):
    last = None
    for i in range(retries + 1):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
        last = r
        if r.status_code == 200:
            return r.json().get("token") or r.json().get("access_token")
        if r.status_code == 429:
            time.sleep(35)
            continue
        break
    pytest.fail(f"Login failed for {email}: {last.status_code} {last.text[:200]}")


@pytest.fixture(scope="module")
def owner_token():
    return _login(OWNER_EMAIL, OWNER_PASS)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- PM frequency validation ----------
class TestPMFrequencies:
    def _post(self, tok, freq):
        payload = {
            "equipment_id": "iso-demo-eq-nonexistent-xyz",
            "frequency": freq,
            "next_pm": "2026-06-01",
        }
        return requests.post(f"{BASE_URL}/api/svc/pm/schedules", headers=_hdr(tok), json=payload, timeout=30)

    @pytest.mark.parametrize("freq", ["weekly", "fortnightly", "monthly", "quarterly", "biannual", "annual"])
    def test_valid_frequencies_pass_validation(self, owner_token, freq):
        r = self._post(owner_token, freq)
        # We expect NOT a 400 frequency-validation error. Acceptable: 200, 201, 404 (equipment missing), 403
        assert r.status_code != 400 or "frequency" not in r.text.lower(), (
            f"Freq {freq} rejected as invalid: {r.status_code} {r.text[:300]}"
        )
        print(f"PM freq={freq} -> {r.status_code}")

    def test_invalid_frequency_rejected(self, owner_token):
        r = self._post(owner_token, "daily")
        assert r.status_code == 400, f"Expected 400 for 'daily', got {r.status_code} {r.text[:200]}"
        assert "frequency" in r.text.lower(), f"Expected freq error msg, got: {r.text[:200]}"


# ---------- Master Admin service-desk customers ----------
class TestMasterAdminCustomers:
    URL = f"{BASE_URL}/api/master-admin/service-desk/customers"

    def test_admin_gets_customers(self, admin_token):
        r = requests.get(self.URL, headers=_hdr(admin_token), timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        data = r.json()
        # Structure
        assert "summary" in data or "total" in data, f"Missing summary: {list(data.keys())}"
        summary = data.get("summary", data)
        total = summary.get("total") or data.get("total") or len(data.get("customers", []) or data.get("items", []))
        assert total >= 5, f"Expected >=5 customers, got {total}"

        customers = data.get("customers") or data.get("items") or data.get("results") or []
        names = {c.get("name") or c.get("org_name") or c.get("organization_name") for c in customers}
        expected = {"Peak Service Co", "FitFix Engineers", "GymCare Partners", "Rundown Repairs", "NewStart Servicing"}
        missing = expected - names
        assert not missing, f"Missing seeded orgs: {missing}. Present: {names}"

    def test_owner_forbidden(self, owner_token):
        r = requests.get(self.URL, headers=_hdr(owner_token), timeout=30)
        assert r.status_code == 403, f"Expected 403 for non-master, got {r.status_code}: {r.text[:200]}"


# ---------- Lifecycle 404 for non-owning org ----------
class TestLifecycle404:
    def test_owner_gets_404_not_500(self, owner_token):
        r = requests.get(
            f"{BASE_URL}/api/svc/cases/SDDEMO_case_LIFECYCLE/lifecycle",
            headers=_hdr(owner_token),
            timeout=30,
        )
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text[:200]}"
        assert r.status_code < 500
