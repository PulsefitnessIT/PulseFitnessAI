"""Iteration 221-223 + search-miss telemetry."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import _test_backend_url, rate_limit_bypass_headers


def _h(token):
    return {"Authorization": f"Bearer {token}", **rate_limit_bypass_headers()}


# ── iter 221: Sicon field mapping ──────────────────────────────────


def test_sicon_mapping_requires_master(pulse_pro_token):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/sicon/field-mapping", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 403


def test_sicon_mapping_returns_27_rows(master_admin_token_session):
    base = _test_backend_url()
    r = requests.get(
        f"{base}/api/sicon/field-mapping",
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 27, f"PDF source has 27 rows; we returned {body['total']}"
    assert set(body["entities"]) == {"Case", "Contract", "Engineer", "Customer"}
    # Every row carries the keys the UI table expects.
    for row in body["mappings"]:
        for k in ("entity", "gymaxis_field", "sicon_field", "direction", "type", "notes"):
            assert k in row
        assert row["direction"] in ("→", "←", "↔")


# ── iter 222: GDPR opt-outs ────────────────────────────────────────


def test_gdpr_opt_out_helpers():
    """The pure helper logic must be safe-default and channel-aware."""
    from utils.gdpr import is_dict_opted_out, CHANNELS  # type: ignore

    # No contact → opt-out (safer).
    assert is_dict_opted_out({}, "email") is True
    assert is_dict_opted_out(None, "email") is True

    # Marketing catch-all wins.
    contact = {"opt_out_marketing": True, "opt_out_email": False}
    assert is_dict_opted_out(contact, "email") is True
    assert is_dict_opted_out(contact, "sms") is True

    # Per-channel only.
    assert is_dict_opted_out({"opt_out_email": True}, "email") is True
    assert is_dict_opted_out({"opt_out_email": True}, "sms") is False

    # All known channels respond.
    for ch in CHANNELS:
        assert isinstance(is_dict_opted_out({}, ch), bool)


# ── iter 223: Triage feedback ──────────────────────────────────────


def _seed_issue(org_id: str) -> str:
    """Insert a fake issue for the master-admin org so the triage
    feedback endpoint has a target."""
    sys.path.insert(0, "/app/backend")
    from utils.database import db  # noqa: E402

    issue_id = str(uuid.uuid4())

    async def run():
        await db.issues.insert_one({
            "id": issue_id,
            "organization_id": org_id,
            "title": "Iteration 223 pytest fault",
            "ai_triage": "{\"repair_steps\":[{\"title\":\"Cycle the power\"}]}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    asyncio.get_event_loop().run_until_complete(run())
    return issue_id


def _master_org_id(token: str) -> str | None:
    base = _test_backend_url()
    r = requests.get(f"{base}/api/auth/me", headers=_h(token), timeout=5)
    if r.status_code != 200:
        return None
    return r.json().get("organization_id")


def test_triage_feedback_records_and_lists(master_admin_token_session):
    base = _test_backend_url()
    org_id = _master_org_id(master_admin_token_session) or ""
    issue_id = _seed_issue(org_id)

    r = requests.post(
        f"{base}/api/issues/{issue_id}/triage-feedback",
        headers=_h(master_admin_token_session),
        json={
            "attempted": True,
            "tried_steps": ["Cycle the power", "Check the cable"],
            "tried_other": "Wiggled the QR sticker because it was peeling.",
            "outcome": "no_change",
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["stored"]["attempted"] is True
    assert "Cycle the power" in body["stored"]["tried_steps"]
    assert body["stored"]["outcome"] == "no_change"

    # List endpoint surfaces it back.
    r2 = requests.get(
        f"{base}/api/issues/{issue_id}/triage-feedback",
        headers=_h(master_admin_token_session),
        timeout=10,
    )
    assert r2.status_code == 200
    feedback = r2.json()["feedback"]
    assert len(feedback) == 1
    assert feedback[0]["tried_other"].startswith("Wiggled")


def test_triage_feedback_unknown_issue_404(master_admin_token_session):
    base = _test_backend_url()
    r = requests.post(
        f"{base}/api/issues/non-existent-id/triage-feedback",
        headers=_h(master_admin_token_session),
        json={"attempted": False},
        timeout=10,
    )
    assert r.status_code == 404


def test_triage_feedback_invalid_outcome_silently_dropped(master_admin_token_session):
    base = _test_backend_url()
    org_id = _master_org_id(master_admin_token_session) or ""
    issue_id = _seed_issue(org_id)
    r = requests.post(
        f"{base}/api/issues/{issue_id}/triage-feedback",
        headers=_h(master_admin_token_session),
        json={"attempted": True, "outcome": "anything-else"},
        timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["stored"]["outcome"] is None  # invalid → dropped, not 400


# ── help-search miss telemetry ─────────────────────────────────────


def test_help_search_miss_flag_and_telemetry(master_admin_token_session):
    base = _test_backend_url()
    headers = _h(master_admin_token_session)

    sentinel = f"zxqwzxqw{uuid.uuid4().hex[:8]}"
    r = requests.get(f"{base}/api/help/search?q={sentinel}", headers=headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["miss"] is True
    assert body["results"] == []

    # Search-misses admin endpoint shows our sentinel within seconds.
    r2 = requests.get(f"{base}/api/help/search-misses", headers=headers, timeout=10)
    assert r2.status_code == 200
    body2 = r2.json()
    recent_queries = [r["query"].lower() for r in body2["recent"]]
    assert sentinel in recent_queries, recent_queries[:5]


def test_help_search_misses_requires_master(pulse_pro_token):
    base = _test_backend_url()
    r = requests.get(f"{base}/api/help/search-misses", headers=_h(pulse_pro_token), timeout=10)
    assert r.status_code == 403
