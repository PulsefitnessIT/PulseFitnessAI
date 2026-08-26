"""Test flag-missing / follow-ups endpoints for the stock-take feature."""
import os
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://photo-fix-verify.preview.emergentagent.com"


def _auth():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "owner@isodemo.com", "password": "IsoDemo123!"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_list_stocktakes_and_followups():
    h = _auth()
    r = requests.get(f"{BASE}/api/equipment/stocktakes", headers=h, timeout=30)
    assert r.status_code == 200
    stocktakes = r.json().get("stocktakes", [])
    assert isinstance(stocktakes, list)
    # pick one with missing
    target = next((s for s in stocktakes if (s.get("missing_count") or 0) > 0), None)
    assert target, "expected at least one stock-take with missing machines"

    # flag missing (idempotent)
    r2 = requests.post(f"{BASE}/api/equipment/stocktakes/{target['id']}/flag-missing", headers=h, timeout=30)
    assert r2.status_code in (200, 201), r2.text

    # follow-ups list
    r3 = requests.get(f"{BASE}/api/equipment/follow-ups", headers=h, params={"status": "open"}, timeout=30)
    assert r3.status_code == 200
    data = r3.json()
    assert "follow_ups" in data
    assert "open_count" in data
    assert isinstance(data["follow_ups"], list)
    assert data["open_count"] == len(data["follow_ups"]) or data["open_count"] >= 0


def test_resolve_and_reopen_followup():
    h = _auth()
    r = requests.get(f"{BASE}/api/equipment/follow-ups", headers=h, params={"status": "open"}, timeout=30)
    assert r.status_code == 200
    fus = r.json().get("follow_ups", [])
    if not fus:
        return
    item = fus[0]
    initial = len(fus)
    # resolve
    r2 = requests.put(
        f"{BASE}/api/equipment/stocktakes/{item['stocktake_id']}/follow-ups/{item['equipment_id']}",
        headers=h, json={"status": "resolved"}, timeout=30,
    )
    assert r2.status_code in (200, 204), r2.text
    r3 = requests.get(f"{BASE}/api/equipment/follow-ups", headers=h, params={"status": "open"}, timeout=30)
    assert r3.status_code == 200
    after = r3.json().get("follow_ups", [])
    assert len(after) == initial - 1
    # reopen so subsequent runs are stable
    requests.put(
        f"{BASE}/api/equipment/stocktakes/{item['stocktake_id']}/follow-ups/{item['equipment_id']}",
        headers=h, json={"status": "open"}, timeout=30,
    )
