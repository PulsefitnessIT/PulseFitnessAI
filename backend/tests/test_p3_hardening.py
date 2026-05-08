"""
P3 defence-in-depth regression tests: IP allowlist, MIME validation, password
rotation policy, PII retention purge, security manifest endpoint.
"""
import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
import requests
from fastapi import HTTPException, UploadFile

from tests.conftest import _test_backend_url, run_async as run

BASE = _test_backend_url()


# ─── IP allowlist middleware ─────────────────────────────────────

def test_ip_allowlist_parses_and_filters(monkeypatch):
    from utils import hardening
    monkeypatch.setenv("MASTER_ADMIN_IP_ALLOWLIST", "10.0.0.0/8, 203.0.113.5")
    nets = hardening._parse_allowlist()
    assert len(nets) == 2

    import ipaddress
    assert ipaddress.ip_address("10.1.2.3") in nets[0]
    assert ipaddress.ip_address("203.0.113.5") in nets[1]
    assert ipaddress.ip_address("8.8.8.8") not in nets[0]


def test_ip_allowlist_no_env_is_noop(monkeypatch):
    from utils import hardening
    monkeypatch.delenv("MASTER_ADMIN_IP_ALLOWLIST", raising=False)
    assert hardening._parse_allowlist() == []


def test_ip_allowlist_invalid_cidr_ignored(monkeypatch, caplog):
    from utils import hardening
    monkeypatch.setenv("MASTER_ADMIN_IP_ALLOWLIST", "not-an-ip, 10.0.0.0/8")
    nets = hardening._parse_allowlist()
    assert len(nets) == 1


# ─── Upload MIME / magic-byte validation ────────────────────────

def _fake_upload(name: str, data: bytes) -> UploadFile:
    buf = io.BytesIO(data)
    m = MagicMock(spec=UploadFile)
    m.filename = name
    async def _read():
        buf.seek(0)
        return buf.read()
    m.read = _read
    return m


def test_upload_validation_accepts_pdf():
    from utils.hardening import validate_upload_content_type
    pdf = b"%PDF-1.4\n%abc123"
    result = run(validate_upload_content_type(_fake_upload("invoice.pdf", pdf), allowed_categories=("pdf",)))
    assert result == pdf


def test_upload_validation_rejects_exe_extension():
    from utils.hardening import validate_upload_content_type
    with pytest.raises(HTTPException) as exc:
        run(validate_upload_content_type(_fake_upload("malware.exe", b"MZ\x90\x00"), allowed_categories=("pdf",)))
    assert exc.value.status_code == 400
    assert "not allowed" in exc.value.detail.lower()


def test_upload_validation_rejects_png_in_pdf_category():
    from utils.hardening import validate_upload_content_type
    png = b"\x89PNG\r\n\x1a\nabc"
    with pytest.raises(HTTPException) as exc:
        run(validate_upload_content_type(_fake_upload("cover.png", png), allowed_categories=("pdf",)))
    assert exc.value.status_code == 400


def test_upload_validation_rejects_empty_file():
    from utils.hardening import validate_upload_content_type
    with pytest.raises(HTTPException) as exc:
        run(validate_upload_content_type(_fake_upload("x.pdf", b""), allowed_categories=("pdf",)))
    assert exc.value.status_code == 400


# ─── Password policy ────────────────────────────────────────────

def test_password_needs_rotation_old(monkeypatch):
    monkeypatch.setenv("PASSWORD_MAX_AGE_DAYS", "180")
    from importlib import reload
    from utils import hardening as h
    reload(h)
    old = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    assert h.password_needs_rotation({"password_updated_at": old}) is True


def test_password_needs_rotation_fresh():
    from utils.hardening import password_needs_rotation
    fresh = datetime.now(timezone.utc).isoformat()
    assert password_needs_rotation({"password_updated_at": fresh}) is False


def test_password_needs_rotation_missing_timestamp():
    from utils.hardening import password_needs_rotation
    assert password_needs_rotation({}) is True


# ─── PII retention purge ────────────────────────────────────────

def test_pii_purge_deletes_long_archived_org():
    from utils.database import db
    from utils.hardening import purge_archived_orgs

    org_id = f"test-purge-{uuid.uuid4()}"
    ancient = (datetime.now(timezone.utc) - timedelta(days=800)).isoformat()

    async def _seed():
        await db.organizations.insert_one({"id": org_id, "name": "Old Gym", "archived_at": ancient})
        await db.users.insert_one({"id": f"u-{uuid.uuid4()}", "organization_id": org_id, "email": "ghost@x.com"})
        await db.equipment.insert_many([{"id": str(uuid.uuid4()), "organization_id": org_id} for _ in range(3)])

    async def _verify():
        assert await db.organizations.find_one({"id": org_id}) is None
        assert await db.equipment.count_documents({"organization_id": org_id}) == 0

    run(_seed())
    totals = run(purge_archived_orgs())
    assert totals["orgs_purged"] >= 1
    run(_verify())


def test_pii_purge_skips_fresh_archived_org():
    from utils.database import db
    from utils.hardening import purge_archived_orgs

    org_id = f"test-fresh-{uuid.uuid4()}"
    recent = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    async def _seed():
        await db.organizations.insert_one({"id": org_id, "name": "Recent Gym", "archived_at": recent})

    async def _verify_and_cleanup():
        assert await db.organizations.find_one({"id": org_id}) is not None
        await db.organizations.delete_one({"id": org_id})

    run(_seed())
    run(purge_archived_orgs())
    run(_verify_and_cleanup())


# ─── /api/security/manifest endpoint ─────────────────────────────

def test_security_manifest_is_public():
    r = requests.get(f"{BASE}/api/security/manifest", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "authentication" in body
    assert body["authentication"]["mfa"].startswith("TOTP")
    assert "audit" in body
    assert "events_tracked" in body["audit"]
    assert len(body["audit"]["events_tracked"]) >= 10


def test_security_manifest_reports_password_policy():
    r = requests.get(f"{BASE}/api/security/manifest", timeout=10)
    body = r.json()
    assert body["authentication"]["password_policy"]["min_length"] >= 8
    assert body["authentication"]["password_policy"]["max_age_days"] > 0


# ─── /auth/me surfaces password_needs_rotation ──────────────────

def test_auth_me_exposes_password_rotation_flag(pulse_pro_token):
    if not pulse_pro_token:
        return
    r = requests.get(
        f"{BASE}/api/auth/me",
        headers={"Authorization": f"Bearer {pulse_pro_token}"},
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert "password_needs_rotation" in body
    assert "password_max_age_days" in body
    assert isinstance(body["password_needs_rotation"], bool)
