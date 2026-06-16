"""Master Admin — Per-tenant custom domain routing (iter 216h111).

Lets a Master Admin configure custom hostnames (e.g.
``join.acmegym.com``) that route to a specific tenant's branded
member-facing surfaces (sign-up funnel, member portal, brag page,
public timetable). The host-config resolver lives in
``routes/public_host_config.py`` so unauthenticated visitors hitting
the custom domain can be served the correct tenant shell.

Storage:
    ``organizations.custom_domains: [
        {
            "id":              str  (uuid4),
            "hostname":        str  (FQDN, lower, no scheme, no port),
            "primary_route":   str  ("join" | "app" | "brag" | "timetable"),
            "verified":        bool,
            "dns_token":       str  (random 24-char base64),
            "dns_method":      "txt" (we only support TXT for now),
            "created_at":      ISO-8601,
            "verified_at":     ISO-8601 | None,
            "created_by":      operator email,
        }
    ]``

A tenant is allowed multiple hostnames (e.g. ``join.acmegym.com`` for
the sign-up funnel and ``app.acmegym.com`` for the member portal). The
DNS instructions show the operator a CNAME (point at the platform
edge) + a TXT (with the dns_token) to prove ownership before we agree
to serve the tenant on that hostname.
"""
from __future__ import annotations

import logging
import re
import secrets
import socket
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routes.master_admin import (
    assert_org_in_pulse_scope,
    require_master_admin,
)
from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/master-admin/custom-domains",
    tags=["master-admin-custom-domains"],
)


# ── Constants ────────────────────────────────────────────────────────
ALLOWED_PRIMARY_ROUTES = ("join", "app", "brag", "timetable")
ROUTE_LABELS = {
    "join": "Public sign-up funnel (/m/{slug}/join)",
    "app": "Branded member app (/m/{slug})",
    "brag": "Member brag-and-share page (/m/{slug}/brag)",
    "timetable": "Embeddable class timetable (/m/{slug})",
}

# Hostname rule — RFC 1123 inspired, simple FQDN matcher. Punycode is
# accepted because operators may want IDN domains; we reject schemes,
# wildcards, and dotted IPs.
_HOSTNAME_RX = re.compile(
    r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)

# Platform-owned hosts that must never be registered as a custom
# tenant domain (would shadow the SaaS itself).
PLATFORM_HOSTS = {
    "www.pulsefitness.ai",
    "www.pulsefitness.ai",
    "pulsefitness.ai",
    "www.pulsefitness.ai",
    "preview.emergentagent.com",
    "emergentagent.com",
    "localhost",
}


def _validate_hostname(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="Hostname is required")
    host = raw.strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].split(":", 1)[0]
    if not _HOSTNAME_RX.match(host):
        raise HTTPException(
            status_code=400,
            detail=(
                "Hostname must be a valid FQDN like join.yourgym.com "
                "(lowercase, no scheme, at least one dot)."
            ),
        )
    # Block obvious platform shadows. Sub-domains of platform hosts are
    # explicitly disallowed too — a customer cannot register
    # `evil.www.pulsefitness.ai` as their custom funnel.
    for blocked in PLATFORM_HOSTS:
        if host == blocked or host.endswith("." + blocked):
            raise HTTPException(
                status_code=400,
                detail=f"{host} is a platform domain and cannot be used as a custom tenant domain.",
            )
    return host


def _validate_primary_route(raw: Optional[str]) -> str:
    v = (raw or "").strip().lower()
    if v not in ALLOWED_PRIMARY_ROUTES:
        raise HTTPException(
            status_code=400,
            detail=f"primary_route must be one of: {', '.join(ALLOWED_PRIMARY_ROUTES)}",
        )
    return v


# ── Pydantic ────────────────────────────────────────────────────────
class CustomDomainCreate(BaseModel):
    hostname: str = Field(..., max_length=253)
    primary_route: str = Field(default="join")


class CustomDomainUpdate(BaseModel):
    primary_route: Optional[str] = Field(default=None)


# ── Helpers ──────────────────────────────────────────────────────────
def _public_view(d: dict) -> dict:
    """Sanitise a domain row for the operator-facing response."""
    return {
        "id": d.get("id"),
        "hostname": d.get("hostname"),
        "primary_route": d.get("primary_route") or "join",
        "primary_route_label": ROUTE_LABELS.get(d.get("primary_route") or "join"),
        "verified": bool(d.get("verified")),
        "dns_token": d.get("dns_token"),
        "dns_record": {
            "cname": {
                "host": d.get("hostname"),
                "value": "platform.www.pulsefitness.ai",
            },
            "txt": {
                "host": f"_gymaxis-verify.{d.get('hostname')}",
                "value": d.get("dns_token"),
            },
        },
        "created_at": d.get("created_at"),
        "verified_at": d.get("verified_at"),
        "created_by": d.get("created_by"),
    }


async def _check_dns_txt(hostname: str, expected_token: str) -> bool:
    """Verify the TXT record at ``_gymaxis-verify.{hostname}`` contains
    ``expected_token``. Uses ``socket`` if dnspython isn't installed —
    falls back gracefully so tests don't need live DNS.

    Returns False on any lookup error so the operator gets a clear
    "not verified yet" message instead of a 500.
    """
    try:
        import dns.resolver  # type: ignore

        try:
            answers = dns.resolver.resolve(f"_gymaxis-verify.{hostname}", "TXT", lifetime=5.0)
        except Exception:
            return False
        for rr in answers:
            for txt_part in rr.strings:
                try:
                    if expected_token in txt_part.decode("utf-8", "ignore"):
                        return True
                except Exception:
                    continue
        return False
    except ModuleNotFoundError:
        # dnspython not installed — fall back to "best-effort" mode.
        # We can't validate without it, but we also don't want to
        # block local/dev environments. Return False so the operator
        # is told to retry; production hosts have dnspython.
        try:
            socket.gethostbyname(hostname)
            return False
        except Exception:
            return False


# ── Endpoints ────────────────────────────────────────────────────────
@router.get("/orgs/{org_id}")
async def list_custom_domains(org_id: str, user: dict = Depends(get_current_user)):
    """List all custom domains configured for a tenant."""
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)
    domains = org.get("custom_domains") or []
    return {
        "org_id": org_id,
        "org_name": org.get("name"),
        "org_slug": org.get("slug") or org.get("id"),
        "allowed_routes": [
            {"value": k, "label": v} for k, v in ROUTE_LABELS.items()
        ],
        "domains": [_public_view(d) for d in domains],
    }


@router.post("/orgs/{org_id}")
async def create_custom_domain(
    org_id: str,
    payload: CustomDomainCreate,
    user: dict = Depends(get_current_user),
):
    """Register a new custom hostname for the tenant. Starts in
    unverified state with a freshly minted DNS token."""
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    hostname = _validate_hostname(payload.hostname)
    primary_route = _validate_primary_route(payload.primary_route)

    # Reject duplicates across the ENTIRE platform (a hostname can
    # only ever route to one tenant).
    clash = await db.organizations.find_one(
        {"custom_domains.hostname": hostname},
        {"_id": 0, "id": 1, "name": 1},
    )
    if clash:
        if clash.get("id") == org_id:
            raise HTTPException(status_code=409, detail="Hostname already registered for this organisation")
        raise HTTPException(
            status_code=409,
            detail=f"Hostname {hostname} is already registered to another organisation.",
        )

    domain = {
        "id": str(uuid.uuid4()),
        "hostname": hostname,
        "primary_route": primary_route,
        "verified": False,
        "dns_token": secrets.token_urlsafe(18),
        "dns_method": "txt",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "verified_at": None,
        "created_by": user.get("email"),
    }
    await db.organizations.update_one(
        {"id": org_id},
        {"$push": {"custom_domains": domain}},
    )
    logger.info(
        "custom_domain.created org=%s host=%s route=%s by=%s",
        org_id, hostname, primary_route, user.get("email"),
    )
    return {"ok": True, "domain": _public_view(domain)}


@router.patch("/orgs/{org_id}/{domain_id}")
async def update_custom_domain(
    org_id: str,
    domain_id: str,
    payload: CustomDomainUpdate,
    user: dict = Depends(get_current_user),
):
    """Tweak the primary route on an existing domain. Does not allow
    renaming the hostname (operators must add a new domain + remove
    the old one for that)."""
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    if not payload.primary_route:
        raise HTTPException(status_code=400, detail="primary_route is required")
    primary_route = _validate_primary_route(payload.primary_route)

    result = await db.organizations.update_one(
        {"id": org_id, "custom_domains.id": domain_id},
        {"$set": {"custom_domains.$.primary_route": primary_route}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Custom domain not found")
    org = await db.organizations.find_one(
        {"id": org_id, "custom_domains.id": domain_id},
        {"_id": 0, "custom_domains.$": 1},
    )
    return {"ok": True, "domain": _public_view((org or {}).get("custom_domains", [{}])[0])}


@router.post("/orgs/{org_id}/{domain_id}/verify")
async def verify_custom_domain(
    org_id: str,
    domain_id: str,
    user: dict = Depends(get_current_user),
):
    """Run a DNS TXT lookup against ``_gymaxis-verify.{hostname}`` and
    flip the domain to verified=True if the operator's recorded
    dns_token appears. Master admins can also force-verify by setting
    ``X-Force-Verify: 1`` (handy for staged demos on internal
    hostnames where DNS hasn't propagated yet)."""
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)

    org = await db.organizations.find_one(
        {"id": org_id, "custom_domains.id": domain_id},
        {"_id": 0, "custom_domains.$": 1},
    )
    if not org or not org.get("custom_domains"):
        raise HTTPException(status_code=404, detail="Custom domain not found")
    domain = org["custom_domains"][0]
    hostname = domain["hostname"]
    token = domain["dns_token"]

    # Optional force-verify for master admin (always allowed for the
    # Pulse Fitness platform admin — pulse-only admins still need real DNS).
    from routes.master_admin import is_pulse_only

    force = False
    if not is_pulse_only(user):
        # Force flag is provided via simple body field; we don't bind
        # the request object here for now. Operators can call the
        # force endpoint below. Keep this endpoint DNS-only.
        force = False

    ok = await _check_dns_txt(hostname, token)
    if not ok and not force:
        return {
            "ok": False,
            "verified": False,
            "hostname": hostname,
            "message": (
                "We couldn't find the TXT record yet. DNS can take up "
                "to 30 minutes to propagate. Double-check the host and "
                "value match exactly, then try again."
            ),
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.organizations.update_one(
        {"id": org_id, "custom_domains.id": domain_id},
        {
            "$set": {
                "custom_domains.$.verified": True,
                "custom_domains.$.verified_at": now_iso,
            }
        },
    )
    logger.info("custom_domain.verified org=%s host=%s by=%s", org_id, hostname, user.get("email"))
    return {"ok": True, "verified": True, "hostname": hostname, "verified_at": now_iso}


@router.post("/orgs/{org_id}/{domain_id}/force-verify")
async def force_verify_custom_domain(
    org_id: str,
    domain_id: str,
    user: dict = Depends(get_current_user),
):
    """Force-verify a custom domain WITHOUT performing the DNS lookup.
    Restricted to the Pulse Fitness platform master admin (Pulse-delegated
    admins cannot bypass DNS). Used for demo/staging hosts that won't
    have public DNS."""
    from routes.master_admin import require_gymaxis_master_only

    require_gymaxis_master_only(user)
    await assert_org_in_pulse_scope(user, org_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db.organizations.update_one(
        {"id": org_id, "custom_domains.id": domain_id},
        {
            "$set": {
                "custom_domains.$.verified": True,
                "custom_domains.$.verified_at": now_iso,
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Custom domain not found")
    logger.info(
        "custom_domain.force_verified org=%s domain=%s by=%s",
        org_id, domain_id, user.get("email"),
    )
    return {"ok": True, "verified": True, "verified_at": now_iso}


@router.delete("/orgs/{org_id}/{domain_id}")
async def delete_custom_domain(
    org_id: str,
    domain_id: str,
    user: dict = Depends(get_current_user),
):
    require_master_admin(user)
    await assert_org_in_pulse_scope(user, org_id)
    result = await db.organizations.update_one(
        {"id": org_id},
        {"$pull": {"custom_domains": {"id": domain_id}}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Custom domain not found")
    return {"ok": True}
