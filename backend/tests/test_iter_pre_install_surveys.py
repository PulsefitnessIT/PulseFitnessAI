"""Pre-Install Site Survey — CRM Corporate feature."""
import io
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE}/api"
CRM_EMAIL = "owner@isodemo.com"
CRM_PASSWORD = "IsoDemo123!"
COMPANY_ID = "iso-cA"
SITE_ID = "iso-demo-site-a"

_TOKEN_CACHE = {}


def _login():
    if _TOKEN_CACHE.get("token"):
        return _TOKEN_CACHE["token"]
    for _ in range(3):
        r = requests.post(f"{API}/crm/auth/login", json={"email": CRM_EMAIL, "password": CRM_PASSWORD})
        if r.status_code == 200:
            j = r.json()
            tok = j.get("token") or j.get("access_token")
            _TOKEN_CACHE["token"] = tok
            return tok
        if r.status_code == 429:
            time.sleep(20)
            continue
        pytest.skip(f"CRM login failed: {r.status_code} {r.text[:200]}")
    pytest.skip("CRM login rate limited")


@pytest.fixture(scope="session")
def hdr():
    return {"Authorization": f"Bearer {_login()}"}


@pytest.fixture(scope="session")
def survey(hdr):
    r = requests.post(f"{API}/crm/site-surveys", headers=hdr,
                      json={"company_id": COMPANY_ID, "site_id": SITE_ID,
                            "survey_type": "new_gym_installation"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["reference"].startswith("PIS-")
    assert d["status"] == "draft"
    return d


def test_schema(hdr):
    r = requests.get(f"{API}/crm/site-surveys/schema", headers=hdr)
    assert r.status_code == 200
    d = r.json()
    assert len(d["sections"]) == 22
    assert len(d["survey_types"]) == 15
    assert len(d["statuses"]) == 12
    assert len(d["readiness_checks"]) == 15
    assert "attachment_categories" in d


def test_create_and_bogus_company_404(hdr, survey):
    assert survey["company_id"] == COMPANY_ID
    r = requests.post(f"{API}/crm/site-surveys", headers=hdr,
                      json={"company_id": "bogus-xxx", "site_id": SITE_ID})
    assert r.status_code == 404


def test_update_and_readiness(hdr, survey):
    sid = survey["id"]
    payload = {"data": {
        "site_details": {"site_name": "Demo HO"},
        "access": {"delivery_entrance": "Rear entrance"},
        "power": {"electrical_supply_available": True},
        "rooms": [{"room_name": "Main gym", "room_length": 10, "room_width": 8}],
        "risks": [{"category": "Access risk", "risk_level": "High", "description": "Narrow stairs"}],
    }}
    r = requests.put(f"{API}/crm/site-surveys/{sid}", headers=hdr, json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["readiness"]["high_risk"] is True

    r2 = requests.get(f"{API}/crm/site-surveys/{sid}/readiness", headers=hdr)
    assert r2.status_code == 200
    rd = r2.json()
    assert rd["high_risk"] is True
    assert any(c.get("critical") for c in rd["checks"])


def test_status_guard(hdr, survey):
    sid = survey["id"]
    r = requests.post(f"{API}/crm/site-surveys/{sid}/status",
                      headers=hdr, json={"status": "approved_for_installation"})
    assert r.status_code == 400
    r = requests.post(f"{API}/crm/site-surveys/{sid}/status",
                      headers=hdr, json={"status": "approved_for_installation", "override": True})
    assert r.status_code == 400
    r = requests.post(f"{API}/crm/site-surveys/{sid}/status",
                      headers=hdr, json={"status": "approved_for_installation",
                                         "override": True, "reason": "Manager approved for testing"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved_for_installation"


def test_handover(hdr, survey):
    sid = survey["id"]
    r = requests.get(f"{API}/crm/site-surveys/{sid}/handover", headers=hdr)
    assert r.status_code == 200
    assert r.json()["reference"] == survey["reference"]
    r2 = requests.get(f"{API}/crm/site-surveys/{sid}/handover.pdf", headers=hdr)
    assert r2.status_code == 200
    assert r2.headers.get("content-type", "").startswith("application/pdf")
    assert r2.content.startswith(b"%PDF")


def test_audit(hdr, survey):
    sid = survey["id"]
    r = requests.get(f"{API}/crm/site-surveys/{sid}/audit", headers=hdr)
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()["events"]}
    for a in ("survey_created", "survey_edited", "status_changed", "pdf_generated"):
        assert a in actions, f"missing audit action {a}: got {actions}"


def test_attachments(hdr, survey):
    sid = survey["id"]
    files = {"file": ("floorplan.pdf", io.BytesIO(b"%PDF-1.4 minimal"), "application/pdf")}
    r = requests.post(f"{API}/crm/site-surveys/{sid}/attachments",
                      headers=hdr, params={"category": "floor_plans"}, files=files)
    assert r.status_code == 200, r.text
    att = r.json()
    assert att["category"] == "floor_plans"
    att_id = att["id"]

    s = requests.get(f"{API}/crm/site-surveys/{sid}", headers=hdr).json()
    assert s["has_floor_plan"] is True
    assert s["attachment_count"] >= 1

    r = requests.get(f"{API}/crm/site-surveys/{sid}/attachments", headers=hdr)
    assert r.status_code == 200
    assert any(a["id"] == att_id for a in r.json()["attachments"])

    r = requests.delete(f"{API}/crm/site-surveys/{sid}/attachments/{att_id}", headers=hdr)
    assert r.status_code == 200


def test_supersede(hdr):
    r = requests.post(f"{API}/crm/site-surveys", headers=hdr,
                      json={"company_id": COMPANY_ID, "site_id": SITE_ID})
    assert r.status_code == 200
    old = r.json()
    r = requests.post(f"{API}/crm/site-surveys/{old['id']}/supersede", headers=hdr)
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["version"] == 2
    assert new["is_current"] is True
    assert new["status"] == "draft"

    old_r = requests.get(f"{API}/crm/site-surveys/{old['id']}", headers=hdr).json()
    assert old_r["status"] == "superseded"
    assert old_r["is_current"] is False
