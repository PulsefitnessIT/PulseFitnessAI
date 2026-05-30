"""Iter 220dg — Engineer → customer outbound ETA push.

Pins:

  * Helpers: ``build_tracking_url_for_case`` lazy-mints a
    ``track_token``; ``build_eta_minutes_estimate`` computes a
    haversine ETA only when the engineer pinged recently;
    ``eta_label_from_minutes`` renders friendly strings.
  * ``POST /api/svc/engineer/jobs/{case_id}/eta-update``:
      - 404 if case missing
      - 403 if caller isn't the assigned engineer (non-admin)
      - 409 if status not en_route / assigned / on_site
      - 400 if no customer_email
      - happy path stamps ``eta_last_sent_at`` / ``eta_last_minutes``
        and emits a ``comm`` event.
  * Auto-notify on transition adds ``eta_label`` + ``tracking_url``
    + ``tracking_link_html`` to the email context so the default
    en_route template renders an arrival window + Track-live CTA.
  * Default ``engineer_en_route`` template uses the new tokens.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _user(uid="eng-1", org="org-1", admin=False):
    return {
        "id": uid, "organization_id": org,
        "is_master_admin": admin,
        "email": "u@x.test", "full_name": "Eng One",
    }


# ── 1 · Helpers ──────────────────────────────────────────────────


def test_eta_label_friendly_phrases():
    from routes.svc.engineer_eta_update import eta_label_from_minutes
    assert eta_label_from_minutes(None) == "shortly"
    assert eta_label_from_minutes(0)    == "shortly"
    assert eta_label_from_minutes(1)    == "in about 1 minute"
    assert eta_label_from_minutes(25)   == "in about 25 minutes"
    assert eta_label_from_minutes(60)   == "in about 1 hour"
    assert eta_label_from_minutes(125)  == "in about 2h 5m"


def test_build_tracking_url_lazy_mints_token_when_missing():
    fdb = MagicMock()
    fdb.svc_cases.update_one = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb), \
             patch.dict("os.environ", {"FRONTEND_URL": "https://app.test"}):
            from routes.svc.engineer_eta_update import build_tracking_url_for_case
            return await build_tracking_url_for_case(
                {"id": "case-1", "organization_id": "org-1"},
            )

    url = _run(run())
    assert url.startswith("https://app.test/track/")
    assert len(url.split("/track/")[1]) >= 20  # token_urlsafe(18) → ~24 chars
    fdb.svc_cases.update_one.assert_awaited_once()


def test_build_tracking_url_reuses_existing_token():
    fdb = MagicMock()
    fdb.svc_cases.update_one = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb), \
             patch.dict("os.environ", {"FRONTEND_URL": "https://app.test"}):
            from routes.svc.engineer_eta_update import build_tracking_url_for_case
            return await build_tracking_url_for_case({
                "id": "case-1", "organization_id": "org-1",
                "track_token": "AAAAAAAAAAAAAAAAAAAA",
            })

    url = _run(run())
    assert url == "https://app.test/track/AAAAAAAAAAAAAAAAAAAA"
    fdb.svc_cases.update_one.assert_not_called()


def test_build_eta_returns_none_when_case_not_en_route():
    async def run():
        from routes.svc.engineer_eta_update import build_eta_minutes_estimate
        return await build_eta_minutes_estimate({"status": "assigned"})
    assert _run(run()) is None


def test_build_eta_returns_minutes_with_fresh_ping():
    fdb = MagicMock()
    recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    fdb.svc_engineer_locations.find_one = AsyncMock(return_value={
        "lat": 51.5074, "lng": -0.1278,    # London
        "recorded_at": recent,
    })
    case = {
        "status": "en_route", "assigned_engineer_id": "eng-1",
        "site_lat": 51.5200, "site_lng": -0.1050,   # ~2 km north-east
    }

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb):
            from routes.svc.engineer_eta_update import build_eta_minutes_estimate
            return await build_eta_minutes_estimate(case)

    mins = _run(run())
    assert mins is not None
    assert 1 <= mins <= 15   # 2 km @ 35 km/h ≈ 3-4 min


def test_build_eta_returns_none_when_ping_stale():
    fdb = MagicMock()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    fdb.svc_engineer_locations.find_one = AsyncMock(return_value={
        "lat": 51.5, "lng": -0.13, "recorded_at": stale,
    })

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb):
            from routes.svc.engineer_eta_update import build_eta_minutes_estimate
            return await build_eta_minutes_estimate({
                "status": "en_route", "assigned_engineer_id": "eng-1",
                "site_lat": 51.52, "site_lng": -0.1,
            })

    assert _run(run()) is None


# ── 2 · Endpoint guards ──────────────────────────────────────────


def test_eta_update_404_when_case_missing():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value=None)

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb):
            from routes.svc.engineer_eta_update import send_eta_update, EtaUpdateIn
            return await send_eta_update(
                case_id="nope", body=EtaUpdateIn(), user=_user(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 404


def test_eta_update_403_when_not_assigned_engineer():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "someone-else",
        "status": "en_route", "customer_email": "c@x.test",
    })

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb):
            from routes.svc.engineer_eta_update import send_eta_update, EtaUpdateIn
            return await send_eta_update(
                case_id="case-1", body=EtaUpdateIn(), user=_user(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 403


def test_eta_update_409_when_wrong_status():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "eng-1",
        "status": "new", "customer_email": "c@x.test",
    })

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb):
            from routes.svc.engineer_eta_update import send_eta_update, EtaUpdateIn
            return await send_eta_update(
                case_id="case-1", body=EtaUpdateIn(), user=_user(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 409


def test_eta_update_400_when_no_customer_email():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "eng-1",
        "status": "en_route", "customer_email": "",
    })

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb):
            from routes.svc.engineer_eta_update import send_eta_update, EtaUpdateIn
            return await send_eta_update(
                case_id="case-1", body=EtaUpdateIn(), user=_user(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 400


def test_eta_update_409_when_comms_disabled():
    import pytest
    from fastapi import HTTPException

    fdb = MagicMock()
    fdb.svc_cases.find_one = AsyncMock(return_value={
        "id": "case-1", "organization_id": "org-1",
        "assigned_engineer_id": "eng-1",
        "status": "en_route", "customer_email": "c@x.test",
        "comms_auto_notify": False,
    })

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb):
            from routes.svc.engineer_eta_update import send_eta_update, EtaUpdateIn
            return await send_eta_update(
                case_id="case-1", body=EtaUpdateIn(), user=_user(),
            )

    with pytest.raises(HTTPException) as exc:
        _run(run())
    assert exc.value.status_code == 409


# ── 3 · Happy path ───────────────────────────────────────────────


def test_eta_update_happy_path_sends_email_and_stamps_case():
    fdb = MagicMock()
    case = {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "title": "Treadmill #3",
        "assigned_engineer_id": "eng-1",
        "assigned_engineer_name": "Eng One",
        "status": "en_route",
        "customer_email": "customer@x.test",
        "customer_name": "Customer Co",
        "site_name": "London HQ",
        "track_token": "TOK_123456789012345678",
        "priority": "p2",
    }
    fdb.svc_cases.find_one = AsyncMock(return_value=case)
    fdb.svc_cases.update_one = AsyncMock()
    fdb.svc_engineer_locations.find_one = AsyncMock(return_value=None)
    # ``_ensure_defaults`` queries svc_email_templates.find(...).to_list().
    tpl_cur = MagicMock()
    tpl_cur.to_list = AsyncMock(return_value=[])
    fdb.svc_email_templates.find = MagicMock(return_value=tpl_cur)
    fdb.svc_email_templates.insert_many = AsyncMock()
    fdb.svc_email_templates.insert_one = AsyncMock()
    fdb.svc_email_templates.find_one = AsyncMock(return_value={
        "subject": "Your engineer is on the way — {{reference}}",
        "body_html": (
            "<p>Hi {{customer_name}},</p>"
            "<p>{{engineer_name}} is on the way to {{site_name}}.</p>"
            "<p>Arrival: <strong>{{eta_label}}</strong>.</p>"
            "{{engineer_message_html}}"
            "{{tracking_link_html}}"
        ),
        "active": True,
    })
    fdb.svc_comms_log.insert_one = AsyncMock()
    send = AsyncMock(return_value=True)
    append = AsyncMock()

    async def run():
        with patch("routes.svc.engineer_eta_update.db", fdb), \
             patch("routes.svc.comms.db", fdb), \
             patch("utils.email.send_email", send), \
             patch("utils.svc_state.append_event", append), \
             patch.dict("os.environ", {"FRONTEND_URL": "https://app.test"}):
            from routes.svc.engineer_eta_update import send_eta_update, EtaUpdateIn
            return await send_eta_update(
                case_id="case-1",
                body=EtaUpdateIn(eta_minutes=15,
                                 message="Stuck behind a lorry"),
                user=_user(),
            )

    out = _run(run())
    assert out["ok"] is True
    assert out["eta_minutes"] == 15
    assert out["eta_label"] == "in about 15 minutes"
    assert out["tracking_url"].endswith("/track/TOK_123456789012345678")
    # Email actually went out via send_email + tracking link inserted.
    send.assert_awaited_once()
    sent_kwargs = send.await_args.kwargs
    assert "TOK_123456789012345678" in sent_kwargs["html"]
    assert "Stuck behind a lorry" in sent_kwargs["html"]
    assert "in about 15 minutes" in sent_kwargs["html"]
    # Case stamped with sent timestamps.
    update_calls = fdb.svc_cases.update_one.await_args_list
    set_doc = update_calls[-1].args[1]["$set"]
    assert set_doc["eta_last_minutes"] == 15
    assert "eta_last_sent_at" in set_doc
    append.assert_awaited_once()


# ── 4 · Auto-notify is enriched too ──────────────────────────────


def test_auto_notify_includes_tracking_link_and_eta_context():
    fdb = MagicMock()
    case = {
        "id": "case-1", "organization_id": "org-1",
        "reference": "GA-100", "title": "Treadmill",
        "customer_email": "c@x.test", "customer_name": "Cust",
        "site_name": "HQ", "priority": "p2",
        "comms_auto_notify": True,
        "track_token": "TOKAUTONOTIFY99999999",
        "assigned_engineer_id": "eng-1",
        "assigned_engineer_name": "Eng One",
    }
    fdb.svc_comms_log.find_one = AsyncMock(return_value=None)
    fdb.svc_comms_log.insert_one = AsyncMock()
    fdb.svc_email_templates.find = MagicMock()
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=[])
    fdb.svc_email_templates.find.return_value = cur
    fdb.svc_email_templates.insert_many = AsyncMock()
    fdb.svc_email_templates.insert_one = AsyncMock()
    fdb.svc_email_templates.find_one = AsyncMock(return_value={
        "subject": "On the way — {{reference}}",
        "body_html": (
            "<p>{{engineer_name}} en route, ETA {{eta_label}}.</p>"
            "{{tracking_link_html}}"
        ),
        "active": True,
    })
    fdb.organizations.find_one = AsyncMock(return_value={"id": "org-1", "name": "Acme"})
    fdb.sites.find_one = AsyncMock(return_value=None)
    fdb.svc_engineer_locations.find_one = AsyncMock(return_value=None)
    fdb.svc_case_events.insert_one = AsyncMock()
    send = AsyncMock(return_value=True)

    async def run():
        with patch("routes.svc.comms.db", fdb), \
             patch("routes.svc.engineer_eta_update.db", fdb), \
             patch("routes.svc.comms.send_email", send), \
             patch.dict("os.environ", {"FRONTEND_URL": "https://app.test"}):
            from routes.svc.comms import auto_notify_on_transition
            await auto_notify_on_transition(
                case=case, target_state="en_route", actor=_user(),
            )

    _run(run())
    send.assert_awaited_once()
    html = send.await_args.kwargs["html"]
    assert "TOKAUTONOTIFY99999999" in html
    assert "shortly" in html or "in about" in html  # ETA label present


# ── 5 · Default template now references new tokens ───────────────


def test_default_en_route_template_uses_new_tokens():
    from routes.svc import comms
    en_route = next(d for d in comms._DEFAULTS if d["key"] == "engineer_en_route")
    assert "{{eta_label}}" in en_route["body_html"]
    assert "{{tracking_link_html}}" in en_route["body_html"]
    assert "{{engineer_message_html}}" in en_route["body_html"]


# ── 6 · Frontend wiring ──────────────────────────────────────────


def test_frontend_eta_chip_mounted_and_wired():
    src = Path(
        "/app/frontend/src/pages/ServiceOps/Engineer/EngineerJobDetailV2.js"
    ).read_text()
    assert "EtaUpdateChip" in src
    assert "/svc/engineer/jobs/${caseId}/eta-update" in src
    for tid in (
        "jaag-eta-chip", "jaag-eta-open", "jaag-eta-panel",
        "jaag-eta-mins", "jaag-eta-message", "jaag-eta-submit",
        "jaag-eta-cancel",
    ):
        assert f'data-testid="{tid}"' in src, f"missing test-id: {tid}"
    # Preset chips render with a templated test ID.
    assert "jaag-eta-preset-${n}" in src
