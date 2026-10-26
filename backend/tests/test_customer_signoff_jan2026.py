"""Customer sign-off on engineer fault / service reports (Jan 2026).

Covers: SVC engineer GET signoff / POST signature validation / complete gate,
service-report PDF sign-off block, calibration certificate sign-off section,
BFPO job signature + complete gate + job-sheet PDF, BFPO PPM complete gate +
certificate PDF.
"""
import io
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient
from pypdf import PdfReader

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
BYPASS = {"x-ratelimit-bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET") or "test-bypass-secret-for-ci-runs-only-2026"}
PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _env_db():
    url, name = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
    if not url:
        for line in open("/app/backend/.env"):
            k, _, v = line.strip().partition("=")
            v = v.strip('"')
            if k == "MONGO_URL":
                url = v
            if k == "DB_NAME":
                name = v
    return MongoClient(url)[name]


DB = _env_db()


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{BASE_URL}/api/auth/login", json=body, headers=BYPASS, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    d = r.json()
    return d.get("token") or d.get("access_token"), d.get("user") or {}


class _Client:
    """Stateless client (no cookie jar — a Set-Cookie from one call must not shadow the bearer)."""
    def __init__(self, tok, user=None):
        self.h = {"Authorization": f"Bearer {tok}", **BYPASS}
        self.user = user or {}

    def get(self, url, **kw):
        return requests.get(url, headers=self.h, timeout=60, **kw)

    def post(self, url, **kw):
        return requests.post(url, headers=self.h, timeout=60, **kw)


def _pdf_text(content: bytes) -> str:
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(content)).pages)


@pytest.fixture
def admin():
    # function-scoped: the gymaxisai admin user doc gets re-seeded (new id) by other suites
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    return _Client(tok, user)


@pytest.fixture
def svc_case(admin):
    cid = f"TEST_sig_{uuid.uuid4().hex[:8]}"
    DB.svc_cases.insert_one({
        "id": cid, "organization_id": admin.user["organization_id"], "reference": f"TSIG-{cid[-4:]}",
        "title": "TEST sign-off", "status": "on_site", "assigned_engineer_id": admin.user["id"],
        "customer_name": "Site Manager", "customer_email": "TEST_site.contact@example.com",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield cid
    DB.svc_cases.delete_one({"id": cid})
    DB.svc_signatures.delete_many({"case_id": cid})
    DB.svc_case_calibrations.delete_many({"case_id": cid})
    DB.svc_case_events.delete_many({"case_id": cid})


# ─── SVC engineer app ──────────────────────────────────────────────
class TestSvcSignoff:
    def test_get_signoff_returns_site_contact(self, admin, svc_case):
        r = admin.get(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/signoff")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["site_contact"]["email"] == "test_site.contact@example.com"
        assert d["site_contact"]["name"] == "Site Manager"
        assert d["signoff"] is None

    def test_get_signoff_404(self, admin):
        r = admin.get(f"{BASE_URL}/api/svc/engineer/jobs/nope-{uuid.uuid4().hex[:6]}/signoff")
        assert r.status_code == 404

    def test_complete_blocked_without_signoff(self, admin, svc_case):
        r = admin.post(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/complete",
                       json={"summary": "done", "target": "repaired"})
        assert r.status_code == 400
        assert "Customer sign-off is required" in r.json()["detail"]
        assert DB.svc_cases.find_one({"id": svc_case})["status"] == "on_site"

    @pytest.mark.parametrize("body,msg", [
        ({"image_data": PNG}, "printed name"),
        ({"signed_by_name": "Joe"}, "printed name"),
        ({"signed_by_name": "Joe", "image_data": PNG, "signed_by_email": "not-an-email"}, "valid email"),
        ({"unavailable": True}, "reason"),
        ({"unavailable": True, "reason": "   "}, "reason"),
    ])
    def test_signature_validation(self, admin, svc_case, body, msg):
        r = admin.post(f"{BASE_URL}/api/svc/engineer/signature", json={"case_id": svc_case, **body})
        assert r.status_code == 400, r.text
        assert msg in r.json()["detail"]
        assert DB.svc_signatures.count_documents({"case_id": svc_case}) == 0

    def test_signature_requires_case_id_and_existing_case(self, admin):
        assert admin.post(f"{BASE_URL}/api/svc/engineer/signature", json={"signed_by_name": "x", "image_data": PNG}).status_code == 400
        assert admin.post(f"{BASE_URL}/api/svc/engineer/signature",
                          json={"case_id": "missing-xyz", "signed_by_name": "x", "image_data": PNG}).status_code == 404

    def test_sign_then_pdf_then_complete(self, admin, svc_case):
        r = admin.post(f"{BASE_URL}/api/svc/engineer/signature", json={
            "case_id": svc_case, "signed_by_name": "Jane Customer", "signed_by_email": "TEST_Jane@Example.com",
            "signed_by_role": "Duty Manager", "image_data": PNG})
        assert r.status_code == 200, r.text
        sig = r.json()
        assert sig["signed_by_name"] == "Jane Customer"
        assert sig["signed_by_email"] == "test_jane@example.com"
        assert sig["unavailable"] is False and "_id" not in sig

        g = admin.get(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/signoff").json()
        assert g["signoff"]["signed_by_name"] == "Jane Customer"
        assert "image_data" not in g["signoff"]

        pdf = admin.get(f"{BASE_URL}/api/svc/cases/{svc_case}/service-report.pdf")
        assert pdf.status_code == 200, pdf.text[:300]
        txt = _pdf_text(pdf.content)
        assert "Jane Customer" in txt and "test_jane@example.com" in txt
        assert "CUSTOMER SIGN-OFF" in txt.upper()

        c = admin.post(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/complete",
                       json={"summary": "Replaced belt", "target": "repaired"})
        assert c.status_code == 200, c.text
        assert c.json()["status"] == "repaired"
        time.sleep(6)  # background email task
        case = DB.svc_cases.find_one({"id": svc_case}, {"_id": 0})
        assert case["status"] == "repaired"
        print("service_report_sent_to =", case.get("service_report_sent_to"))
        if case.get("service_report_sent_to"):
            assert case["service_report_sent_to"] == "test_jane@example.com"

    def test_unavailable_then_pdf_and_complete_no_email(self, admin, svc_case):
        r = admin.post(f"{BASE_URL}/api/svc/engineer/signature",
                       json={"case_id": svc_case, "unavailable": True, "reason": "Site unmanned on arrival"})
        assert r.status_code == 200, r.text
        assert r.json()["unavailable"] is True
        assert r.json()["unavailable_reason"] == "Site unmanned on arrival"
        txt = _pdf_text(admin.get(f"{BASE_URL}/api/svc/cases/{svc_case}/service-report.pdf").content)
        assert "Customer unable to sign" in txt and "Site unmanned on arrival" in txt
        c = admin.post(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/complete",
                       json={"summary": "Done", "target": "repaired", "email_report": False})
        assert c.status_code == 200, c.text
        time.sleep(3)
        assert not DB.svc_cases.find_one({"id": svc_case}).get("service_report_sent_to")

    def test_pdf_with_special_chars_in_name(self, admin, svc_case):
        r = admin.post(f"{BASE_URL}/api/svc/engineer/signature", json={
            "case_id": svc_case, "signed_by_name": "O'Brien & Sons <Ltd>", "image_data": PNG})
        assert r.status_code == 200
        pdf = admin.get(f"{BASE_URL}/api/svc/cases/{svc_case}/service-report.pdf")
        assert pdf.status_code == 200, f"PDF failed with special chars in signer name: {pdf.status_code} {pdf.text[:200]}"

    def test_calibration_certificate_has_customer_signoff(self, admin, svc_case):
        r = admin.post(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/calibration", json={
            "equipment_name": "Treadmill", "readings": [{"label": "Speed", "target": "10", "measured": "10", "result": "pass"}]})
        assert r.status_code == 200, r.text
        admin.post(f"{BASE_URL}/api/svc/engineer/signature", json={
            "case_id": svc_case, "signed_by_name": "Cal Signer", "signed_by_email": "TEST_cal@example.com", "image_data": PNG})
        pdf = admin.get(f"{BASE_URL}/api/svc/cases/{svc_case}/calibration/certificate.pdf")
        assert pdf.status_code == 200, pdf.text[:300]
        txt = _pdf_text(pdf.content)
        assert "Customer sign-off" in txt or "CUSTOMER SIGN-OFF" in txt.upper()
        assert "Cal Signer" in txt


# ─── BFPO engineer ─────────────────────────────────────────────────
@pytest.fixture(scope="module")
def gib():
    tok, _ = None, None
    for pw in ("BfpoEng123!", "Bfpo123!"):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "engineer.gib@bfpo.pulsefitness.test",
                          "password": pw, "portal": "mod"}, headers=BYPASS)
        if r.status_code == 200:
            tok = r.json().get("token")
            break
    assert tok
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", **BYPASS})
    return s


def _new_bfpo_case(gib):
    jobs = gib.get(f"{BASE_URL}/api/bfpo/jobs").json()["jobs"]
    parent = next(j for j in jobs if j.get("country") == "Gibraltar")
    r = gib.post(f"{BASE_URL}/api/bfpo/jobs/{parent['id']}/report-fault",
                 json={"title": "TEST_ signoff fault", "description": "x", "priority": "p3"})
    assert r.status_code == 200, r.text
    cid = r.json()["case"]["id"]
    assert gib.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/accept", json={}).status_code == 200
    assert gib.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/arrive", json={"safe": True, "notes": "ok"}).status_code == 200
    return cid


class TestBfpoSignoff:
    def test_bfpo_full_flow(self, gib):
        cid = _new_bfpo_case(gib)
        info = gib.get(f"{BASE_URL}/api/bfpo/jobs/{cid}/signoff")
        assert info.status_code == 200, info.text
        assert "site_contact" in info.json() and info.json()["signoff"] is None
        r = gib.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/complete", json={"summary": "x", "safe_and_working": True})
        assert r.status_code == 400 and "sign-off" in r.json()["detail"]
        r = gib.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/signature",
                     json={"signed_by_name": "Sgt Smith", "signed_by_email": "bad", "image_data": PNG})
        assert r.status_code == 400
        r = gib.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/signature", json={
            "signed_by_name": "Sgt Smith", "signed_by_role": "PTI", "signed_by_email": "TEST_smith@army.mod.test", "image_data": PNG})
        assert r.status_code == 200, r.text
        assert r.json()["signature"]["signed_by_email"] == "test_smith@army.mod.test"
        assert gib.get(f"{BASE_URL}/api/bfpo/jobs/{cid}/signoff").json()["signoff"]["signed_by_name"] == "Sgt Smith"
        r = gib.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/complete", json={"summary": "Fixed", "safe_and_working": True})
        assert r.status_code == 200, r.text
        assert r.json()["case"]["status"] in ("closed", "awaiting_sign_off")
        pdf = gib.get(f"{BASE_URL}/api/bfpo/jobs/{cid}/job-sheet.pdf")
        assert pdf.status_code == 200
        txt = _pdf_text(pdf.content)
        assert "CUSTOMER SIGN-OFF" in txt and "Sgt Smith" in txt and "test_smith@army.mod.test" in txt

    def test_bfpo_unavailable(self, gib):
        cid = _new_bfpo_case(gib)
        assert gib.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/signature", json={"unavailable": True}).status_code == 400
        r = gib.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/signature", json={"unavailable": True, "reason": "Unit on exercise"})
        assert r.status_code == 200, r.text
        assert gib.post(f"{BASE_URL}/api/bfpo/jobs/{cid}/complete", json={"summary": "Fixed", "safe_and_working": True}).status_code == 200
        txt = _pdf_text(gib.get(f"{BASE_URL}/api/bfpo/jobs/{cid}/job-sheet.pdf").content)
        assert "Customer unable to sign" in txt and "Unit on exercise" in txt


# ─── BFPO PPM ──────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def staff():
    tok, _ = _login("staff@bfpo.pulsefitness.test", "Bfpo123!", portal="mod")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", **BYPASS})
    return s


class TestPpmSignoff:
    def test_ppm_complete_requires_signoff_and_cert(self, staff, gib):
        sites = gib.get(f"{BASE_URL}/api/bfpo/sites").json()["sites"]
        svc = None
        for s in sites:
            r = staff.post(f"{BASE_URL}/api/bfpo/ppm/services", json={"site_id": s["id"]})
            if r.status_code == 200:
                svc = r.json()["service"]
                break
        if not svc:
            pytest.skip("No Gibraltar site with equipment for PPM")
        sid = svc["id"]
        try:
            detail = gib.get(f"{BASE_URL}/api/bfpo/ppm/services/{sid}").json()
            for i in detail["inspections"]:
                rr = gib.post(f"{BASE_URL}/api/bfpo/ppm/inspections/{i['id']}",
                              json={"results": [{"id": "c1", "result": "pass"}]})
                assert rr.status_code == 200
            r = gib.post(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/complete", json={})
            assert r.status_code == 400 and "sign-off" in r.json()["detail"]
            r = gib.post(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/complete", json={"signoff": {"signed_by_name": "x"}})
            assert r.status_code == 400
            r = gib.post(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/complete", json={"signoff": {
                "signed_by_name": "Maj PPM", "signed_by_email": "TEST_ppm@army.mod.test", "image_data": PNG}})
            assert r.status_code == 200, r.text
            row = DB.svc_signatures.find_one({"ppm_service_id": sid}, {"_id": 0})
            assert row and row["signed_by_name"] == "Maj PPM" and row["case_id"] is None
            pdf = gib.get(f"{BASE_URL}/api/bfpo/ppm/services/{sid}/certificate.pdf")
            assert pdf.status_code == 200
            txt = _pdf_text(pdf.content)
            assert "CUSTOMER SIGN-OFF" in txt and "Maj PPM" in txt and "test_ppm@army.mod.test" in txt
        finally:
            DB.svc_signatures.delete_many({"ppm_service_id": sid})
            DB.bfpo_ppm_inspections.delete_many({"service_id": sid})
            DB.bfpo_ppm_services.delete_one({"id": sid})


class TestReopenNeedsFreshSignoff:
    def test_reopened_job_requires_new_signature(self, admin, svc_case):
        import asyncio
        from utils.svc_state import transition
        sign = {"case_id": svc_case, "signed_by_name": "First Signer", "image_data": PNG}
        assert admin.post(f"{BASE_URL}/api/svc/engineer/signature", json=sign).status_code == 200
        r = admin.post(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/complete",
                       json={"summary": "done", "target": "awaiting_sign_off", "email_report": False})
        assert r.status_code == 200, r.text
        # Reopen: awaiting_sign_off → on_site
        org = DB.svc_cases.find_one({"id": svc_case})["organization_id"]
        asyncio.run(transition(case_id=svc_case, organization_id=org, target_state="on_site",
                               actor={"id": "test", "email": "t@x"}, reason="customer rejected"))
        assert DB.svc_cases.find_one({"id": svc_case}).get("reopened_at")
        g = admin.get(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/signoff").json()
        assert g["signoff"] is None and g["reopened_at"]
        r = admin.post(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/complete",
                       json={"summary": "done again", "target": "awaiting_sign_off", "email_report": False})
        assert r.status_code == 400 and "reopened" in r.json()["detail"]
        assert admin.post(f"{BASE_URL}/api/svc/engineer/signature",
                          json={**sign, "signed_by_name": "Second Signer"}).status_code == 200
        r = admin.post(f"{BASE_URL}/api/svc/engineer/jobs/{svc_case}/complete",
                       json={"summary": "done again", "target": "awaiting_sign_off", "email_report": False})
        assert r.status_code == 200, r.text
