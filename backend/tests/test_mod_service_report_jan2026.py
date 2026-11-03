# MOD Service Report consistency (Jan 2026): BFPO job-sheet -> standard Service Report,
# MOD site fault service-report download, non-MOD calibration regression, PPM schedule is_mod flag.
import io
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pypdf import PdfReader

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
BYPASS = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}

MOD_SITE_ORG = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"
MOD_CASE_REF = "SVC-00038"
MOD_CASE_ID = "b33cbfa5-b41f-400a-aa27-05676409afa4"         # bfpo-mod-org, no calibration
CAL_CASE_ID = "0bf5a90a-e9c4-454a-a1b1-912b5cebee4d"         # iso-demo-org SVC-00026, has calibration
LINKED_ISSUE = "bdf587ef-a741-437b-b13f-6d0ff72a7650"         # MOD Test Site, resolved, bfpo_case_id
OTHER_SITE_ISSUE = "29ac6b10-4b9c-4f30-9da1-b5224ed54b93"     # another MOD site
CYP_CASE_REF = "SVC-00004"                                    # Cyprus territory (not Gibraltar)

_db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
_tokens = {}


def _login(email, password, portal=None):
    key = (email, portal)
    if key in _tokens:
        return _tokens[key]
    body = {"email": email, "password": password}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{BASE_URL}/api/auth/login", json=body, headers=BYPASS, timeout=30)
    tok = r.json().get("token") if r.status_code == 200 else None
    _tokens[key] = tok
    return tok


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", **BYPASS}


def _text(pdf_bytes):
    rd = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((p.extract_text() or "") for p in rd.pages), rd


def _img_count(rd):
    return len(list(rd.pages[0].images))


@pytest.fixture(scope="module")
def eng_tok():
    t = _login("engineer.gib@bfpo.pulsefitness.test", "BfpoEng123!", "mod") or \
        _login("engineer.gib@bfpo.pulsefitness.com", "pulse123", "mod")
    if not t:
        pytest.skip("BFPO engineer login failed")
    return t


@pytest.fixture(scope="module")
def site_tok():
    t = _login("test@army.mod.test", "ModTest123!", "mod")
    if not t:
        pytest.skip("MOD site login failed")
    return t


@pytest.fixture(scope="module")
def iso_tok():
    t = _login("owner@isodemo.com", "IsoDemo123!")
    if not t:
        pytest.skip("iso owner login failed")
    return t


# ── BFPO engineer job sheet -> Service Report ─────────────────────
class TestBfpoJobSheet:
    def test_job_sheet_is_service_report(self, eng_tok):
        r = requests.get(f"{BASE_URL}/api/bfpo/jobs/{MOD_CASE_ID}/job-sheet.pdf", headers=_hdr(eng_tok), timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.headers["content-type"].startswith("application/pdf")
        assert f'Service Report - {MOD_CASE_REF}.pdf' in r.headers.get("content-disposition", "")
        txt, rd = _text(r.content)
        for s in ("Service Report", "Customer / Site Address", "Engineer", "Job No", MOD_CASE_REF):
            assert s in txt, f"missing {s!r}"
        assert "Electronic Job Sheet" not in txt
        assert "TREADMILL CALIBRATION" not in txt  # no calibration captured

    def test_job_sheet_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/bfpo/jobs/{MOD_CASE_ID}/job-sheet.pdf", headers=BYPASS, timeout=30)
        assert r.status_code in (401, 403)

    def test_job_sheet_out_of_territory(self, eng_tok):
        c = _db.svc_cases.find_one({"reference": CYP_CASE_REF, "organization_id": "bfpo-mod-org"}, {"_id": 0, "id": 1})
        r = requests.get(f"{BASE_URL}/api/bfpo/jobs/{c['id']}/job-sheet.pdf", headers=_hdr(eng_tok), timeout=30)
        assert r.status_code in (403, 404)

    def test_mod_header_has_more_images_than_non_mod(self, eng_tok, iso_tok):
        mod = requests.get(f"{BASE_URL}/api/bfpo/jobs/{MOD_CASE_ID}/job-sheet.pdf", headers=_hdr(eng_tok), timeout=60)
        non = requests.get(f"{BASE_URL}/api/svc/cases/{CAL_CASE_ID}/service-report.pdf", headers=_hdr(iso_tok), timeout=60)
        assert mod.status_code == 200 and non.status_code == 200
        _, rm = _text(mod.content)
        _, rn = _text(non.content)
        names_m = [i.name for i in rm.pages[0].images]
        names_n = [i.name for i in rn.pages[0].images]
        print("MOD page1 images:", names_m, "non-MOD:", names_n)
        assert _img_count(rm) >= _img_count(rn) + 1 or len(names_m) > 2


# ── Non-MOD regression: calibration section still rendered ───────
class TestNonModServiceReport:
    def test_calibration_included(self, iso_tok):
        r = requests.get(f"{BASE_URL}/api/svc/cases/{CAL_CASE_ID}/service-report.pdf", headers=_hdr(iso_tok), timeout=60)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        txt, _ = _text(r.content)
        assert "Service Report" in txt and "Job No" in txt
        assert "TREADMILL CALIBRATION" in txt


# ── MOD site fault -> service report download ────────────────────
class TestModSiteFaultReport:
    created = []

    def test_linked_issue_200(self, site_tok):
        r = requests.get(f"{BASE_URL}/api/mod/site/faults/{LINKED_ISSUE}/service-report.pdf", headers=_hdr(site_tok), timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.headers["content-type"].startswith("application/pdf")
        assert "Service Report - " in r.headers.get("content-disposition", "")
        txt, _ = _text(r.content)
        assert "Service Report" in txt and "Customer / Site Address" in txt
        assert "Electronic Job Sheet" not in txt

    def test_unlinked_issue_404(self, site_tok):
        iid = f"TEST_{uuid.uuid4()}"
        _db.issues.insert_one({"id": iid, "organization_id": MOD_SITE_ORG, "title": "TEST_ unlinked fault",
                               "status": "open", "created_at": "2026-01-01T00:00:00+00:00"})
        TestModSiteFaultReport.created.append(iid)
        r = requests.get(f"{BASE_URL}/api/mod/site/faults/{iid}/service-report.pdf", headers=_hdr(site_tok), timeout=30)
        assert r.status_code == 404

    def test_other_site_issue_404(self, site_tok):
        r = requests.get(f"{BASE_URL}/api/mod/site/faults/{OTHER_SITE_ISSUE}/service-report.pdf", headers=_hdr(site_tok), timeout=30)
        assert r.status_code == 404

    def test_no_auth_401(self):
        r = requests.get(f"{BASE_URL}/api/mod/site/faults/{LINKED_ISSUE}/service-report.pdf", headers=BYPASS, timeout=30)
        assert r.status_code == 401

    def test_non_mod_user_forbidden(self, iso_tok):
        r = requests.get(f"{BASE_URL}/api/mod/site/faults/{LINKED_ISSUE}/service-report.pdf", headers=_hdr(iso_tok), timeout=30)
        assert r.status_code in (403, 404)

    @classmethod
    def teardown_class(cls):
        for iid in cls.created:
            _db.issues.delete_one({"id": iid})


# ── PPM schedule detail exposes is_mod ───────────────────────────
class TestPpmIsMod:
    created = []

    def test_existing_schedule_is_mod_false(self, iso_tok):
        sid = "9ba2bdb5-9333-4b06-81f2-f3084d7603b3"
        r = requests.get(f"{BASE_URL}/api/svc/ppm/schedules/{sid}", headers=_hdr(iso_tok), timeout=30)
        assert r.status_code == 200, r.text[:200]
        s = r.json()["schedule"]
        assert isinstance(s["is_mod"], bool) and s["is_mod"] is False

    def test_mod_site_schedule_is_mod_true(self, iso_tok):
        sid = f"TEST_{uuid.uuid4()}"
        _db.ppm_schedules.insert_one({"id": sid, "organization_id": "iso-demo-org", "source": "service_desk",
                                      "site_id": MOD_SITE_ORG, "site_name": "TEST_ MOD Test Site",
                                      "customer_name": "TEST_ MOD", "service_type": "PPM",
                                      "next_pm": "2026-02-10", "equipment_ids": []})
        TestPpmIsMod.created.append(sid)
        r = requests.get(f"{BASE_URL}/api/svc/ppm/schedules/{sid}", headers=_hdr(iso_tok), timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert r.json()["schedule"]["is_mod"] is True

    @classmethod
    def teardown_class(cls):
        for sid in cls.created:
            _db.ppm_schedules.delete_one({"id": sid})
