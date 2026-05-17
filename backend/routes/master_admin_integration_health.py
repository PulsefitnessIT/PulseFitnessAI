"""
Master Admin · Org integration health sub-router.

Iter 216h184 — Extracted from `routes/master_admin.py` as phase 8 of
the 4,283 LoC → focused-routers decomposition.

Owns the integration-health surface — used by the Organisations drawer
Integrations tab + the platform-wide Integrations Hub page:

    POST /master-admin/organizations/{org_id}/verify-mappings
    GET  /master-admin/organizations/{org_id}/integration-health
    GET  /master-admin/integrations-hub

Two private helpers travel with the routes:
    _check_code_collision  — duplicate-code guard across orgs
    _integration_status    — platform-level Sicon / Orbit 4 status block

Shared helpers (`assert_org_in_pulse_scope`, `is_pulse_only`,
`require_master_admin`) stay on `routes.master_admin` because they're
used by ~12 modules.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends

from utils.auth import get_current_user
from utils.database import db
from routes.master_admin import (
    assert_org_in_pulse_scope,
    is_pulse_only,
    require_master_admin,
)


router = APIRouter()


# ───────────── private helpers ─────────────

async def _check_code_collision(code: str, fields: list[str], exclude_org_id: str) -> Optional[dict]:
    """Return ``{org_id, name}`` for any OTHER org in our DB sharing this code
    on any of ``fields``. Empty/whitespace codes are skipped."""
    if not (code and code.strip()):
        return None
    norm = code.strip()
    other = await db.organizations.find_one(
        {
            "id": {"$ne": exclude_org_id},
            "$or": [{f: norm} for f in fields],
        },
        {"_id": 0, "id": 1, "name": 1},
    )
    return other if other else None


async def _integration_status(integration_id: str) -> dict:
    """Return ``{status: "configured"|"not_configured", configured: bool}`` for
    the platform-level Sicon / Orbit 4 integration row."""
    cfg = await db.integration_configs.find_one(
        {"id": integration_id}, {"_id": 0, "configured": 1, "connection_status": 1, "last_verified_at": 1},
    )
    if not cfg or not cfg.get("configured"):
        return {"status": "not_configured", "configured": False}
    return {
        "status": "configured",
        "configured": True,
        "connection_status": cfg.get("connection_status", "unknown"),
        "last_verified_at": cfg.get("last_verified_at"),
    }


# ───────────── routes ─────────────

@router.post("/master-admin/organizations/{org_id}/verify-mappings")
async def verify_org_mappings(
    org_id: str,
    body: dict = Body(default={}),
    user: dict = Depends(get_current_user),
):
    """Sanity-check the tenant identifier codes (`customer_account_number`,
    `sage_customer_number`, `sicon_customer_number`) for an org.

    Returns one block per field with:
      • ``format_ok`` — non-empty, alphanumeric-ish (not pure whitespace)
      • ``collision`` — pointer to another org already using this code
      • ``auto_route_preview`` — count of rows that would be matched by Bulk
        Imports running with this code (useful sanity check)
    Also returns a ``sicon`` / ``orbit4`` block describing whether the
    integration is configured at the platform level. Pulse-only callers
    are scoped via the existing org-in-scope check.
    """
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)

    # Use the body codes when provided, else fall back to whatever's stored
    # on the org doc — lets the UI verify draft edits before saving.
    payload = body or {}
    candidates = {
        "customer_account_number": (payload.get("customer_account_number") or org.get("customer_account_number") or "").strip(),
        "sage_customer_number": (payload.get("sage_customer_number") or org.get("sage_customer_number") or "").strip(),
        "sicon_customer_number": (payload.get("sicon_customer_number") or org.get("sicon_customer_number") or "").strip(),
    }

    fields_for_collision = list(candidates.keys())
    field_results: dict = {}
    for field, value in candidates.items():
        if not value:
            field_results[field] = {
                "value": "",
                "format_ok": False,
                "collision": None,
                "note": "empty — set this code to enable Bulk Imports auto-routing for this tenant",
            }
            continue

        # Format check: at least 2 chars, no whitespace, only alnum + - _ . / allowed
        format_ok = (
            len(value) >= 2
            and all(ch.isalnum() or ch in "-_./" for ch in value)
        )
        collision = await _check_code_collision(value, fields_for_collision, org_id)
        # Auto-route preview — how many EQUIPMENT rows referencing this org
        # the Bulk Imports auto-routing would already match. Pure read.
        equipment_count = await db.equipment.count_documents({"organization_id": org_id})
        contact_count = await db.crm_contacts.count_documents({"organization_id": org_id})
        field_results[field] = {
            "value": value,
            "format_ok": format_ok,
            "collision": collision,
            "auto_route_preview": {
                "existing_equipment_in_tenant": equipment_count,
                "existing_contacts_in_tenant": contact_count,
            },
        }

    sicon = await _integration_status("sicon")
    orbit4 = await _integration_status("orbit4")

    # Top-level convenience flag — "all green" iff every populated code
    # has format_ok and zero collisions. Empty fields don't fail; they're
    # informational only.
    all_green = all(
        (r["format_ok"] and not r["collision"])
        for r in field_results.values()
        if r["value"]
    ) and any(r["value"] for r in field_results.values())

    return {
        "ok": True,
        "all_green": all_green,
        "fields": field_results,
        "integrations": {"sicon": sicon, "orbit4": orbit4},
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/master-admin/organizations/{org_id}/integration-health")
async def org_integration_health(org_id: str, user: dict = Depends(get_current_user)):
    """Iter 216h21 — per-org integration health snapshot for the
    Organisations drawer's new Integrations tab (P4 redesign).

    READ-ONLY. Surfaces the connection state of every third-party
    integration that touches a single organisation:
      • stripe_connect — Stripe Express onboarding + platform fee
      • sicon          — Sicon Service (Sage 200 ledger) account ref
      • orbit4         — Orbit 4 stock / equipment master
      • sage200        — Sage 200 customer ledger

    The canonical editors for these connections live on the global
    Integrations pages — this endpoint just returns the per-org slice
    so operators don't have to bounce around the console.
    """
    require_master_admin(user)
    org = await assert_org_in_pulse_scope(user, org_id)

    # Stripe Connect — pull whatever's persisted on the org doc plus
    # the platform-fee setting from `app_config` if available.
    stripe_account_id = org.get("stripe_connect_account_id") or org.get("stripe_account_id") or ""
    stripe_charges_enabled = bool(org.get("stripe_charges_enabled", False))
    stripe_payouts_enabled = bool(org.get("stripe_payouts_enabled", False))
    platform_cfg = await db.app_config.find_one({"_id": "stripe_connect"}, {"_id": 0}) or {}
    platform_fee_pct = platform_cfg.get("platform_fee_pct")

    # Sicon — configured iff the org has a customer account ref AND
    # the platform-level Sicon integration is in `configured` state.
    sicon_platform = await _integration_status("sicon")
    sicon_account = org.get("sicon_customer_account_number") or org.get("sicon_customer_number") or ""
    sicon_auto_post = bool(org.get("sicon_auto_post", False))

    # Orbit 4 — same pattern.
    orbit_platform = await _integration_status("orbit4")
    orbit_customer = org.get("orbit4_customer_id") or ""

    # Sage 200 — currently lives via the customer number on the org
    # doc + the same Sicon bridge for posting. Treated as a separate
    # row in the UI because operators think of them separately.
    sage_account = org.get("sage_customer_number") or ""

    return {
        "org_id": org_id,
        "stripe_connect": {
            "connected": bool(stripe_account_id),
            "account_id": stripe_account_id,
            "charges_enabled": stripe_charges_enabled,
            "payouts_enabled": stripe_payouts_enabled,
            "platform_fee_pct": platform_fee_pct,
        },
        "sicon": {
            "configured": bool(sicon_account) and bool(sicon_platform.get("configured")),
            "platform_configured": bool(sicon_platform.get("configured")),
            "account_ref": sicon_account,
            "auto_post": sicon_auto_post,
        },
        "orbit4": {
            "configured": bool(orbit_customer) and bool(orbit_platform.get("configured")),
            "platform_configured": bool(orbit_platform.get("configured")),
            "customer_id": orbit_customer,
        },
        "sage200": {
            "configured": bool(sage_account),
            "account_ref": sage_account,
        },
    }


@router.get("/master-admin/integrations-hub")
async def integrations_hub(user: dict = Depends(get_current_user)):
    """Iter 216h22 — single round-trip status summary for the new
    Integrations Hub page (P5 redesign).

    READ-ONLY aggregate of the 4 third-party connections Master Admins
    care about most:
      • stripe_connect — platform-level Stripe Express OAuth, plus a
        count of orgs that have completed onboarding.
      • sicon          — Sicon Service (Sage 200 ledger) — config doc
        in `db.integrations` + per-org Sicon customer-number coverage.
      • orbit4         — Orbit 4 stock master — same shape as Sicon.
      • sage200        — Per-org Sage customer numbers (Sage is wired
        via the Sicon bridge — no separate platform creds).

    Per-row fields:
      • enabled             — platform-level toggle
      • status              — "connected" | "degraded" | "not_configured" | "down"
      • last_event_at       — most recent integration_logs timestamp
      • events_24h          — count of integration_logs in the last 24 h
      • errors_24h          — count where success=False in last 24 h
      • orgs_configured     — number of orgs that have the per-org ref
      • orgs_total          — total org count (for the brand currently filtered)
      • brand               — "all" | "pulse" | "gymaxis" — applied
                              to the orgs_configured/total counts.
    """
    require_master_admin(user)
    from utils.brand_filter import brand_filter_clause
    brand = "all"
    # Pulse-only callers are pinned to the Pulse brand server-side too.
    if is_pulse_only(user):
        brand = "pulse"

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_iso = cutoff.isoformat()

    async def _row(integration_id: str, ref_field: str, label: str):
        """Build a per-integration row using the `integrations` and
        `integration_logs` collections plus per-org ref coverage."""
        cfg = await db.integrations.find_one({"integration_id": integration_id}, {"_id": 0}) or {}
        enabled = bool(cfg.get("enabled", False))
        events_24h = await db.integration_logs.count_documents({
            "integration_id": integration_id, "timestamp": {"$gte": cutoff_iso},
        })
        errors_24h = await db.integration_logs.count_documents({
            "integration_id": integration_id, "timestamp": {"$gte": cutoff_iso}, "success": False,
        })
        # Most recent event (any). For the "Last sync" pill.
        last_doc = await db.integration_logs.find_one(
            {"integration_id": integration_id},
            {"_id": 0, "timestamp": 1, "success": 1},
            sort=[("timestamp", -1)],
        )

        # Per-org ref coverage. Scope to the brand filter when present.
        org_query: dict = {}
        if brand == "pulse":
            org_query = brand_filter_clause("pulse")
        elif brand == "gymaxis":
            org_query = brand_filter_clause("gymaxis")

        orgs_total = await db.organizations.count_documents(org_query)
        ref_query = {**org_query, ref_field: {"$exists": True, "$ne": ""}}
        orgs_configured = await db.organizations.count_documents(ref_query) if ref_field else 0

        if not enabled and not orgs_configured:
            status = "not_configured"
        elif errors_24h > 0 and errors_24h >= max(1, events_24h // 5):
            status = "degraded"
        elif enabled:
            status = "connected"
        else:
            status = "not_configured"

        return {
            "key": integration_id,
            "label": label,
            "enabled": enabled,
            "status": status,
            "last_event_at": (last_doc or {}).get("timestamp"),
            "last_event_success": (last_doc or {}).get("success"),
            "events_24h": events_24h,
            "errors_24h": errors_24h,
            "orgs_configured": orgs_configured,
            "orgs_total": orgs_total,
            "ref_field": ref_field,
        }

    sicon_row  = await _row("sicon",  "sicon_customer_account_number", "Sicon Service (Sage 200 ledger)")
    orbit_row  = await _row("orbit4", "orbit4_customer_id",             "Orbit 4 (stock master)")

    # Stripe Connect is platform-level + per-org onboarding state.
    stripe_cfg = await db.app_config.find_one({"_id": "stripe_connect"}, {"_id": 0}) or {}
    stripe_enabled = bool(stripe_cfg.get("enabled", True))  # Stripe is on unless explicitly off
    stripe_org_query: dict = {"stripe_connect_account_id": {"$exists": True, "$ne": ""}}
    if brand == "pulse":
        stripe_org_query = {**brand_filter_clause("pulse"), **stripe_org_query}
    elif brand == "gymaxis":
        stripe_org_query = {**brand_filter_clause("gymaxis"), **stripe_org_query}
    stripe_orgs_configured = await db.organizations.count_documents(stripe_org_query)
    stripe_orgs_total = await db.organizations.count_documents(
        brand_filter_clause(brand) if brand != "all" else {},
    )
    stripe_status = "connected" if stripe_orgs_configured > 0 else ("not_configured" if not stripe_enabled else "degraded")
    stripe_row = {
        "key": "stripe_connect",
        "label": "Stripe Connect",
        "enabled": stripe_enabled,
        "status": stripe_status,
        "last_event_at": None,
        "last_event_success": None,
        "events_24h": 0,
        "errors_24h": 0,
        "orgs_configured": stripe_orgs_configured,
        "orgs_total": stripe_orgs_total,
        "platform_fee_pct": stripe_cfg.get("platform_fee_pct"),
        "ref_field": "stripe_connect_account_id",
    }

    # Sage 200 is sub-integration: customer numbers stored on the org
    # doc, posts ride the Sicon bridge.
    sage_org_query = {**(brand_filter_clause(brand) if brand != "all" else {}), "sage_customer_number": {"$exists": True, "$ne": ""}}
    sage_orgs_configured = await db.organizations.count_documents(sage_org_query)
    sage_status = "connected" if sage_orgs_configured > 0 else "not_configured"
    sage_row = {
        "key": "sage200",
        "label": "Sage 200 (customer ledger)",
        "enabled": sage_orgs_configured > 0,
        "status": sage_status,
        "last_event_at": None,
        "last_event_success": None,
        "events_24h": 0,
        "errors_24h": 0,
        "orgs_configured": sage_orgs_configured,
        "orgs_total": stripe_orgs_total,
        "ref_field": "sage_customer_number",
    }

    summary = {
        "connected":      sum(1 for r in (stripe_row, sicon_row, orbit_row, sage_row) if r["status"] == "connected"),
        "degraded":       sum(1 for r in (stripe_row, sicon_row, orbit_row, sage_row) if r["status"] == "degraded"),
        "not_configured": sum(1 for r in (stripe_row, sicon_row, orbit_row, sage_row) if r["status"] == "not_configured"),
        "total":          4,
    }

    return {
        "brand": brand,
        "integrations": [stripe_row, sicon_row, orbit_row, sage_row],
        "summary": summary,
    }
