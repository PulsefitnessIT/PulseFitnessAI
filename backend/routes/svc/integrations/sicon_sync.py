"""
GymAxis Service Operations — Sicon Service sync stubs.

Iter 215dp.

This is the bridge layer for the cutover period (until Phase 8). All
new `svc_*` entities flow through these helpers so we can flip the
"live push" switch without touching feature code.

Currently the helpers ENQUEUE outbound payloads to the
`svc_sicon_outbox` collection. A scheduled worker (TODO) will drain
the outbox and call the real Sicon API.

The mapping rules are authoritative in `/app/memory/SVC_FIELD_MAPPING.md`.
Keep the `_to_sicon_*` functions in lockstep with that file — every
new GymAxis field added to a Pydantic model in `models/svc/*` must
appear here OR be explicitly tagged `gymaxis_only` in the mapping doc.
"""
from datetime import datetime, timezone
import logging
import uuid

from utils.database import db

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Status / type crosswalks (mirrors §8 and §9 of SVC_FIELD_MAPPING.md)
# ─────────────────────────────────────────────────────────────────

STATUS_CROSSWALK: dict[str, str] = {
    "new": "Logged",
    "triaged": "Triaged",
    "assigned": "Assigned",
    "en_route": "EnRoute",
    "on_site": "OnSite",
    "paused_parts": "OnHoldAwaitingParts",
    "paused_customer": "OnHoldAwaitingCustomer",
    "repaired": "Repaired",
    "awaiting_sign_off": "AwaitingCustomerSignOff",
    "closed": "Completed",
    "invoiced": "Invoiced",
    "rejected": "Cancelled",
}

PRIORITY_CROSSWALK: dict[str, int] = {"p1": 1, "p2": 2, "p3": 3, "p4": 4}

NOTE_TYPE_CROSSWALK: dict[str, str] = {
    "intake": "Logged",
    "note": "EngineerNote",
    "state_change": "StatusChange",
    "edit": "RecordEdit",
    "comm": "Communication",
    "photo": "Attachment",
    "signature": "CompletionSignature",
    "time_start": "Timesheet",
    "time_stop": "Timesheet",
}

# Cover-type → Sage nominal (placeholders, finance to confirm)
COVER_NOMINAL: dict[str, str] = {
    "contract": "4001",
    "warranty": "4002",
    "chargeable": "4010",
    "ppm": "4003",
}


# ─────────────────────────────────────────────────────────────────
# Payload builders
# ─────────────────────────────────────────────────────────────────

def _to_sicon_call(case: dict) -> dict:
    """Translate a `svc_cases` doc to a Sicon `ServiceCall` payload.

    Direction: GymAxis → Sicon. Read-back fields (AssignedToSageUser*,
    closed_at when Sicon owns) are intentionally omitted on outbound.
    """
    return {
        "OurReference": case.get("id"),
        "CallReference": case.get("reference"),
        "Description": (case.get("title") or "")[:80],
        "Notes": case.get("description") or "",
        "StatusID": STATUS_CROSSWALK.get(case.get("status"), "Logged"),
        "PriorityID": PRIORITY_CROSSWALK.get(case.get("priority"), 3),
        "CallTypeID": case.get("cover_type") or "contract",
        "JobTypeID": case.get("case_type") or "repair",
        "FaultCodeID": case.get("fault_code") or "",
        "FaultCategoryID": case.get("fault_category") or "",
        "EquipmentIDs": (case.get("equipment_ids") or ([case["asset_id"]] if case.get("asset_id") else [])),
        "EquipmentSerials": case.get("equipment_serials") or [],
        "Parts": [
            {
                "PartCode": p.get("part_sku"),
                "Description": p.get("part_name"),
                "Quantity": p.get("qty") or 1,
                "Source": p.get("source") or "warehouse",
                "EngineerID": p.get("engineer_id") or "",
            }
            for p in (case.get("allocated_parts") or [])
        ],
        "RequiredSkills": case.get("required_skills") or [],
        "SubLocation": {
            "SiconSubLocationID": case.get("site_id") or None,
            "Description": case.get("site_name") or "",
        },
        "ContractID": case.get("contract_id") or "",
        "ContactName": case.get("customer_name") or "",
        "ContactEmail": case.get("customer_email") or "",
        "ContactPhone": case.get("customer_phone") or "",
        "ScheduledDateTime": case.get("scheduled_at"),
        "EstimatedMinutes": case.get("estimated_minutes") or 0,
        "SLATargetResponseAt": case.get("sla_response_at"),
        "SLATargetResolveAt": case.get("sla_resolve_at"),
        "SLAPausedAt": case.get("sla_paused_at"),
        "CompletedDateTime": case.get("closed_at"),
        "LoggedDateTime": case.get("created_at"),
        "LoggedByMethod": case.get("source") or "portal",
        "LoggedBySageUserID": case.get("logged_by_id") or "",
        "LoggedByUserName": case.get("logged_by_name") or "",
        "Tags": ";".join(case.get("tags") or []),
    }


def _to_sicon_tracking_note(event: dict) -> dict:
    """Translate a `svc_case_events` row to a Sicon TrackingNote payload."""
    body = event.get("body") or ""
    if event.get("type") == "state_change":
        body = f"{event.get('from_state', '')} → {event.get('to_state', '')}"
        if event.get("reason"):
            body += f" · {event['reason']}"
    return {
        "OurReference": event.get("id"),
        "ServiceCallReference": event.get("case_reference") or event.get("case_id"),
        "NoteTypeID": NOTE_TYPE_CROSSWALK.get(event.get("type"), "EngineerNote"),
        "NoteText": body,
        "VisibleToCustomer": (event.get("extra") or {}).get("visibility") == "customer",
        "VisibleToEngineer": (event.get("extra") or {}).get("visibility") != "customer",
        "CreatedBySageUserID": event.get("actor_id") or "",
        "CreatedByUserName": event.get("actor_name") or "",
        "CreatedDateTime": event.get("at"),
    }


def _to_sicon_appointment(time_entry: dict) -> dict:
    """Translate a `svc_time_entries` row to a Sicon Appointment payload."""
    return {
        "OurReference": time_entry.get("id"),
        "ServiceCallReference": time_entry.get("case_reference") or time_entry.get("case_id"),
        "ResourceID": time_entry.get("engineer_sage_user_id") or time_entry.get("engineer_id"),
        "StartDateTime": time_entry.get("start_at"),
        "EndDateTime": time_entry.get("end_at"),
        "AppointmentTypeID": time_entry.get("category") or "on_site",
        "Chargeable": bool(time_entry.get("chargeable")),
        "Notes": time_entry.get("notes") or "",
    }


def _to_sicon_signature(sig: dict) -> dict:
    """Translate a `svc_signatures` row to a Sicon CompletionSignature payload."""
    return {
        "OurReference": sig.get("id"),
        "ServiceCallReference": sig.get("case_reference") or sig.get("case_id"),
        "CustomerName": sig.get("signed_by_name") or "",
        "CustomerRole": sig.get("signed_by_role") or "",
        "SignedAt": sig.get("signed_at"),
        "SignatureImage": sig.get("image_data") or "",
        "WorkDoneSummary": sig.get("summary") or "",
    }


def _to_sicon_attachment(photo: dict) -> dict:
    """Translate a `svc_engineer_photos` row to a Sicon ServiceCallAttachment."""
    return {
        "OurReference": photo.get("id"),
        "ServiceCallReference": photo.get("case_reference") or photo.get("case_id"),
        "FileURL": photo.get("file_url") or "",
        "ContentType": photo.get("mime_type") or "image/jpeg",
        "Description": photo.get("caption") or "",
        "CreatedAt": photo.get("taken_at"),
        "CreatedBySageUserID": photo.get("taken_by_id") or "",
        "CreatedByUserName": photo.get("taken_by_name") or "",
    }


# Sicon stock movement type IDs (mirrors §12 of SVC_FIELD_MAPPING.md)
PART_MOVEMENT_CROSSWALK: dict[str, str] = {
    "allocate":   "AllocateToCall",
    "deallocate": "ReleaseFromCall",
    "consume":    "ConsumeOnSite",
    "transfer":   "TransferBetweenLocations",
    "return":     "ReturnToWarehouse",
    "receive":    "GoodsReceiptFromPO",
    "po_receipt": "GoodsReceiptFromPO",   # alias used by inventory.receive_po
}


def _to_sicon_part_movement(movement: dict) -> dict:
    """Translate a `svc_part_movements` row to a Sicon StockMovement payload."""
    return {
        "OurReference": movement.get("id"),
        "ServiceCallReference": movement.get("case_reference") or movement.get("case_id"),
        "MovementTypeID": PART_MOVEMENT_CROSSWALK.get(
            movement.get("movement_type") or "allocate", "AllocateToCall",
        ),
        "PartCode": movement.get("part_sku"),
        "Quantity": movement.get("qty") or 0,
        "FromLocation": movement.get("from_location") or movement.get("source") or "warehouse",
        "ToLocation": movement.get("to_location") or "case",
        "EngineerID": movement.get("engineer_id") or "",
        "AllocationID": movement.get("allocation_id") or "",
        "MovedAt": movement.get("at") or movement.get("allocated_at"),
        "MovedBySageUserID": movement.get("actor_id") or movement.get("allocated_by_id") or "",
        "MovedByUserName": movement.get("actor_name") or movement.get("allocated_by_name") or "",
        "Notes": movement.get("notes") or "",
    }


# ─────────────────────────────────────────────────────────────────
# Outbox enqueue (the actual Sicon HTTP call lives in a worker — TBD)
# ─────────────────────────────────────────────────────────────────

async def _enqueue(*, organization_id: str, kind: str, sicon_endpoint: str, payload: dict) -> None:
    """Append an outbound payload to the `svc_sicon_outbox` collection.

    Idempotent on `(kind, payload.OurReference)` — replays are safe.
    """
    our_ref = payload.get("OurReference") or str(uuid.uuid4())
    await db.svc_sicon_outbox.update_one(
        {"organization_id": organization_id, "kind": kind, "our_reference": our_ref},
        {
            "$set": {
                "organization_id": organization_id,
                "kind": kind,
                "endpoint": sicon_endpoint,
                "payload": payload,
                "status": "pending",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "our_reference": our_ref,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "attempts": 0,
            },
        },
        upsert=True,
    )


async def push_case(case: dict) -> None:
    """Enqueue a case upsert to Sicon. Safe to call on any state change."""
    try:
        await _enqueue(
            organization_id=case["organization_id"],
            kind="case",
            sicon_endpoint="/api/Service/Calls",
            payload=_to_sicon_call(case),
        )
    except Exception as e:  # never block the user-facing flow
        logger.warning("sicon push_case failed: %s", e)


async def push_event(event: dict, *, case_reference: str = "") -> None:
    """Enqueue a timeline event as a Sicon tracking note."""
    try:
        ev = {**event, "case_reference": case_reference or event.get("case_reference")}
        await _enqueue(
            organization_id=event["organization_id"],
            kind="tracking_note",
            sicon_endpoint="/api/Service/TrackingNotes",
            payload=_to_sicon_tracking_note(ev),
        )
    except Exception as e:
        logger.warning("sicon push_event failed: %s", e)


async def push_time_entry(entry: dict, *, case_reference: str = "") -> None:
    try:
        e = {**entry, "case_reference": case_reference or entry.get("case_reference")}
        await _enqueue(
            organization_id=entry["organization_id"],
            kind="appointment",
            sicon_endpoint="/api/Service/Appointments",
            payload=_to_sicon_appointment(e),
        )
    except Exception as e:
        logger.warning("sicon push_time_entry failed: %s", e)


async def push_signature(sig: dict, *, case_reference: str = "") -> None:
    try:
        s = {**sig, "case_reference": case_reference or sig.get("case_reference")}
        await _enqueue(
            organization_id=sig["organization_id"],
            kind="signature",
            sicon_endpoint="/api/Service/Signatures",
            payload=_to_sicon_signature(s),
        )
    except Exception as e:
        logger.warning("sicon push_signature failed: %s", e)


async def push_attachment(photo: dict, *, case_reference: str = "") -> None:
    try:
        p = {**photo, "case_reference": case_reference or photo.get("case_reference")}
        await _enqueue(
            organization_id=photo["organization_id"],
            kind="attachment",
            sicon_endpoint="/api/Service/Attachments",
            payload=_to_sicon_attachment(p),
        )
    except Exception as e:
        logger.warning("sicon push_attachment failed: %s", e)


async def push_part_movement(movement: dict, *, case_reference: str = "") -> None:
    """Enqueue a stock movement (allocate / deallocate / consume / transfer / return / receive).

    Always non-blocking — failures are logged but never bubble up to the caller.
    """
    try:
        m = {**movement, "case_reference": case_reference or movement.get("case_reference")}
        await _enqueue(
            organization_id=movement["organization_id"],
            kind="part_movement",
            sicon_endpoint="/api/Service/StockMovements",
            payload=_to_sicon_part_movement(m),
        )
    except Exception as e:
        logger.warning("sicon push_part_movement failed: %s", e)


__all__ = [
    "push_case",
    "push_event",
    "push_time_entry",
    "push_signature",
    "push_attachment",
    "push_part_movement",
    "STATUS_CROSSWALK",
    "PRIORITY_CROSSWALK",
    "NOTE_TYPE_CROSSWALK",
    "PART_MOVEMENT_CROSSWALK",
    "COVER_NOMINAL",
]
