"""Iter 216h117 — MOD bulk-import pipeline regression tests.

Covers the master-admin only `/api/master-admin/mod/bulk-import` endpoint:
  • CSV template downloads with the canonical column set
  • Bulk creates mod_site orgs + their shared kiosk logins under a
    nominated parent (mod_org or mod_branch)
  • Returns plaintext credentials exactly once, then a CSV export
    endpoint streams them within the 10-minute TTL
  • Non master-admins get 403
"""
from __future__ import annotations

import csv
import io
import os

import pytest
import requests

from tests.conftest import _test_backend_url

API = _test_backend_url() + "/api"


_TOK_CACHE: dict = {}


def _master_token() -> str:
    if _TOK_CACHE.get('t'):
        return _TOK_CACHE['t']
    try:
        r = requests.post(
            f"{API}/auth/login",
            json={"email": "admin@gymaxisai.com", "password": "MasterAdmin123!"},
            timeout=10,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        pytest.skip(f"Live API unreachable ({type(e).__name__}) — skipping live-server test")
    r.raise_for_status()
    _TOK_CACHE["t"] = r.json()["token"]
    return _TOK_CACHE["t"]


def _seed_demo(tok: str) -> dict:
    try:
        r = requests.post(
            f"{API}/mod/demo/seed-army-catterick",
            headers={"Authorization": f"Bearer {tok}"},
            timeout=30,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        pytest.skip(f"Live API unreachable ({type(e).__name__}) — skipping live-server test")
    r.raise_for_status()
    return r.json()


def _find_org(account_type: str, name_contains: str) -> dict:
    """Look up an org via the master-admin search API (NOT Mongo) so
    the test works even when CI's local Mongo differs from the API's DB.
    """
    try:
        token = _master_token()
        r = requests.get(
            f"{API}/master-admin/organizations/search",
            params={"q": name_contains, "limit": 50},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.status_code == 200:
            payload = r.json()
            rows = payload.get("organizations") or payload.get("results") or (payload if isinstance(payload, list) else [])
            for row in rows:
                if row.get("account_type") == account_type and name_contains.lower() in (row.get("name") or "").lower():
                    return row
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pytest.skip("Live API unreachable — skipping live-server test")
    except Exception:
        pass

    # Fallback for local dev where Mongo matches the API.
    from pymongo import MongoClient

    client = MongoClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        return db.organizations.find_one(
            {"account_type": account_type, "name": {"$regex": name_contains, "$options": "i"}},
            {"_id": 0},
        )
    finally:
        client.close()


def test_template_download_returns_canonical_headers() -> None:
    tok = _master_token()
    r = requests.get(
        f"{API}/master-admin/mod/bulk-import/template",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    reader = csv.reader(io.StringIO(r.text))
    headers = next(reader)
    for required in ("site_name", "mod_branch", "mod_force", "postcode",
                     "primary_contact_email", "address"):
        assert required in headers, f"Missing column: {required}"


def test_bulk_import_requires_master_admin() -> None:
    """A non master admin must not be able to spin up new MOD orgs."""
    tok_master = _master_token()
    _seed_demo(tok_master)
    parent = _find_org("mod_org", "British Army")
    assert parent

    import uuid as _uuid
    suffix = _uuid.uuid4().hex[:6]
    email = f"bulk-import-noadmin+{suffix}@example.com"
    reg = requests.post(
        f"{API}/auth/register",
        json={
            "email": email, "password": "Test12345!Strong",
            "full_name": "Bulk Test", "company_name": f"Test Org {suffix}",
        },
        timeout=15,
    )
    assert reg.status_code in (200, 201), reg.text
    tok = reg.json()["token"]
    csv_blob = "site_name,mod_branch,mod_force\nFoo,Demo Garrison,army\n"
    files = {"file": ("sites.csv", csv_blob.encode(), "text/csv")}
    r = requests.post(
        f"{API}/master-admin/mod/bulk-import?parent_org_id={parent['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        files=files, timeout=30,
    )
    assert r.status_code == 403


def test_bulk_import_creates_sites_and_returns_credentials(monkeypatch=None) -> None:
    tok = _master_token()
    _seed_demo(tok)
    parent = _find_org("mod_org", "British Army")
    assert parent

    # Two rows — one under Demo Garrison branch, one under a NEW branch ID
    # ("Aldershot Garrison") so we exercise the inherited-from-mod_org path.
    import uuid as _uuid
    suffix = _uuid.uuid4().hex[:6]
    site_a = f"Bulk Test Site A {suffix}"
    site_b = f"Bulk Test Site B {suffix}"
    csv_blob = (
        "site_name,mod_branch,mod_force,postcode,primary_contact_email,address\n"
        f"{site_a},Demo Garrison,army,DL9 9XX,test.a@army.mod.local,1 Test Lane DL9 9XX\n"
        f"{site_b},Aldershot Garrison,army,GU11 0AA,,2 Test Road GU11 0AA\n"
    )
    files = {"file": ("sites.csv", csv_blob.encode(), "text/csv")}
    r = requests.post(
        f"{API}/master-admin/mod/bulk-import?parent_org_id={parent['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        files=files, timeout=60,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 2
    assert len(body["credentials"]) == 2
    creds_by_name = {c["site_name"]: c for c in body["credentials"]}
    assert site_a in creds_by_name and site_b in creds_by_name
    # Plaintext password must be returned exactly once and follow the
    # canonical mint format (alphanumeric + dash + suffix + !).
    for cred in creds_by_name.values():
        assert cred["password"] and cred["password"].endswith("!")
        assert cred["username"]

    # ── Verify orgs exist with correct hierarchy ──
    from pymongo import MongoClient

    client = MongoClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        for name, branch in ((site_a, "Demo Garrison"), (site_b, "Aldershot Garrison")):
            doc = db.organizations.find_one({"name": name}, {"_id": 0})
            assert doc, f"Site not created: {name}"
            assert doc["account_type"] == "mod_site"
            assert doc["mod_root_id"] == parent["id"]
            assert doc["mod_force"] == "army"
            assert doc["mod_branch"] == branch
            assert doc.get("created_via") == "mod_bulk_import"
    finally:
        client.close()

    # ── Sign-in with one of the generated credentials ──
    cred = creds_by_name[site_a]
    login_resp = requests.post(
        f"{API}/auth/login",
        json={"email": cred["username"], "password": cred["password"], "portal": "mod"},
        timeout=15,
    )
    assert login_resp.status_code == 200, login_resp.text
    body_login = login_resp.json()
    assert body_login.get("token"), body_login

    # ── CSV credential export within TTL ──
    exp = requests.get(
        f"{API}/master-admin/mod/bulk-import/export-credentials?import_id={body['import_id']}",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert exp.status_code == 200
    reader = csv.reader(io.StringIO(exp.text))
    rows = list(reader)
    assert rows[0] == ["site_name", "site_code", "username", "password", "branch", "force",
                       "country", "region", "serviced_by", "service_supplier",
                       "contact_email", "notified"]
    # 1 header + 2 data rows
    assert len(rows) == 3


def test_bulk_import_rejects_missing_site_name() -> None:
    tok = _master_token()
    parent = _find_org("mod_org", "British Army")
    csv_blob = "wrong_col\nfoo\n"
    files = {"file": ("bad.csv", csv_blob.encode(), "text/csv")}
    r = requests.post(
        f"{API}/master-admin/mod/bulk-import?parent_org_id={parent['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        files=files, timeout=15,
    )
    assert r.status_code == 400
    assert "site_name" in r.json()["detail"]


def test_bulk_import_inherits_branch_when_parent_is_mod_branch() -> None:
    """When the chosen parent IS a mod_branch, the mod_branch column on
    each row is overridden by the parent's branch — the importer doesn't
    let a single CSV span multiple branches in this mode."""
    tok = _master_token()
    _seed_demo(tok)
    parent = _find_org("mod_branch", "Demo Garrison")
    assert parent

    import uuid as _uuid
    suffix = _uuid.uuid4().hex[:6]
    site_name = f"Branch Inherit {suffix}"
    csv_blob = (
        "site_name,mod_branch,mod_force,postcode,primary_contact_email,address\n"
        # Try to slip a different branch — must be overridden.
        f"{site_name},Other Garrison,army,DL9 1AA,foo@example.com,3 Foo St\n"
    )
    files = {"file": ("sites.csv", csv_blob.encode(), "text/csv")}
    r = requests.post(
        f"{API}/master-admin/mod/bulk-import?parent_org_id={parent['id']}",
        headers={"Authorization": f"Bearer {tok}"},
        files=files, timeout=30,
    )
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1

    from pymongo import MongoClient
    client = MongoClient(os.environ["MONGO_URL"])
    try:
        db = client[os.environ["DB_NAME"]]
        doc = db.organizations.find_one({"name": site_name}, {"_id": 0})
        assert doc
        # Parent's branch wins.
        assert doc["mod_branch"] == "Demo Garrison"
    finally:
        client.close()
