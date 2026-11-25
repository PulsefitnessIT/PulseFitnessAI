# Iter 298 — Pulse parts price list import, engineer price hiding, quote auto-fill from price list, report fallback
import io
import os
import uuid
from datetime import datetime, timezone

import bcrypt
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
PULSE_ORG = "3ece2d0c-57ea-4acd-a6b4-d748478ed117"
OWNER = ("portal@pulsefitness.ltd", "PulseFleet123!")
KNOWN_SKU = "105-275-4"  # price list row: Sales Price 10.45, CV Parts, Orchis


def _env(key):
    for line in open("/app/backend/.env"):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


mdb = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CREATED = {"users": [], "cases": [], "parts_requests": []}


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def owner_h():
    return _login(*OWNER)


@pytest.fixture(scope="module")
def eng_h():
    email = f"test_eng_{uuid.uuid4().hex[:8]}@pulsefitness.test"
    uid = f"TEST_{uuid.uuid4()}"
    mdb.users.insert_one({"id": uid, "email": email, "full_name": "TEST_ Engineer", "organization_id": PULSE_ORG,
                          "role": "engineer", "active": True, "must_change_password": False,
                          "password": bcrypt.hashpw(b"TestEng123!", bcrypt.gensalt()).decode()})
    CREATED["users"].append(uid)
    return _login(email, "TestEng123!")


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    if CREATED["users"]:
        mdb.users.delete_many({"id": {"$in": CREATED["users"]}})
    if CREATED["cases"]:
        mdb.svc_cases.delete_many({"id": {"$in": CREATED["cases"]}})
    if CREATED["parts_requests"]:
        mdb.svc_parts_requests.delete_many({"id": {"$in": CREATED["parts_requests"]}})


def _case(**extra):
    cid = f"TEST_{uuid.uuid4()}"
    now = datetime.now(timezone.utc).isoformat()
    mdb.svc_cases.insert_one({"id": cid, "organization_id": PULSE_ORG, "reference": f"TEST-{cid[-6:]}",
                              "title": "TEST_ price list case", "cover_type": "chargeable", "status": "in_progress",
                              "created_at": now, "updated_at": now, **extra})
    CREATED["cases"].append(cid)
    return cid


def _pr(case_id, sku, qty, status="pending", source=None):
    pid = f"TEST_{uuid.uuid4()}"
    doc = {"id": pid, "organization_id": PULSE_ORG, "case_id": case_id, "part_sku": sku, "qty": qty, "status": status,
           "created_at": datetime.now(timezone.utc).isoformat()}
    if source:
        doc.update(source=source, origin_case_id=case_id)
    mdb.svc_parts_requests.insert_one(doc)
    CREATED["parts_requests"].append(pid)


# --- Price list import -------------------------------------------------------
class TestPriceListImport:
    def test_marker_and_counts(self):
        m = mdb.migrations.find_one({"_id": {"$regex": "^pulse_price_list:"}})
        assert m and m["rows"] == 21174 and PULSE_ORG in m["orgs"]
        assert mdb.svc_parts.count_documents({"organization_id": PULSE_ORG, "price_source": "pulse_price_list"}) == 21174

    def test_no_duplicate_skus(self):
        dup = list(mdb.svc_parts.aggregate([{"$match": {"organization_id": PULSE_ORG}},
                                            {"$group": {"_id": "$sku", "n": {"$sum": 1}}}, {"$match": {"n": {"$gt": 1}}}, {"$limit": 5}]))
        assert dup == []

    def test_owner_sees_prices(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/svc/parts/catalogue", headers=owner_h, params={"search": KNOWN_SKU, "page_size": 5})
        assert r.status_code == 200
        it = next(p for p in r.json()["items"] if p["sku"] == KNOWN_SKU)
        assert it["list_price"] == 10.45 and it["category"] == "CV Parts"
        assert it["manufacturer"] == "Orchis Products Company Ltd" and "cost" in it

    def test_facets_total(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/svc/parts/catalogue/facets", headers=owner_h)
        assert r.status_code == 200 and r.json()["total"] >= 21174
        assert "CV Parts" in r.json()["categories"]

    def test_seed_is_idempotent(self):
        import asyncio
        import sys
        sys.path.insert(0, "/app/backend")
        from tests.conftest import drive_async
        from utils.parts_price_list import seed_pulse_price_list
        assert drive_async(seed_pulse_price_list()) == 0


# --- Engineer price hiding -----------------------------------------------------
class TestEngineerPriceHiding:
    def test_catalogue_hides_prices(self, eng_h):
        r = requests.get(f"{BASE_URL}/api/svc/parts/catalogue", headers=eng_h, params={"search": KNOWN_SKU})
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and all("list_price" not in p and "cost" not in p for p in items)

    def test_get_part_hides_prices(self, eng_h, owner_h):
        pid = mdb.svc_parts.find_one({"organization_id": PULSE_ORG, "sku": KNOWN_SKU})["id"]
        r = requests.get(f"{BASE_URL}/api/svc/parts/catalogue/{pid}", headers=eng_h)
        assert r.status_code == 200 and "list_price" not in r.json() and "cost" not in r.json()
        r2 = requests.get(f"{BASE_URL}/api/svc/parts/catalogue/{pid}", headers=owner_h)
        assert r2.json()["list_price"] == 10.45

    def test_legacy_parts_search_hides_prices(self, eng_h):
        # /api/svc/parts is what the engineer PartsTab search calls
        r = requests.get(f"{BASE_URL}/api/svc/parts", headers=eng_h, params={"search": KNOWN_SKU, "limit": 5})
        assert r.status_code == 200
        parts = r.json()["parts"]
        assert parts, "no results"
        leaked = [p["sku"] for p in parts if "list_price" in p or "cost" in p]
        assert not leaked, f"/api/svc/parts leaks list_price/cost to engineers: {leaked}"

    def test_parts_tab_query_contract(self, eng_h):
        # Frontend PartsTab sends params {q, limit} and reads r.data.items
        r = requests.get(f"{BASE_URL}/api/svc/parts", headers=eng_h, params={"q": KNOWN_SKU, "limit": 12})
        body = r.json()
        assert "items" in body, f"PartsTab reads .items but response keys are {list(body)}"


# --- Quote auto-fill from price list -------------------------------------------
class TestAutoFill:
    def test_parts_request_priced_from_list(self, owner_h):
        cid = _case()
        _pr(cid, KNOWN_SKU, 2)
        _pr(cid, "TBC", 1)
        _pr(cid, KNOWN_SKU, 5, status="rejected")
        r = requests.post(f"{BASE_URL}/api/svc/billing/{cid}/quote/auto-fill", headers=owner_h)
        assert r.status_code == 200, r.text
        parts = [l for l in r.json()["proposed_lines"] if l["kind"] == "part"]
        assert len(parts) == 1
        assert parts[0]["part_sku"] == KNOWN_SKU and parts[0]["qty"] == 2 and parts[0]["unit_amount"] == 10.45

    def test_fallback_cost_markup_when_no_list_price(self, owner_h):
        p = mdb.svc_parts.find_one({"organization_id": PULSE_ORG, "list_price": 0, "cost": {"$gt": 0}})
        if not p:
            pytest.skip("no zero-list-price part with cost")
        cid = _case()
        _pr(cid, p["sku"], 1)
        r = requests.post(f"{BASE_URL}/api/svc/billing/{cid}/quote/auto-fill", headers=owner_h)
        line = [l for l in r.json()["proposed_lines"] if l["kind"] == "part"][0]
        assert line["unit_amount"] == round(p["cost"] * 1.30, 2)

    def test_next_visit_parts_not_billed_on_original(self, owner_h):
        # further_parts_required requests are for the NEXT visit; they should not be billed on the current job
        cid = _case(status="completed")
        _pr(cid, KNOWN_SKU, 1, source="further_parts_required")
        r = requests.post(f"{BASE_URL}/api/svc/billing/{cid}/quote/auto-fill", headers=owner_h)
        parts = [l for l in r.json()["proposed_lines"] if l["kind"] == "part"]
        assert parts == [], f"next-visit parts billed on current job: {parts}"


# --- Service report PDF work_completed fallback ---------------------------------
class TestServiceReportFallback:
    def test_pdf_uses_resolution_notes(self, owner_h):
        from pypdf import PdfReader
        cid = _case(status="completed", resolution_notes="TESTRESNOTES replaced belt",
                    engineer_report={"work_completed": "", "further_work_required": "", "further_parts_required": [],
                                     "start_time": "2026-11-18T09:00:00+00:00", "end_time": "2026-11-18T10:00:00+00:00"})
        r = requests.get(f"{BASE_URL}/api/svc/cases/{cid}/service-report.pdf", headers=owner_h)
        assert r.status_code == 200, r.text[:300]
        text = "".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(r.content)).pages)
        assert "TESTRESNOTES" in text
