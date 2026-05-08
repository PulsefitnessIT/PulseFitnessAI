"""
TOTP-based Multi-Factor Authentication (RFC 6238).

Used to gate master-admin logins and, optionally, any role marked
`mfa_required` on the user doc. Secrets are encrypted at rest with Fernet
(key read from ``MFA_ENCRYPTION_KEY`` — auto-derived from ``JWT_SECRET``
when not set so dev environments still work).

Flow:
  1. POST /auth/mfa/setup       → returns provisioning URI + QR PNG (one-shot)
  2. POST /auth/mfa/enable      → verifies first code, flips `mfa_enabled=true`,
                                  returns 10 backup codes (shown once)
  3. POST /auth/login           → if user has MFA → returns ``temp_token`` +
                                  ``requires_mfa: true`` instead of full JWT
  4. POST /auth/mfa/verify      → accepts temp_token + 6-digit code; returns
                                  full JWT on success. Replay-protected via
                                  ``mfa_used_codes`` collection.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from utils.database import db

logger = logging.getLogger(__name__)

ISSUER_NAME = os.environ.get("MFA_ISSUER_NAME", "GymAxis AI")
BACKUP_CODE_COUNT = 10
TOTP_WINDOW = 1  # ±30 s clock skew tolerance


def _load_fernet() -> Fernet:
    """Return a Fernet instance.

    Uses ``MFA_ENCRYPTION_KEY`` when present; otherwise derives a key
    deterministically from ``JWT_SECRET`` so existing encrypted secrets keep
    decrypting across restarts in dev. Setting ``MFA_ENCRYPTION_KEY`` in prod
    is mandatory for key-rotation support.
    """
    key = os.environ.get("MFA_ENCRYPTION_KEY", "").strip()
    if not key:
        jwt_secret = os.environ.get("JWT_SECRET", "").strip()
        if not jwt_secret:
            # Fail loudly — never fall back to a predictable key in any
            # environment. Missing secrets must be surfaced, not silently
            # replaced, or an attacker can decrypt MFA blobs.
            raise RuntimeError(
                "MFA_ENCRYPTION_KEY (or JWT_SECRET fallback) must be set "
                "in the environment to initialise MFA encryption.",
            )
        derived = hashlib.sha256(jwt_secret.encode()).digest()
        key = base64.urlsafe_b64encode(derived).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(secret: str) -> str:
    return _load_fernet().encrypt(secret.encode()).decode()


def decrypt_secret(blob: str) -> str:
    try:
        return _load_fernet().decrypt(blob.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        logger.error(f"[mfa] secret decryption failed: {exc}")
        raise HTTPException(status_code=500, detail="MFA secret is corrupt; re-enrol required")


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER_NAME)


def qrcode_png_bytes(uri: str) -> bytes:
    qr = qrcode.QRCode(version=1, box_size=8, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def verify_code(secret: str, code: str) -> bool:
    if not code or len(code) != 6 or not code.isdigit():
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=TOTP_WINDOW)


def generate_backup_codes() -> tuple[list[str], list[str]]:
    """Return ``(plain_codes, hashed_codes)``. Plain codes shown once to user."""
    plain: list[str] = []
    hashed: list[str] = []
    for _ in range(BACKUP_CODE_COUNT):
        code = secrets.token_hex(4).upper()  # 8-char hex, human-typable
        plain.append(code)
        hashed.append(bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode())
    return plain, hashed


def check_backup_code(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ─── Replay-attack prevention ───────────────────────────────────

async def mark_code_used(user_id: str, code: str) -> None:
    """Record a successfully-verified TOTP code. TTL-swept by Mongo after 120 s."""
    await db.mfa_used_codes.update_one(
        {"user_id": user_id, "code_hash": hashlib.sha256(code.encode()).hexdigest()},
        {"$set": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def is_code_replayed(user_id: str, code: str) -> bool:
    row = await db.mfa_used_codes.find_one(
        {"user_id": user_id, "code_hash": hashlib.sha256(code.encode()).hexdigest()},
        {"_id": 0, "user_id": 1},
    )
    return row is not None


async def ensure_mfa_indexes() -> None:
    try:
        await db.mfa_used_codes.create_index("created_at", expireAfterSeconds=120)
        await db.mfa_used_codes.create_index([("user_id", 1), ("code_hash", 1)], unique=True)
    except Exception as e:
        logger.warning(f"[mfa] index creation failed: {e}")


# ─── Enrollment / state helpers ─────────────────────────────────

async def user_mfa_state(user_id: str) -> dict:
    """Return {enabled, enrolled_at, backup_codes_remaining}."""
    doc = await db.user_mfa.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return {"enabled": False, "enrolled_at": None, "backup_codes_remaining": 0}
    remaining = sum(1 for c in (doc.get("backup_codes") or []) if not c.get("used"))
    return {
        "enabled": bool(doc.get("enabled")),
        "enrolled_at": doc.get("enrolled_at"),
        "backup_codes_remaining": remaining,
    }


async def begin_enrollment(user_id: str, email: str) -> dict:
    """Persist a draft secret and return the provisioning URI plus an inline
    base64 QR code (data URI) so the frontend can render it directly with no
    second authenticated request.
    """
    secret = generate_secret()
    await db.user_mfa.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "draft_secret_encrypted": encrypt_secret(secret),
            "draft_created_at": datetime.now(timezone.utc).isoformat(),
            "enabled": False,  # not yet confirmed
        }},
        upsert=True,
    )
    uri = provisioning_uri(secret, email)
    png = qrcode_png_bytes(uri)
    qr_data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return {"provisioning_uri": uri, "secret": secret, "qrcode_data_url": qr_data_url}


async def confirm_enrollment(user_id: str, code: str) -> list[str]:
    """Verify the first code, promote draft→live, return plain backup codes."""
    doc = await db.user_mfa.find_one({"user_id": user_id}, {"_id": 0})
    if not doc or not doc.get("draft_secret_encrypted"):
        raise HTTPException(status_code=400, detail="MFA enrolment not started")
    draft = doc["draft_secret_encrypted"]
    # Draft older than 15 min → expired
    draft_ts = doc.get("draft_created_at", "")
    try:
        if draft_ts and datetime.fromisoformat(draft_ts.replace("Z", "+00:00")) < \
                datetime.now(timezone.utc) - timedelta(minutes=15):
            raise HTTPException(status_code=400, detail="Enrolment session expired. Start over.")
    except ValueError:
        pass
    secret = decrypt_secret(draft)
    if not verify_code(secret, code):
        raise HTTPException(status_code=400, detail="Invalid code. Try again.")
    plain, hashed = generate_backup_codes()
    now = datetime.now(timezone.utc).isoformat()
    await db.user_mfa.update_one(
        {"user_id": user_id},
        {"$set": {
            "enabled": True,
            "secret_encrypted": draft,
            "enrolled_at": now,
            "backup_codes": [{"hash": h, "used": False} for h in hashed],
            "draft_secret_encrypted": None,
            "draft_created_at": None,
        }},
    )
    return plain


async def disable_mfa(user_id: str) -> None:
    await db.user_mfa.update_one(
        {"user_id": user_id},
        {"$set": {
            "enabled": False,
            "secret_encrypted": None,
            "backup_codes": [],
            "disabled_at": datetime.now(timezone.utc).isoformat(),
        }},
    )


async def verify_login_code(user_id: str, code: str) -> bool:
    """Verify a TOTP or backup code during login. Handles replay + backup marking."""
    doc = await db.user_mfa.find_one({"user_id": user_id}, {"_id": 0})
    if not doc or not doc.get("enabled"):
        raise HTTPException(status_code=400, detail="MFA not enabled for this account")
    # 1. Try TOTP
    if doc.get("secret_encrypted"):
        if await is_code_replayed(user_id, code):
            raise HTTPException(status_code=400, detail="Code already used. Wait for next interval.")
        secret = decrypt_secret(doc["secret_encrypted"])
        if verify_code(secret, code):
            await mark_code_used(user_id, code)
            return True
    # 2. Try backup codes
    backups = doc.get("backup_codes") or []
    for idx, b in enumerate(backups):
        if b.get("used"):
            continue
        if check_backup_code(code, b["hash"]):
            backups[idx]["used"] = True
            backups[idx]["used_at"] = datetime.now(timezone.utc).isoformat()
            await db.user_mfa.update_one(
                {"user_id": user_id},
                {"$set": {"backup_codes": backups}},
            )
            return True
    return False


# ─── Policy helpers ──────────────────────────────────────────────

def user_requires_mfa(user: dict) -> bool:
    """Return True if the user's role/flag demands MFA on login.

    Master admins ALWAYS require MFA once enabled. Other roles opt-in via
    ``mfa_required: true`` on the user doc.
    """
    if user.get("is_master_admin"):
        return True
    return bool(user.get("mfa_required"))
