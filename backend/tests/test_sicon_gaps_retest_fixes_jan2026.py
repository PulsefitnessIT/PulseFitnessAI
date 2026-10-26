# Retest of fixes: equipment-gaps site isolation, service-desk staff rule, no-org PATCH,
# bulk placeholder fill, export DD/MM/YYYY dates, AI kit analyse Sicon passthrough.
import io
import os
import time
import uuid
import datetime as dt
import pytest
import requests
import openpyxl
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = ("admin@pulsefitness.com", "C2s9yJ3YAhydB4d34-Bykg")
MANAGER = ("manager@isodemo.com", "IsoDemo123!")
OWNER = ("owner@isodemo.com", "IsoDemo123!")
ORG = "iso-demo-org"
SITE_A, SITE_B = "iso-demo-site-a", "iso-demo-site-b"

_mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = _mc[os.environ.get("DB_NAME", "test_database")]
RUN = uuid.uuid4().hex[:6].upper()
TORG = f"TEST_retest_org_{RUN}"

SICON = ["Sicon Customer Ref", "Location Description", "Sublocation Description",
         "Supplier Reference", "Supplier Name", "Contract Number", "Contract Line No",
         "SLA Name", "Stock Item Code", "Description", "Make", "Model", "Serial Number",
         "Install Date", "Manufacturer Warranty Expiry Date", "Last Service Date",
         "Service Interval", "Service Period", "Next Service Date", "ID Number",
         "Service Template", "Equipment Group", "service_provider", "unit_price",
         "replacement_cost", "length", "width", "height", "MOD-Force",
         "MOD Code", "Asset Tag", "Condition", "Equipment Type", "Manufacture Date"]


def _login(email, pw):
    for _ in range(3):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
        if r.status_code == 200 and r.json().get("token"):
            s = requests.Session()
            s.headers["Authorization"] = f"Bearer {r.json()['token']}"
            return s
        if r.status_code == 429:
            time.sleep(30)
            continue
        break
    pytest.skip(f"login failed {email}: {r.status_code}")


@pytest.fixture(scope="session")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="session")
def manager():
    return _login(*MANAGER)


@pytest.fixture(scope="session")
def owner():
    return _login(*OWNER)


@pytest.fixture(scope="session", autouse=True)
def seed():
    DB.organizations.insert_one({"id": TORG, "name": f"TEST Retest {RUN}", "account_type": "full"})
    docs = [
        {"id": f"TEST_{RUN}_a", "organization_id": ORG, "site_id": SITE_A, "name": f"TEST_{RUN} A", "manufacturer": ""},
        {"id": f"TEST_{RUN}_b", "organization_id": ORG, "site_id": SITE_B, "name": f"TEST_{RUN} B", "manufacturer": ""},
        {"id": f"TEST_{RUN}_noorg", "name": f"TEST_{RUN} NoOrg", "manufacturer": ""},
        {"id": f"TEST_{RUN}_p1", "organization_id": TORG, "name": f"TEST_{RUN} P1", "manufacturer": "UNKNOWN",
         "install_date": "2024-02-15", "last_service_date": "2026-03-01"},
        {"id": f"TEST_{RUN}_p2", "organization_id": TORG, "name": f"TEST_{RUN} P2", "manufacturer": "n/a"},
        {"id": f"TEST_{RUN}_p3", "organization_id": TORG, "name": f"TEST_{RUN} P3", "manufacturer": "Precor"},
    ]
    DB.equipment.insert_many(docs)
    yield
    DB.equipment.delete_many({"id": {"$regex": f"^TEST_{RUN}"}})
    DB.equipment.delete_many({"organization_id": TORG})
    DB.organizations.delete_many({"id": TORG})


# ── Site isolation (manager restricted to site A) ──
class TestSiteIsolation:
    def test_list_all_only_site_a(self, manager):
        r = manager.get(f"{BASE_URL}/api/equipment-gaps", params={"show": "all"})
        assert r.status_code == 200, r.text
        sites = {i.get("site_id") for i in r.json()["items"]}
        assert sites <= {SITE_A}, sites
        assert any(i["id"] == f"TEST_{RUN}_a" for i in r.json()["items"])
        assert {s["id"] for s in r.json()["sites"]} <= {SITE_A}

    def test_site_b_param_403(self, manager):
        r = manager.get(f"{BASE_URL}/api/equipment-gaps", params={"site_id": SITE_B})
        assert r.status_code == 403 and "site_access_denied" in r.text, r.text

    def test_site_b_header_403(self, manager):
        r = manager.get(f"{BASE_URL}/api/equipment-gaps", headers={"X-Site-Id": SITE_B})
        assert r.status_code == 403 and "site_access_denied" in r.text, r.text

    def test_patch_site_b_403(self, manager):
        r = manager.patch(f"{BASE_URL}/api/equipment-gaps/TEST_{RUN}_b", json={"model": "x"})
        assert r.status_code == 403, r.text
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_b"}).get("model") is None

    def test_patch_site_a_ok(self, manager):
        r = manager.patch(f"{BASE_URL}/api/equipment-gaps/TEST_{RUN}_a", json={"model": "M1"})
        assert r.status_code == 200, r.text
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_a"})["model"] == "M1"

    def test_bulk_site_b_403(self, manager):
        r = manager.post(f"{BASE_URL}/api/equipment-gaps/bulk",
                         json={"site_id": SITE_B, "field": "location", "value": "X"})
        assert r.status_code == 403, r.text

    def test_bulk_all_sites_narrowed(self, manager):
        r = manager.post(f"{BASE_URL}/api/equipment-gaps/bulk",
                         json={"field": "equipment_group", "value": f"TESTGRP{RUN}", "ids": [f"TEST_{RUN}_a", f"TEST_{RUN}_b"]})
        assert r.status_code == 200, r.text
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_a"}).get("equipment_group") == f"TESTGRP{RUN}"
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_b"}).get("equipment_group") is None

    def test_export_narrowed(self, manager):
        r = manager.get(f"{BASE_URL}/api/equipment-gaps/export.xlsx")
        assert r.status_code == 200
        rows = list(openpyxl.load_workbook(io.BytesIO(r.content))["Sheet1"].iter_rows(values_only=True))
        names = [row[9] for row in rows[1:]]
        assert f"TEST_{RUN} A" in names and f"TEST_{RUN} B" not in names
        r2 = manager.get(f"{BASE_URL}/api/equipment-gaps/export.xlsx", params={"site_id": SITE_B})
        assert r2.status_code == 403


# ── Customer-tenant service desk user isn't staff ──
class TestServiceDeskTenant:
    def test_scopes_403(self, owner):
        assert owner.get(f"{BASE_URL}/api/equipment-gaps/scopes").status_code == 403

    def test_other_org_403(self, owner):
        assert owner.get(f"{BASE_URL}/api/equipment-gaps", params={"organization_id": TORG}).status_code == 403
        assert owner.patch(f"{BASE_URL}/api/equipment-gaps/TEST_{RUN}_p1", json={"model": "x"}).status_code in (403, 404)
        assert owner.post(f"{BASE_URL}/api/equipment-gaps/bulk",
                          json={"organization_id": TORG, "field": "location", "value": "x"}).status_code == 403

    def test_own_org_ok_sees_both_sites(self, owner):
        r = owner.get(f"{BASE_URL}/api/equipment-gaps", params={"show": "all"})
        assert r.status_code == 200 and r.json()["organization_id"] == ORG
        ids = {i["id"] for i in r.json()["items"]}
        assert {f"TEST_{RUN}_a", f"TEST_{RUN}_b"} <= ids


# ── Staff fixes ──
class TestStaff:
    def test_patch_no_org(self, admin):
        r = admin.patch(f"{BASE_URL}/api/equipment-gaps/TEST_{RUN}_noorg", json={"manufacturer": "Matrix"})
        assert r.status_code == 200, r.text
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_noorg"})["manufacturer"] == "Matrix"

    def test_bulk_placeholder_manufacturer(self, admin):
        r = admin.post(f"{BASE_URL}/api/equipment-gaps/bulk",
                       json={"organization_id": TORG, "field": "manufacturer", "value": "Life Fitness", "only_blank": True})
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 2, r.json()
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_p1"})["manufacturer"] == "Life Fitness"
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_p2"})["manufacturer"] == "Life Fitness"
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_p3"})["manufacturer"] == "Precor"

    def test_export_dates_excel(self, admin):
        r = admin.get(f"{BASE_URL}/api/equipment-gaps/export.xlsx", params={"organization_id": TORG})
        assert r.status_code == 200
        ws = openpyxl.load_workbook(io.BytesIO(r.content))["Sheet1"]
        hdr = [c.value for c in ws[1]]
        assert hdr == SICON
        ci, cl = hdr.index("Install Date") + 1, hdr.index("Last Service Date") + 1
        row = next(r_ for r_ in range(2, ws.max_row + 1) if ws.cell(r_, 10).value == f"TEST_{RUN} P1")
        c = ws.cell(row, ci)
        assert isinstance(c.value, (dt.datetime, dt.date)), type(c.value)
        assert c.value.date() if isinstance(c.value, dt.datetime) else c.value == dt.date(2024, 2, 15)
        assert c.number_format.upper() == "DD/MM/YYYY", c.number_format
        assert ws.cell(row, cl).number_format.upper() == "DD/MM/YYYY"


# ── AI kit analyse with Sicon xlsx ──
def test_ai_kit_analyse_sicon_verbatim(admin):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(SICON)
    r1 = {h: "" for h in SICON}
    r1.update({"Sicon Customer Ref": "REF1", "Location Description": "Main Gym", "Description": f"TEST_{RUN} Treadmill",
               "Make": "Life Fitness", "Model": "95T", "Serial Number": f"TEST_{RUN}_AISN"})
    ws.append([r1[h] for h in SICON])
    buf = io.BytesIO()
    wb.save(buf)
    r = admin.post(f"{BASE_URL}/api/master-admin/mod-estate/ai-kit-import/analyse",
                   files={"file": ("sicon.xlsx", buf.getvalue(),
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, timeout=120)
    assert r.status_code == 200, r.text[:300]
    rows = [x for s in r.json()["sheets"] for x in s["rows"]]
    print(rows)
    row = next(x for x in rows if x.get("serial_number") == f"TEST_{RUN}_AISN")
    assert row["name"] == f"TEST_{RUN} Treadmill", row["name"]
    assert row.get("sub_location", "") == "", row.get("sub_location")
    assert row.get("location") == "Main Gym"
    print("manufacturer:", row.get("manufacturer"), "model:", row.get("model"))
