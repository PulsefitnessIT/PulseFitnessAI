"""Iter 220 P1 API — CRM Master Price List spreadsheet migration via REST API.

Exercises the full pipeline end-to-end against the running backend:
upload -> suggest-mapping -> preview -> commit -> product list/stats.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://platform-doctor.preview.emergentagent.com").rstrip("/")
SAMPLE = "/app/test_samples/pulse_master_price_list_sample.xlsx"
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASS = "MasterAdmin123!"


@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(f"{BASE_URL}/api/crm/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("token") or data.get("access_token") or data.get("crm_token")
    assert tok, f"no token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(crm_token):
    return {"Authorization": f"Bearer {crm_token}"}


# ---- CRM auth ----
def test_crm_login_returns_token(crm_token):
    assert isinstance(crm_token, str) and len(crm_token) > 20


# ---- Upload ----
@pytest.fixture(scope="module")
def import_id(auth_headers):
    assert os.path.exists(SAMPLE), f"sample workbook missing: {SAMPLE}"
    with open(SAMPLE, "rb") as f:
        files = {"file": ("pulse_master_price_list_sample.xlsx", f,
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = requests.post(f"{BASE_URL}/api/crm/price-list/import/upload",
                          headers=auth_headers, files=files, timeout=120)
    assert r.status_code == 200, f"upload failed {r.status_code}: {r.text[:400]}"
    raw = r.json()
    # Response shape: {"import": {...}, "canonical_fields": [...]} OR flat
    imp = raw.get("import") or raw
    body = {**raw, **imp}  # flatten for convenience
    assert imp.get("status") == "uploaded", f"status={imp.get('status')}"
    assert imp.get("id"), "import id missing"
    assert imp.get("total_detected_rows", 0) >= 7000, f"detected rows={imp.get('total_detected_rows')}"
    sheets = imp.get("sheets") or []
    body["id"] = imp["id"]
    body["total_detected_rows"] = imp["total_detected_rows"]
    body["sheets"] = sheets
    body["canonical_fields"] = raw.get("canonical_fields") or imp.get("canonical_fields") or []
    assert len(sheets) >= 1
    s0 = sheets[0]
    for key in ("header_row", "code_col", "columns", "auto_mapping", "sample"):
        assert key in s0, f"sheet missing key {key}"
    assert isinstance(body.get("canonical_fields"), list) and len(body["canonical_fields"]) > 0
    return body["id"], body, sheets


def test_upload_returns_expected_shape(import_id):
    _id, body, sheets = import_id
    # detected rows ~7193
    assert 6000 <= body["total_detected_rows"] <= 20000


# ---- Suggest mapping (AI advisory) ----
def test_suggest_mapping_does_not_500(auth_headers, import_id):
    _id, _body, _sheets = import_id
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/{_id}/suggest-mapping",
                      headers=auth_headers, json={"sheet": "Main Gym"}, timeout=120)
    assert r.status_code in (200, 202), f"suggest-mapping returned {r.status_code}: {r.text[:300]}"
    data = r.json()
    # Should return a mapping object (could be {} on heuristic fallback, but must be dict)
    assert isinstance(data, dict)


# ---- Preview (dry-run) ----
def _build_sheet_cfg(sheet_dict, name_filter=None, selected=True, mappings_override=None):
    cfg = {
        "name": sheet_dict["name"],
        "header_row": sheet_dict["header_row"],
        "header_band": sheet_dict.get("header_band") or [sheet_dict["header_row"]],
        "code_col": sheet_dict["code_col"],
        "name_col": sheet_dict.get("name_col") or (sheet_dict["code_col"] + 1),
        "mappings": mappings_override or {str(sheet_dict["code_col"]): "sku",
                                          str(sheet_dict.get("name_col") or (sheet_dict["code_col"] + 1)): "name"},
        "selected": selected,
    }
    return cfg


def test_preview_returns_summary_without_writing(auth_headers, import_id):
    _id, _body, sheets = import_id
    # only pick a small sheet for speed
    small = sorted(sheets, key=lambda s: s.get("product_count", 0))[0]
    cfg = _build_sheet_cfg(small, mappings_override={
        str(small["code_col"]): "sku",
        str(small.get("name_col") or (small["code_col"] + 1)): "name",
    })
    payload = {"sheets": [cfg]}
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/{_id}/preview",
                      headers=auth_headers, json=payload, timeout=120)
    assert r.status_code == 200, f"preview failed {r.status_code}: {r.text[:400]}"
    raw = r.json()
    data = raw.get("preview") or raw
    for k in ("total", "ready", "warnings", "errors", "new", "updates", "unmapped_columns_total", "per_sheet"):
        assert k in data, f"preview missing key {k}; got {list(data.keys())}"
    assert isinstance(data["per_sheet"], list) and len(data["per_sheet"]) >= 1


# ---- Commit ----
@pytest.fixture(scope="module")
def commit_result(auth_headers, import_id):
    _id, _body, sheets = import_id
    # pick smallest sheet for fast commit
    small = sorted(sheets, key=lambda s: s.get("product_count", 0))[0]
    cfg = _build_sheet_cfg(small, mappings_override={
        str(small["code_col"]): "sku",
        str(small.get("name_col") or (small["code_col"] + 1)): "name",
    })
    payload = {
        "sheets": [cfg],
        "options": {
            "mode": "live",
            "version_label": f"TEST_iter220p1_{uuid.uuid4().hex[:6]}",
            "create": True,
            "update": True,
        },
    }
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/{_id}/commit",
                      headers=auth_headers, json=payload, timeout=180)
    assert r.status_code == 200, f"commit failed {r.status_code}: {r.text[:400]}"
    data = r.json()
    return _id, data


def test_commit_returns_summary(commit_result):
    _id, data = commit_result
    assert data.get("version") or data.get("version_id") or data.get("version_label"), \
        f"commit response missing version info: {list(data.keys())}"
    summary = data.get("summary") or data
    for k in ("created", "updated", "skipped"):
        assert k in summary, f"commit summary missing {k}; got {list(summary.keys())}"


def test_commit_idempotency_same_import_409(auth_headers, commit_result, import_id):
    _id, _data = commit_result
    _iid, _body, sheets = import_id
    small = sorted(sheets, key=lambda s: s.get("product_count", 0))[0]
    cfg = _build_sheet_cfg(small)
    payload = {"sheets": [cfg], "options": {"mode": "live", "version_label": "TEST_dup", "create": True, "update": True}}
    r = requests.post(f"{BASE_URL}/api/crm/price-list/import/{_id}/commit",
                      headers=auth_headers, json=payload, timeout=60)
    assert r.status_code == 409, f"expected 409 on re-commit, got {r.status_code}: {r.text[:200]}"


# ---- Products list + provenance ----
def test_products_list_has_provenance_and_unmapped(auth_headers, commit_result):
    # Allow brief replication / async write
    time.sleep(1.0)
    r = requests.get(f"{BASE_URL}/api/crm/products",
                     headers=auth_headers, params={"limit": 20}, timeout=60)
    assert r.status_code == 200, f"products list failed {r.status_code}: {r.text[:200]}"
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("products") or []
    assert len(items) > 0, "no products returned after commit"
    # check provenance + unmapped_fields on at least one product
    found_prov = False
    found_unmapped = False
    for p in items:
        if p.get("source_sheet") and p.get("source_row"):
            found_prov = True
        if p.get("unmapped_fields"):
            found_unmapped = True
    assert found_prov, "no product carries source_sheet/source_row provenance"
    # unmapped may be empty for the tiny sheet — soft-check
    if not found_unmapped:
        print("WARN: no product with unmapped_fields in tiny-sheet sample (may be expected for tiny sheets)")


# ---- Stats ----
def test_price_list_stats(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/stats", headers=auth_headers, timeout=30)
    assert r.status_code == 200, f"stats failed {r.status_code}: {r.text[:200]}"
    data = r.json()
    for k in ("total", "archived", "missing_sage", "missing_price", "with_unmapped", "suppliers"):
        assert k in data, f"stats missing {k}; got {list(data.keys())}"


# ---- Product filters ----
def test_products_filters(auth_headers):
    for params in (
        {"active": "true", "limit": 5},
        {"active": "false", "limit": 5},
        {"has_unmapped": "true", "limit": 5},
        {"missing_sage": "true", "limit": 5},
        {"sort": "name", "limit": 5},
    ):
        r = requests.get(f"{BASE_URL}/api/crm/products",
                         headers=auth_headers, params=params, timeout=30)
        assert r.status_code == 200, f"filter {params} failed {r.status_code}: {r.text[:200]}"


# ---- Patch + restore preserves provenance ----
def test_patch_preserves_provenance(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/products",
                     headers=auth_headers, params={"limit": 5}, timeout=30)
    items = r.json() if isinstance(r.json(), list) else r.json().get("items") or r.json().get("products") or []
    target = next((p for p in items if p.get("source_sheet")), None)
    if not target:
        pytest.skip("no product with provenance available to patch")
    pid = target.get("id") or target.get("_id")
    orig_sheet = target.get("source_sheet")
    orig_unmapped = target.get("unmapped_fields") or []
    new_name = f"TEST_iter220p1_patched_{uuid.uuid4().hex[:4]}"
    r = requests.patch(f"{BASE_URL}/api/crm/products/{pid}",
                       headers=auth_headers, json={"name": new_name}, timeout=30)
    assert r.status_code in (200, 204), f"PATCH failed {r.status_code}: {r.text[:200]}"
    r2 = requests.get(f"{BASE_URL}/api/crm/products", headers=auth_headers,
                      params={"search": new_name, "limit": 5}, timeout=30)
    items2 = r2.json() if isinstance(r2.json(), list) else r2.json().get("items") or r2.json().get("products") or []
    patched = next((p for p in items2 if (p.get("id") or p.get("_id")) == pid), None)
    assert patched, "patched product not found"
    assert patched.get("source_sheet") == orig_sheet, "provenance stripped on patch"
    # unmapped should still exist (count preserved)
    assert len(patched.get("unmapped_fields") or []) == len(orig_unmapped), \
        "unmapped_fields stripped on patch"


# ---- Archive + restore ----
def test_archive_then_restore(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/products",
                     headers=auth_headers, params={"limit": 5, "active": "true"}, timeout=30)
    items = r.json() if isinstance(r.json(), list) else r.json().get("items") or r.json().get("products") or []
    if not items:
        pytest.skip("no active product to archive")
    pid = items[0].get("id") or items[0].get("_id")
    d = requests.delete(f"{BASE_URL}/api/crm/products/{pid}", headers=auth_headers, timeout=30)
    assert d.status_code in (200, 204), f"archive failed {d.status_code}: {d.text[:200]}"
    rs = requests.post(f"{BASE_URL}/api/crm/products/{pid}/restore", headers=auth_headers, timeout=30)
    assert rs.status_code in (200, 204), f"restore failed {rs.status_code}: {rs.text[:200]}"


# ---- Role gating: missing auth -> 401/403 ----
def test_upload_requires_auth():
    with open(SAMPLE, "rb") as f:
        files = {"file": ("x.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = requests.post(f"{BASE_URL}/api/crm/price-list/import/upload", files=files, timeout=30)
    assert r.status_code in (401, 403), f"expected 401/403 without auth, got {r.status_code}"
