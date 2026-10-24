"""MOD Operations fault bridge (every MOD intake path → /bfpo) + Pulse invoice header/footer on PDFs."""
import io
import os
import uuid
import time
import concurrent.futures as cf
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
BYPASS = {"X-RateLimit-Bypass": os.environ.get("RATE_LIMIT_BYPASS_SECRET", "")}
MOD_SITE_ORG = "abfdabd9-ae11-4877-a44d-a36fea7f1f4e"  # MOD Test Site
STAFF_EMAIL, STAFF_PW = "lee.somers@pulsefitness.com", "TempPass123!"

mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _login(email, pw, portal=None):
    body = {"email": email, "password": pw}
    if portal:
        body["portal"] = portal
    r = requests.post(f"{BASE_URL}/api/auth/login", json=body, headers=BYPASS, timeout=30)
    if r.status_code != 200 or not r.json().get("token"):
        pytest.skip(f"login failed for {email}: {r.status_code} {r.text[:200]}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def staff():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {_login(STAFF_EMAIL, STAFF_PW)}", **BYPASS})
    return s


@pytest.fixture(scope="module")
def created():
    ids = []
    yield ids
    for iid in ids:
        for c in mdb.svc_cases.find({"mod_issue_id": iid}, {"id": 1}):
            mdb.svc_case_events.delete_many({"case_id": c["id"]})
        mdb.svc_cases.delete_many({"mod_issue_id": iid})
        mdb.issues.delete_one({"id": iid})


def _insert_issue(created, **extra):
    """Simulate a non-wizard intake path (Log-a-fault / QR) — raw issue under the MOD org, no bfpo_case_id."""
    iid = f"TEST_modbridge_{uuid.uuid4().hex[:8]}"
    doc = {"id": iid, "organization_id": MOD_SITE_ORG, "status": "open",
           "issue_description": "TEST_ belt slipping on treadmill", "priority": "high",
           "reporter_name": "TEST Cpl Reporter", "reporter_email": "rep@army.mod.test",
           "classification_flags": ["OFFICIAL-SENSITIVE"],
           "created_at": datetime.now(timezone.utc).isoformat()}
    doc.update(extra)
    mdb.issues.insert_one(dict(doc))
    created.append(iid)
    return iid


def _sync(staff):
    """_safe_bridge on GETs is throttled (30s/process) — force the bridge via the unthrottled sync endpoint."""
    r = staff.post(f"{BASE_URL}/api/bfpo/faults/sync", timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# --- MOD Ops visibility -------------------------------------------------------
class TestModOpsBridge:
    def test_staff_dashboard_ok(self, staff):
        r = staff.get(f"{BASE_URL}/api/bfpo/staff/dashboard", timeout=60)
        assert r.status_code == 200, r.text[:300]

    def test_log_a_fault_issue_appears_in_staff_jobs(self, staff, created):
        iid = _insert_issue(created)
        _sync(staff)
        r = staff.get(f"{BASE_URL}/api/bfpo/staff/jobs", params={"status": "open"}, timeout=60)
        assert r.status_code == 200
        issue = mdb.issues.find_one({"id": iid})
        assert issue.get("bfpo_case_id"), "issue was not bridged"
        jobs = {j["id"]: j for j in r.json()["jobs"]}
        assert issue["bfpo_case_id"] in jobs
        j = jobs[issue["bfpo_case_id"]]
        assert j["source"] == "mod_fault"
        assert j["reporter_name"] == "TEST Cpl Reporter"
        assert j["priority"] == "p2" and j.get("safety_critical") is True

    def test_job_detail_has_mod_issue(self, staff, created):
        iid = created[0]
        cid = mdb.issues.find_one({"id": iid})["bfpo_case_id"]
        r = staff.get(f"{BASE_URL}/api/bfpo/staff/jobs/{cid}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["mod_issue"]["id"] == iid
        assert d["mod_issue"]["reporter_name"] == "TEST Cpl Reporter"
        assert d["site"] and d["site"]["id"] == MOD_SITE_ORG
        # bridge writes an 'intake' timeline event
        assert any("Fault logged by" in (e.get("body") or "") for e in d.get("events") or []), d.get("events")

    def test_idempotent_no_duplicate(self, staff, created):
        _sync(staff)
        staff.get(f"{BASE_URL}/api/bfpo/staff/jobs", timeout=60)
        assert mdb.svc_cases.count_documents({"mod_issue_id": created[0]}) == 1

    def test_concurrent_requests_no_duplicate_jobs(self, staff, created):
        # 10 unbridged faults + 16 parallel page loads (React StrictMode / several tabs / engineers)
        iids = [_insert_issue(created) for _ in range(10)]
        # unthrottled sync endpoint x12 in parallel + throttled GETs → exercises the atomic claim
        reqs = [("post", f"{BASE_URL}/api/bfpo/faults/sync")] * 12 + [
            ("get", f"{BASE_URL}/api/bfpo/staff/jobs"), ("get", f"{BASE_URL}/api/bfpo/staff/dashboard"),
            ("get", f"{BASE_URL}/api/bfpo/staff/sites"), ("get", f"{BASE_URL}/api/bfpo/jobs")]
        with cf.ThreadPoolExecutor(16) as ex:
            codes = list(ex.map(lambda m: getattr(staff, m[0])(m[1], timeout=90).status_code, reqs))
        assert all(c == 200 for c in codes), codes
        counts = [mdb.svc_cases.count_documents({"mod_issue_id": i}) for i in iids]
        assert all(n == 1 for n in counts), f"race: duplicate MOD Ops jobs per fault {counts}"

    def test_own_service_desk_case_not_double_listed(self, staff, created):
        """Fault escalated to the MOD org's own service desk (svc_case.source_meta.issue_id) must not ALSO get a BFPO job."""
        iid = _insert_issue(created, resolution_type="engineer")
        cid = f"TEST_modown_{uuid.uuid4().hex[:6]}"
        mdb.svc_cases.insert_one({"id": cid, "organization_id": MOD_SITE_ORG, "status": "new", "mod_issue_id": iid,
                                  "reference": "TESTOWN", "title": "TEST own desk case",
                                  "source_meta": {"issue_id": iid, "channel": "operations_portal"}})
        _sync(staff)
        jobs = staff.get(f"{BASE_URL}/api/bfpo/staff/jobs", params={"status": "open"}, timeout=60).json()["jobs"]
        listed = [j for j in jobs if j["id"] == cid or j["id"] == (mdb.issues.find_one({"id": iid}) or {}).get("bfpo_case_id")]
        assert len(listed) == 1, f"fault listed {len(listed)}x in MOD Ops"

    def test_site_resolved_closes_unworked_job(self, staff, created):
        iid = _insert_issue(created)
        _sync(staff)
        cid = mdb.issues.find_one({"id": iid})["bfpo_case_id"]
        mdb.issues.update_one({"id": iid}, {"$set": {"status": "resolved",
                                                     "resolved_at": datetime.now(timezone.utc).isoformat()}})
        _sync(staff)
        case = mdb.svc_cases.find_one({"id": cid})
        assert case["status"] == "closed"
        assert case.get("resolution_notes") == "Resolved by the site"
        ev = list(mdb.svc_case_events.find({"case_id": cid}, {"_id": 0}))
        assert any("resolved before an engineer" in (e.get("body") or "") for e in ev), ev

    def test_already_resolved_fault_bridged_closed(self, staff, created):
        iid = _insert_issue(created, status="resolved", resolved_at=datetime.now(timezone.utc).isoformat())
        _sync(staff)
        cid = mdb.issues.find_one({"id": iid}).get("bfpo_case_id")
        assert cid
        assert mdb.svc_cases.find_one({"id": cid})["status"] == "closed"

    def test_linked_case_not_double_bridged(self, staff, created):
        iid = _insert_issue(created, linked_case_id="TEST_existing_case")
        _sync(staff)
        assert not mdb.issues.find_one({"id": iid}).get("bfpo_case_id")

    def test_staff_site_detail_mod_org(self, staff):
        r = staff.get(f"{BASE_URL}/api/bfpo/sites/{MOD_SITE_ORG}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert (d.get("site") or d).get("id") == MOD_SITE_ORG or d.get("name")

    def test_sync_endpoint(self, staff):
        r = staff.post(f"{BASE_URL}/api/bfpo/faults/sync", timeout=60)
        assert r.status_code == 200 and r.json()["success"] is True

    def test_unique_index_exists(self):
        idx = mdb.svc_cases.index_information()
        assert "uniq_mod_issue_id" in idx and idx["uniq_mod_issue_id"].get("unique"), list(idx)

    def test_throttled_get_still_bridges_after_31s(self, staff, created):
        """GET-triggered bridge is throttled to once/30s; after waiting ≥31s a plain GET must bridge a new fault."""
        time.sleep(31)
        iid = _insert_issue(created)
        t0 = time.time()
        staff.get(f"{BASE_URL}/api/bfpo/staff/jobs", timeout=60)
        assert mdb.issues.find_one({"id": iid}).get("bfpo_case_id"), "GET did not bridge after throttle window"
        # immediate 2nd GET is throttled (no bridge of a newer fault)
        iid2 = _insert_issue(created)
        staff.get(f"{BASE_URL}/api/bfpo/staff/jobs", timeout=60)
        if time.time() - t0 < 29:
            assert not mdb.issues.find_one({"id": iid2}).get("bfpo_case_id"), "throttle not applied"

    def test_unauth_blocked(self):
        r = requests.get(f"{BASE_URL}/api/bfpo/staff/jobs", timeout=30)
        assert r.status_code in (401, 403)


# --- PDF branding: invoice header/footer artwork ------------------------------
def _pdf_images(pdf_bytes):
    import pypdf
    rd = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    imgs = []
    for p in rd.pages:
        res = p.get("/Resources") or {}
        xo = res.get("/XObject") or {}
        for k in xo:
            o = xo[k].get_object()
            if o.get("/Subtype") == "/Image":
                imgs.append((o.get("/Width"), o.get("/Height")))
    text = "\n".join((p.extract_text() or "") for p in rd.pages)
    return imgs, text, len(rd.pages)


class TestInvoiceBranding:
    def test_assets_present(self):
        for f in ("pulse-invoice-header.png", "pulse-invoice-footer.png"):
            assert os.path.exists(f"/app/backend/assets/{f}")
        for f in ("pulse-invoice-header.png", "pulse-invoice-footer.png"):
            r = requests.get(f"{BASE_URL}/brand/{f}", timeout=30)
            assert r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")

    def test_make_pulse_doc_uses_header_footer(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from reportlab.platypus import Paragraph, Spacer
        from utils.pulse_doc_template import (make_pulse_doc, pulse_header, pulse_styles,
                                              pulse_footer_factory, INVOICE_BOTTOM_MARGIN)
        buf = io.BytesIO()
        s = pulse_styles()
        doc = make_pulse_doc(buf, "TEST")
        story = [pulse_header(s)] + [Paragraph(f"Line {i}", s.get("body") or list(s.values())[0]) for i in range(120)]
        try:
            doc.build(story, onFirstPage=pulse_footer_factory(), onLaterPages=pulse_footer_factory())
        except TypeError:
            doc.build(story)
        imgs, text, pages = _pdf_images(buf.getvalue())
        assert pages >= 2
        dims = set(imgs)
        assert (1800, 215) in dims, f"header art missing: {dims}"
        assert (1800, 310) in dims, f"footer art missing: {dims}"
        assert doc.bottomMargin >= INVOICE_BOTTOM_MARGIN

    def test_bfpo_job_sheet_pdf(self, staff, created):
        if not created:
            pytest.skip("no bridged job")
        cid = mdb.issues.find_one({"id": created[0]})["bfpo_case_id"]
        r = staff.get(f"{BASE_URL}/api/bfpo/jobs/{cid}/job-sheet.pdf", timeout=60)
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        imgs, text, _ = _pdf_images(r.content)
        print("job-sheet images:", imgs)
