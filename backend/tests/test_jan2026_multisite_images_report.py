# Regression: multi-site staffing scoping, bulk image lookup termination, CSV import backfill, service-report PDF
import io
import os
import time
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SITE_B_STAFF = {"deptdemo-sales-b"}
SITE_B = "iso-demo-site-b"


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200 or "token" not in r.json():
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def owner():
    return _login("owner@isodemo.com", "IsoDemo123!")


@pytest.fixture(scope="module")
def manager():
    return _login("manager@isodemo.com", "IsoDemo123!")


def _monday():
    d = date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def _ids_and_sites(payload):
    """Collect staff ids + site ids from arbitrary nested JSON."""
    staff, sites = set(), set()

    def walk(o):
        if isinstance(o, dict):
            for k in ("staff_id", "staff_member_id"):
                if isinstance(o.get(k), str):
                    staff.add(o[k])
            if isinstance(o.get("site_id"), str):
                sites.add(o["site_id"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(payload)
    return staff, sites


# ---------------- D. Multi-site staffing scope ----------------
class TestMultiSite:
    def test_manager_staff_only_site_a(self, manager):
        r = manager.get(f"{BASE_URL}/api/staffing/staff")
        assert r.status_code == 200, r.text
        rows = r.json()["staff"]
        ids = {s["id"] for s in rows}
        assert not (ids & SITE_B_STAFF), f"Site B staff leaked: {ids & SITE_B_STAFF}"
        for s in rows:
            assert SITE_B not in (s.get("site_ids") or []), s

    def test_owner_sees_site_b_staff(self, owner):
        r = owner.get(f"{BASE_URL}/api/staffing/staff")
        assert r.status_code == 200
        ids = {s["id"] for s in r.json()["staff"]}
        assert SITE_B_STAFF <= ids

    @pytest.mark.parametrize("path", [
        "/api/staffing/shifts", "/api/staffing/live-floor", "/api/staffing/leave",
        "/api/staffing/timesheets?week_start={monday}",
    ])
    def test_manager_staffing_lists_no_site_b(self, manager, path):
        r = manager.get(f"{BASE_URL}{path.format(monday=_monday())}")
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:300]}"
        staff, sites = _ids_and_sites(r.json())
        assert not (staff & SITE_B_STAFF), f"{path} leaked Site B staff"
        assert SITE_B not in sites, f"{path} leaked Site B site rows"
        assert "Sid Sales B" not in r.text

    def test_manager_sites_only_a(self, manager):
        r = manager.get(f"{BASE_URL}/api/sites")
        assert r.status_code == 200
        ids = {s["id"] for s in r.json()["sites"]}
        assert SITE_B not in ids, ids
        assert "iso-demo-site-a" in ids

    def test_owner_sites_both(self, owner):
        r = owner.get(f"{BASE_URL}/api/sites")
        ids = {s["id"] for s in r.json()["sites"]}
        assert {"iso-demo-site-a", SITE_B} <= ids


# ---------------- B. Bulk image lookup termination ----------------
class TestBulkImages:
    def test_batch_terminates(self, owner):
        seen = set()
        for i in range(15):
            r = owner.post(f"{BASE_URL}/api/equipment/lookup-images/batch?limit=8", timeout=180)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["ok"] is True
            ids = {x["id"] for x in d["results"]}
            assert not (ids & seen), "batch re-examined the same items"
            seen |= ids
            if d["total_examined"] == 0:
                return
        pytest.fail("batch never exhausted after 15 calls")

    def test_csv_import_schedules_backfill(self, owner):
        name = f"TEST_ImgBackfill {int(time.time())}"
        csv = f"name,manufacturer,equipment_type\n{name},Pulse Fitness,Treadmill\n"
        r = owner.post(f"{BASE_URL}/api/equipment/import-csv",
                       files={"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")}, timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        eq = None
        for _ in range(12):
            time.sleep(5)
            lst = owner.get(f"{BASE_URL}/api/equipment").json()
            items = lst if isinstance(lst, list) else lst.get("equipment") or lst.get("items") or []
            eq = next((e for e in items if e.get("name") == name), None)
            if eq and (eq.get("auto_image_looked_up_at") or eq.get("auto_image_url")):
                break
        assert eq, "imported equipment not found"
        try:
            assert eq.get("auto_image_looked_up_at") or eq.get("auto_image_url"), "backfill did not run in ~60s"
        finally:
            owner.delete(f"{BASE_URL}/api/equipment/{eq['id']}")


# ---------------- E. Service report PDF ----------------
class TestServiceReportPdf:
    CASE = "0bf5a90a-e9c4-454a-a1b1-912b5cebee4d"  # SVC-00026

    def _text(self, content):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(content)).pages)

    def test_calibration_case_pdf(self, owner):
        r = owner.get(f"{BASE_URL}/api/svc/cases/{self.CASE}/service-report.pdf", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.content[:4] == b"%PDF"
        t = self._text(r.content)
        open("/tmp/svc26.txt", "w").write(t)
        for s in ["Service Report", "Customer / Site Address", "Engineer", "Job No", "Job Type",
                  "Priority", "Visit Date", "Status", "Issued"]:
            assert s.lower() in t.lower(), f"missing '{s}'"
        assert "SPEED" in t.upper() and "INCLINE" in t.upper() and "CALIBRATION" in t.upper()

    def test_non_calibration_case_pdf(self, owner):
        r = owner.get(f"{BASE_URL}/api/svc/cases?limit=50")
        assert r.status_code == 200
        d = r.json()
        cases = d if isinstance(d, list) else d.get("cases") or d.get("items") or []
        other = [c for c in cases if c.get("id") != self.CASE]
        if not other:
            pytest.skip("no other case")
        r2 = owner.get(f"{BASE_URL}/api/svc/cases/{other[0]['id']}/service-report.pdf", timeout=60)
        assert r2.status_code == 200, r2.text[:300]
        assert r2.content[:4] == b"%PDF"
        assert "Service Report".lower() in self._text(r2.content).lower()


# ---------------- D2. Other staffing endpoints must also respect site lock ----------------
class TestMultiSiteOtherEndpoints:
    @pytest.mark.parametrize("path", [
        "/api/staffing/hr/profile/deptdemo-sales-b",
        "/api/staffing/staff/deptdemo-sales-b/employee-file",
        "/api/staffing/staff/deptdemo-sales-b/module-access",
        "/api/staffing/clock/board",
        "/api/staffing/performance",
        "/api/staffing/team/module-matrix",
        "/api/staffing/compliance/tracker",
        "/api/staffing/ai/absence-risk",
    ])
    def test_manager_no_site_b_leak(self, manager, path):
        r = manager.get(f"{BASE_URL}{path}", timeout=60)
        if r.status_code in (403, 404):
            return
        assert r.status_code == 200, r.text[:200]
        body = r.content.decode("latin-1")
        for marker in ("Sid Sales B", "deptdemo-sales-b", "sales.b@isodemo"):
            if "/deptdemo-sales-b/" in path or path.endswith("deptdemo-sales-b"):
                pytest.fail(f"{path} returned 200 for a Site B staff member (should be 403/404)")
            assert marker not in body, f"{path} leaks Site B staff ({marker})"
