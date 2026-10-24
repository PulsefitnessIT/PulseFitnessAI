"""
Operations Portal ⇄ Service Desk reverse bridge (Iter 252).

The FORWARD half already exists (`routes/issues._mirror_issue_to_svc_case`):
when a gym on the Operations Portal escalates a fault to an engineer, an
`svc_cases` row is materialised, stamped with
``source_meta = {"issue_id": <issue id>, "channel": "operations_portal"}``.

This module is the REVERSE half: as that case moves through the Service
Desk / Engineer App, we mirror progress back onto the originating
`issues` document so the customer's Operations Portal shows live status
(engineer en route → on site → work complete → resolved) and a link to
the case reference — instead of the fault sitting "open" forever.

It is generic: it keys purely off ``source_meta.issue_id`` within the
same organisation, so it works for ANY service supplier whose customer
is on the Operations Portal, not just Pulse Fitness.

Wired into `utils.svc_state.transition` as a fire-and-forget hook, so
EVERY path (engineer complete, desk status change, customer sign-off,
inbound Sicon sync) keeps the portal in sync.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from utils.database import db

logger = logging.getLogger(__name__)

# Case state → (issue KPI timestamps to stamp if unset, timeline event,
#               human label shown on the portal timeline).
_EN_ROUTE = "en_route"
_ON_SITE = "on_site"
_REPAIRED = "repaired"
_AWAITING_SIGN_OFF = "awaiting_sign_off"
_CLOSED = "closed"
_REJECTED = "rejected"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def mirror_case_state_to_issue(*, case: dict, target_state: str, actor: dict | None) -> bool:
    """Mirror a case state change back onto its originating Ops-Portal issue.

    Returns True when an issue was updated, False otherwise. Best-effort:
    callers must not let a failure here block the case transition.
    """
    source = case.get("source_meta") or {}
    issue_id = source.get("issue_id")
    issue_q = {"id": issue_id, "organization_id": case.get("organization_id")}
    if not issue_id and case.get("mod_issue_id"):
        # MOD Operations job mirrored from a MOD site fault (lives under the BFPO org).
        issue_id = case["mod_issue_id"]
        issue_q = {"id": issue_id}
    if not issue_id:
        return False  # not an Ops-Portal-originated case — nothing to mirror

    issue = await db.issues.find_one(
        issue_q,
        {"_id": 0, "id": 1, "status": 1, "engineer_assigned_at": 1,
         "engineer_arrived_at": 1, "work_started_at": 1, "work_completed_at": 1,
         "first_response_at": 1, "resolved_at": 1},
    )
    if not issue:
        return False

    now = _now()
    actor_name = (actor or {}).get("full_name") or (actor or {}).get("email") or "Engineer"
    set_fields: dict = {
        # Always keep the portal pointing at the live case.
        "linked_case_id": case.get("id"),
        "linked_case_reference": case.get("reference"),
        "last_case_sync_at": now,
        "case_status": target_state,
    }

    def _stamp_if_unset(field: str) -> None:
        if not issue.get(field):
            set_fields[field] = now

    timeline_event: str | None = None
    timeline_label: str | None = None

    if target_state == _EN_ROUTE:
        _stamp_if_unset("engineer_assigned_at")
        _stamp_if_unset("first_response_at")
        timeline_event, timeline_label = "engineer_en_route", "Engineer en route"
    elif target_state == _ON_SITE:
        _stamp_if_unset("engineer_arrived_at")
        _stamp_if_unset("work_started_at")
        _stamp_if_unset("first_response_at")
        timeline_event, timeline_label = "engineer_on_site", "Engineer on site"
    elif target_state in (_REPAIRED, _AWAITING_SIGN_OFF):
        _stamp_if_unset("work_completed_at")
        timeline_event, timeline_label = "work_completed", "Work completed by engineer"
    elif target_state == _CLOSED:
        _stamp_if_unset("work_completed_at")
        # Close the loop on the portal: the fault is resolved by engineer.
        if (issue.get("status") or "") != "resolved":
            set_fields["status"] = "resolved"
            set_fields["resolved_at"] = now
            set_fields["resolution_type"] = "engineer"
            set_fields["resolved_by"] = actor_name
        timeline_event, timeline_label = "resolved_by_engineer", "Resolved by engineer"
    elif target_state == _REJECTED:
        timeline_event, timeline_label = "case_rejected", "Service case rejected — fault reopened"
    else:
        # New / triaged / assigned / paused — keep the link & status fresh
        # but don't stamp KPIs or push a timeline entry.
        pass

    update: dict = {"$set": set_fields}
    if timeline_event:
        update["$push"] = {"timeline": {
            "event": timeline_event,
            "label": timeline_label,
            "timestamp": now,
            "by": actor_name,
            "case_reference": case.get("reference"),
            "source": "service_desk",
        }}

    try:
        await db.issues.update_one({"id": issue_id}, update)
        return True
    except Exception as e:  # pragma: no cover — defensive only
        logger.warning("mirror_case_state_to_issue failed for issue %s: %s", issue_id, e)
        return False


__all__ = ["mirror_case_state_to_issue"]
