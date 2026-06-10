"""
Iter 220 P1 slice 4 — CRM Master Price List backup/export E2E API tests.
Hits the live public REACT_APP_BACKEND_URL via /api/* routes.
"""
import os
import pytest
import requests

def _resolve_base_url():
    u = os.environ.get("REACT_APP_BACKEND_URL")
    if not u:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        u = line.split("=", 1)[1].strip()
                        break
        except OSError:
            pass
    return (u or "").rstrip("/")


BASE_URL = _resolve_base_url()

# Module-scoped state shared across tests (pytest wraps test fns so we can't
# attach attrs to them).
_STATE: dict = {}
CRM_EMAIL = "admin@gymaxisai.com"
CRM_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(
        f"{BASE_URL}/api/crm/auth/login",
        json={"email": CRM_EMAIL, "password": CRM_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"crm login failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    assert tok, f"no token in body: {body}"
    return tok


@pytest.fixture(scope="module")
def auth_headers(crm_token):
    return {"Authorization": f"Bearer {crm_token}"}


# ----- manual export (CSV w/ cost+margin as approver admin) -----

def test_manual_export_csv_with_cost_margin(auth_headers):
    payload = {
        "format": "csv",
        "scope": "live",
        "include_cost": True,
        "include_margin": True,
    }
    r = requests.post(
        f"{BASE_URL}/api/crm/price-list/export",
        json=payload,
        headers=auth_headers,
        timeout=60,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    data = body.get("export", body)
    for k in ("id", "download_url", "filename", "product_count", "size", "format", "sensitive", "expires_at"):
        assert k in data, f"missing key {k} in {data}"
    assert data["format"] == "csv"
    assert data["sensitive"] is True
    assert data["product_count"] >= 1
    # Stash for downstream tests
    _STATE["csv_export"] = data


def test_download_with_token_returns_csv_with_header():
    data = _STATE["csv_export"]
    url = data["download_url"]
    r = requests.get(url, timeout=60, allow_redirects=True)
    assert r.status_code == 200, f"download failed {r.status_code} {r.text[:200]}"
    text = r.text
    first_line = text.splitlines()[0] if text else ""
    assert "," in first_line, f"no csv header? {first_line[:200]}"
    # Cost/margin columns since approver requested them
    lowered = first_line.lower()
    assert "cost" in lowered, f"no cost column in header: {first_line[:200]}"
    assert "margin" in lowered, f"no margin column in header: {first_line[:200]}"


def test_download_wrong_token_404():
    data = _STATE["csv_export"]
    eid = data["id"]
    # Construct bad token URL
    bad = f"{BASE_URL}/api/crm/price-list/export/download/{eid}?token=invalid_token_xxx"
    r = requests.get(bad, timeout=20, allow_redirects=False)
    assert r.status_code == 404, f"expected 404 got {r.status_code}"


def test_download_empty_token_404():
    data = _STATE["csv_export"]
    eid = data["id"]
    bad = f"{BASE_URL}/api/crm/price-list/export/download/{eid}"
    r = requests.get(bad, timeout=20, allow_redirects=False)
    assert r.status_code == 404, f"expected 404 got {r.status_code}"


# ----- manual export xlsx -----

def test_manual_export_xlsx_is_valid_excel(auth_headers):
    payload = {"format": "xlsx", "scope": "live", "include_cost": False, "include_margin": False}
    r = requests.post(
        f"{BASE_URL}/api/crm/price-list/export",
        json=payload,
        headers=auth_headers,
        timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    data = body.get("export", body)
    assert data["format"] == "xlsx"
    assert data["sensitive"] is False
    # download
    r2 = requests.get(data["download_url"], timeout=60)
    assert r2.status_code == 200
    assert r2.content[:2] == b"PK", "xlsx file should start with PK"


# ----- exports list -----

def test_list_exports(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/exports", headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    items = body if isinstance(body, list) else body.get("items") or body.get("exports") or []
    assert isinstance(items, list)
    assert len(items) >= 1
    sample = items[0]
    # Should NOT include raw token nor file content
    flat = str(sample).lower()
    assert "token" not in flat or sample.get("download_token") is None
    assert "content" not in sample


# ----- fresh link endpoint -----

def test_get_export_link_returns_fresh_url(auth_headers):
    eid = _STATE["csv_export"]["id"]
    r = requests.get(
        f"{BASE_URL}/api/crm/price-list/export/{eid}/link",
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    data = body.get("link", body)
    assert "download_url" in data
    assert "expires_at" in data
    # Verify still downloadable
    r2 = requests.get(data["download_url"], timeout=30)
    assert r2.status_code == 200


# ----- backup config GET/PUT -----

def test_backup_config_get_defaults(auth_headers):
    r = requests.get(f"{BASE_URL}/api/crm/price-list/backup/config", headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    cfg = body.get("config", body)
    assert "is_approver" in body or "is_approver" in cfg
    is_approver = body.get("is_approver", cfg.get("is_approver"))
    assert is_approver is True
    # core fields
    for k in ("enabled", "day_of_week", "time", "retention_days", "include_cost", "include_margin"):
        assert k in cfg, f"missing {k} in cfg: {cfg}"


def test_backup_config_put_computes_next_run(auth_headers):
    payload = {
        "enabled": True,
        "day_of_week": 0,
        "time": "06:00",
        "format": "xlsx",
        "retention_days": 90,
        "include_cost": True,
        "include_margin": True,
        "recipients": ["admin@gymaxisai.com"],
    }
    r = requests.put(
        f"{BASE_URL}/api/crm/price-list/backup/config",
        json=payload,
        headers=auth_headers,
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    cfg = body.get("config", body)
    assert cfg.get("enabled") is True
    assert cfg.get("next_run_at"), f"no next_run_at: {cfg}"


# ----- run now -----

def test_backup_run_now(auth_headers):
    r = requests.post(
        f"{BASE_URL}/api/crm/price-list/backup/run",
        headers=auth_headers,
        timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    data = body.get("export", body)
    assert data.get("id")
    assert data.get("format") in ("csv", "xlsx")
    assert data.get("type", "backup") in ("backup", "manual")  # tolerate either label
    assert data.get("download_url")
