"""Iter 216h163 — Self-service per-site data export endpoints."""
import io
import json
import os
import uuid
import zipfile
from datetime import datetime, timezone

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://service-ops-hub-6.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email: str, pwd: str) -> dict:
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


# ── Admin owner session (has owner/manager rights via master_admin) ──

@pytest.fixture
def admin():
    return _login("admin@gymaxisai.com", "MasterAdmin123!")


@pytest.fixture
def engineer():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


# ── Sites list ───────────────────────────────────────────────────

def test_sites_endpoint_returns_list_shape(engineer):
    tok = engineer["token"]
    r = requests.get(f"{API}/api/account/data-export/sites",
                     headers=_hdr(tok), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sites" in body and "count" in body
    assert isinstance(body["sites"], list)
    assert body["count"] == len(body["sites"])
    # Each entry has the canonical fields.
    for s in body["sites"]:
        assert {"id", "name", "org_id", "kind"}.issubset(s.keys())
        assert s["kind"] in ("internal", "mod_child")


def test_sites_endpoint_rejects_no_auth():
    """Unauthenticated request must be blocked."""
    r = requests.get(f"{API}/api/account/data-export/sites", timeout=20)
    assert r.status_code in (401, 403), r.text


# ── JSON export shape ────────────────────────────────────────────

def test_json_export_includes_site_and_counts(engineer):
    tok = engineer["token"]
    sites = requests.get(f"{API}/api/account/data-export/sites",
                         headers=_hdr(tok), timeout=20).json()["sites"]
    if not sites:
        pytest.skip("No sites in this org to export")
    target = sites[0]
    r = requests.get(
        f"{API}/api/account/data-export/site/{target['id']}.json",
        headers=_hdr(tok), timeout=30,
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["site"]["id"] == target["id"]
    assert payload["site"]["kind"] == target["kind"]
    assert "counts" in payload
    for k in ("equipment", "issues", "svc_cases", "svc_quotes",
              "svc_invoices", "audit_logs"):
        assert k in payload["counts"]
        assert isinstance(payload["counts"][k], int)
        assert isinstance(payload[k], list)
    assert payload["exported_by"]["email"] == engineer["user"]["email"]


def test_json_export_rejects_cross_tenant(engineer):
    """Asking for a UUID that doesn't belong to the caller → 403."""
    tok = engineer["token"]
    bogus = str(uuid.uuid4())
    r = requests.get(
        f"{API}/api/account/data-export/site/{bogus}.json",
        headers=_hdr(tok), timeout=20,
    )
    assert r.status_code == 403, r.text


# ── ZIP export structure ─────────────────────────────────────────

def test_zip_export_contains_manifest_and_csvs(engineer):
    tok = engineer["token"]
    sites = requests.get(f"{API}/api/account/data-export/sites",
                         headers=_hdr(tok), timeout=20).json()["sites"]
    if not sites:
        pytest.skip("No sites in this org to export")
    target = sites[0]
    r = requests.get(
        f"{API}/api/account/data-export/site/{target['id']}.zip",
        headers=_hdr(tok), timeout=30,
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/zip")
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert "manifest.json" in names
    assert "full_export.json" in names
    # Manifest must contain the metadata header sections.
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["site"]["id"] == target["id"]
    assert "counts" in manifest
    # Manifest must NOT carry the heavy list collections (those are CSVs).
    assert "equipment" not in manifest
    assert "audit_logs" not in manifest


# ── Audit-trail side-effect ──────────────────────────────────────

def test_export_writes_audit_log(engineer):
    tok = engineer["token"]
    sites = requests.get(f"{API}/api/account/data-export/sites",
                         headers=_hdr(tok), timeout=20).json()["sites"]
    if not sites:
        pytest.skip("No sites in this org to export")
    target = sites[0]
    db = _mongo()
    before = db["audit_logs"].count_documents(
        {"action": "site_data_export", "resource_id": target["id"]},
    )
    r = requests.get(
        f"{API}/api/account/data-export/site/{target['id']}.json",
        headers=_hdr(tok), timeout=30,
    )
    assert r.status_code == 200
    after = db["audit_logs"].count_documents(
        {"action": "site_data_export", "resource_id": target["id"]},
    )
    assert after == before + 1, "site_data_export audit entry missing"
    latest = db["audit_logs"].find_one(
        {"action": "site_data_export", "resource_id": target["id"]},
        sort=[("timestamp", -1)],
    )
    assert latest["user_email"] == engineer["user"]["email"]
    assert "JSON export" in (latest.get("details") or "")
