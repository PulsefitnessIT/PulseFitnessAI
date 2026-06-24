"""Onboarding Phase 5 — reports/exports, email templates, settings, customer portal."""
import os
import uuid
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"

TEST_TAG = f"TESTONB5-{uuid.uuid4().hex[:6]}"


# ── Session fixtures ──────────────────────────────────────────────────────────

def _login(session: requests.Session, email: str, password: str) -> dict:
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("token") or data.get("access_token") or (data.get("user") or {}).get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return data


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
    return s


@pytest.fixture(scope="session")
def org_user(admin):
    """Register a trial org user to obtain organization_id for portal tests."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    email = f"testonb5_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "TestPass123!"
    org_name = f"{TEST_TAG} Org"

    payload = {
        "email": email,
        "password": pwd,
        "full_name": "Test User",
        "company_name": org_name,
        "is_trial": False,
    }
    r = s.post(f"{API}/auth/register", json=payload)
    created = r.status_code in (200, 201)
    if not created:
        print(f"  /auth/register → {r.status_code} {r.text[:200]}")

    if not created:
        pytest.skip("Could not create trial org user via public signup endpoints; skipping portal tests.")

    # Login as the new user
    s2 = requests.Session()
    s2.headers.update({"Content-Type": "application/json"})
    try:
        _login(s2, email, pwd)
    except Exception as e:
        pytest.skip(f"Org user login failed: {e}")

    # Get organization_id via /auth/me
    me = s2.get(f"{API}/auth/me")
    if me.status_code != 200:
        pytest.skip(f"/auth/me failed: {me.status_code}")
    me_data = me.json()
    org_id = me_data.get("organization_id") or (me_data.get("user") or {}).get("organization_id")
    if not org_id:
        pytest.skip(f"No organization_id on org user: {me_data}")
    return {"session": s2, "email": email, "organization_id": org_id}


@pytest.fixture(scope="session")
def test_project(admin):
    """Create a fresh test onboarding project."""
    payload = {
        "customer_name": f"{TEST_TAG} Customer",
        "customer_type": "single_site",
        "modules": ["operations"],
    }
    r = admin.post(f"{API}/onboarding/projects", json=payload)
    assert r.status_code in (200, 201), f"create project failed: {r.status_code} {r.text[:200]}"
    p = r.json()
    assert "id" in p
    return p


# ── Reports ───────────────────────────────────────────────────────────────────

class TestReports:
    def test_reports_master_admin(self, admin, test_project):
        r = admin.get(f"{API}/onboarding/reports")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("total_projects", "completed", "go_live_success_rate", "by_status", "by_type", "by_owner", "imports_run", "rows"):
            assert k in d, f"missing {k} in {list(d.keys())}"
        assert isinstance(d["rows"], list)
        assert d["total_projects"] >= 1
        assert any(r["customer_name"] == test_project["customer_name"] for r in d["rows"])

    def test_reports_unauthenticated(self):
        r = requests.get(f"{API}/onboarding/reports")
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


# ── Exports ───────────────────────────────────────────────────────────────────

class TestExports:
    def test_export_csv(self, admin):
        r = admin.get(f"{API}/onboarding/reports/export", params={"format": "csv"})
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "Customer" in r.text  # header row

    def test_export_excel(self, admin):
        r = admin.get(f"{API}/onboarding/reports/export", params={"format": "excel"})
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "spreadsheetml" in ct or "openxmlformats" in ct, ct
        assert len(r.content) > 100
        assert r.content[:2] == b"PK"  # xlsx is a zip

    def test_export_pdf(self, admin):
        r = admin.get(f"{API}/onboarding/reports/export", params={"format": "pdf"})
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"

    def test_export_bogus(self, admin):
        r = admin.get(f"{API}/onboarding/reports/export", params={"format": "bogus"})
        assert r.status_code == 400


# ── Email templates ───────────────────────────────────────────────────────────

class TestEmailTemplates:
    EXPECTED = {"welcome", "request_missing_info", "user_invitation", "go_live_prep",
                "go_live_complete", "onboarding_delayed", "data_issue", "training_reminder"}

    def test_list_templates(self, admin):
        r = admin.get(f"{API}/onboarding/email-templates")
        assert r.status_code == 200
        d = r.json()
        ids = {t["id"] for t in d.get("templates", [])}
        assert self.EXPECTED <= ids, f"missing template ids: {self.EXPECTED - ids}"
        assert len(d["templates"]) == 8

    def test_render_welcome(self, admin, test_project):
        r = admin.post(f"{API}/onboarding/email-templates/render",
                       json={"template_id": "welcome", "project_id": test_project["id"]})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "subject" in d and "body" in d
        assert test_project["customer_name"] in d["subject"], d["subject"]
        assert "{customer_name}" not in d["subject"]
        assert "{customer_name}" not in d["body"]
        assert "{contact_name}" not in d["body"]

    def test_render_unknown_template(self, admin, test_project):
        r = admin.post(f"{API}/onboarding/email-templates/render",
                       json={"template_id": "nope_404", "project_id": test_project["id"]})
        assert r.status_code == 404

    def test_render_unknown_project(self, admin):
        r = admin.post(f"{API}/onboarding/email-templates/render",
                       json={"template_id": "welcome", "project_id": "no-such-project"})
        assert r.status_code == 404


# ── Email send ────────────────────────────────────────────────────────────────

class TestEmailSend:
    def test_send_welcome(self, admin, test_project):
        r = admin.post(f"{API}/onboarding/email-templates/send",
                       json={"template_id": "welcome", "project_id": test_project["id"],
                             "to": "test@example.com"})
        if r.status_code == 502:
            # Recipient validation / env gate — report (known acceptable per spec)
            pytest.skip(f"Email send blocked by env / recipient gate (502): {r.text[:200]}")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("ok") is True
        assert d.get("sent_to") == "test@example.com"


# ── Settings ──────────────────────────────────────────────────────────────────

class TestSettings:
    def test_get_settings(self, admin):
        r = admin.get(f"{API}/onboarding/settings")
        assert r.status_code == 200
        d = r.json()
        assert "customer_portal_enabled" in d

    def test_patch_settings_only_allowed_key(self, admin):
        # set false first
        r = admin.patch(f"{API}/onboarding/settings", json={"customer_portal_enabled": False})
        assert r.status_code == 200
        assert r.json().get("customer_portal_enabled") is False
        # set true
        r = admin.patch(f"{API}/onboarding/settings", json={"customer_portal_enabled": True})
        assert r.status_code == 200
        assert r.json().get("customer_portal_enabled") is True
        # extra key should be ignored
        r = admin.patch(f"{API}/onboarding/settings", json={"customer_portal_enabled": True, "evil_key": "x"})
        assert r.status_code == 200
        d = r.json()
        assert "evil_key" not in d


# ── Customer portal ───────────────────────────────────────────────────────────

class TestCustomerPortal:
    def test_portal_disabled_returns_403(self, admin):
        # disable
        admin.patch(f"{API}/onboarding/settings", json={"customer_portal_enabled": False})
        # any authed user (use admin which lacks portal access but should still see the 403 gate first)
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
        r = s.get(f"{API}/onboarding/portal/me")
        assert r.status_code == 403, f"expected 403 when disabled got {r.status_code}: {r.text[:200]}"

    def test_portal_enabled_no_org_returns_404(self, admin):
        admin.patch(f"{API}/onboarding/settings", json={"customer_portal_enabled": True})
        # Master admin has no organization_id → 404
        r = admin.get(f"{API}/onboarding/portal/me")
        assert r.status_code in (404,), f"expected 404 when portal on but no org/project got {r.status_code}: {r.text[:200]}"

    def test_portal_happy_path(self, admin, org_user, test_project):
        # 1. Link the project to the org
        admin.patch(f"{API}/onboarding/settings", json={"customer_portal_enabled": True})

        # Create a NEW project specifically for this org (test_project may already be unlinked)
        proj_payload = {
            "customer_name": f"{TEST_TAG} OrgProject",
            "customer_type": "single_site",
            "modules": ["operations"],
        }
        c = admin.post(f"{API}/onboarding/projects", json=proj_payload)
        assert c.status_code in (200, 201), c.text[:200]
        proj = c.json()

        link = admin.patch(f"{API}/onboarding/projects/{proj['id']}",
                            json={"organization_id": org_user["organization_id"]})
        assert link.status_code == 200, link.text[:300]
        assert link.json().get("organization_id") == org_user["organization_id"]

        # 2. Org user calls portal/me
        s = org_user["session"]
        r = s.get(f"{API}/onboarding/portal/me")
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["customer_name"] == proj_payload["customer_name"]
        assert "progress" in body
        assert "steps" in body and isinstance(body["steps"], list) and len(body["steps"]) > 0

        # 3. Bad status → 400
        step_id = body["steps"][0]["id"]
        r = s.patch(f"{API}/onboarding/portal/me/steps/{step_id}", json={"status": "garbage"})
        assert r.status_code == 400

        # 4. ready_for_review → ok
        r = s.patch(f"{API}/onboarding/portal/me/steps/{step_id}", json={"status": "ready_for_review"})
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("ok") is True

        # 5. complete → ok and persisted
        r = s.patch(f"{API}/onboarding/portal/me/steps/{step_id}", json={"status": "complete"})
        assert r.status_code == 200
        # Re-fetch and verify
        r = s.get(f"{API}/onboarding/portal/me")
        assert r.status_code == 200
        updated = next((s_ for s_ in r.json()["steps"] if s_["id"] == step_id), None)
        assert updated is not None
        assert updated["status"] == "complete"

        # Cleanup: archive project
        admin.patch(f"{API}/onboarding/projects/{proj['id']}", json={"status": "archived"})


# ── Cleanup ───────────────────────────────────────────────────────────────────

def test_zzz_cleanup(admin):
    """Archive any TESTONB5 projects created in this run."""
    r = admin.get(f"{API}/onboarding/reports")
    if r.status_code != 200:
        return
    rows = r.json().get("rows", [])
    # Need IDs — refetch via /onboarding/projects list if available
    listed = admin.get(f"{API}/onboarding/projects")
    if listed.status_code == 200:
        projects = listed.json()
        if isinstance(projects, dict):
            projects = projects.get("projects") or projects.get("rows") or []
        for p in projects:
            if TEST_TAG in (p.get("customer_name") or ""):
                admin.patch(f"{API}/onboarding/projects/{p['id']}", json={"status": "archived"})
