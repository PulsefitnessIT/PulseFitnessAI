"""Backend tests for MOD Auto-Quote (MOD code trust) and Master Admin company delete.

Covers:
- POST /api/crm/mod-quote/import-spreadsheet trusts MOD Code column
- Row line maps to SingleStation Strength Machine (not Rowing)
- DELETE /api/crm/v2/companies/{id} works for master admin
"""
import os
import io
import uuid
import pytest
import requests

def _read_env():
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_env()).rstrip("/")

MASTER_EMAIL = "admin@pulsefitness.com"
MASTER_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"

CRAIG_EMAIL = "craig.henshall@pulsefitness.com"
CRAIG_PASSWORD = "PulseMOD123!"

XLSX = "/tmp/lease.xlsx"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def platform_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"platform login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def crm_master_token():
    """CRM auth token derived from master admin - via /api/crm/auth/login with same creds."""
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": MASTER_EMAIL, "password": MASTER_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"crm login master failed: {r.status_code} {r.text[:200]}")
    tok = r.json().get("token") or r.json().get("access_token")
    return tok


@pytest.fixture(scope="module")
def crm_craig_token():
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": CRAIG_EMAIL, "password": CRAIG_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"crm login craig failed: {r.status_code} {r.text[:200]}")
    return r.json().get("token") or r.json().get("access_token")


# ---------- MOD Quote import ----------
class TestMODQuoteImport:
    def _import(self, token):
        assert os.path.exists(XLSX), f"{XLSX} missing"
        with open(XLSX, "rb") as f:
            files = {"file": ("lease.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            data = {"contract_type": "A", "year": "1"}
            r = requests.post(
                f"{BASE_URL}/api/crm/mod-quote/import-spreadsheet",
                headers={"Authorization": f"Bearer {token}"},
                files=files,
                data=data,
                timeout=180,
            )
        return r

    def test_import_trusts_mod_code(self, crm_craig_token):
        r = self._import(crm_craig_token)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:500]}"
        body = r.json()
        lines = body.get("lines") or body.get("items") or []
        assert lines, f"no lines returned. body keys={list(body.keys())}"

        # Every line has source == mod_code and needs_review == False
        bad = [ln for ln in lines if ln.get("needs_review")]
        assert not bad, f"needs_review lines: {[(l.get('description'), l.get('mod_code')) for l in bad]}"

        srcs = {ln.get("source") for ln in lines}
        assert srcs == {"mod_code"}, f"unexpected sources: {srcs}"

        # 'Row' -> SingleStation Strength Machine
        row_lines = [ln for ln in lines if (ln.get("description") or "").strip().lower() == "row"]
        assert row_lines, "No 'Row' line found in spreadsheet lines"
        for rl in row_lines:
            svc = (rl.get("rate_card_label") or rl.get("sor_service_line") or rl.get("service_line") or "").lower()
            assert "singlestation" in svc or "single station" in svc or "strength" in svc, \
                f"'Row' didn't map to SingleStation Strength Machine: {rl}"
            assert "rowing" not in svc, f"'Row' mapped to Rowing Machine: {rl}"

        # Shoulder Press / Dual Multi-Pulley -> strength
        for label in ["Shoulder Press", "Dual Multi-Pulley", "Dual Adjustable Pulley"]:
            lns = [ln for ln in lines if label.lower() in (ln.get("description") or "").lower()]
            for ln in lns:
                svc = (ln.get("rate_card_label") or ln.get("sor_service_line") or "").lower()
                assert "strength" in svc or "singlestation" in svc or "single station" in svc, \
                    f"{label} not mapped to strength: {ln}"

        # Wattbike -> Upright Bike
        wb = [ln for ln in lines if "wattbi" in (ln.get("description") or "").lower()]
        for ln in wb:
            svc = (ln.get("rate_card_label") or ln.get("sor_service_line") or "").lower()
            assert "upright" in svc, f"Wattbike not Upright Bike: {ln}"

    def test_import_rejects_no_file(self, crm_craig_token):
        r = requests.post(
            f"{BASE_URL}/api/crm/mod-quote/import-spreadsheet",
            headers={"Authorization": f"Bearer {crm_craig_token}"},
            data={"contract_type": "A", "year": "1"},
            timeout=30,
        )
        assert r.status_code in (400, 422), f"expected 4xx got {r.status_code}"


# ---------- Company delete (master admin) ----------
class TestCompanyDelete:
    def test_master_can_create_and_delete_company(self, crm_master_token):
        name = f"TEST_DeleteMe_{uuid.uuid4().hex[:8]}"
        create = requests.post(
            f"{BASE_URL}/api/crm/v2/companies",
            headers={"Authorization": f"Bearer {crm_master_token}", "Content-Type": "application/json"},
            json={"name": name},
            timeout=30,
        )
        assert create.status_code in (200, 201), f"create failed: {create.status_code} {create.text[:300]}"
        cid = create.json().get("id") or create.json().get("company", {}).get("id")
        assert cid, f"no id in create response: {create.json()}"

        # Delete
        d = requests.delete(
            f"{BASE_URL}/api/crm/v2/companies/{cid}",
            headers={"Authorization": f"Bearer {crm_master_token}"},
            timeout=30,
        )
        assert d.status_code in (200, 204), f"delete failed: {d.status_code} {d.text[:300]}"

        # Verify gone
        g = requests.get(
            f"{BASE_URL}/api/crm/v2/companies/{cid}",
            headers={"Authorization": f"Bearer {crm_master_token}"},
            timeout=30,
        )
        assert g.status_code == 404, f"expected 404 after delete, got {g.status_code}"
