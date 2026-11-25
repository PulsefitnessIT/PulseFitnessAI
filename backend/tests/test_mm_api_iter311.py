"""Iteration 311 — Maintenance Master API checks via PUBLIC URL against the mmt_ui_ upload committed in the UI
(run after `python tests/mm_ui_seed.py` / UI commit). Never touches the real upload except read-only + 403 commit check."""
REPO = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))  # noqa: E402
import os
import sys

import pytest
import requests

sys.path.insert(0, REPO + "/backend/tests")
from test_cm_maintenance_master import _h, mdb  # noqa: E402

BASE = os.environ.get("REACT_APP_BACKEND_URL") or open(REPO + "/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
MM = f"{BASE.rstrip('/')}/api/crm/v2/aftersales/maintenance-master"
REAL = "e7a84748-9c0d-4415-ba64-d66c621d3dae"


@pytest.fixture(scope="module")
def coord():
    return _h("cm-test-coord")


@pytest.fixture(scope="module")
def mgr():
    return _h("cm-test-asm")


@pytest.fixture(scope="module")
def alpha():
    c = mdb.crm2_contracts.find_one({"contract_number": "MMT-1001"}, {"_id": 0})
    if not c:
        pytest.skip("MMT-1001 not committed")
    return c


# Uploads list / sicon flag
def test_uploads_list_sicon_off(coord):
    r = requests.get(f"{MM}/uploads", headers=coord)
    assert r.status_code == 200 and r.json()["sicon_writes_enabled"] is False
    assert any(u["id"] == REAL for u in r.json()["uploads"])


# Real upload is untouched, still ready
def test_real_upload_still_ready(coord):
    u = requests.get(f"{MM}/uploads/{REAL}", headers=coord).json()
    assert u["state"] == "ready"
    assert u["summary"]["totals"]["Maintenance Database"]["rows"] == 813


# Coordinator cannot commit (403) — real upload, safe because auth rejects before any work
def test_coordinator_commit_forbidden(coord):
    r = requests.post(f"{MM}/uploads/{REAL}/commit", headers=coord, json={})
    assert r.status_code == 403
    assert mdb.crm2_mm_uploads.find_one({"id": REAL})["state"] == "ready"


# Stale revision → 409
def test_stale_revision_409(coord, alpha):
    cur = requests.get(f"{MM}/contracts/{alpha['id']}", headers=coord).json()["contract"]["revision"]
    r = requests.patch(f"{MM}/contracts/{alpha['id']}", headers=coord,
                       json={"revision": cur - 1 if cur > 1 else cur + 5, "changes": {"comments": "TEST_stale"}})
    assert r.status_code == 409


# Invalid edits
def test_invalid_edits(coord, alpha):
    rev = requests.get(f"{MM}/contracts/{alpha['id']}", headers=coord).json()["contract"]["revision"]
    assert requests.patch(f"{MM}/contracts/{alpha['id']}", headers=coord,
                          json={"revision": rev, "changes": {"annual_value": "abc"}}).status_code == 400
    assert requests.patch(f"{MM}/contracts/{alpha['id']}", headers=coord,
                          json={"revision": rev, "changes": {"end_date": "notadate"}}).status_code == 400
    assert requests.patch(f"{MM}/contracts/{alpha['id']}", headers=coord,
                          json={"revision": rev, "changes": {"status": "active"}}).status_code == 400


# Sicon queue never writes externally
def test_sicon_queue_held(mgr, coord, alpha):
    assert requests.post(f"{MM}/contracts/{alpha['id']}/sicon-queue", headers=coord).status_code == 403
    q = requests.post(f"{MM}/contracts/{alpha['id']}/sicon-queue", headers=mgr).json()
    assert q["state"] == "held_writes_disabled" and q["external_write_attempted"] is False
    rows = requests.get(f"{MM}/sicon-queue", headers=coord).json()
    assert rows["sicon_writes_enabled"] is False
    assert rows["queue"] and all(x["external_write_attempted"] is False for x in rows["queue"])


# Contract list filters
def test_contract_filters(coord):
    assert requests.get(f"{MM}/contracts", headers=coord, params={"q": "MMT Beta"}).json()["count"] == 1
    st = requests.get(f"{MM}/contracts", headers=coord, params={"status": "expired", "q": "MMT"}).json()
    assert st["count"] == 1 and st["contracts"][0]["contract_number"] == "MMT-0901"


# Imported contracts visible in the existing CRM contracts list
def test_imported_visible_in_crm_contracts(coord):
    r = requests.get(f"{BASE.rstrip('/')}/api/crm/v2/contracts", headers=coord, params={"search": "MMT"})
    assert r.status_code == 200
    body = r.json()
    items = body.get("contracts") or body.get("items") or (body if isinstance(body, list) else [])
    print("crm list count", len(items), str(body)[:300])
    assert any(str(c.get("contract_number", "")).startswith("MMT-") for c in items)


# Export endpoints
def test_exports(coord):
    for p in ("/export/current", "/export/master"):
        r = requests.get(f"{MM}{p}", headers=coord, timeout=180)
        assert r.status_code == 200 and r.content[:2] == b"PK", p
