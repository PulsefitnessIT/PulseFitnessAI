"""Maintenance Master — role gates (finance read-only, coordinator no commit/sicon) and
updated-workbook export after a re-import (coordinator edits must survive)."""
import io

import openpyxl
import requests

from tests.test_cm_maintenance_master import MM, _h, _upload, _wait, setup, workbook, mdb  # noqa: F401


# Role gates on the Maintenance Master endpoints
def test_role_gates_and_reimport_export():
    coord, mgr, fin = _h("cm-test-coord"), _h("cm-test-asm"), _h("cm-test-fin")
    u = _upload("mmt_roles_v1.xlsx", workbook(), coord)
    assert u["state"] == "ready"
    # finance: read ok, write blocked
    assert requests.get(f"{MM}/uploads", headers=fin).status_code == 200
    assert requests.post(f"{MM}/uploads", headers=fin, json={"filename": "mmt_f.xlsx", "size": 1, "total_chunks": 1}).status_code == 403
    assert requests.post(f"{MM}/uploads/{u['id']}/commit", headers=fin, json={}).status_code == 403
    assert requests.post(f"{MM}/uploads/{u['id']}/commit", headers=mgr, json={"create_missing_customers": True}).status_code == 200
    _wait(u["id"], mgr, ("partial", "committed"))
    alpha = mdb.crm2_contracts.find_one({"contract_number": "MMT-1001"})
    assert requests.patch(f"{MM}/contracts/{alpha['id']}", headers=fin, json={"revision": 1, "changes": {"comments": "x"}}).status_code == 403
    assert requests.post(f"{MM}/contracts/{alpha['id']}/notes", headers=fin, json={"text": "x"}).status_code == 403
    assert requests.post(f"{MM}/contracts/{alpha['id']}/sicon-queue", headers=coord).status_code == 403
    # coordinator edit
    r = requests.patch(f"{MM}/contracts/{alpha['id']}", headers=coord,
                       json={"revision": alpha.get("revision") or 1, "changes": {"coordinator_name": "Casey Edit", "comments": "edited in app"}})
    assert r.status_code == 200, r.text
    # export master (single upload) reflects edit
    wb = openpyxl.load_workbook(io.BytesIO(requests.get(f"{MM}/export/master", headers=coord, timeout=120).content))
    ws = wb["Maintenance Database"]
    hdr = [c.value for c in ws[1]]
    assert ws.cell(row=2, column=hdr.index("Comments") + 1).value == "edited in app"
    # re-import a newer workbook, commit it, export again: the coordinator edit must still be in the updated workbook
    u2 = _upload("mmt_roles_v2.xlsx", workbook(extra_amount=1550.0), coord)
    requests.post(f"{MM}/uploads/{u2['id']}/commit", headers=mgr, json={})
    _wait(u2["id"], mgr, ("partial", "committed"))
    wb = openpyxl.load_workbook(io.BytesIO(requests.get(f"{MM}/export/master", headers=coord, timeout=120).content))
    ws = wb["Maintenance Database"]
    got = ws.cell(row=2, column=hdr.index("Comments") + 1).value
    assert got == "edited in app", f"after re-import the updated workbook lost the app edit (got {got!r})"
