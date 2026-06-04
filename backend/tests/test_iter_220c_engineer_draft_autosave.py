"""Iter 220c — Engineer job-draft autosave (data-loss prevention).

When an engineer types a Work Summary on the Complete tab and switches
to Parts (or anywhere else), the React component unmounts and the local
state would vanish. The new draft endpoints persist the in-flight work
both client-side (localStorage) and server-side (MongoDB) so nothing is
ever lost on tab switch, reload, or app crash.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import httpx
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://engineer-jobs-live.preview.emergentagent.com",
)

_CACHE: dict[str, str] = {}


def _bypass_headers() -> dict[str, str]:
    secret = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": secret} if secret else {}


def _login(email: str, password: str) -> str:
    key = f"login::{email}"
    if _CACHE.get(key):
        return _CACHE[key]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/auth/login",
            json={"email": email, "password": password},
            headers=_bypass_headers(),
        )
        r.raise_for_status()
    _CACHE[key] = r.json()["token"]
    return _CACHE[key]


def _admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


def _make_case(db, admin) -> str:
    cid = f"draft-iter220c-{uuid.uuid4().hex[:8]}"
    db.svc_cases.insert_one({
        "id": cid,
        "organization_id": admin["organization_id"],
        "reference": "DRAFT-T",
        "title": "Draft autosave test",
        "status": "on_site",
        "assigned_engineer_id": admin["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return cid


def _admin() -> dict:
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    return db.users.find_one({"email": "admin@gymaxisai.com"}, {"_id": 0})


# ─────────────────── Basic round-trip ───────────────────


def test_draft_round_trip_persists_and_returns_typed_summary():
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    admin = _admin()
    case_id = _make_case(db, admin)
    try:
        # GET empty
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                headers=_admin_headers(),
            )
        assert r.status_code == 200
        assert r.json()["draft"] == {}

        # PUT
        with httpx.Client(timeout=15.0) as c:
            r = c.put(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                json={"draft": {
                    "summary": "Testing 123 — replaced belt and rollers",
                    "target": "awaiting_sign_off",
                    "custom_fields": {"drag_factor": 122},
                }},
                headers=_admin_headers(),
            )
        assert r.status_code == 200, r.text
        first_saved_at = r.json()["saved_at"]

        # GET round-trip
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                headers=_admin_headers(),
            )
        body = r.json()
        assert body["draft"]["summary"].startswith("Testing 123")
        assert body["draft"]["target"] == "awaiting_sign_off"
        assert body["draft"]["custom_fields"]["drag_factor"] == 122
        assert body["updated_at"] == first_saved_at
    finally:
        db.svc_engineer_job_drafts.delete_many({"case_id": case_id})
        db.svc_cases.delete_one({"id": case_id})


def test_draft_subsequent_put_overwrites_previous_payload():
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    admin = _admin()
    case_id = _make_case(db, admin)
    try:
        with httpx.Client(timeout=15.0) as c:
            c.put(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                json={"draft": {"summary": "First version"}},
                headers=_admin_headers(),
            )
            c.put(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                json={"draft": {"summary": "Second version", "target": "repaired"}},
                headers=_admin_headers(),
            )
            r = c.get(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                headers=_admin_headers(),
            )
        body = r.json()
        assert body["draft"]["summary"] == "Second version"
        assert body["draft"]["target"] == "repaired"
    finally:
        db.svc_engineer_job_drafts.delete_many({"case_id": case_id})
        db.svc_cases.delete_one({"id": case_id})


# ─────────────────── Delete ───────────────────


def test_draft_delete_clears_storage():
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    admin = _admin()
    case_id = _make_case(db, admin)
    try:
        with httpx.Client(timeout=15.0) as c:
            c.put(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                json={"draft": {"summary": "Will be wiped"}},
                headers=_admin_headers(),
            )
            r = c.delete(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                headers=_admin_headers(),
            )
            assert r.status_code == 200
            r2 = c.get(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                headers=_admin_headers(),
            )
            assert r2.json()["draft"] == {}
    finally:
        db.svc_engineer_job_drafts.delete_many({"case_id": case_id})
        db.svc_cases.delete_one({"id": case_id})


# ─────────────────── Successful complete wipes the draft ───────────────────


def test_complete_clears_draft_after_success():
    """The engineer typed and saved a draft, then completed the job.
    The next time they open the case there should be no stale draft.
    """
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    admin = _admin()
    case_id = _make_case(db, admin)
    try:
        with httpx.Client(timeout=15.0) as c:
            c.put(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                json={"draft": {"summary": "Will be cleared"}},
                headers=_admin_headers(),
            )
            # Complete
            r = c.post(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/complete",
                json={"summary": "All sorted", "target": "repaired"},
                headers=_admin_headers(),
            )
            assert r.status_code == 200, r.text
            # Draft should be gone
            r2 = c.get(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                headers=_admin_headers(),
            )
            assert r2.json()["draft"] == {}
    finally:
        db.svc_engineer_job_drafts.delete_many({"case_id": case_id})
        db.svc_cases.delete_one({"id": case_id})


# ─────────────────── Size cap + auth guards ───────────────────


def test_draft_rejects_payload_larger_than_32_kb():
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    admin = _admin()
    case_id = _make_case(db, admin)
    try:
        oversized = "x" * (33 * 1024)
        with httpx.Client(timeout=15.0) as c:
            r = c.put(
                f"{BASE}/api/svc/engineer/jobs/{case_id}/draft",
                json={"draft": {"summary": oversized}},
                headers=_admin_headers(),
            )
        assert r.status_code == 413
    finally:
        db.svc_engineer_job_drafts.delete_many({"case_id": case_id})
        db.svc_cases.delete_one({"id": case_id})


def test_draft_404_for_unknown_case():
    with httpx.Client(timeout=15.0) as c:
        r = c.put(
            f"{BASE}/api/svc/engineer/jobs/missing-{uuid.uuid4().hex[:8]}/draft",
            json={"draft": {"summary": "x"}},
            headers=_admin_headers(),
        )
    assert r.status_code == 404
