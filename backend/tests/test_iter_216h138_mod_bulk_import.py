"""Iter 216h138 — MOD bulk-import pipeline tests.

Covers:
  • GET  /api/master-admin/mod-sites/template.csv
  • POST /api/master-admin/mod-sites/preview-csv
  • POST /api/master-admin/mod-sites/bulk-import      (idempotent)
  • GET  /api/master-admin/mod-sites/bulk-import/{batch}/credentials.csv

Auth: master admin only.
"""
import base64
import csv
import io
import os
import uuid

import pymongo
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://photo-fix-verify.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _ensure_root():
    """Ensure the demo MOD root exists for the import."""
    db = _mongo()
    if not db["organizations"].find_one({"id": "mod-root-uk"}):
        db["organizations"].insert_one({
            "id": "mod-root-uk", "name": "Ministry of Defence",
            "account_type": "mod_org", "is_mod_root": True,
            "mod_root_id": "mod-root-uk",
            "subscription_tier": "pro",
            "created_at": "2026-01-01T00:00:00+00:00",
        })


def _make_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "site_code", "site_name", "branch", "address_line1", "city",
        "postcode", "country", "password",
    ])
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def _scrub(prefix="bulk-test-"):
    """Remove any prior test sites/users so re-runs are clean."""
    db = _mongo()
    db["organizations"].delete_many({"site_code": {"$regex": f"^{prefix}"}})
    db["users"].delete_many({"username": {"$regex": f"^{prefix}"}})


# ───────────────────────── tests ───────────────────────────


def test_template_download():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    r = requests.get(f"{API}/api/master-admin/mod-sites/template.csv",
                      headers=_hdr(tok), timeout=15)
    assert r.status_code == 200
    assert "site_code" in r.text
    assert "site_name" in r.text
    assert "branch" in r.text
    # The browser-download header is set so the wizard can attribute
    # the file correctly when saved.
    assert "attachment" in (r.headers.get("content-disposition") or "")


def test_preview_csv_validates_and_counts():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    csv_text = _make_csv([
        ["bulk-test-1", "Test Site 1", "Army", "Site 1 Rd", "Aldershot", "GU11 1AA", "United Kingdom", ""],
        ["bulk-test-2", "Test Site 2", "RAF",  "Site 2 Rd", "Oxford",    "OX1 2BB",  "United Kingdom", ""],
        ["",            "Test Site 3", "",     "",          "",          "",         "",                ""],  # invalid: no branch
    ])
    r = requests.post(f"{API}/api/master-admin/mod-sites/preview-csv",
                       headers=_hdr(tok),
                       files={"file": ("test.csv", csv_text, "text/csv")},
                       timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2  # third row is dropped as invalid
    assert any(e["error"].lower().startswith("missing or invalid branch") for e in body["errors"])
    assert body["would_create"] + body["would_skip"] == 2


def test_bulk_import_creates_sites_and_users():
    _scrub()
    _ensure_root()
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    suffix = uuid.uuid4().hex[:6]
    csv_text = _make_csv([
        [f"bulk-test-{suffix}-a", f"Test Site A {suffix}", "Army", "", "Aldershot", "GU11 1AA", "UK", ""],
        [f"bulk-test-{suffix}-b", f"Test Site B {suffix}", "RAF",  "", "Oxford",    "OX1 2BB",  "UK", "MyPwd!2026"],
    ])
    r = requests.post(f"{API}/api/master-admin/mod-sites/bulk-import?sync=true",
                       headers=_hdr(tok),
                       files={"file": ("test.csv", csv_text, "text/csv")},
                       timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert body["created"] == 2
    assert body["skipped"] == 0
    assert body["batch_id"]
    assert body["credentials_csv_b64"]

    # Validate the credentials CSV has both rows
    creds = base64.b64decode(body["credentials_csv_b64"]).decode("utf-8")
    assert f"bulk-test-{suffix}-a" in creds
    assert f"bulk-test-{suffix}-b" in creds
    # The user-supplied password was respected for site B
    assert "MyPwd!2026" in creds

    # Validate Mongo
    db = _mongo()
    site_a = db["organizations"].find_one({"site_code": f"bulk-test-{suffix}-a"}, {"_id": 0})
    assert site_a is not None
    assert site_a["account_type"] == "mod_site"
    assert site_a["mod_root_id"] == "mod-root-uk"
    assert site_a["mod_branch"] == "Army"
    assert site_a["imported_via"] == "mod_bulk_import_csv"
    assert site_a["import_batch_id"] == body["batch_id"]

    user_a = db["users"].find_one({"username": f"bulk-test-{suffix}-a"}, {"_id": 0})
    assert user_a is not None
    assert user_a["organization_id"] == site_a["id"]
    assert user_a["account_type"] == "mod_site"
    # Password is bcrypt'd at rest, NEVER plaintext
    assert user_a["password"].startswith("$2")  # bcrypt prefix
    assert "MyPwd!2026" not in user_a["password"]


def test_bulk_import_is_idempotent_on_site_code():
    _scrub()
    _ensure_root()
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    suffix = uuid.uuid4().hex[:6]
    csv_text = _make_csv([
        [f"bulk-test-idem-{suffix}", f"Idem Site {suffix}", "Army", "", "Aldershot", "GU11 9ZZ", "UK", ""],
    ])
    files = {"file": ("test.csv", csv_text, "text/csv")}
    r1 = requests.post(f"{API}/api/master-admin/mod-sites/bulk-import?sync=true",
                        headers=_hdr(tok), files=files, timeout=30)
    assert r1.status_code == 200
    assert r1.json()["created"] == 1
    # Run again — must NOT create a duplicate
    files = {"file": ("test.csv", csv_text, "text/csv")}
    r2 = requests.post(f"{API}/api/master-admin/mod-sites/bulk-import?sync=true",
                        headers=_hdr(tok), files=files, timeout=30)
    assert r2.status_code == 200, r2.text
    assert r2.json()["created"] == 0
    assert r2.json()["skipped"] == 1


def test_bulk_import_rejects_missing_root():
    _ensure_root()  # ensure mod-root-uk exists separately
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    suffix = uuid.uuid4().hex[:6]
    csv_text = _make_csv([
        [f"bad-root-{suffix}", f"Bad Root {suffix}", "Army", "", "Aldershot", "GU11 9XX", "UK", ""],
    ])
    r = requests.post(
        f"{API}/api/master-admin/mod-sites/bulk-import"
         "?mod_root_id=mod-does-not-exist&sync=true",
        headers=_hdr(tok),
        files={"file": ("test.csv", csv_text, "text/csv")}, timeout=15,
    )
    assert r.status_code == 400, r.text
    assert "not found" in r.text.lower()


def test_async_bulk_import_returns_running_then_done():
    """The default async flow returns `status=running` immediately and
    transitions to `done` once the BackgroundTask completes. This is
    the path the UI uses for 1000-row CSVs."""
    _scrub()
    _ensure_root()
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    import time as _t
    suffix = uuid.uuid4().hex[:6]
    csv_text = _make_csv([
        [f"async-{suffix}-{i}", f"Async Site {i}", "Army", "", "Test", "AB1 2CD", "UK", ""]
        for i in range(5)
    ])
    r = requests.post(f"{API}/api/master-admin/mod-sites/bulk-import",
                       headers=_hdr(tok),
                       files={"file": ("test.csv", csv_text, "text/csv")},
                       timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "running"
    bid = body["batch_id"]
    # Poll until done (≤30 s)
    final = None
    for _ in range(30):
        s = requests.get(f"{API}/api/master-admin/mod-sites/bulk-import/{bid}/status",
                          headers=_hdr(tok), timeout=10).json()
        if s["status"] == "done":
            final = s
            break
        _t.sleep(1)
    assert final is not None, "Background task did not finish in 30s"
    assert final["created"] == 5
    assert final["skipped"] == 0
    assert final["credentials_csv_b64"]


def test_credentials_download_round_trip():
    _scrub()
    _ensure_root()
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    suffix = uuid.uuid4().hex[:6]
    csv_text = _make_csv([
        [f"creds-{suffix}", f"Creds Site {suffix}", "Navy", "", "Portsmouth", "PO1 1AA", "UK", ""],
    ])
    r = requests.post(f"{API}/api/master-admin/mod-sites/bulk-import?sync=true",
                       headers=_hdr(tok),
                       files={"file": ("test.csv", csv_text, "text/csv")},
                       timeout=30)
    body = r.json()
    bid = body["batch_id"]
    g = requests.get(
        f"{API}/api/master-admin/mod-sites/bulk-import/{bid}/credentials.csv",
        headers=_hdr(tok), timeout=15,
    )
    assert g.status_code == 200
    assert f"creds-{suffix}" in g.text


def test_endpoints_require_master_admin():
    r = requests.get(f"{API}/api/master-admin/mod-sites/template.csv", timeout=10)
    assert r.status_code in (401, 403)
    r2 = requests.post(f"{API}/api/master-admin/mod-sites/preview-csv",
                        files={"file": ("x.csv", "site_name\nx", "text/csv")},
                        timeout=10)
    assert r2.status_code in (401, 403)
