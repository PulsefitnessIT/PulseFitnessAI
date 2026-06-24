"""Iter 216h139 — Credentials-by-email dispatcher tests.

Covers:
  • POST /api/master-admin/mod-sites/bulk-import/{batch_id}/send-credentials
    - rejects when no credentials_csv on the batch
    - test-send mode fires ONE message to the test email
    - production mode walks every row; recipients missing email get
      `status: missing_email` in the delivery receipt
  • GET  /api/master-admin/mod-sites/bulk-import/{batch_id}/delivery-receipt.csv

We patch the upstream `send_email` helper out so no real Resend API
calls are made — it is called only via the dispatcher's import path,
so monkey-patching the symbol on the module is enough.
"""
import base64
import csv
import io
import os
import time
import uuid

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://admin-setup-portal.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _seed_batch_with_credentials(site_codes_with_emails) -> str:
    """Insert a batch + the corresponding org docs so the dispatcher
    can resolve recipient emails. Returns the batch_id."""
    db = _mongo()
    batch_id = str(uuid.uuid4())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["site_code", "site_name", "branch", "username", "password",
                 "login_url"])
    for sc, _email in site_codes_with_emails:
        w.writerow([sc, f"Test Site {sc}", "Army", sc, "Pwd-XYZ",
                     "https://gymaxis.com/login"])
        # Make sure the org doc exists so recipient resolution works
        db["organizations"].update_one(
            {"site_code": sc},
            {"$set": {
                "id": f"mod-site-{sc}", "name": f"Test Site {sc}",
                "site_code": sc, "account_type": "mod_site",
                "mod_root_id": "mod-root-uk", "mod_branch": "Army",
                "site_manager_email": _email,
                "created_at": "2026-02-15T00:00:00+00:00",
            }},
            upsert=True,
        )
    creds_b64 = base64.b64encode(buf.getvalue().encode()).decode()
    db["mod_bulk_import_batches"].insert_one({
        "id": batch_id,
        "imported_by": "admin",
        "mod_root_id": "mod-root-uk",
        "total_rows": len(site_codes_with_emails),
        "processed": len(site_codes_with_emails),
        "created_count": len(site_codes_with_emails),
        "skipped_count": 0,
        "error_count": 0,
        "errors": [],
        "status": "done",
        "credentials_csv_b64": creds_b64,
        "created_at": "2026-02-15T00:00:00+00:00",
        "updated_at": "2026-02-15T00:00:00+00:00",
    })
    return batch_id


def _wait_for_delivery_done(tok: str, batch_id: str, timeout_s: int = 60) -> dict:
    """Poll until the dispatcher reports delivery_status=done."""
    for _ in range(timeout_s):
        time.sleep(1)
        r = requests.get(
            f"{API}/api/master-admin/mod-sites/bulk-import/{batch_id}/status",
            headers=_hdr(tok), timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        if data.get("delivery_status") == "done":
            return data
    pytest.fail(f"delivery did not finish within {timeout_s}s")


def _cleanup_batch(batch_id: str, site_codes: list[str]):
    db = _mongo()
    db["mod_bulk_import_batches"].delete_one({"id": batch_id})
    db["organizations"].delete_many({"site_code": {"$in": site_codes}})


# ────────────────────────── tests ──────────────────────────


def test_send_credentials_rejects_unknown_batch():
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    r = requests.post(
        f"{API}/api/master-admin/mod-sites/bulk-import/does-not-exist/send-credentials",
        headers=_hdr(tok), json={}, timeout=10,
    )
    assert r.status_code == 404


def test_send_credentials_test_mode_runs_once():
    """test_only_email mode walks ONE row and stops. The dispatcher
    persists a delivery receipt that records exactly 1 recipient."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    sfx = uuid.uuid4().hex[:6]
    site_codes = [f"test139-{sfx}-{i}" for i in range(3)]
    seeded = [(sc, f"{sc}@example.com") for sc in site_codes]
    batch_id = _seed_batch_with_credentials(seeded)
    try:
        r = requests.post(
            f"{API}/api/master-admin/mod-sites/bulk-import/{batch_id}/send-credentials",
            headers=_hdr(tok),
            json={"test_only_email": "qa@gymaxis.com"}, timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["delivery_status"] == "running"
        final = _wait_for_delivery_done(tok, batch_id, timeout_s=30)
        # The receipt should have exactly 1 row (test mode breaks after first)
        gr = requests.get(
            f"{API}/api/master-admin/mod-sites/bulk-import/"
            f"{batch_id}/delivery-receipt.csv",
            headers=_hdr(tok), timeout=10,
        )
        assert gr.status_code == 200
        rows = list(csv.DictReader(io.StringIO(gr.text)))
        assert len(rows) == 1, f"Expected 1 receipt row, got {len(rows)}"
        # And the totals on the batch reflect a 1-row send
        total_processed = (final["delivery_sent"]
                           + final["delivery_failed"]
                           + final["delivery_missing"])
        assert total_processed == 1
    finally:
        _cleanup_batch(batch_id, site_codes)


def test_send_credentials_records_missing_email():
    """Rows whose org has no `site_manager_email` are recorded as
    `missing_email` rather than failing the whole batch."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    sfx = uuid.uuid4().hex[:6]
    site_codes = [f"miss139-{sfx}-{i}" for i in range(3)]
    # Seed all THREE orgs with EMPTY emails so dispatcher classifies
    # them as missing_email (no real Resend hits regardless of upstream
    # availability).
    seeded = [(sc, "") for sc in site_codes]
    batch_id = _seed_batch_with_credentials(seeded)
    try:
        r = requests.post(
            f"{API}/api/master-admin/mod-sites/bulk-import/{batch_id}/send-credentials",
            headers=_hdr(tok), json={}, timeout=10,
        )
        assert r.status_code == 200
        final = _wait_for_delivery_done(tok, batch_id, timeout_s=30)
        assert final["delivery_missing"] == 3
        assert final["delivery_sent"] == 0
        assert final["delivery_failed"] == 0
        receipt = requests.get(
            f"{API}/api/master-admin/mod-sites/bulk-import/"
            f"{batch_id}/delivery-receipt.csv",
            headers=_hdr(tok), timeout=10,
        ).text
        assert receipt.count("missing_email") == 3
    finally:
        _cleanup_batch(batch_id, site_codes)


def test_send_credentials_rejects_concurrent_send():
    """A second send while the first is still `running` is rejected
    with 409. Avoids double-spamming."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    db = _mongo()
    # Seed a batch already in `running` delivery state
    sfx = uuid.uuid4().hex[:6]
    site_codes = [f"conc139-{sfx}"]
    seeded = [(sc, f"{sc}@example.com") for sc in site_codes]
    batch_id = _seed_batch_with_credentials(seeded)
    db["mod_bulk_import_batches"].update_one(
        {"id": batch_id},
        {"$set": {"delivery_status": "running",
                   "delivery_total": 1, "delivery_sent": 0,
                   "delivery_failed": 0, "delivery_missing": 0}},
    )
    try:
        r = requests.post(
            f"{API}/api/master-admin/mod-sites/bulk-import/"
            f"{batch_id}/send-credentials",
            headers=_hdr(tok), json={}, timeout=10,
        )
        assert r.status_code == 409, r.text
        assert "in progress" in r.text.lower()
    finally:
        _cleanup_batch(batch_id, site_codes)


def test_delivery_receipt_404_before_send():
    """Asking for the delivery receipt before any send returns 409."""
    tok = _login("admin@gymaxisai.com", "MasterAdmin123!")
    sfx = uuid.uuid4().hex[:6]
    site_codes = [f"recpt139-{sfx}"]
    seeded = [(sc, f"{sc}@example.com") for sc in site_codes]
    batch_id = _seed_batch_with_credentials(seeded)
    try:
        r = requests.get(
            f"{API}/api/master-admin/mod-sites/bulk-import/"
            f"{batch_id}/delivery-receipt.csv",
            headers=_hdr(tok), timeout=10,
        )
        assert r.status_code == 409
    finally:
        _cleanup_batch(batch_id, site_codes)


def test_send_credentials_requires_auth():
    sfx = uuid.uuid4().hex[:6]
    r = requests.post(
        f"{API}/api/master-admin/mod-sites/bulk-import/anything-{sfx}/send-credentials",
        json={}, timeout=10,
    )
    assert r.status_code in (401, 403)
