"""Backend tests for /api/master-admin/operator-portal-login (Jan 2026)."""
import os
import jwt
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-eng-booking.preview.emergentagent.com").rstrip("/")

MASTER_EMAIL = "admin@pulsefitness.com"
MASTER_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"
NON_ADMIN_EMAIL = "owner@isodemo.com"
NON_ADMIN_PASSWORD = "IsoDemo123!"

EXPECTED_ORG_ID = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
EXPECTED_ORG_NAME = "Pulse Fitness Ltd"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def master_token():
    return _login(MASTER_EMAIL, MASTER_PASSWORD)


@pytest.fixture(scope="module")
def non_admin_token():
    return _login(NON_ADMIN_EMAIL, NON_ADMIN_PASSWORD)


def test_operator_portal_login_as_master_admin(master_token):
    r = requests.post(
        f"{BASE_URL}/api/master-admin/operator-portal-login",
        headers={"Authorization": f"Bearer {master_token}"},
        json={},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("organization_id") == EXPECTED_ORG_ID
    assert data.get("organization_name") == EXPECTED_ORG_NAME
    assert data.get("area") == "operator"
    tok = data.get("token")
    assert isinstance(tok, str) and len(tok) > 20

    # Decode without verification to inspect payload
    payload = jwt.decode(tok, options={"verify_signature": False})
    assert payload.get("organization_id") == EXPECTED_ORG_ID
    assert payload.get("impersonated_by") == MASTER_EMAIL


def test_operator_portal_login_forbidden_for_non_master_admin(non_admin_token):
    r = requests.post(
        f"{BASE_URL}/api/master-admin/operator-portal-login",
        headers={"Authorization": f"Bearer {non_admin_token}"},
        json={},
        timeout=30,
    )
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"


def test_operator_portal_login_unauthenticated():
    r = requests.post(f"{BASE_URL}/api/master-admin/operator-portal-login", json={}, timeout=30)
    assert r.status_code in (401, 403)
