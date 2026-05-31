"""Iter 220aw — Wave 5 Security Hardening · SSRF / AV / Secret-vault.

Closes 3 risk-register findings:

  * F-24 — Malware scanner. Static-signature scan (EICAR + shell-in-image
    payloads) fires regardless of ClamAV availability; ``STRICT_AV_MODE``
    forces fail-closed even in dev.
  * F-26 — SSRF guard. ``assert_safe_external_url`` rejects every URL
    that resolves to a private / loopback / link-local / metadata IP,
    plus an explicit hostname denylist (``metadata.google.internal``).
  * F-27 — Fernet field-level encryption. ``utils/secret_vault.py``
    exposes ``encrypt_secrets_in_dict`` / ``decrypt_secrets_in_dict`` /
    ``redact_secrets_in_dict``. Wired into ``routes/integrations.py``
    so ``api_token`` / ``webhook_secret`` / ``credentials`` are
    encrypted at rest and masked in GET responses.

Pure unit tests — no live MongoDB, ClamAV, or DNS.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── F-24 · malware_scan static signatures + STRICT mode ───────────


def test_static_scan_detects_eicar():
    from utils.malware_scan import _static_scan, EICAR_SIGNATURE
    assert _static_scan(EICAR_SIGNATURE) == "Eicar-Test-Signature"
    # Embedded anywhere in the first 64 KB still trips.
    assert _static_scan(b"x" * 1000 + EICAR_SIGNATURE + b"y" * 1000) == "Eicar-Test-Signature"


def test_static_scan_detects_shell_in_image():
    from utils.malware_scan import _static_scan
    assert _static_scan(b"#!/bin/sh\necho hi") == "ShellScript-In-Upload"
    assert _static_scan(b"#!/bin/bash\nls") == "BashScript-In-Upload"


def test_static_scan_misses_clean_bytes():
    from utils.malware_scan import _static_scan
    assert _static_scan(b"%PDF-1.4\n... clean PDF content ...") is None
    assert _static_scan(b"\xff\xd8\xff\xe0 ... clean JPEG ...") is None
    assert _static_scan(b"") is None


def test_scan_bytes_blocks_eicar():
    from fastapi import HTTPException
    from utils.malware_scan import EICAR_SIGNATURE, scan_bytes
    try:
        _run(scan_bytes(EICAR_SIGNATURE, "test.txt"))
        raise AssertionError("expected HTTPException(400)")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Eicar" in exc.detail


def test_scan_bytes_clean_bytes_pass_in_dev(monkeypatch):
    monkeypatch.delenv("CLAMAV_HOST", raising=False)
    monkeypatch.delenv("STRICT_AV_MODE", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    from utils.malware_scan import scan_bytes
    _run(scan_bytes(b"%PDF-1.4 clean", "test.pdf"))  # no raise


def test_scan_bytes_strict_mode_fails_closed_without_clamav(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.delenv("CLAMAV_HOST", raising=False)
    monkeypatch.setenv("STRICT_AV_MODE", "true")
    from utils.malware_scan import scan_bytes
    try:
        _run(scan_bytes(b"%PDF-1.4 clean", "test.pdf"))
        raise AssertionError("expected HTTPException(503)")
    except HTTPException as exc:
        assert exc.status_code == 503
        assert "STRICT_AV_MODE" in exc.detail or "unavailable" in exc.detail.lower()
    monkeypatch.delenv("STRICT_AV_MODE")


# ── F-26 · SSRF guard ─────────────────────────────────────────────


def test_ssrf_rejects_non_http_schemes():
    from utils.ssrf_guard import is_safe_external_url
    for bad in ("ftp://x.com", "file:///etc/passwd", "gopher://x",
                "javascript:alert(1)", "data:text/html,x"):
        assert not is_safe_external_url(bad), f"should reject {bad!r}"


def test_ssrf_rejects_literal_private_ips():
    from utils.ssrf_guard import is_safe_external_url
    for bad in ("http://127.0.0.1/", "http://localhost/",
                "http://10.0.0.1/", "http://192.168.1.1/",
                "http://172.16.0.1/",
                "http://169.254.169.254/latest/meta-data/",
                "http://[::1]/", "http://[fe80::1]/"):
        assert not is_safe_external_url(bad), f"should reject {bad!r}"


def test_ssrf_rejects_metadata_hostnames():
    from utils.ssrf_guard import is_safe_external_url
    assert not is_safe_external_url("http://metadata.google.internal/")
    assert not is_safe_external_url("http://metadata/computeMetadata/v1/")


def test_ssrf_rejects_userinfo_urls():
    from utils.ssrf_guard import is_safe_external_url
    assert not is_safe_external_url("http://user:pass@example.com/")


def test_ssrf_rejects_garbage():
    from utils.ssrf_guard import is_safe_external_url
    assert not is_safe_external_url(None)
    assert not is_safe_external_url("")
    assert not is_safe_external_url("http:///")  # no host
    assert not is_safe_external_url("http://" + "x" * 3000)  # too long


def test_ssrf_allows_public_urls():
    """Stub DNS to return a public IP — guard should accept."""
    from utils import ssrf_guard
    with patch.object(ssrf_guard, "_resolve_all",
                      return_value=["93.184.216.34"]):  # example.com
        assert ssrf_guard.is_safe_external_url("https://example.com/path?q=1")


def test_ssrf_rejects_public_host_with_private_dns(monkeypatch):
    """DNS-rebind: hostname looks public but resolves to a private IP."""
    from utils import ssrf_guard
    with patch.object(ssrf_guard, "_resolve_all",
                      return_value=["10.0.0.5"]):
        assert not ssrf_guard.is_safe_external_url("https://rebind.example.com/")


def test_ssrf_assert_raises_ssrfblocked():
    from fastapi import HTTPException
    from utils.ssrf_guard import assert_safe_external_url, SSRFBlocked
    try:
        assert_safe_external_url("http://127.0.0.1/")
        raise AssertionError("expected SSRFBlocked")
    except SSRFBlocked as exc:
        assert exc.status_code == 400
        assert isinstance(exc, HTTPException)


# ── F-27 · secret_vault ────────────────────────────────────────────


def test_encrypt_value_returns_sentinel_dict():
    from utils.secret_vault import encrypt_value
    blob = encrypt_value("sk_live_abcdef")
    assert isinstance(blob, dict)
    assert blob["__enc"] == "v1"
    assert blob["data"] and blob["data"] != "sk_live_abcdef"


def test_encrypt_value_roundtrip_string():
    from utils.secret_vault import encrypt_value, decrypt_value
    plain = "sk_live_abcdef_long_token_123"
    blob = encrypt_value(plain)
    assert decrypt_value(blob) == plain


def test_encrypt_value_roundtrip_dict():
    from utils.secret_vault import encrypt_value, decrypt_value
    plain = {"username": "alice", "password": "p@ss", "scope": ["a", "b"]}
    blob = encrypt_value(plain)
    out = decrypt_value(blob)
    assert out == plain


def test_encrypt_value_idempotent_on_blob():
    from utils.secret_vault import encrypt_value
    once = encrypt_value("secret")
    twice = encrypt_value(once)
    assert twice == once  # no re-encrypt


def test_decrypt_value_returns_plain_unchanged():
    from utils.secret_vault import decrypt_value
    assert decrypt_value("not-a-blob") == "not-a-blob"
    assert decrypt_value(None) is None


def test_encrypt_secrets_in_dict_covers_default_fields():
    from utils.secret_vault import encrypt_secrets_in_dict
    doc = {
        "integration_id": "sicon",
        "enabled": True,
        "api_token": "sk_live_1",
        "webhook_secret": "whsec_1",
        "credentials": {"username": "u", "password": "p"},
        "base_url": "https://api.example.com",
    }
    out = encrypt_secrets_in_dict(doc)
    assert out is doc  # in-place
    assert isinstance(doc["api_token"], dict) and doc["api_token"]["__enc"] == "v1"
    assert isinstance(doc["webhook_secret"], dict) and doc["webhook_secret"]["__enc"] == "v1"
    assert isinstance(doc["credentials"], dict) and doc["credentials"]["__enc"] == "v1"
    # Non-secret fields untouched.
    assert doc["integration_id"] == "sicon"
    assert doc["enabled"] is True
    assert doc["base_url"] == "https://api.example.com"


def test_encrypt_then_decrypt_dict_roundtrip():
    from utils.secret_vault import (
        decrypt_secrets_in_dict,
        encrypt_secrets_in_dict,
    )
    original = {
        "api_token": "sk_live_xyz",
        "webhook_secret": "whsec_abc",
        "credentials": {"k": "v"},
        "non_secret": "kept",
    }
    enc = encrypt_secrets_in_dict(dict(original))
    dec = decrypt_secrets_in_dict(dict(enc))
    assert dec["api_token"] == "sk_live_xyz"
    assert dec["webhook_secret"] == "whsec_abc"
    assert dec["credentials"] == {"k": "v"}
    assert dec["non_secret"] == "kept"


def test_redact_secrets_in_dict_masks_values():
    from utils.secret_vault import encrypt_secrets_in_dict, redact_secrets_in_dict
    doc = {"api_token": "sk_live", "credentials": {"u": "v"}, "base_url": "x"}
    encrypt_secrets_in_dict(doc)
    redacted = redact_secrets_in_dict(doc)
    assert redacted["api_token"] == "••••••"
    assert redacted["credentials"] == "••••••"
    assert redacted["base_url"] == "x"  # non-secret unchanged
    # Original dict untouched.
    assert isinstance(doc["api_token"], dict)


def test_redact_masks_plain_secret_too():
    """If the field is still plaintext (legacy row), we still mask."""
    from utils.secret_vault import redact_secrets_in_dict
    doc = {"api_token": "sk_live_visible", "base_url": "x"}
    out = redact_secrets_in_dict(doc)
    assert out["api_token"] == "••••••"
    assert "sk_live_visible" not in str(out)


def test_redact_handles_empty_token():
    from utils.secret_vault import encrypt_secrets_in_dict, redact_secrets_in_dict
    doc = {"api_token": "", "base_url": "x"}
    encrypt_secrets_in_dict(doc)
    out = redact_secrets_in_dict(doc)
    # Empty token → masked to empty string, not the visible •••• mask.
    assert out["api_token"] == ""


# ── End-to-end smoke: integrations PUT encrypts on write ──────────


def test_update_integration_encrypts_api_token():
    """Smoke: ``update_integration`` writes encrypted blob to mongo."""
    import routes.integrations as ri

    captured = {}

    async def _fake_get_config(_):
        return {"integration_id": "sicon", "enabled": False}

    async def _fake_verify_admin(_):
        return True

    async def _fake_log(*_a, **_k):
        return None

    async def _fake_update_one(_filter, doc):
        captured["doc"] = doc
        return MagicMock(modified_count=1)

    async def _fake_audit_required(*_a, **_k):
        return None

    with patch.object(ri, "get_integration_config", _fake_get_config), \
         patch.object(ri, "verify_admin", _fake_verify_admin), \
         patch.object(ri, "log_integration_event", _fake_log), \
         patch.object(ri, "db") as mock_db, \
         patch("utils.security_plus.audit_required", _fake_audit_required):
        mock_db.integrations.update_one = _fake_update_one
        _run(ri.update_integration(
            integration_id="sicon",
            body={"api_token": "sk_plain_live", "webhook_secret": "whsec_plain"},
            user={"id": "admin", "email": "a@x.com"},
        ))
    set_doc = captured["doc"]["$set"]
    # Must NOT contain plaintext tokens.
    assert "sk_plain_live" not in str(set_doc)
    assert "whsec_plain" not in str(set_doc)
    # Must contain encrypted blobs in their place.
    assert isinstance(set_doc["api_token"], dict)
    assert set_doc["api_token"]["__enc"] == "v1"
    assert isinstance(set_doc["webhook_secret"], dict)
    assert set_doc["webhook_secret"]["__enc"] == "v1"
