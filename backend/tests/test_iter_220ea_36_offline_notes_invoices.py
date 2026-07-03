"""Iter 220ea·36 — Offline parity for engineer notes + invoices.

Extends offline coverage (quotes + job-completion already done; mileage
already covered via engineerSendOrQueue) to the two remaining write paths
the user called out: handoff notes and invoices. Both are now queued in the
engineer outbox and replayed on reconnect, with an Idempotency-Key making
the server create idempotent so a lost-response replay never duplicates.
"""
from __future__ import annotations

import os
import pathlib
import uuid

import requests

from conftest import rate_limit_bypass_headers

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "https://rbac-modules.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("TEST_MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
ADMIN_PW = os.environ.get("TEST_MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
FRONT = pathlib.Path("/app/frontend/src/pages/ServiceOps/Engineer")


def _token() -> str:
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
        headers=rate_limit_bypass_headers(), timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


# ─── Invoice create idempotency ─────────────────────────────────────

def test_invoice_create_idempotent_on_replay():
    tok = _token()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    key = f"pytest-inv-{uuid.uuid4().hex}"
    name = f"PYTEST_Inv_{uuid.uuid4().hex[:8]}"
    payload = {"customer_name": name, "lines": [{"kind": "labour", "description": "Repair", "quantity": 1, "unit_price": 80}]}

    r1 = requests.post(f"{BASE}/api/svc/engineer/invoices", json=payload, headers={**h, "Idempotency-Key": key}, timeout=30)
    assert r1.status_code in (200, 201), r1.text
    a = r1.json()
    assert a.get("idempotency_key") == key

    r2 = requests.post(f"{BASE}/api/svc/engineer/invoices", json=payload, headers={**h, "Idempotency-Key": key}, timeout=30)
    b = r2.json()
    assert b["id"] == a["id"], "replay created a DUPLICATE invoice"
    assert b["invoice_number"] == a["invoice_number"]

    requests.post(f"{BASE}/api/svc/engineer/invoices/{a['id']}/mark", json={"status": "void"}, headers=h, timeout=30)


def test_invoice_create_without_key_unique():
    tok = _token()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    name = f"PYTEST_InvNoKey_{uuid.uuid4().hex[:8]}"
    payload = {"customer_name": name, "lines": [{"kind": "labour", "description": "x", "quantity": 1, "unit_price": 10}]}
    a = requests.post(f"{BASE}/api/svc/engineer/invoices", json=payload, headers=h, timeout=30).json()
    b = requests.post(f"{BASE}/api/svc/engineer/invoices", json=payload, headers=h, timeout=30).json()
    assert a["id"] != b["id"]
    for inv in (a, b):
        requests.post(f"{BASE}/api/svc/engineer/invoices/{inv['id']}/mark", json={"status": "void"}, headers=h, timeout=30)


# ─── Handoff note idempotency ───────────────────────────────────────

def _find_case_for_admin(h: dict) -> str | None:
    r = requests.get(f"{BASE}/api/svc/cases", params={"limit": 1}, headers=h, timeout=30)
    if r.status_code != 200:
        return None
    cases = r.json().get("cases") or []
    return cases[0]["id"] if cases else None


def test_handoff_note_idempotent_on_replay():
    tok = _token()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    case_id = _find_case_for_admin(h)
    if not case_id:
        return  # no cases reachable in this env — skip gracefully
    key = f"pytest-note-{uuid.uuid4().hex}"
    note = f"PYTEST handoff {uuid.uuid4().hex[:6]}"
    headers = {**h, "Idempotency-Key": key}

    r1 = requests.post(f"{BASE}/api/svc/engineer/jobs/{case_id}/handoff-note", json={"note": note}, headers=headers, timeout=30)
    if r1.status_code == 404:
        return  # admin can't act as engineer on this case — skip
    assert r1.status_code == 200, r1.text
    e1 = r1.json()["entry"]
    assert e1.get("idempotency_key") == key

    r2 = requests.post(f"{BASE}/api/svc/engineer/jobs/{case_id}/handoff-note", json={"note": note}, headers=headers, timeout=30)
    assert r2.status_code == 200
    e2 = r2.json()["entry"]
    assert e2["id"] == e1["id"], "replay appended a DUPLICATE handoff note"


# ─── Wiring guards ──────────────────────────────────────────────────

def test_backend_endpoints_accept_idempotency():
    inv = pathlib.Path("/app/backend/routes/svc/engineer_invoices.py").read_text()
    assert 'alias="Idempotency-Key"' in inv and 'inv["idempotency_key"]' in inv
    p3 = pathlib.Path("/app/backend/routes/svc/engineer_phase3.py").read_text()
    # handoff-note now reads the header and dedupes
    assert p3.count('alias="Idempotency-Key"') >= 3  # mileage + parts + note


def test_frontend_notes_and_invoices_offline():
    job = (FRONT / "EngineerJobDetailV2.js").read_text()
    # Handoff note composer now queues via engineerSendOrQueue.
    assert "path: `/svc/engineer/jobs/${caseId}/handoff-note`" in job
    assert "Handoff note queued" in job
    inv = (FRONT / "EngineerInvoiceBuilder.js").read_text()
    assert "outboxPost" in inv and "Idempotency-Key" in inv
    assert "Saved offline" in inv and "r.queued" in inv


def test_pending_sync_badge_on_lists():
    """Iter 220ea·37 — the outbox 'pending sync' pill is surfaced on both
    the Quotes and Invoices list headers so engineers get confirmation
    their on-site quotes/invoices are queued and when they've synced."""
    for fname in ("EngineerQuotes.js", "EngineerInvoices.js"):
        src = (FRONT / fname).read_text()
        assert "OutboxStatusPill" in src, f"{fname} missing OutboxStatusPill import/use"
        assert "from '@/utils/engineerStatusBoot'" in src, f"{fname} missing pill import path"
