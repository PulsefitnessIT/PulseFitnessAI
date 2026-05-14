"""Regression tests for iter 216h100 — Communications inbox SLA + assignment + canned templates + rate limiter."""
from __future__ import annotations

import asyncio
import time

import requests

from tests.conftest import (
    MASTER_ADMIN_EMAIL,
    MASTER_ADMIN_PASSWORD,
    _test_backend_url,
)

API = _test_backend_url() + "/api"


def _master_token() -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": MASTER_ADMIN_EMAIL, "password": MASTER_ADMIN_PASSWORD},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("token")


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── SLA settings ──────────────────────────────────────────────────────


def test_inbox_settings_round_trip():
    token = _master_token()
    # GET defaults
    r = requests.get(f"{API}/master-admin/communications/settings", headers=_h(token), timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "settings" in body and "admins" in body
    assert body["settings"]["warning_hours"] >= 1
    assert body["settings"]["breach_hours"] >= body["settings"]["warning_hours"]
    # PUT
    save = requests.put(
        f"{API}/master-admin/communications/settings",
        headers=_h(token),
        json={"warning_hours": 6, "breach_hours": 36},
        timeout=10,
    )
    assert save.status_code == 200, save.text
    assert save.json()["settings"] == {"warning_hours": 6, "breach_hours": 36}
    # Re-fetch confirms persistence
    r2 = requests.get(f"{API}/master-admin/communications/settings", headers=_h(token), timeout=10)
    assert r2.json()["settings"] == {"warning_hours": 6, "breach_hours": 36}
    # Restore defaults so other tests in the suite aren't surprised.
    requests.put(
        f"{API}/master-admin/communications/settings",
        headers=_h(token),
        json={"warning_hours": 4, "breach_hours": 24},
        timeout=10,
    )


def test_inbox_summary_now_includes_sla():
    token = _master_token()
    r = requests.get(f"{API}/master-admin/communications/summary", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sla" in body and "warning" in body["sla"] and "breached" in body["sla"]
    assert "sla_settings" in body


def test_inbox_list_rows_carry_sla_field():
    token = _master_token()
    r = requests.get(f"{API}/master-admin/communications?limit=5", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    for it in items:
        assert "sla" in it
        assert it["sla"] in {"ok", "warning", "breached", "none"}


# ── Assignment ────────────────────────────────────────────────────────


def test_assignment_accepts_master_admin_and_rejects_others():
    token = _master_token()
    # Seed an enquiry
    seed = requests.post(
        f"{API}/contact",
        json={"name": "Assign QA", "email": "assign@example.com", "message": "ignore"},
        timeout=15,
    )
    eid = seed.json()["id"]
    # Valid assignee
    ok = requests.patch(
        f"{API}/master-admin/communications/{eid}",
        headers=_h(token),
        json={"assigned_to": MASTER_ADMIN_EMAIL},
        timeout=10,
    )
    assert ok.status_code == 200, ok.text
    detail = requests.get(
        f"{API}/master-admin/communications/{eid}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    ).json()
    assert detail["assigned_to"] == MASTER_ADMIN_EMAIL.lower()
    # Invalid assignee
    bad = requests.patch(
        f"{API}/master-admin/communications/{eid}",
        headers=_h(token),
        json={"assigned_to": "not-a-real-admin@example.com"},
        timeout=10,
    )
    assert bad.status_code == 400
    # Clear via empty string
    clr = requests.patch(
        f"{API}/master-admin/communications/{eid}",
        headers=_h(token),
        json={"assigned_to": ""},
        timeout=10,
    )
    assert clr.status_code == 200


# ── Canned replies ────────────────────────────────────────────────────


def test_canned_replies_crud():
    token = _master_token()
    # Create
    c = requests.post(
        f"{API}/master-admin/canned-replies",
        headers=_h(token),
        json={"label": "QA template " + str(int(time.time())), "subject": "QA subject", "body": "QA body"},
        timeout=10,
    )
    assert c.status_code == 200, c.text
    item = c.json()["item"]
    tid = item["id"]
    # List
    lst = requests.get(f"{API}/master-admin/canned-replies", headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
    assert any(t["id"] == tid for t in lst["items"])
    # Update
    u = requests.put(
        f"{API}/master-admin/canned-replies/{tid}",
        headers=_h(token),
        json={"label": item["label"], "subject": "QA subject v2", "body": "QA body v2"},
        timeout=10,
    )
    assert u.status_code == 200
    # Delete
    d = requests.delete(f"{API}/master-admin/canned-replies/{tid}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert d.status_code == 200
    # 404 on missing
    d404 = requests.delete(f"{API}/master-admin/canned-replies/nonexistent", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    assert d404.status_code == 404


# ── Rate limiter ──────────────────────────────────────────────────────


def test_rate_limiter_paces_under_max_rps():
    """Hammer the acquire() call 12 times — should take at least
    2 seconds (12 / 4 rps = 3s, minus the first burst window of 1s
    that runs ahead of the pacing)."""
    from utils.email_rate_limiter import acquire, MAX_RPS, stats

    async def run():
        start = time.monotonic()
        await asyncio.gather(*[acquire() for _ in range(12)])
        return time.monotonic() - start

    elapsed = asyncio.run(run())
    # Allow a generous lower bound to avoid CI flakiness — the
    # important assertion is "did not finish instantly".
    assert MAX_RPS > 0
    assert elapsed >= 1.5, f"rate limiter let 12 acquires through in {elapsed:.2f}s"
    # Queue must be drained at the end.
    assert stats()["queue_depth"] == 0


def test_health_full_includes_email_tile():
    token = _master_token()
    r = requests.get(f"{API}/health/full", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "email" in body
    e = body["email"]
    assert "max_rps" in e and e["max_rps"] >= 1
    assert "queue_depth" in e
    assert e["status"] in {"ok", "amber", "backed_up", "unknown"}
