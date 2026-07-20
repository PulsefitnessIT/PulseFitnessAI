"""End-to-end backend tests for the Staff Onboarding, Offer Letter & Employment
Contract Wizard (Phase 1 spine).

Covers HR case → invite → recruit portal (accept-invite, forms, upload,
policies, agreements, submit) → RTW → paperwork-complete gate → offer
create/approve/issue + gate → accept → contract create/approve/issue → sign →
countersign → activate → audit trail.
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
    """Login sparingly (login is rate-limited 429)."""
    for attempt in range(3):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": HR_EMAIL, "password": HR_PASSWORD}, timeout=30)
        if r.status_code == 200:
            return r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")
        if r.status_code == 429:
            time.sleep(40)
            continue
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


# ─────────────── HR settings + duplicate check + create case ───────────────
def test_01_settings_seeds(hr):
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/settings")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("packages") and len(data["packages"]) >= 5
    r2 = hr.get(f"{BASE_URL}/api/staff-onboarding/templates")
    assert r2.status_code == 200
    t = r2.json()
    assert len(t["offer"]) >= 1 and len(t["contract"]) >= 1
    assert len(t["policies"]) == 5 and len(t["agreements"]) == 4


def test_02_duplicate_check(hr):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/duplicate-check",
                json={"personal_email": "definitely-no-such@example.test"})
    assert r.status_code == 200
    assert "matches" in r.json()


def test_03_create_case(hr, state):
    unique = uuid.uuid4().hex[:8]
    email = f"TEST_recruit_{unique}@example.test"
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases", json={
        "legal_first_name": "TEST", "surname": f"Recruit{unique}",
        "preferred_name": "TestR", "personal_email": email,
        "mobile": "07000000000", "position": "Field Service Engineer",
        "proposed_start_date": "2026-02-15",
    })
    assert r.status_code == 200, r.text
    case = r.json()
    assert case["staff_id"] and case["id"]
    state["case_id"] = case["id"]
    state["staff_id"] = case["staff_id"]
    state["email"] = email


def test_04_patch_case(hr, state):
    r = hr.patch(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}", json={
        "package": "engineer",
        "employment_proposal": {
            "job_title": "Field Service Engineer", "department": "Service",
            "site": "HQ", "line_manager": "Ops Manager",
            "proposed_start_date": "2026-02-15", "salary": "£30,000",
            "hours_per_week": 40, "employment_type": "Permanent Full-Time",
            "probation_period": "3 months", "notice_period": "1 month",
            "holiday_entitlement": "25 days + BH", "employing_company": "Pulse Fitness Ltd",
            "pay_frequency": "Monthly", "authorised_signatory": "HR Director",
        },
    })
    assert r.status_code == 200, r.text
    assert r.json().get("package") == "engineer"


def test_05_invite(hr, state):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/invite", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["invite_token"] and data["portal_path"].startswith("/new-starter/")
    state["invite_token"] = data["invite_token"]


# ─────────────── Recruit portal ───────────────
def test_06_accept_invite_creates_user(state):
    r = requests.post(f"{BASE_URL}/api/new-starter/accept-invite",
                      json={"token": state["invite_token"], "password": RECRUIT_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("token") and body["user"]["role"] == "recruit"
    state["recruit_token"] = body["token"]
    state["recruit_user_id"] = body["user"]["id"]


def test_07_password_too_short(state):
    r = requests.post(f"{BASE_URL}/api/new-starter/accept-invite",
                      json={"token": state["invite_token"], "password": "short"}, timeout=30)
    assert r.status_code == 400


@pytest.fixture(scope="module")
def rec(state):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {state['recruit_token']}"})
    return s


def test_08_recruit_me(rec):
    r = rec.get(f"{BASE_URL}/api/new-starter/me")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["portal_name"] == "Pulse Fitness New Starter Portal"
    assert d["activated"] is False
    assert len(d["policies"]) == 5 and len(d["agreements"]) == 4


def test_09_save_new_starter_form(rec):
    r = rec.post(f"{BASE_URL}/api/new-starter/forms".replace("/api/new-starter/forms",
                                                             "/api/new-starter/forms"),
                 json={})  # placeholder; use PUT below
    # actual: PUT
    r = rec.put(f"{BASE_URL}/api/new-starter/forms", json={
        "form_key": "new_starter",
        "data": {
            "legal_name": "TEST Recruit", "date_of_birth": "1990-01-01",
            "address": "1 Test St", "emergency_contact_name": "Kin",
            "emergency_contact_phone": "07999999999",
            "bank_account": "12345678", "sort_code": "12-34-56",
            "ni_number": "AB123456C",
        },
    })
    assert r.status_code == 200, r.text


def test_10_recruit_upload(rec, state):
    files = {"file": ("id.png", io.BytesIO(b"\x89PNG\r\n\x1a\nfakepng" + b"0" * 100), "image/png")}
    data = {"document_type": "identity"}
    r = requests.post(f"{BASE_URL}/api/new-starter/upload", files=files, data=data,
                      headers={"Authorization": rec.headers["Authorization"]}, timeout=60)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc.get("file_hash") and doc.get("storage_path")
    state["doc_id"] = doc["id"]


def test_11_ack_policies(rec, state):
    me = rec.get(f"{BASE_URL}/api/new-starter/me").json()
    for pol in me["policies"]:
        r = rec.post(f"{BASE_URL}/api/new-starter/policies/{pol['key']}/acknowledge",
                     json={"signature_name": "TEST Recruit"})
        assert r.status_code == 200, r.text


def test_12_sign_agreements(rec):
    me = rec.get(f"{BASE_URL}/api/new-starter/me").json()
    for agr in me["agreements"]:
        r = rec.post(f"{BASE_URL}/api/new-starter/agreements/{agr['key']}/sign",
                     json={"signature_name": "TEST Recruit", "signature_method": "typed",
                           "acknowledge": True})
        assert r.status_code == 200, r.text


def test_13_submit(rec):
    r = rec.post(f"{BASE_URL}/api/new-starter/submit", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_hr_review"


# ─────────────── Gates: RTW + paperwork ───────────────
def test_14_offer_before_paperwork_fails(hr, state):
    templates = hr.get(f"{BASE_URL}/api/staff-onboarding/templates").json()
    tmpl = [t for t in templates["offer"] if "engineer" in t["target_roles"]][0]
    state["offer_template_id"] = tmpl["id"]
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/offer",
                json={"template_id": tmpl["id"]})
    assert r.status_code == 400


def test_15_rtw_verify(hr, state):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/right-to-work",
                json={"method": "manual", "result": "verified"})
    assert r.status_code == 200


def test_16_paperwork_state_all_complete(hr, state):
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/paperwork-state")
    assert r.status_code == 200
    d = r.json()
    assert d["all_complete"] is True, d


def test_17_paperwork_complete(hr, state):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/paperwork-complete",
                json={"comment": "All good"})
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_offer"


# ─────────────── Offer ───────────────
def test_18_offer_create_approve_issue(hr, state):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/offer",
                json={"template_id": state["offer_template_id"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/offer/approve",
                json={"comment": "ok"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/offer/issue", json={})
    assert r.status_code == 200 and r.json()["status"] == "issued"


def test_19_contract_before_offer_accepted_fails(hr, state):
    templates = hr.get(f"{BASE_URL}/api/staff-onboarding/templates").json()
    ct = [t for t in templates["contract"] if "engineer" in t["target_roles"]][0]
    state["contract_template_id"] = ct["id"]
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/contract",
                json={"template_id": ct["id"]})
    assert r.status_code == 400


def test_20_offer_accept(rec, state):
    r = rec.post(f"{BASE_URL}/api/new-starter/offer/respond",
                 json={"action": "accept", "signature_name": "TEST Recruit",
                       "intended_start_date": "2026-02-15"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"
    assert r.json().get("certificate_id")


# ─────────────── Contract ───────────────
def test_21_contract_create_has_differences(hr, state):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/contract",
                json={"template_id": state["contract_template_id"]})
    assert r.status_code == 200, r.text
    con = r.json()
    assert "differences" in con and isinstance(con["differences"], list)
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/contract/approve",
                json={"comment": "ok"})
    assert r.status_code == 200
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/contract/issue", json={})
    assert r.status_code == 200 and r.json()["status"] == "issued"


def test_22_contract_sign_employee(rec):
    r = rec.post(f"{BASE_URL}/api/new-starter/contract/sign",
                 json={"signature_name": "TEST Recruit", "signature_method": "typed",
                       "acknowledge": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "employee_signed"


def test_23_contract_countersign(hr, state):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/contract/countersign",
                json={"signature_name": "HR Director", "signature_method": "typed", "acknowledge": True})
    assert r.status_code == 200, r.text
    con = r.json()
    assert con["status"] == "fully_signed" and con.get("locked") is True
    assert con.get("certificate_id")


# ─────────────── Activation ───────────────
def test_24_activation_ready(hr, state):
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/activation-state")
    assert r.status_code == 200
    assert r.json()["ready"] is True, r.json()


def test_25_activate(hr, state):
    r = hr.post(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/activate", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "complete"
    assert r.json()["staff_id"] == state["staff_id"]  # SAME staff record


def test_26_portal_becomes_staff_portal_same_account(rec, state):
    r = rec.get(f"{BASE_URL}/api/new-starter/me")
    assert r.status_code == 200
    d = r.json()
    assert d["portal_name"] == "Pulse Fitness Staff Portal"
    assert d["activated"] is True


def test_27_audit_has_many_events(hr, state):
    r = hr.get(f"{BASE_URL}/api/staff-onboarding/cases/{state['case_id']}/audit")
    assert r.status_code == 200
    events = r.json()["events"]
    kinds = {e["event"] for e in events}
    for req in ["case_created", "invite_sent", "invite_accepted", "form_submitted",
                "document_uploaded", "policy_acknowledged", "agreement_signed",
                "pack_submitted", "right_to_work_verified", "paperwork_complete",
                "offer_created", "offer_approved", "offer_issued", "offer_accepted",
                "contract_created", "contract_approved", "contract_issued",
                "contract_employee_signed", "contract_fully_signed", "employee_activated"]:
        assert req in kinds, f"missing audit event: {req} — got {kinds}"
    assert len(events) >= 20


def test_28_no_duplicate_staff_member(hr, state):
    """The staff_id must remain the SAME single record throughout."""
    from pymongo import MongoClient
    import os as _os
    mongo_url = _os.environ.get("MONGO_URL")
    # If we can't get mongo direct, use API to confirm listing shows just one entry for our email
    if not mongo_url:
        pytest.skip("no MONGO_URL")
    client = MongoClient(mongo_url)
    dbn = _os.environ.get("DB_NAME", "test_database")
    coll = client[dbn].staff_members
    same = list(coll.find({"email": state["email"].lower()}))
    assert len(same) == 1, f"duplicate staff_members rows for {state['email']}: {len(same)}"
    assert same[0]["id"] == state["staff_id"]
    assert same[0]["active"] is True
    assert same[0]["lifecycle_stage"] == "employee"
