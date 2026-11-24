"""Iteration 312 — retest of Maintenance Master fixes (public URL). Run after mm_ui_seed.py seed + commit of the mmt_ upload.
Never commits the real upload (read-only checks only)."""
import io
import os
import sys

import openpyxl
import pytest
import requests

sys.path.insert(0, "/app/backend/tests")
from test_cm_maintenance_master import _h, mdb  # noqa: E402

BASE = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
MM = f"{BASE.rstrip('/')}/api/crm/v2/aftersales/maintenance-master"
REAL = "e7a84748-9c0d-4415-ba64-d66c621d3dae"


@pytest.fixture(scope="module")
def coord():
    return _h("cm-test-coord")


def _c(num):
    c = mdb.crm2_contracts.find_one({"contract_number": num}, {"_id": 0})
    if not c:
        pytest.skip(f"{num} not committed")
    return c


# FIX 1: exception report on the real upload is ~1,339 rows, not 9,406
def test_real_exception_report_size(coord):
    r = requests.get(f"{MM}/uploads/{REAL}/report", headers=coord, params={"kind": "exceptions"}, timeout=180)
    assert r.status_code == 200
    n = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True)["Rows"].max_row - 1
    print("exception rows", n)
    assert 1000 < n < 2000


# FIX 1: committed contracts no longer carry 'approve creation'; exceptions filter only real gaps
def test_exceptions_filter(coord):
    _c("MMT-1001")
    assert mdb.crm2_contracts.count_documents({"contract_number": {"$regex": "^MMT-"}, "mm_exceptions": {"$regex": "approve creation"}}) == 0
    nums = [c["contract_number"] for c in requests.get(f"{MM}/contracts", headers=coord, params={"q": "MMT", "exceptions": True}).json()["contracts"]]
    assert "MMT-1002" in nums and "MMT-1001" not in nums


# Notes do not bump revision numbers in history
def test_note_revision(coord):
    c = _c("MMT-1006")
    rev = requests.get(f"{MM}/contracts/{c['id']}", headers=coord).json()["contract"]["revision"]
    requests.post(f"{MM}/contracts/{c['id']}/notes", headers=coord, json={"text": "TEST_note"}).raise_for_status()
    d = requests.get(f"{MM}/contracts/{c['id']}", headers=coord).json()
    assert d["contract"]["revision"] == rev
    assert [h for h in d["changes"] if h["field"] == "note"][0]["revision"] == rev


# FIX 2: columns still written to cells; changes sheet lists every edit with correct column label
def test_master_export_changes_sheet(coord):
    c = _c("MMT-1002")
    rev = requests.get(f"{MM}/contracts/{c['id']}", headers=coord).json()["contract"]["revision"]
    r = requests.patch(f"{MM}/contracts/{c['id']}", headers=coord, json={"revision": rev, "reason": "TEST_312",
                       "changes": {"contract_amount": 950, "comments": "TEST_cmt", "coordinator_name": "TEST_Coord"}})
    assert r.status_code == 200, r.text
    x = requests.get(f"{MM}/export/master", headers=coord, timeout=180)
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    md = wb["Maintenance Database"]
    hdr = [h.value for h in md[1]]
    row = next(r for r in md.iter_rows(min_row=2) if r[hdr.index("Contract number")].value == "MMT-1002")
    assert float(row[hdr.index("Contract amount (£)")].value) == 950
    assert row[hdr.index("Comments")].value == "TEST_cmt"
    ch = [r for r in wb["Pulse Fitness Pro changes"].iter_rows(min_row=2, values_only=True) if r[2] == "MMT-1002"]
    by = {r[3]: r for r in ch}
    assert {"contract_amount", "comments", "coordinator_name"} <= set(by)
    assert by["comments"][4] == "Comments"
    # coordinator_name has no column in the real/fictional workbook -> must not claim a column
    assert "Contract coordinator" not in hdr
    assert str(by["coordinator_name"][4]).startswith("no column"), by["coordinator_name"]
