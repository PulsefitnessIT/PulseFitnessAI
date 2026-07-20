"""Phase 2 REMAINING BACKLOG backend tests for Staff Onboarding:
 - Completed forms PDF (/cases/{id}/forms.pdf)
 - Onboarding pack PDF (/cases/{id}/pack.pdf)
 - Verification providers scaffold (/verification/providers)
 - Verification public webhook (/verification/webhook) with provider match
 - RTW/DBS extended with provider + provider_reference + provider_status
 - AI duplicate scan (/cases/{id}/ai/duplicate-scan)  — uses Emergent LLM key
 - AI consistency (/cases/{id}/ai/consistency) — uses Emergent LLM key
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
    for attempt in range(4):
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
    s.headers.update({"Authorization": f"Bearer {hr_token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def state():
    return {}


def _create_case(hr):
    unique = uuid.uuid4().hex[:8]
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases", json={
        "legal_first_name": "TEST", "surname": f"Backlog{unique}",
        "preferred_name": "BL", "personal_email": f"TEST_bl_{unique}@example.test",
        "mobile": "07100000001", "position": "Field Service Engineer",
        "proposed_start_date": "2026-04-01"})
    assert r.status_code == 200, r.text
    return r.json()


# ═══════════ Verification providers scaffold ═══════════
def test_01_verification_providers(hr):
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/verification/providers")
    assert r.status_code == 200, r.text
    d = r.json()
    provs = d.get("providers") or []
    assert len(provs) == 4, provs
    keys = {p["key"]: p for p in provs}
    for k in ("manual", "govuk_rtw", "idsp", "dbs_umbrella"):
        assert k in keys, f"missing provider {k}"
    assert keys["manual"]["configured"] is True
    assert keys["govuk_rtw"]["configured"] is False
    assert keys["idsp"]["configured"] is False
    assert keys["dbs_umbrella"]["configured"] is False
    assert d.get("webhook_secured") is False
    assert d.get("webhook_path", "").endswith("/verification/webhook")


# ═══════════ RTW/DBS extended fields persistence ═══════════
def test_10_rtw_and_dbs_with_provider(hr, state):
    c = _create_case(hr); cid = c["id"]; state["cid"] = cid
    ref_rtw = "REF-RTW-" + uuid.uuid4().hex[:6]
    ref_dbs = "REF-DBS-" + uuid.uuid4().hex[:6]
    state["ref_rtw"] = ref_rtw; state["ref_dbs"] = ref_dbs

    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/right-to-work",
                json={"method": "share_code", "result": "verified",
                      "share_code": "SC-XYZ",
                      "provider": "govuk_rtw",
                      "provider_reference": ref_rtw,
                      "provider_status": "initiated"})
    assert r.status_code == 200, r.text

    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/dbs",
                json={"level": "enhanced", "status": "requested",
                      "provider": "dbs_umbrella",
                      "provider_reference": ref_dbs,
                      "provider_status": "initiated"})
    assert r.status_code == 200, r.text

    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/checks")
    assert r.status_code == 200
    d = r.json()
    rtw = d["right_to_work"]; dbs = d["dbs"]
    assert rtw and rtw["provider"] == "govuk_rtw"
    assert rtw["provider_reference"] == ref_rtw
    assert rtw["provider_status"] == "initiated"
    assert dbs and dbs["provider"] == "dbs_umbrella"
    assert dbs["provider_reference"] == ref_dbs


# ═══════════ Public verification webhook ═══════════
def test_20_webhook_dbs_match_updates_record(state):
    ref = state["ref_dbs"]
    # NO auth header — public endpoint
    r = requests.post(f"{BASE_URL}/api/staff-onboarding/verification/webhook",
                      json={"check_type": "dbs", "provider": "dbs_umbrella",
                            "provider_reference": ref,
                            "status": "completed", "result": "clear",
                            "certificate_number": "C-9-" + ref[-4:]},
                      timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("matched")


def test_21_webhook_updates_reflected_in_checks(hr, state):
    cid = state["cid"]; ref = state["ref_dbs"]
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/checks")
    assert r.status_code == 200
    dbs = r.json()["dbs"]
    assert dbs["status"] == "clear"
    assert dbs["provider_status"] == "completed"
    assert dbs["certificate_number"] == "C-9-" + ref[-4:]


def test_22_webhook_404_on_bad_reference():
    r = requests.post(f"{BASE_URL}/api/staff-onboarding/verification/webhook",
                      json={"check_type": "dbs", "provider": "dbs_umbrella",
                            "provider_reference": "NO-SUCH-REF-12345",
                            "status": "completed", "result": "clear"},
                      timeout=30)
    assert r.status_code == 404, r.text


def test_23_webhook_400_on_malformed():
    r = requests.post(f"{BASE_URL}/api/staff-onboarding/verification/webhook",
                      json={"foo": "bar"}, timeout=30)
    assert r.status_code == 400


def test_24_webhook_rtw_match(state, hr):
    cid = state["cid"]; ref = state["ref_rtw"]
    r = requests.post(f"{BASE_URL}/api/staff-onboarding/verification/webhook",
                      json={"check_type": "rtw", "provider": "govuk_rtw",
                            "provider_reference": ref,
                            "status": "completed", "result": "verified",
                            "expiry": "2028-01-01"},
                      timeout=30)
    assert r.status_code == 200, r.text
    # confirm reflected
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/checks")
    rtw = r.json()["right_to_work"]
    assert rtw["provider_status"] == "completed"
    assert rtw.get("expiry") == "2028-01-01"


# ═══════════ Completed forms PDF ═══════════
def test_30_forms_pdf(hr, state):
    cid = state["cid"]
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/forms.pdf")
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 800


# ═══════════ Onboarding pack PDF ═══════════
def test_31_pack_pdf(hr, state):
    cid = state["cid"]
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/pack.pdf")
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 1000


# ═══════════ AI duplicate scan (Emergent LLM) ═══════════
def test_40_ai_duplicate_scan(hr, state):
    cid = state["cid"]
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/ai/duplicate-scan",
                json={}, timeout=90)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert "matches" in d and isinstance(d["matches"], list)
    assert "summary" in d
    # matches may be empty for a unique recruit; each match should carry shape
    for m in d["matches"]:
        assert "staff_id" in m
        assert "confidence" in m
        assert "reasons" in m


# ═══════════ AI consistency (Emergent LLM) — needs offer/contract ═══════════
def test_50_ai_consistency_400_without_offer(hr, state):
    cid = state["cid"]
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/ai/consistency",
                json={}, timeout=90)
    # this case has no offer yet
    assert r.status_code == 400, r.text[:200]


def test_51_ai_consistency_with_offer_and_contract(hr, state):
    """Build a full case with offer + contract to exercise AI consistency."""
    cid = state["cid"]

    # invite
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/invite", json={})
    if r.status_code != 200:
        pytest.skip(f"invite failed {r.status_code}: {r.text[:200]}")
    invite_token = r.json()["invite_token"]

    r = requests.post(f"{BASE_URL}/api/new-starter/accept-invite",
                      json={"token": invite_token, "password": RECRUIT_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    rt = r.json()["token"]
    rec = requests.Session()
    rec.headers.update({"Authorization": f"Bearer {rt}", "Content-Type": "application/json"})

    rec.put(f"{BASE_URL}/api/new-starter/forms", json={
        "form_key": "new_starter",
        "data": {"legal_first_name": "TEST", "surname": "Backlog",
                 "dob": "1990-01-01", "address": "1 Test St",
                 "ni_number": "AB123456C", "bank_account": "12345678",
                 "sort_code": "12-34-56",
                 "emergency_contact_name": "EM",
                 "emergency_contact_phone": "07000000000"}})

    files = {"file": ("passport.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    requests.post(f"{BASE_URL}/api/new-starter/upload", files=files,
                  data={"kind": "id_document", "label": "Passport"},
                  headers={"Authorization": f"Bearer {rt}"}, timeout=60)

    me = rec.get(f"{BASE_URL}/api/new-starter/me").json()
    for p in me.get("policies", []):
        rec.post(f"{BASE_URL}/api/new-starter/policies/{p['key']}/acknowledge", json={})
    me = rec.get(f"{BASE_URL}/api/new-starter/me").json()
    for a in me.get("agreements", []):
        rec.post(f"{BASE_URL}/api/new-starter/agreements/{a['key']}/sign",
                 json={"typed_signature": "TEST Backlog"})

    rec.post(f"{BASE_URL}/api/new-starter/submit", json={})
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/paperwork-complete", json={})
    if r.status_code != 200:
        pytest.skip(f"paperwork-complete failed: {r.text[:200]}")

    templates = hr.get(f"{BASE_URL}/api/staff-onboarding/templates").json()
    otmpl = templates["offer"][0]
    ctmpl = templates["contract"][0]

    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/offer",
                json={"template_id": otmpl["id"]})
    assert r.status_code == 200, r.text
    hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/offer/approve", json={})
    hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/offer/issue", json={})
    r = rec.post(f"{BASE_URL}/api/new-starter/offer/respond",
                 json={"action": "accept", "signature_name": "TEST Backlog"})
    assert r.status_code == 200, r.text

    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/contract",
                json={"template_id": ctmpl["id"]})
    assert r.status_code == 200, r.text
    hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/contract/approve", json={})
    hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/contract/issue", json={})

    # NOW run AI consistency
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/ai/consistency",
                json={}, timeout=90)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d.get("risk_level") in ("low", "medium", "high", "unknown")
    assert isinstance(d.get("inconsistencies"), list)
    assert "summary" in d
    assert "deterministic_differences" in d

    # pack.pdf now includes offer + contract
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{cid}/pack.pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 2000
