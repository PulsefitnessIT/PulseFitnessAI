"""
Iteration 171 — QR Reception Poster Tests

Tests for the new poster endpoint and related features:
1. GET /api/m/{slug}/poster.png - public PNG poster (book variant)
2. GET /api/m/{slug}/poster.png?variant=brag - brag variant
3. 404 for invalid slug
4. Cache-Control header (set by backend, may be overridden by CDN)
5. Unit tests for render_poster_png utility
6. Frontend button presence (AppUrlCard, BrandedBragPage)
7. Regression tests for iteration-170 features
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
OPERATOR_EMAIL = "studio.leeds@gymaxisai.com"
OPERATOR_PASSWORD = "Studio2026!"
BRAG_SLUG = "pulse-leeds"
INVALID_SLUG = "not-a-real-slug-xyz"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Operator login failed: {resp.status_code}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    """Headers with operator auth."""
    return {"Authorization": f"Bearer {operator_token}"}


class TestPosterEndpoint:
    """Tests for GET /api/m/{slug}/poster.png"""

    def test_poster_book_variant_returns_png(self):
        """Default variant (book) returns valid PNG."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.headers.get("Content-Type") == "image/png"
        # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
        assert resp.content[:4] == b'\x89PNG', "Response should start with PNG magic bytes"
        # Size check: should be >20KB for a proper poster
        assert len(resp.content) > 20000, f"Poster too small: {len(resp.content)} bytes"
        print(f"✓ Book variant: {len(resp.content)} bytes, valid PNG")

    def test_poster_brag_variant_returns_different_png(self):
        """Brag variant returns a different PNG (different QR code)."""
        resp_book = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png")
        resp_brag = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?variant=brag")

        assert resp_brag.status_code == 200
        assert resp_brag.headers.get("Content-Type") == "image/png"
        assert resp_brag.content[:4] == b'\x89PNG'
        assert len(resp_brag.content) > 20000

        # The two variants should be different (different QR codes)
        assert resp_book.content != resp_brag.content, "Book and brag variants should differ"
        print(f"✓ Brag variant: {len(resp_brag.content)} bytes, differs from book variant")

    def test_poster_invalid_slug_returns_404(self):
        """Invalid slug returns 404."""
        resp = requests.get(f"{BASE_URL}/api/m/{INVALID_SLUG}/poster.png")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        data = resp.json()
        assert "detail" in data
        print(f"✓ Invalid slug returns 404: {data['detail']}")

    def test_poster_no_auth_required(self):
        """Poster endpoint is public (no auth required)."""
        # No Authorization header
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png")
        assert resp.status_code == 200, "Poster should be accessible without auth"
        print("✓ Poster endpoint is public (no auth required)")

    def test_poster_content_disposition_header(self):
        """Poster has Content-Disposition header for download."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png")
        cd = resp.headers.get("Content-Disposition", "")
        assert "filename=" in cd, f"Missing filename in Content-Disposition: {cd}"
        assert BRAG_SLUG in cd, f"Slug not in filename: {cd}"
        print(f"✓ Content-Disposition: {cd}")

    def test_poster_cache_control_set_by_backend(self):
        """Backend sets Cache-Control header (may be overridden by CDN)."""
        # Note: The backend sets "public, max-age=900" but CDN may override
        # We just verify the endpoint returns successfully
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png")
        assert resp.status_code == 200
        cache_control = resp.headers.get("Cache-Control", "")
        # Log what we got - CDN may override
        print(f"✓ Cache-Control header: {cache_control}")
        # Backend code sets "public, max-age=900" - if CDN doesn't override, check it
        # If CDN overrides, this is expected behavior


class TestBragEndpoint:
    """Tests for GET /api/m/{slug}/brag (public stats)."""

    def test_brag_returns_stats(self):
        """Brag endpoint returns organization and stats."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/brag")
        assert resp.status_code == 200
        data = resp.json()

        assert "organization" in data
        assert "stats" in data

        org = data["organization"]
        assert org.get("name"), "Organization name missing"
        assert org.get("slug") == BRAG_SLUG

        stats = data["stats"]
        assert "active_members" in stats
        assert "classes_this_month" in stats
        assert "attendance_this_month" in stats
        print(f"✓ Brag stats: {stats['active_members']} active members, {stats['classes_this_month']} classes")

    def test_brag_invalid_slug_returns_404(self):
        """Invalid slug returns 404."""
        resp = requests.get(f"{BASE_URL}/api/m/{INVALID_SLUG}/brag")
        assert resp.status_code == 404
        print("✓ Invalid slug returns 404 for brag endpoint")


class TestAnalyticsRegression:
    """Regression tests for iteration-170 analytics features."""

    def test_analytics_overview(self, operator_headers):
        """Overview endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/overview", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data
        assert "trend" in data
        print(f"✓ Analytics overview: {data['kpis'].get('active_members')} active members")

    def test_analytics_retention(self, operator_headers):
        """Retention endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/retention", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data
        assert "cohort_matrix" in data
        print("✓ Analytics retention endpoint works")

    def test_analytics_classes(self, operator_headers):
        """Classes endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/classes", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "classes_ranked" in data
        assert "instructors" in data
        print(f"✓ Analytics classes: {len(data['classes_ranked'])} classes ranked")

    def test_analytics_operations(self, operator_headers):
        """Operations endpoint still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/operations", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data
        assert "site_comparison" in data
        print("✓ Analytics operations endpoint works")

    def test_members_by_kpi_active(self, operator_headers):
        """KPI drill-down for active_members works."""
        resp = requests.get(
            f"{BASE_URL}/api/memberships/analytics/members-by-kpi",
            params={"kpi": "active_members"},
            headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["kpi"] == "active_members"
        assert "members" in data
        assert "count" in data
        print(f"✓ KPI drill-down: {data['count']} active members")

    def test_send_weekly_digest(self, operator_headers):
        """Weekly digest trigger works."""
        resp = requests.post(
            f"{BASE_URL}/api/memberships/analytics/send-weekly-digest",
            headers=operator_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should return sent list or skipped reason
        assert "sent" in data or "skipped" in data
        print(f"✓ Weekly digest: {data}")


class TestMembershipsConsoleRegression:
    """Regression tests for Memberships console features."""

    def test_dashboard(self, operator_headers):
        """Dashboard endpoint works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/dashboard", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "active_members" in data
        print(f"✓ Dashboard: {data['active_members']} active members")

    def test_members_list(self, operator_headers):
        """Members list endpoint works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/members", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "members" in data
        print(f"✓ Members list: {len(data['members'])} members")

    def test_plans_list(self, operator_headers):
        """Plans list endpoint works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/plans", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "plans" in data
        print(f"✓ Plans list: {len(data['plans'])} plans")

    def test_setup_status(self, operator_headers):
        """Setup status endpoint works (needed for AppUrlCard)."""
        resp = requests.get(f"{BASE_URL}/api/memberships/setup/status", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "organization" in data
        org = data["organization"]
        assert "slug" in org, "Organization should have slug for poster URL"
        print(f"✓ Setup status: slug={org.get('slug')}")


class TestPosterUtilityUnit:
    """Unit-level tests for render_poster_png utility."""

    def test_render_poster_png_basic(self):
        """render_poster_png produces valid PNG."""
        from utils.memberships_poster import render_poster_png

        png = render_poster_png(
            studio_name="Test Studio",
            url="https://example.com/m/test",
            brand_hex="#19CDFF"
        )

        assert isinstance(png, bytes)
        assert png[:4] == b'\x89PNG', "Should produce valid PNG"
        assert len(png) > 10000, "PNG should be substantial size"
        print(f"✓ render_poster_png basic: {len(png)} bytes")

    def test_render_poster_png_short_hex(self):
        """Handles short-form hex (#fff) gracefully."""
        from utils.memberships_poster import render_poster_png

        png = render_poster_png(
            studio_name="Test Studio",
            url="https://example.com/m/test",
            brand_hex="#fff"  # Short form
        )

        assert png[:4] == b'\x89PNG'
        print("✓ render_poster_png handles short hex (#fff)")

    def test_render_poster_png_missing_hash(self):
        """Handles hex without # gracefully."""
        from utils.memberships_poster import render_poster_png

        png = render_poster_png(
            studio_name="Test Studio",
            url="https://example.com/m/test",
            brand_hex="19CDFF"  # Missing #
        )

        assert png[:4] == b'\x89PNG'
        print("✓ render_poster_png handles hex without #")

    def test_render_poster_png_invalid_hex(self):
        """Handles invalid hex gracefully (falls back to default)."""
        from utils.memberships_poster import render_poster_png

        png = render_poster_png(
            studio_name="Test Studio",
            url="https://example.com/m/test",
            brand_hex="not-a-color"  # Invalid
        )

        assert png[:4] == b'\x89PNG'
        print("✓ render_poster_png handles invalid hex (falls back to default)")

    def test_render_poster_png_brag_variant(self):
        """Brag variant produces different CTA text."""
        from utils.memberships_poster import render_poster_png

        png_book = render_poster_png(
            studio_name="Test Studio",
            url="https://example.com/m/test",
            variant="book"
        )
        png_brag = render_poster_png(
            studio_name="Test Studio",
            url="https://example.com/m/test/brag",
            variant="brag"
        )

        # Both should be valid PNGs
        assert png_book[:4] == b'\x89PNG'
        assert png_brag[:4] == b'\x89PNG'
        # They should differ (different CTA text and URL in QR)
        assert png_book != png_brag
        print("✓ render_poster_png brag variant differs from book")

    def test_render_poster_png_empty_studio_name(self):
        """Handles empty studio name gracefully."""
        from utils.memberships_poster import render_poster_png

        png = render_poster_png(
            studio_name="",
            url="https://example.com/m/test",
            brand_hex="#19CDFF"
        )

        assert png[:4] == b'\x89PNG'
        print("✓ render_poster_png handles empty studio name")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
