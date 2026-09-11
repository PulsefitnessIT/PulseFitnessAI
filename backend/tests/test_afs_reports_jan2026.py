"""Backend tests for Aftersales Profitability & Forecast Reporting (Task 8).

Covers:
  - GET /api/crm/v2/aftersales/reports structure and totals
  - High-claim math for AFSCOMPLDEMO-contract-1 (2025+2026 seed cases)
  - PUT /settings labour_rate & high_claim_ratio persistence + recompute
  - Forecast excludes paid invoices; contract without schedule contributes £0
  - Settings reset after suite to keep demo consistent (75.0 / 0.5)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
CID = "AFSCOMPLDEMO-contract-1"

CRM_EMAIL = "owner@isodemo.com"
CRM_PWD = "IsoDemo123!"


@pytest.fixture(scope="module")
def crm_token():
    r = requests.post(f"{API}/crm/auth/login",
                      json={"email": CRM_EMAIL, "password": CRM_PWD}, timeout=30)
    assert r.status_code == 200, f"CRM login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token")
    assert tok, "No token in CRM login response"
    return tok


@pytest.fixture(scope="module")
def client(crm_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {crm_token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module", autouse=True)
def reset_settings_after(client):
    """Ensure demo integrity — reset settings after tests run."""
    yield
    try:
        client.put(f"{API}/crm/v2/aftersales/settings",
                   json={"labour_rate": 75.0, "high_claim_ratio": 0.5}, timeout=30)
    except Exception:
        pass


# ─── Structure & baseline totals ───────────────────────────────────────
def test_reports_structure_and_totals(client):
    # Baseline reset first so numbers match spec.
    client.put(f"{API}/crm/v2/aftersales/settings",
               json={"labour_rate": 75.0, "high_claim_ratio": 0.5}, timeout=30)

    r = client.get(f"{API}/crm/v2/aftersales/reports", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()

    # Top-level shape
    assert set(data.keys()) >= {"forecast", "high_claim", "generated_at"}
    fc = data["forecast"]
    hc = data["high_claim"]

    # Forecast
    assert fc["active_contracts"] == 2, f"active_contracts={fc['active_contracts']}"
    assert abs(fc["arr"] - 174480) < 1, f"arr={fc['arr']}"
    assert len(fc["months"]) == 12
    # Each month entry shape
    for m in fc["months"]:
        assert "month" in m and "amount" in m
        assert len(m["month"]) == 7 and m["month"][4] == "-"
    assert abs(fc["total_12m"] - 1400) < 1, f"total_12m={fc['total_12m']}"
    assert len(fc["expiring_soon"]) == 2, f"expiring_soon={fc['expiring_soon']}"

    # High-claim
    assert hc["labour_rate"] == 75.0
    assert hc["ratio_threshold"] == 0.5
    rows = {row["contract_id"]: row for row in hc["contracts"]}
    assert CID in rows, "AlphaCo contract missing from high-claim rows"
    row = rows[CID]
    # 1620 min /60 * 75 = 2025 labour ; parts 650 ; total 2675
    assert abs(row["est_claim_cost"] - 2675) < 0.5, row
    assert row["claim_count"] == 4
    assert row["flagged"] is True
    # margin_pct = (4200-2675)/4200*100 ≈ 36.3
    assert abs(row["margin_pct"] - 36.3) < 0.2, row["margin_pct"]
    assert hc["flagged_count"] >= 1


# ─── Editable settings recompute report ────────────────────────────────
def test_settings_editability_and_recompute(client):
    # Update settings
    r = client.put(f"{API}/crm/v2/aftersales/settings",
                   json={"labour_rate": 120, "high_claim_ratio": 0.7}, timeout=30)
    assert r.status_code == 200, r.text
    s = r.json()
    assert float(s["labour_rate"]) == 120.0
    assert float(s["high_claim_ratio"]) == 0.7

    # GET /settings roundtrip
    g = client.get(f"{API}/crm/v2/aftersales/settings", timeout=30).json()
    assert float(g["labour_rate"]) == 120.0
    assert float(g["high_claim_ratio"]) == 0.7

    # Report should recompute
    rep = client.get(f"{API}/crm/v2/aftersales/reports", timeout=30).json()
    rows = {r["contract_id"]: r for r in rep["high_claim"]["contracts"]}
    row = rows[CID]
    # 27h * 120 = 3240 + 650 = 3890
    assert abs(row["est_claim_cost"] - 3890) < 0.5, row
    assert rep["high_claim"]["labour_rate"] == 120.0
    assert rep["high_claim"]["ratio_threshold"] == 0.7
    # 3890 < 4200*0.7 = 2940? 3890 >= 2940 => still flagged
    assert row["flagged"] is True


# ─── Forecast integrity ────────────────────────────────────────────────
def test_forecast_excludes_paid_and_missing_schedule(client):
    # reset settings first
    client.put(f"{API}/crm/v2/aftersales/settings",
               json={"labour_rate": 75.0, "high_claim_ratio": 0.5}, timeout=30)
    rep = client.get(f"{API}/crm/v2/aftersales/reports", timeout=30).json()
    fc = rep["forecast"]
    # 12 sequential months, no duplicates
    months = [m["month"] for m in fc["months"]]
    assert len(months) == len(set(months)) == 12
    # non-negative amounts
    for m in fc["months"]:
        assert m["amount"] >= 0
    # AlphaCo contributes ~£1400 (4 monthlies) — Fire & Rescue has no schedule → £0
    assert abs(fc["total_12m"] - 1400) < 0.5


# ─── PPM cases NOT counted in high-claim ──────────────────────────────
def test_ppm_not_counted_in_high_claim(client):
    """Fire & Rescue contract has PPM/other cases (0 minutes) — should have 0 est_cost or not appear as flagged."""
    rep = client.get(f"{API}/crm/v2/aftersales/reports", timeout=30).json()
    rows = rep["high_claim"]["contracts"]
    # only AlphaCo should be flagged
    flagged = [r for r in rows if r["flagged"]]
    assert all(r["contract_id"] == CID for r in flagged), \
        f"Unexpected flagged contract: {[r['contract_id'] for r in flagged]}"
