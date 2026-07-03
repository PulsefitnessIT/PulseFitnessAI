"""Test master-admin org list returns owner_email with fallback (iter Jan 2026)."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for local: read frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

MA_EMAIL = "admin@pulsefitness.com"
MA_PASS = "C2s9yJ3YAhydB4d34-Bykg"


def _login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": MA_EMAIL, "password": MA_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token: {r.text[:300]}"
    return tok


def test_master_admin_orgs_include_owner_email():
    tok = _login()
    r = requests.get(f"{BASE_URL}/api/master-admin/organizations",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=60)
    assert r.status_code == 200, f"list failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    orgs = data if isinstance(data, list) else (
        data.get("organizations") or data.get("items") or data.get("data") or []
    )
    assert isinstance(orgs, list) and len(orgs) > 0, f"no orgs: {str(data)[:400]}"
    # every entry must contain the owner_email field
    for o in orgs:
        assert "owner_email" in o, f"owner_email missing from org: {list(o.keys())[:20]}"
    # iso-demo-org must resolve a non-empty owner_email
    iso = next((o for o in orgs if o.get("id") == "iso-demo-org"
                or o.get("_id") == "iso-demo-org"
                or (o.get("name") or "").lower().startswith("iso demo")), None)
    assert iso, f"iso-demo-org not found. sample names: {[o.get('name') for o in orgs[:10]]}"
    assert iso.get("owner_email"), (
        f"iso-demo-org owner_email empty. org={ {k:iso.get(k) for k in ['id','name','owner_email','admin_email','primary_contact_email']} }"
    )
    print("owner_email for iso-demo-org:", iso.get("owner_email"))
