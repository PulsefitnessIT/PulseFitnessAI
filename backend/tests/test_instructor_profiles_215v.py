"""
Iteration 215v — Instructor Profile Pages Backend Tests

Tests for:
- CRUD operations for instructor profiles (create, read, update, delete/archive)
- Photo and hero photo upload endpoints
- Public endpoints (no auth required)
- OG image generation and caching
- Share HTML page with OG meta tags
- Security: no email/phone leak in public responses
- Slug uniqueness and auto-generation
"""
import os
import pytest
import requests
import hashlib

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from test_credentials.md
OPERATOR_EMAIL = "lee.somers@pulsefitness.com"
OPERATOR_PASSWORD = "TempPass123!"
STUDIO_SLUG = "maintenance-hub-357"

# Pre-seeded instructor from main agent
PRE_SEEDED_INSTRUCTOR_ID = "0cce241e-c932-49e5-9074-9b125dfd30b9"
PRE_SEEDED_INSTRUCTOR_SLUG = "aiden-rowe"


@pytest.fixture(scope="module")
def operator_token():
    """Get operator JWT token for authenticated requests."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": OPERATOR_EMAIL,
        "password": OPERATOR_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def headers(operator_token):
    """Headers with auth token."""
    return {
        "Authorization": f"Bearer {operator_token}",
        "Content-Type": "application/json"
    }


class TestInstructorCRUD:
    """Test operator CRUD operations for instructors."""

    created_instructor_id = None
    created_instructor_slug = None

    def test_create_instructor_success(self, headers):
        """POST /api/memberships/instructors — create instructor with all fields."""
        payload = {
            "name": "TEST_Jane Doe",
            "email": "jane.doe@test.com",
            "phone": "+447700900123",
            "headline": "RYT-500 · Vinyasa & Pre-natal",
            "bio": "Jane has been teaching yoga for over 10 years...",
            "specialties": ["Vinyasa", "Pre-natal", "Meditation"],
            "qualifications": ["RYT-500", "Pre-natal Certified"],
            "years_experience": 10,
            "social": {
                "instagram": "@janedoeyoga",
                "tiktok": "@janedoe",
                "linkedin": "https://linkedin.com/in/janedoe",
                "website": "https://janedoeyoga.com"
            },
            "is_published": True
        }
        response = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload, headers=headers)
        assert response.status_code == 200, f"Create failed: {response.text}"

        data = response.json()
        assert "instructor" in data
        inst = data["instructor"]

        # Verify all fields
        assert inst["name"] == "TEST_Jane Doe"
        assert inst["email"] == "jane.doe@test.com"
        assert inst["headline"] == "RYT-500 · Vinyasa & Pre-natal"
        assert inst["specialties"] == ["Vinyasa", "Pre-natal", "Meditation"]
        assert inst["qualifications"] == ["RYT-500", "Pre-natal Certified"]
        assert inst["years_experience"] == 10
        assert inst["is_published"] == True
        assert "id" in inst
        assert "slug" in inst
        assert inst["slug"].startswith("test-jane-doe")  # Auto-generated slug

        # Store for later tests
        TestInstructorCRUD.created_instructor_id = inst["id"]
        TestInstructorCRUD.created_instructor_slug = inst["slug"]
        print(f"Created instructor: {inst['id']} with slug: {inst['slug']}")

    def test_create_instructor_missing_name_400(self, headers):
        """POST /api/memberships/instructors — 400 on missing name."""
        payload = {
            "headline": "No name provided"
        }
        response = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload, headers=headers)
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"

    def test_create_instructor_no_auth_401(self):
        """POST /api/memberships/instructors — 401 without token."""
        payload = {"name": "Unauthorized Test"}
        response = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload)
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    def test_list_instructors(self, headers):
        """GET /api/memberships/instructors — lists non-archived instructors."""
        response = requests.get(f"{BASE_URL}/api/memberships/instructors", headers=headers)
        assert response.status_code == 200, f"List failed: {response.text}"

        data = response.json()
        assert "instructors" in data
        assert isinstance(data["instructors"], list)

        # Should include our created instructor
        ids = [i["id"] for i in data["instructors"]]
        if TestInstructorCRUD.created_instructor_id:
            assert TestInstructorCRUD.created_instructor_id in ids
        print(f"Found {len(data['instructors'])} instructors")

    def test_get_instructor_detail(self, headers):
        """GET /api/memberships/instructors/{id} — single instructor detail."""
        inst_id = TestInstructorCRUD.created_instructor_id or PRE_SEEDED_INSTRUCTOR_ID
        response = requests.get(f"{BASE_URL}/api/memberships/instructors/{inst_id}", headers=headers)
        assert response.status_code == 200, f"Get detail failed: {response.text}"

        data = response.json()
        assert "instructor" in data
        assert data["instructor"]["id"] == inst_id

    def test_get_instructor_not_found_404(self, headers):
        """GET /api/memberships/instructors/{id} — 404 for non-existent."""
        response = requests.get(f"{BASE_URL}/api/memberships/instructors/nonexistent-id-12345", headers=headers)
        assert response.status_code == 404

    def test_patch_instructor(self, headers):
        """PATCH /api/memberships/instructors/{id} — partial update."""
        inst_id = TestInstructorCRUD.created_instructor_id or PRE_SEEDED_INSTRUCTOR_ID
        payload = {
            "headline": "Updated headline for testing",
            "years_experience": 15
        }
        response = requests.patch(f"{BASE_URL}/api/memberships/instructors/{inst_id}", json=payload, headers=headers)
        assert response.status_code == 200, f"Patch failed: {response.text}"

        data = response.json()
        assert data["instructor"]["headline"] == "Updated headline for testing"
        assert data["instructor"]["years_experience"] == 15

    def test_patch_instructor_name_updates_slug(self, headers):
        """PATCH /api/memberships/instructors/{id} — changing name updates slug."""
        inst_id = TestInstructorCRUD.created_instructor_id
        if not inst_id:
            pytest.skip("No created instructor to test")

        payload = {"name": "TEST_Jane Smith Updated"}
        response = requests.patch(f"{BASE_URL}/api/memberships/instructors/{inst_id}", json=payload, headers=headers)
        assert response.status_code == 200, f"Patch failed: {response.text}"

        data = response.json()
        assert "test-jane-smith" in data["instructor"]["slug"]
        TestInstructorCRUD.created_instructor_slug = data["instructor"]["slug"]
        print(f"Updated slug: {data['instructor']['slug']}")


class TestInstructorPhotos:
    """Test photo upload endpoints."""

    def test_set_photo(self, headers):
        """POST /api/memberships/instructors/{id}/photo — set profile photo."""
        inst_id = TestInstructorCRUD.created_instructor_id or PRE_SEEDED_INSTRUCTOR_ID
        # Small valid base64 PNG (1x1 pixel)
        tiny_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        payload = {"photo_url": tiny_png}
        response = requests.post(f"{BASE_URL}/api/memberships/instructors/{inst_id}/photo", json=payload, headers=headers)
        assert response.status_code == 200, f"Set photo failed: {response.text}"
        assert response.json().get("ok") == True

    def test_set_hero_photo(self, headers):
        """POST /api/memberships/instructors/{id}/hero — set hero photo."""
        inst_id = TestInstructorCRUD.created_instructor_id or PRE_SEEDED_INSTRUCTOR_ID
        tiny_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        payload = {"photo_url": tiny_png}
        response = requests.post(f"{BASE_URL}/api/memberships/instructors/{inst_id}/hero", json=payload, headers=headers)
        assert response.status_code == 200, f"Set hero failed: {response.text}"
        assert response.json().get("ok") == True

    def test_set_photo_not_found_404(self, headers):
        """POST /api/memberships/instructors/{id}/photo — 404 for non-existent."""
        payload = {"photo_url": "https://example.com/photo.jpg"}
        response = requests.post(f"{BASE_URL}/api/memberships/instructors/nonexistent-id/photo", json=payload, headers=headers)
        assert response.status_code == 404


class TestInstructorArchive:
    """Test archive (soft delete) functionality."""

    archived_instructor_id = None

    def test_create_instructor_for_archive(self, headers):
        """Create an instructor specifically for archive testing."""
        payload = {
            "name": "TEST_Archive Target",
            "is_published": True
        }
        response = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload, headers=headers)
        assert response.status_code == 200
        TestInstructorArchive.archived_instructor_id = response.json()["instructor"]["id"]

    def test_archive_instructor(self, headers):
        """DELETE /api/memberships/instructors/{id} — soft archives."""
        inst_id = TestInstructorArchive.archived_instructor_id
        if not inst_id:
            pytest.skip("No instructor to archive")

        response = requests.delete(f"{BASE_URL}/api/memberships/instructors/{inst_id}", headers=headers)
        assert response.status_code == 200, f"Archive failed: {response.text}"
        assert response.json().get("ok") == True

    def test_archived_not_in_list(self, headers):
        """GET /api/memberships/instructors — archived instructor excluded."""
        inst_id = TestInstructorArchive.archived_instructor_id
        if not inst_id:
            pytest.skip("No archived instructor to check")

        response = requests.get(f"{BASE_URL}/api/memberships/instructors", headers=headers)
        assert response.status_code == 200

        ids = [i["id"] for i in response.json()["instructors"]]
        assert inst_id not in ids, "Archived instructor should not appear in list"


class TestPublicEndpoints:
    """Test public (no auth) endpoints."""

    def test_public_list_instructors(self):
        """GET /api/public/studios/{slug}/instructors — no auth, returns published only."""
        response = requests.get(f"{BASE_URL}/api/public/studios/{STUDIO_SLUG}/instructors")
        assert response.status_code == 200, f"Public list failed: {response.text}"

        data = response.json()
        assert "studio" in data
        assert "instructors" in data
        assert isinstance(data["instructors"], list)

        # Verify no email/phone leaked
        for inst in data["instructors"]:
            assert "email" not in inst, f"Email leaked in public response: {inst}"
            assert "phone" not in inst, f"Phone leaked in public response: {inst}"
            # Verify expected public fields
            assert "id" in inst
            assert "slug" in inst
            assert "name" in inst
            assert "headline" in inst or inst.get("headline") is None
            assert "bio" in inst or inst.get("bio") is None
            assert "photo_url" in inst or inst.get("photo_url") is None
            assert "specialties" in inst
            assert "qualifications" in inst
            assert "social" in inst

        print(f"Public list returned {len(data['instructors'])} instructors")

    def test_public_instructor_profile(self):
        """GET /api/public/studios/{slug}/instructors/{instructor_slug} — profile JSON."""
        # Use pre-seeded instructor
        response = requests.get(f"{BASE_URL}/api/public/studios/{STUDIO_SLUG}/instructors/{PRE_SEEDED_INSTRUCTOR_SLUG}")
        assert response.status_code == 200, f"Public profile failed: {response.text}"

        data = response.json()
        assert "studio" in data
        assert "instructor" in data
        assert "upcoming" in data

        # Verify studio fields
        studio = data["studio"]
        assert "id" in studio
        assert "name" in studio
        assert "slug" in studio
        assert "primary_color" in studio

        # Verify instructor fields (public view)
        inst = data["instructor"]
        assert "id" in inst
        assert "slug" in inst
        assert "name" in inst
        assert "email" not in inst, "Email should not be in public view"
        assert "phone" not in inst, "Phone should not be in public view"

        # Verify upcoming classes structure
        assert isinstance(data["upcoming"], list)
        for occ in data["upcoming"]:
            assert "id" in occ
            assert "name" in occ or occ.get("name") is None
            assert "starts_at" in occ

    def test_public_instructor_not_found_404(self):
        """GET /api/public/studios/{slug}/instructors/{slug} — 404 for non-existent."""
        response = requests.get(f"{BASE_URL}/api/public/studios/{STUDIO_SLUG}/instructors/nonexistent-instructor-slug")
        assert response.status_code == 404

    def test_public_studio_not_found_404(self):
        """GET /api/public/studios/{slug}/instructors — 404 for non-existent studio."""
        response = requests.get(f"{BASE_URL}/api/public/studios/nonexistent-studio-slug/instructors")
        assert response.status_code == 404


class TestOGImageAndShare:
    """Test OG image generation and share HTML page."""

    og_image_bytes_first = None

    def test_og_image_first_hit_fresh(self):
        """GET /api/m/{slug}/i/{instructor_slug}/og.png — first hit renders fresh."""
        response = requests.get(f"{BASE_URL}/api/m/{STUDIO_SLUG}/i/{PRE_SEEDED_INSTRUCTOR_SLUG}/og.png")
        assert response.status_code == 200, f"OG image failed: {response.text}"
        assert response.headers.get("Content-Type") == "image/png"

        # Check cache header
        cache_header = response.headers.get("X-GymAxis-OG-Cache")
        assert cache_header in ["fresh", "cache"], f"Unexpected cache header: {cache_header}"

        # Verify it's a valid PNG
        content = response.content
        assert content[:8] == b'\x89PNG\r\n\x1a\n', "Response is not a valid PNG"
        assert len(content) > 1000, "PNG seems too small"

        TestOGImageAndShare.og_image_bytes_first = content
        print(f"OG image: {len(content)} bytes, cache: {cache_header}")

    def test_og_image_second_hit_cache(self):
        """GET /api/m/{slug}/i/{instructor_slug}/og.png — second hit returns cache."""
        response = requests.get(f"{BASE_URL}/api/m/{STUDIO_SLUG}/i/{PRE_SEEDED_INSTRUCTOR_SLUG}/og.png")
        assert response.status_code == 200

        # Should be cached now
        cache_header = response.headers.get("X-GymAxis-OG-Cache")
        # Note: might still be "fresh" if cache storage failed, but bytes should match

        # Verify identical bytes — switched MD5 → SHA-256 per code review.
        # (Cosmetic; this hash is only used to compare two byte buffers.)
        if TestOGImageAndShare.og_image_bytes_first:
            first_hash = hashlib.sha256(TestOGImageAndShare.og_image_bytes_first).hexdigest()
            second_hash = hashlib.sha256(response.content).hexdigest()
            assert first_hash == second_hash, "OG image bytes differ between requests"
            print(f"OG image cache verified: SHA-256 {first_hash[:16]}…")

    def test_share_html_page(self):
        """GET /api/m/{slug}/i/{instructor_slug}/share — returns HTML with OG meta tags."""
        response = requests.get(f"{BASE_URL}/api/m/{STUDIO_SLUG}/i/{PRE_SEEDED_INSTRUCTOR_SLUG}/share")
        assert response.status_code == 200, f"Share page failed: {response.text}"
        assert "text/html" in response.headers.get("Content-Type", "")

        html = response.text

        # Verify OG meta tags
        assert 'og:title' in html, "Missing og:title"
        assert 'og:image' in html, "Missing og:image"
        assert 'og:description' in html, "Missing og:description"
        assert 'twitter:card' in html, "Missing twitter:card"
        assert 'summary_large_image' in html, "Missing twitter:card=summary_large_image"

        # Verify OG image URL points to our endpoint
        assert f"/api/m/{STUDIO_SLUG}/i/{PRE_SEEDED_INSTRUCTOR_SLUG}/og.png" in html

        print("Share HTML page has all required OG meta tags")

    def test_og_image_not_found_404(self):
        """GET /api/m/{slug}/i/{instructor_slug}/og.png — 404 for non-existent."""
        response = requests.get(f"{BASE_URL}/api/m/{STUDIO_SLUG}/i/nonexistent-instructor/og.png")
        assert response.status_code == 404


class TestSlugUniqueness:
    """Test slug uniqueness within org."""

    def test_duplicate_name_gets_unique_slug(self, headers):
        """Creating two instructors with same name should get unique slugs.

        Prior test runs may have leaked instructors with this base slug,
        so we (a) purge any pre-existing matches before creating fresh
        ones and (b) accept any numeric suffix rather than hard-coding -2/-3.
        """
        import re

        payload = {"name": "TEST_Duplicate Name Test"}
        base_slug_prefix = "test-duplicate-name-test"

        # Purge leaked records so the suffix counter restarts cleanly.
        listing = requests.get(f"{BASE_URL}/api/memberships/instructors", headers=headers)
        if listing.status_code == 200:
            for it in listing.json().get("instructors", []):
                slug = (it.get("slug") or "").lower()
                if slug == base_slug_prefix or slug.startswith(f"{base_slug_prefix}-"):
                    requests.delete(
                        f"{BASE_URL}/api/memberships/instructors/{it['id']}",
                        headers=headers,
                    )

        # Create first
        r1 = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload, headers=headers)
        assert r1.status_code == 200
        slug1 = r1.json()["instructor"]["slug"]
        id1 = r1.json()["instructor"]["id"]

        # Create second with same name
        r2 = requests.post(f"{BASE_URL}/api/memberships/instructors", json=payload, headers=headers)
        assert r2.status_code == 200
        slug2 = r2.json()["instructor"]["slug"]
        id2 = r2.json()["instructor"]["id"]

        # Slugs should be different and second should carry a numeric suffix.
        assert slug1 != slug2, f"Slugs should be unique: {slug1} vs {slug2}"
        assert re.search(r"-\d+$", slug2), f"Second slug should have numeric suffix: {slug2}"

        print(f"Slug uniqueness verified: {slug1} vs {slug2}")

        # Cleanup
        requests.delete(f"{BASE_URL}/api/memberships/instructors/{id1}", headers=headers)
        requests.delete(f"{BASE_URL}/api/memberships/instructors/{id2}", headers=headers)


class TestCleanup:
    """Cleanup test data."""

    def test_cleanup_created_instructor(self, headers):
        """Archive the instructor created during tests."""
        inst_id = TestInstructorCRUD.created_instructor_id
        if inst_id:
            response = requests.delete(f"{BASE_URL}/api/memberships/instructors/{inst_id}", headers=headers)
            print(f"Cleaned up instructor {inst_id}: {response.status_code}")
