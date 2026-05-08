"""Sicon field mapping reference table.

Complete mapping spec extracted from the GymAxis Executive Review
deck (page 12, iteration 221 — Apr 29 2026). 27 field pairs across
Cases, Contracts, Engineers, and Customers. This is the authoritative
list shown to master admins under Master Admin → Sicon → Mapping
so they can audit which GymAxis field flows into which Sicon column
for every sync.

Backed by a static module-level constant rather than a Mongo
collection because the mapping is part of the integration contract
(version-controlled with the code that does the mapping in
``utils/sicon_mappers.py``).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user


router = APIRouter()

# ── 27-row mapping table ────────────────────────────────────────────
# entity / gymaxis_field / sicon_field / direction / type / notes


SICON_FIELD_MAPPING: list[dict] = [
    # ── Cases (issues) ──────────────────────────────────────────────
    {"entity": "Case", "gymaxis_field": "issue.id",                "sicon_field": "case.GymAxisRef",       "direction": "→",   "type": "string",   "notes": "Round-trip identity. Stored on Sicon side for back-references."},
    {"entity": "Case", "gymaxis_field": "issue.title",             "sicon_field": "case.Description",       "direction": "→",   "type": "string",   "notes": "Truncated to 200 chars on Sicon side."},
    {"entity": "Case", "gymaxis_field": "issue.body",              "sicon_field": "case.LongDescription",   "direction": "→",   "type": "text",     "notes": "Full fault narrative, AI triage transcript prepended."},
    {"entity": "Case", "gymaxis_field": "issue.priority",          "sicon_field": "case.PriorityId",        "direction": "→",   "type": "enum",     "notes": "Mapped via priority_mapping config (low/medium/critical → numeric)."},
    {"entity": "Case", "gymaxis_field": "issue.status",            "sicon_field": "case.TrackingStatusId",  "direction": "↔",   "type": "enum",     "notes": "Bi-directional. Sicon → GymAxis updates set issue.status."},
    {"entity": "Case", "gymaxis_field": "issue.case_type",         "sicon_field": "case.CaseTypeId",        "direction": "→",   "type": "enum",     "notes": "Configurable per organisation."},
    {"entity": "Case", "gymaxis_field": "issue.assignee_engineer", "sicon_field": "case.EngineerId",        "direction": "↔",   "type": "ref",      "notes": "Sicon engineer roster pulled via /sicon/engineers."},
    {"entity": "Case", "gymaxis_field": "issue.created_at",        "sicon_field": "case.OpenedDate",        "direction": "→",   "type": "datetime", "notes": "ISO 8601 in UTC."},
    {"entity": "Case", "gymaxis_field": "issue.resolved_at",       "sicon_field": "case.ClosedDate",        "direction": "↔",   "type": "datetime", "notes": "Null until close. Sicon close pulls back."},
    {"entity": "Case", "gymaxis_field": "issue.location.id",       "sicon_field": "case.SiteId",            "direction": "→",   "type": "ref",      "notes": "Maps to Sicon site code (per-org config)."},
    {"entity": "Case", "gymaxis_field": "issue.equipment.id",      "sicon_field": "case.EquipmentRef",      "direction": "→",   "type": "ref",      "notes": "Optional. Pre-populated from QR scan or fault trace."},
    {"entity": "Case", "gymaxis_field": "issue.notes[]",           "sicon_field": "case.Notes",             "direction": "→",   "type": "list",     "notes": "Each new note pushed via /sicon/add-note."},
    {"entity": "Case", "gymaxis_field": "issue.appointments[]",    "sicon_field": "case.Appointments",      "direction": "↔",   "type": "list",     "notes": "Two-way schedule sync."},
    {"entity": "Case", "gymaxis_field": "issue.org.id",            "sicon_field": "case.CustomerId",        "direction": "→",   "type": "ref",      "notes": "Org → Sicon customer mapping."},

    # ── Contracts ───────────────────────────────────────────────────
    {"entity": "Contract", "gymaxis_field": "contract.id",            "sicon_field": "contract.GymAxisRef",   "direction": "→",   "type": "string",   "notes": "Identity round-trip."},
    {"entity": "Contract", "gymaxis_field": "contract.name",          "sicon_field": "contract.Title",        "direction": "→",   "type": "string",   "notes": ""},
    {"entity": "Contract", "gymaxis_field": "contract.start_date",    "sicon_field": "contract.StartDate",    "direction": "→",   "type": "date",     "notes": "ISO 8601."},
    {"entity": "Contract", "gymaxis_field": "contract.end_date",      "sicon_field": "contract.EndDate",      "direction": "→",   "type": "date",     "notes": ""},
    {"entity": "Contract", "gymaxis_field": "contract.value_pence",   "sicon_field": "contract.AnnualValue",  "direction": "→",   "type": "money",    "notes": "Stored minor units in GymAxis, GBP major in Sicon."},
    {"entity": "Contract", "gymaxis_field": "contract.lines[]",       "sicon_field": "contract.Lines",        "direction": "→",   "type": "list",     "notes": "Each line item pushed via /sicon/sync-contract-line."},
    {"entity": "Contract", "gymaxis_field": "contract.org.id",        "sicon_field": "contract.CustomerId",   "direction": "→",   "type": "ref",      "notes": ""},
    {"entity": "Contract", "gymaxis_field": "contract.renewal_date",  "sicon_field": "contract.RenewalDate",  "direction": "→",   "type": "date",     "notes": "Drives auto-renewal reminders on both sides."},

    # ── Engineers / Resources ──────────────────────────────────────
    {"entity": "Engineer", "gymaxis_field": "engineer.id",            "sicon_field": "resource.Id",            "direction": "←",   "type": "ref",      "notes": "Pulled via /sicon/engineers/refresh."},
    {"entity": "Engineer", "gymaxis_field": "engineer.full_name",     "sicon_field": "resource.Name",          "direction": "←",   "type": "string",   "notes": ""},
    {"entity": "Engineer", "gymaxis_field": "engineer.email",         "sicon_field": "resource.Email",         "direction": "←",   "type": "string",   "notes": "Used for in-app deep-links."},

    # ── Customers / Organisations ──────────────────────────────────
    {"entity": "Customer", "gymaxis_field": "organization.id",        "sicon_field": "customer.Id",            "direction": "↔",   "type": "ref",      "notes": "Two-way map maintained by integration ops."},
    {"entity": "Customer", "gymaxis_field": "organization.name",      "sicon_field": "customer.Name",          "direction": "→",   "type": "string",   "notes": "Push-only on first sync; manual edits live in Sicon thereafter."},
]


@router.get("/sicon/field-mapping")
async def get_sicon_field_mapping(user: dict = Depends(get_current_user)) -> dict:
    """Return the full Sicon field mapping table for the Master Admin
    Sicon panel. Master-admin only — this exposes integration internals."""
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(403, "Master admin only")
    # Group by entity for the UI's tabbed/grouped table layout.
    grouped: dict[str, list[dict]] = {}
    for row in SICON_FIELD_MAPPING:
        grouped.setdefault(row["entity"], []).append(row)
    return {
        "mappings": SICON_FIELD_MAPPING,
        "grouped": grouped,
        "total": len(SICON_FIELD_MAPPING),
        "entities": list(grouped.keys()),
    }
