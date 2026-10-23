"""
Tests for:
(A) Master Admin Pulse Fitness Portal - non-impersonation self switch
(B) MOD equipment AI import - mod_code header, template inclusion, persistence
"""
import os
import base64
import json
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://sicon-sync-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PW = "C2s9yJ3YAhydB4d34-Bykg"


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    assert len(parts) == 3, f"not a JWT: {token[:40]}"
    pad = "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(parts[1] + pad))


@pytest.fixture(scope="module")
def admin_token():
    # Pace to avoid 429 rate limit
    time.sleep(2)
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    if r.status_code == 429:
        time.sleep(30)
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in login response: {data}"
    return tok


# ---- (A) Pulse Fitness operator-portal-login (non-impersonation self switch) ----

class TestPulseOperatorPortalLogin:
    def test_operator_portal_login_returns_non_impersonation(self, admin_token):
        r = requests.post(
            f"{API}/master-admin/operator-portal-login",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        data = r.json()
        assert data.get("impersonation") is False, f"expected impersonation False, got {data}"
        assert data.get("organization_name") == "Pulse Fitness Ltd", f"got org name {data.get('organization_name')}"
        tok = data.get("token") or data.get("access_token")
        assert tok, f"no token: {data}"
        payload = _decode_jwt_payload(tok)
        assert "act_org" in payload, f"missing act_org claim: {payload}"
        assert "impersonated_by" not in payload, f"unexpected impersonated_by claim: {payload}"

    def test_auth_me_with_act_token_returns_admin_self(self, admin_token):
        r = requests.post(
            f"{API}/master-admin/operator-portal-login",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert r.status_code == 200
        act_tok = r.json().get("token") or r.json().get("access_token")

        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {act_tok}"}, timeout=30)
        assert me.status_code == 200, f"{me.status_code} {me.text}"
        m = me.json()
        assert m.get("email") == ADMIN_EMAIL, f"expected admin email, got {m.get('email')}"
        assert m.get("is_master_admin") is True, f"is_master_admin not true: {m}"
        assert m.get("org_is_operator") is True, f"org_is_operator not true: {m}"
        assert m.get("company_name") == "Pulse Fitness Ltd", f"company_name {m.get('company_name')}"


# ---- (A2) Regression: other-org portal login STILL impersonates ----

class TestOtherOrgPortalLoginStillImpersonates:
    def test_other_org_portal_login_has_impersonation(self, admin_token):
        # Find a non-Pulse org id
        h = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{API}/master-admin/organizations", headers=h, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"cannot list organizations: {r.status_code}")
        orgs = r.json()
        if isinstance(orgs, dict):
            orgs = orgs.get("organizations") or orgs.get("items") or []
        non_pulse = None
        for o in orgs:
            name = (o.get("name") or o.get("organization_name") or "").lower()
            oid = o.get("id") or o.get("_id") or o.get("organization_id")
            if oid and "pulse" not in name:
                non_pulse = oid
                break
        if not non_pulse:
            pytest.skip("no non-Pulse organization found to test impersonation regression")
        r = requests.post(f"{API}/master-admin/org-portal-login/{non_pulse}", headers=h, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        data = r.json()
        tok = data.get("token") or data.get("access_token") or data.get("impersonation_token")
        assert tok, f"no token: {data}"
        payload = _decode_jwt_payload(tok)
        assert "impersonated_by" in payload, f"missing impersonated_by (should still be impersonation): {payload}"


# ---- (B) MOD estate templates include mod_code ----

class TestModEstateTemplates:
    def test_csv_template_includes_mod_code(self, admin_token):
        r = requests.get(
            f"{API}/master-admin/mod-estate/equipment-template.csv",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        header_line = r.text.splitlines()[0].lower()
        assert "mod_code" in header_line, f"mod_code not in CSV header: {header_line}"

    def test_xlsx_template_includes_mod_code(self, admin_token):
        r = requests.get(
            f"{API}/master-admin/mod-estate/equipment-template.xlsx",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code}: {len(r.content)} bytes"
        # xlsx is a zip; parse it to find header cells
        import io, zipfile
        z = zipfile.ZipFile(io.BytesIO(r.content))
        blob = b""
        for name in z.namelist():
            if name.startswith("xl/") and (name.endswith(".xml")):
                blob += z.read(name)
        assert b"mod_code" in blob.lower(), "mod_code header not found in xlsx contents"


# ---- (B2) AI import analyse captures mod_code ----

class TestAiKitImportModCode:
    CSV_CONTENT = (
        "name,equipment_type,manufacturer,model,MOD Code,serial_number,quantity\n"
        "Treadmill Bay 3,Treadmill,Life Fitness,95T,MOD-Tread,LF-TM-001,1\n"
        "Rower,Rower,Concept2,ModelD,MOD-Row,C2-RW-002,2\n"
    )

    def test_analyse_captures_mod_code(self, admin_token):
        files = {"file": ("mod.csv", self.CSV_CONTENT, "text/csv")}
        r = requests.post(
            f"{API}/master-admin/mod-estate/ai-kit-import/analyse",
            headers={"Authorization": f"Bearer {admin_token}"},
            files=files,
            timeout=60,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:500]}"
        data = r.json()
        # Response may be {tabs:[{rows:[...]}]} or {rows:[...]} etc.
        rows = None
        if isinstance(data, dict):
            if isinstance(data.get("rows"), list) and data["rows"] and isinstance(data["rows"][0], dict) and "name" in data["rows"][0]:
                rows = data["rows"]
            else:
                for key in ("tabs", "sheets", "tables"):
                    v = data.get(key)
                    if isinstance(v, list) and v:
                        inner = v[0].get("rows") if isinstance(v[0], dict) else None
                        if isinstance(inner, list) and inner:
                            rows = inner
                            break
        assert rows, f"no rows in analyse response: {json.dumps(data)[:800]}"
        first = rows[0]
        mc = first.get("mod_code") or first.get("modCode")
        assert mc, f"mod_code missing on row: {first}"
        assert "MOD-Tread" in str(mc), f"expected MOD-Tread, got {mc}"
