"""Iteration 308 retest — Build Quote document import: apply refuses ineligible /
already-covered lines even if the client sends decision 'accepted'.
Fictional data only (prefix ``TEST_bq8api_``), removed by exact ids. Real AI extraction (~15s).
"""
import io
import os

import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
AFS = f"{API}/crm/v2/aftersales"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
T = "TEST_bq8api_"
CUST = f"{T}cust"
CFG = [f"{T}cfg-trd", f"{T}cfg-inel"]
ROWS = ["B9-TRD-300 | B9Run 300 Treadmill | 1 | B9-T-0001 | 5995.00",
        "B9-VIBE-1 | B9Vibe Plate Vibration Trainer | 1 | B9-V-0001 | 2495.00",
        "B9-TRD-300 | B9Run 300 Treadmill | 1 | B9-T-OLD1 | 5995.00",
        "B9-ZZZ-404 | Mystery Cross 4 | 1 | B9-X-0001 | 899.00"]


def _pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    cv = canvas.Canvas(b, pagesize=A4)
    y = 800
    for line in ["Pulse Fitness Limited - Sales Invoice", "Sales Invoice No: SI-B9-5512   Date: 15/01/2026",
                 "Customer: TEST_bq8api Quayside Leisure Ltd   Account: B9ACC-4410",
                 "Deliver to: 3 Quay Street, Falmouth TR11 3QQ", "",
                 "Item code | Description | Qty | Serial numbers | Unit price"] + ROWS + ["", "VAT 20%"]:
        cv.drawString(40, y, line)
        y -= 18
    cv.save()
    return b.getvalue()


@pytest.fixture(scope="module")
def h():
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token('cm-test-coord')}"})
    if r.status_code != 200:
        pytest.skip(f"cross-login failed: {r.text}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def imp(h):
    mdb.organizations.insert_one({"id": CUST, "name": "TEST_bq8api Quayside Leisure"})
    mdb.sites.insert_one({"id": f"{T}site", "organization_id": CUST, "name": "TEST_bq8api Quay Site", "postcode": "TR11 3QQ"})
    mdb.crm2_companies.insert_one({"id": f"{T}co", "organization_id": OP, "name": "TEST_bq8api Quayside Leisure",
                                   "legal_name": "TEST_bq8api Quayside Leisure Ltd", "postcode": "TR11 3QQ",
                                   "sage_account": "B9ACC-4410", "linked_organization_id": CUST})
    mdb.crm2_afs_rate_groups.insert_one({"id": f"{T}rg", "organization_id": OP, "name": f"{T}rg", "standard_pct": 10})
    base = {"organization_id": OP, "contract_eligible": True, "rrp_snapshot": 5000, "rate_group": f"{T}rg",
            "console_type": "", "approval_status": "Approved"}
    mdb.crm2_afs_service_configs.insert_many([
        {**base, "id": CFG[0], "model": "B9Run 300", "reference_sku": "B9-TRD-300"},
        {**base, "id": CFG[1], "model": "B9Vibe Plate", "reference_sku": "B9-VIBE-1", "contract_eligible": False}])
    mdb.crm2_contracts.insert_one({"id": f"{T}live", "organization_id": OP, "company_id": f"{T}co", "status": "active"})
    mdb.equipment.insert_one({"id": f"{T}eq-old", "organization_id": CUST, "site_id": f"{T}site", "model": "B9Run 300",
                              "serial_number": "B9-T-OLD1", "contract_cover": {"contract_id": f"{T}live"},
                              "status": "active", "install_date": "2024-05-01"})
    r = requests.post(f"{AFS}/build-quote/imports", headers=h, data={"doc_type": "sales_invoice"},
                      files={"file": (f"{T}invoice.pdf", _pdf(), "application/pdf")}, timeout=180)
    data = r.json() if r.status_code == 200 else None
    yield data
    if data:
        mdb.crm2_afs_quote_imports.delete_one({"id": data["id"]})
    mdb.equipment.delete_many({"organization_id": CUST})
    mdb.crm2_companies.delete_one({"id": f"{T}co"})
    mdb.crm2_afs_service_configs.delete_many({"id": {"$in": CFG}})
    mdb.crm2_contracts.delete_one({"id": f"{T}live"})
    mdb.sites.delete_one({"id": f"{T}site"})
    mdb.organizations.delete_one({"id": CUST})
    mdb.crm2_afs_rate_groups.delete_one({"id": f"{T}rg"})


def _line(imp, pred):
    return next(ln for ln in imp["lines"] if pred(ln))


def _apply(h, imp, decisions):
    return requests.post(f"{AFS}/build-quote/imports/{imp['id']}/apply", headers=h,
                         json={"site_id": f"{T}site", "decisions": decisions}, timeout=30)


# Extraction + flags
def test_import_flags(imp):
    assert imp, "upload failed"
    assert imp["company_id"] == f"{T}co"
    inel = _line(imp, lambda l: "B9-V-0001" in l["serials"])
    old = _line(imp, lambda l: "B9-T-OLD1" in l["serials"])
    assert "unsupported" in inel["flags"] and inel["decision"] == "excluded"
    assert inel["commercial"]["label"].endswith("Not eligible for maintenance")
    assert "already_covered" in old["flags"] and old["decision"] == "excluded"


def _base_dec(imp):
    unk = _line(imp, lambda l: "B9-X-0001" in l["serials"])
    return [{"line_no": unk["line_no"], "decision": "excluded"}]


# Apply guard: ineligible line forced to accepted
def test_apply_rejects_ineligible_accept(h, imp):
    inel = _line(imp, lambda l: "B9-V-0001" in l["serials"])
    r = _apply(h, imp, _base_dec(imp) + [{"line_no": inel["line_no"], "decision": "accepted"}])
    assert r.status_code == 400 and "not eligible for maintenance" in r.text, r.text
    assert mdb.equipment.count_documents({"organization_id": CUST}) == 1


# Apply guard: ineligible line forced to accepted with an eligible config override
def test_apply_rejects_ineligible_accept_with_override(h, imp):
    inel = _line(imp, lambda l: "B9-V-0001" in l["serials"])
    r = _apply(h, imp, _base_dec(imp) + [{"line_no": inel["line_no"], "decision": "accepted", "config_id": CFG[0]}])
    assert r.status_code == 400 and "not eligible" in r.text, r.text


# Apply guard: already-covered line forced to accepted
def test_apply_rejects_covered_accept(h, imp):
    old = _line(imp, lambda l: "B9-T-OLD1" in l["serials"])
    r = _apply(h, imp, _base_dec(imp) + [{"line_no": old["line_no"], "decision": "accepted"}])
    assert r.status_code == 400 and "already under an active contract" in r.text, r.text


# Gap probe: unknown line accepted by choosing an ineligible config via "Find machine"
def test_apply_rejects_unknown_line_with_ineligible_config(h, imp):
    unk = _line(imp, lambda l: "B9-X-0001" in l["serials"])
    r = _apply(h, imp, [{"line_no": unk["line_no"], "decision": "accepted", "config_id": CFG[1]}])
    created = mdb.equipment.count_documents({"organization_id": CUST, "model": "B9Vibe Plate"})
    assert r.status_code == 400, f"apply accepted an ineligible machine via config override: {r.status_code} {r.text[:200]} created={created}"


# Normal apply still works and creates nothing for excluded lines
def test_apply_default_ok(h, imp):
    mdb.equipment.delete_many({"organization_id": CUST, "id": {"$ne": f"{T}eq-old"}})
    r = _apply(h, imp, _base_dec(imp))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["equipment_created"] == 1 and len(d["asset_ids"]) == 1
    assert mdb.equipment.count_documents({"organization_id": CUST, "serial_number": "B9-V-0001"}) == 0
