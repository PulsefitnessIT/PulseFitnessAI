"""Iter 220ea·30 - Tester cohort recruitment, spec sheet editable, social library engineer_recruit."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://platform-doctor.preview.emergentagent.com').rstrip('/')
ADMIN_EMAIL = "admin@gymaxisai.com"
ADMIN_PASSWORD = "MasterAdmin123!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---- Public recruitment status (no auth) ----
def test_recruitment_status_public():
    r = requests.get(f"{BASE_URL}/api/partners/recruitment/status", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("total_spaces") == 10
    assert data.get("trial_days") == 10
    assert "taken" in data and "remaining" in data and "open" in data
    assert isinstance(data["taken"], int)
    assert isinstance(data["remaining"], int)
    assert data["remaining"] == max(0, 10 - data["taken"])


# ---- Public apply with cohort=tester ----
def test_public_apply_tester_cohort_and_approval(admin_headers):
    unique = int(time.time())
    email = f"tester.applicant+{unique}@example.com"
    files = {
        "full_name": (None, "Tester Applicant"),
        "email": (None, email),
        "phone": (None, "+447700900111"),
        "city": (None, "London"),
        "country": (None, "United Kingdom"),
        "years_experience": (None, "5"),
        "specialties": (None, "Cardio, Strength"),
        "cohort": (None, "tester"),
        "about": (None, "Tester cohort applicant for QA"),
        "accept_terms": (None, "true"),
        "accepted_terms": (None, "true"),
        "agree_terms": (None, "true"),
        "terms_accepted": (None, "true"),
    }
    r = requests.post(f"{BASE_URL}/api/partners/public-apply", files=files, timeout=30)
    assert r.status_code in (200, 201), f"public-apply failed: {r.status_code} {r.text}"
    body = r.json()
    app_id = body.get("application_id") or body.get("id") or (body.get("application") or {}).get("id")
    assert app_id, f"no application_id in response: {body}"

    # Fetch via master-admin to verify tester_cohort flag
    r = requests.get(f"{BASE_URL}/api/partners/applications", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    apps = r.json() if isinstance(r.json(), list) else r.json().get("applications", [])
    match = next((a for a in apps if a.get("id") == app_id or a.get("email") == email), None)
    assert match, f"Application {app_id} not found in master-admin list"
    assert match.get("tester_cohort") is True, f"tester_cohort not True: {match}"

    # Approve
    r = requests.post(f"{BASE_URL}/api/partners/applications/{app_id}/approve",
                      headers=admin_headers, json={}, timeout=30)
    assert r.status_code in (200, 201), f"approve failed: {r.status_code} {r.text}"
    approve_body = r.json()
    partner_id = (approve_body.get("partner") or {}).get("id") or approve_body.get("partner_id")

    # Verify partner via master-admin list
    r = requests.get(f"{BASE_URL}/api/master-admin/partners", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    partners = r.json() if isinstance(r.json(), list) else r.json().get("partners", [])
    p = None
    if partner_id:
        p = next((x for x in partners if x.get("id") == partner_id), None)
    if not p:
        p = next((x for x in partners if x.get("email") == email), None)
    assert p, f"approved partner not found (email={email})"
    assert p.get("tester_cohort") is True, f"tester_cohort not propagated to partner: {p}"
    assert p.get("trial_ends_at"), f"trial_ends_at missing: {p}"
    sub = p.get("subscription") or {}
    assert sub.get("status") == "trialing", f"subscription.status not trialing: {sub}"
    assert sub.get("current_period_end"), f"current_period_end missing: {sub}"


# ---- Spec sheet edit ----
def test_spec_sheet_edit_and_restore(admin_headers):
    r = requests.get(f"{BASE_URL}/api/spec-sheets/list", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body if isinstance(body, list) else body.get("spec_sheets") or body.get("items") or []
    assert items, "no spec sheets found"
    spec = items[0]
    spec_id = spec.get("id") or spec.get("_id") or spec.get("spec_id")
    original = spec.get("equipment_model") or spec.get("model") or ""
    assert spec_id, f"missing spec id: {spec}"

    new_model = (original or "Model") + " EDITTEST"
    r = requests.patch(f"{BASE_URL}/api/spec-sheets/{spec_id}",
                       headers=admin_headers,
                       json={"equipment_model": new_model}, timeout=20)
    assert r.status_code == 200, f"PATCH failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("success") is True
    ss = data.get("spec_sheet") or {}
    assert ss.get("equipment_model") == new_model
    assert "rematched_count" in data
    assert isinstance(data["rematched_count"], int)

    # Restore
    r = requests.patch(f"{BASE_URL}/api/spec-sheets/{spec_id}",
                       headers=admin_headers,
                       json={"equipment_model": original}, timeout=20)
    assert r.status_code == 200, f"restore failed: {r.status_code} {r.text}"


# ---- Social Media Library engineer_recruit campaign ----
def test_social_media_library_engineer_recruit(admin_headers):
    # Iter 230 — deletions are intentionally sticky (seed marker), so we
    # no longer pin the LIVE row count (an admin may legitimately prune
    # posts). Instead: the seed catalogue must still ship the full 7-post
    # campaign, and whatever survives in the DB must keep its shape.
    from routes.social_media_library import ENGINEER_RECRUIT_ROWS
    assert len(ENGINEER_RECRUIT_ROWS) >= 7, (
        f"seed catalogue must ship >=7 engineer_recruit posts, got {len(ENGINEER_RECRUIT_ROWS)}"
    )
    seed_orders = sorted(r_.get("post_order") for r_ in ENGINEER_RECRUIT_ROWS[:7])
    assert seed_orders == [1, 2, 3, 4, 5, 6, 7], f"seed post_order not 1..7: {seed_orders}"

    r = requests.get(f"{BASE_URL}/api/master-admin/social-media-library",
                     headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    rows = body if isinstance(body, list) else body.get("posts") or body.get("items") or body.get("rows") or []
    recruit = [r_ for r_ in rows if r_.get("campaign") == "engineer_recruit"]
    assert recruit, "engineer_recruit campaign missing from the live library"
    for r_ in recruit:
        if r_.get("post_order") in range(1, 8):
            assert r_.get("channel") == "all", f"channel not 'all': {r_}"
            assert "/marketing/engineer_recruit/post_0" in (r_.get("image_url") or ""), r_
            assert r_.get("caption"), f"empty caption: {r_}"
            assert r_.get("hashtags"), f"empty hashtags: {r_}"


# ---- Static poster files ----
def test_poster_images_served():
    for i in range(1, 8):
        url = f"{BASE_URL}/marketing/engineer_recruit/post_0{i}.png"
        r = requests.get(url, timeout=20)
        assert r.status_code == 200, f"poster {i} not served: {r.status_code} {url}"
        ct = r.headers.get("content-type", "")
        assert "image" in ct.lower(), f"poster {i} wrong content-type: {ct}"
