"""Iter 220i — Full backend test suite for branding, machine-row fields, and email fixes.

Tests:
  1. GET /api/svc/branding returns {effective, organization, engineer, has_engineer_override}
  2. PUT /api/svc/branding/me upserts engineer override; short hex (#abc) normalised to #AABBCC; invalid hex → 400
  3. DELETE /api/svc/branding/me clears override and has_engineer_override becomes false
  4. GET /api/svc/work-report-fields/for-machine-row/{row_id} returns 404 for unknown id
  5. GET /api/svc/work-report-fields/for-machine-row/{row_id} returns {fields, values, context} for real row
  6. GET /api/svc/cases/{case_id}/service-report.pdf returns application/pdf 200
  7. utils.email.GYMAXIS_LOGO_MARK no longer points at customer-assets.emergentagent.com
  8. wrap_branded() output contains /brand/gymaxis-mark-tight.png
  9. HEAD /brand/gymaxis-mark-tight.png returns 200 OK
"""
from __future__ import annotations

import importlib
import os
import sys
import uuid
import asyncio

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://engineer-hub-114.preview.emergentagent.com",
)
_CACHE: dict[str, str] = {}


def _bypass() -> dict[str, str]:
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": s} if s else {}


def _login(email: str, password: str) -> str:
    if _CACHE.get(email):
        return _CACHE[email]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, headers=_bypass())
        r.raise_for_status()
        data = r.json()
    _CACHE[email] = data.get("token") or data.get("access_token")
    return _CACHE[email]


def _hdr() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


# ── 1. GET /api/svc/branding returns correct structure ─────────────


class TestBrandingEndpoints:
    """Test branding CRUD endpoints."""

    def test_get_branding_returns_correct_structure(self):
        """GET /api/svc/branding returns {effective, organization, engineer, has_engineer_override}"""
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{BASE}/api/svc/branding", headers=_hdr())
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
            body = r.json()
            assert "effective" in body, "Missing 'effective' key"
            assert "organization" in body, "Missing 'organization' key"
            assert "engineer" in body, "Missing 'engineer' key"
            assert "has_engineer_override" in body, "Missing 'has_engineer_override' key"
            print(f"✓ GET /api/svc/branding returns correct structure: {list(body.keys())}")

    def test_put_branding_me_upserts_and_normalises_hex(self):
        """PUT /api/svc/branding/me upserts engineer override; short hex normalised to #AABBCC"""
        with httpx.Client(timeout=15.0) as c:
            H = _hdr()
            
            # Test short hex normalisation (#abc → #AABBCC)
            payload = {
                "logo_url": f"/api/public/files/test-{uuid.uuid4().hex[:6]}",
                "primary_color": "#abc",
                "accent_color": "#FF5599",
            }
            r = c.put(f"{BASE}/api/svc/branding/me", json=payload, headers=H)
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
            body = r.json()
            
            # Verify short hex was normalised
            assert body["engineer"]["primary_color"] == "#AABBCC", f"Expected #AABBCC, got {body['engineer']['primary_color']}"
            assert body["engineer"]["accent_color"] == "#FF5599", f"Expected #FF5599, got {body['engineer']['accent_color']}"
            assert body["effective"]["primary_color"] == "#AABBCC", "Effective should reflect engineer override"
            assert body["has_engineer_override"] is True, "has_engineer_override should be True"
            print("✓ PUT /api/svc/branding/me normalises short hex (#abc → #AABBCC)")

    def test_put_branding_me_invalid_hex_returns_400(self):
        """PUT /api/svc/branding/me with invalid hex returns 400"""
        with httpx.Client(timeout=15.0) as c:
            r = c.put(f"{BASE}/api/svc/branding/me", json={"primary_color": "not-a-hex"}, headers=_hdr())
            assert r.status_code == 400, f"Expected 400 for invalid hex, got {r.status_code}: {r.text}"
            print("✓ PUT /api/svc/branding/me returns 400 for invalid hex")

    def test_delete_branding_me_clears_override(self):
        """DELETE /api/svc/branding/me clears override and has_engineer_override becomes false"""
        with httpx.Client(timeout=15.0) as c:
            H = _hdr()
            
            # First set an override
            c.put(f"{BASE}/api/svc/branding/me", json={"primary_color": "#123456"}, headers=H)
            
            # Then delete it
            r = c.delete(f"{BASE}/api/svc/branding/me", headers=H)
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
            body = r.json()
            assert body["has_engineer_override"] is False, "has_engineer_override should be False after DELETE"
            print("✓ DELETE /api/svc/branding/me clears override")


# ── 2. Machine-row custom fields endpoint ──────────────────────────


class TestMachineRowFields:
    """Test work-report-fields/for-machine-row endpoint."""

    def test_for_machine_row_unknown_id_returns_404(self):
        """GET /api/svc/work-report-fields/for-machine-row/{row_id} returns 404 for unknown id"""
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{BASE}/api/svc/work-report-fields/for-machine-row/__nonexistent_row__",
                headers=_hdr(),
            )
            assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
            print("✓ GET /api/svc/work-report-fields/for-machine-row returns 404 for unknown id")

    def test_for_machine_row_real_row_returns_structure(self):
        """GET /api/svc/work-report-fields/for-machine-row/{row_id} returns {fields, values, context} for real row.
        
        This test creates a case, adds a machine row, then queries the endpoint.
        """
        with httpx.Client(timeout=20.0) as c:
            H = _hdr()
            
            # First, get engineer jobs to find a case we can use
            r = c.get(f"{BASE}/api/svc/engineer/jobs?limit=5", headers=H)
            if r.status_code != 200:
                pytest.skip("Could not fetch engineer jobs - endpoint may not be available for this user")
            
            jobs = r.json().get("jobs") or r.json() or []
            # /svc/engineer/jobs returns {by_day: {...}} when when=today/upcoming
            # — flatten to a list if we got that shape.
            if isinstance(jobs, dict) and "by_day" in jobs:
                jobs = [c for day in jobs["by_day"].values() for c in day]
            if not isinstance(jobs, list):
                jobs = []
            if not jobs:
                # Try to create a case
                r = c.post(f"{BASE}/api/svc/cases", json={
                    "title": "Test case for machine row",
                    "description": "Testing iter 220i",
                    "priority": "p3",
                }, headers=H)
                if r.status_code not in (200, 201):
                    pytest.skip("Could not create test case")
                case_id = r.json().get("id")
            else:
                case_id = jobs[0].get("id")
            
            if not case_id:
                pytest.skip("No case available for testing")
            
            # Add a machine row
            r = c.post(f"{BASE}/api/svc/engineer/jobs/{case_id}/machines", json={
                "asset_name": "Test BikeErg #99",
                "asset_type": "BikeErg",
            }, headers=H)
            
            if r.status_code not in (200, 201):
                pytest.skip(f"Could not add machine row: {r.status_code} {r.text}")
            
            row_id = r.json().get("id")
            assert row_id, "Machine row should have an id"
            
            # Now test the for-machine-row endpoint
            r = c.get(f"{BASE}/api/svc/work-report-fields/for-machine-row/{row_id}", headers=H)
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
            body = r.json()
            
            assert "fields" in body, "Response should contain 'fields'"
            assert "values" in body, "Response should contain 'values'"
            assert "context" in body, "Response should contain 'context'"
            
            # Context should have equipment_type
            ctx = body["context"]
            assert "equipment_type" in ctx, "Context should contain 'equipment_type'"
            print(f"✓ GET /api/svc/work-report-fields/for-machine-row returns correct structure: {list(body.keys())}")
            print(f"  Context: {ctx}")
            
            # Cleanup - delete the machine row
            c.delete(f"{BASE}/api/svc/engineer/jobs/{case_id}/machines/{row_id}", headers=H)


# ── 3. Service Report PDF endpoint ─────────────────────────────────


class TestServiceReportPDF:
    """Test service report PDF generation."""

    def test_service_report_pdf_returns_200_pdf(self):
        """GET /api/svc/cases/{case_id}/service-report.pdf returns application/pdf 200"""
        with httpx.Client(timeout=20.0) as c:
            H = _hdr()
            
            # Find a case to test with
            r = c.get(f"{BASE}/api/svc/engineer/jobs?limit=5", headers=H)
            if r.status_code != 200:
                # Try the desk endpoint
                r = c.get(f"{BASE}/api/svc/desk/cases?limit=5", headers=H)
            
            if r.status_code != 200:
                pytest.skip("Could not fetch cases")
            
            jobs = r.json().get("jobs") or r.json().get("cases") or r.json() or []
            if isinstance(jobs, dict) and "by_day" in jobs:
                jobs = [c for day in jobs["by_day"].values() for c in day]
            if not isinstance(jobs, list):
                jobs = []
            if not jobs:
                pytest.skip("No cases available for PDF test")
            
            case_id = jobs[0].get("id")
            if not case_id:
                pytest.skip("Case has no id")
            
            # Request the PDF
            r = c.get(f"{BASE}/api/svc/cases/{case_id}/service-report.pdf", headers=H)
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
            assert r.headers.get("content-type", "").startswith("application/pdf"), \
                f"Expected application/pdf, got {r.headers.get('content-type')}"
            assert r.content.startswith(b"%PDF"), "Response should be a valid PDF"
            print(f"✓ GET /api/svc/cases/{case_id}/service-report.pdf returns valid PDF ({len(r.content)} bytes)")


# ── 4. Email logo self-hosted check ────────────────────────────────


class TestEmailLogoSelfHosted:
    """Test that email logo is self-hosted, not on customer-assets.emergentagent.com."""

    def test_gymaxis_logo_mark_not_external(self, monkeypatch):
        """utils.email.GYMAXIS_LOGO_MARK should not point at customer-assets.emergentagent.com"""
        monkeypatch.setenv("EMAIL_PUBLIC_BASE_URL", "https://example.test")
        import utils.email as e
        importlib.reload(e)
        mark = e.GYMAXIS_LOGO_MARK
        assert "customer-assets.emergentagent.com" not in mark, f"Logo should be self-hosted, got: {mark}"
        assert mark.endswith("/brand/gymaxis-mark-tight.png"), f"Logo should end with /brand/gymaxis-mark-tight.png, got: {mark}"
        print(f"✓ GYMAXIS_LOGO_MARK is self-hosted: {mark}")

    def test_wrap_branded_uses_self_hosted_mark(self, monkeypatch):
        """wrap_branded() output should contain /brand/gymaxis-mark-tight.png, not external URL"""
        monkeypatch.setenv("EMAIL_PUBLIC_BASE_URL", "https://test.example")
        import utils.email as e
        importlib.reload(e)
        
        html = asyncio.get_event_loop().run_until_complete(
            e.wrap_branded("<p>hello</p>", organization_id=None)
        )
        
        assert "customer-assets.emergentagent.com" not in html, "Should not contain external URL"
        assert "/brand/gymaxis-mark-tight.png" in html, "Should contain self-hosted logo path"
        print("✓ wrap_branded() uses self-hosted logo mark")


# ── 5. Brand asset URL check ───────────────────────────────────────


class TestBrandAssetURL:
    """Test that the brand asset URL is accessible."""

    def test_brand_gymaxis_mark_url_returns_200(self):
        """HEAD /brand/gymaxis-mark-tight.png should return 200 OK"""
        with httpx.Client(timeout=10.0) as c:
            # The brand assets are served from the frontend, so use the base URL
            r = c.head(f"{BASE}/brand/gymaxis-mark-tight.png")
            # Accept 200 or 304 (cached)
            assert r.status_code in (200, 304), f"Expected 200/304, got {r.status_code}"
            print(f"✓ HEAD /brand/gymaxis-mark-tight.png returns {r.status_code}")

    def test_brand_gymaxis_mark_url_get_returns_image(self):
        """GET /brand/gymaxis-mark-tight.png should return an image"""
        with httpx.Client(timeout=10.0) as c:
            r = c.get(f"{BASE}/brand/gymaxis-mark-tight.png")
            assert r.status_code == 200, f"Expected 200, got {r.status_code}"
            content_type = r.headers.get("content-type", "")
            assert "image" in content_type or "png" in content_type.lower(), \
                f"Expected image content-type, got {content_type}"
            print(f"✓ GET /brand/gymaxis-mark-tight.png returns image ({len(r.content)} bytes)")


# ── 6. PDF builder accepts logo_bytes kwarg ────────────────────────


class TestPDFBuilderLogoBytes:
    """Test that PDF builder accepts logo_bytes kwarg."""

    def test_pdf_builder_accepts_logo_bytes_kwarg(self):
        """_build_pdf should accept logo_bytes kwarg without error"""
        from routes.svc.service_report import _build_pdf

        payload = {
            "case": {"id": "c", "reference": "JOB-1", "title": "Visit"},
            "org": {"name": "Acme", "brand_primary_color": "#0F9D58"},
            "engineer": {},
            "engineer_branding": {"primary_color": "#DC2626"},
            "signature": None,
            "time_entries": [],
            "rating": None,
            "rating_comment": None,
            "safety_signoff": None,
            "machines": [],
            "custom_field_defs": [],
            "fix_summary": "",
            "photos": [],
        }
        
        # Test without logo
        pdf1 = _build_pdf(payload, [], None, logo_bytes=None)
        assert pdf1.startswith(b"%PDF"), "Should produce valid PDF without logo"
        assert len(pdf1) > 1000, "PDF should have reasonable size"
        
        # Test with logo (1x1 PNG)
        one_px_png = __import__("base64").b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAIAAAACUFjqAAAAEklEQVR4nGP8z4APMOGVHbHSAEEsAROxCnMTAAAAAElFTkSuQmCC"
        )
        pdf2 = _build_pdf(payload, [], None, logo_bytes=one_px_png)
        assert pdf2.startswith(b"%PDF"), "Should produce valid PDF with logo"
        assert len(pdf2) > 1000, "PDF should have reasonable size"
        print("✓ _build_pdf accepts logo_bytes kwarg")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
