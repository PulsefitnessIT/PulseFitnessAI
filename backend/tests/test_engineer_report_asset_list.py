# Engineer report fields (svc + MOD jobs + MOD PPM), case detail/signoff, PPM calendar visits, Service Desk asset list (all sites + PDF)
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pypdf import PdfReader

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
BYPASS = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

ADMIN = ("admin@pulsefitness.com", "C2s9yJ3YAhydB4d34-Bykg")
OWNER = ("owner@isodemo.com", "IsoDemo123!")
ADMIN_ORG = "d19de469-645a-4b66-93b1-52455a643f5b"
ADMIN_ID = "1fedcc01-1f53-408a-bc48-017375348536"
SIG_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

CREATED = {"svc_cases": [], "bfpo_ppm_services": [], "equipment": [], "ppm_schedules": []}


def _now(delta_min=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_min)).isoformat()


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{BASE_URL}/api/auth/login", json=body, headers=BYPASS)
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:120]}")
    return {"Authorization": f"Bearer {r.json()['token']}", **BYPASS}


@pytest.fixture(scope="module")
def admin_h():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def owner_h():
    return _login(*OWNER)


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for cid in CREATED["svc_cases"]:
        mdb.svc_cases.delete_one({"id": cid})
        mdb.svc_signatures.delete_many({"case_id": cid})
        mdb.svc_case_events.delete_many({"case_id": cid})
    for sid in CREATED["bfpo_ppm_services"]:
        mdb.bfpo_ppm_services.delete_one({"id": sid})
        mdb.svc_signatures.delete_many({"ppm_service_id": sid})
        mdb.documents.delete_many({"linked_to.type": "ppm_service", "linked_to.id": sid})
    for eid in CREATED["equipment"]:
        mdb.equipment.delete_one({"id": eid})
    for pid in CREATED["ppm_schedules"]:
        mdb.ppm_schedules.delete_one({"id": pid})


def _seed_case(org=ADMIN_ORG, **extra):
    cid = f"TEST_{uuid.uuid4().hex[:10]}"
    doc = {"id": cid, "organization_id": org, "reference": f"TEST-{cid[-6:]}", "status": "on_site",
           "assigned_engineer_id": ADMIN_ID, "assigned_engineer_name": "Master Admin",
           "customer_name": "TEST_Customer", "title": "TEST_ fault", "created_at": _now(-120), "updated_at": _now(-120),
           "case_type": "repair", "priority": "p3"}
    doc.update(extra)
    mdb.svc_cases.insert_one(dict(doc))
    CREATED["svc_cases"].append(cid)
    return cid


def _report(start=-90, end=-10):
    return {"work_completed": "TEST_ replaced belt", "further_work_required": "TEST_ check motor in 3 months",
            "further_parts_required": [{"name": "TEST_ Drive belt", "qty": 2, "sku": "DB-1"},
                                       {"name": "  ", "qty": 5}, {"name": "TEST_ Fuse", "qty": 0}],
            "start_time": _now(start), "end_time": _now(end)}


def _pdf_text(content: bytes) -> str:
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(content)).pages)


# ── Service desk engineer complete ───────────────────────────────
class TestSvcEngineerComplete:
    def test_end_before_start_400(self, admin_h):
        cid = _seed_case()
        requests.post(f"{BASE_URL}/api/svc/engineer/signature", headers=admin_h,
                      json={"case_id": cid, "unavailable": True, "reason": "TEST_ away"})
        r = requests.post(f"{BASE_URL}/api/svc/engineer/jobs/{cid}/complete", headers=admin_h,
                          json={"summary": "TEST_", "report": _report(start=-10, end=-60)})
        assert r.status_code == 400
        assert "End time must be after the start time" in r.text

    def test_signoff_required(self, admin_h):
        cid = _seed_case()
        r = requests.post(f"{BASE_URL}/api/svc/engineer/jobs/{cid}/complete", headers=admin_h,
                          json={"summary": "TEST_ done", "report": _report()})
        assert r.status_code == 400
        assert "sign-off" in r.text.lower()
        assert not (mdb.svc_cases.find_one({"id": cid}) or {}).get("engineer_report")

    def test_complete_with_signature_and_report(self, admin_h):
        cid = _seed_case()
        s = requests.post(f"{BASE_URL}/api/svc/engineer/signature", headers=admin_h,
                          json={"case_id": cid, "signed_by_name": "TEST_ Signer", "image_data": SIG_PNG})
        assert s.status_code == 200, s.text
        r = requests.post(f"{BASE_URL}/api/svc/engineer/jobs/{cid}/complete", headers=admin_h,
                          json={"summary": "TEST_ done summary", "report": _report()})
        assert r.status_code == 200, r.text
        er = mdb.svc_cases.find_one({"id": cid})["engineer_report"]
        assert er["work_completed"] == "TEST_ replaced belt"
        assert er["further_work_required"].startswith("TEST_ check motor")
        assert [p["name"] for p in er["further_parts_required"]] == ["TEST_ Drive belt", "TEST_ Fuse"]
        assert er["further_parts_required"][1]["qty"] == 1
        assert er["start_time"].endswith("+00:00") and er["end_time"].endswith("+00:00")
        TestSvcEngineerComplete.cid = cid

    def test_get_case_includes_report_and_signoff(self, admin_h):
        cid = getattr(TestSvcEngineerComplete, "cid", None) or pytest.skip("no completed case")
        r = requests.get(f"{BASE_URL}/api/svc/cases/{cid}", headers=admin_h)
        assert r.status_code == 200, r.text
        d = r.json()
        case = d.get("case") or d
        assert case["engineer_report"]["work_completed"] == "TEST_ replaced belt"
        assert case["signoff"]["signed_by_name"] == "TEST_ Signer"
        assert case["signoff"]["image_data"].startswith("data:image/png")

    def test_service_report_pdf_has_engineer_report(self, admin_h):
        cid = getattr(TestSvcEngineerComplete, "cid", None) or pytest.skip("no completed case")
        r = requests.get(f"{BASE_URL}/api/svc/cases/{cid}/service-report.pdf", headers=admin_h)
        assert r.status_code == 200, r.text[:200]
        assert r.content[:4] == b"%PDF"
        t = _pdf_text(r.content)
        for s in ("ENGINEER REPORT", "Description of Work Completed", "Further Work Required",
                  "Further Parts Required", "Drive belt", "Start time"):
            assert s in t, f"missing {s}"

    def test_service_report_pdf_legacy_without_report(self, admin_h):
        cid = _seed_case(status="closed", resolution_notes="TEST_ legacy fix")
        r = requests.get(f"{BASE_URL}/api/svc/cases/{cid}/service-report.pdf", headers=admin_h)
        assert r.status_code == 200, r.text[:200]
        t = _pdf_text(r.content)
        assert "ENGINEER REPORT" not in t


# ── MOD / BFPO job + PPM ─────────────────────────────────────────
class TestBfpo:
    def test_bfpo_job_complete_stores_report(self, admin_h):
        cid = _seed_case(org="bfpo-mod-org", status="assigned")
        s = requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/signature", headers=admin_h,
                          json={"unavailable": True, "reason": "TEST_ nobody on site"})
        assert s.status_code == 200, s.text
        bad = requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/complete", headers=admin_h,
                            json={"summary": "TEST_", "safe_and_working": True, "report": _report(-5, -50)})
        assert bad.status_code == 400
        r = requests.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/complete", headers=admin_h,
                          json={"summary": "TEST_ mod done", "safe_and_working": True, "report": _report()})
        assert r.status_code == 200, r.text
        er = mdb.svc_cases.find_one({"id": cid})["engineer_report"]
        assert len(er["further_parts_required"]) == 2
        pdf = requests.get(f"{BASE_URL}/api/bfpo/jobs/{cid}/job-sheet.pdf", headers=admin_h)
        assert pdf.status_code == 200
        assert "ENGINEER REPORT" in _pdf_text(pdf.content)

    def test_bfpo_ppm_complete_report_and_certificate(self, admin_h):
        sid = f"TEST_ppm_{uuid.uuid4().hex[:8]}"
        mdb.bfpo_ppm_services.insert_one({"id": sid, "organization_id": "bfpo-mod-org", "reference": "TEST-PPM-1",
                                          "site_id": "TEST_site", "site_name": "TEST_ Site", "status": "in_progress",
                                          "due_date": _now()[:10], "created_at": _now()})
        CREATED["bfpo_ppm_services"].append(sid)
        nos = requests.post(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/complete", headers=admin_h,
                            json={"notes": "TEST_", "report": _report()})
        assert nos.status_code == 400 and "sign-off" in nos.text.lower()
        r = requests.post(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/complete", headers=admin_h,
                          json={"notes": "TEST_ ppm notes", "report": _report(),
                                "signoff": {"signed_by_name": "TEST_ PPM Signer", "image_data": SIG_PNG}})
        assert r.status_code == 200, r.text
        svc = mdb.bfpo_ppm_services.find_one({"id": sid})
        assert svc["engineer_report"]["work_completed"] == "TEST_ replaced belt"
        cert = requests.get(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/certificate.pdf", headers=admin_h)
        assert cert.status_code == 200
        t = _pdf_text(cert.content)
        assert "ENGINEER REPORT" in t and "Further Parts Required" in t


# ── PPM calendar visit detail ────────────────────────────────────
class TestPpmCalendar:
    def test_schedule_detail_visit_has_report_and_signoff(self, owner_h):
        pid = f"TEST_sch_{uuid.uuid4().hex[:8]}"
        mdb.ppm_schedules.insert_one({"id": pid, "organization_id": "iso-demo-org", "source": "service_desk",
                                      "site_name": "TEST_ Site", "next_pm": _now()[:10], "equipment_ids": []})
        CREATED["ppm_schedules"].append(pid)
        cid = _seed_case(org="iso-demo-org", status="closed", pm_schedule_id=pid,
                         engineer_report={"work_completed": "TEST_ ppm work", "further_work_required": "",
                                          "further_parts_required": [], "start_time": _now(-60), "end_time": _now()})
        mdb.svc_signatures.insert_one({"id": f"TEST_sig_{cid}", "case_id": cid, "signed_by_name": "TEST_ Cal Signer",
                                       "image_data": SIG_PNG, "signed_at": _now(), "unavailable": False})
        r = requests.get(f"{BASE_URL}/api/svc/ppm/schedules/{pid}", headers=owner_h)
        assert r.status_code == 200, r.text
        v = r.json()["visits"][0]
        assert v["engineer_report"]["work_completed"] == "TEST_ ppm work"
        assert v["signoff"]["signed_by_name"] == "TEST_ Cal Signer"
        assert "_id" not in v["signoff"]


# ── Service desk equipment: all sites + asset list PDF ──────────
class TestDeskEquipment:
    def test_all_sites_list(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/svc/desk/customer-equipment",
                         params={"organization_id": "iso-demo-org", "site_id": "all"}, headers=owner_h)
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == mdb.equipment.count_documents({"organization_id": "iso-demo-org"})
        assert all("site_name" in e for e in d["equipment"])
        assert len({e.get("site_id") for e in d["equipment"]}) > 1

    def test_single_site_list(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/svc/desk/customer-equipment",
                         params={"organization_id": "iso-demo-org", "site_id": "iso-demo-site-b"}, headers=owner_h)
        assert r.status_code == 200
        sites = {e.get("site_id") for e in r.json()["equipment"]}
        assert "iso-demo-site-a" not in sites

    def test_pdf_all_sites_with_last_service(self, owner_h):
        eid = f"TEST_eq_{uuid.uuid4().hex[:8]}"
        mdb.equipment.insert_one({"id": eid, "organization_id": "iso-demo-org", "site_id": "iso-demo-site-b",
                                  "name": "TEST_ Treadmill PDF", "serial_number": "TESTSN1", "status": "operational"})
        CREATED["equipment"].append(eid)
        _seed_case(org="iso-demo-org", status="closed", asset_id=eid, reference="TEST-LASTSVC", updated_at=_now(),
                   engineer_report={"work_completed": "TEST_ last service work"})
        r = requests.get(f"{BASE_URL}/api/svc/desk/customer-equipment.pdf",
                         params={"organization_id": "iso-demo-org", "site_id": "all"}, headers=owner_h)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        rd = PdfReader(io.BytesIO(r.content))
        assert rd.pages[0].mediabox.width > rd.pages[0].mediabox.height  # landscape
        t = _pdf_text(r.content)
        assert "Asset List" in t and "All sites" in t
        assert "TEST_ Treadmill PDF" in t and "TEST-LASTSVC" in t and "TEST_ last service work" in t
        assert "Demo Branch B" in t

    def test_pdf_single_site(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/svc/desk/customer-equipment.pdf",
                         params={"organization_id": "iso-demo-org", "site_id": "iso-demo-site-a"}, headers=owner_h)
        assert r.status_code == 200 and r.content[:4] == b"%PDF"

    def test_pdf_unauthorised_org_404(self, owner_h):
        r = requests.get(f"{BASE_URL}/api/svc/desk/customer-equipment.pdf",
                         params={"organization_id": ADMIN_ORG, "site_id": "all"}, headers=owner_h)
        assert r.status_code == 404

    def test_pdf_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/svc/desk/customer-equipment.pdf",
                         params={"organization_id": "iso-demo-org", "site_id": "all"}, headers=BYPASS)
        assert r.status_code in (401, 403)
