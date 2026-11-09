# MOD HQ "site login provisioned" email — env-driven MOD login link (MOD_PORTAL_URL / FRONTEND_URL)
import os
import sys
import uuid
import asyncio

import pytest
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def _frontend_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip()
    return url.rstrip("/")


BASE_URL = _frontend_backend_url()


# ── Unit: _hq_provision_email_html link building ─────────────────────
class TestProvisionEmailUnit:
    def test_mod_portal_url_used(self, monkeypatch):
        from routes.mod_portal import _hq_provision_email_html
        monkeypatch.setenv("MOD_PORTAL_URL", "https://modservice.pulsefitness.com")
        html = _hq_provision_email_html({"name": "Test Site"}, "site-user", "ABC123")
        assert 'href="https://modservice.pulsefitness.com/MODService"' in html
        assert "preview.emergentagent.com" not in html
        assert "pulsefitness.ai" not in html
        assert "Test Site" in html and "site-user" in html and "ABC123" in html

    def test_mod_portal_url_trailing_slash(self, monkeypatch):
        from routes.mod_portal import _hq_provision_email_html
        monkeypatch.setenv("MOD_PORTAL_URL", "https://modservice.pulsefitness.com/")
        html = _hq_provision_email_html({"name": "X"}, "u", "p")
        assert 'href="https://modservice.pulsefitness.com/MODService"' in html
        assert "//MODService" not in html

    def test_fallback_frontend_url(self, monkeypatch):
        from routes.mod_portal import _hq_provision_email_html
        monkeypatch.delenv("MOD_PORTAL_URL", raising=False)
        monkeypatch.setenv("FRONTEND_URL", "https://example.test/")
        html = _hq_provision_email_html({"name": "Test Site"}, "site-user", "ABC123")
        assert 'href="https://example.test/MODService"' in html
        assert "preview.emergentagent.com" not in html

    def test_empty_mod_portal_url_falls_back(self, monkeypatch):
        from routes.mod_portal import _hq_provision_email_html
        monkeypatch.setenv("MOD_PORTAL_URL", "")
        monkeypatch.setenv("FRONTEND_URL", "https://example.test")
        html = _hq_provision_email_html({"name": "T"}, "u", "p")
        assert 'href="https://example.test/MODService"' in html


# ── Regression: health ───────────────────────────────────────────────
class TestHealth:
    def test_health_ok(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=20)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ── Endpoint: POST /api/mod/pro/sites/{id}/provision-credentials ─────
class TestProvisionEndpoint:
    def test_unauth_rejected(self):
        r = requests.post(f"{BASE_URL}/api/mod/pro/sites/nonexistent/provision-credentials", json={}, timeout=20)
        assert r.status_code in (401, 403)

    def test_master_admin_non_mod_pro_gets_403_not_500(self):
        email = os.environ.get("MASTER_ADMIN_EMAIL")
        pw = os.environ.get("MASTER_ADMIN_PASSWORD")
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
        if r.status_code != 200 or not r.json().get("token") and not r.json().get("access_token"):
            pytest.skip(f"master admin login not usable: {r.status_code} {r.text[:200]}")
        tok = r.json().get("token") or r.json().get("access_token")
        r2 = s.post(
            f"{BASE_URL}/api/mod/pro/sites/nonexistent/provision-credentials",
            json={}, headers={"Authorization": f"Bearer {tok}"}, timeout=30,
        )
        assert r2.status_code in (403, 404), r2.text
        assert r2.status_code != 500

    def test_hq_provision_e2e_with_seeded_test_data(self):
        """Seed TEST_ mod_org HQ + mod_site + HQ user; call endpoint WITHOUT notify_email
        (no real email); then clean up by id."""
        from motor.motor_asyncio import AsyncIOMotorClient
        from utils.auth import create_token

        hq_id = f"TEST_hq_{uuid.uuid4().hex[:8]}"
        site_id = f"TEST_site_{uuid.uuid4().hex[:8]}"
        hq_user_id = f"TEST_user_{uuid.uuid4().hex[:8]}"

        async def seed():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            d = c[os.environ["DB_NAME"]]
            await d.organizations.insert_one({"id": hq_id, "name": "TEST_HQ", "account_type": "mod_org",
                                              "is_mod": True, "mod_root_id": hq_id})
            await d.organizations.insert_one({"id": site_id, "name": f"TEST_Site {site_id[-4:]}",
                                              "account_type": "mod_site", "is_mod": True, "mod_root_id": hq_id})
            await d.users.insert_one({"id": hq_user_id, "email": f"{hq_user_id.lower()}@example.test",
                                      "full_name": "TEST HQ", "role": "owner", "account_type": "mod_org",
                                      "organization_id": hq_id, "is_mod_user": True})
            c.close()

        async def cleanup():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            d = c[os.environ["DB_NAME"]]
            await d.users.delete_many({"organization_id": site_id, "account_type": "mod_site"})
            await d.users.delete_one({"id": hq_user_id})
            await d.organizations.delete_one({"id": site_id})
            await d.organizations.delete_one({"id": hq_id})
            c.close()

        asyncio.run(seed())
        try:
            tok = create_token(hq_user_id)
            h = {"Authorization": f"Bearer {tok}"}
            r = requests.post(f"{BASE_URL}/api/mod/pro/sites/{site_id}/provision-credentials",
                              json={"rotate_if_exists": True}, headers=h, timeout=30)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["ok"] is True
            assert data["site_id"] == site_id
            assert isinstance(data["password"], str) and len(data["password"]) > 0
            assert data["rotated"] is False
            assert data["notified_email"] is None
            # rotate path
            r2 = requests.post(f"{BASE_URL}/api/mod/pro/sites/{site_id}/provision-credentials",
                               json={"rotate_if_exists": True}, headers=h, timeout=30)
            assert r2.status_code == 200, r2.text
            assert r2.json()["rotated"] is True
            assert r2.json()["username"] == data["username"]
            # rotate disabled -> 409
            r3 = requests.post(f"{BASE_URL}/api/mod/pro/sites/{site_id}/provision-credentials",
                               json={"rotate_if_exists": False}, headers=h, timeout=30)
            assert r3.status_code == 409
        finally:
            asyncio.run(cleanup())
