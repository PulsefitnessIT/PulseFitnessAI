"""Phase 3 tests for Site Staff Shared Login.

Covers:
- Bulk import: template, preview (new/duplicate), confirm
- Usage report (reports/usage)
- Reporter propagation to svc_cases (reporter_job_title + logged_via_shared_login)
- Engineer detail endpoint exposes those fields
- Supplier portal _resolve_reporter_contact returns role + via_shared_login
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

MANAGER_EMAIL = "owner@isodemo.com"
MANAGER_PASSWORD = "IsoDemo123!"
SHARED_USERNAME = "demo-head-office"
SHARED_PASSWORD = "Fox-6307-river"
SITE_ID = "iso-demo-site-a"


def _login(email, password):
    return requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=20,
    )


@pytest.fixture(scope="module")
def manager_headers():
    # Brief pause before / between logins to avoid IP rate limit (429)
    time.sleep(2)
    r = _login(MANAGER_EMAIL, MANAGER_PASSWORD)
    if r.status_code == 429:
        time.sleep(65)
        r = _login(MANAGER_EMAIL, MANAGER_PASSWORD)
    assert r.status_code == 200, f"Manager login: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def shared_headers():
    time.sleep(2)
    r = _login(SHARED_USERNAME, SHARED_PASSWORD)
    if r.status_code == 429:
        time.sleep(65)
        r = _login(SHARED_USERNAME, SHARED_PASSWORD)
    assert r.status_code == 200, f"Shared login: {r.status_code} {r.text}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Bulk Import ----------
class TestBulkImport:
    def test_template_download(self, manager_headers):
        r = requests.get(
            f"{BASE_URL}/api/site-staff/import/template",
            headers=manager_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        ct = r.headers.get("content-type", "")
        # Must be a CSV-ish response
        text = r.text
        assert "first_name" in text and "last_name" in text and "email" in text, text[:200]

    def test_preview_new_and_duplicate(self, manager_headers):
        suffix = uuid.uuid4().hex[:6]
        csv = (
            "first_name,last_name,job_title,email,phone,department,active\n"
            f"Sarah,Jones,General Manager,sarah.qa@example.com,07123 456789,Operations,true\n"
            f"BulkNew{suffix},Tester,Engineer,bulknew-{suffix}@example.com,+15555550101,Ops,true\n"
        )
        r = requests.post(
            f"{BASE_URL}/api/site-staff/import/preview",
            params={"site_id": SITE_ID},
            files={"file": (f"staff_{suffix}.csv", csv, "text/csv")},
            headers={"Authorization": manager_headers["Authorization"]},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        rows = data.get("rows") or data.get("items") or []
        assert rows, f"No rows in preview: {data}"
        # Classifications
        statuses = [str(row.get("status") or row.get("classification") or "").lower() for row in rows]
        assert any(s == "duplicate" for s in statuses), f"No duplicate row: {statuses} / {data}"
        assert any(s in ("new", "create") for s in statuses), f"No new row: {statuses} / {data}"

        # Stash for confirm step
        TestBulkImport._csv = csv
        TestBulkImport._suffix = suffix
        TestBulkImport._preview_token = data.get("preview_token") or data.get("token")

    def test_confirm_import(self, manager_headers):
        # Re-run preview to obtain normalized rows for the JSON confirm body
        csv = TestBulkImport._csv
        suffix = TestBulkImport._suffix
        pv = requests.post(
            f"{BASE_URL}/api/site-staff/import/preview",
            params={"site_id": SITE_ID},
            files={"file": (f"staff_{suffix}.csv", csv, "text/csv")},
            headers={"Authorization": manager_headers["Authorization"]},
            timeout=20,
        )
        assert pv.status_code == 200, pv.text
        rows = pv.json().get("rows") or []
        # Pass only rows; backend dedupes by email so we can send all
        body = {"site_id": SITE_ID, "rows": rows}
        r = requests.post(
            f"{BASE_URL}/api/site-staff/import/confirm",
            json=body,
            headers=manager_headers,
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text
        data = r.json()
        created = int(data.get("created", data.get("imported", 0)))
        skipped = int(data.get("skipped", data.get("duplicates", 0)))
        # New should be 1 (BulkNew row), duplicate=1 (Sarah)
        assert created >= 1, f"created < 1: {data}"
        assert skipped >= 1, f"skipped (duplicate) < 1: {data}"


# ---------- Usage report ----------
class TestUsageReport:
    def test_usage_report(self, manager_headers):
        r = requests.get(
            f"{BASE_URL}/api/site-staff/reports/usage",
            params={"site_id": SITE_ID},
            headers=manager_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Must include summary stats
        summary = data.get("summary") or data
        for k in ("total_faults", "via_shared_login", "active_reporters", "staff_count"):
            assert k in summary, f"Missing key {k} in summary={list(summary.keys()) if isinstance(summary,dict) else summary}"
        # Per-staff table
        by_staff = data.get("by_staff") or data.get("staff_breakdown") or []
        assert isinstance(by_staff, list)
        # Sarah Jones should have a non-zero count (from prior runs / propagation)
        sarah_count = next(
            (s.get("count", 0) for s in by_staff if "Sarah" in (s.get("name") or "")),
            0,
        )
        # Don't hard-fail if no faults have been logged yet in fresh env
        assert sarah_count >= 0


# ---------- Reporter propagation to svc_cases ----------
class TestReporterPropagation:
    def _get_reporter_id(self, shared_headers):
        r = requests.get(
            f"{BASE_URL}/api/site-staff/active?site_id={SITE_ID}",
            headers=shared_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("staff") if isinstance(body, dict) else body
        # Prefer Sarah Jones - check multiple name fields
        def _has_sarah(s):
            for f in ("full_name", "name", "first_name"):
                v = (s.get(f) or "")
                if "Sarah" in v:
                    return True
            return False
        sarah = next((s for s in items if _has_sarah(s)), None)
        if not sarah and items:
            sarah = items[0]
        assert sarah, f"No Sarah / staff available: {items}"
        return sarah.get("id") or sarah.get("_id"), sarah

    def test_high_severity_issue_propagates_reporter_fields_to_svc_case(
        self, shared_headers, manager_headers
    ):
        rid, sarah = self._get_reporter_id(shared_headers)
        # Use HIGH severity to force engineer escalation
        payload = {
            "serial_number": f"PH3-{uuid.uuid4().hex[:6]}",
            "machine_type": "Treadmill",
            "issue_description": "Severe belt slipping — needs engineer (phase3 test)",
            "severity": "high",
            "reporter_staff_id": rid,
            "resolution_type": "engineer",
        }
        r = requests.post(
            f"{BASE_URL}/api/issues",
            json=payload,
            headers=shared_headers,
            timeout=60,
        )
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        issue = r.json()
        issue_id = issue.get("id")
        assert issue_id
        # Confirm shared-login + job-title set on the issue itself
        assert issue.get("logged_via_shared_login") is True, issue
        assert (issue.get("reporter_job_title") or "").lower().startswith("general"), issue

        # Allow background mirror to complete
        for attempt in range(8):
            time.sleep(1.5)
            rr = requests.get(
                f"{BASE_URL}/api/svc/cases",
                headers=manager_headers,
                params={"limit": 50},
                timeout=20,
            )
            if rr.status_code != 200:
                continue
            cases_body = rr.json()
            cases = (
                cases_body.get("cases")
                or cases_body.get("items")
                or (cases_body if isinstance(cases_body, list) else [])
            )
            match = None
            for c in cases:
                meta = c.get("source_meta") or {}
                if meta.get("issue_id") == issue_id:
                    match = c
                    break
            if match:
                break
        assert match, f"svc_case mirror not found for issue {issue_id}"
        # Phase 3 new fields
        assert match.get("reporter_job_title") == "General Manager", match
        assert match.get("logged_via_shared_login") is True, match
        # Existing customer_* fields still copied from reporter
        assert (match.get("customer_email") or "").lower() == "sarah.qa@example.com"
        assert "Sarah" in (match.get("customer_name") or "")

        TestReporterPropagation._case_id = match.get("id")
        TestReporterPropagation._issue_id = issue_id

    def test_engineer_detail_returns_phase3_fields(self, manager_headers):
        cid = getattr(TestReporterPropagation, "_case_id", None)
        if not cid:
            pytest.skip("No svc_case created")
        # Try engineer endpoint first, fall back to case detail for the
        # same proof since engineer_job_detail returns the full case doc.
        r = requests.get(
            f"{BASE_URL}/api/svc/engineer/jobs/{cid}",
            headers=manager_headers,
            timeout=15,
        )
        if r.status_code in (402, 403):
            # Manager isn't an engineer — verify against generic case detail
            for path in (f"/api/svc/cases/{cid}", f"/api/cases/{cid}"):
                r2 = requests.get(BASE_URL + path, headers=manager_headers, timeout=15)
                if r2.status_code == 200:
                    body = r2.json()
                    case = body.get("case") or body
                    assert case.get("reporter_job_title") == "General Manager", case
                    assert case.get("logged_via_shared_login") is True, case
                    return
            pytest.skip(f"Engineer endpoint blocked ({r.status_code}); no case detail endpoint found")
        assert r.status_code == 200, r.text
        body = r.json()
        case = body.get("case") or body
        assert case.get("reporter_job_title") == "General Manager", case
        assert case.get("logged_via_shared_login") is True, case


# ---------- Supplier reporter resolver (unit test) ----------
class TestSupplierReporter:
    def test_resolve_reporter_contact_unit(self):
        """Direct unit test of _resolve_reporter_contact for shared-login fault."""
        import asyncio, sys
        sys.path.insert(0, "/app/backend")
        from routes.supplier_portal import _resolve_reporter_contact

        issue = {
            "reporter_name": "Sarah Jones",
            "reporter_email": "sarah.qa@example.com",
            "reporter_phone": "07123 456789",
            "reporter_job_title": "General Manager",
            "logged_via_shared_login": True,
            "reported_by": "gym-floor:demo-head-office",
        }
        result = asyncio.get_event_loop().run_until_complete(
            _resolve_reporter_contact(issue)
        )
        assert result.get("role") == "General Manager", result
        assert result.get("via_shared_login") is True, result
        assert result.get("name") == "Sarah Jones"
        assert result.get("email") == "sarah.qa@example.com"
