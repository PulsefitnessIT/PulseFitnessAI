"""CRM · Master Price List — product cost/margin field-level security (Iter 220 P1).

SECURE BY DEFAULT: restricted roles (e.g. sales_rep, rep, support, generic
user) NEVER see product cost or margin fields unless an admin explicitly
grants their role cost visibility. Privileged roles (owner / admin / manager
/ finance / analyst, plus master & pulse admins) always see cost.

Grants are stored per (organization_id, role) in `crm_product_perms`:
    {organization_id, role, can_see_cost: true, ...}
A row with can_see_cost=true means that role IS allowed to see cost.

This module exposes:
  - can_see_product_cost(user)            → bool
  - redact_product_cost(user, payload)    → strip cost fields from product(s)
  - redact_quote_cost(user, payload)      → strip cost/margin from quote(s)
  - REST endpoints under /api/crm/product-perms (admin only).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.database import db
from routes.crm_auth import get_crm_user
from routes.crm_permissions import is_unrestricted
from routes.crm_core import log_audit

router = APIRouter(prefix="/crm/product-perms", tags=["CRM Product Cost Permissions"])

# Roles that always see cost/margin (on top of master/pulse admin + owner/admin).
PRIVILEGED_COST_ROLES = {"owner", "admin", "manager", "finance", "analyst"}

# The cost/margin fields stripped from products for restricted roles.
COST_FIELDS = {
    "cost_price", "markup_percent", "margin", "margin_percent",
    "trade_price", "list_price", "retail_price",
    "installation_cost", "delivery_cost", "discount",
    "rollup_cost", "rollup_margin_percent",
}

# Extra quote-level / quote-line fields stripped for restricted roles.
QUOTE_COST_FIELDS = {
    "cost_price", "margin", "margin_percent", "cost_total", "total_cost",
    "rollup_cost", "rollup_margin_percent",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _of(user: dict) -> dict:
    return {"organization_id": user.get("organization_id")}


async def can_see_product_cost(user: dict) -> bool:
    """True if this user may see product cost/margin."""
    if is_unrestricted(user):  # master/pulse admin + owner/admin
        return True
    role = (user.get("role") or "").lower()
    if role in PRIVILEGED_COST_ROLES:
        return True
    grant = await db.crm_product_perms.find_one(
        {**_of(user), "role": role, "can_see_cost": True}, {"_id": 0, "role": 1}
    )
    return bool(grant)


def _strip(doc, fields: set[str]):
    if isinstance(doc, dict):
        out = {k: v for k, v in doc.items() if k not in fields}
        # nested quote/bundle lines also carry cost
        for key in ("lines", "components", "expanded", "items", "bundle_items"):
            if isinstance(out.get(key), list):
                out[key] = [_strip(it, fields) for it in out[key]]
        return out
    if isinstance(doc, list):
        return [_strip(it, fields) for it in doc]
    return doc


async def redact_product_cost(user: dict, payload):
    """Strip cost/margin fields from a product dict / list of products."""
    if await can_see_product_cost(user):
        return payload
    return _strip(payload, COST_FIELDS)


async def redact_quote_cost(user: dict, payload):
    """Strip cost/margin fields from a quote dict / list of quotes."""
    if await can_see_product_cost(user):
        return payload
    return _strip(payload, QUOTE_COST_FIELDS)


def require_cost_visibility_sync_note() -> None:  # pragma: no cover - doc only
    """Quality dashboard endpoints call can_see_product_cost and 403 when False."""


# ── Admin REST ─────────────────────────────────────────────────────

def _require_admin(user: dict) -> None:
    if not is_unrestricted(user):
        raise HTTPException(403, "Master admin / owner access required")


@router.get("")
async def list_product_perms(user=Depends(get_crm_user)) -> dict:
    _require_admin(user)
    rows = await db.crm_product_perms.find(_of(user), {"_id": 0}).to_list(200)
    granted = {r["role"] for r in rows if r.get("can_see_cost")}
    return {
        "grants": sorted(granted),
        "privileged_roles": sorted(PRIVILEGED_COST_ROLES),
        "cost_fields": sorted(COST_FIELDS),
    }


@router.put("")
async def set_product_perm(data: dict = Body(...), user=Depends(get_crm_user)) -> dict:
    _require_admin(user)
    role = (data.get("role") or "").strip().lower()
    can_see = bool(data.get("can_see_cost"))
    if not role:
        raise HTTPException(400, "role required")
    if role in PRIVILEGED_COST_ROLES:
        raise HTTPException(400, f"'{role}' already sees cost by default")
    if can_see:
        await db.crm_product_perms.update_one(
            {**_of(user), "role": role},
            {"$set": {"can_see_cost": True, "updated_at": _now(), "updated_by": user.get("full_name", "")},
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()}},
            upsert=True,
        )
    else:
        await db.crm_product_perms.delete_one({**_of(user), "role": role})
    await log_audit(
        user, "product_cost_permission", role,
        "granted" if can_see else "revoked",
        {"role": role, "can_see_cost": can_see},
    )
    return {"success": True, "role": role, "can_see_cost": can_see}


@router.get("/me")
async def my_cost_visibility(user=Depends(get_crm_user)) -> dict:
    return {"can_see_cost": await can_see_product_cost(user)}
