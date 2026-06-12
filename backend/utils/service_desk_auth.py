"""Service Desk role guard + audit logging.

Service Desk is an internal Pulse Fitness operational role — sits between
Master Admin (platform execs) and customer-facing Owner/Manager/Staff roles.

Role resolution:
- A user is Service Desk if `user.is_service_desk == True` OR `is_master_admin == True`.
- Master admins automatically pass Service Desk checks (superset).
- The role is granted/revoked ONLY via Master Admin, never self-elevated.

Audit trail:
- Every action taken via a `/api/service-desk/*` endpoint that mutates state
  MUST call `log_desk_action()` with the target resource. The log is viewable
  by Master Admin and by other Service Desk agents (for transparency) but
  cannot be edited or deleted by anyone.
"""
from datetime import datetime, timezone
import uuid
from fastapi import Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db


def _is_service_desk(user: dict) -> bool:
    # Iter 244 — Pulse Master Admins run the Pulse Fitness service operation,
    # so they get Service Desk access alongside flagged desk agents.
    return bool(
        user.get("is_service_desk")
        or user.get("is_master_admin")
        or user.get("is_pulse_admin")
        or user.get("role") == "pulse_master_admin"
    )


async def require_service_desk(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency — 403 unless user is Service Desk or Master Admin."""
    if not _is_service_desk(user):
        raise HTTPException(
            status_code=403,
            detail="Service Desk access required",
        )
    return user


async def log_desk_action(
    actor: dict,
    action: str,
    target_type: str,
    target_id: str,
    summary: str,
    details: dict | None = None,
    impersonating_org_id: str | None = None,
) -> None:
    """Append an immutable audit row.

    action: short verb like 'org.update', 'import.commit', 'user.invite'
    target_type / target_id: what was acted on (org / user / import / supplier ...)
    summary: 1-line human description that shows in the audit feed
    """
    await db.service_desk_audit_log.insert_one({
        "id": str(uuid.uuid4()),
        "actor_id": actor.get("id"),
        "actor_email": actor.get("email"),
        "actor_role": (
            "master_admin" if actor.get("is_master_admin")
            else "pulse_master_admin"
            if (actor.get("is_pulse_admin") or actor.get("role") == "pulse_master_admin")
            else "service_desk"
        ),
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "summary": summary,
        "details": details or {},
        "impersonating_org_id": impersonating_org_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Brand scoping (Iter 245) ─────────────────────────────────────
#
# Desk users provisioned with `service_desk_brand == "pulse"` and Pulse
# Master Admins see only Pulse-visible customer organisations on the
# cross-org Service Desk surfaces (summary, customers, equipment,
# supplier health, impersonation). GymAxis master admins and
# gymaxis-brand agents stay platform-wide.

# Account types that identify a Pulse-serviced customer org. Superset of
# routes.master_admin.PULSE_VISIBLE_ACCOUNT_TYPES — live data also
# carries `pulse_lite` and the MOD variants (`mod_site` / `mod_org` /
# `mod_branch`), which are Pulse-serviced estates.
PULSE_DESK_ACCOUNT_TYPES = [
    "pulse_pro", "pulse_lite", "lite",
    "mod", "mod_site", "mod_org", "mod_branch",
    "full",
]


def _is_pulse_scoped(user: dict) -> bool:
    if user.get("is_master_admin"):
        return False
    return bool(
        user.get("is_pulse_admin")
        or user.get("role") == "pulse_master_admin"
        or (user.get("service_desk_brand") or "").lower() == "pulse"
    )


async def desk_scope_org_ids(user: dict) -> list[str] | None:
    """Return ``None`` for platform-wide desk access, else the list of
    Pulse-visible organisation ids the caller is restricted to."""
    if not _is_pulse_scoped(user):
        return None
    orgs = await db.organizations.find(
        {"account_type": {"$in": PULSE_DESK_ACCOUNT_TYPES}},
        {"_id": 0, "id": 1},
    ).to_list(length=None)
    return [o["id"] for o in orgs]


async def assert_org_in_desk_scope(user: dict, org_id: str) -> None:
    """Raise 404 when a Pulse-scoped desk user touches a non-Pulse org.

    404 (not 403) so out-of-scope org ids are indistinguishable from
    non-existent ones."""
    scope = await desk_scope_org_ids(user)
    if scope is not None and org_id not in scope:
        raise HTTPException(status_code=404, detail="Organisation not found")
