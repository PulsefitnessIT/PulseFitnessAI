"""Iter 220e — Per-machine photos + PDF rendering polish.

Engineers can attach photos to a specific machine row on the Work Visit
Machines card. The Service Report PDF now renders each machine as its
own card with chips (Serviced / Cleaned), notes, and a 2-up photo grid
beneath. Photos already tagged to a machine are excluded from the
global "Additional photos" section to avoid duplication.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from pymongo import MongoClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE = os.environ.get(
    "TEST_BASE_URL",
    "https://mod-only-deploy.preview.emergentagent.com",
)
_CACHE: dict[str, str] = {}


def _bypass() -> dict[str, str]:
    s = os.environ.get("RATE_LIMIT_BYPASS_SECRET")
    return {"X-RateLimit-Bypass": s} if s else {}


def _login(email: str, password: str) -> str:
    if _CACHE.get(email):
        return _CACHE[email]
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, headers=_bypass())
        r.raise_for_status()
    _CACHE[email] = r.json()["token"]
    return _CACHE[email]


def _hdr() -> dict[str, str]:
    return {"Authorization": f"Bearer {_login('admin@gymaxisai.com', 'MasterAdmin123!')}"}


@pytest.fixture
def db():
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture
def admin(db):
    return db.users.find_one({"email": "admin@gymaxisai.com"}, {"_id": 0})


@pytest.fixture
def case(db, admin):
    cid = f"pm220e-{uuid.uuid4().hex[:8]}"
    db.svc_cases.insert_one({
        "id": cid,
        "organization_id": admin["organization_id"],
        "reference": "PM-E",
        "title": "Per-machine photo test",
        "status": "on_site",
        "assigned_engineer_id": admin["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield cid
    db.svc_cases.delete_one({"id": cid})
    db.svc_work_visit_machines.delete_many({"case_id": cid})
    db.svc_engineer_photos.delete_many({"case_id": cid})


def _make_row(case_id: str, name: str = "Erg") -> str:
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/engineer/jobs/{case_id}/machines",
            json={"asset_name": name},
            headers=_hdr(),
        )
    return r.json()["id"]


# ─────────────────── photo tagging round-trip ───────────────────


def test_photo_attached_to_machine_row_returns_in_list(case):
    row_id = _make_row(case, "BikeErg #1")
    with httpx.Client(timeout=15.0) as c:
        rp = c.post(
            f"{BASE}/api/svc/engineer/photos",
            json={
                "case_id": case,
                "machine_row_id": row_id,
                "file_url": "https://example.invalid/photo.jpg",
                "mime_type": "image/jpeg",
                "caption": "Drive belt before",
            },
            headers=_hdr(),
        )
        assert rp.status_code == 200, rp.text
        photo_id = rp.json()["id"]
        # List machines and confirm photo is fanned in.
        lst = c.get(f"{BASE}/api/svc/engineer/jobs/{case}/machines", headers=_hdr())
    machines = lst.json()["machines"]
    assert len(machines) == 1
    photos = machines[0].get("photos") or []
    assert len(photos) == 1
    assert photos[0]["id"] == photo_id
    assert photos[0]["caption"] == "Drive belt before"


def test_photo_machine_row_id_must_exist(case):
    with httpx.Client(timeout=15.0) as c:
        r = c.post(
            f"{BASE}/api/svc/engineer/photos",
            json={
                "case_id": case,
                "machine_row_id": "bogus-row-id",
                "file_url": "https://example.invalid/x.jpg",
                "mime_type": "image/jpeg",
            },
            headers=_hdr(),
        )
    assert r.status_code == 404


def test_photo_without_machine_row_id_still_works(case):
    """Backwards-compat: existing photos workflow (no machine_row_id)
    must still post successfully and NOT appear in any machine's photos
    bucket."""
    row_id = _make_row(case, "Treadmill A")
    with httpx.Client(timeout=15.0) as c:
        rp = c.post(
            f"{BASE}/api/svc/engineer/photos",
            json={
                "case_id": case,
                "file_url": "https://example.invalid/site.jpg",
                "mime_type": "image/jpeg",
                "caption": "Site overview",
            },
            headers=_hdr(),
        )
        assert rp.status_code == 200
        lst = c.get(f"{BASE}/api/svc/engineer/jobs/{case}/machines", headers=_hdr())
    machines = lst.json()["machines"]
    assert machines[0]["id"] == row_id
    assert (machines[0].get("photos") or []) == []


def test_delete_photo_removes_link_from_machine(case):
    row_id = _make_row(case, "RowErg #9")
    with httpx.Client(timeout=15.0) as c:
        rp = c.post(
            f"{BASE}/api/svc/engineer/photos",
            json={
                "case_id": case,
                "machine_row_id": row_id,
                "file_url": "https://example.invalid/p.jpg",
                "mime_type": "image/jpeg",
            },
            headers=_hdr(),
        )
        photo_id = rp.json()["id"]
        dr = c.delete(f"{BASE}/api/svc/engineer/photos/{photo_id}", headers=_hdr())
        assert dr.status_code == 200
        lst = c.get(f"{BASE}/api/svc/engineer/jobs/{case}/machines", headers=_hdr())
    assert (lst.json()["machines"][0].get("photos") or []) == []


def test_delete_photo_404_when_missing():
    with httpx.Client(timeout=15.0) as c:
        r = c.delete(
            f"{BASE}/api/svc/engineer/photos/missing-{uuid.uuid4().hex[:8]}",
            headers=_hdr(),
        )
    assert r.status_code == 404


# ─────────────────── PDF includes machine block + page footer ───────────────────


def test_service_report_pdf_renders_with_per_machine_block(db, admin, case):
    """Build a closed case with one machine + one tagged photo and
    confirm the PDF endpoint returns a real PDF (≥ 2 KB) without
    erroring. The actual visual quality is deferred to the user's eye;
    this is a smoke test that the new card layout doesn't crash on
    unreachable photo URLs."""
    row_id = _make_row(case, "Concept 2 RowErg #14")
    # Tick serviced + add notes + photo (unreachable URL is fine —
    # _fetch_image_bytes returns None and the card just omits the photo).
    with httpx.Client(timeout=20.0) as c:
        c.patch(
            f"{BASE}/api/svc/engineer/jobs/{case}/machines/{row_id}",
            json={"serviced": True, "cleaned": True, "notes": "Belt replaced; flywheel re-lubed"},
            headers=_hdr(),
        )
        c.post(
            f"{BASE}/api/svc/engineer/photos",
            json={
                "case_id": case,
                "machine_row_id": row_id,
                "file_url": "https://invalid.example.test/photo.jpg",
                "mime_type": "image/jpeg",
                "caption": "Before service",
            },
            headers=_hdr(),
        )
        # Need the case to be closed/repaired so the PDF endpoint will
        # render. Mark it via Mongo to dodge the chargeable/full-complete
        # flow which has many side-effects.
        db.svc_cases.update_one(
            {"id": case},
            {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc).isoformat()}},
        )
        r = c.get(f"{BASE}/api/svc/cases/{case}/service-report.pdf", headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert len(r.content) > 2000
    # Valid PDF magic header + EOF marker.
    assert r.content.startswith(b"%PDF-")
    assert r.content.rstrip().endswith(b"%%EOF")
