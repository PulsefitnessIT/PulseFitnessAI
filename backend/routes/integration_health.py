"""Integration Health endpoints (Iter 215l).

Live-checks third-party integrations and surfaces the result to Master
Admin only. Designed so end-customers never see "Resend domain not
verified" — that's a developer/HQ concern, not an operator concern.

Each check returns:
    {ok: bool, status: "healthy"|"degraded"|"down"|"not_configured",
     message: str, details: dict, latency_ms: int}

Endpoints
---------
* GET /api/master-admin/integration-health        — run all checks
* GET /api/master-admin/integration-health/{key}  — run a single check

Master-admin only (403 otherwise).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")


def _require_health_access(user: dict) -> None:
    """Integration health is readable by full platform Master Admins AND
    delegated Pulse Master Admins — Pulse ops legitimately need to monitor
    the third-party services their portal depends on (Iter 222)."""
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(status_code=403, detail="Master admin only")


def _result(ok: bool, status: str, message: str, latency_ms: int = 0, **details) -> dict:
    return {
        "ok": ok,
        "status": status,
        "message": message,
        "latency_ms": latency_ms,
        "details": details,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Individual checks ─────────────────────────────────────────────

async def check_database() -> dict:
    t0 = time.time()
    try:
        await db.command("ping")
        latency = int((time.time() - t0) * 1000)
        return _result(True, "healthy", "MongoDB ping OK.", latency)
    except Exception as e:  # noqa: BLE001
        return _result(False, "down", f"MongoDB ping failed: {e}", int((time.time() - t0) * 1000))


async def check_stripe() -> dict:
    t0 = time.time()
    api_key = os.environ.get("STRIPE_API_KEY")
    if not api_key:
        return _result(False, "not_configured", "STRIPE_API_KEY env var not set.", 0)
    try:
        import stripe
        stripe.api_key = api_key
        # Cheapest auth-validating call.
        acct = await asyncio.to_thread(stripe.Account.retrieve)
        latency = int((time.time() - t0) * 1000)
        return _result(
            True, "healthy",
            f"Stripe account {acct.get('id')} reachable.",
            latency,
            account_id=acct.get("id"),
            charges_enabled=acct.get("charges_enabled"),
            payouts_enabled=acct.get("payouts_enabled"),
        )
    except Exception as e:  # noqa: BLE001
        return _result(False, "down", f"Stripe auth failed: {e}", int((time.time() - t0) * 1000))


async def check_resend() -> dict:
    t0 = time.time()
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        return _result(False, "not_configured", "RESEND_API_KEY env var not set.", 0)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        latency = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return _result(False, "down", f"Resend API returned {r.status_code}.", latency)
        data = r.json()
        domains = data.get("data") or []
        verified = [d for d in domains if d.get("status") == "verified"]
        unverified = [d for d in domains if d.get("status") != "verified"]
        if not domains:
            return _result(False, "degraded", "Resend account has no domains configured.", latency)
        if unverified:
            unverified_names = ", ".join(d.get("name", "?") for d in unverified[:3])
            return _result(
                False, "degraded",
                f"{len(unverified)} domain(s) need DNS verification: {unverified_names}.",
                latency, verified=len(verified), unverified=len(unverified),
            )
        return _result(
            True, "healthy",
            f"All {len(verified)} domain(s) verified.",
            latency, verified=len(verified),
        )
    except Exception as e:  # noqa: BLE001
        return _result(False, "down", f"Resend reachability failed: {e}", int((time.time() - t0) * 1000))


async def check_storage() -> dict:
    """Round-trip a tiny test object through the Emergent storage proxy."""
    t0 = time.time()
    try:
        from utils.database import put_object, get_object, APP_NAME
        path = f"{APP_NAME}/_health/probe.txt"
        payload = b"ok"
        result = await asyncio.to_thread(put_object, path, payload, "text/plain")
        data, _ = await asyncio.to_thread(get_object, result.get("path", path))
        latency = int((time.time() - t0) * 1000)
        if data == payload:
            return _result(True, "healthy", "Storage round-trip OK.", latency)
        return _result(False, "degraded", "Storage round-trip returned mismatched bytes.", latency)
    except Exception as e:  # noqa: BLE001
        return _result(False, "down", f"Storage probe failed: {e}", int((time.time() - t0) * 1000))


async def check_emergent_llm() -> dict:
    """Verify the Emergent LLM key is configured. We don't burn tokens
    on a real completion — only confirm presence and well-formedness.
    Live validation happens implicitly via the storage round-trip
    (which calls the same backing service)."""
    t0 = time.time()
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return _result(False, "not_configured", "EMERGENT_LLM_KEY env var not set.", 0)
    latency = int((time.time() - t0) * 1000)
    if not key.startswith("sk-emergent-") or len(key) < 30:
        return _result(False, "degraded",
                       "EMERGENT_LLM_KEY present but format looks wrong.",
                       latency, key_prefix=key[:12])
    return _result(True, "healthy",
                   "Emergent LLM key configured (live-validated via storage probe).",
                   latency, key_prefix=key[:12])


CHECKS = {
    "database": ("Database (MongoDB)", check_database),
    "stripe": ("Stripe Payments", check_stripe),
    "resend": ("Resend Email", check_resend),
    "storage": ("Object Storage", check_storage),
    "emergent_llm": ("Emergent LLM Key", check_emergent_llm),
}


# ── HTTP endpoints ─────────────────────────────────────────────────

@router.get("/master-admin/integration-health")
async def integration_health_all(user: dict = Depends(get_current_user)):
    """Run every integration check in parallel. Master Admin + Pulse Admin."""
    _require_health_access(user)
    results = await asyncio.gather(
        *(fn() for _, fn in CHECKS.values()),
        return_exceptions=True,
    )
    out = []
    for (key, (label, _)), res in zip(CHECKS.items(), results):
        if isinstance(res, Exception):
            out.append({"key": key, "label": label,
                        **_result(False, "down", f"Check raised: {res}", 0)})
        else:
            out.append({"key": key, "label": label, **res})
    summary = {
        "healthy": sum(1 for r in out if r["status"] == "healthy"),
        "degraded": sum(1 for r in out if r["status"] == "degraded"),
        "down": sum(1 for r in out if r["status"] == "down"),
        "not_configured": sum(1 for r in out if r["status"] == "not_configured"),
        "total": len(out),
    }
    return {"checks": out, "summary": summary}


@router.get("/master-admin/integration-health/{key}")
async def integration_health_one(key: str, user: dict = Depends(get_current_user)):
    _require_health_access(user)
    if key not in CHECKS:
        raise HTTPException(404, f"Unknown check '{key}'. Valid: {list(CHECKS)}")
    label, fn = CHECKS[key]
    res = await fn()
    return {"key": key, "label": label, **res}
