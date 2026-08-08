"""
Defence-in-depth hardening helpers (P3, Feb 2026).

- ``master_admin_ip_allowlist``: env-gated middleware that blocks access to any
  route prefixed ``/api/master-admin`` unless the caller's IP matches
  ``MASTER_ADMIN_IP_ALLOWLIST`` (comma-separated CIDR or bare IPs).
- ``validate_upload_content_type``: magic-byte sniffing for file uploads
  (covers the common attack: uploading a .exe disguised as .pdf).
- ``password_needs_rotation``: true when a user's password is older than the
  ``PASSWORD_MAX_AGE_DAYS`` policy.
- ``purge_archived_orgs``: nightly job that deletes orgs archived more than
  ``PII_RETENTION_DAYS`` ago, along with their users/equipment/issues.
"""
from __future__ import annotations

import ipaddress
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, UploadFile

from utils.database import db

logger = logging.getLogger(__name__)

PASSWORD_MAX_AGE_DAYS = int(os.environ.get("PASSWORD_MAX_AGE_DAYS", "180"))
PII_RETENTION_DAYS = int(os.environ.get("PII_RETENTION_DAYS", "365"))


# ─── IP allowlist for master-admin routes ────────────────────────

def _parse_allowlist() -> list:
    raw = (os.environ.get("MASTER_ADMIN_IP_ALLOWLIST", "") or "").strip()
    if not raw:
        return []
    nets: list = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            logger.warning(f"[ip-allowlist] ignoring invalid CIDR/IP: {part}")
    return nets


def _extract_client_ip(request: Request) -> Optional[str]:
    # SEC-002 — use the spoof-resistant derivation (reads X-Forwarded-For from
    # the RIGHT, skipping trusted proxy hops) so the master-admin IP allow-list
    # can't be bypassed by a forged left-most X-Forwarded-For.
    try:
        from utils.security import client_ip
        ip = client_ip(request)
        if ip and ip != "unknown":
            return ip
    except Exception:
        pass
    return request.client.host if request.client else None


async def master_admin_ip_allowlist(request: Request, call_next):
    """Middleware: when MASTER_ADMIN_IP_ALLOWLIST is set, /api/master-admin/*
    traffic is restricted to those networks. No env var → no-op (dev friendly)."""
    path = request.url.path
    if path.startswith("/api/master-admin/"):
        nets = _parse_allowlist()
        if nets:
            ip_str = _extract_client_ip(request) or ""
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                ip = None
            ok = bool(ip) and any(ip in n for n in nets)
            if not ok:
                logger.warning(f"[ip-allowlist] blocked master-admin access from {ip_str} on {path}")
                return _blocked_response(ip_str)
    return await call_next(request)


def _blocked_response(ip_str: str):
    from starlette.responses import JSONResponse
    return JSONResponse(
        status_code=403,
        content={"detail": f"Access denied for IP {ip_str}"},
    )


# ─── File upload MIME / magic-byte validation ────────────────────

_MAGIC: dict[bytes, str] = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"%PDF-": "application/pdf",
    b"PK\x03\x04": "application/zip",  # also docx/xlsx
    b"\x1f\x8b\x08": "application/gzip",
    b"RIFF": "audio/wav-or-webp",  # RIFF cover
    b"\x00\x00\x00\x18ftyp": "video/mp4",
    b"\x00\x00\x00\x1cftyp": "video/mp4",
}

_BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".ps1", ".msi", ".dll", ".jar", ".vbs", ".scr"}


async def validate_upload_content_type(file: UploadFile, allowed_categories: tuple[str, ...] = ("image", "pdf", "doc", "zip")) -> bytes:
    """Read the first 12 bytes, detect type, and reject mismatches or blocked
    extensions. Returns the fully-read bytes so the caller doesn't double-read.

    ``allowed_categories`` — high-level filter: ``image`` allows png/jpeg/gif,
    ``pdf`` allows PDFs, ``doc`` allows PDF/zip (docx/xlsx are zips), ``zip``
    allows raw ZIP archives.
    """
    filename = (file.filename or "").lower()
    ext = os.path.splitext(filename)[1]
    if ext in _BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Upload type {ext} is not allowed")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Magic-byte sniff
    header = data[:16]
    detected: Optional[str] = None
    for sig, mime in _MAGIC.items():
        if header.startswith(sig):
            detected = mime
            break

    # For text-like categories we don't need magic bytes (CSV, TXT)
    if detected is None and ext in (".txt", ".csv", ".md", ".json"):
        return data
    if detected is None:
        raise HTTPException(status_code=400, detail=f"Could not identify upload type for {filename}")

    if not _category_allows(detected, allowed_categories):
        raise HTTPException(
            status_code=400,
            detail=f"File type {detected} is not permitted for this upload",
        )
    # Final defence: ClamAV scan (no-op when daemon not configured).
    from utils.malware_scan import scan_bytes
    await scan_bytes(data, filename)
    return data


def _category_allows(detected: str, categories: tuple[str, ...]) -> bool:
    if "image" in categories and detected.startswith("image/"):
        return True
    if "pdf" in categories and detected == "application/pdf":
        return True
    if "doc" in categories and detected in ("application/pdf", "application/zip"):
        return True
    if "zip" in categories and detected == "application/zip":
        return True
    return bool("video" in categories and detected.startswith("video/"))


# ─── Password policy ─────────────────────────────────────────────

def password_needs_rotation(user: dict) -> bool:
    """Return True if the user's password is older than the policy window."""
    ts = user.get("password_updated_at") or user.get("created_at")
    if not ts:
        return True
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return True
    return (datetime.now(timezone.utc) - dt) > timedelta(days=PASSWORD_MAX_AGE_DAYS)


# ─── PII retention — purge archived orgs ─────────────────────────

_PURGE_COLLECTIONS = (
    "users", "equipment", "issues", "files", "supplier_cases", "notifications",
    "ppm_schedules", "ppm_tasks", "trust_events", "support_sessions",
    "support_messages", "integration_bridge", "sicon_engineers", "sicon_appointments",
    "mfa_used_codes", "user_mfa",
)


async def purge_archived_orgs() -> dict:
    """Delete orgs archived > PII_RETENTION_DAYS ago, plus their dependent rows.

    Idempotent + safe to run every poll cycle. Only targets orgs where
    ``archived_at`` is a populated timestamp older than the retention window.
    Returns a summary for logging.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PII_RETENTION_DAYS)).isoformat()
    expired = await db.organizations.find(
        {"archived_at": {"$lt": cutoff, "$ne": None, "$type": "string"}},
        {"_id": 0, "id": 1, "name": 1, "archived_at": 1},
    ).to_list(200)
    if not expired:
        return {"orgs_purged": 0, "rows_deleted": 0}

    total_rows = 0
    for org in expired:
        oid = org["id"]
        for coll in _PURGE_COLLECTIONS:
            try:
                r = await db[coll].delete_many({"organization_id": oid})
                total_rows += r.deleted_count
            except Exception as exc:
                logger.warning(f"[pii-purge] {coll} for {oid} failed: {exc}")
        # Also scrub master-admin audit log entries referring to this org
        try:
            await db.security_audit_log.update_many(
                {"org_id": oid},
                {"$set": {"org_id": "__purged__", "pii_purged_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception as exc:
            logger.warning(f"[pii-purge] audit scrub for {oid} failed: {exc}")
        await db.organizations.delete_one({"id": oid})
        logger.info(f"[pii-purge] deleted org {oid} ({org.get('name')}) archived {org.get('archived_at')}")

    try:
        from utils.security_plus import audit_required
        await audit_required("security_audit_log", {
            "event": "pii.retention.purged",
            "orgs": [o["id"] for o in expired],
            "rows_deleted": total_rows,
        })
    except Exception:
        pass
    return {"orgs_purged": len(expired), "rows_deleted": total_rows}
