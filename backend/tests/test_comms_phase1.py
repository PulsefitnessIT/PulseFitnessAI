"""Phase 1 — Comms Centre / shared Campaign Engine backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-eng-booking.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"


@pytest.fixture(scope="module")
def auth_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    # Try common login endpoints
    candidates = ["/api/auth/login", "/api/auth/email/login", "/api/login"]
    token = None
    for ep in candidates:
        r = s.post(f"{BASE_URL}{ep}", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
        if r.status_code == 200:
            data = r.json()
            token = data.get("token") or data.get("access_token") or (data.get("data") or {}).get("token")
            if token:
                break
    if not token:
        pytest.skip(f"Could not authenticate master admin: tried {candidates}")
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def created_campaign(auth_client):
    r = auth_client.post(
        f"{BASE_URL}/api/comms/campaigns",
        json={
            "campaign_type": "newsletter",
            "name": "TEST_pytest_newsletter",
            "content": {
                "subject": "Hello {{first_name}}",
                "blocks": [
                    {"type": "heading", "props": {"text": "Hi {{first_name}}"}},
                    {"type": "text", "props": {"text": "Welcome to Pulse"}},
                    {"type": "footer", "props": {"text": "From Pulse Fitness AI"}},
                ],
            },
        },
        timeout=30,
    )
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text[:300]}"
    return r.json()["campaign"]


class TestMeta:
    def test_meta(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/comms/meta", timeout=20)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert len(data["campaign_types"]) == 27
        assert len(data["statuses"]) == 10
        assert len(data["blocks"]) == 11
        assert set(data["modules"]) == {"marketing", "memberships", "crm"}
        assert "member" in data["merge_tags"] and "b2b" in data["merge_tags"]


class TestUnauthenticated:
    def test_meta_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/comms/meta", timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


class TestCreateAndModuleDerivation:
    def test_member_announcement_derives_memberships(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={"campaign_type": "member_announcement", "name": "TEST_ma"},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        c = r.json()["campaign"]
        assert c["related_module"] == "memberships"
        assert c["status"] == "draft"
        assert c["campaign_type"] == "member_announcement"

    def test_sales_followup_derives_crm(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={"campaign_type": "sales_followup", "name": "TEST_sf"},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json()["campaign"]["related_module"] == "crm"

    def test_newsletter_derives_marketing(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={"campaign_type": "newsletter", "name": "TEST_nl"},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json()["campaign"]["related_module"] == "marketing"

    def test_unknown_type_rejected(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={"campaign_type": "bogus_xyz", "name": "TEST_x"},
            timeout=20,
        )
        assert r.status_code == 400

    def test_blocks_render_body_html(self, auth_client, created_campaign):
        # Verify content.body_html was auto-rendered
        cid = created_campaign["id"]
        r = auth_client.get(f"{BASE_URL}/api/comms/campaigns/{cid}", timeout=20)
        assert r.status_code == 200
        body = r.json()["campaign"]["content"].get("body_html") or ""
        assert "<table" in body
        assert "Hi {{first_name}}" in body  # raw kept in stored html


class TestListFilters:
    def test_list_filter_memberships(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/comms/campaigns?module=memberships", timeout=20)
        assert r.status_code == 200
        for d in r.json()["campaigns"]:
            assert d["related_module"] == "memberships"

    def test_list_filter_crm(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/comms/campaigns?module=crm", timeout=20)
        assert r.status_code == 200
        for d in r.json()["campaigns"]:
            assert d["related_module"] == "crm"

    def test_list_filter_type(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/comms/campaigns?type=newsletter", timeout=20)
        assert r.status_code == 200
        for d in r.json()["campaigns"]:
            assert d["campaign_type"] == "newsletter"

    def test_list_filter_q(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/comms/campaigns?q=TEST_pytest", timeout=20)
        assert r.status_code == 200
        names = [d["name"] for d in r.json()["campaigns"]]
        assert any("TEST_pytest" in n for n in names)


class TestQualityAndUpdate:
    def test_quality_no_subject(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={
                "campaign_type": "regular",
                "name": "TEST_q_nosub",
                "content": {"subject": "", "blocks": [{"type": "text", "props": {"text": "hi"}}]},
            },
            timeout=20,
        )
        cid = r.json()["campaign"]["id"]
        g = auth_client.get(f"{BASE_URL}/api/comms/campaigns/{cid}", timeout=20).json()
        codes = [w["code"] for w in g["quality"]]
        assert "no_subject" in codes
        assert "no_unsubscribe" in codes  # no footer/unsubscribe

    def test_quality_broken_merge_tag(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={
                "campaign_type": "regular",
                "name": "TEST_q_brokenmerge",
                "content": {
                    "subject": "Hi {{unknown_tag_xyz}}",
                    "blocks": [{"type": "text", "props": {"text": "x"}}],
                },
            },
            timeout=20,
        )
        cid = r.json()["campaign"]["id"]
        g = auth_client.get(f"{BASE_URL}/api/comms/campaigns/{cid}", timeout=20).json()
        codes = [w["code"] for w in g["quality"]]
        assert "broken_merge_tag" in codes

    def test_quality_missing_alt(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={
                "campaign_type": "regular",
                "name": "TEST_q_alt",
                "content": {
                    "subject": "Subject",
                    "blocks": [{"type": "image", "props": {"src": "x"}}],
                },
            },
            timeout=20,
        )
        cid = r.json()["campaign"]["id"]
        g = auth_client.get(f"{BASE_URL}/api/comms/campaigns/{cid}", timeout=20).json()
        codes = [w["code"] for w in g["quality"]]
        assert "missing_alt" in codes

    def test_update_re_renders_body_html(self, auth_client, created_campaign):
        cid = created_campaign["id"]
        r = auth_client.put(
            f"{BASE_URL}/api/comms/campaigns/{cid}",
            json={
                "name": "TEST_pytest_renamed",
                "content": {
                    "subject": "Updated subject",
                    "blocks": [{"type": "heading", "props": {"text": "UPDATED_HEADING_TOKEN"}}],
                },
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        # verify persistence
        g = auth_client.get(f"{BASE_URL}/api/comms/campaigns/{cid}", timeout=20).json()
        assert g["campaign"]["name"] == "TEST_pytest_renamed"
        assert "UPDATED_HEADING_TOKEN" in g["campaign"]["content"]["body_html"]


class TestStatusTransitions:
    def test_valid_transitions(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={"campaign_type": "regular", "name": "TEST_status"},
            timeout=20,
        )
        cid = r.json()["campaign"]["id"]
        s1 = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns/{cid}/status", json={"status": "in_review"}, timeout=20,
        )
        assert s1.status_code == 200
        assert s1.json()["status"] == "in_review"
        assert s1.json()["approval"]["status"] == "pending"
        s2 = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns/{cid}/status", json={"status": "approved"}, timeout=20,
        )
        assert s2.status_code == 200
        assert s2.json()["approval"]["status"] == "approved"

    def test_invalid_transition_rejected(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={"campaign_type": "regular", "name": "TEST_invalid_status"},
            timeout=20,
        )
        cid = r.json()["campaign"]["id"]
        # draft -> sent is not allowed
        bad = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns/{cid}/status", json={"status": "sent"}, timeout=20,
        )
        assert bad.status_code == 400


class TestDuplicateArchive:
    def test_duplicate_resets_metrics(self, auth_client, created_campaign):
        cid = created_campaign["id"]
        r = auth_client.post(f"{BASE_URL}/api/comms/campaigns/{cid}/duplicate", timeout=20)
        assert r.status_code == 200
        d = r.json()["campaign"]
        assert d["id"] != cid
        assert d["status"] == "draft"
        assert d["metrics"]["sent"] == 0
        assert "(copy)" in d["name"]

    def test_archive_soft_deletes(self, auth_client):
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns",
            json={"campaign_type": "regular", "name": "TEST_archive"},
            timeout=20,
        )
        cid = r.json()["campaign"]["id"]
        d = auth_client.delete(f"{BASE_URL}/api/comms/campaigns/{cid}", timeout=20)
        assert d.status_code == 200
        g = auth_client.get(f"{BASE_URL}/api/comms/campaigns/{cid}", timeout=20).json()
        assert g["campaign"]["status"] == "archived"


class TestPreviewAndTestSend:
    def test_preview_substitutes_tags(self, auth_client, created_campaign):
        cid = created_campaign["id"]
        r = auth_client.get(f"{BASE_URL}/api/comms/campaigns/{cid}/preview", timeout=20)
        assert r.status_code == 200, r.text[:300]
        p = r.json()
        # subject was "Updated subject" after update, fall back
        assert "{{" not in p["html"], "Raw tags remain in preview"
        assert "{{" not in p["subject"]

    def test_test_send(self, auth_client, created_campaign):
        cid = created_campaign["id"]
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns/{cid}/test-send",
            json={"to": "leersomers@gmail.com"},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "ok" in body
        assert body["sent_to"] == "leersomers@gmail.com"

    def test_test_send_invalid_email(self, auth_client, created_campaign):
        cid = created_campaign["id"]
        r = auth_client.post(
            f"{BASE_URL}/api/comms/campaigns/{cid}/test-send",
            json={"to": "notanemail"},
            timeout=20,
        )
        assert r.status_code == 400


class TestDashboard:
    def test_dashboard_aggregates(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/comms/dashboard", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_campaigns", "by_status", "by_module", "totals", "open_rate", "click_rate", "recent"):
            assert k in d
        assert isinstance(d["recent"], list)
        assert d["total_campaigns"] >= 1

    def test_dashboard_module_filter(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/comms/dashboard?module=crm", timeout=20)
        assert r.status_code == 200
        for d in r.json()["recent"]:
            assert d["related_module"] == "crm"
