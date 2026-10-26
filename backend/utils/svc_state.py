"""
Pulse Fitness Service Operations — state machine.

Iter 215dn (Phase 1).

Single source of truth for the case lifecycle. Every transition emits a
`svc_case_events` row with actor + reason + delta — this is the foundation
for the audit trail and the timeline UI.

Design:
- States are plain strings (Mongo-friendly, easy to query/index).
- Transitions are declared in `_TRANSITIONS`; anything not listed raises.
- `transition(...)` is the only legitimate way to change `svc_cases.status`.
"""
from datetime import datetime, timezone
import uuid

from utils.database import db


# ─────────────────────────────────────────────────────────────────
# State graph
# ─────────────────────────────────────────────────────────────────

NEW = "new"
TRIAGED = "triaged"
ASSIGNED = "assigned"
EN_ROUTE = "en_route"
ON_SITE = "on_site"
PAUSED_PARTS = "paused_parts"
PAUSED_CUSTOMER = "paused_customer"
REPAIRED = "repaired"
AWAITING_SIGN_OFF = "awaiting_sign_off"
CLOSED = "closed"
INVOICED = "invoiced"
REJECTED = "rejected"

ALL_STATES = (
    NEW, TRIAGED, ASSIGNED, EN_ROUTE, ON_SITE,
    PAUSED_PARTS, PAUSED_CUSTOMER, REPAIRED,
    AWAITING_SIGN_OFF, CLOSED, INVOICED, REJECTED,
)

# State → set of legal next states
_TRANSITIONS = {
    NEW: {TRIAGED, ASSIGNED, REJECTED},
    TRIAGED: {ASSIGNED, REJECTED},
    ASSIGNED: {EN_ROUTE, ON_SITE, ASSIGNED, NEW, REJECTED},  # self = reassign
    EN_ROUTE: {ON_SITE, ASSIGNED},
    ON_SITE: {PAUSED_PARTS, PAUSED_CUSTOMER, REPAIRED, AWAITING_SIGN_OFF, CLOSED},
    PAUSED_PARTS: {ON_SITE, ASSIGNED, REPAIRED},
    PAUSED_CUSTOMER: {ON_SITE, ASSIGNED, REPAIRED},
    REPAIRED: {AWAITING_SIGN_OFF, CLOSED},
    AWAITING_SIGN_OFF: {CLOSED, ON_SITE},  # customer rejects → re-open
    CLOSED: {INVOICED},
    INVOICED: set(),
    REJECTED: set(),
}

# States in which the SLA resolution clock is paused.
SLA_PAUSED_STATES = {PAUSED_PARTS, PAUSED_CUSTOMER}

# Iter 290f — canonical "SLA at risk" window. A case is *at risk* when its
# resolution target falls within this many hours AND has not yet passed
# (already-past targets are "breached", a mutually-exclusive bucket). Shared
# by the desk KPI strip, the performance dashboard tile and the
# /svc/cases?sla=at_risk drill-down so the three always reconcile.
SLA_RISK_WINDOW_HOURS = 24

# States the desk should treat as "open".
OPEN_STATES = {NEW, TRIAGED, ASSIGNED, EN_ROUTE, ON_SITE, PAUSED_PARTS, PAUSED_CUSTOMER, REPAIRED, AWAITING_SIGN_OFF}

# Terminal states — case is finished, no further engineer action expected.
# Used by the queue, dispatch board and SLA reporting to exclude completed
# work. Iter 216h151 — replaces ad-hoc string literals scattered around the
# codebase (`["closed", "invoiced", "cancelled", "void"]`) which referenced
# states that don't exist in this state machine.
TERMINAL_STATES = {CLOSED, INVOICED, REJECTED}
SIGNOFF_DONE_STATES = {REPAIRED, AWAITING_SIGN_OFF, CLOSED, INVOICED}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, set())


async def transition(
    *,
    case_id: str,
    organization_id: str,
    target_state: str,
    actor: dict,
    reason: str = "",
    extra: dict | None = None,
) -> dict:
    """Atomically move a case to `target_state`.

    Raises ValueError on illegal transitions; returns the updated case doc.
    Always writes a `svc_case_events` row tagged `state_change`.
    """
    if target_state not in ALL_STATES:
        raise ValueError(f"Unknown state {target_state!r}")
    case = await db.svc_cases.find_one({"id": case_id, "organization_id": organization_id})
    if not case:
        raise ValueError("Case not found")
    current = case.get("status") or NEW
    if current == target_state and target_state != ASSIGNED:
        # No-op transition (allow ASSIGNED→ASSIGNED for reassignment).
        return case
    if not can_transition(current, target_state):
        raise ValueError(f"Cannot move case from {current!r} to {target_state!r}")

    update: dict = {
        "status": target_state,
        "updated_at": _now(),
    }
    if target_state in SLA_PAUSED_STATES and not case.get("sla_paused_at"):
        update["sla_paused_at"] = _now()
    if current in SLA_PAUSED_STATES and target_state not in SLA_PAUSED_STATES:
        # Resume SLA — adjust resolve target by paused duration.
        paused_at = case.get("sla_paused_at")
        if paused_at and case.get("sla_resolve_at"):
            paused_dt = datetime.fromisoformat(paused_at)
            now_dt = datetime.now(timezone.utc)
            paused_secs = (now_dt - paused_dt).total_seconds()
            old_target = datetime.fromisoformat(case["sla_resolve_at"])
            new_target = old_target.timestamp() + paused_secs
            update["sla_resolve_at"] = datetime.fromtimestamp(new_target, tz=timezone.utc).isoformat()
        update["sla_paused_at"] = None
    if target_state == CLOSED:
        update["closed_at"] = _now()
    # Reopened after completion → a fresh customer sign-off is needed.
    if current in SIGNOFF_DONE_STATES and target_state not in SIGNOFF_DONE_STATES | {REJECTED}:
        update["reopened_at"] = _now()

    await db.svc_cases.update_one({"id": case_id}, {"$set": update})

    # Append timeline event (best-effort — never blocks).
    try:
        await db.svc_case_events.insert_one({
            "id": str(uuid.uuid4()),
            "case_id": case_id,
            "organization_id": organization_id,
            "type": "state_change",
            "from_state": current,
            "to_state": target_state,
            "reason": reason or "",
            "actor_id": (actor or {}).get("id", ""),
            "actor_name": (actor or {}).get("full_name", "") or (actor or {}).get("email", ""),
            "extra": extra or {},
            "at": _now(),
        })
    except Exception:
        pass

    case.update(update)
    case.pop("_id", None)

    # Phase 4 — fire-and-forget customer auto-notify (en_route / on_site / closed).
    # Lazy import to avoid circular dependency with routes.svc.comms.
    try:
        from routes.svc.comms import auto_notify_on_transition  # noqa: WPS433
        await auto_notify_on_transition(case=case, target_state=target_state, actor=actor)
    except Exception:
        # Never block a state transition on a comms failure.
        pass

    # Iter 252 — reverse Ops-Portal bridge. If this case originated from an
    # Operations Portal fault, mirror the new state back onto that issue so
    # the customer's portal shows live progress + resolution. Fire-and-forget.
    try:
        from utils.svc_ops_bridge import mirror_case_state_to_issue  # noqa: WPS433
        await mirror_case_state_to_issue(case=case, target_state=target_state, actor=actor)
    except Exception:
        pass

    return case


async def append_event(
    *,
    case_id: str,
    organization_id: str,
    event_type: str,
    actor: dict,
    body: str = "",
    extra: dict | None = None,
) -> dict:
    """Generic append to the case timeline for non-state events (note, photo, comm)."""
    row = {
        "id": str(uuid.uuid4()),
        "case_id": case_id,
        "organization_id": organization_id,
        "type": event_type,
        "body": body,
        "actor_id": (actor or {}).get("id", ""),
        "actor_name": (actor or {}).get("full_name", "") or (actor or {}).get("email", ""),
        "extra": extra or {},
        "at": _now(),
    }
    try:
        await db.svc_case_events.insert_one(row)
    except Exception:
        pass
    row.pop("_id", None)
    return row


# ─────────────────────────────────────────────────────────────────
# Strict status enforcement (Iter — prevent casing/vocabulary drift)
# ─────────────────────────────────────────────────────────────────

def coerce_status(value: str) -> str:
    """Validate + normalise a case status to the canonical lowercase vocab.

    Every writer that sets ``svc_cases.status`` directly (rather than via
    ``transition``) MUST pass its value through here so a stray ``"ASSIGNED"``
    or unknown state can never reach the DB and silently fall out of the
    engineer/desk queries (which filter on the lowercase OPEN_STATES set).
    Raises ValueError on anything not in ALL_STATES.
    """
    if not isinstance(value, str):
        raise ValueError(f"Invalid case status {value!r}")
    norm = value.strip().lower()
    if norm not in ALL_STATES:
        raise ValueError(f"Unknown case status {value!r} (expected one of {ALL_STATES})")
    return norm


async def normalize_legacy_statuses() -> int:
    """One-shot startup healer: lowercase any legacy svc_cases.status values
    that differ only by case from a canonical state (e.g. the old
    ``"ASSIGNED"`` PPM allocations). Returns the count fixed."""
    fixed = 0
    cursor = db.svc_cases.find(
        {"status": {"$nin": list(ALL_STATES)}},
        {"id": 1, "status": 1},
    )
    async for c in cursor:
        s = c.get("status")
        if isinstance(s, str) and s.strip().lower() in ALL_STATES:
            await db.svc_cases.update_one(
                {"id": c["id"]}, {"$set": {"status": s.strip().lower()}}
            )
            fixed += 1
    return fixed
