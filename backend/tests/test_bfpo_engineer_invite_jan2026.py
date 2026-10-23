"""BFPO Engineer Invite / Provisioning tests (Jan 2026).

Focus: authorization negatives, duplicate-email 400, invite token lifecycle,
short-password rejection. Happy paths already manually verified per handoff.
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://sicon-sync-hub.preview.emergentagent.com").rstrip("/")
RL_BYPASS = {"x-ratelimit-bypass": "test-bypass-secret-for-ci-runs-only-2026"}

STAFF_EMAIL = "staff@bfpo.pulsefitness.test"
STAFF_PASSWORD = "Bfpo123!"
ENG_EMAIL = "engineer.gib@bfpo.pulsefitness.test"
ENG_PASSWORD = "Bfpo123!"


def _login(email, password, portal="mod"):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password, "portal": portal},
        headers=RL_BYPASS,
        timeout=30,
    )
    return r


@pytest.fixture(scope="module")
def staff_token():
    r = _login(STAFF_EMAIL, STAFF_PASSWORD)
    if r.status_code != 200:
        pytest.skip(f"staff login failed: {r.status_code} {r.text[:200]}")
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def engineer_token():
    r = _login(ENG_EMAIL, ENG_PASSWORD)
    if r.status_code != 200:
        pytest.skip(f"engineer login failed: {r.status_code} {r.text[:200]}")
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def ordinary_token():
    # Try creating/logging a plain user via a common test account.
    # Fall back to no-auth if we can't get one; tests that rely on this will skip.
    candidates = [
        ("qa.plain@pulsefitness.test", "Plain123!"),
        ("qa.user@pulsefitness.test", "Plain123!"),
    ]
    for email, pw in candidates:
        r = _login(email, pw, portal="mod")
        if r.status_code == 200:
            return r.json().get("token") or r.json().get("access_token")
        # try crm portal
        r = _login(email, pw, portal="crm")
        if r.status_code == 200:
            return r.json().get("token") or r.json().get("access_token")
    return None


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Happy path smoke: list team & territories ----------
class TestStaffListing:
    def test_staff_can_list_territories(self, staff_token):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/territories", headers=_auth(staff_token), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Accept either bare list or wrapped
        terrs = data if isinstance(data, list) else data.get("territories") or data.get("items") or []
        ids = {t.get("id") for t in terrs}
        assert {"terr-gib", "terr-falk", "terr-cyp", "terr-ken"}.issubset(ids), f"Missing territories: got {ids}"

    def test_staff_can_list_team(self, staff_token):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/team", headers=_auth(staff_token), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        members = data.get("members") if isinstance(data, dict) else data
        assert isinstance(members, list)
        if members:
            m = members[0]
            for k in ("full_name", "email", "bfpo_role", "is_active"):
                assert k in m, f"member missing {k}: {m}"


# ---------- Authorization negatives ----------
class TestAuthorizationNegatives:
    def test_engineer_forbidden_on_staff_team(self, engineer_token):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/team", headers=_auth(engineer_token), timeout=30)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"

    def test_engineer_forbidden_on_create_engineer(self, engineer_token):
        payload = {
            "full_name": "Should Not Create",
            "email": f"qa.bfpo+neg-{uuid.uuid4().hex[:6]}@bfpo.pulsefitness.test",
            "phone": "+441234567890",
            "bfpo_role": "engineer",
            "password_mode": "invite",
            "bfpo_territory_ids": ["terr-gib"],
            "bfpo_site_ids": ["site-gib-1"],
        }
        r = requests.post(
            f"{BASE_URL}/api/bfpo/staff/engineers",
            headers=_auth(engineer_token),
            json=payload,
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"

    def test_unauthenticated_denied(self):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/team", timeout=30)
        assert r.status_code in (401, 403), f"got {r.status_code}: {r.text[:200]}"

    def test_ordinary_user_forbidden(self, ordinary_token):
        if not ordinary_token:
            pytest.skip("No ordinary (non-BFPO) user available to test with")
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/team", headers=_auth(ordinary_token), timeout=30)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"


# ---------- Create engineer + duplicate email + invite lifecycle ----------
@pytest.fixture(scope="module")
def created_invite(staff_token):
    email = f"qa.bfpo+inv-{uuid.uuid4().hex[:8]}@bfpo.pulsefitness.test"
    payload = {
        "full_name": "QA Invite Engineer",
        "email": email,
        "phone": "+441234500000",
        "bfpo_role": "engineer",
        "password_mode": "invite",
        "bfpo_territory_ids": ["terr-gib"],
        "bfpo_site_ids": ["site-gib-1"],
    }
    r = requests.post(
        f"{BASE_URL}/api/bfpo/staff/engineers",
        headers=_auth(staff_token),
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        pytest.skip(f"cannot create invite engineer: {r.status_code} {r.text[:300]}")
    body = r.json()
    return {"email": email, "resp": body, "payload": payload}


class TestInviteFlow:
    def test_create_returns_invite_url(self, created_invite):
        body = created_invite["resp"]
        assert body.get("invite_url"), f"invite_url missing: {body}"
        assert body.get("temp_password") in (None, "", False), f"temp_password should be null for invite mode: {body.get('temp_password')}"
        member = body.get("member") or body
        assert member.get("invite_pending") is True

    def test_duplicate_email_rejected(self, staff_token, created_invite):
        payload = dict(created_invite["payload"])
        r = requests.post(
            f"{BASE_URL}/api/bfpo/staff/engineers",
            headers=_auth(staff_token),
            json=payload,
            timeout=30,
        )
        assert r.status_code == 400, f"duplicate email should be 400, got {r.status_code}: {r.text[:300]}"

    def test_invite_token_public_get(self, created_invite):
        url = created_invite["resp"]["invite_url"]
        # extract token
        token = url.rstrip("/").split("/")[-1]
        # Try without any query param
        if "?" in token:
            token = token.split("?")[0]
        r = requests.get(f"{BASE_URL}/api/bfpo/invite/{token}", timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data.get("valid") is True
        assert data.get("email") == created_invite["email"]
        assert data.get("full_name")

    def test_invite_short_password_rejected(self, created_invite):
        url = created_invite["resp"]["invite_url"]
        token = url.rstrip("/").split("/")[-1].split("?")[0]
        r = requests.post(
            f"{BASE_URL}/api/bfpo/invite/{token}/accept",
            json={"password": "short"},
            timeout=30,
        )
        assert r.status_code == 400, f"short password should be 400, got {r.status_code}: {r.text[:300]}"

    def test_invite_accept_and_login_then_reuse_fails(self, created_invite):
        url = created_invite["resp"]["invite_url"]
        token = url.rstrip("/").split("/")[-1].split("?")[0]
        new_pw = "StrongPass!23"
        r = requests.post(
            f"{BASE_URL}/api/bfpo/invite/{token}/accept",
            json={"password": new_pw},
            timeout=30,
        )
        assert r.status_code == 200, f"accept failed: {r.status_code} {r.text[:300]}"
        # Login with new password
        lr = _login(created_invite["email"], new_pw, portal="mod")
        assert lr.status_code == 200, f"login after accept failed: {lr.status_code} {lr.text[:300]}"
        user = lr.json().get("user") or {}
        assert user.get("bfpo_role") == "engineer", f"role wrong: {user}"
        # Re-use token
        r2 = requests.post(
            f"{BASE_URL}/api/bfpo/invite/{token}/accept",
            json={"password": "AnotherStrong!23"},
            timeout=30,
        )
        assert r2.status_code in (400, 409, 410), f"reused token should fail, got {r2.status_code}: {r2.text[:300]}"

    def test_invalid_invite_token(self):
        r = requests.get(f"{BASE_URL}/api/bfpo/invite/not-a-real-token-xyz-{uuid.uuid4().hex}", timeout=30)
        # Server may return 200 with valid:false, or 404
        if r.status_code == 200:
            assert r.json().get("valid") is False
        else:
            assert r.status_code in (400, 404)


# ---------- Temp-password mode ----------
class TestTempPasswordMode:
    def test_temp_password_login_forces_change(self, staff_token):
        email = f"qa.bfpo+tmp-{uuid.uuid4().hex[:8]}@bfpo.pulsefitness.test"
        payload = {
            "full_name": "QA Temp Engineer",
            "email": email,
            "phone": "+441234500001",
            "bfpo_role": "engineer",
            "password_mode": "temp",
            "bfpo_territory_ids": ["terr-gib"],
            "bfpo_site_ids": ["site-gib-1"],
        }
        r = requests.post(
            f"{BASE_URL}/api/bfpo/staff/engineers",
            headers=_auth(staff_token),
            json=payload,
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text[:300]
        body = r.json()
        temp_pw = body.get("temp_password")
        assert temp_pw, f"temp_password missing: {body}"
        lr = _login(email, temp_pw, portal="mod")
        assert lr.status_code == 200, f"login failed: {lr.status_code} {lr.text[:300]}"
        user = lr.json().get("user") or {}
        assert user.get("must_change_password") is True, f"must_change_password not true: {user}"


# ---------- Edit / resend / status ----------
class TestEditResendStatus:
    @pytest.fixture(scope="class")
    def eng(self, staff_token):
        email = f"qa.bfpo+edit-{uuid.uuid4().hex[:8]}@bfpo.pulsefitness.test"
        payload = {
            "full_name": "QA Edit Engineer",
            "email": email,
            "phone": "+441111111111",
            "bfpo_role": "engineer",
            "password_mode": "invite",
            "bfpo_territory_ids": ["terr-gib"],
            "bfpo_site_ids": ["site-gib-1"],
        }
        r = requests.post(
            f"{BASE_URL}/api/bfpo/staff/engineers",
            headers=_auth(staff_token),
            json=payload,
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text[:300]
        member = (r.json().get("member") or r.json())
        return {"id": member.get("id") or member.get("_id") or member.get("user_id"), "email": email}

    def test_edit_engineer(self, staff_token, eng):
        eid = eng["id"]
        assert eid, "engineer id missing from create response"
        r = requests.patch(
            f"{BASE_URL}/api/bfpo/staff/engineers/{eid}",
            headers=_auth(staff_token),
            json={
                "full_name": "QA Edit Engineer Renamed",
                "phone": "+442222222222",
                "bfpo_role": "lead",
                "bfpo_territory_ids": ["terr-gib", "terr-cyp"],
                "bfpo_site_ids": ["site-gib-1", "site-gib-2"],
            },
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        m = r.json().get("member") or r.json()
        assert m.get("full_name") == "QA Edit Engineer Renamed"
        assert m.get("bfpo_role") == "lead"
        assert "terr-cyp" in (m.get("bfpo_territory_ids") or [])
        assert "site-gib-2" in (m.get("bfpo_site_ids") or [])

    def test_resend_invite(self, staff_token, eng):
        r = requests.post(
            f"{BASE_URL}/api/bfpo/staff/engineers/{eng['id']}/resend-invite",
            headers=_auth(staff_token),
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        assert b.get("invite_url"), f"resend missing invite_url: {b}"

    def test_deactivate_reactivate(self, staff_token, eng):
        r = requests.post(
            f"{BASE_URL}/api/bfpo/staff/engineers/{eng['id']}/status",
            headers=_auth(staff_token),
            json={"active": False},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        m = r.json().get("member") or r.json()
        assert m.get("is_active") is False
        r2 = requests.post(
            f"{BASE_URL}/api/bfpo/staff/engineers/{eng['id']}/status",
            headers=_auth(staff_token),
            json={"active": True},
            timeout=30,
        )
        assert r2.status_code == 200, r2.text[:300]
        m2 = r2.json().get("member") or r2.json()
        assert m2.get("is_active") is True
