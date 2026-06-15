"""Iter 216h142 — Engineer Notifications + Web Push tests.

Covers:
  • notification list + unread-count
  • mark-read (single + read-all) + delete
  • Web Push: VAPID key endpoint + subscribe persists
  • End-to-end: assigning a case via /svc/admin/diary auto-creates a
    job_assigned notification for the assigned engineer.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pymongo
import pytest
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://staffing-ops-preview.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def sess():
    return _login("e1.agent@gymaxisai.com", "E1Agent123!")


def _ensure_engineer(db, org_id, user_id, name):
    db["svc_engineers"].update_one(
        {"organization_id": org_id, "id": user_id},
        {"$setOnInsert": {
            "id": user_id, "organization_id": org_id,
            "full_name": name, "email": "", "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )


def _seed_notif(db, org_id, user_id, kind="generic", title="Hi", body="Body"):
    nid = str(uuid.uuid4())
    db["svc_notifications"].insert_one({
        "id": nid, "user_id": user_id, "organization_id": org_id,
        "kind": kind, "title": title, "body": body,
        "link": None, "read_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return nid


def test_unread_count_starts_at_baseline(sess):
    tok = sess["token"]
    r = requests.get(f"{API}/api/svc/engineer/notifications/unread-count",
                     headers=_hdr(tok), timeout=10)
    assert r.status_code == 200
    assert "unread" in r.json()


def test_list_mark_read_and_delete(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    nid = _seed_notif(db, org_id, user_id, kind="test", title="QA")
    try:
        # List
        r = requests.get(f"{API}/api/svc/engineer/notifications",
                         headers=_hdr(tok), timeout=10)
        assert r.status_code == 200
        ids = [n["id"] for n in r.json()["notifications"]]
        assert nid in ids

        # Unread filter
        ru = requests.get(f"{API}/api/svc/engineer/notifications?unread=true",
                          headers=_hdr(tok), timeout=10)
        assert ru.status_code == 200
        assert nid in [n["id"] for n in ru.json()["notifications"]]

        # Mark single read
        rm = requests.post(f"{API}/api/svc/engineer/notifications/{nid}/read",
                           headers=_hdr(tok), timeout=10)
        assert rm.status_code == 200
        doc = db["svc_notifications"].find_one({"id": nid})
        assert doc["read_at"] is not None

        # Delete
        rd = requests.delete(f"{API}/api/svc/engineer/notifications/{nid}",
                             headers=_hdr(tok), timeout=10)
        assert rd.status_code == 200
        assert db["svc_notifications"].find_one({"id": nid}) is None
    finally:
        db["svc_notifications"].delete_one({"id": nid})


def test_read_all_marks_all_unread(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    seeded = [_seed_notif(db, org_id, user_id, title=f"#{i}") for i in range(3)]
    try:
        r = requests.post(f"{API}/api/svc/engineer/notifications/read-all",
                          headers=_hdr(tok), timeout=10)
        assert r.status_code == 200
        for nid in seeded:
            assert db["svc_notifications"].find_one({"id": nid})["read_at"] is not None
    finally:
        for nid in seeded:
            db["svc_notifications"].delete_one({"id": nid})


def test_vapid_key_endpoint(sess):
    tok = sess["token"]
    r = requests.get(f"{API}/api/svc/engineer/push/vapid-key",
                     headers=_hdr(tok), timeout=10)
    assert r.status_code == 200
    pk = r.json().get("public_key") or ""
    assert len(pk) > 40, "VAPID public key should be a base64url ~88 chars"


def test_push_subscribe_persists(sess):
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    fake_endpoint = f"https://fcm.googleapis.com/wp/{uuid.uuid4().hex}"
    sub = {
        "endpoint": fake_endpoint,
        "keys": {"p256dh": "abc", "auth": "xyz"},
    }
    try:
        r = requests.post(
            f"{API}/api/svc/engineer/push/subscribe",
            headers=_hdr(tok),
            json={"subscription": sub, "user_agent": "pytest"},
            timeout=10,
        )
        assert r.status_code == 200
        h = r.json()["endpoint_hash"]
        doc = db["svc_push_subscriptions"].find_one(
            {"id": h, "user_id": user_id, "organization_id": org_id},
        )
        assert doc is not None
        assert doc["subscription"]["endpoint"] == fake_endpoint
        # Unsubscribe
        ru = requests.delete(
            f"{API}/api/svc/engineer/push/subscriptions/{h}",
            headers=_hdr(tok), timeout=10,
        )
        assert ru.status_code == 200
    finally:
        db["svc_push_subscriptions"].delete_many({"id": {"$regex": ".*"}, "user_agent": "pytest"})


def test_diary_assign_fires_notification(sess):
    """Assigning a case via /api/svc/admin/diary/case/{id}/assign
    creates a job_assigned notification for the engineer."""
    tok = sess["token"]
    user_id = sess["user"]["id"]
    org_id = sess["user"]["organization_id"]
    db = _mongo()
    _ensure_engineer(db, org_id, user_id, "QA Eng")
    case_id = str(uuid.uuid4())
    db["svc_cases"].insert_one({
        "id": case_id, "organization_id": org_id,
        "reference": f"TST-{case_id[:4]}", "title": "Notif test job",
        "status": "open", "priority": "P2",
        "site_name": "QA Gym", "scheduled_at": None,
        "assigned_engineer_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        when = (datetime.now(timezone.utc) + timedelta(hours=4)) \
            .replace(microsecond=0).isoformat()
        r = requests.post(
            f"{API}/api/svc/admin/diary/case/{case_id}/assign",
            headers=_hdr(tok),
            json={"engineer_id": user_id, "scheduled_at": when},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        # Wait a tick for the in-process notification create
        notif = db["svc_notifications"].find_one(
            {"user_id": user_id, "source_type": "case", "source_id": case_id,
             "kind": "job_assigned"},
        )
        assert notif is not None, "job_assigned notification not created"
        assert "Notif test job" in notif["title"] or "TST-" in notif["title"]
    finally:
        db["svc_cases"].delete_one({"id": case_id})
        db["svc_notifications"].delete_many({"source_id": case_id})
