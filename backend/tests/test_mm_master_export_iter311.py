"""Iter311: edit contract_amount + comments on fictional MMT-1006, verify updated Master workbook writes them in original cells."""
from tests._paths import REPO  # noqa: E402
import io
import sys

import openpyxl
import requests

sys.path.insert(0, REPO + "/backend/tests")
from test_mm_api_iter311 import MM, _h, mdb  # noqa: E402


def test_master_export_reflects_edits():
    coord = _h("cm-test-coord")
    c = mdb.crm2_contracts.find_one({"contract_number": "MMT-1006"}, {"_id": 0})
    r = requests.patch(f"{MM}/contracts/{c['id']}", headers=coord,
                       json={"revision": c.get("revision") or 1, "changes": {"contract_amount": 750, "comments": "TEST_edited"}})
    assert r.status_code == 200, r.text
    blob = requests.get(f"{MM}/export/master", headers=coord, timeout=120).content
    ws = openpyxl.load_workbook(io.BytesIO(blob))["Maintenance Database"]
    hdr = [x.value for x in ws[1]]
    row = c["mm_source"]["row"]
    amt = ws.cell(row=row, column=hdr.index("Contract amount (£)") + 1).value
    com = ws.cell(row=row, column=hdr.index("Comments") + 1).value
    a = mdb.crm2_contracts.find_one({"contract_number": "MMT-1001"}, {"_id": 0})
    print("row", row, "amount", amt, "comments", com, "| alpha coord in app:", a.get("coordinator_name"),
          "annual:", a.get("annual_value"), "| 'Contract coordinator' col in workbook:", "Contract coordinator" in hdr)
    assert amt == 750 and com == "TEST_edited"
