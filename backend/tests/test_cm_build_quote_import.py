"""Operational Automation Phase 2 — Build Quote from a sales invoice / delivery
note: customer recognition, exact-code machine matching, exceptions, no
duplicate customers/equipment/quotes, unapproved prices cannot be issued.

Fictional data only (prefix ``cm_bq_``). Uses the real document extractor.
"""
import asyncio
import io
import os
import subprocess

import pytest
import requests
from pymongo import MongoClient

from utils.auth import create_token

API = os.environ.get("CM_TEST_API", "http://localhost:8001") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OP = mdb.organizations.find_one({"is_operator_company": True})["id"]
T = "cm_bq_"
AFS = f"{API}/crm/v2/aftersales"
CUST = f"{T}cust"


def _crm(uid):
    r = requests.post(f"{API}/crm/auth/cross-login", headers={"Authorization": f"Bearer {create_token(uid)}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _pdf(title, ref, rows, account="M2ACC-7781"):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    cv = canvas.Canvas(b, pagesize=A4)
    y = 800
    for line in [f"Pulse Fitness Limited — {title}", f"{title} No: {ref}   Date: 12/03/2026",
                 f"Customer: Brightwater Leisure Trust Ltd   Account: {account}",
                 "Deliver to: Brightwater Leisure Centre, 1 Quay Road, Bristol BS1 5TT", "",
                 "Item code | Description | Qty | Serial numbers | Unit price"] + rows + ["", "Carriage 1 75.00", "VAT 20%"]:
        cv.drawString(40, y, line)
        y -= 18
    cv.save()
    return b.getvalue()


ROWS = ["M2-TRD-100 | M2Run 100 Treadmill | 2 | BQ-T-0001, BQ-T-0002 | 5995.00",
        "M2-BIKE-20 | M2Bike 20 Upright Bike | 1 | BQ-B-0001 | 1495.00",
        "M2-ZZZ-999 | Mystery Rower 9 | 1 | BQ-R-0001 | 899.00",
        "M2-BELT-01 | Treadmill running belt (spare part) | 2 |  | 120.00",
        "M2-TRD-100 | M2Run 100 Treadmill | 1 | BQ-T-OLD1 | 5995.00"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    subprocess.run(["python", "scripts/seed_cm_workspace_test_users.py"], cwd="/app/backend",
                   env={**os.environ, "PYTHONPATH": "/app/backend"}, check=True)
    mdb.organizations.insert_one({"id": CUST, "name": "Brightwater Leisure Trust"})
    mdb.sites.insert_one({"id": f"{T}site", "organization_id": CUST, "name": "Brightwater Leisure Centre", "postcode": "BS1 5TT"})
    mdb.crm2_companies.insert_many([
        {"id": f"{T}co", "organization_id": OP, "name": "Brightwater Leisure Trust", "legal_name": "Brightwater Leisure Trust Ltd",
         "postcode": "BS1 5TT", "sage_account": "M2ACC-7781", "linked_organization_id": CUST},
        {"id": f"{T}co2", "organization_id": OP, "name": "Brightwater Leisure Trust (Old)", "postcode": "GL1 1AA"}])
    base = {"organization_id": OP, "contract_eligible": True, "rrp_snapshot": 5000, "rate_group": "", "console_type": ""}
    mdb.crm2_afs_service_configs.insert_many([
        {**base, "id": f"{T}cfg-trd", "model": "M2Run 100", "reference_sku": "M2-TRD-100", "approval_status": "Approved"},
        {**base, "id": f"{T}cfg-bike", "model": "M2Bike 20", "reference_sku": "M2-BIKE-20", "approval_status": "Provisional"},
        {**base, "id": f"{T}cfg-var1", "model": "M2Cross", "console_type": "LED", "reference_sku": "M2-VAR", "approval_status": "Approved"},
        {**base, "id": f"{T}cfg-var2", "model": "M2Cross", "console_type": "Touch", "reference_sku": "M2-VAR", "approval_status": "Approved"}])
    mdb.crm2_contracts.insert_one({"id": f"{T}live", "organization_id": OP, "company_id": f"{T}co", "status": "active",
                                   "contract_number": "BQ-LIVE-1"})
    mdb.equipment.insert_one({"id": f"{T}eq-old", "organization_id": CUST, "site_id": f"{T}site", "model": "M2Run 100",
                              "serial_number": "BQ-T-OLD1", "contract_cover": {"contract_id": f"{T}live"}})
    yield
    rx = {"$regex": f"^{T}"}
    imps = [i["id"] for i in mdb.crm2_afs_quote_imports.find({"company_id": rx}, {"id": 1})]
    mdb.crm2_afs_quotes.delete_many({"company_id": rx})
    mdb.crm2_afs_quote_imports.delete_many({"$or": [{"company_id": rx}, {"id": {"$in": imps}}, {"filename": rx}]})
    mdb.equipment.delete_many({"organization_id": CUST})
    for coll in ("crm2_companies", "crm2_afs_service_configs", "crm2_contracts", "sites", "organizations"):
        mdb[coll].delete_many({"id": rx})


def _run(coro):
    async def go():
        from utils.database import db
        db.client.get_io_loop = asyncio.get_running_loop
        return await coro()
    return asyncio.run(go())


def test_customer_recognition_never_guesses():
    from utils.cm_quote_import import match_customer
    r = _run(lambda: match_customer(OP, {"account_ref": "M2ACC-7781", "customer_name": "Someone Else"}))
    assert r["status"] == "matched" and r["company"]["id"] == f"{T}co" and "account" in r["basis"]
    r = _run(lambda: match_customer(OP, {"customer_name": "Brightwater Leisure Trust Ltd", "postcode": "bs15tt"}))
    assert r["status"] == "matched" and r["company"]["id"] == f"{T}co"
    r = _run(lambda: match_customer(OP, {"customer_name": "Brightwater Leisure", "postcode": "ZZ1 1ZZ"}))
    assert r["status"] == "review" and r["company"] is None and {c["id"] for c in r["candidates"]} >= {f"{T}co", f"{T}co2"}


def test_line_matching_flags():
    from utils.cm_quote_import import match_lines
    lines = [{"item_code": "M2-TRD-100", "model": "M2Run 100", "quantity": 2, "serials": ["A1", "A2"]},
             {"item_code": "M2-VAR", "model": "M2Cross", "quantity": 1, "serials": []},
             {"item_code": "NOPE-1", "description": "Treadmill belt spare", "quantity": 1},
             {"item_code": "NOPE-2", "model": "Mystery Rower", "quantity": 1},
             {"item_code": "M2-TRD-100", "model": "M2Run 100", "quantity": 2, "serials": ["A3"]},
             {"item_code": "M2-TRD-100", "model": "M2Run 100", "quantity": 1, "serials": ["BQ-T-OLD1"]}]
    out = _run(lambda: match_lines(OP, lines, "sales_invoice", CUST))
    assert out[0]["auto_accepted"] and out[0]["decision"] == "accepted" and out[0]["matched"]["basis"] == "exact product code"
    assert "variant_review" in out[1]["flags"] and out[1]["decision"] == "review"
    assert "spare_part" in out[2]["flags"] and out[2]["decision"] == "excluded"
    assert "unknown_code" in out[3]["flags"] and not out[3]["matched"] and out[3]["decision"] == "review"
    assert "serial_mismatch" in out[4]["flags"] and not out[4]["auto_accepted"]
    assert "already_covered" in out[5]["flags"] and out[5]["decision"] == "excluded"
    mi = _run(lambda: match_lines(OP, lines[:1], "maintenance_invoice", CUST))
    assert "evidence_only_price" in mi[0]["flags"]


def test_invoice_to_quote_end_to_end_without_duplicates():
    h = _crm("cm-test-coord")
    pdf = _pdf("Sales Invoice", "SI-BQ-4471", ROWS)
    files = {"file": (f"{T}invoice.pdf", pdf, "application/pdf")}
    r = requests.post(f"{AFS}/build-quote/imports", headers=h, files=files, data={"doc_type": "sales_invoice"}, timeout=120)
    assert r.status_code == 200, r.text
    imp = r.json()
    assert imp["customer"]["status"] == "matched" and imp["company_id"] == f"{T}co"
    assert (imp["extracted"].get("document_ref") or "").endswith("4471")
    by_code = {}
    for ln in imp["lines"]:
        by_code.setdefault(ln["item_code"], []).append(ln)
    trd = [x for x in by_code["M2-TRD-100"] if "BQ-T-0001" in x["serials"]][0]
    assert trd["quantity"] == 2 and trd["serials"] == ["BQ-T-0001", "BQ-T-0002"] and trd["auto_accepted"]
    old = [x for x in by_code["M2-TRD-100"] if "BQ-T-OLD1" in x["serials"]][0]
    assert "already_covered" in old["flags"]
    assert "unknown_code" in by_code["M2-ZZZ-999"][0]["flags"]
    assert "spare_part" in by_code["M2-BELT-01"][0]["flags"]
    assert all("Carriage" not in (x.get("description") or "") for x in imp["lines"])
    # Same document again → same import (no second extraction / record).
    again = requests.post(f"{AFS}/build-quote/imports", headers=h, files=files, data={"doc_type": "sales_invoice"}, timeout=120).json()
    assert again["id"] == imp["id"] and again["existing"]
    # Unknown line still pending → apply refused until decided.
    r = requests.post(f"{AFS}/build-quote/imports/{imp['id']}/apply", headers=h, json={"site_id": f"{T}site"})
    assert r.status_code == 400 and "decision" in r.text
    unknown = by_code["M2-ZZZ-999"][0]["line_no"]
    decisions = [{"line_no": unknown, "decision": "excluded"}]
    r = requests.post(f"{AFS}/build-quote/imports/{imp['id']}/apply", headers=h, json={"site_id": f"{T}site", "decisions": decisions})
    assert r.status_code == 200, r.text
    first = r.json()
    assert len(first["asset_ids"]) == 3 and first["equipment_created"] == 3      # 2 treadmills + 1 bike
    r2 = requests.post(f"{AFS}/build-quote/imports/{imp['id']}/apply", headers=h, json={"site_id": f"{T}site", "decisions": decisions}).json()
    assert sorted(r2["asset_ids"]) == sorted(first["asset_ids"]) and r2["equipment_created"] == 0
    assert mdb.equipment.count_documents({"organization_id": CUST}) == 4
    assert mdb.crm2_companies.count_documents({"name": {"$regex": "Brightwater"}}) == 2   # no new customer

    body = {"company_id": f"{T}co", "site_ids": [f"{T}site"], "asset_ids": first["asset_ids"] + [f"{T}eq-old"],
            "contract_type": "gold", "save": True, "source": "document_import", "source_import_id": imp["id"]}
    q1 = requests.post(f"{AFS}/build-quote-from-estate", headers=h, json=body).json()
    q2 = requests.post(f"{AFS}/build-quote-from-estate", headers=h, json=body).json()
    assert q1["saved_quote_id"] == q2["saved_quote_id"] and q2["existing"]
    assert mdb.crm2_afs_quotes.count_documents({"source_import_id": imp["id"]}) == 1
    q = mdb.crm2_afs_quotes.find_one({"id": q1["saved_quote_id"]})
    assert q["source_documents"][0]["sha256"] == imp["sha256"] and q["source_documents"][0]["doc_type"] == "sales_invoice"
    assert any(e["kind"] == "ALREADY_COVERED" for e in q["exceptions"])
    assert f"{T}eq-old" not in {a["id"] for g in q["grouped_lines"] for a in [{"id": x} for x in g["asset_ids"]]}
    assert q["unpriced_count"] >= 1                                           # provisional bike blocks issue
    r = requests.post(f"{AFS}/quotes/{q['id']}/accept", headers=h, json={})
    assert r.status_code == 400 and "unpriced" in r.text.lower()
    assert mdb.crm2_afs_quote_imports.find_one({"id": imp["id"]})["quote_id"] == q["id"]
    # CRM sees the same customer and the same equipment.
    est = requests.get(f"{AFS}/estate/{T}co", headers=h).json()
    serials = {a.get("serial_number") for s in est["sites"] for a in s["assets"]}
    assert {"BQ-T-0001", "BQ-T-0002", "BQ-B-0001", "BQ-T-OLD1"} <= serials


def test_delivery_note_and_permissions():
    h = _crm("cm-test-coord")
    pdf = _pdf("Delivery Note", "DN-BQ-0912", ["M2-TRD-100 | M2Run 100 Treadmill | 1 | BQ-T-0003 |"])
    r = requests.post(f"{AFS}/build-quote/imports", headers=h, data={"doc_type": "delivery_note"},
                      files={"file": (f"{T}dn.pdf", pdf, "application/pdf")}, timeout=120)
    assert r.status_code == 200, r.text
    dn = r.json()
    assert dn["company_id"] == f"{T}co" and dn["lines"][0]["serials"] == ["BQ-T-0003"] and dn["lines"][0]["auto_accepted"]
    assert requests.post(f"{AFS}/build-quote/imports", headers=_crm("cm-test-fin"), data={"doc_type": "delivery_note"},
                         files={"file": ("x.pdf", pdf, "application/pdf")}).status_code == 403
    assert requests.post(f"{AFS}/build-quote/imports", headers=h, data={"doc_type": "delivery_note"},
                         files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 400
