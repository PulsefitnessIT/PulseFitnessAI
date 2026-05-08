"""End-to-end tests for Memberships Phase 3 — class announcements,
operator manual attendance, instructor performance, cover assignment.

Run with:  cd /app/backend && python -m pytest tests/test_memberships_phase3.py -v
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001"
API = f"{BASE_URL.rstrip('/')}/api"

OPERATOR = {
    "email": "lee.somers@pulsefitness.com",
    "password": "TempPass123!",
}


@pytest.fixture(scope="module")
def operator_token() -> str:
    """Single login per test module to dodge auth rate limits."""
    r = requests.post(f"{API}/auth/login", json=OPERATOR, timeout=30)
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def hdr(operator_token: str) -> dict:
    return {"Authorization": f"Bearer {operator_token}"}


# ───────────────────────── Class announcements ─────────────────────────


def test_announce_unauthenticated_blocked(hdr):
    r = requests.post(f"{API}/memberships/occurrences/anything/announce",
                      json={"message": "hi"}, timeout=30)
    assert r.status_code in (401, 403)


def test_announce_unknown_occurrence_404(hdr):
    r = requests.post(
        f"{API}/memberships/occurrences/no-such-occ/announce",
        headers=hdr,
        json={"message": "Studio B tonight!"},
        timeout=30,
    )
    assert r.status_code == 404


def test_announce_empty_message_400(hdr):
    r = requests.post(
        f"{API}/memberships/occurrences/some-occ/announce",
        headers=hdr,
        json={"message": ""},
        timeout=30,
    )
    # Pydantic rejects min_length violation as 422; either 400 or 422 is fine.
    assert r.status_code in (400, 422)


def test_announcements_list_unknown_occ_returns_empty(hdr):
    r = requests.get(
        f"{API}/memberships/occurrences/never-existed/announcements",
        headers=hdr, timeout=30,
    )
    # Either 200 with empty list or 404 — both are acceptable healthy
    # behaviour. We just want auth + no crashes.
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json().get("count") == 0


# ───────────────────────── Manual attendance ─────────────────────────


def test_operator_attendance_unknown_occ_404(hdr):
    r = requests.post(
        f"{API}/memberships/occurrences/no-such-occ/attendance",
        headers=hdr,
        json={"items": [{"booking_id": "x", "status": "attended"}]},
        timeout=30,
    )
    assert r.status_code == 404


def test_operator_attendance_no_items_400(hdr):
    # Create a fake occurrence id won't match — but without items[] we
    # short-circuit to a 400 even before the DB lookup. Use a real occ
    # if available, otherwise the server will 404 — either is healthy.
    r = requests.post(
        f"{API}/memberships/occurrences/anything/attendance",
        headers=hdr, json={}, timeout=30,
    )
    assert r.status_code in (400, 404)


def test_operator_attendance_unauthenticated_blocked(hdr):
    r = requests.post(
        f"{API}/memberships/occurrences/anything/attendance",
        json={"items": []}, timeout=30,
    )
    assert r.status_code in (401, 403)


# ───────────────────────── Instructor performance ─────────────────────────


def test_instructor_performance_returns_window(hdr):
    r = requests.get(
        f"{API}/memberships/instructors/performance?days=30",
        headers=hdr, timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rows" in body
    assert "window_days" in body
    assert body["window_days"] == 30
    # Each row must have the required summary fields
    for row in body["rows"]:
        for key in ("instructor_user_id", "name", "classes_total",
                    "fill_rate_pct", "attendance_rate_pct",
                    "no_show_rate_pct", "pay_due_pence"):
            assert key in row, f"missing {key} in {row}"


def test_instructor_performance_clamps_window(hdr):
    """days < 7 should clamp to 7; days > 365 should clamp to 365."""
    r = requests.get(
        f"{API}/memberships/instructors/performance?days=1",
        headers=hdr, timeout=30,
    )
    assert r.status_code == 200
    assert r.json()["window_days"] == 7
    r = requests.get(
        f"{API}/memberships/instructors/performance?days=9999",
        headers=hdr, timeout=30,
    )
    assert r.status_code == 200
    assert r.json()["window_days"] == 365


def test_instructor_performance_unauthenticated_blocked(hdr):
    r = requests.get(f"{API}/memberships/instructors/performance",
                     timeout=30)
    assert r.status_code in (401, 403)


# ───────────────────────── Cover-request assignment ─────────────────────────


def test_assign_cover_unknown_request_404(hdr):
    r = requests.post(
        f"{API}/memberships/cover-requests/no-such-id/assign",
        headers=hdr,
        json={"instructor_user_id": "someone"},
        timeout=30,
    )
    assert r.status_code == 404


def test_assign_cover_missing_instructor_400(hdr):
    r = requests.post(
        f"{API}/memberships/cover-requests/anything/assign",
        headers=hdr, json={}, timeout=30,
    )
    assert r.status_code == 400


def test_assign_cover_unauthenticated_blocked(hdr):
    r = requests.post(
        f"{API}/memberships/cover-requests/anything/assign",
        json={"instructor_user_id": "x"}, timeout=30,
    )
    assert r.status_code in (401, 403)
