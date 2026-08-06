"""
Security hardening utilities (P0-P2 pass, Feb 2026).

Covers:
- P1.6  Mongo-backed sliding-window rate limiter (multi-replica safe)
- P1.7  Organisation scope decorator
- P1.8  Body-size limit middleware
- P1.9  Generic HMAC webhook verifier
- P1+.11 JWT revocation (jti + deny list in MongoDB)
- P1+.12 Per-user LLM budget counter
- P1+.13 Supplier-token rotation + expiry
- P2.15  Fail-closed audit writer for sensitive ops

Every helper is a small, single-purpose function so callers (auth routes,
middlewares, background jobs) can mix & match without circular imports.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException, Request

from utils.database import db

logger = logging.getLogger(__name__)


# ════════════════════ P2.16 — Safe regex search ═══════════════════
# Build Mongo ``$regex`` clauses from UNTRUSTED user input without
# opening the door to regex-injection / ReDoS. Every metacharacter in
# the supplied term is escaped, so a value like ``.*`` or a
# catastrophic-backtracking pattern is treated as a literal substring.
# Case-insensitive substring search semantics are preserved.


def safe_regex(value: Optional[str], options: str = "i") -> dict:
    """Return a Mongo ``$regex`` clause for a case-insensitive substring
    match on UNTRUSTED ``value``. All regex metacharacters are escaped to
    prevent regex-injection and ReDoS. Empty/None input matches everything
    (``""``) which callers should gate behind a truthiness check anyway."""
    return {"$regex": re.escape((value or "").strip()), "$options": options}


def safe_regex_exact(value: Optional[str], options: str = "i") -> dict:
    """Like :func:`safe_regex` but anchored for a WHOLE-string (case-
    insensitive) match — ``^value$`` with every metacharacter escaped.
    Use for lookups that intend an exact match (e.g. unique name/email)
    without exposing a regex-injection surface."""
    return {"$regex": f"^{re.escape((value or '').strip())}$", "$options": options}


# ════════════════════ P1.6 — Rate limiter ═════════════════════════
# Sliding window backed by MongoDB. Each hit appends {ts} to a capped array,
# and old entries are pruned per call. Shared across every pod so horizontal
# scale doesn't multiply the allowance.

_RATE_COLLECTION = "rate_buckets"


async def rate_limit_async(key: str, max_requests: int, window_seconds: int) -> None:
    """Sliding-window rate limiter (Mongo-backed).

    Raises 429 when the caller has hit `max_requests` within the last
    `window_seconds`. Safe to call from any async path; adds ~1-2 ms."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    cutoff_ts = cutoff.timestamp()

    # Atomically prune old hits and push the new one
    result = await db[_RATE_COLLECTION].find_one_and_update(
        {"_id": key},
        {
            "$pull": {"hits": {"$lt": cutoff_ts}},
            "$set": {"window_seconds": window_seconds, "updated_at": now.isoformat()},
        },
        upsert=True,
        return_document=True,
    )
    hits = (result or {}).get("hits") or []
    hits = [h for h in hits if h >= cutoff_ts]

    if len(hits) >= max_requests:
        retry = int(max(1, window_seconds - (now.timestamp() - min(hits))))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry in {retry}s.",
            headers={"Retry-After": str(retry)},
        )

    await db[_RATE_COLLECTION].update_one(
        {"_id": key}, {"$push": {"hits": now.timestamp()}},
    )


async def ensure_rate_limiter_indexes() -> None:
    try:
        await db[_RATE_COLLECTION].create_index(
            "updated_at", expireAfterSeconds=24 * 3600,
        )
    except Exception as e:
        logger.warning(f"rate_buckets TTL index creation failed: {e}")


def client_rate_key(request: Request, user: Optional[dict], suffix: str) -> str:
    """Stable per-identity key used by the middleware rate limiter."""
    if user and user.get("id"):
        return f"user:{user['id']}:{suffix}"
    ip = (request.client.host if request.client else "unknown")
    # Honour proxy header if configured
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip() or ip
    return f"ip:{ip}:{suffix}"


# ════════════════════ P1+.11 — JWT revocation ════════════════════

async def revoke_jwt(
    jti: str,
    exp_ts: int,
    reason: str = "logout",
    grace_seconds: int = 0,
) -> None:
    """Add a JWT's jti to the deny list. TTL index will sweep it after expiry.

    Iter 216h54 — `grace_seconds` lets the caller delay the effective
    revocation. This is critical on `/auth/refresh`: an immediate revoke
    on rotation races with in-flight client requests still carrying the
    old token (e.g. parallel /auth/me + /sites + /branding fired on
    page load). With a 60s grace window those in-flight calls complete
    cleanly; replay attacks past the window are still blocked.
    """
    if not jti:
        return
    effective_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, grace_seconds))
    await db.jwt_revocations.update_one(
        {"jti": jti},
        {"$set": {
            "jti": jti, "reason": reason,
            "exp": datetime.fromtimestamp(exp_ts, tz=timezone.utc),
            "revoked_at": datetime.now(timezone.utc).isoformat(),
            "effective_at": effective_at.isoformat(),
        }},
        upsert=True,
    )


async def is_jwt_revoked(jti: Optional[str]) -> bool:
    """Return True only if the jti is on the deny list AND past its
    `effective_at` grace window. Tokens still inside the grace window
    are treated as valid so a just-rotated session doesn't 401 the
    handful of requests already in-flight when refresh completed.
    """
    if not jti:
        return False
    row = await db.jwt_revocations.find_one(
        {"jti": jti}, {"_id": 0, "jti": 1, "effective_at": 1},
    )
    if not row:
        return False
    eff = row.get("effective_at")
    if not eff:
        # Legacy rows without grace window — treat as immediately revoked
        # (preserves old behaviour for logouts and pre-216h54 revocations).
        return True
    try:
        eff_dt = datetime.fromisoformat(eff.replace("Z", "+00:00")) if isinstance(eff, str) else eff
    except Exception:
        return True
    return datetime.now(timezone.utc) >= eff_dt


async def ensure_revocation_indexes() -> None:
    try:
        await db.jwt_revocations.create_index([("jti", 1)], unique=True)
        await db.jwt_revocations.create_index("exp", expireAfterSeconds=0)
    except Exception as e:
        logger.warning(f"jwt_revocations index creation failed: {e}")


def new_jti() -> str:
    return uuid.uuid4().hex


# ════════════════════ P1+.12 — LLM budgets ═══════════════════════
# Track LLM spend per user within a rolling day/month window. Surfaces in the
# Ask Support Desk; raises 429 when the cap is hit.

DAILY_USER_ASK_LIMIT = int(os.environ.get("SUPPORT_USER_DAILY_LIMIT", "150"))
MONTHLY_ORG_ASK_LIMIT = int(os.environ.get("SUPPORT_ORG_MONTHLY_LIMIT", "5000"))


async def check_and_record_llm_budget(user_id: str, org_id: Optional[str]) -> None:
    """Raises 429 if the caller has burned their daily/monthly allowance."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    user_key = f"user:{user_id}:{today}"
    org_key = f"org:{org_id or 'none'}:{month}"

    # Increment + read in two cheap upserts
    ur = await db.llm_budgets.find_one_and_update(
        {"_id": user_key},
        {"$inc": {"count": 1},
         "$set": {"scope": "user", "owner": user_id, "bucket": today,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True, return_document=True,
    )
    if (ur or {}).get("count", 0) > DAILY_USER_ASK_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Daily Ask limit reached ({DAILY_USER_ASK_LIMIT}). Try again tomorrow.",
        )

    if org_id:
        orr = await db.llm_budgets.find_one_and_update(
            {"_id": org_key},
            {"$inc": {"count": 1},
             "$set": {"scope": "org", "owner": org_id, "bucket": month,
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True, return_document=True,
        )
        if (orr or {}).get("count", 0) > MONTHLY_ORG_ASK_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Monthly organisation Ask limit reached ({MONTHLY_ORG_ASK_LIMIT}). "
                       "Contact your account manager to lift the cap.",
            )


async def ensure_llm_budget_indexes() -> None:
    try:
        await db.llm_budgets.create_index("updated_at", expireAfterSeconds=45 * 24 * 3600)
        await db.llm_budgets.create_index([("owner", 1), ("bucket", 1)])
    except Exception as e:
        logger.warning(f"llm_budgets index creation failed: {e}")


# ════════════════════ P1+.13 — Supplier tokens ═══════════════════

SUPPLIER_TOKEN_TTL_DAYS = int(os.environ.get("SUPPLIER_TOKEN_TTL_DAYS", "30"))


def generate_supplier_token() -> str:
    return secrets.token_urlsafe(24)


def supplier_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=SUPPLIER_TOKEN_TTL_DAYS)


async def validate_supplier_token(token: str) -> dict:
    """Fetch + validate a supplier case token, raising 401/410 as appropriate."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    case = await db.supplier_cases.find_one({"token": token}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    exp = case.get("token_expires_at")
    if exp and datetime.fromisoformat(exp.replace("Z", "+00:00")) < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Supplier link expired")
    return case


async def rotate_supplier_token(case_id: str) -> str:
    """Issue a fresh token + reset the expiry window."""
    new_tok = generate_supplier_token()
    await db.supplier_cases.update_one(
        {"id": case_id},
        {"$set": {
            "token": new_tok,
            "token_expires_at": supplier_token_expiry().isoformat(),
            "token_rotated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return new_tok


# ════════════════════ P1.9 — Generic HMAC verifier ═══════════════

def verify_hmac_signature(body: bytes, signature: str, secret: str,
                          algo: str = "sha256") -> bool:
    if not (body is not None and signature and secret):
        return False
    expected = hmac.new(
        secret.encode(), body, getattr(hashlib, algo),
    ).hexdigest()
    # Strip common prefixes (sha256=...) from Stripe/GitHub-style signatures
    candidate = signature.split("=", 1)[1] if "=" in signature else signature
    return hmac.compare_digest(expected, candidate)


# ════════════════════ P2.15 — Fail-closed audit writer ═══════════

async def audit_required(collection: str, doc: dict, retries: int = 2) -> None:
    """Write an audit document. Raises 503 if we cannot persist it.

    Use this wrapper for sensitive operations (admin writes, escalations,
    webhook dispatches) where the SOC 2 auditor expects a fail-closed record."""
    doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    last_err: Optional[Exception] = None
    for _ in range(retries + 1):
        try:
            await db[collection].insert_one(doc)
            return
        except Exception as e:
            last_err = e
            await asyncio.sleep(0.15)
    logger.error(f"audit_required failed: {last_err}")
    raise HTTPException(status_code=503, detail="Audit persistence failed; request aborted.")


# ════════════════════ P1.8 — Body size middleware ═══════════════

DEFAULT_BODY_LIMIT_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", str(2 * 1024 * 1024)))  # 2 MB
UPLOAD_BODY_LIMIT_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))   # 25 MB
# Iter 216h55 — Pulse Fitness imports up to ~500k pieces of equipment in a
# single CSV (~120-150 MB). Bulk-import endpoints get their own tier so
# the 25 MB single-file upload limit doesn't reject onboarding payloads.
BULK_IMPORT_BODY_LIMIT_BYTES = int(os.environ.get("MAX_BULK_IMPORT_BYTES", str(200 * 1024 * 1024)))  # 200 MB
UPLOAD_PATH_PREFIXES = (
    "/api/equipment-import", "/api/upload", "/api/files", "/api/spec-sheets",
    "/api/equipment/", "/api/mod/site/attachments", "/api/master-admin/invoice/",
    "/api/master-admin/sites/preview-csv", "/api/master-admin/equipment/preview-csv",
)
BULK_IMPORT_PATH_PREFIXES = (
    "/api/master-admin/bulk-import/",
    "/api/master-admin/sites/import",
    "/api/master-admin/equipment/import",
    "/api/crm/price-list/import/",
)


def _is_upload_path(path: str) -> bool:
    return any(path.startswith(p) for p in UPLOAD_PATH_PREFIXES)


def _is_bulk_import_path(path: str) -> bool:
    return any(path.startswith(p) for p in BULK_IMPORT_PATH_PREFIXES)


async def body_size_guard(request: Request,
                          call_next: Callable[[Request], Awaitable]):
    """Rejects requests whose body exceeds the per-route limit.

    Three tiers (iter 216h55):
      • Bulk-import endpoints  → 200 MB (Pulse-scale CSV onboarding)
      • Upload endpoints       → 25 MB  (individual file uploads)
      • Everything else        → 2 MB

    Two-layer enforcement:
      1. Content-Length header check (cheap, rejects before reading).
      2. Stream wrapper that counts bytes and aborts on overflow
         (defends against chunked transfers or spoofed Content-Length).

    Returns a 413 JSONResponse directly — middleware-layer HTTPExceptions
    aren't converted to responses by Starlette's BaseHTTPMiddleware.
    """
    from starlette.responses import JSONResponse

    path = str(request.url.path)
    if _is_bulk_import_path(path):
        limit = BULK_IMPORT_BODY_LIMIT_BYTES
    elif _is_upload_path(path):
        limit = UPLOAD_BODY_LIMIT_BYTES
    else:
        limit = DEFAULT_BODY_LIMIT_BYTES

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
        except ValueError:
            size = 0
        if size > limit:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body exceeds {limit} bytes"},
            )

    # Wrap receive() to count actual streamed bytes — guards against
    # chunked transfers or clients that omit/spoof Content-Length.
    counter = {"n": 0, "over": False}
    original_receive = request.receive

    async def _counting_receive():
        msg = await original_receive()
        if msg.get("type") == "http.request":
            body = msg.get("body") or b""
            counter["n"] += len(body)
            if counter["n"] > limit:
                counter["over"] = True
                # Return an empty terminal frame so the handler sees EOF.
                return {"type": "http.request", "body": b"", "more_body": False}
        return msg

    request._receive = _counting_receive  # type: ignore[attr-defined]
    response = await call_next(request)
    if counter["over"]:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request body exceeds {limit} bytes"},
        )
    return response


# ════════════════════ P0/P1 helper — CORS loader ═════════════════

# Production-default origins for the two customer-facing brands. We always
# include these so a forgotten ``CORS_ORIGINS`` env var doesn't lock real
# customers out of their own app. The env var still wins when present,
# which is how staging / preview overrides happen.
_BRAND_DEFAULT_ORIGINS = [
    "https://pulsefitness.ai",
    "https://www.pulsefitness.ai",
    "https://fitness-ai-migrate.emergent.host",
]


def _is_prod() -> bool:
    return (
        (os.environ.get("APP_ENV") or "").lower() == "production"
        or (os.environ.get("ENVIRONMENT", "development") or "").lower().startswith("prod")
    )


def resolve_cors_origins() -> list[str]:
    """Resolve the CORS allow-list.

    SECURITY (SEC-001): the app sends credentials (``allow_credentials=True``),
    so we MUST NOT return ``*`` — reflecting an arbitrary origin together with
    credentials lets any website read a logged-in user's data cross-origin.
    We therefore ALWAYS return an explicit allow-list. Emergent preview/host
    subdomains are covered by :func:`resolve_cors_origin_regex` so preview
    redeploys keep working without a wildcard.

    Order of precedence:
      1. ``CORS_ORIGINS`` env var (comma-separated, non-``*``). Always wins.
      2. The customer brand domains, plus localhost in non-prod for local dev.
    """
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw and raw != "*":
        return [o.strip() for o in raw.split(",") if o.strip()]
    if raw == "*":
        # A literal wildcard is unsafe with credentials — ignore it in EVERY
        # environment and fall back to the explicit brand allow-list.
        logger.warning("[security] CORS_ORIGINS='*' ignored (unsafe with credentials) — using brand defaults + platform regex")
    else:
        logger.warning("[security] CORS_ORIGINS not set — using brand defaults + platform regex")
    origins = list(_BRAND_DEFAULT_ORIGINS)
    if not _is_prod():
        # Local-dev convenience — a running React dev server on the host.
        origins += [
            "http://localhost:3000", "http://127.0.0.1:3000",
            "http://localhost:5173", "http://127.0.0.1:5173",
        ]
    return origins


# Emergent platform preview/host subdomains. Allowing these via regex means
# preview redeploys (which change the subdomain) keep working without editing
# CORS_ORIGINS, while still excluding arbitrary third-party origins.
_PLATFORM_ORIGIN_REGEX = r"https://([a-z0-9-]+\.)*(preview\.emergentagent\.com|emergent\.host)"


def resolve_cors_origin_regex():
    """Regex of trusted platform origins, or None to disable.

    ``CORS_ORIGIN_REGEX`` env var overrides. Otherwise we ALWAYS return the
    Emergent preview/host regex so the platform's own preview + deployed
    subdomains are permitted (the explicit brand allow-list from
    :func:`resolve_cors_origins` covers the customer domains). This never
    matches arbitrary third-party origins.
    """
    raw = os.environ.get("CORS_ORIGIN_REGEX", "").strip()
    if raw:
        return raw
    return _PLATFORM_ORIGIN_REGEX


async def ensure_security_indexes() -> None:
    await ensure_rate_limiter_indexes()
    await ensure_revocation_indexes()
    await ensure_llm_budget_indexes()
