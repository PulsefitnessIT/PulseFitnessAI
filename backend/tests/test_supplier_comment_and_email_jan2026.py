"""Regression tests for supplier two-way chat notifying the customer,
and site_contact_email persistence on supplier cases (Issue 2), plus
smoke test on redesigned email builders not raising (Issue 1).
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

LITE_EMAIL = "lite.docs@pulsedemo.test"
LITE_PASSWORD = "LiteDocs123!"


@pytest.fixture(scope="module")
def user_token():
    r = requests.post(f"{API}/auth/login", json={"email": LITE_EMAIL, "password": LITE_PASSWORD})
    assert r.status_code == 200, f"user login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def issue_ctx(user_token):
    """Find or create an issue we can use to spin up a supplier case."""
    h = {"Authorization": f"Bearer {user_token}"}
    r = requests.get(f"{API}/issues", headers=h)
    issue = None
    if r.status_code == 200:
        data = r.json()
        items = data if isinstance(data, list) else data.get("issues", [])
        # Prefer an open one
        if items:
            issue = items[0]

    if not issue:
        # Need equipment first — pick or create
        er = requests.get(f"{API}/equipment", headers=h)
        eq_items = er.json() if er.status_code == 200 else []
        if isinstance(eq_items, dict):
            eq_items = eq_items.get("equipment", [])
        assert eq_items, f"no equipment available to create an issue: {er.status_code} {er.text[:200]}"
        eq = eq_items[0]
        payload = {
            "title": f"TEST_supplier_comment_{uuid.uuid4().hex[:6]}",
            "equipment_id": eq["id"],
            "serial_number": eq.get("serial_number") or "TEST-SN",
            "machine_type": eq.get("machine_type") or eq.get("type") or "Treadmill",
            "issue_description": "Automated regression fault",
            "severity": "medium",
            "issue_type": "reactive",
            "priority": "medium",
        }
        r = requests.post(f"{API}/issues", json=payload, headers=h)
        assert r.status_code in (200, 201), f"issue create failed: {r.status_code} {r.text}"
        issue = r.json()

    return {"token": user_token, "issue": issue}


def test_contact_supplier_creates_case_with_site_contact_email(issue_ctx):
    """Issue 1 + 2: contact-supplier endpoint 200 and stores site_contact_email."""
    h = {"Authorization": f"Bearer {issue_ctx['token']}"}
    issue_id = issue_ctx["issue"]["id"]
    payload = {
        "supplier_email": "supplier.qa@example.com",
        "message": "TEST_regression contacting supplier",
    }
    r = requests.post(f"{API}/issues/{issue_id}/contact-supplier", json=payload, headers=h)
    assert r.status_code == 200, f"contact-supplier failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("sent") is True
    token = body.get("supplier_case_token")
    assert token, f"missing token in {body}"

    # Fetch case publicly — verify site_contact_email populated
    r2 = requests.get(f"{API}/supplier/case/{token}")
    assert r2.status_code == 200, r2.text
    case = r2.json()
    assert case.get("site_contact_email", "").strip() != "", (
        f"site_contact_email should be populated on the case, got: {case.get('site_contact_email')!r}"
    )
    # stash for the next test
    pytest.supplier_token = token


def test_supplier_public_comment_saves_and_returns(issue_ctx):
    """Issue 2: unauthenticated supplier comment saves and is returned by GET."""
    token = getattr(pytest, "supplier_token", None)
    assert token, "prior test must have set supplier_token"

    msg = f"TEST_supplier_reply_{uuid.uuid4().hex[:6]}"
    # multipart form — no auth
    r = requests.post(
        f"{API}/supplier/case/{token}/comments",
        data={"message": msg, "author_name": "QA Supplier", "author_role": "supplier"},
    )
    assert r.status_code == 200, f"public comment failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("message") == msg
    assert body.get("author_role") == "supplier"

    # GET comments -> our message present
    r2 = requests.get(f"{API}/supplier/case/{token}/comments")
    assert r2.status_code == 200, r2.text
    comments = r2.json()
    if isinstance(comments, dict):
        comments = comments.get("comments", [])
    assert any(c.get("message") == msg for c in comments), (
        f"posted comment not found in list of {len(comments)} comments"
    )


def test_supplier_case_still_has_site_contact_email_after_comment(issue_ctx):
    """Issue 2: legacy heal branch — case still has site_contact_email after supplier comment."""
    token = getattr(pytest, "supplier_token", None)
    assert token
    r = requests.get(f"{API}/supplier/case/{token}")
    assert r.status_code == 200
    assert r.json().get("site_contact_email", "").strip() != ""
