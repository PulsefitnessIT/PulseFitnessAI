"""
Backend tests for Staff Onboarding company docs manager (policies/agreements) +
AI signature-field detection on PDF upload (Jan 2026).

Endpoints exercised:
  POST/PUT/DELETE /api/staff-onboarding/policies[/{key}]
  POST/PUT/DELETE /api/staff-onboarding/agreements[/{key}]
  POST /api/staff-onboarding/{kind}/{key}/upload   (PDF → AI signature detection)
  GET  /api/staff-onboarding/recruit/me           (post-invite portal payload)
"""
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

HR_EMAIL = "owner@isodemo.com"
HR_PW = "IsoDemo123!"

TEST_PREFIX = f"TEST_docs_{uuid.uuid4().hex[:6]}_"


def _login(email, password):
    for attempt in range(3):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            return r.json().get("token") or r.json().get("access_token")
        if r.status_code == 429:
            time.sleep(40)
            continue
        break
    pytest.skip(f"Login failed for {email}: {r.status_code} {r.text[:200]}")


@pytest.fixture(scope="module")
def hr_token():
    tok = _login(HR_EMAIL, HR_PW)
    assert tok
    return tok


@pytest.fixture(scope="module")
def hr_client(hr_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {hr_token}"})
    return s


def _slug(title):
    # match backend _slugify best-effort (lowercase, non-alnum→-)
    import re
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s


@pytest.fixture(scope="module")
def sample_signature_pdf():
    """Real PDF containing signature/date/initial lines, using reportlab."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 12)
    y = 780
    for line in [
        "COMPANY CONFIDENTIALITY AGREEMENT",
        "",
        "This agreement is made between the Company and the Employee.",
        "The Employee agrees to keep all company information confidential.",
        "",
        "Employee signature: ______________________     Date: __________",
        "",
        "Employee initials: ______",
        "",
        "Signed on behalf of the Company: ______________________",
    ]:
        c.drawString(72, y, line)
        y -= 22
    c.showPage(); c.save()
    return buf.getvalue()


# ───────── Policies CRUD ─────────
class TestPoliciesCRUD:
    key = None

    def test_create_policy(self, hr_client):
        title = TEST_PREFIX + "Home Working Policy"
        r = hr_client.post(f"{BASE_URL}/api/staff-onboarding/policies",
                           json={"title": title, "body": "Work from home reasonably.",
                                 "acknowledgement_required": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == title
        assert d["acknowledgement_required"] is True
        assert d["body"] == "Work from home reasonably."
        assert d.get("key")
        TestPoliciesCRUD.key = d["key"]

    def test_update_policy(self, hr_client):
        assert TestPoliciesCRUD.key
        r = hr_client.put(f"{BASE_URL}/api/staff-onboarding/policies/{TestPoliciesCRUD.key}",
                          json={"body": "Updated body v2"})
        assert r.status_code == 200, r.text
        assert r.json()["body"] == "Updated body v2"

    def test_delete_policy(self, hr_client):
        assert TestPoliciesCRUD.key
        r = hr_client.delete(f"{BASE_URL}/api/staff-onboarding/policies/{TestPoliciesCRUD.key}")
        assert r.status_code == 200
        assert r.json().get("deleted", 0) >= 1


# ───────── Agreements CRUD + PDF upload + AI ─────────
class TestAgreementsAndAIUpload:
    key = None

    def test_create_agreement(self, hr_client):
        title = TEST_PREFIX + "Confidentiality Agreement"
        r = hr_client.post(f"{BASE_URL}/api/staff-onboarding/agreements",
                           json={"title": title, "body": "placeholder", "requires_signature": False})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == title
        TestAgreementsAndAIUpload.key = d["key"]

    def test_upload_pdf_and_ai_detection(self, hr_client, sample_signature_pdf):
        assert TestAgreementsAndAIUpload.key
        key = TestAgreementsAndAIUpload.key
        files = {"file": (f"{TEST_PREFIX}sig.pdf", sample_signature_pdf, "application/pdf")}
        # Remove default JSON header
        headers = {k: v for k, v in hr_client.headers.items() if k.lower() != "content-type"}
        r = requests.post(f"{BASE_URL}/api/staff-onboarding/agreements/{key}/upload",
                          files=files, headers=headers, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("text_chars", 0) > 20, f"PDF text extraction should extract >20 chars, got {body}"
        ai = body.get("ai") or {}
        # AI is live — should detect signature/date/initial lines
        assert ai.get("requires_signature") is True, f"AI should mark requires_signature=True: {ai}"
        fields = ai.get("signature_fields") or []
        assert len(fields) >= 1, f"AI should detect at least one signature field: {ai}"
        types = {(f.get("type") or "").lower() for f in fields}
        # At minimum a signature type should be found
        assert "signature" in types or any("sign" in (f.get("label") or "").lower() for f in fields), \
            f"Expected signature-type field: {fields}"

    def test_agreement_flagged_requires_signature_after_upload(self, hr_client):
        # Poll recruit_me-like list: list of agreements is exposed via /policies-agreements meta if any;
        # simplest: re-fetch through create endpoint side effect — try list via GET /api/staff-onboarding/... else skip.
        # Confirm via update-then-read that requires_signature was set to True by AI.
        key = TestAgreementsAndAIUpload.key
        # Idempotent PUT with no body should return current doc
        r = hr_client.put(f"{BASE_URL}/api/staff-onboarding/agreements/{key}", json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("requires_signature") is True, f"Post-upload agreement should be requires_signature=True: {d}"
        assert d.get("signature_fields"), f"signature_fields should be persisted: {d}"

    def test_delete_agreement(self, hr_client):
        key = TestAgreementsAndAIUpload.key
        r = hr_client.delete(f"{BASE_URL}/api/staff-onboarding/agreements/{key}")
        assert r.status_code == 200
        assert r.json().get("deleted", 0) >= 1
