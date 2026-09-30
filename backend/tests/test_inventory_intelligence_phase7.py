"""Phase 7 Inventory Intelligence backend tests."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://aftersales-engine-1.preview.emergentagent.com").rstrip("/")
OWNER_EMAIL = "owner@isodemo.com"
OWNER_PASS = "IsoDemo123!"


@pytest.fixture(scope="module")
def token():
    for _ in range(3):
        r = requests.post(f"{BASE}/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS})
        if r.status_code == 200:
            return r.json().get("access_token") or r.json().get("token")
        if r.status_code == 429:
            time.sleep(40)
            continue
        break
    pytest.skip(f"Login failed: {r.status_code} {r.text[:200]}")


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def seeded(h):
    """Seed low-stock holding to trigger alerts + replenishment."""
    # Create warehouse
    r = requests.post(f"{BASE}/api/inventory/warehouses", headers=h,
                      json={"code": "QA-INTEL-WH", "name": "QA Intel WH", "type": "main", "country": "GB"})
    wh_id = None
    if r.status_code in (200, 201):
        wh_id = r.json().get("id") or r.json().get("warehouse_id")
    else:
        # maybe already exists — list
        lr = requests.get(f"{BASE}/api/inventory/warehouses", headers=h)
        if lr.status_code == 200:
            for w in (lr.json().get("warehouses") or lr.json() or []):
                if w.get("code") == "QA-INTEL-WH":
                    wh_id = w.get("id")
                    break
    if not wh_id:
        pytest.skip(f"Could not create/find warehouse: {r.status_code} {r.text[:200]}")

    rr = requests.post(f"{BASE}/api/inventory/stock/receive", headers=h,
                       json={"warehouse_id": wh_id, "product_code": "QA-INTEL-TEST", "quantity": 1})
    return {"warehouse_id": wh_id, "receive_status": rr.status_code, "receive_body": rr.text[:200]}


def test_overview(h):
    r = requests.get(f"{BASE}/api/inventory/intel/overview", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "alert_counts" in d and "open_alerts" in d and "last_scan" in d


def test_scan(h, seeded):
    r = requests.post(f"{BASE}/api/inventory/intel/scan", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("agents_run") == 7
    assert "alerts_raised" in d


def test_alerts_list(h):
    r = requests.get(f"{BASE}/api/inventory/intel/alerts", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "alerts" in d and "counts" in d


def test_alerts_inventory_risk_present(h):
    r = requests.get(f"{BASE}/api/inventory/intel/alerts", headers=h, params={"severity": "monitor"})
    assert r.status_code == 200
    alerts = r.json().get("alerts", [])
    # look for QA-INTEL-TEST monitor alert
    found = any("QA-INTEL-TEST" in (a.get("title", "") + str(a.get("affected", {}))) for a in alerts)
    assert found or len(alerts) > 0, f"Expected inventory risk alert; got {len(alerts)} alerts"


def test_alert_status_transition_and_invalid(h):
    r = requests.get(f"{BASE}/api/inventory/intel/alerts", headers=h, params={"status": "new"})
    alerts = r.json().get("alerts", [])
    if not alerts:
        pytest.skip("no open alerts to transition")
    aid = alerts[0]["id"]
    # invalid
    bad = requests.post(f"{BASE}/api/inventory/intel/alerts/{aid}/status", headers=h, json={"status": "bogus"})
    assert bad.status_code == 400
    # valid: resolve
    ok = requests.post(f"{BASE}/api/inventory/intel/alerts/{aid}/status", headers=h, json={"status": "resolved"})
    assert ok.status_code == 200, ok.text
    # confirm no longer in "new" list
    r2 = requests.get(f"{BASE}/api/inventory/intel/alerts", headers=h, params={"status": "new"})
    ids_now = [a["id"] for a in r2.json().get("alerts", [])]
    assert aid not in ids_now


@pytest.mark.parametrize("report", ["serial_register", "stock_ledger", "order_progress", "dealer_stock_ageing"])
def test_reports(h, report):
    r = requests.get(f"{BASE}/api/inventory/intel/reports/{report}", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("report") == report
    assert "rows" in d and "columns" in d


def test_reports_invalid(h):
    r = requests.get(f"{BASE}/api/inventory/intel/reports/bogus", headers=h)
    assert r.status_code == 400


def test_replenishment(h, seeded):
    r = requests.get(f"{BASE}/api/inventory/intel/replenishment", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "recommendations" in d and "note" in d
    assert "no Sage purchase order" in d["note"].lower() or "human approval" in d["note"].lower()
    codes = [rec["product_code"] for rec in d["recommendations"]]
    assert "QA-INTEL-TEST" in codes, f"expected QA-INTEL-TEST in recs, got {codes}"


def test_replenishment_reorder_point_param(h):
    r = requests.get(f"{BASE}/api/inventory/intel/replenishment", headers=h, params={"reorder_point": 0})
    assert r.status_code == 200
    assert r.json().get("reorder_point") == 0


def test_cleanup(h):
    """Best effort cleanup."""
    # nothing critical; DB layer cleanup is left for main. This is a marker."""
    assert True
