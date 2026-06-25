"""Backend tests for the Onboarding CSV import + Head Office attach flow.

Covers:
- /api/master-admin/bulk-import/templates/equipment (template download)
- /api/equipment-import/parse-spreadsheet (CSV parse -> import_id + equipment[])
- /api/master-admin/head-offices (HO picker source)
- /api/master-admin/organizations/{org_id}/sites (branch site create) + confirm import w/ site_id
"""
import io
import os
import uuid
import pytest
import requests

def _read_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    assert token, f"no token in login response: {r.json()}"
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


CSV_BODY = (
    "site_name,supplier,name,equipment_type,manufacturer,model,serial_number,unit_price,location\n"
    "Branch X,Pulse Fitness,Treadmill A,Treadmill,Life Fitness,T7000,SN-TEST-1,3450,Main Floor\n"
    "Branch X,Pulse Fitness,Bike B,Bike,Wattbike,Atom,SN-TEST-2,1800,Cycle Studio\n"
)


def test_template_download(auth_headers):
    r = requests.get(f"{BASE_URL}/api/master-admin/bulk-import/templates/equipment", headers=auth_headers, timeout=30)
    assert r.status_code == 200, f"template status {r.status_code}"
    assert "text/csv" in (r.headers.get("content-type") or "").lower() or r.content.startswith(b"name") or len(r.content) > 0
    assert b"," in r.content or b";" in r.content


def test_parse_spreadsheet(auth_headers):
    files = {"file": ("equipment.csv", io.BytesIO(CSV_BODY.encode("utf-8")), "text/csv")}
    r = requests.post(f"{BASE_URL}/api/equipment-import/parse-spreadsheet", headers=auth_headers, files=files, timeout=60)
    assert r.status_code == 200, f"parse status {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("import_id"), "missing import_id"
    eq = body.get("equipment") or []
    assert len(eq) == 2, f"expected 2 rows, got {len(eq)}: {eq}"
    # Look for first row fields - normalize keys
    first = eq[0]
    flat = " ".join(str(v) for v in first.values()).lower()
    assert "life fitness" in flat or "lifefitness" in flat, f"manufacturer missing: {first}"
    assert "sn-test-1" in flat or "sntest1" in flat, f"serial missing: {first}"


def test_head_offices_list(auth_headers):
    r = requests.get(f"{BASE_URL}/api/master-admin/head-offices", headers=auth_headers, timeout=30)
    assert r.status_code == 200, f"HO list status {r.status_code}: {r.text}"
    body = r.json()
    items = body if isinstance(body, list) else body.get("items") or body.get("head_offices") or body.get("organizations") or []
    assert isinstance(items, list)
    # Just check shape — test env may or may not have seeded HOs
    print(f"head_offices_count={len(items)}")


def test_full_ho_attach_flow(auth_headers):
    # 1) Get a head office org
    r = requests.get(f"{BASE_URL}/api/master-admin/head-offices", headers=auth_headers, timeout=30)
    assert r.status_code == 200
    body = r.json()
    items = body if isinstance(body, list) else body.get("items") or body.get("head_offices") or body.get("organizations") or []
    if not items:
        pytest.skip("No head office orgs seeded in this env")
    ho = items[0]
    org_id = ho.get("organization_id") or ho.get("id") or ho.get("_id")
    assert org_id, f"no org id on HO entry: {ho}"

    # 2) Parse CSV -> import_id
    files = {"file": ("equipment.csv", io.BytesIO(CSV_BODY.encode("utf-8")), "text/csv")}
    pr = requests.post(f"{BASE_URL}/api/equipment-import/parse-spreadsheet", headers=auth_headers, files=files, timeout=60)
    assert pr.status_code == 200, pr.text
    import_id = pr.json().get("import_id")
    assert import_id

    # 3) Create branch site under HO org
    site_name = f"TEST_QA_Branch_{uuid.uuid4().hex[:6]}"
    site_payload = {"name": site_name, "site_name": site_name, "address": "1 Test Way", "postcode": "N1 1AA", "city": "London"}
    sr = requests.post(f"{BASE_URL}/api/master-admin/organizations/{org_id}/sites", headers=auth_headers, json=site_payload, timeout=30)
    assert sr.status_code in (200, 201), f"site create {sr.status_code}: {sr.text}"
    sbody = sr.json()
    site_id = sbody.get("site_id") or sbody.get("id") or (sbody.get("site") or {}).get("site_id") or (sbody.get("site") or {}).get("id")
    assert site_id, f"no site_id returned: {sbody}"

    # 4) Confirm import with target org + site_id
    confirm_payload = {"target_organization_id": org_id, "site_id": site_id}
    cr = requests.post(f"{BASE_URL}/api/equipment-import/confirm/{import_id}", headers=auth_headers, json=confirm_payload, timeout=60)
    assert cr.status_code == 200, f"confirm {cr.status_code}: {cr.text}"
    cbody = cr.json()
    created = cbody.get("created") or cbody.get("count") or cbody.get("imported_count") or len(cbody.get("equipment") or [])
    print(f"confirm_response={cbody}")
    assert created in (2, "2") or (isinstance(created, int) and created >= 1), f"unexpected confirm result: {cbody}"
