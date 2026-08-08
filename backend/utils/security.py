"""Security utilities: rate limiting, input sanitisation, password validation."""
import os
import time
import re
import html
from collections import defaultdict
from fastapi import HTTPException, Request


def _trusted_proxy_hops() -> int:
    """Number of TRUSTED reverse-proxy hops that append to X-Forwarded-For
    AFTER the real client's address. Measured for this platform: Cloudflare
    + GCP load-balancer = 2 (the K8s ingress passes through without adding a
    3rd). Overridable via env for other deployments."""
    try:
        return max(0, int(os.environ.get("TRUSTED_PROXY_HOPS", "2")))
    except ValueError:
        return 2


def client_ip(request: Request) -> str:
    """Spoof-resistant real-client-IP extraction (SEC-002).

    The chain is: client → Cloudflare → GCP LB → K8s ingress → FastAPI. Each
    TRUSTED proxy APPENDS the peer it saw to the RIGHT of X-Forwarded-For, so
    the last ``TRUSTED_PROXY_HOPS`` entries are infra-controlled and the real
    client sits immediately to their left (index ``-(hops+1)``). Anything a
    client injects lands further LEFT and is therefore ignored — you cannot
    forge your position past the fixed number of trusted appenders.

    (The old code returned the LEFT-most XFF value, which is fully
    attacker-controlled — the spoofing hole this fixes.)
    """
    hops = _trusted_proxy_hops()
    xff = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if parts:
        idx = len(parts) - 1 - hops
        if idx >= 0:
            return parts[idx]
        # Fewer entries than the expected trusted chain → not behind the full
        # proxy stack (local/dev or an internal call). No trusted appender was
        # bypassed, so the left-most is the best (and non-forgeable-here) value.
        return parts[0]
    # No XFF at all (direct/local): fall back to X-Real-IP then the socket peer.
    xri = request.headers.get("x-real-ip", "").strip()
    if xri:
        return xri
    return request.client.host if request.client else "unknown"


def _client_ip(request: Request) -> str:
    """Backwards-compatible alias — delegates to the spoof-resistant
    :func:`client_ip`."""
    return client_ip(request)

# ── Rate Limiter (MongoDB-backed, shared across pods & restarts) ──────
#
# Rate-limit + account-lockout state used to live in per-process dicts, so a
# restart wiped every counter and each pod enforced its OWN allowance (N pods
# = N× the limit, and an attacker throttled on one pod was free on the next).
# We now persist to the shared `rate_buckets` collection in MongoDB (same store
# the async middleware limiter uses), so limits are global and durable.
#
# These functions keep their original SYNCHRONOUS signatures — callers (auth
# routes etc.) are unchanged — backed by a dedicated lazy pymongo client. The
# ops are single indexed upserts on low-QPS auth paths, and they FAIL OPEN
# (logged) if the store is briefly unreachable so a DB blip never causes a
# total auth outage.

import logging as _logging
from datetime import datetime, timezone

_rl_logger = _logging.getLogger(__name__)
_RATE_COLLECTION = "rate_buckets"
_sync_client = None
_sync_col = None
_sync_col_failed = False


def _rl_col():
    """Lazy sync handle to the shared rate-limit collection. Returns None (and
    the limiter fails open) if Mongo is unreachable. Constructed lazily on
    first use — never at import — so an Atlas SRV DNS lookup can't hang boot."""
    global _sync_client, _sync_col, _sync_col_failed
    if _sync_col is not None:
        return _sync_col
    if _sync_col_failed:
        return None
    try:
        from pymongo import MongoClient
        url = os.environ["MONGO_URL"]
        name = os.environ["DB_NAME"]
        _sync_client = MongoClient(url, serverSelectionTimeoutMS=1500, connectTimeoutMS=1500)
        _sync_col = _sync_client[name][_RATE_COLLECTION]
        try:
            # TTL sweeps abandoned buckets (BSON-date `updated_at`) after 24h.
            _sync_col.create_index("updated_at", expireAfterSeconds=24 * 3600)
        except Exception:
            pass
        return _sync_col
    except Exception as e:
        _sync_col_failed = True
        _rl_logger.warning("[rate-limit] shared store unavailable, failing OPEN: %s", e)
        return None


def _sliding_window_hit(key: str, max_requests: int, window_seconds: int) -> None:
    """Atomic Mongo sliding-window check. Raises 429 if `key` has already had
    `max_requests` hits inside the last `window_seconds`; otherwise records
    this hit. Fails open if the store is down."""
    col = _rl_col()
    if col is None:
        return
    now = time.time()
    cutoff = now - window_seconds
    try:
        from pymongo import ReturnDocument
        doc = col.find_one_and_update(
            {"_id": key},
            {"$pull": {"hits": {"$lt": cutoff}},
             "$set": {"window_seconds": window_seconds, "updated_at": datetime.now(timezone.utc)}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )
        hits = [h for h in (doc.get("hits") or []) if h >= cutoff]
        if len(hits) >= max_requests:
            oldest = min(hits)
            retry_after = max(1, int(oldest + window_seconds - now))
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
        col.update_one({"_id": key}, {"$push": {"hits": now}})
    except HTTPException:
        raise
    except Exception as e:
        _rl_logger.warning("[rate-limit] store error on %r, failing OPEN: %s", key, e)


def rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    """Check rate limit. Raises 429 if exceeded. (Mongo-backed, shared.)"""
    _sliding_window_hit(key, max_requests, window_seconds)


def rate_limit_by_ip(request: Request, max_requests: int = 10, window_seconds: int = 60) -> None:
    """Rate limit by client IP."""
    ip = _client_ip(request)
    rate_limit(f"ip:{ip}", max_requests, window_seconds)


def rate_limit_login(request: Request) -> None:
    """Strict rate limit for login: 5 attempts per 5 minutes per IP.

    Limits are overridable via `LOGIN_RATE_LIMIT_MAX` / `LOGIN_RATE_LIMIT_WINDOW`
    env vars so test runs (which legitimately make many login calls from one IP)
    can raise the ceiling without loosening production defaults.

    Internal CI/test runs may also pass `X-RateLimit-Bypass: <secret>` (secret
    is `RATE_LIMIT_BYPASS_SECRET` from backend .env) to skip the limiter. The
    secret is never exposed to the frontend so an external attacker cannot use it.
    """
    bypass = os.environ.get("RATE_LIMIT_BYPASS_SECRET", "").strip()
    if bypass and request.headers.get("x-ratelimit-bypass", "") == bypass:
        return
    ip = _client_ip(request)
    max_req = int(os.environ.get("LOGIN_RATE_LIMIT_MAX", "5"))
    window = int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW", "300"))
    rate_limit(f"login:{ip}", max_requests=max_req, window_seconds=window)


def rate_limit_password_reset(request: Request) -> None:
    """Rate limit password reset: 3 per 15 minutes per IP."""
    ip = _client_ip(request)
    rate_limit(f"reset:{ip}", max_requests=3, window_seconds=900)


# ── Account Lockout (MongoDB-backed, shared across pods & restarts) ───
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = 900  # 15 minutes


def check_account_lockout(email: str) -> None:
    """Check if account is locked due to failed attempts (shared store)."""
    col = _rl_col()
    if col is None:
        return
    try:
        doc = col.find_one({"_id": f"lock:{email.lower()}"})
    except Exception as e:
        _rl_logger.warning("[lockout] read failed OPEN: %s", e)
        return
    if not doc:
        return
    until = doc.get("lock_until", 0)
    now = time.time()
    if until > now:
        remaining = int(until - now)
        raise HTTPException(
            status_code=429,
            detail=f"Account temporarily locked. Try again in {max(1, remaining // 60)} minutes.",
        )


def record_failed_login(email: str) -> None:
    """Record a failed login attempt. Locks the account (in the shared store)
    once the threshold is reached inside the window."""
    col = _rl_col()
    if col is None:
        return
    email_lower = email.lower()
    now = time.time()
    cutoff = now - LOCKOUT_DURATION
    try:
        from pymongo import ReturnDocument
        doc = col.find_one_and_update(
            {"_id": f"faillogin:{email_lower}"},
            {"$pull": {"hits": {"$lt": cutoff}},
             "$set": {"updated_at": datetime.now(timezone.utc)}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )
        col.update_one({"_id": f"faillogin:{email_lower}"}, {"$push": {"hits": now}})
        count = len([h for h in (doc.get("hits") or []) if h >= cutoff]) + 1
        if count >= LOCKOUT_THRESHOLD:
            col.update_one(
                {"_id": f"lock:{email_lower}"},
                {"$set": {"lock_until": now + LOCKOUT_DURATION,
                          "updated_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
    except Exception as e:
        _rl_logger.warning("[lockout] record failed OPEN: %s", e)


def clear_failed_logins(email: str) -> None:
    """Clear failed-login counter + lock on successful login / manual unlock."""
    col = _rl_col()
    if col is None:
        return
    email_lower = email.lower()
    try:
        col.delete_many({"_id": {"$in": [f"faillogin:{email_lower}", f"lock:{email_lower}"]}})
    except Exception as e:
        _rl_logger.warning("[lockout] clear failed: %s", e)


def clear_login_rate_limits() -> None:
    """Flush every per-IP login rate-limit bucket. Used by the Master Admin
    "unlock" action so a manually-unlocked user isn't immediately blocked
    again by the IP rate limiter from their earlier burst of attempts."""
    col = _rl_col()
    if col is None:
        return
    try:
        col.delete_many({"_id": {"$regex": r"^(login|ip):"}})
    except Exception as e:
        _rl_logger.warning("[rate-limit] flush failed: %s", e)


def get_failed_login_count(email: str) -> int:
    """Return the number of failed login attempts currently in the window."""
    col = _rl_col()
    if col is None:
        return 0
    try:
        doc = col.find_one({"_id": f"faillogin:{email.lower()}"})
        if not doc:
            return 0
        cutoff = time.time() - LOCKOUT_DURATION
        return len([h for h in (doc.get("hits") or []) if h >= cutoff])
    except Exception:
        return 0


# ── Password Strength ─────────────────────────────────────────────

PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", "12"))

# Small local blocklist of the most common breached/weak passwords. Cheap,
# deterministic, no external dependency (a full HIBP k-anonymity check can be
# layered on later behind PASSWORD_HIBP_CHECK without changing callers).
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "passw0rd", "123456", "1234567",
    "12345678", "123456789", "1234567890", "qwerty", "qwerty123", "111111",
    "letmein", "welcome", "welcome1", "admin", "admin123", "iloveyou",
    "monkey", "dragon", "football", "abc123", "111111111", "000000",
    "changeme", "pulsefitness", "pulse123", "gymaxis", "sunshine", "master",
}


def validate_password_strength(password: str) -> None:
    """Enforce minimum password requirements. Raises 400 if weak.

    Policy (hardened): >= PASSWORD_MIN_LENGTH (default 12) chars, upper + lower
    + digit + symbol, and not a well-known breached/common password.
    """
    errors = []
    if len(password or "") < PASSWORD_MIN_LENGTH:
        errors.append(f"at least {PASSWORD_MIN_LENGTH} characters")
    if not re.search(r"[A-Z]", password or ""):
        errors.append("one uppercase letter")
    if not re.search(r"[a-z]", password or ""):
        errors.append("one lowercase letter")
    if not re.search(r"\d", password or ""):
        errors.append("one number")
    if not re.search(r"[^A-Za-z0-9]", password or ""):
        errors.append("one symbol")

    if errors:
        raise HTTPException(
            status_code=400,
            detail=f"Password must contain {', '.join(errors)}.",
        )

    # Reject known-breached / trivially-guessable passwords.
    normalised = re.sub(r"[^a-z0-9]", "", (password or "").lower())
    if normalised in _COMMON_PASSWORDS or (password or "").lower() in _COMMON_PASSWORDS:
        raise HTTPException(
            status_code=400,
            detail="This password is too common or has appeared in a data breach. Please choose a stronger, unique password.",
        )


# Live breached-password check via the HaveIBeenPwned k-anonymity range API.
# Privacy-safe: only the first 5 chars of the SHA-1 hash ever leave the server.
# Fail-OPEN: if the check is disabled or the API is unreachable we allow the
# password (the local policy above still applies) so HIBP downtime never blocks
# a legitimate user. Enable/disable with PASSWORD_HIBP_CHECK (default: enabled).
PASSWORD_HIBP_CHECK = os.environ.get("PASSWORD_HIBP_CHECK", "true").lower() in ("1", "true", "yes")


async def assert_password_not_breached(password: str) -> None:
    """Raise 400 if the password appears in the HIBP breach corpus.

    Safe to call after validate_password_strength() in async endpoints.
    Silently returns (fail-open) when disabled or on any network/timeout error.
    """
    if not PASSWORD_HIBP_CHECK or not password:
        return
    import hashlib
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.5) as client:
            resp = await client.get(
                f"https://api.pwnedpasswords.com/range/{prefix}",
                headers={"Add-Padding": "true"},
            )
        if resp.status_code != 200:
            return  # fail-open
        for line in resp.text.splitlines():
            parts = line.strip().split(":")
            if len(parts) == 2 and parts[0].upper() == suffix and parts[1].strip() not in ("", "0"):
                raise HTTPException(
                    status_code=400,
                    detail="This password has appeared in a known data breach. Please choose a different, unique password.",
                )
    except HTTPException:
        raise
    except Exception:
        return  # network/timeout — fail-open, local policy still enforced


# ── Input Sanitisation (XSS prevention) ──────────────────────────
#
# React already escapes text inside ``{value}`` JSX expressions, so
# server-side HTML-entity encoding is *redundant* and corrupts the data
# the user sees ("they're" → "they&#x27;re"). Instead we strip the
# characters that could let user input *break out* of the text node into
# raw HTML — ``<`` and ``>``. Anything that does end up rendered through
# ``dangerouslySetInnerHTML`` (rare, audit-only) must be sanitised at the
# render boundary, not here.
import re as _re

_TAG_OPENER = _re.compile(r"[<>]")


def sanitise_string(value: str) -> str:
    """Strip HTML tag delimiters from user-supplied text.

    Returns the input unchanged apart from ``<`` and ``>`` removal and
    control-character normalisation. Apostrophes, quotes and ampersands
    are preserved so the frontend renders them as the user typed them.
    """
    if not value:
        return value
    # Decode any pre-existing entity encoding from older data so we
    # converge on plain text everywhere.
    value = html.unescape(value)
    # Drop NULL bytes / DEL — they have no business in text.
    value = value.replace("\x00", "").replace("\x7f", "")
    # Strip tag delimiters (defence-in-depth — React would escape anyway).
    return _TAG_OPENER.sub("", value)


def sanitise_dict(data: dict, fields: list[str] | None = None) -> dict:
    """Sanitise string fields in a dictionary."""
    result = dict(data)
    sanitise_all = not fields
    for key, value in result.items():
        if isinstance(value, str) and (sanitise_all or key in fields):
            result[key] = sanitise_string(value)
    return result
