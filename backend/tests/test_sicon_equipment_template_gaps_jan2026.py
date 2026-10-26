# Sicon equipment template standardisation + Missing Information (equipment gaps) + BFPO engineer asset capture
import io
import os
import csv
import time
import uuid
import pytest
import requests
import openpyxl
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = ("admin@pulsefitness.com", "C2s9yJ3YAhydB4d34-Bykg")
ENGINEER = ("engineer.gib@bfpo.pulsefitness.test", "BfpoEng123!")
OWNER = ("manager@isodemo.com", "IsoDemo123!")  # owner@isodemo.com has is_service_desk=True (=staff)

_mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = _mc[os.environ.get("DB_NAME", "test_database")]

SICON = ["Sicon Customer Ref", "Location Description", "Sublocation Description",
         "Supplier Reference", "Supplier Name", "Contract Number", "Contract Line No",
         "SLA Name", "Stock Item Code", "Description", "Make", "Model", "Serial Number",
         "Install Date", "Manufacturer Warranty Expiry Date", "Last Service Date",
         "Service Interval", "Service Period", "Next Service Date", "ID Number",
         "Service Template", "Equipment Group", "service_provider", "unit_price",
         "replacement_cost", "length", "width", "height", "MOD-Force"]

RUN = uuid.uuid4().hex[:6].upper()
TEST_ORG = f"TEST_sicon_org_{RUN}"


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    for _ in range(2):
        r = requests.post(f"{BASE_URL}/api/auth/login", json=body)
        if r.status_code == 200 and r.json().get("token"):
            return r.json()["token"]
        if r.status_code == 429:
            time.sleep(30)
            continue
        break
    pytest.skip(f"login failed for {email}: {r.status_code} {r.text[:120]}")


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {_login(*ADMIN)}"
    return s


@pytest.fixture(scope="session")
def owner():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {_login(*OWNER)}"
    return s


@pytest.fixture(scope="session")
def engineer():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {_login(*ENGINEER, portal='mod')}"
    return s


@pytest.fixture(scope="session", autouse=True)
def test_org():
    DB.organizations.insert_one({"id": TEST_ORG, "name": f"TEST Sicon Org {RUN}", "account_type": "full"})
    yield TEST_ORG
    DB.equipment.delete_many({"organization_id": TEST_ORG})
    DB.organizations.delete_many({"id": TEST_ORG})
    DB.equipment.delete_many({"serial_number": {"$regex": f"^TEST_{RUN}"}})
    DB.equipment.delete_many({"name": {"$regex": f"^TEST_{RUN}"}})


def _sicon_row(**kw):
    row = {h: "" for h in SICON}
    row.update(kw)
    return row


def _csv_bytes(headers, rows):
    b = io.StringIO()
    w = csv.DictWriter(b, fieldnames=headers)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return b.getvalue().encode()


def _xlsx_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(SICON)
    for r in rows:
        ws.append([r.get(h, "") for h in SICON])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Template downloads ────────────────────────────────────────────────
CSV_TEMPLATE_URLS = [
    "/api/master-admin/bulk-import/templates/equipment",
    "/api/account/import/equipment/template",
    "/api/master-admin/mod-estate/equipment-template.csv",
    "/api/equipment/template/csv",
    "/api/equipment/csv-template",
    "/api/onboarding/equipment-template.csv",
    "/api/svc/engineer/equipment/template-csv",
    "/api/master-admin/equipment/template.csv",
]


@pytest.mark.parametrize("path", CSV_TEMPLATE_URLS)
def test_csv_templates_are_sicon(admin, path):
    r = admin.get(f"{BASE_URL}{path}")
    assert r.status_code == 200, r.text[:200]
    first = r.content.decode("utf-8-sig").splitlines()[0]
    hdr = next(csv.reader([first]))
    assert hdr == SICON, hdr


@pytest.mark.parametrize("path", [
    "/api/master-admin/bulk-import/templates/equipment?format=xlsx",
    "/api/master-admin/mod-estate/equipment-template.xlsx",
])
def test_xlsx_templates_are_sicon(admin, path):
    r = admin.get(f"{BASE_URL}{path}")
    assert r.status_code == 200, r.text[:200]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[0] == "Sheet1"
    assert "How to complete" in wb.sheetnames
    hdr = [c.value for c in wb["Sheet1"][1]]
    assert hdr == SICON


# ── Bulk import (master admin) ────────────────────────────────────────
class TestBulkImport:
    def test_sicon_xlsx_import(self, admin, test_org):
        rows = [_sicon_row(**{"Sicon Customer Ref": "TESTREF1", "Location Description": "Main Gym",
                              "Sublocation Description": "Bay 3", "Description": f"TEST_{RUN} Treadmill",
                              "Make": "Life Fitness", "Model": "95T", "Serial Number": f"TEST_{RUN}_SN1",
                              "Install Date": "15/02/2024", "Last Service Date": "01/03/2026",
                              "Service Interval": "6", "Service Period": "Months",
                              "Stock Item Code": "STK-1", "SLA Name": "Gold", "Equipment Group": "Cardio",
                              "ID Number": "ID-77"})]
        r = admin.post(f"{BASE_URL}/api/master-admin/bulk-import/equipment", params={"organization_id": test_org},
                       files={"file": ("Equipment Import.xlsx", _xlsx_bytes(rows),
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        print(d)
        assert d.get("imported", 0) >= 1, d
        eq = DB.equipment.find_one({"organization_id": test_org, "serial_number": f"TEST_{RUN}_SN1"}, {"_id": 0})
        assert eq, "not persisted"
        print({k: eq.get(k) for k in ("name", "manufacturer", "location", "sub_location", "install_date",
                                      "next_service_date", "next_service_auto", "stock_item_code", "sla_name",
                                      "equipment_group", "id_number", "sicon_customer_ref", "site_id")})
        assert eq["name"] == f"TEST_{RUN} Treadmill"
        assert eq["manufacturer"] == "Life Fitness"
        assert eq["location"] == "Main Gym"
        assert eq.get("sub_location") == "Bay 3"
        assert str(eq.get("install_date"))[:10] == "2024-02-15"
        assert str(eq.get("next_service_date"))[:10] == "2026-09-01"
        assert eq.get("next_service_auto") is True
        assert eq.get("stock_item_code") == "STK-1"
        assert eq.get("sla_name") == "Gold"
        assert eq.get("equipment_group") == "Cardio"
        assert eq.get("id_number") == "ID-77"

    def test_sicon_csv_import(self, admin, test_org):
        rows = [_sicon_row(**{"Location Description": "Studio", "Description": f"TEST_{RUN} Bike",
                              "Make": "Keiser", "Model": "M3i", "Serial Number": f"TEST_{RUN}_SN2"})]
        r = admin.post(f"{BASE_URL}/api/master-admin/bulk-import/equipment", params={"organization_id": test_org},
                       files={"file": ("e.csv", _csv_bytes(SICON, rows), "text/csv")})
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("imported", 0) >= 1, r.json()
        assert DB.equipment.find_one({"organization_id": test_org, "serial_number": f"TEST_{RUN}_SN2"})

    def test_old_format_csv_still_imports(self, admin, test_org):
        hdr = ["name", "equipment_type", "manufacturer", "model", "serial_number"]
        rows = [{"name": f"TEST_{RUN} Rower", "equipment_type": "rower", "manufacturer": "Concept2",
                 "model": "D", "serial_number": f"TEST_{RUN}_SN3"}]
        r = admin.post(f"{BASE_URL}/api/master-admin/bulk-import/equipment", params={"organization_id": test_org},
                       files={"file": ("old.csv", _csv_bytes(hdr, rows), "text/csv")})
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("imported", 0) >= 1, r.json()
        assert DB.equipment.find_one({"organization_id": test_org, "serial_number": f"TEST_{RUN}_SN3"})


# ── Other importers accept Sicon headers ──────────────────────────────
class TestOtherImporters:
    def _rows(self, tag):
        return [_sicon_row(**{"Location Description": "Gym", "Description": f"TEST_{RUN} {tag}",
                              "Make": "Matrix", "Model": "T7", "Serial Number": f"TEST_{RUN}_{tag}"})]

    def test_equipment_import_csv_dash(self, admin):
        r = admin.post(f"{BASE_URL}/api/equipment/import-csv",
                       files={"file": ("e.csv", _csv_bytes(SICON, self._rows("DASH")), "text/csv")})
        print(r.status_code, r.text[:300])
        assert r.status_code == 200
        assert DB.equipment.find_one({"serial_number": f"TEST_{RUN}_DASH"}), "dash importer didn't persist"

    def test_equipment_import_csv_slash(self, admin):
        r = admin.post(f"{BASE_URL}/api/equipment/import/csv",
                       files={"file": ("e.csv", _csv_bytes(SICON, self._rows("SLASH")), "text/csv")})
        print(r.status_code, r.text[:300])
        assert r.status_code == 200
        assert DB.equipment.find_one({"serial_number": f"TEST_{RUN}_SLASH"}), "slash importer didn't persist"

    def test_onboarding_csv_import(self, admin):
        content = _csv_bytes(SICON, self._rows("ONB")).decode()
        r = admin.post(f"{BASE_URL}/api/onboarding/equipment-csv-import", json={"csv_content": content})
        print(r.status_code, r.text[:300])
        assert r.status_code == 200
        eq = DB.equipment.find_one({"serial_number": f"TEST_{RUN}_ONB"})
        assert eq and eq.get("manufacturer") == "Matrix"

    def test_svc_engineer_customer_import(self, admin):
        me = admin.get(f"{BASE_URL}/api/auth/me").json()
        org = (me.get("user") or me).get("organization_id")
        if not org:
            pytest.skip("admin has no org")
        cid = f"TEST_cust_{RUN}"
        DB.svc_engineer_customers.insert_one({"id": cid, "organization_id": org, "name": "TEST cust"})
        try:
            r = admin.post(f"{BASE_URL}/api/svc/engineer/customers/{cid}/equipment/import-csv",
                           files={"file": ("e.csv", _csv_bytes(SICON, self._rows("SVC")), "text/csv")})
            print(r.status_code, r.text[:300])
            assert r.status_code == 200
            assert r.json().get("inserted", 0) >= 1
        finally:
            DB.svc_engineer_customers.delete_one({"id": cid})
            for c in ("svc_engineer_equipment", "equipment"):
                DB[c].delete_many({"serial_number": f"TEST_{RUN}_SVC"})

    def test_master_admin_preview_csv(self, admin):
        r = admin.post(f"{BASE_URL}/api/master-admin/equipment/preview-csv",
                       files={"file": ("e.csv", _csv_bytes(SICON, self._rows("PRV")), "text/csv")})
        print(r.status_code, r.text[:400])
        assert r.status_code == 200
        assert f"TEST_{RUN} PRV" in r.text and "Matrix" in r.text


# ── Missing information API ───────────────────────────────────────────
class TestGaps:
    @pytest.fixture(scope="class", autouse=True)
    def seed(self, test_org):
        docs = [
            {"id": f"TEST_{RUN}_g1", "organization_id": test_org, "name": f"TEST_{RUN} G1", "manufacturer": "UNKNOWN",
             "model": "N/A", "serial_number": "", "location": ""},
            {"id": f"TEST_{RUN}_g2", "organization_id": test_org, "name": f"TEST_{RUN} G2", "manufacturer": "Precor",
             "model": "X", "serial_number": f"TEST_{RUN}_G2SN", "location": "Gym", "sicon_customer_ref": "R1"},
        ]
        DB.equipment.insert_many([dict(d) for d in docs])
        yield

    def test_scopes_staff(self, admin, test_org):
        r = admin.get(f"{BASE_URL}/api/equipment-gaps/scopes")
        assert r.status_code == 200
        s = [x for x in r.json()["scopes"] if x["organization_id"] == test_org]
        assert s and s[0]["incomplete"] >= 1, r.json()["scopes"][:3]

    def test_scopes_non_staff_403(self, owner):
        assert owner.get(f"{BASE_URL}/api/equipment-gaps/scopes").status_code == 403

    def test_list_incomplete_and_all(self, admin, test_org):
        r = admin.get(f"{BASE_URL}/api/equipment-gaps", params={"organization_id": test_org, "show": "incomplete"})
        assert r.status_code == 200
        d = r.json()
        g1 = next(i for i in d["items"] if i["id"] == f"TEST_{RUN}_g1")
        for f in ("manufacturer", "model", "serial_number", "location"):
            assert f in g1["missing"], g1["missing"]
        assert not any(i["id"] == f"TEST_{RUN}_g2" for i in d["items"])
        sm = d["summary"]
        assert {"total", "complete", "incomplete", "percent_complete", "by_field"} <= set(sm)
        ra = admin.get(f"{BASE_URL}/api/equipment-gaps", params={"organization_id": test_org, "show": "all"}).json()
        assert any(i["id"] == f"TEST_{RUN}_g2" and i["missing"] == [] for i in ra["items"])
        assert len(ra["items"]) == ra["summary"]["total"]

    def test_patch_whitelist_and_recompute(self, admin):
        gid = f"TEST_{RUN}_g1"
        bad = admin.patch(f"{BASE_URL}/api/equipment-gaps/{gid}", json={"organization_id": "x"})
        assert bad.status_code == 400
        r = admin.patch(f"{BASE_URL}/api/equipment-gaps/{gid}", json={
            "manufacturer": "Technogym", "model": "Run 700", "serial_number": f"TEST_{RUN}_G1SN",
            "last_service_date": "01/03/2026", "service_interval": "6", "service_period": "months"})
        assert r.status_code == 200, r.text
        it = r.json()["item"]
        assert "manufacturer" not in it["missing"] and "serial_number" not in it["missing"]
        assert it["next_service_date"] == "2026-09-01"
        db_doc = DB.equipment.find_one({"id": gid})
        assert db_doc["manufacturer"] == "Technogym" and db_doc["next_service_date"] == "2026-09-01"

    def test_bulk_fill_location_and_ref(self, admin, test_org):
        r = admin.post(f"{BASE_URL}/api/equipment-gaps/bulk", json={
            "organization_id": test_org, "field": "location", "value": "Main Hall", "only_blank": True})
        assert r.status_code == 200 and r.json()["updated"] >= 1
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_g1"})["location"] == "Main Hall"
        assert DB.equipment.find_one({"id": f"TEST_{RUN}_g2"})["location"] == "Gym"  # only_blank respected
        bad = admin.post(f"{BASE_URL}/api/equipment-gaps/bulk", json={
            "organization_id": test_org, "field": "serial_number", "value": "X"})
        assert bad.status_code == 400
        r2 = admin.post(f"{BASE_URL}/api/equipment-gaps/bulk", json={
            "organization_id": test_org, "field": "sicon_customer_ref", "value": "TESTACC9"})
        assert r2.status_code == 200
        org = DB.organizations.find_one({"id": test_org})
        assert org.get("customer_account_number") == "TESTACC9"

    def test_export_xlsx(self, admin, test_org):
        r = admin.get(f"{BASE_URL}/api/equipment-gaps/export.xlsx", params={"organization_id": test_org})
        assert r.status_code == 200
        ws = openpyxl.load_workbook(io.BytesIO(r.content))["Sheet1"]
        rows = list(ws.iter_rows(values_only=True))
        assert list(rows[0]) == SICON
        assert any(f"TEST_{RUN} G1" in (row[9] or "") for row in rows[1:])

    def test_non_staff_other_org_403(self, owner, test_org):
        assert owner.get(f"{BASE_URL}/api/equipment-gaps", params={"organization_id": test_org}).status_code == 403
        assert owner.patch(f"{BASE_URL}/api/equipment-gaps/TEST_{RUN}_g1", json={"model": "x"}).status_code in (403, 404)  # 404 = cross-org hidden
        assert owner.post(f"{BASE_URL}/api/equipment-gaps/bulk", json={
            "organization_id": test_org, "field": "location", "value": "x"}).status_code == 403

    def test_non_staff_own_org_ok(self, owner):
        r = owner.get(f"{BASE_URL}/api/equipment-gaps")
        assert r.status_code == 200
        assert r.json()["organization_id"] == "iso-demo-org"


# ── AI messy importer commit carries Sicon fields ─────────────────────
def test_ai_kit_commit_carries_sicon_fields(admin):
    site = "mod-site-test-kifaru"
    r = admin.post(f"{BASE_URL}/api/master-admin/mod-estate/ai-kit-import/commit", json={
        "site_id": site, "skip_duplicates": False,
        "rows": [{"name": f"TEST_{RUN} AI Kit", "manufacturer": "Life Fitness", "model": "IC7",
                  "serial_number": f"TEST_{RUN}_AI", "location": "Gym", "install_date": "10/01/2025",
                  "last_service_date": "01/03/2026", "service_interval": "6", "service_period": "Months",
                  "id_number": "AI-1"}]})
    print(r.status_code, r.text[:300])
    assert r.status_code == 200
    eq = DB.equipment.find_one({"serial_number": f"TEST_{RUN}_AI"}, {"_id": 0})
    assert eq, "not persisted"
    print({k: eq.get(k) for k in ("install_date", "last_service_date", "service_interval", "service_period", "next_service_date", "id_number")})
    assert str(eq.get("install_date"))[:10] == "2025-01-10"
    assert str(eq.get("next_service_date"))[:10] == "2026-09-01"
    assert eq.get("id_number") == "AI-1"


# ── BFPO engineer capture ─────────────────────────────────────────────
class TestBfpoEngineer:
    @pytest.fixture(scope="class")
    def job(self, engineer):
        r = engineer.get(f"{BASE_URL}/api/bfpo/jobs")
        assert r.status_code == 200, r.text[:200]
        jobs = [j for j in r.json()["jobs"] if j.get("site_id")]
        if not jobs:
            pytest.skip("no open job with site")
        j = jobs[0]
        site = j["site_id"]
        is_mod = DB.organizations.find_one({"id": site, "account_type": {"$in": ["mod_site", "mod_branch", "mod_org"]}})
        base = {"organization_id": site} if is_mod else {"organization_id": "bfpo-mod-org", "site_id": site}
        eid = f"TEST_{RUN}_bfpo"
        DB.equipment.insert_one({"id": eid, **base, "name": f"TEST_{RUN} BFPO Bike", "manufacturer": "",
                                 "model": "UNKNOWN", "serial_number": "", "location": "Gym",
                                 "sicon_customer_ref": ""})
        yield {"case_id": j["id"], "eid": eid}
        DB.equipment.delete_one({"id": eid})
        DB.svc_case_events.delete_many({"case_id": j["id"], "extra.equipment_id": eid})
        DB.svc_case_events.delete_many({"case_id": j["id"], "meta.equipment_id": eid})

    def test_gaps_list(self, engineer, job):
        r = engineer.get(f"{BASE_URL}/api/bfpo/jobs/{job['case_id']}/equipment-gaps")
        assert r.status_code == 200
        it = next((i for i in r.json()["items"] if i["id"] == job["eid"]), None)
        assert it, "seeded eq not in gaps"
        assert "sicon_customer_ref" not in it["missing"]
        assert {"manufacturer", "model", "serial_number", "install_date"} <= set(it["missing"])

    def test_save_details(self, engineer, job):
        url = f"{BASE_URL}/api/bfpo/jobs/{job['case_id']}/equipment/{job['eid']}/details"
        bad = engineer.post(url, json={"sicon_customer_ref": "X"})
        assert bad.status_code == 400
        r = engineer.post(url, json={"manufacturer": "Wattbike", "model": "Atom", "serial_number": f"TEST_{RUN}_BF",
                                     "install_date": "2023-05-01"})
        assert r.status_code == 200, r.text
        assert r.json()["item"]["missing"] == [] or r.json()["item"]["missing"] == ["sicon_customer_ref"]
        d = DB.equipment.find_one({"id": job["eid"]})
        assert d["manufacturer"] == "Wattbike" and d["details_source"] == "engineer_app"
        r2 = engineer.get(f"{BASE_URL}/api/bfpo/jobs/{job['case_id']}/equipment-gaps")
        assert not any(i["id"] == job["eid"] for i in r2.json()["items"])

    def test_404_other_site(self, engineer, job):
        r = engineer.post(f"{BASE_URL}/api/bfpo/jobs/{job['case_id']}/equipment/TEST_{RUN}_g2/details",
                          json={"model": "x"})
        assert r.status_code == 404
