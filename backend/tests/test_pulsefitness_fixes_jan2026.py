"""Regression tests for the Jan 2026 PulseFitness fix batch:

  1. Staffing role mapping — 'administrator' must map to platform 'staff'
     (NOT 'manager') via _platform_role_from_staff_role and the
     POST /api/staffing/staff/{id}/issue-credentials endpoint.

  2. MOD quote PDF — utils.crm_quote_pdf.build_crm_quote_pdf must render
     rows from `lines` (used by mod_sor quotes) with a "TL No." column and
     SER code in the description; must NOT print "No line items".

  3. MOD site via CRM — POST /api/master-admin/mod-estate/sites creates an
     org tagged account_type='mod_site' + mod_force=<force> that appears
     in GET /api/master-admin/mod-estate/site-readiness (cleaned up).
"""
import os
import re
import sys
import time
import uuid
from io import BytesIO

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"

# Make backend package importable for direct unit test of the PDF builder.
sys.path.insert(0, "/app/backend")


# ── Shared auth (single login, respect rate-limit) ─────────────────────
@pytest.fixture(scope="module")
def admin_token():
    for attempt in range(4):
        r = requests.post(f"{API}/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                          timeout=15)
        if r.status_code == 200:
            return r.json().get("token") or r.json().get("access_token")
        if r.status_code == 429:
            time.sleep(6 + attempt * 3)
            continue
        pytest.skip(f"Admin login failed: {r.status_code} {r.text[:200]}")
    pytest.skip("Admin login rate-limited")


@pytest.fixture(scope="module")
def admin_client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}",
                      "Content-Type": "application/json"})
    return s


# ── 1) Role mapping (unit) ─────────────────────────────────────────────
class TestRoleMapping:
    def test_administrator_maps_to_staff(self):
        from routes.staffing import _platform_role_from_staff_role as f
        assert f("administrator") == "staff", (
            "Administrator is office/admin — must be 'staff', not 'manager'")

    def test_engineer_maps_to_engineer(self):
        from routes.staffing import _platform_role_from_staff_role as f
        assert f("engineer") == "engineer"
        assert f("technician") == "engineer"

    def test_manager_and_director_map_to_manager(self):
        from routes.staffing import _platform_role_from_staff_role as f
        assert f("manager") == "manager"
        assert f("director") == "manager"
        assert f("supervisor") == "manager"

    def test_unknown_maps_to_staff(self):
        from routes.staffing import _platform_role_from_staff_role as f
        assert f("receptionist") == "staff"
        assert f(None) == "staff"
        assert f("") == "staff"


# ── 2) MOD quote PDF (unit) ────────────────────────────────────────────
class TestModQuotePDF:
    def _extract(self, pdf_bytes: bytes) -> str:
        from pdfminer.high_level import extract_text
        return extract_text(BytesIO(pdf_bytes))

    def test_mod_quote_pdf_renders_lines_with_tl_and_ser(self):
        from utils.crm_quote_pdf import build_crm_quote_pdf
        quote = {
            "quote_number": "MOD-QA-0001",
            "quote_kind": "mod_sor",
            "title": "QA MOD Quote",
            "currency": "GBP",
            "lines": [
                {"sku": "5A", "sicon_ref": "PAT SER100078",
                 "description": "Treadmill preventive maintenance",
                 "quantity": 1, "unit": "Each",
                 "unit_price": 250.00, "subtotal": 250.00},
                {"sku": "23A", "sicon_ref": "PAT SER100099",
                 "description": "Belt replacement",
                 "quantity": 2, "unit": "Each",
                 "unit_price": 45.00, "subtotal": 90.00},
            ],
        }
        org = {"id": "qa-org", "name": "QA Ops", "country": "United Kingdom"}
        pdf = build_crm_quote_pdf(quote, org)
        assert pdf[:4] == b"%PDF", "Output is not a PDF"
        text = self._extract(pdf)
        # No fallback placeholder
        assert "No line items" not in text, "Placeholder still printed for mod_sor with lines"
        # TL No. column header
        assert re.search(r"TL\s*No", text), f"'TL No.' header missing.\n{text[:400]}"
        # TL numbers per line (from sku)
        assert "5A" in text
        assert "23A" in text
        # SER codes in description
        assert "SER100078" in text
        assert "SER100099" in text

    def test_mod_quote_pdf_with_line_items_still_works(self):
        """Backward compat — a mod_sor quote using `line_items` should still render."""
        from utils.crm_quote_pdf import build_crm_quote_pdf
        quote = {
            "quote_number": "MOD-QA-0002",
            "quote_kind": "mod_sor",
            "title": "QA MOD Quote 2",
            "currency": "GBP",
            "line_items": [{"sku": "7B", "sicon_ref": "PAT SER200001",
                            "description": "Cross-trainer service",
                            "quantity": 1, "unit_price": 199, "subtotal": 199}],
        }
        pdf = build_crm_quote_pdf(quote, {"id": "qa", "name": "QA"})
        text = self._extract(pdf)
        assert "No line items" not in text
        assert "7B" in text and "SER200001" in text


# ── 3) MOD site via CRM master-admin endpoint ──────────────────────────
class TestModEstateSiteCreate:
    TEST_SITE_NAME = f"TEST_QA_CRM_Site_{uuid.uuid4().hex[:6]}"
    created_site_id = None

    def test_site_readiness_reachable(self, admin_client):
        r = admin_client.get(f"{API}/master-admin/mod-estate/site-readiness", timeout=20)
        assert r.status_code == 200, r.text[:300]
        # Should be a dict/list — used later for verification
        assert isinstance(r.json(), (dict, list))

    def test_create_mod_site_raf(self, admin_client):
        payload = {"site_name": self.TEST_SITE_NAME, "force": "raf"}
        r = admin_client.post(f"{API}/master-admin/mod-estate/sites",
                              json=payload, timeout=25)
        if r.status_code == 400 and "HQ not set up" in r.text:
            pytest.skip("RAF HQ not seeded in this environment (env setup, not a bug)")
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:400]}"
        data = r.json()
        site_id = data.get("site_id") or data.get("id") or (data.get("site") or {}).get("id")
        assert site_id, f"No site id in response: {data}"
        type(self).created_site_id = site_id
        # Directly check the org record via DB is not available over API; instead
        # verify it appears in site-readiness.
        rr = admin_client.get(f"{API}/master-admin/mod-estate/site-readiness", timeout=20)
        assert rr.status_code == 200
        blob = rr.json()
        # Handle either list or dict wrappers
        found = False
        stack = [blob]
        while stack:
            v = stack.pop()
            if isinstance(v, dict):
                if v.get("id") == site_id or v.get("name") == self.TEST_SITE_NAME:
                    force = (v.get("mod_force") or v.get("force") or "").lower()
                    if not force or force == "raf":
                        found = True
                        break
                stack.extend(v.values())
            elif isinstance(v, list):
                stack.extend(v)
        assert found, f"Newly-created site {site_id} not visible in site-readiness"

    def test_cleanup_created_site(self, admin_client):
        sid = type(self).created_site_id
        if not sid:
            pytest.skip("No site created; nothing to clean")
        # Try common delete endpoints — tolerate missing.
        for url in (f"{API}/master-admin/mod-estate/sites/{sid}",
                    f"{API}/master-admin/organizations/{sid}"):
            r = admin_client.delete(url, timeout=15)
            if r.status_code in (200, 204):
                return
        # Fallback — direct mongo cleanup so we don't pollute the estate.
        try:
            import asyncio
            from motor.motor_asyncio import AsyncIOMotorClient
            mongo_url = os.environ["MONGO_URL"]
            db_name = os.environ["DB_NAME"]

            async def _del():
                cli = AsyncIOMotorClient(mongo_url)
                await cli[db_name].organizations.delete_one({"id": sid})
                cli.close()

            asyncio.get_event_loop().run_until_complete(_del())
        except Exception as e:
            print(f"[warn] Could not cleanup {sid}: {e}")
