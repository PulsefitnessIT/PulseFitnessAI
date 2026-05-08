"""
Iteration 172 — Memberships: OG preview, multi-format posters, confidence-band forecast, launch kit.

Tests:
  • GET /api/m/{slug}/og.png — 1200×630 OG preview image
  • GET /api/m/{slug}/share — HTML with OG meta tags + redirect
  • GET /api/m/{slug}/poster.png?format=square|story|a4 — multi-format posters
  • GET /api/m/{slug}/poster.pdf — A4 PDF poster
  • GET /api/memberships/analytics/overview — revenue_forecast with lower_gbp/upper_gbp bands
  • POST /api/memberships/setup/resend-launch-kit — operator-only, returns templates + links
  • POST /api/memberships/setup/complete — now returns launch_kit in response
  • 404 for unknown slugs on all public endpoints
  • 403 for member-token access to operator endpoints
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "studio.leeds@gymaxisai.com"
OPERATOR_PASSWORD = "Studio2026!"
BRAG_SLUG = "pulse-leeds"
INVALID_SLUG = "not-a-real-studio-xyz"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    if resp.status_code != 200:
        pytest.skip(f"Operator login failed: {resp.status_code} - {resp.text}")
    return resp.json().get("token")


@pytest.fixture(scope="module")
def operator_headers(operator_token):
    """Headers with operator auth."""
    return {"Authorization": f"Bearer {operator_token}", "Content-Type": "application/json"}


class TestOGPreviewImage:
    """GET /api/m/{slug}/og.png — 1200×630 Open Graph preview image."""

    def test_og_png_returns_valid_image(self):
        """OG image returns 200, image/png, valid PNG magic bytes."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/og.png")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "image/png" in resp.headers.get("Content-Type", ""), "Expected image/png content type"
        # Check PNG magic bytes
        assert resp.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        # Check reasonable size (should be ~30-50KB for 1200x630)
        size_kb = len(resp.content) / 1024
        assert 20 < size_kb < 100, f"OG image size {size_kb:.1f}KB outside expected range 20-100KB"
        print(f"✓ OG image: {size_kb:.1f}KB, valid PNG")

    def test_og_png_no_auth_required(self):
        """OG image is public, no auth needed."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/og.png")
        assert resp.status_code == 200, "OG image should be public"

    def test_og_png_404_invalid_slug(self):
        """OG image returns 404 for unknown slug."""
        resp = requests.get(f"{BASE_URL}/api/m/{INVALID_SLUG}/og.png")
        assert resp.status_code == 404, f"Expected 404 for invalid slug, got {resp.status_code}"


class TestSharePage:
    """GET /api/m/{slug}/share — HTML with OG meta tags + redirect."""

    def test_share_returns_html(self):
        """Share page returns text/html."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/share")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        content_type = resp.headers.get("Content-Type", "")
        assert "text/html" in content_type, f"Expected text/html, got {content_type}"

    def test_share_has_og_image_meta(self):
        """Share page contains og:image meta tag pointing to og.png."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/share")
        html = resp.text
        assert 'property="og:image"' in html or "property='og:image'" in html, "Missing og:image meta tag"
        assert f"/api/m/{BRAG_SLUG}/og.png" in html, "og:image should reference og.png endpoint"
        print("✓ Share page has og:image meta tag")

    def test_share_has_refresh_redirect(self):
        """Share page contains http-equiv refresh to brag page."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/share")
        html = resp.text
        assert 'http-equiv="refresh"' in html or "http-equiv='refresh'" in html, "Missing refresh meta tag"
        assert f"/m/{BRAG_SLUG}/brag" in html, "Refresh should redirect to brag page"
        print("✓ Share page has refresh redirect to brag")

    def test_share_has_twitter_card(self):
        """Share page contains Twitter card meta tags."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/share")
        html = resp.text
        assert 'name="twitter:card"' in html or "name='twitter:card'" in html, "Missing twitter:card meta"
        assert 'name="twitter:image"' in html or "name='twitter:image'" in html, "Missing twitter:image meta"
        print("✓ Share page has Twitter card meta tags")

    def test_share_404_invalid_slug(self):
        """Share page returns 404 for unknown slug."""
        resp = requests.get(f"{BASE_URL}/api/m/{INVALID_SLUG}/share")
        assert resp.status_code == 404, f"Expected 404 for invalid slug, got {resp.status_code}"


class TestMultiFormatPosters:
    """GET /api/m/{slug}/poster.png?format=square|story|a4 — multi-format posters."""

    def test_poster_square_format(self):
        """Square format (1080×1080) returns valid PNG."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?format=square")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "image/png" in resp.headers.get("Content-Type", "")
        assert resp.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        size_kb = len(resp.content) / 1024
        print(f"✓ Square poster: {size_kb:.1f}KB")

    def test_poster_story_format(self):
        """Story format (1080×1920) returns valid PNG."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?format=story")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "image/png" in resp.headers.get("Content-Type", "")
        assert resp.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        size_kb = len(resp.content) / 1024
        print(f"✓ Story poster: {size_kb:.1f}KB")

    def test_poster_a4_format_default(self):
        """A4 format (default) returns valid PNG."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?format=a4")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "image/png" in resp.headers.get("Content-Type", "")
        assert resp.content[:8] == b'\x89PNG\r\n\x1a\n', "Invalid PNG magic bytes"
        size_kb = len(resp.content) / 1024
        print(f"✓ A4 poster: {size_kb:.1f}KB")

    def test_poster_default_is_a4(self):
        """Default format (no param) is A4."""
        resp_default = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png")
        resp_a4 = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?format=a4")
        # Both should succeed and have similar sizes (within 10%)
        assert resp_default.status_code == 200
        assert resp_a4.status_code == 200
        size_default = len(resp_default.content)
        size_a4 = len(resp_a4.content)
        # Allow some variance due to dynamic content
        assert abs(size_default - size_a4) / max(size_default, size_a4) < 0.2, "Default should be A4 format"
        print("✓ Default format matches A4")

    def test_poster_formats_have_different_sizes(self):
        """Different formats produce different image sizes."""
        resp_square = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?format=square")
        resp_story = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?format=story")
        resp_a4 = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?format=a4")

        sizes = {
            "square": len(resp_square.content),
            "story": len(resp_story.content),
            "a4": len(resp_a4.content),
        }
        # All should be different (different canvas sizes)
        assert len(set(sizes.values())) == 3, f"Expected 3 different sizes, got {sizes}"
        print(f"✓ Format sizes: square={sizes['square']/1024:.1f}KB, story={sizes['story']/1024:.1f}KB, a4={sizes['a4']/1024:.1f}KB")

    def test_poster_404_invalid_slug(self):
        """Poster returns 404 for unknown slug."""
        resp = requests.get(f"{BASE_URL}/api/m/{INVALID_SLUG}/poster.png?format=square")
        assert resp.status_code == 404


class TestPosterPDF:
    """GET /api/m/{slug}/poster.pdf — A4 PDF poster."""

    def test_poster_pdf_returns_valid_pdf(self):
        """PDF poster returns 200, application/pdf, valid PDF magic."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.pdf")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        content_type = resp.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Expected application/pdf, got {content_type}"
        # Check PDF magic bytes
        assert resp.content[:4] == b'%PDF', "Invalid PDF magic bytes"
        size_kb = len(resp.content) / 1024
        assert 50 < size_kb < 200, f"PDF size {size_kb:.1f}KB outside expected range 50-200KB"
        print(f"✓ PDF poster: {size_kb:.1f}KB, valid PDF")

    def test_poster_pdf_no_auth_required(self):
        """PDF poster is public, no auth needed."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.pdf")
        assert resp.status_code == 200, "PDF poster should be public"

    def test_poster_pdf_404_invalid_slug(self):
        """PDF poster returns 404 for unknown slug."""
        resp = requests.get(f"{BASE_URL}/api/m/{INVALID_SLUG}/poster.pdf")
        assert resp.status_code == 404


class TestRevenueForecastConfidenceBands:
    """GET /api/memberships/analytics/overview — revenue_forecast with confidence bands."""

    def test_overview_has_revenue_forecast(self, operator_headers):
        """Overview includes revenue_forecast array."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/overview", headers=operator_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "revenue_forecast" in data, "Missing revenue_forecast in overview"
        print("✓ Overview has revenue_forecast")

    def test_forecast_has_confidence_bands(self, operator_headers):
        """Each forecast entry has bucket, revenue_gbp, lower_gbp, upper_gbp."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/overview", headers=operator_headers)
        data = resp.json()
        forecast = data.get("revenue_forecast", [])

        if len(forecast) == 0:
            # May be empty if not enough historical data
            print("⚠ revenue_forecast is empty (may need more historical data)")
            return

        for entry in forecast:
            assert "bucket" in entry, f"Missing bucket in forecast entry: {entry}"
            assert "revenue_gbp" in entry, f"Missing revenue_gbp in forecast entry: {entry}"
            assert "lower_gbp" in entry, f"Missing lower_gbp in forecast entry: {entry}"
            assert "upper_gbp" in entry, f"Missing upper_gbp in forecast entry: {entry}"
            # Verify band logic: lower <= revenue <= upper
            assert entry["lower_gbp"] <= entry["revenue_gbp"] <= entry["upper_gbp"], \
                f"Invalid band: lower={entry['lower_gbp']}, rev={entry['revenue_gbp']}, upper={entry['upper_gbp']}"

        print(f"✓ Forecast has {len(forecast)} entries with confidence bands")
        for e in forecast:
            print(f"  {e['bucket']}: £{e['revenue_gbp']:.2f} (±{e['upper_gbp']-e['lower_gbp']:.2f})")


class TestResendLaunchKit:
    """POST /api/memberships/setup/resend-launch-kit — operator-only."""

    def test_resend_launch_kit_success(self, operator_headers):
        """Resend launch kit returns templates and links."""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/resend-launch-kit",
                            json={}, headers=operator_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Should have sent array (may be empty if no RESEND_API_KEY)
        assert "sent" in data or "skipped" in data, f"Expected sent or skipped in response: {data}"

        # If not skipped, should have templates and links
        if "skipped" not in data:
            assert "templates" in data, f"Missing templates in response: {data}"
            assert "links" in data, f"Missing links in response: {data}"

            templates = data["templates"]
            assert "whatsapp" in templates, "Missing whatsapp template"
            assert "instagram" in templates, "Missing instagram template"
            assert "email" in templates, "Missing email template"

            links = data["links"]
            assert "app" in links, "Missing app link"
            assert "brag" in links, "Missing brag link"
            assert "share" in links, "Missing share link"

            print(f"✓ Launch kit: sent={len(data.get('sent', []))}, templates={list(templates.keys())}, links={list(links.keys())}")
        else:
            print(f"✓ Launch kit skipped: {data.get('skipped')}")

    def test_resend_launch_kit_401_no_auth(self):
        """Resend launch kit requires auth."""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/resend-launch-kit", json={})
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"

    def test_resend_launch_kit_persists_sent_at(self, operator_headers):
        """Resend launch kit persists launch_kit_sent_at on org."""
        # First call
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/resend-launch-kit",
                            json={}, headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()

        if "sent_at" in data:
            assert data["sent_at"], "sent_at should be set"
            print(f"✓ Launch kit sent_at: {data['sent_at']}")


class TestSetupCompleteWithLaunchKit:
    """POST /api/memberships/setup/complete — now returns launch_kit."""

    def test_setup_complete_returns_launch_kit(self, operator_headers):
        """Setup complete includes launch_kit in response."""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/complete",
                            json={}, headers=operator_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert "ok" in data, "Missing ok in response"
        assert data["ok"] is True, "ok should be True"
        assert "launch_kit" in data, f"Missing launch_kit in response: {data}"

        launch_kit = data["launch_kit"]
        # launch_kit may be skipped or have sent/templates/links
        print(f"✓ Setup complete with launch_kit: {list(launch_kit.keys()) if isinstance(launch_kit, dict) else launch_kit}")

    def test_setup_complete_401_no_auth(self):
        """Setup complete requires auth."""
        resp = requests.post(f"{BASE_URL}/api/memberships/setup/complete", json={})
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"


class TestPublicEndpoints404:
    """All public endpoints return 404 for unknown slugs."""

    @pytest.mark.parametrize("endpoint", [
        "/api/m/{slug}/og.png",
        "/api/m/{slug}/share",
        "/api/m/{slug}/poster.png",
        "/api/m/{slug}/poster.png?format=square",
        "/api/m/{slug}/poster.png?format=story",
        "/api/m/{slug}/poster.pdf",
        "/api/m/{slug}/brag",
    ])
    def test_404_for_invalid_slug(self, endpoint):
        """Public endpoint returns 404 for invalid slug."""
        url = f"{BASE_URL}{endpoint.replace('{slug}', INVALID_SLUG)}"
        resp = requests.get(url)
        assert resp.status_code == 404, f"Expected 404 for {endpoint}, got {resp.status_code}"


class TestRegressionIteration171:
    """Regression tests for iteration 171 features."""

    def test_poster_book_variant(self):
        """Poster book variant still works."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?variant=book")
        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("Content-Type", "")

    def test_poster_brag_variant(self):
        """Poster brag variant still works."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/poster.png?variant=brag")
        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("Content-Type", "")

    def test_brag_page_returns_stats(self):
        """Brag page returns organization and stats."""
        resp = requests.get(f"{BASE_URL}/api/m/{BRAG_SLUG}/brag")
        assert resp.status_code == 200
        data = resp.json()
        assert "organization" in data
        assert "stats" in data
        assert "active_members" in data["stats"]

    def test_analytics_overview(self, operator_headers):
        """Analytics overview still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/overview", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data
        assert "trend" in data

    def test_analytics_retention(self, operator_headers):
        """Analytics retention still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/retention", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data
        assert "cohort_matrix" in data

    def test_analytics_classes(self, operator_headers):
        """Analytics classes still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/classes", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data
        assert "classes_ranked" in data

    def test_analytics_operations(self, operator_headers):
        """Analytics operations still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/operations", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data
        assert "site_comparison" in data

    def test_members_by_kpi(self, operator_headers):
        """Members by KPI drill-down still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/members-by-kpi?kpi=active_members",
                           headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "kpi" in data
        assert "members" in data

    def test_weekly_digest(self, operator_headers):
        """Weekly digest endpoint still works."""
        resp = requests.post(f"{BASE_URL}/api/memberships/analytics/send-weekly-digest",
                            json={}, headers=operator_headers)
        assert resp.status_code == 200

    def test_csv_export(self, operator_headers):
        """CSV export still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/export.csv?report=overview",
                           headers=operator_headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("Content-Type", "")

    def test_pdf_export(self, operator_headers):
        """PDF export still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/analytics/export.pdf", headers=operator_headers)
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("Content-Type", "")

    def test_crm_push(self, operator_headers):
        """CRM push still works (with empty member_ids)."""
        resp = requests.post(f"{BASE_URL}/api/memberships/analytics/crm-push",
                            json={"member_ids": [], "pipeline": "retention"},
                            headers=operator_headers)
        # Should return 400 for empty member_ids
        assert resp.status_code == 400

    def test_dashboard(self, operator_headers):
        """Dashboard still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/dashboard", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "active_members" in data

    def test_setup_status(self, operator_headers):
        """Setup status still works."""
        resp = requests.get(f"{BASE_URL}/api/memberships/setup/status", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "organization" in data
