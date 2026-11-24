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
    mdb.crm2_afs_rate_groups.insert_one({"id": f"{T}rg", "organization_id": OP, "name": f"{T}rg", "standard_pct": 10})
    mdb.users.insert_one({"id": f"{T}owner", "email": f"{T}owner@example.test", "organization_id": CUST, "role": "owner",
                          "full_name": "BQ Owner", "is_active": True})
    base = {"organization_id": OP, "contract_eligible": True, "rrp_snapshot": 5000, "rate_group": f"{T}rg", "console_type": ""}
    mdb.crm2_afs_service_configs.insert_many([
        {**base, "id": f"{T}cfg-trd", "model": "M2Run 100", "reference_sku": "M2-TRD-100", "approval_status": "Approved"},
        {**base, "id": f"{T}cfg-bike", "model": "M2Bike 20", "reference_sku": "M2-BIKE-20", "approval_status": "Provisional"},
        {**base, "id": f"{T}cfg-var1", "model": "M2Cross", "console_type": "LED", "reference_sku": "M2-VAR", "approval_status": "Approved"},
        {**base, "id": f"{T}cfg-var2", "model": "M2Cross", "console_type": "Touch", "reference_sku": "M2-VAR", "approval_status": "Approved"},
        {**base, "id": f"{T}cfg-inel", "model": "M2Vibe", "reference_sku": "M2-VIBE", "approval_status": "Approved", "contract_eligible": False},
        {**base, "id": f"{T}cfg-notar", "model": "M2Row", "reference_sku": "M2-ROW", "approval_status": "Approved", "rate_group": f"{T}none"}]
        + [{**base, "id": f"{T}cfg-ok{i}", "model": f"M2Strength {i}", "reference_sku": f"M2-STR-{i}", "approval_status": "Approved"} for i in range(5)])
    mdb.crm2_contracts.insert_one({"id": f"{T}live", "organization_id": OP, "company_id": f"{T}co", "status": "active",
                                   "contract_number": "BQ-LIVE-1"})
    mdb.equipment.insert_one({"id": f"{T}eq-old", "organization_id": CUST, "site_id": f"{T}site", "model": "M2Run 100",
                              "serial_number": "BQ-T-OLD1", "contract_cover": {"contract_id": f"{T}live"},
                              "status": "active", "install_date": "2024-05-01"})
    yield
    rx = {"$regex": f"^{T}"}
    imps = [i["id"] for i in mdb.crm2_afs_quote_imports.find({"company_id": rx}, {"id": 1})]
    mdb.crm2_afs_quotes.delete_many({"company_id": rx})
    mdb.crm2_afs_quote_imports.delete_many({"$or": [{"company_id": rx}, {"id": {"$in": imps}}, {"filename": rx}]})
    mdb.equipment.delete_many({"organization_id": CUST})
    for coll in ("crm2_companies", "crm2_afs_service_configs", "crm2_contracts", "sites", "organizations",
                 "crm2_afs_rate_groups", "users"):
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
    new = list(mdb.equipment.find({"id": {"$in": first["asset_ids"]}}))
    assert all(e["status"] == "pending_installation" and e["lifecycle_stage"] == "identified_from_invoice"
               and e["install_verified"] is False and not e.get("install_date") and not e.get("warranty_expiry")
               and e["source_evidence"][0]["sha256"] == imp["sha256"] for e in new)
    r2 = requests.post(f"{AFS}/build-quote/imports/{imp['id']}/apply", headers=h, json={"site_id": f"{T}site", "decisions": decisions}).json()
    assert sorted(r2["asset_ids"]) == sorted(first["asset_ids"]) and r2["equipment_created"] == 0
    assert mdb.equipment.count_documents({"organization_id": CUST}) == 4
    old_eq = mdb.equipment.find_one({"id": f"{T}eq-old"})
    assert old_eq["status"] == "active" and old_eq["install_date"] == "2024-05-01"        # untouched
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


def test_matching_is_separate_from_pricing_approval():
    """5 approved + 2 provisional + 1 model review + 1 unsupported (+1 tariff missing)."""
    from utils.cm_quote_import import match_lines, summarise
    lines = ([{"item_code": f"M2-STR-{i}", "model": f"M2Strength {i}", "quantity": 1} for i in range(5)]
             + [{"item_code": "M2-BIKE-20", "model": "M2Bike 20", "quantity": 1, "serials": ["P1"]},
                {"item_code": "M2-BIKE-20", "model": "M2Bike 20", "quantity": 1, "serials": ["P2"]},
                {"item_code": "M2-VAR", "model": "M2Cross", "quantity": 1},
                {"item_code": "M2-VIBE", "model": "M2Vibe", "quantity": 1},
                {"item_code": "M2-ROW", "model": "M2Row", "quantity": 1}])
    out = _run(lambda: match_lines(OP, lines, "sales_invoice", CUST))
    for ln in out[:5]:
        assert ln["identification"] == "matched" and ln["auto_accepted"] and ln["commercial"]["status"] == "price_approved"
        assert ln["commercial"]["label"] == "Machine matched — Price approved"
    for ln in out[5:7]:   # matched, accepted, but commercially not ready
        assert ln["identification"] == "matched" and ln["auto_accepted"] and ln["decision"] == "accepted"
        assert ln["matched"]["model"] == "M2Bike 20" and ln["commercial"]["status"] == "price_requires_approval"
        assert "no_approved_price" not in ln["flags"] and "price_provisional" not in ln["flags"]
    assert out[7]["identification"] == "review" and out[7]["decision"] == "review" and out[7]["variant_options"]
    assert out[8]["commercial"]["status"] == "not_eligible" and out[8]["decision"] == "excluded"
    assert out[9]["commercial"]["status"] == "tariff_missing" and out[9]["commercial"]["label"].endswith("tariff missing")
    sm = summarise(out)
    assert sm == {"lines": 10, "matched": 9, "needs_identification": 1, "commercially_ready": 5,
                  "price_approval_required": 3, "excluded": 1}


def test_installation_confirmation_and_activation_safeguard():
    from routes.crm_aftersales import _activation_conflicts
    pend = mdb.equipment.find_one({"organization_id": CUST, "lifecycle_stage": "identified_from_invoice"})
    ag = {"id": f"{T}ag", "company_id": f"{T}co-none", "start_date": "2026-01-01", "linked_organization_id": CUST,
          "asset_register": [{"id": pend["id"], "annual": 100}]}
    out = _run(lambda: _activation_conflicts({"organization_id": OP}, ag, None))
    assert [x["type"] for x in out] == ["installation_unverified"]
    tok = {"Authorization": f"Bearer {create_token(f'{T}owner')}"}
    r = requests.patch(f"{API}/equipment/{pend['id']}", headers=tok, json={"install_date": "2026-04-02"})
    assert r.status_code == 200, r.text
    e = mdb.equipment.find_one({"id": pend["id"]})
    assert e["status"] == "active" and e["lifecycle_stage"] == "installed" and e["install_verified"] is True
    assert e["install_date"] == "2026-04-02" and e["install_verified_by"]
    assert _run(lambda: _activation_conflicts({"organization_id": OP}, ag, None)) == []


def test_customer_matching_at_scale_5000():
    import time
    from utils.cm_quote_import import ensure_indexes, match_customer
    rows, sites = [], []
    for i in range(5000):
        multi = i % 50 == 0
        org = f"{T}big-org-{i}"
        rows.append({"id": f"{T}big-{i}", "organization_id": OP, "name": f"Scale Leisure {i:04d}",
                     "legal_name": f"Scale Leisure {i:04d} Ltd", "sage_account": f"SC{i:05d}",
                     "postcode": f"SC{i % 90 + 1} {i % 9}AB", "linked_organization_id": org})
        sites += [{"id": f"{T}big-site-{i}-{k}", "organization_id": org, "name": f"Site {k}",
                   "postcode": f"MS{i % 90 + 1} {k}ZZ"} for k in range(3 if multi else 1)]
    rows += [{"id": f"{T}dup-{k}", "organization_id": OP, "name": "Riverside Gym", "postcode": f"RV{k} 1AA"} for k in range(3)]
    mdb.crm2_companies.insert_many(rows)
    mdb.sites.insert_many(sites)
    try:
        _run(ensure_indexes)
        t = time.perf_counter()
        r = _run(lambda: match_customer(OP, {"account_ref": "SC04321", "customer_name": "Wrong Name"}))
        t_ref = time.perf_counter() - t
        assert r["status"] == "matched" and r["company"]["id"] == f"{T}big-4321"
        t = time.perf_counter()
        r = _run(lambda: match_customer(OP, {"customer_name": "scale leisure 4999 limited", "postcode": "SC50 4AB"}))
        t_name = time.perf_counter() - t
        assert r["status"] == "matched" and r["company"]["id"] == f"{T}big-4999"
        # Multi-site organisation found by a non-primary site postcode.
        r = _run(lambda: match_customer(OP, {"customer_name": "Scale Leisure 4950 Ltd", "postcode": "MS1 2ZZ"}))
        assert r["status"] == "matched" and r["company"]["id"] == f"{T}big-4950" and r["basis"] == "legal name + postcode"
        # Duplicate trading names without postcode evidence → review, never auto-picked.
        r = _run(lambda: match_customer(OP, {"customer_name": "Riverside Gym"}))
        assert r["status"] == "review" and r["company"] is None and len(r["candidates"]) == 3
        assert _run(lambda: match_customer(OP, {"customer_name": "Scale Leisure"}))["company"] is None
        before = mdb.crm2_companies.count_documents({"organization_id": OP})
        h = _crm("cm-test-coord")
        t = time.perf_counter()
        res = requests.get(f"{API}/crm/v2/companies?search=Scale%20Leisure%204987&limit=25", headers=h).json()
        t_search = time.perf_counter() - t
        assert any(c["id"] == f"{T}big-4987" for c in res["companies"])            # far beyond the first 200
        assert mdb.crm2_companies.count_documents({"organization_id": OP}) == before   # nothing created
        print(f"TIMINGS ref={t_ref*1000:.0f}ms name+pc={t_name*1000:.0f}ms crm_search={t_search*1000:.0f}ms")
        assert t_ref < 1.5 and t_name < 1.5
    finally:
        mdb.crm2_companies.delete_many({"id": {"$regex": f"^{T}(big|dup)-"}})
        mdb.sites.delete_many({"id": {"$regex": f"^{T}big-site-"}})
