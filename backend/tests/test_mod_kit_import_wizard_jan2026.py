"""Backend regression for the CRM MOD-site → AI Kit Import wizard (Jan 2026).

Covers:
  1. Master admin can create a MOD site (POST /master-admin/mod-estate/sites)
  2. Upload a small CSV containing a `mod_code` column to /ai-kit-import/analyse
  3. Commit the parsed rows via /ai-kit-import/commit
  4. Verify the equipment persisted under that site carry `mod_code`
  5. Cleanup (organizations, users, equipment) — the site name is prefixed with
     "QA " so it is easy to find and prune.
"""

import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@pulsefitness.com"
ADMIN_PASSWORD = "C2s9yJ3YAhydB4d34-Bykg"


@pytest.fixture(scope="module")
def token():
    assert BASE_URL, "REACT_APP_BACKEND_URL missing"
    # Auth endpoint rate-limits after ~4 rapid logins — one login for the module.
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in response: {r.text[:200]}"
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def site(headers):
    # Guarantee-unique QA site name
    unique = f"QA Import Wizard {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{BASE_URL}/api/master-admin/mod-estate/sites",
                      json={"site_name": unique, "force": "raf",
                            "country": "United Kingdom"},
                      headers=headers, timeout=30)
    assert r.status_code in (200, 201), f"site create failed: {r.status_code} {r.text}"
    data = r.json()
    site_obj = data.get("site") or data
    site_id = site_obj.get("id")
    assert site_id, f"no site id: {data}"
    yield {"id": site_id, "name": unique}

    # ---- teardown: delete site and its equipment ----
    try:
        requests.delete(f"{BASE_URL}/api/master-admin/mod-estate/sites/{site_id}",
                        headers=headers, timeout=30)
    except Exception:
        pass


def test_equipment_template_csv_downloads(headers):
    r = requests.get(f"{BASE_URL}/api/master-admin/mod-estate/equipment-template.csv",
                     headers=headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert "name" in r.text.lower()


def test_analyse_and_commit_with_mod_code(headers, site):
    csv_bytes = (
        "name,equipment_type,manufacturer,mod_code\n"
        "QA Treadmill 1,cardio,Life Fitness,MOD-Tread\n"
        "QA Bench 1,strength,Rogue,MOD-Bench\n"
        "QA Bike 1,cardio,Wattbike,MOD-Bike\n"
    ).encode("utf-8")

    files = {"file": ("qa-kit.csv", io.BytesIO(csv_bytes), "text/csv")}
    r = requests.post(
        f"{BASE_URL}/api/master-admin/mod-estate/ai-kit-import/analyse",
        params={"site_id": site["id"]},
        files=files, headers=headers, timeout=60)
    assert r.status_code == 200, f"analyse failed: {r.status_code} {r.text[:400]}"
    preview = r.json()
    sheets = preview.get("sheets") or []
    assert sheets, f"no sheets in preview: {preview}"

    # Collect all non-summary rows and verify mod_code was recognised
    all_rows = []
    for sh in sheets:
        if sh.get("is_summary"):
            continue
        all_rows.extend(sh.get("rows") or [])
    assert len(all_rows) >= 3, f"expected >=3 rows, got {len(all_rows)}"
    mod_codes = [r.get("mod_code") for r in all_rows if r.get("mod_code")]
    assert any(c == "MOD-Tread" for c in mod_codes), \
        f"mod_code not recognised in preview: rows={all_rows}"

    # Commit — supply the parsed rows back
    r2 = requests.post(
        f"{BASE_URL}/api/master-admin/mod-estate/ai-kit-import/commit",
        json={"site_id": site["id"], "rows": all_rows,
              "skip_duplicates": True},
        headers=headers, timeout=60)
    assert r2.status_code == 200, f"commit failed: {r2.status_code} {r2.text[:400]}"
    result = r2.json()
    assert result.get("imported", 0) >= 3, f"commit imported < 3: {result}"

    # ---- Verify persistence via the master-admin by-category drill-down ----
    time.sleep(1)
    codes_on_site = set()
    for cat in ("cardio", "strength"):
        rr = requests.get(
            f"{BASE_URL}/api/master-admin/mod-estate/site/{site['id']}/equipment-by-category",
            params={"category": cat}, headers=headers, timeout=30)
        assert rr.status_code == 200, f"by-category({cat}) failed: {rr.status_code} {rr.text[:300]}"
        for it in rr.json().get("items") or []:
            if it.get("mod_code"):
                codes_on_site.add(it["mod_code"])
    assert "MOD-Tread" in codes_on_site and "MOD-Bench" in codes_on_site, \
        f"mod_code not persisted on site equipment; codes={codes_on_site}"
