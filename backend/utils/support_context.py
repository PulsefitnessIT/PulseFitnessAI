"""
Ask Pulse Fitness — server-side context builder.

Given a user + page + entity_id, returns:
- `slice` — redacted projection fed to the LLM (no raw Mongo docs, no cross-tenant refs)
- `pill`  — short context string shown at the top of the support sheet ("You are viewing X · Y · Z")
- `allowed_entity_ids` — set of IDs the LLM is permitted to mention; post-hoc filter blocks
  anything outside this set to prevent hallucinated cross-tenant leakage
- `suggested_intents` — rendered as starter chips in the UI

Design rules
------------
- EVERY query is scoped to the caller's org_id. The UI cannot override org.
- PII is masked (email → `l***@pulsefitness.com`, phone → `020 ****1234`) BEFORE it
  reaches the LLM. The UI can reveal the real value if role allows.
- Retention: `support_context` docs live 15 min (TTL index). Never stored long-term.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.database import db


# ---------------------------- helpers -----------------------------------------

def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email or ""
    user, domain = email.split("@", 1)
    if len(user) <= 2:
        return f"{user[:1]}***@{domain}"
    return f"{user[:1]}***{user[-1:]}@{domain}"


def _mask_phone(phone: str) -> str:
    if not phone:
        return ""
    digits_only = "".join(c for c in phone if c.isdigit())
    if len(digits_only) < 6:
        return phone
    return f"{digits_only[:4]} ****{digits_only[-3:]}"


def _months_between(later: str, earlier: str) -> int:
    try:
        a = datetime.fromisoformat(later.replace("Z", "+00:00"))
        b = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
        return max(0, (a.year - b.year) * 12 + a.month - b.month)
    except Exception:
        return 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------- slice builders ----------------------------------

async def _equipment_slice(org_id: str, equipment_id: str) -> Optional[dict]:
    eq = await db.equipment.find_one({"id": equipment_id, "organization_id": org_id}, {"_id": 0})
    if not eq:
        return None
    faults = await _recent_equipment_faults(org_id, equipment_id)
    warranty_remaining = _warranty_remaining_months(eq)
    supplier = await _equipment_supplier_slice(org_id, eq.get("supplier_id"))
    return _assemble_equipment_slice(eq, faults, warranty_remaining, supplier)


async def _recent_equipment_faults(org_id: str, equipment_id: str) -> list[dict]:
    cutoff = (_now() - timedelta(days=60)).isoformat()
    return await db.issues.find(
        {"equipment_id": equipment_id, "organization_id": org_id, "created_at": {"$gte": cutoff}},
        {"_id": 0, "id": 1, "issue_description": 1, "severity": 1, "status": 1, "created_at": 1, "fault_code": 1},
    ).sort("created_at", -1).limit(20).to_list(length=20)


def _warranty_remaining_months(eq: dict) -> int:
    install_date = eq.get("install_date") or ""
    warranty_months = int(eq.get("warranty_months") or 0)
    if not (install_date and warranty_months):
        return 0
    age = _months_between(_now().isoformat(), install_date)
    return max(0, warranty_months - age)


async def _equipment_supplier_slice(org_id: str, supplier_id: Optional[str]) -> Optional[dict]:
    if not supplier_id:
        return None
    return await db.suppliers.find_one(
        {"id": supplier_id, "organization_id": org_id},
        {"_id": 0, "name": 1, "contact_person": 1, "avg_response_days": 1, "tier": 1},
    )


def _assemble_equipment_slice(eq: dict, faults: list[dict], warranty_remaining: int,
                              supplier: Optional[dict]) -> dict:
    return {
        "equipment_id": eq["id"],
        "display_name": f"{eq.get('machine_type', 'Equipment')} · {eq.get('serial_number', '')}",
        "machine_type": eq.get("machine_type"),
        "serial_number": eq.get("serial_number"),
        "install_date": eq.get("install_date") or "",
        "warranty_months": int(eq.get("warranty_months") or 0),
        "warranty_remaining_months": warranty_remaining,
        "status": eq.get("status"),
        "fault_count_60d": len(faults),
        "recent_fault_codes": [f.get("fault_code") for f in faults if f.get("fault_code")][:5],
        "recent_faults_summary": [
            {"date": f.get("created_at", "")[:10], "desc": (f.get("issue_description") or "")[:120],
             "severity": f.get("severity"), "status": f.get("status"), "fault_code": f.get("fault_code")}
            for f in faults[:5]
        ],
        "supplier": supplier,
    }


async def _fault_slice(org_id: str, fault_id: str) -> Optional[dict]:
    f = await db.issues.find_one({"id": fault_id, "organization_id": org_id}, {"_id": 0})
    if not f:
        return None
    eq_slice = None
    if f.get("equipment_id"):
        eq_slice = await _equipment_slice(org_id, f["equipment_id"])
    return {
        "fault_id": f["id"],
        "summary": (f.get("issue_description") or "")[:300],
        "severity": f.get("severity"),
        "status": f.get("status"),
        "created_at": f.get("created_at"),
        "ai_triage": (f.get("ai_triage") or "")[:500] if f.get("ai_triage") else None,
        "supplier_case_exists": bool(f.get("supplier_case")),
        "equipment": eq_slice,
    }


async def _org_summary_slice(org_id: str) -> dict:
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1, "account_type": 1, "branding": 1})
    open_faults = await db.issues.count_documents(
        {"organization_id": org_id, "status": {"$in": ["open", "in_progress"]}}
    )
    equipment_count = await db.equipment.count_documents({"organization_id": org_id})
    account_type = (org or {}).get("account_type") or ""
    is_pulse = account_type in ("pulse_pro", "lite")
    return {
        "org_name": (org or {}).get("name", ""),
        "account_type": account_type,
        "plan_tier": _plan_tier(account_type),  # "pro" | "lite" | "standard"
        "platform_name": "Pulse Fitness" if is_pulse else "Pulse Fitness",
        "assistant_name": "Pulse Fitness" if is_pulse else "Pulse Fitness",
        "is_pulse": is_pulse,
        "equipment_count": equipment_count,
        "open_faults_count": open_faults,
    }


def _plan_tier(account_type: str) -> str:
    if account_type == "pulse_pro":
        return "pro"
    if account_type == "lite":
        return "lite"
    return "standard"


# ---------------------------- public API --------------------------------------

async def build_support_context(
    user: dict,
    page: Optional[str] = None,
    entity_id: Optional[str] = None,
    entity_type: Optional[str] = None,
) -> dict:
    """Build a redacted support-context slice for the given user + page scope.

    Returns a dict: {slice, pill, allowed_entity_ids, suggested_intents}.
    """
    org_id = user.get("organization_id")
    if not org_id:
        org_summary = {"org_name": "", "account_type": "", "platform_name": "Pulse Fitness",
                       "equipment_count": 0, "open_faults_count": 0}
        return _empty_context(user, org_summary)

    org_summary = await _org_summary_slice(org_id)
    slice_data: dict = {"org": org_summary}
    allowed_ids: list[str] = [org_id]

    equipment_slice = await _maybe_equipment_slice(org_id, entity_id, entity_type)
    if equipment_slice:
        slice_data["equipment"] = equipment_slice
        allowed_ids.append(equipment_slice["equipment_id"])
        if equipment_slice.get("supplier"):
            slice_data["supplier"] = equipment_slice["supplier"]

    fault_slice = await _maybe_fault_slice(org_id, entity_id, entity_type)
    if fault_slice:
        slice_data["fault"] = fault_slice
        allowed_ids.append(fault_slice["fault_id"])
        if fault_slice.get("equipment"):
            slice_data["equipment"] = fault_slice["equipment"]
            allowed_ids.append(fault_slice["equipment"]["equipment_id"])

    return {
        "slice": slice_data,
        "pill": _build_pill(slice_data),
        "allowed_entity_ids": list(set(allowed_ids)),
        "suggested_intents": _build_suggested_intents(slice_data),
        "assistant_name": org_summary.get("assistant_name", "Pulse Fitness"),
        "plan_tier": org_summary.get("plan_tier", "standard"),
    }


def _empty_context(user: dict, org_summary: dict) -> dict:
    return {
        "slice": {"org": org_summary},
        "pill": org_summary.get("org_name", "Pulse Fitness"),
        "allowed_entity_ids": [],
        "suggested_intents": _default_intents(),
        "assistant_name": org_summary.get("assistant_name", "Pulse Fitness"),
        "plan_tier": org_summary.get("plan_tier", "standard"),
    }


async def _maybe_equipment_slice(org_id: str, entity_id: Optional[str], entity_type: Optional[str]) -> Optional[dict]:
    if entity_type == "equipment" and entity_id:
        return await _equipment_slice(org_id, entity_id)
    return None


async def _maybe_fault_slice(org_id: str, entity_id: Optional[str], entity_type: Optional[str]) -> Optional[dict]:
    if entity_type == "fault" and entity_id:
        return await _fault_slice(org_id, entity_id)
    return None


def _build_pill(slice_data: dict) -> str:
    eq = slice_data.get("equipment")
    fault = slice_data.get("fault")
    org = slice_data.get("org") or {}
    if fault:
        parts = [f"Fault · {fault.get('severity', 'unknown')}"]
        if fault.get("equipment"):
            parts.insert(0, fault["equipment"]["display_name"])
        return " · ".join(parts)
    if eq:
        pieces = [eq["display_name"]]
        if eq.get("warranty_remaining_months", 0) > 0:
            pieces.append(f"{eq['warranty_remaining_months']}mo warranty left")
        elif eq.get("warranty_months"):
            pieces.append("warranty expired")
        if eq.get("fault_count_60d", 0) > 0:
            pieces.append(f"{eq['fault_count_60d']} faults / 60d")
        return " · ".join(pieces)
    return org.get("org_name", "Pulse Fitness")


def _build_suggested_intents(slice_data: dict) -> list[dict]:
    if slice_data.get("equipment"):
        eq = slice_data["equipment"]
        intents = [
            {"id": "fault_explanation", "label": "Why has this machine been down?"},
            {"id": "warranty_check", "label": "Is this under warranty? How long left?"},
            {"id": "how_do_I", "label": "Log a fault for this machine"},
        ]
        if eq.get("fault_count_60d", 0) >= 3:
            intents[0]["label"] = f"Why {eq['fault_count_60d']} faults in 60 days?"
        if eq.get("warranty_remaining_months", 0) <= 3 and eq.get("warranty_remaining_months", 0) > 0:
            intents[1]["label"] = f"Warranty ends in {eq['warranty_remaining_months']}mo — what do I need to claim?"
        return intents
    if slice_data.get("fault"):
        return [
            {"id": "fault_explanation", "label": "What does this fault code mean?"},
            {"id": "message_supplier", "label": "Chase my supplier about this"},
            {"id": "warranty_check", "label": "Is this equipment under warranty?"},
        ]
    return _default_intents()


def _default_intents() -> list[dict]:
    return [
        {"id": "how_do_I", "label": "How do I log a new fault?"},
        {"id": "how_do_I", "label": "How do I add a supplier?"},
        {"id": "fault_explanation", "label": "Show me my top failing equipment"},
    ]
