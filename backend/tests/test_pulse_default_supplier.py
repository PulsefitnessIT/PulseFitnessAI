"""Backend tests for Pulse Fitness Ltd default supplier feature (Jan 2026)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pulse-tender-system.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PRO_EMAIL = "owner@isodemo.com"
PRO_PW = "IsoDemo123!"
LITE_EMAIL = "lite.suptest@pulsedemo.test"
LITE_PW = "LiteSup123!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("token") or data.get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def pro_client():
    return _login(PRO_EMAIL, PRO_PW)


@pytest.fixture(scope="module")
def lite_client():
    return _login(LITE_EMAIL, LITE_PW)


def _find_default(suppliers):
    for s in suppliers:
        if s.get("is_default_pulse"):
            return s
    return None


class TestProSuppliers:
    def test_pro_get_suppliers_has_locked_default_first(self, pro_client):
        r = pro_client.get(f"{API}/suppliers")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("can_add_suppliers") is True
        suppliers = data.get("suppliers") or []
        assert len(suppliers) > 0
        first = suppliers[0]
        assert first.get("is_default_pulse") is True, "default not pinned first"
        assert first.get("name") == "Pulse Fitness Ltd"
        assert first.get("email") == "service.dept@pulsefitness.com"
        assert first.get("locked") is True

    def test_pro_delete_default_forbidden(self, pro_client):
        r = pro_client.get(f"{API}/suppliers")
        default = _find_default(r.json().get("suppliers", []))
        assert default
        rd = pro_client.delete(f"{API}/suppliers/{default['id']}")
        assert rd.status_code == 403

    def test_pro_update_default_forbidden(self, pro_client):
        r = pro_client.get(f"{API}/suppliers")
        default = _find_default(r.json().get("suppliers", []))
        assert default
        ru = pro_client.put(f"{API}/suppliers/{default['id']}", json={"name": "Hacked"})
        assert ru.status_code == 403

    def test_pro_can_add_and_cleanup(self, pro_client):
        payload = {
            "name": "TEST_PulseDefaultSupplier",
            "email": "test_pulse_default@example.com",
            "phone": "0000",
            "contact_person": "T",
            "supplier_types": ["service"],
            "send_welcome": False,
        }
        r = pro_client.post(f"{API}/suppliers", json=payload)
        assert r.status_code == 200, r.text
        sid = r.json().get("id")
        assert sid
        # cleanup
        rd = pro_client.delete(f"{API}/suppliers/{sid}")
        assert rd.status_code == 200

    def test_dispatch_readiness_coherent(self, pro_client):
        r = pro_client.get(f"{API}/suppliers/dispatch-readiness")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["machines_ready"] + d["machines_blocked"] == d["total_machines"]
        # No-supplier machines are counted as ready (fall back to Pulse default)
        assert d["machines_no_supplier"] <= d["machines_ready"]


class TestLiteSuppliers:
    def test_lite_get_only_default(self, lite_client):
        r = lite_client.get(f"{API}/suppliers")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("can_add_suppliers") is False
        suppliers = data.get("suppliers") or []
        assert len(suppliers) == 1
        s = suppliers[0]
        assert s.get("is_default_pulse") is True
        assert s.get("locked") is True
        assert s.get("name") == "Pulse Fitness Ltd"
        assert s.get("email") in (
            "service.dept@pulsefitness.com",
            "MODService@pulsefitness.com",
        )

    def test_lite_post_forbidden(self, lite_client):
        r = lite_client.post(f"{API}/suppliers", json={
            "name": "TEST_ShouldFail", "email": "x@x.com", "send_welcome": False,
        })
        assert r.status_code == 403
