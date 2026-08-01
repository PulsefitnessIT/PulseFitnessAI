"""Security utilities: rate limiting, input sanitisation, password validation."""
import os
import time
import re
import html
from collections import defaultdict
from fastapi import HTTPException, Request


def _client_ip(request: Request) -> str:
    """Best-effort real-client-IP extraction behind a reverse proxy (CF → K8s ingress → FastAPI).

    Prefers the left-most value of X-Forwarded-For, then X-Real-IP, then the
    direct client host. Essential so rate limits aren't bypassed by traffic
    being load-balanced across ingress pods (each showing a different
    internal IP to FastAPI).
    """
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip", "").strip()
    if xri:
        return xri
    return request.client.host if request.client else "unknown"

# ── Rate Limiter (in-memory, per-IP) ──────────────────────────────

_rate_store: dict[str, list[float]] = defaultdict(list)


def rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    """Check rate limit. Raises 429 if exceeded."""
    now = time.time()
    cutoff = now - window_seconds

    # Clean old entries
    _rate_store[key] = [t for t in _rate_store[key] if t > cutoff]

    if len(_rate_store[key]) >= max_requests:
        # Compute when the oldest request in the window will expire, so the
        # Retry-After header is accurate (not just the full window).
        oldest = _rate_store[key][0]
        retry_after = max(1, int(oldest + window_seconds - now))
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Please try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    _rate_store[key].append(now)


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


# ── Account Lockout ───────────────────────────────────────────────

_failed_logins: dict[str, list[float]] = defaultdict(list)
_locked_accounts: dict[str, float] = {}
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = 900  # 15 minutes


def check_account_lockout(email: str) -> None:
    """Check if account is locked due to failed attempts."""
    email_lower = email.lower()
    if email_lower in _locked_accounts:
        lock_time = _locked_accounts[email_lower]
        if time.time() - lock_time < LOCKOUT_DURATION:
            remaining = int(LOCKOUT_DURATION - (time.time() - lock_time))
            raise HTTPException(
                status_code=429,
                detail=f"Account temporarily locked. Try again in {remaining // 60} minutes.",
            )
        else:
            del _locked_accounts[email_lower]
            _failed_logins[email_lower] = []


def record_failed_login(email: str) -> None:
    """Record a failed login attempt. Locks account after threshold."""
    email_lower = email.lower()
    now = time.time()
    _failed_logins[email_lower] = [t for t in _failed_logins[email_lower] if t > now - LOCKOUT_DURATION]
    _failed_logins[email_lower].append(now)

    if len(_failed_logins[email_lower]) >= LOCKOUT_THRESHOLD:
        _locked_accounts[email_lower] = now


def clear_failed_logins(email: str) -> None:
    """Clear failed login counter on successful login."""
    email_lower = email.lower()
    _failed_logins.pop(email_lower, None)
    _locked_accounts.pop(email_lower, None)


def clear_login_rate_limits() -> None:
    """Flush every per-IP login rate-limit bucket. Used by the Master Admin
    "unlock" action so a manually-unlocked user isn't immediately blocked
    again by the IP rate limiter from their earlier burst of attempts."""
    for key in list(_rate_store.keys()):
        if key.startswith("login:") or key.startswith("ip:"):
            _rate_store.pop(key, None)


def get_failed_login_count(email: str) -> int:
    """Return the number of failed login attempts currently in the window."""
    return len(_failed_logins.get(email.lower(), []))


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
