"""Iter 220ea·35 — Offline-safe engineer quoting + flaky-test fix.

Engineers raise quotes on-site with no signal; the app queues the POST in
the IndexedDB outbox and replays it on reconnect. A stable Idempotency-Key
(reused on every replay) makes `create_quote` idempotent so a lost-response
replay never duplicates the quote.
"""
from __future__ import annotations

import os
import pathlib
import uuid

import requests

from conftest import rate_limit_bypass_headers

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "https://mod-hq-email.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
ADMIN_PW = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
FRONT = pathlib.Path("/app/frontend/src")


def _token() -> str:
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
        headers=rate_limit_bypass_headers(), timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


def _payload(name: str) -> dict:
    return {"customer_name": name, "lines": [{"kind": "labour", "description": "On-site service", "quantity": 1, "unit_price": 120}]}


def test_quote_create_idempotent_on_replay():
    tok = _token()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    key = f"pytest-{uuid.uuid4().hex}"
    name = f"PYTEST_Idem_{uuid.uuid4().hex[:8]}"

    r1 = requests.post(f"{BASE}/api/svc/engineer/quotes", json=_payload(name), headers={**h, "Idempotency-Key": key}, timeout=30)
    assert r1.status_code in (200, 201), r1.text
    q1 = r1.json()
    assert q1.get("idempotency_key") == key

    # Replay the exact same request (simulates outbox re-send after a lost response).
    r2 = requests.post(f"{BASE}/api/svc/engineer/quotes", json=_payload(name), headers={**h, "Idempotency-Key": key}, timeout=30)
    assert r2.status_code in (200, 201)
    q2 = r2.json()
    assert q2["id"] == q1["id"], "replay created a DUPLICATE quote"
    assert q2["quote_number"] == q1["quote_number"]

    # Cleanup the single quote (best-effort — no public delete, so mark it).
    requests.post(f"{BASE}/api/svc/engineer/quotes/{q1['id']}/mark", json={"status": "declined"}, headers=h, timeout=30)


def test_quote_create_without_key_is_unique():
    tok = _token()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    name = f"PYTEST_NoKey_{uuid.uuid4().hex[:8]}"
    a = requests.post(f"{BASE}/api/svc/engineer/quotes", json=_payload(name), headers=h, timeout=30).json()
    b = requests.post(f"{BASE}/api/svc/engineer/quotes", json=_payload(name), headers=h, timeout=30).json()
    assert a["id"] != b["id"]
    for q in (a, b):
        requests.post(f"{BASE}/api/svc/engineer/quotes/{q['id']}/mark", json={"status": "declined"}, headers=h, timeout=30)


# ─── Wiring guards ──────────────────────────────────────────────────

def test_backend_create_quote_accepts_idempotency_header():
    src = (pathlib.Path("/app/backend/routes/svc/engineer_quotes.py")).read_text()
    assert 'alias="Idempotency-Key"' in src
    assert '"idempotency_key"' in src or "idempotency_key" in src


def test_quote_builder_routes_through_outbox():
    src = (FRONT / "pages/ServiceOps/Engineer/EngineerQuoteBuilder.js").read_text()
    assert "outboxPost" in src
    assert "Idempotency-Key" in src
    assert "Saved offline" in src  # queued UX
    assert "r.queued" in src
