"""
Iter 220x — Health & Safety channel folded into the existing Weekly Digest.

User feedback: "Don't think we need a dedicated HSE digest report — could
this be added to the Weekly Digest report?"

These tests pin down:

* The default ``channels`` payload exposes ``health_safety_incidents``.
* ``build_digest_payload`` includes incident rows when the channel is on
  AND there are accidents / dangerous_occurrences / RIDDOR-flagged
  incidents in the org's last frequency-window.
* The channel toggle off correctly excludes incidents.
* ``render_digest_html`` recognises ``incident.*`` types (no "incident."
  leakage in the rendered HTML).
* The ``/api/digest/preferences`` GET endpoint returns the new channel.

These tests mock ``db.incidents.find`` directly (motor's session-loop
client gets flaky when multiple test functions hammer the same
collection in quick succession — see Iter 220r for the same pattern).
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import requests

from tests.conftest import _test_backend_url

BASE = _test_backend_url()


def _run(coro):
    """Drive ``coro`` on a fresh loop. Each test gets its own loop so
    motor lifecycle never bleeds across tests."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_cursor(items):
    cur = MagicMock()
    cur.sort = MagicMock(return_value=cur)
    cur.to_list = AsyncMock(return_value=list(items))
    return cur


def _make_incident_doc(org_id: str, **overrides) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"inc-test-{uuid.uuid4().hex[:10]}",
        "organization_id": org_id,
        "reference": f"IR-TEST-{uuid.uuid4().hex[:6].upper()}",
        "kind": "accident",
        "severity": "minor",
        "status": "reported",
        "description": "Member tripped on a stray dumbbell while walking the free-weights row.",
        "riddor": {"status": "not_assessed"},
        "fatality": False,
        "auto_escalated": False,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    doc.update(overrides)
    return doc


# ─── Default preferences expose the new channel ──────────────────

def test_default_preferences_include_hs_channel():
    from utils.digest import DEFAULT_PREFS
    assert "health_safety_incidents" in DEFAULT_PREFS["channels"]
    # Safety-critical channels should default ON for managers/owners.
    assert DEFAULT_PREFS["channels"]["health_safety_incidents"] is True


def test_get_preferences_returns_hs_channel(pulse_pro_token):
    if not pulse_pro_token:
        return
    r = requests.get(
        f"{BASE}/api/digest/preferences",
        headers={"Authorization": f"Bearer {pulse_pro_token}"}, timeout=10,
    )
    assert r.status_code == 200
    channels = r.json().get("channels") or {}
    assert "health_safety_incidents" in channels


# ─── build_digest_payload — incident inclusion (mocked DB) ────────

def test_build_payload_includes_recent_accident_when_channel_on():
    from utils import digest

    org_id = "org-test-1"
    doc = _make_incident_doc(org_id, kind="accident", severity="moderate")
    user = {"id": "u-1", "organization_id": org_id, "email": "m@x",
            "company_name": "Test Gym"}
    prefs = {
        "frequency": "weekly",
        "channels": {
            "warranty_expiring": False, "ppm_overdue": False,
            "supplier_sla_drift": False,
            "health_safety_incidents": True,
        },
    }

    fake_db = MagicMock()
    fake_db.trust_events.find = MagicMock(return_value=_make_cursor([]))
    fake_db.incidents.find = MagicMock(return_value=_make_cursor([doc]))

    with patch.object(digest, "db", fake_db):
        payload = _run(digest.build_digest_payload(user, prefs))

    assert payload is not None
    types = [it["type"] for it in payload["items"]]
    assert any(t.startswith("incident.") for t in types), types


def test_build_payload_excludes_incidents_when_channel_off():
    from utils import digest

    user = {"id": "u-1", "organization_id": "org-test-2", "email": "m@x"}
    prefs = {
        "frequency": "weekly",
        "channels": {
            "warranty_expiring": False, "ppm_overdue": False,
            "supplier_sla_drift": False,
            "health_safety_incidents": False,
        },
    }

    fake_db = MagicMock()
    fake_db.trust_events.find = MagicMock(return_value=_make_cursor([]))
    fake_db.incidents.find = MagicMock(return_value=_make_cursor([]))

    with patch.object(digest, "db", fake_db):
        payload = _run(digest.build_digest_payload(user, prefs))
    # No nudges and HS off → nothing to send. And incidents.find must
    # not even have been called.
    assert payload is None
    fake_db.incidents.find.assert_not_called()


def test_build_payload_riddor_flagged_marks_high_severity():
    from utils import digest

    org_id = "org-test-3"
    doc = _make_incident_doc(
        org_id, kind="dangerous_occurrence",
        severity="serious",
        riddor={"status": "confirmed"},
    )
    user = {"id": "u-1", "organization_id": org_id, "email": "m@x"}
    prefs = {
        "frequency": "weekly",
        "channels": {
            "warranty_expiring": False, "ppm_overdue": False,
            "supplier_sla_drift": False,
            "health_safety_incidents": True,
        },
    }

    fake_db = MagicMock()
    fake_db.trust_events.find = MagicMock(return_value=_make_cursor([]))
    fake_db.incidents.find = MagicMock(return_value=_make_cursor([doc]))

    with patch.object(digest, "db", fake_db):
        payload = _run(digest.build_digest_payload(user, prefs))

    assert payload is not None
    riddor_rows = [it for it in payload["items"] if it["type"] == "incident.riddor"]
    assert riddor_rows, f"expected an incident.riddor row in {payload['items']}"
    assert riddor_rows[0]["severity"] == "high"


def test_build_payload_window_scales_with_frequency():
    """The weekly query uses a 7d window and the monthly uses 30d. We
    pin this by inspecting the ``created_at`` predicate the function
    passes to ``incidents.find``."""
    from utils import digest

    org_id = "org-test-4"
    user = {"id": "u-1", "organization_id": org_id, "email": "m@x"}
    base_channels = {
        "warranty_expiring": False, "ppm_overdue": False,
        "supplier_sla_drift": False, "health_safety_incidents": True,
    }

    fake_db = MagicMock()
    fake_db.trust_events.find = MagicMock(return_value=_make_cursor([]))
    fake_db.incidents.find = MagicMock(return_value=_make_cursor([]))

    with patch.object(digest, "db", fake_db):
        _run(digest.build_digest_payload(user, {"frequency": "weekly", "channels": base_channels}))
        weekly_query = fake_db.incidents.find.call_args[0][0]
        weekly_since = datetime.fromisoformat(weekly_query["created_at"]["$gte"])

        fake_db.incidents.find.reset_mock()
        fake_db.incidents.find.return_value = _make_cursor([])
        _run(digest.build_digest_payload(user, {"frequency": "monthly", "channels": base_channels}))
        monthly_query = fake_db.incidents.find.call_args[0][0]
        monthly_since = datetime.fromisoformat(monthly_query["created_at"]["$gte"])

    now = datetime.now(timezone.utc)
    # Weekly window ~7 days; monthly window ~30 days. Allow ±5 min jitter
    # for the second clock-tick between the two calls.
    weekly_days = (now - weekly_since).total_seconds() / 86400
    monthly_days = (now - monthly_since).total_seconds() / 86400
    assert 6.9 <= weekly_days <= 7.1, weekly_days
    assert 29.9 <= monthly_days <= 30.1, monthly_days


def test_build_payload_window_keeps_query_org_scoped():
    """The query MUST filter by the user's organization_id — never
    leak incidents across tenants."""
    from utils import digest

    org_id = "org-test-leak-guard"
    user = {"id": "u-1", "organization_id": org_id, "email": "m@x"}
    prefs = {
        "frequency": "weekly",
        "channels": {
            "warranty_expiring": False, "ppm_overdue": False,
            "supplier_sla_drift": False, "health_safety_incidents": True,
        },
    }

    fake_db = MagicMock()
    fake_db.trust_events.find = MagicMock(return_value=_make_cursor([]))
    fake_db.incidents.find = MagicMock(return_value=_make_cursor([]))

    with patch.object(digest, "db", fake_db):
        _run(digest.build_digest_payload(user, prefs))

    fake_db.incidents.find.assert_called_once()
    query = fake_db.incidents.find.call_args[0][0]
    assert query["organization_id"] == org_id


# ─── Window math (no DB) ─────────────────────────────────────────

def test_window_days_unknown_frequency_defaults_to_weekly():
    """Daily / weekly / monthly map cleanly; anything else falls back
    to the 7-day window we already tested."""
    from utils import digest
    # The mapping lives inside ``build_digest_payload`` — easiest way to
    # pin it is to call the function with a bogus frequency and check
    # the predicate.
    org_id = "org-test-fallback"
    user = {"id": "u-1", "organization_id": org_id, "email": "m@x"}
    prefs = {
        "frequency": "bogus-value",
        "channels": {
            "warranty_expiring": False, "ppm_overdue": False,
            "supplier_sla_drift": False, "health_safety_incidents": True,
        },
    }
    fake_db = MagicMock()
    fake_db.trust_events.find = MagicMock(return_value=_make_cursor([]))
    fake_db.incidents.find = MagicMock(return_value=_make_cursor([]))

    with patch.object(digest, "db", fake_db):
        _run(digest.build_digest_payload(user, prefs))

    query = fake_db.incidents.find.call_args[0][0]
    since = datetime.fromisoformat(query["created_at"]["$gte"])
    days = (datetime.now(timezone.utc) - since).total_seconds() / 86400
    assert 6.9 <= days <= 7.1, days


# ─── Render path handles incident types cleanly ──────────────────

def test_render_digest_html_humanises_incident_types():
    from utils.digest import render_digest_html
    user = {"full_name": "Lee", "email": "l@x", "company_name": "Pulse"}
    payload = {
        "summary": "2 item(s) need your attention at Pulse",
        "items": [
            {"type": "incident.accident", "severity": "med",
             "customer_safe_message": "[IR-2026-0001] Member tripped near rack."},
            {"type": "incident.riddor", "severity": "high",
             "customer_safe_message": "[IR-2026-0002] Possible >7-day absence."},
        ],
    }
    html = render_digest_html(user, payload, "weekly")
    assert "Accident reported" in html
    assert "RIDDOR reportable incident" in html
    # No raw "incident." leakage in the rendered titles.
    assert "incident.accident" not in html
    assert "incident.riddor" not in html


def test_timedelta_import_in_digest():
    """Guard: build_digest_payload imports timedelta inside utils.digest.
    A missing import would crash with NameError only at call time."""
    from utils import digest
    assert hasattr(digest, "timedelta") or "timedelta" in dir(digest), \
        "timedelta must be importable from utils.digest"
