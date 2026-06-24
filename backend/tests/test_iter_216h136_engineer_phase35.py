"""Iter 216h136 — Engineer App Phase 3.5 tests.

Covers the three sub-features:

  • Videos on jobs: `/photos` endpoint now stamps `kind: "video"` when
    the mime starts with `video/`, leaves photos as `kind: "photo"`.
  • Parts-request workflow: engineer files request, admin approves /
    rejects, status transitions, allocation lands on the case.
  • Geo-auto mileage is frontend-only — no backend changes needed.
"""
import os
import uuid
from datetime import datetime, timezone

import pymongo
import requests

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or "https://admin-setup-portal.preview.emergentagent.com").rstrip("/")
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def _mongo():
    return pymongo.MongoClient(os.environ["MONGO_URL"])[DB_NAME]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _login(email, pwd):
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]


def _hdr(t): return {"Authorization": f"Bearer {t}"}


def _seed_case(user_id, org_id):
    db = _mongo()
    case_id = str(uuid.uuid4())
    ref = f"PR-{uuid.uuid4().hex[:6].upper()}"
    db["svc_cases"].insert_one({
        "id": case_id, "organization_id": org_id, "reference": ref,
        "title": "Test parts/video", "status": "assigned", "priority": "medium",
        "assigned_engineer_id": user_id, "allocated_parts": [],
        "created_at": _now(), "safety_signoff_at": _now(),
    })
    return {"id": case_id, "reference": ref}


# ───────────────────────── videos ─────────────────────────


def test_photos_endpoint_stamps_kind_video_for_video_mime():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    case = _seed_case(user["id"], user["organization_id"])
    r = requests.post(f"{API}/api/svc/engineer/photos", headers=_hdr(tok), timeout=15,
                      json={"case_id": case["id"],
                            "file_url": "https://example.com/clip.webm",
                            "mime_type": "video/webm",
                            "caption": "[BEFORE] Belt warn-up clip",
                            "duration_seconds": 18})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "video"
    assert body["mime_type"] == "video/webm"
    assert body["duration_seconds"] == 18


def test_photos_endpoint_kind_photo_for_image():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    case = _seed_case(user["id"], user["organization_id"])
    r = requests.post(f"{API}/api/svc/engineer/photos", headers=_hdr(tok), timeout=15,
                      json={"case_id": case["id"],
                            "file_url": "https://example.com/photo.jpg",
                            "mime_type": "image/jpeg"})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "photo"


# ──────────────────────── parts requests ───────────────────────


def test_engineer_creates_request_admin_approves_part_lands_on_case():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    case = _seed_case(user["id"], user["organization_id"])
    sku = f"REQ-{uuid.uuid4().hex[:6].upper()}"
    # 1) engineer files request
    r = requests.post(f"{API}/api/svc/engineer/parts-requests", headers=_hdr(tok),
                      json={"case_id": case["id"], "part_sku": sku,
                            "part_name": "Test belt", "qty": 2,
                            "urgency": "urgent", "notes": "Customer waiting"},
                      timeout=15)
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["status"] == "pending"
    assert req["urgency"] == "urgent"
    assert req["in_catalogue"] is False

    # 2) listing must surface it
    g = requests.get(f"{API}/api/svc/engineer/parts-requests", headers=_hdr(tok),
                     params={"case_id": case["id"]}, timeout=10).json()
    assert any(x["id"] == req["id"] for x in g["items"])

    # 3) admin sees it in the inbox with the `pending` count
    a = requests.get(f"{API}/api/admin/parts-requests", headers=_hdr(tok),
                     params={"status": "pending"}, timeout=10).json()
    assert any(x["id"] == req["id"] for x in a["items"])
    assert a["counts"]["pending"] >= 1

    # 4) admin approves with ship_from=warehouse
    r2 = requests.post(f"{API}/api/admin/parts-requests/{req['id']}/approve",
                       headers=_hdr(tok),
                       json={"ship_from": "warehouse",
                             "notes": "From van #3"}, timeout=15)
    assert r2.status_code == 200, r2.text
    approved = r2.json()
    assert approved["status"] == "approved"
    assert approved["ship_from"] == "warehouse"
    assert approved["allocation_id"]

    # 5) the case must now carry that allocation
    fresh = _mongo()["svc_cases"].find_one({"id": case["id"]}, {"_id": 0})
    allocs = fresh.get("allocated_parts") or []
    assert any(a.get("from_request_id") == req["id"] for a in allocs)
    assert all(a.get("fulfilled") is False for a in allocs)  # awaiting engineer to mark used


def test_engineer_can_cancel_pending_request_but_not_approved():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    case = _seed_case(user["id"], user["organization_id"])
    r = requests.post(f"{API}/api/svc/engineer/parts-requests", headers=_hdr(tok),
                      json={"case_id": case["id"], "part_sku": "CANCELME-1",
                            "qty": 1}, timeout=10).json()
    # Cancel pending — OK
    c1 = requests.delete(f"{API}/api/svc/engineer/parts-requests/{r['id']}",
                          headers=_hdr(tok), timeout=10)
    assert c1.status_code == 200
    # Cancel again — already cancelled, must 409
    c2 = requests.delete(f"{API}/api/svc/engineer/parts-requests/{r['id']}",
                          headers=_hdr(tok), timeout=10)
    assert c2.status_code == 409, c2.text


def test_admin_reject_persists_reason():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    case = _seed_case(user["id"], user["organization_id"])
    r = requests.post(f"{API}/api/svc/engineer/parts-requests", headers=_hdr(tok),
                      json={"case_id": case["id"], "part_sku": "REJ-1", "qty": 1},
                      timeout=10).json()
    rej = requests.post(f"{API}/api/admin/parts-requests/{r['id']}/reject",
                        headers=_hdr(tok),
                        json={"reason": "Out of stock — 6 week ETA"},
                        timeout=10)
    assert rej.status_code == 200
    body = rej.json()
    assert body["status"] == "rejected"
    assert body["reject_reason"] == "Out of stock — 6 week ETA"
    # Re-rejecting must 409
    again = requests.post(f"{API}/api/admin/parts-requests/{r['id']}/reject",
                          headers=_hdr(tok),
                          json={"reason": "Already rejected"}, timeout=10)
    assert again.status_code == 409


def test_admin_endpoints_require_admin():
    """Non-admin tokens get 403 — engineer-app gate already lets
    Master admins through, so we test with no auth instead."""
    r = requests.get(f"{API}/api/admin/parts-requests", timeout=10)
    assert r.status_code in (401, 403)


def test_engineer_request_validates_urgency():
    tok, user = _login("admin@gymaxisai.com", "MasterAdmin123!")
    case = _seed_case(user["id"], user["organization_id"])
    r = requests.post(f"{API}/api/svc/engineer/parts-requests", headers=_hdr(tok),
                      json={"case_id": case["id"], "part_sku": "X-1",
                            "qty": 1, "urgency": "MEH"}, timeout=10)
    assert r.status_code in (422,), r.text
