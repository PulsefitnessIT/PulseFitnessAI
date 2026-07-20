"""Phase 2 backend tests for Staff Onboarding: template builder (merge fields,
preview, create/update with versioning, reset-defaults), DBS/RTW checks
workflow, and PDF endpoints for offer + contract.

Also runs a mini spine (create case → invite → accept → forms → policies →
agreements → submit → paperwork-complete → offer create/approve/issue →
recruit accept → contract create/approve/issue → recruit sign) purely to
have offer + contract fixtures available for the PDF endpoint tests. The full
spine is covered by test_staff_onboarding_wizard_jan2026.py.
"""
from __future__ import annotations

import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

HR_EMAIL = "owner@isodemo.com"
HR_PASSWORD = "IsoDemo123!"
RECRUIT_PASSWORD = "Recruit123!"


@pytest.fixture(scope="module")
def hr_token():
    for attempt in range(3):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": HR_EMAIL, "password": HR_PASSWORD}, timeout=30)
        if r.status_code == 200:
            return r.json().get("access_token") or r.json().get("token")
        if r.status_code == 429:
            time.sleep(40); continue
        pytest.skip(f"HR login failed: {r.status_code} {r.text}")
    pytest.skip("HR login rate-limited")


@pytest.fixture(scope="module")
def hr(hr_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {hr_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def state():
    return {}


# ═════════════ Template Builder ═════════════
def test_01_merge_fields(hr):
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/merge-fields")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "fields" in data and len(data["fields"]) >= 20
    keys = [f["key"] for f in data["fields"]]
    for req in ("legal_name", "company", "job_title", "salary", "start_date"):
        assert req in keys, f"missing key {req}"
    # token format {{key}}
    assert all(f["token"] == "{{" + f["key"] + "}}" for f in data["fields"])


def test_02_reset_defaults(hr):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/templates/reset-defaults")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert isinstance(body.get("reset"), int)


def test_03_preview_placeholder_substitutes(hr):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/templates/preview",
                json={"body": "Dear {{legal_name}}, offering {{job_title}} at {{company}}."})
    assert r.status_code == 200, r.text
    rendered = r.json()["rendered"]
    assert "{{" not in rendered  # no unresolved tokens
    assert "[Legal name" in rendered or "[Legal" in rendered or "legal" in rendered.lower()


def test_04_templates_list_and_pick_existing(hr, state):
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/templates")
    assert r.status_code == 200
    t = r.json()
    assert t["offer"] and t["contract"]
    off = t["offer"][0]
    con = t["contract"][0]
    # body should have realistic UK wording (has merge fields)
    assert "{{" in (off.get("body") or "")
    state["offer_tmpl_id"] = off["id"]
    state["offer_tmpl_version_before"] = off.get("version", 1)
    state["contract_tmpl_id"] = con["id"]


def test_05_update_template_increments_version_and_flips_sample(hr, state):
    tid = state["offer_tmpl_id"]
    new_body = "UPDATED " + uuid.uuid4().hex[:6] + " Hello {{legal_name}}"
    r = hr.put(f"{BASE_URL}/api/staff-onboarding/templates/offer/{tid}",
               json={"body": new_body, "title": "TEST_Updated Offer"})
    assert r.status_code == 200, r.text
    upd = r.json()
    assert upd["version"] == state["offer_tmpl_version_before"] + 1
    assert upd["is_sample"] is False
    assert upd["body"] == new_body
    assert upd["title"] == "TEST_Updated Offer"


def test_06_template_versions_history(hr, state):
    tid = state["offer_tmpl_id"]
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/templates/offer/{tid}/versions")
    assert r.status_code == 200
    vers = r.json()["versions"]
    assert len(vers) >= 1
    assert vers[0].get("version") == state["offer_tmpl_version_before"]


def test_07_create_new_template(hr, state):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/templates/offer",
                json={"title": "TEST_Custom Offer " + uuid.uuid4().hex[:6],
                      "target_roles": ["engineer"],
                      "body": "Hello {{legal_name}}, custom offer body."})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["id"] and doc["version"] == 1 and doc["is_sample"] is False
    state["custom_offer_tmpl_id"] = doc["id"]


def test_08_reset_defaults_restores_sample(hr, state):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/templates/reset-defaults")
    assert r.status_code == 200
    # verify seed offer template body restored
    r2 = hr.get(f"{BASE_URL}/api/staff-onboarding/templates")
    off = [t for t in r2.json()["offer"] if t["id"] == state["offer_tmpl_id"]]
    assert off and off[0]["is_sample"] is True


# ═════════════ Checks options + case + RTW/DBS persistence ═════════════
def test_10_checks_options(hr):
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/checks/options")
    assert r.status_code == 200, r.text
    d = r.json()
    assert isinstance(d.get("rtw_methods"), list) and len(d["rtw_methods"]) >= 3
    assert isinstance(d.get("dbs_statuses"), list) and len(d["dbs_statuses"]) >= 5


def _mini_create_case(hr):
    unique = uuid.uuid4().hex[:8]
    email = f"TEST_p2_{unique}@example.test"
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases", json={
        "legal_first_name": "TEST", "surname": f"Phase2{unique}",
        "preferred_name": "P2", "personal_email": email,
        "mobile": "07100000001", "position": "Field Service Engineer",
        "proposed_start_date": "2026-03-01",
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_11_case_and_rtw_dbs_persist(hr, state):
    c = _mini_create_case(hr)
    state["cid"] = c["id"]
    cid = c["id"]

    # RTW save
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/right-to-work",
                json={"method": "share_code", "result": "verified",
                      "share_code": "ABC123XYZ", "document_type": "passport"})
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "verified"

    # DBS required toggle
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/dbs-required?required=true")
    assert r.status_code == 200
    assert r.json()["dbs_required"] is True

    # DBS save
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/dbs",
                json={"level": "enhanced", "status": "clear",
                      "certificate_number": "DBS-TEST-001",
                      "issue_date": "2026-01-15"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "clear"

    # Verify GET reflects saved values
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/checks")
    assert r.status_code == 200
    d = r.json()
    assert d["right_to_work"] and d["right_to_work"]["result"] == "verified"
    assert d["right_to_work"]["share_code"] == "ABC123XYZ"
    assert d["dbs"] and d["dbs"]["status"] == "clear"
    assert d["dbs"]["certificate_number"] == "DBS-TEST-001"
    assert d["dbs_required"] is True


# ═════════════ Full spine to unlock offer + contract for PDF ═════════════
def _get(hr, path):
    r = hr.get(f"{BASE_URL}{path}")
    return r.json() if r.status_code == 200 else None


def test_20_spine_to_offer_and_contract(hr, state):
    """Build a case up to contract issued so PDF endpoints have data."""
    cid = state["cid"]

    # invite
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/invite", json={})
    assert r.status_code == 200, r.text
    invite_token = r.json()["invite_token"]

    # recruit accepts (creates user)
    r = requests.post(f"{BASE_URL}/api/new-starter/accept-invite",
                      json={"token": invite_token, "password": RECRUIT_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    recruit_token = r.json()["token"]
    rec = requests.Session()
    rec.headers.update({"Authorization": f"Bearer {recruit_token}",
                        "Content-Type": "application/json"})

    # fill forms
    me = rec.get(f"{BASE_URL}/api/new-starter/me", timeout=30).json()
    r = rec.put(f"{BASE_URL}/api/new-starter/forms", json={
        "form_key": "new_starter",
        "data": {"legal_first_name": "TEST", "surname": "Phase2",
                 "dob": "1990-01-01", "address": "1 Test St",
                 "ni_number": "AB123456C", "bank_account": "12345678",
                 "sort_code": "12-34-56",
                 "emergency_contact_name": "EM", "emergency_contact_phone": "07000000000"}})
    assert r.status_code == 200

    # upload id doc
    files = {"file": ("passport.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"kind": "id_document", "label": "Passport"}
    r = requests.post(f"{BASE_URL}/api/new-starter/upload", files=files, data=data,
                      headers={"Authorization": f"Bearer {recruit_token}"}, timeout=60)
    assert r.status_code == 200, r.text

    # acknowledge all policies + agreements
    me = rec.get(f"{BASE_URL}/api/new-starter/me").json()
    for p in me.get("policies", []):
        rec.post(f"{BASE_URL}/api/new-starter/policies/{p['key']}/acknowledge", json={})
    me = rec.get(f"{BASE_URL}/api/new-starter/me").json()
    for a in me.get("agreements", []):
        rec.post(f"{BASE_URL}/api/new-starter/agreements/{a['key']}/sign",
                 json={"typed_signature": "TEST Phase2"})

    # submit
    r = rec.post(f"{BASE_URL}/api/new-starter/submit", json={})
    assert r.status_code == 200

    # HR: RTW cleared (already), paperwork-complete
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/paperwork-complete", json={})
    assert r.status_code == 200, r.text

    # offer
    templates = hr.get(f"{BASE_URL}/api/staff-onboarding/templates").json()
    offer_tmpl = [t for t in templates["offer"] if "engineer" in t.get("target_roles", [])]
    offer_tmpl = offer_tmpl[0] if offer_tmpl else templates["offer"][0]
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/offer",
                json={"template_id": offer_tmpl["id"]})
    assert r.status_code == 200, r.text
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/offer/approve", json={})
    assert r.status_code == 200
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/offer/issue", json={})
    assert r.status_code == 200

    state["recruit_token"] = recruit_token

    # Recruit accepts offer
    r = rec.post(f"{BASE_URL}/api/new-starter/offer/respond",
                 json={"action": "accept", "signature_name": "TEST Phase2"})
    assert r.status_code == 200, r.text

    # Contract
    contract_tmpl = [t for t in templates["contract"] if "engineer" in t.get("target_roles", [])]
    contract_tmpl = contract_tmpl[0] if contract_tmpl else templates["contract"][0]
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/contract",
                json={"template_id": contract_tmpl["id"]})
    assert r.status_code == 200, r.text
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/contract/approve", json={})
    assert r.status_code == 200
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/contract/issue", json={})
    assert r.status_code == 200


# ═════════════ PDFs ═════════════
def test_30_hr_offer_pdf(hr, state):
    cid = state["cid"]
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/offer.pdf")
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 1000


def test_31_hr_contract_pdf(hr, state):
    cid = state["cid"]
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/contract.pdf")
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF-")


def test_32_recruit_offer_pdf(state):
    tok = state.get("recruit_token")
    if not tok:
        pytest.skip("recruit token unavailable")
    r = requests.get(f"{BASE_URL}/api/new-starter/offer.pdf",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    assert r.content.startswith(b"%PDF-")


def test_33_recruit_contract_pdf(state):
    tok = state.get("recruit_token")
    if not tok:
        pytest.skip("recruit token unavailable")
    r = requests.get(f"{BASE_URL}/api/new-starter/contract.pdf",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    assert r.content.startswith(b"%PDF-")


def test_34_offer_pdf_404_when_no_offer(hr):
    # Create a fresh case with no offer
    c = _mini_create_case(hr)
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{c['id']}/offer.pdf")
    assert r.status_code == 404


# ═════════════ Route ordering sanity ═════════════
def test_40_preview_not_treated_as_kind(hr):
    """`/templates/preview` must NOT be captured by `/templates/{kind}` POST."""
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/templates/preview",
                json={"body": "hi {{legal_name}}"})
    assert r.status_code == 200
    assert "rendered" in r.json()


def test_41_reset_defaults_not_treated_as_kind(hr):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/templates/reset-defaults")
    assert r.status_code == 200
    assert r.json().get("ok") is True
