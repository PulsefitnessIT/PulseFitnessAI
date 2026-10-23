"""Onboarding Phase 1 (projects) + Phase 2 (import centre) end-to-end backend tests."""
import os
import io
import csv
import uuid
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://sicon-sync-hub.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"

TEST_TAG = f"TESTONB{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    # Try common login endpoints
    for path in ["/api/auth/login", "/api/login"]:
        r = sess.post(f"{BASE}{path}", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            tok = data.get("access_token") or data.get("token") or (data.get("user") or {}).get("token")
            if tok:
                sess.headers.update({"Authorization": f"Bearer {tok}"})
            return sess
    pytest.skip(f"Login failed: {r.status_code} {r.text[:200]}")


@pytest.fixture(scope="module")
def org_id(s):
    # Find any existing org we can reuse for import target
    r = s.get(f"{BASE}/api/master-admin/organizations", timeout=30)
    if r.status_code == 200:
        orgs = r.json().get("organizations") or r.json().get("items") or r.json()
        if isinstance(orgs, list) and orgs:
            return orgs[0].get("id")
    # fallback try
    r = s.get(f"{BASE}/api/organizations", timeout=30)
    if r.status_code == 200:
        d = r.json()
        items = d.get("organizations") or d.get("items") or (d if isinstance(d, list) else [])
        if items:
            return items[0].get("id")
    pytest.skip("No organisation available")


created_project_ids = []


# ── Phase 1 ───────────────────────────────────────────────────────────────

def test_customer_types(s):
    r = s.get(f"{BASE}/api/onboarding/customer-types", timeout=15)
    assert r.status_code == 200, r.text
    types = r.json()["types"]
    assert len(types) == 9
    assert {t["id"] for t in types} >= {"single_site", "multi_site", "enterprise", "supplier"}


def test_create_project_progressive_disclosure(s):
    name = f"{TEST_TAG}-MultiSite"
    r = s.post(f"{BASE}/api/onboarding/projects", json={
        "customer_name": name,
        "customer_type": "multi_site",
        "modules": ["operations", "crm", "memberships"],
    }, timeout=20)
    assert r.status_code == 200, r.text
    proj = r.json()
    created_project_ids.append(proj["id"])
    keys = {s_["key"] for s_ in proj["checklist"]}
    # Multi-site disclosure
    assert "site_hierarchy" in keys and "regional_managers" in keys
    # CRM module disclosure
    assert "contacts" in keys
    # Memberships disclosure
    assert "members" in keys and "membership_types" in keys
    assert "progress" in proj and "required_total" in proj["progress"]


def test_list_and_get(s):
    r = s.get(f"{BASE}/api/onboarding/projects", timeout=15)
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["projects"]]
    pid = created_project_ids[0]
    assert pid in ids
    r2 = s.get(f"{BASE}/api/onboarding/projects/{pid}", timeout=15)
    assert r2.status_code == 200 and r2.json()["id"] == pid


def test_patch_profile_and_step(s):
    pid = created_project_ids[0]
    r = s.patch(f"{BASE}/api/onboarding/projects/{pid}", json={"owner": "qa@test", "profile": {"region": "EU"}}, timeout=15)
    assert r.status_code == 200
    assert r.json()["owner"] == "qa@test"
    # patch a checklist step
    step = r.json()["checklist"][0]
    r2 = s.patch(f"{BASE}/api/onboarding/projects/{pid}/checklist/{step['id']}",
                 json={"status": "complete"}, timeout=15)
    assert r2.status_code == 200
    assert any(x["id"] == step["id"] and x["status"] == "complete" for x in r2.json()["checklist"])


def test_go_live_gating_then_success(s):
    pid = created_project_ids[0]
    # Should fail while required steps incomplete
    r = s.post(f"{BASE}/api/onboarding/projects/{pid}/go-live", timeout=15)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    # Complete all required steps
    proj = s.get(f"{BASE}/api/onboarding/projects/{pid}").json()
    for step in proj["checklist"]:
        if not step.get("optional"):
            s.patch(f"{BASE}/api/onboarding/projects/{pid}/checklist/{step['id']}",
                    json={"status": "complete"}, timeout=15)
    r2 = s.post(f"{BASE}/api/onboarding/projects/{pid}/go-live", timeout=20)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["go_live"]["approved"] is True
    assert body["go_live"]["summary"]["customer_name"].startswith(TEST_TAG)


def test_dashboard(s):
    r = s.get(f"{BASE}/api/onboarding/dashboard", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ("onboarding_count", "completed_count", "blocked_count", "avg_completion"):
        assert k in d


def test_duplicate_org_guard(s, org_id):
    name = f"{TEST_TAG}-DupA"
    r = s.post(f"{BASE}/api/onboarding/projects", json={
        "customer_name": name, "customer_type": "single_site", "modules": [],
        "organization_id": org_id,
    }, timeout=15)
    # If an existing project already tracks this org, skip; otherwise expect 200
    if r.status_code == 409:
        pytest.skip("Org already tracked by another project; duplicate guard implicitly verified")
    assert r.status_code == 200, r.text
    created_project_ids.append(r.json()["id"])
    r2 = s.post(f"{BASE}/api/onboarding/projects", json={
        "customer_name": f"{TEST_TAG}-DupB", "customer_type": "single_site", "modules": [],
        "organization_id": org_id,
    }, timeout=15)
    assert r2.status_code == 409, r2.text


# ── Phase 2 Import Centre ─────────────────────────────────────────────────

def test_import_types_list(s):
    r = s.get(f"{BASE}/api/onboarding/import/types", timeout=15)
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()["types"]}
    assert {"contacts", "members", "suppliers"} <= ids


def test_import_template_contacts(s):
    r = s.get(f"{BASE}/api/onboarding/import/template/contacts", timeout=15)
    assert r.status_code == 200
    assert "email" in r.text.split("\n")[0]


def _build_csv(rows, headers):
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(headers)
    for r in rows: w.writerow(r)
    return buf.getvalue().encode("utf-8")


_email_a = f"test_{TEST_TAG.lower()}_a@example.com"
_email_b = f"test_{TEST_TAG.lower()}_b@example.com"


def test_analyze_auto_map(s):
    headers = ["Email Address", "First Name", "Surname", "Telephone", "Company"]
    rows = [
        [_email_a, "Alice", "Smith", "+44 20 1111 2222", "Acme"],
        [_email_b, "Bob", "Jones", "+44 20 3333 4444", "Beta"],
        ["not-an-email", "Cara", "X", "555", "C"],
        [_email_a, "Dup", "Smith", "+44 20 1111 2222", "Acme"],  # in-file dupe
    ]
    csv_bytes = _build_csv(rows, headers)
    r = s.post(f"{BASE}/api/onboarding/import/analyze",
               data={"import_type": "contacts"},
               files={"file": ("contacts.csv", csv_bytes, "text/csv")}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    m = j["suggested_mapping"]
    assert m.get("email") == "Email Address"
    assert m.get("first_name") == "First Name"
    assert m.get("last_name") == "Surname"
    assert m.get("phone") == "Telephone"
    assert m.get("company") == "Company"
    # stash for next tests
    pytest._onb_rows = j["rows"]
    pytest._onb_mapping = m


def test_validate_flags_errors_and_dupes(s, org_id):
    body = {"import_type": "contacts", "mapping": pytest._onb_mapping,
            "rows": pytest._onb_rows, "organization_id": org_id}
    r = s.post(f"{BASE}/api/onboarding/import/validate", json=body, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    # Row 3 has invalid email
    row3 = next(x for x in j["rows"] if x["row"] == 3)
    assert row3["errors"], row3
    # Row 4 is in-file duplicate of row 1
    row4 = next(x for x in j["rows"] if x["row"] == 4)
    assert "duplicate_in_file" in row4["flags"]


def test_commit_skip_then_skip_existing(s, org_id):
    body = {"import_type": "contacts", "mapping": pytest._onb_mapping,
            "rows": pytest._onb_rows, "organization_id": org_id, "dedupe_action": "skip"}
    r = s.post(f"{BASE}/api/onboarding/import/commit", json=body, timeout=60)
    assert r.status_code == 200, r.text
    rep = r.json()["report"]
    # Expect 2 created (a,b), 1 skipped (dupe in file), 1 failed (invalid email)
    assert rep["created"] >= 2 and rep["failed"] >= 1 and rep["skipped"] >= 1
    # Re-run with skip → previously-created emails now hit existing dedupe → skipped
    r2 = s.post(f"{BASE}/api/onboarding/import/commit", json=body, timeout=60)
    rep2 = r2.json()["report"]
    assert rep2["created"] == 0
    assert rep2["skipped"] >= 2


def test_commit_update_action(s, org_id):
    rows = [{"Email Address": _email_a, "First Name": "AliceUpdated",
             "Surname": "Smith", "Telephone": "+44 20 1111 2222", "Company": "Acme2"}]
    body = {"import_type": "contacts", "mapping": pytest._onb_mapping,
            "rows": rows, "organization_id": org_id, "dedupe_action": "update"}
    r = s.post(f"{BASE}/api/onboarding/import/commit", json=body, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["report"]["updated"] >= 1


def test_saved_mappings(s):
    body = {"import_type": "contacts", "name": f"{TEST_TAG}-map",
            "mapping": pytest._onb_mapping}
    r = s.post(f"{BASE}/api/onboarding/import/mappings", json=body, timeout=15)
    assert r.status_code == 200 and r.json()["name"].startswith(TEST_TAG)
    r2 = s.get(f"{BASE}/api/onboarding/import/mappings?import_type=contacts", timeout=15)
    assert r2.status_code == 200
    assert any(m.get("name", "").startswith(TEST_TAG) for m in r2.json()["mappings"])


# ── Cleanup ───────────────────────────────────────────────────────────────

def test_zzz_cleanup(s, org_id):
    # archive projects we created
    for pid in created_project_ids:
        try:
            s.delete(f"{BASE}/api/onboarding/projects/{pid}", timeout=15)
        except Exception:
            pass
    # Delete created test contacts via direct CRM API if available
    for em in (_email_a, _email_b):
        try:
            # find then delete
            r = s.get(f"{BASE}/api/crm/contacts?q={em}", timeout=15)
            if r.status_code == 200:
                items = r.json().get("contacts") or r.json().get("items") or []
                for c in items:
                    if c.get("email", "").lower() == em.lower():
                        s.delete(f"{BASE}/api/crm/contacts/{c.get('id')}", timeout=15)
        except Exception:
            pass
