"""Iter 220av — Wave 4 Security Hardening · Web-surface scrubbers.

Closes 3 risk-register findings:

  * F-04 — Bleach allow-list on stored rich text (CRM notes / activities /
    tender drafts / blog body). ``sanitize_rich_text`` / ``sanitize_rich_text_dict``.
  * F-05 — Open-redirect on post-login ``next=`` param. ``is_safe_next_url``
    rejects every classic bypass (protocol-relative, backslash, scheme,
    netloc, control chars).
  * F-22 — Email recipient validation. ``validate_email_recipient`` gates
    every ad-hoc send to addresses in the same org / CRM contacts /
    partner roster; transactional kinds pass through.

Pure-unit tests. Heavier integration coverage (live CRM activity post,
admin email send) rides on the existing ~1187-test regression.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── F-04 · sanitize_rich_text ─────────────────────────────────────


def test_sanitize_rich_text_strips_script_tag():
    from utils.web_security import sanitize_rich_text
    out = sanitize_rich_text("Hi <script>alert(1)</script> world")
    # Tag must be gone (content may survive as inert text — that's fine,
    # it's no longer an executable script element).
    assert "<script" not in out.lower()
    assert "</script" not in out.lower()
    assert "Hi" in out and "world" in out


def test_sanitize_rich_text_strips_iframe_and_svg_and_style():
    from utils.web_security import sanitize_rich_text
    for tag in ("iframe", "svg", "style", "object", "embed", "form", "link", "meta"):
        out = sanitize_rich_text(f"x<{tag} src='evil'>bad</{tag}>y")
        assert f"<{tag}" not in out.lower()


def test_sanitize_rich_text_strips_event_handlers():
    from utils.web_security import sanitize_rich_text
    out = sanitize_rich_text('<a href="/safe" onclick="alert(1)">click</a>')
    assert "onclick" not in out.lower()
    assert "click" in out
    assert "/safe" in out  # safe href survives


def test_sanitize_rich_text_strips_javascript_urls():
    from utils.web_security import sanitize_rich_text
    out = sanitize_rich_text('<a href="javascript:alert(1)">x</a>')
    assert "javascript:" not in out.lower()


def test_sanitize_rich_text_preserves_safe_html():
    from utils.web_security import sanitize_rich_text
    safe = "<p>Hello <strong>world</strong>!</p><ul><li>one</li><li>two</li></ul>"
    out = sanitize_rich_text(safe)
    assert "<strong>" in out
    assert "<ul>" in out
    assert "<li>" in out


def test_sanitize_rich_text_handles_empty_and_none():
    from utils.web_security import sanitize_rich_text
    assert sanitize_rich_text(None) == ""
    assert sanitize_rich_text("") == ""


def test_sanitize_rich_text_clamps_length():
    from utils.web_security import sanitize_rich_text
    long = "<p>" + ("x" * 300_000) + "</p>"
    out = sanitize_rich_text(long, max_chars=1000)
    assert len(out) <= 1100  # bleach may add a few chars rebalancing tags


def test_sanitize_rich_text_dict_in_place():
    from utils.web_security import sanitize_rich_text_dict
    doc = {
        "subject": "Hello <script>x</script>",
        "body": "<p>hi <strong>bold</strong></p>",
        "unaffected": "leave me alone",
        "missing": None,
    }
    out = sanitize_rich_text_dict(doc, fields=("subject", "body", "missing"))
    assert out is doc  # mutates in place
    assert "<script>" not in doc["subject"]
    assert "<strong>bold</strong>" in doc["body"]
    assert doc["unaffected"] == "leave me alone"


# ── F-05 · is_safe_next_url ────────────────────────────────────────


def test_safe_next_url_accepts_relative_paths():
    from utils.web_security import is_safe_next_url
    for ok in ("/", "/dashboard", "/crm/contacts", "/admin?tab=billing",
               "/path/with-dash", "/path/with.dot", "/path/with_underscore"):
        assert is_safe_next_url(ok), f"should accept {ok!r}"


def test_safe_next_url_rejects_protocol_relative():
    from utils.web_security import is_safe_next_url
    for bad in ("//evil.com", "//evil.com/path", "///evil.com"):
        assert not is_safe_next_url(bad), f"should reject {bad!r}"


def test_safe_next_url_rejects_backslash_tricks():
    from utils.web_security import is_safe_next_url
    for bad in ("/\\evil.com", "/\\\\evil.com", "/path\\evil"):
        assert not is_safe_next_url(bad), f"should reject {bad!r}"


def test_safe_next_url_rejects_schemes():
    from utils.web_security import is_safe_next_url
    for bad in ("javascript:alert(1)", "data:text/html,<script>",
                "vbscript:msgbox(1)", "http://evil.com",
                "https://app.gymaxisai.com/admin", "ftp://x"):
        assert not is_safe_next_url(bad), f"should reject {bad!r}"


def test_safe_next_url_rejects_control_chars():
    from utils.web_security import is_safe_next_url
    for bad in ("/path\r\n", "/path\x00", "/path\t", "/path with space\nLocation: evil"):
        assert not is_safe_next_url(bad), f"should reject {bad!r}"


def test_safe_next_url_rejects_garbage():
    from utils.web_security import is_safe_next_url
    assert not is_safe_next_url(None)
    assert not is_safe_next_url("")
    assert not is_safe_next_url("dashboard")        # no leading slash
    assert not is_safe_next_url("../../etc/passwd") # no leading slash
    assert not is_safe_next_url("/" + "x" * 600)    # too long


def test_safe_next_or_falls_back():
    from utils.web_security import safe_next_or
    assert safe_next_or("/safe", "/dashboard") == "/safe"
    assert safe_next_or("//evil.com", "/dashboard") == "/dashboard"
    assert safe_next_or(None, "/dashboard") == "/dashboard"


# ── F-22 · validate_email_recipient ────────────────────────────────


def test_recipient_validation_off_by_default(monkeypatch):
    """When env flag is unset, validation must be a complete no-op."""
    monkeypatch.delenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION", raising=False)
    import importlib
    import utils.web_security as w
    importlib.reload(w)

    # Even an obviously malformed email passes when validation is off.
    _run(w.validate_email_recipient(
        to_email="not-an-email",
        kind="adhoc",
        organization_id="org-1",
        db=MagicMock(),
    ))


def test_recipient_validation_allows_transactional_kinds(monkeypatch):
    monkeypatch.setenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION", "true")
    import importlib
    import utils.web_security as w
    importlib.reload(w)
    # Transactional kind always passes — DB not even consulted.
    _run(w.validate_email_recipient(
        to_email="anyone@anywhere.com",
        kind="auth.password_reset",
        organization_id=None,
        db=MagicMock(),
    ))
    monkeypatch.delenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION")
    importlib.reload(w)


def test_recipient_validation_rejects_adhoc_without_org(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION", "true")
    import importlib
    import utils.web_security as w
    importlib.reload(w)
    try:
        _run(w.validate_email_recipient(
            to_email="x@y.com", kind="adhoc",
            organization_id=None, db=MagicMock(),
        ))
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
    monkeypatch.delenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION")
    importlib.reload(w)


def test_recipient_validation_rejects_bad_email_format(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION", "true")
    import importlib
    import utils.web_security as w
    importlib.reload(w)
    try:
        _run(w.validate_email_recipient(
            to_email="not-an-email", kind="adhoc",
            organization_id="org-1", db=MagicMock(),
        ))
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
    monkeypatch.delenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION")
    importlib.reload(w)


def _make_db_mock_with_match_in(collection_name: str):
    """Build a MagicMock that returns a hit for ``collection_name``
    only (every other collection lookup returns None)."""
    mock_db = MagicMock()

    class _Coll:
        def __init__(self, name):
            self.name = name
            self.find_one = AsyncMock(return_value=(
                {"id": "match"} if name == collection_name else None
            ))

    def _getitem(name):
        return _Coll(name)

    mock_db.__getitem__.side_effect = _getitem
    mock_db.users = _Coll("users")
    return mock_db


def test_recipient_validation_allows_same_org_user(monkeypatch):
    monkeypatch.setenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION", "true")
    import importlib
    import utils.web_security as w
    importlib.reload(w)
    db_mock = _make_db_mock_with_match_in("users")
    # users is a direct attribute, not via __getitem__, so override:
    db_mock.users.find_one = AsyncMock(return_value={"id": "u1"})
    _run(w.validate_email_recipient(
        to_email="staff@gym.local", kind="adhoc",
        organization_id="org-1", db=db_mock,
    ))
    monkeypatch.delenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION")
    importlib.reload(w)


def test_recipient_validation_allows_crm_contact(monkeypatch):
    monkeypatch.setenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION", "true")
    import importlib
    import utils.web_security as w
    importlib.reload(w)

    db_mock = MagicMock()
    db_mock.users = MagicMock()
    db_mock.users.find_one = AsyncMock(return_value=None)

    crm_coll = MagicMock()
    crm_coll.find_one = AsyncMock(return_value={"id": "c1"})
    fallback_coll = MagicMock()
    fallback_coll.find_one = AsyncMock(return_value=None)

    def _getitem(name):
        return crm_coll if name == "crm2_contacts" else fallback_coll
    db_mock.__getitem__.side_effect = _getitem

    _run(w.validate_email_recipient(
        to_email="contact@external.com", kind="adhoc",
        organization_id="org-1", db=db_mock,
    ))
    monkeypatch.delenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION")
    importlib.reload(w)


def test_recipient_validation_rejects_unknown_address(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION", "true")
    import importlib
    import utils.web_security as w
    importlib.reload(w)

    db_mock = MagicMock()
    db_mock.users = MagicMock()
    db_mock.users.find_one = AsyncMock(return_value=None)
    none_coll = MagicMock()
    none_coll.find_one = AsyncMock(return_value=None)
    db_mock.__getitem__.side_effect = lambda _name: none_coll

    try:
        _run(w.validate_email_recipient(
            to_email="random@stranger.com", kind="adhoc",
            organization_id="org-1", db=db_mock,
        ))
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "organisation" in exc.detail.lower() or "roster" in exc.detail.lower()
    monkeypatch.delenv("ENFORCE_EMAIL_RECIPIENT_VALIDATION")
    importlib.reload(w)


# ── End-to-end smokes: confirm crm_v2 calls sanitize_rich_text ────


def test_create_activity_scrubs_body_xss():
    """Smoke: activity body containing <script> is scrubbed on persist."""
    import routes.crm_v2 as crm

    fake_user = {"id": "u1", "full_name": "Tester",
                 "organization_id": "org-1"}

    fake_db = MagicMock()
    fake_db.crm2_activities.insert_one = AsyncMock(return_value=MagicMock())

    with patch.object(crm, "db", fake_db):
        result = _run(crm.create_activity(
            data={
                "type": "note",
                "subject": "Important <script>alert(1)</script>",
                "body": "<p>Notes</p><iframe src='evil'></iframe>",
                "company_id": "co-1",
            },
            user=fake_user,
        ))
    assert "<script>" not in result["subject"]
    assert "<iframe" not in result["body"].lower()
    assert "<p>Notes</p>" in result["body"]  # safe HTML survives
