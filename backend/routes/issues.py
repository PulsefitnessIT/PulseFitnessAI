from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Body
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid
import asyncio
import logging

from utils.database import db, EMERGENT_LLM_KEY, RESEND_API_KEY, SENDER_EMAIL, APP_NAME, put_object
from utils.auth import get_current_user, get_organization_filter, apply_site_lock
from utils.ai_access import require_ai_access
from models.schemas import IssueCreate, IssueBatchCreate, ServiceRequest
from emergentintegrations.llm.chat import LlmChat, UserMessage

from routes.issue_helpers import (
    build_triage_system_message, build_triage_prompt, append_past_fixes,
    format_knowledge_context, call_ai_with_retry, parse_ai_json,
    build_fallback_triage, store_fix_history, handle_engineer_escalation,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# When a machine is still under manufacturer warranty, DIY repairs can
# invalidate the cover. The triage must lead with manual guidance + a
# manufacturer referral BEFORE offering hands-on AI repair steps.
WARRANTY_TRIAGE_ADDENDUM = (
    "\n\nWARRANTY-PROTECTION PROTOCOL (this machine is still under the "
    "manufacturer's warranty):\n"
    "1. FIRST, surface any relevant recommendations from the manufacturer's "
    "manuals / knowledge provided. If the manual covers this fault, quote it.\n"
    "2. THEN strongly advise the operator to contact the manufacturer or an "
    "authorised service agent before carrying out ANY physical repair, because "
    "self-repair may invalidate the warranty. Make this the headline action.\n"
    "3. ONLY AFTER that, provide the AI triage as informational guidance to help "
    "the operator describe the fault to the manufacturer. Keep can_fix_onsite "
    "false unless the step is a non-invasive check (e.g. confirming it's plugged "
    "in, reading an error code) that cannot affect the warranty.\n"
    "Begin your diagnosis text with a clear line: 'Under manufacturer warranty — "
    "contact the manufacturer / authorised agent before repair.'"
)

try:
    import resend
except ImportError:
    resend = None


@router.get("/issues/coverage-lookup")
async def coverage_lookup(
    serial_number: str = "",
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216h199 — Phase 3 pre-flight coverage check.

    Frontend calls this just before showing the "Log fault" CTA so the
    user sees "✓ Under GOLD contract until 31/12/2027" inline. Backend
    intake also re-resolves the same data, so this is purely a UX hint —
    no security implications.
    """
    if not serial_number or not serial_number.strip():
        raise HTTPException(status_code=400, detail="serial_number required")
    meta = await _resolve_coverage_for_issue(
        serial_number=serial_number, organization_id=user.get("organization_id"),
    )
    return meta



@router.post("/issues/triage")
async def triage_issue(issue: IssueCreate, user: dict = Depends(require_ai_access)) -> dict:
    try:
        # Auto-warranty check: if this machine is still under manufacturer
        # warranty, the triage must lead with manual guidance + a manufacturer
        # referral so the operator doesn't invalidate the cover with a DIY fix.
        coverage = await _resolve_coverage_for_issue(
            issue.serial_number, user.get("organization_id"),
        )
        in_warranty = bool(coverage.get("warranty_active"))
        warranty_expiry = coverage.get("warranty_expiry")
        warranty_expiry_display = (warranty_expiry or "").split("T")[0]

        system_message = build_triage_system_message(issue.language)
        if in_warranty:
            system_message += WARRANTY_TRIAGE_ADDENDUM

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"triage_{datetime.now().timestamp()}",
            system_message=system_message,
        ).with_model("openai", "gpt-5.2")

        prompt = build_triage_prompt(issue)
        prompt = await append_past_fixes(prompt, issue.machine_type, user.get('organization_id'))

        knowledge_docs = await _fetch_relevant_knowledge(issue.machine_type, issue.supplier, user.get('organization_id'))
        prompt += format_knowledge_context(knowledge_docs)
        if in_warranty:
            prompt += (
                "\n\nNOTE: This machine IS under manufacturer warranty"
                + (f" (expires {warranty_expiry_display})." if warranty_expiry_display else ".")
                + " Apply the WARRANTY-PROTECTION PROTOCOL from your instructions."
            )
        prompt += "\n\nPerform triage and provide structured repair steps."

        raw_result = await call_ai_with_retry(chat, UserMessage(text=prompt))
        parsed = parse_ai_json(raw_result)

        # Validate AI-suggested fault_code against the taxonomy (drop if unknown/null)
        from constants.fault_codes import VALID_FAULT_CODES
        suggested_code = parsed.get('fault_code')
        if suggested_code and suggested_code not in VALID_FAULT_CODES:
            suggested_code = None

        # Build a warranty notice the UI shows ABOVE the triage steps, and never
        # let the AI push an on-site fix while the machine is under warranty.
        warranty_notice = None
        can_fix_onsite = parsed.get('can_fix_onsite', False)
        if in_warranty:
            can_fix_onsite = False
            warranty_notice = {
                "in_warranty": True,
                "warranty_expiry": warranty_expiry,
                "warranty_days_remaining": coverage.get("warranty_days_remaining"),
                "title": "Under manufacturer warranty",
                "message": (
                    "This machine is under manufacturer warranty"
                    + (f" until {warranty_expiry_display}" if warranty_expiry_display else "")
                    + ". Check the manufacturer's manual first and contact the "
                    "manufacturer or an authorised service agent before any repair — "
                    "carrying out your own repair may invalidate the warranty."
                ),
            }

        return {
            "diagnosis": parsed.get('diagnosis', ''),
            "can_fix_onsite": can_fix_onsite,
            "repair_steps": parsed.get('repair_steps', []),
            "tools_needed": parsed.get('tools_needed', []),
            "estimated_time": parsed.get('estimated_time', 'Unknown'),
            "engineer_reason": parsed.get('engineer_reason'),
            "severity_assessment": parsed.get('severity_assessment', issue.severity),
            "fault_code": suggested_code,
            "warranty_active": in_warranty,
            "warranty_notice": warranty_notice,
            "raw_triage": raw_result,
        }
    except Exception as e:
        logger.error(f"AI triage failed: {e}")
        return build_fallback_triage(issue.severity, str(e).lower())


def _derive_issue_defaults(issue: IssueCreate) -> tuple[str, str, str, str]:
    """Derive (status, fault_type, sla_category, resolved_by) from the inbound issue."""
    is_self_fix = issue.resolution_type == "self_fix"
    is_engineer = issue.resolution_type == "engineer"
    status = "resolved" if is_self_fix else "open"
    fault_type = getattr(issue, 'fault_type', None) or (
        "safety_critical" if issue.severity == "safety_critical" else "standard"
    )
    sla_category = getattr(issue, 'sla_category', None) or "standard"
    resolved_by = "gymaxis_ai" if is_self_fix else ("engineer" if is_engineer else None)
    return status, fault_type, sla_category, resolved_by


def _build_issue_doc(issue: IssueCreate, user: dict) -> dict:
    """Build an issue document from input data."""
    from utils.security import sanitise_string
    status, fault_type, sla_category, resolved_by = _derive_issue_defaults(issue)
    now = datetime.now(timezone.utc).isoformat()
    # Iter 216h115 — Classification scan. Runs for every tenant (cheap,
    # pure-function regex). For MOD users we additionally surface the
    # flags in the response and email HQ for review elsewhere. For
    # non-MOD users it's defensive logging.
    classification_flags: list[dict] = []
    try:
        from utils.mod_classification import scan_many
        classification_flags = scan_many([
            issue.issue_description, issue.steps_taken,
        ])
    except Exception:  # pragma: no cover
        classification_flags = []
    return {
        "id": str(uuid.uuid4()),
        # Iter 216d — job_id groups sibling issues logged together. Falls
        # back to None for legacy single-machine flows so old clients keep
        # working unchanged.
        "job_id": getattr(issue, "job_id", None),
        "user_id": user['id'],
        "organization_id": user.get('organization_id'),
        "created_by_name": user.get('full_name'),
        "serial_number": issue.serial_number,
        "machine_type": sanitise_string(issue.machine_type or ""),
        "issue_description": sanitise_string(issue.issue_description or ""),
        "severity": issue.severity,
        "fault_type": fault_type,
        "sla_category": sla_category,
        "supplier": sanitise_string(issue.supplier or ""),
        "steps_taken": sanitise_string(issue.steps_taken or ""),
        "status": status,
        "resolution_type": issue.resolution_type,
        "resolution_note": issue.resolution_note,
        "resolved_by": resolved_by,
        "ai_triage": issue.ai_triage,
        "can_fix_onsite": issue.can_fix_onsite,
        "selected_fix_step": issue.selected_fix_step,
        "selected_fix_title": issue.selected_fix_title,
        "fix_method": issue.fix_method,
        "fault_code": issue.fault_code,
        # Iter 220dt — Job-type taxonomy + serial-unknown escape
        # hatch. Both propagate into the mirrored svc_case via
        # ``_mirror_issue_to_svc_case``.
        "case_type": (getattr(issue, "case_type", None) or "repair"),
        "serial_unknown": bool(getattr(issue, "serial_unknown", False)),
        "serial_unknown_reason": sanitise_string(
            getattr(issue, "serial_unknown_reason", "") or "",
        ) or None,
        # KPI timestamps (auto-captured)
        "created_at": now,
        "updated_at": now,
        "resolved_at": now if status == "resolved" else None,
        "engineer_assigned_at": None,
        "engineer_arrived_at": None,
        "work_started_at": None,
        "work_completed_at": None,
        "first_response_at": None,
        # Engineer activity
        "parts_used": [],
        "engineer_notes": None,
        "safety_checks_passed": None,
        # Iter 216h115 — classification scan persisted for audit.
        "classification_flags": classification_flags,
        "classification_flagged": bool(classification_flags),
        # Timeline
        "timeline": [{"event": "fault_logged", "timestamp": now, "by": user.get("full_name", "")}],
    }


async def _publish_issue_event(issue_doc: dict, user: dict):
    """Publish service issue created event to integration hub (best-effort)."""
    try:
        from routes.integration_hub import publish_event
        await publish_event(
            event_type="service_issue_created", source_system="service_portal", target_system="crm",
            entity_type="service_case", entity_id=issue_doc["id"],
            payload={
                "issue_id": issue_doc["id"], "title": issue_doc.get("machine_type", "Service Issue"),
                "description": issue_doc.get("issue_description", ""),
                "priority": issue_doc.get("severity", "medium"),
                "equipment_name": issue_doc.get("machine_type", ""),
                "organization_name": user.get("organization_name", ""),
            },
            organization_id=user.get("organization_id", ""),
            triggered_by=user.get("full_name", "system"),
        )
    except Exception:
        pass


def _severity_to_priority(severity: Optional[str]) -> str:
    """Map ops-portal severity buckets to Service Desk priority codes."""
    s = (severity or "").lower()
    if s in ("safety_critical", "critical"):
        return "p1"
    if s in ("operational_major", "major", "high"):
        return "p2"
    if s in ("operational_minor", "minor", "medium"):
        return "p3"
    return "p4"


async def _resolve_coverage_for_issue(serial_number: Optional[str],
                                      organization_id: Optional[str]) -> dict:
    """Iter 216h199 — Phase 3 auto-warranty-check.

    Resolves the manufacturer warranty + CRM aftersales contract coverage
    for the equipment matching `serial_number` in `organization_id`, so the
    Service Desk case (and the underlying issue row) get auto-flagged with
    cover_type + contract reference at intake time.

    Returns `coverage_to_case_meta` flat dict shape — caller can spread
    it directly into the issue / svc_case docs. Defensive: never raises;
    on lookup miss returns an "uncovered" meta block.
    """
    from utils.coverage import resolve_equipment_coverage, coverage_to_case_meta
    serial = (serial_number or "").strip()
    if not serial or not organization_id:
        return coverage_to_case_meta({})  # uncovered shape
    try:
        equip = await db.equipment.find_one(
            {"organization_id": organization_id,
             "$or": [{"serial_number": serial}, {"name": serial}]},
            {"_id": 0},
        )
        if not equip:
            return coverage_to_case_meta({})
        cov = await resolve_equipment_coverage(equip, db)
        meta = coverage_to_case_meta(cov)
        # Stamp the resolved equipment id too, so downstream code doesn't
        # have to re-resolve.
        meta["equipment_id"] = equip.get("id") or ""
        # Iter 216h208 — stamp equipment's site_id so the issue can
        # inherit it. Without this the new fault is invisible to a
        # dashboard filtered to that site (e.g. admin viewing /pulse
        # with a SiteSwitcher selection).
        meta["equipment_site_id"] = equip.get("site_id") or None
        return meta
    except Exception as e:  # pragma: no cover — defensive only
        logger.warning(f"_resolve_coverage_for_issue failed: {e}")
        return coverage_to_case_meta({})


async def _mirror_issue_to_svc_case(issue_doc: dict, user: dict) -> None:
    """Bridge: when an Operations Portal fault is escalated to engineer
    (resolution_type='engineer'), materialise an `svc_cases` row so the
    Service Desk team see Pulse Fitness fault logs in their queue.

    Best-effort — never blocks the issue write. Idempotent on (issue_id).
    """
    try:
        if (issue_doc.get("resolution_type") or "") != "engineer":
            return
        # Skip if a case already exists for this issue (replay safe).
        existing = await db.svc_cases.find_one(
            {"organization_id": issue_doc.get("organization_id"), "source_meta.issue_id": issue_doc["id"]},
            {"_id": 0, "id": 1},
        )
        if existing:
            return
        # Resolve site context from the equipment serial when possible.
        site_id = ""
        site_name = ""
        site_postcode = ""
        equipment_id = ""
        try:
            equip = await db.equipment.find_one(
                {"organization_id": issue_doc.get("organization_id"),
                 "$or": [{"serial_number": issue_doc.get("serial_number")},
                         {"name": issue_doc.get("serial_number")}]},
                {"_id": 0, "id": 1, "site_id": 1, "name": 1},
            )
            if equip:
                equipment_id = equip.get("id") or ""
                site_id = equip.get("site_id") or ""
                if site_id:
                    site = await db.sites.find_one(
                        {"id": site_id}, {"_id": 0, "name": 1, "postcode": 1, "address": 1},
                    )
                    if site:
                        site_name = site.get("name") or ""
                        site_postcode = site.get("postcode") or ""
        except Exception:
            pass

        # Build the bridged intake payload and reuse the canonical creator.
        from routes.svc.intake import _create_case as _svc_create_case
        priority = _severity_to_priority(issue_doc.get("severity"))
        # Iter 216h199 — auto-routed cover_type + contract reference,
        # resolved at issue intake. Falls back to "contract" (the pre-h199
        # default) only when nothing was stamped (legacy issues).
        cov_meta = issue_doc.get("coverage_meta") or {}
        resolved_cover = cov_meta.get("cover_type") or "contract"
        payload = {
            "title": issue_doc.get("machine_type") or "Operations Portal fault",
            "description": issue_doc.get("issue_description") or "",
            "priority": priority,
            "cover_type": resolved_cover,
            # Iter 220dt — propagate the customer's chosen job-type
            # (Repair / PPM / Install / Inspection / Callout / Audit)
            # so the engineer Summary chip and downstream reporting
            # both see it. Defaults to "repair" when the legacy form
            # didn't pick one.
            "case_type": issue_doc.get("case_type") or "repair",
            "site_id": site_id,
            "site_name": site_name,
            "site_postcode": site_postcode,
            "asset_id": equipment_id,
            "asset_name": issue_doc.get("machine_type") or "",
            "equipment_ids": [equipment_id] if equipment_id else [],
            "equipment_serials": [issue_doc.get("serial_number") or ""] if issue_doc.get("serial_number") else [],
            "fault_code": issue_doc.get("fault_code") or "",
            "contract_id": cov_meta.get("contract_id") or "",
            "customer_name": user.get("full_name") or "",
            "customer_email": user.get("email") or "",
            "customer_phone": user.get("phone") or "",
            # Iter 220dt — Serial-unknown escape hatch (rubbed-off
            # plate etc). Triggers an engineer-side "Capture serial
            # on visit 1" follow-up task; never blocks intake.
            "capture_serial_required": bool(issue_doc.get("serial_unknown")),
            "capture_serial_reason": issue_doc.get("serial_unknown_reason") or None,
            "source_meta": {
                "issue_id": issue_doc["id"],
                "channel": "operations_portal",
                "severity": issue_doc.get("severity"),
                # Iter 220dt — keep the case_type slug on the audit
                # trail too so we can re-key historic data later.
                "case_type": issue_doc.get("case_type") or "repair",
                "serial_unknown": bool(issue_doc.get("serial_unknown")),
                "serial_unknown_reason": issue_doc.get("serial_unknown_reason") or "",
                # Iter 216h199 — full coverage snapshot so the Service
                # Desk UI can render "✓ Under GOLD contract until
                # 31/12/2027" badges without a second round-trip.
                "coverage_status": cov_meta.get("coverage_status", "uncovered"),
                "contract_number": cov_meta.get("contract_number", ""),
                "contract_title": cov_meta.get("contract_title", ""),
                "contract_tier": cov_meta.get("contract_tier", ""),
                "contract_end_date": cov_meta.get("contract_end_date", ""),
                "contract_coverage_type": cov_meta.get("contract_coverage_type", ""),
                "contract_expiring_soon": cov_meta.get("contract_expiring_soon", False),
                "warranty_active": cov_meta.get("warranty_active", False),
                "warranty_expiry": cov_meta.get("warranty_expiry"),
            },
        }
        await _svc_create_case(payload=payload, source="portal", user=user)
    except Exception as e:
        logger.warning(f"_mirror_issue_to_svc_case failed: {e}")


async def _mirror_job_to_svc_case(issue_docs: list[dict], job_id: str, user: dict) -> None:
    """Iter 216d — bundle a multi-machine fault job into ONE svc_case.

    Used by the batch-issues endpoint. If at least one sibling is
    escalated to engineer, we create a SINGLE svc_case row stamped with
    the job_id and listing every machine's id + serial — so the
    supplier receives one email covering all machines, not N near-
    identical messages.

    Idempotent: if a case already exists for this job_id, do nothing
    (replay-safe).
    """
    try:
        engineer_docs = [d for d in issue_docs if (d.get("resolution_type") or "") == "engineer"]
        if not engineer_docs:
            return

        existing = await db.svc_cases.find_one(
            {"organization_id": user.get("organization_id"), "source_meta.job_id": job_id},
            {"_id": 0, "id": 1},
        )
        if existing:
            return

        # Resolve site context from the FIRST engineer-escalated machine.
        # All siblings are typically at the same site for a single fault
        # job, but if not, the svc_case still ships and the case detail
        # page lists every equipment_id so the engineer can route.
        first = engineer_docs[0]
        site_id = ""
        site_name = ""
        site_postcode = ""
        try:
            equip = await db.equipment.find_one(
                {"organization_id": first.get("organization_id"),
                 "$or": [{"serial_number": first.get("serial_number")},
                         {"name": first.get("serial_number")}]},
                {"_id": 0, "site_id": 1},
            )
            if equip and equip.get("site_id"):
                site_id = equip["site_id"]
                site = await db.sites.find_one(
                    {"id": site_id}, {"_id": 0, "name": 1, "postcode": 1},
                )
                if site:
                    site_name = site.get("name") or ""
                    site_postcode = site.get("postcode") or ""
        except Exception:
            pass

        # Collect every equipment id + serial that's part of the job.
        equipment_ids: list[str] = []
        equipment_serials: list[str] = []
        for doc in engineer_docs:
            sn = (doc.get("serial_number") or "").strip()
            if sn and sn not in equipment_serials:
                equipment_serials.append(sn)
            try:
                eq = await db.equipment.find_one(
                    {"organization_id": doc.get("organization_id"),
                     "$or": [{"serial_number": sn}, {"name": sn}]},
                    {"_id": 0, "id": 1},
                )
                if eq and eq.get("id") and eq["id"] not in equipment_ids:
                    equipment_ids.append(eq["id"])
            except Exception:
                pass

        # Description rolls up every machine's individual issue note so
        # the supplier sees a clear "what's wrong with each one" list.
        lines = [f"Fault job covering {len(engineer_docs)} machine(s):", ""]
        for d in engineer_docs:
            lines.append(
                f"  • {d.get('machine_type', '?')} — SN {d.get('serial_number', '?')}: "
                f"{d.get('issue_description', '(no description)')}"
            )
        rolled_up = "\n".join(lines)

        # Take the most-severe priority across siblings — engineers
        # need to triage to the worst machine on the job.
        priorities = [_severity_to_priority(d.get("severity")) for d in engineer_docs]
        # p1 < p2 < p3 < p4 alphabetically — `min` works.
        priority = min(priorities) if priorities else "p4"

        from routes.svc.intake import _create_case as _svc_create_case
        # Iter 216h199 — pick the strongest coverage across siblings.
        # If ANY machine on the job has a CRM contract, route the case as
        # "contract". Else if ANY is in warranty, "warranty". Else
        # "chargeable". This matches operator intuition — one mixed job
        # on a Gold contract shouldn't get billed.
        sibling_metas = [d.get("coverage_meta") or {} for d in engineer_docs]
        statuses = [m.get("coverage_status", "uncovered") for m in sibling_metas]
        if "covered_contract" in statuses:
            bundled_cover = "contract"
            primary = next(m for m in sibling_metas if m.get("coverage_status") == "covered_contract")
        elif "covered_warranty" in statuses:
            bundled_cover = "warranty"
            primary = next(m for m in sibling_metas if m.get("coverage_status") == "covered_warranty")
        else:
            bundled_cover = "chargeable"
            primary = sibling_metas[0] if sibling_metas else {}

        payload = {
            "title": (
                f"{first.get('machine_type') or 'Operations Portal fault'}"
                f"{' + ' + str(len(engineer_docs) - 1) + ' more' if len(engineer_docs) > 1 else ''}"
            ),
            "description": rolled_up,
            "priority": priority,
            "cover_type": bundled_cover,
            "site_id": site_id,
            "site_name": site_name,
            "site_postcode": site_postcode,
            "asset_id": equipment_ids[0] if equipment_ids else "",
            "asset_name": first.get("machine_type") or "",
            "equipment_ids": equipment_ids,
            "equipment_serials": equipment_serials,
            "fault_code": first.get("fault_code") or "",
            "contract_id": primary.get("contract_id") or "",
            "customer_name": user.get("full_name") or "",
            "customer_email": user.get("email") or "",
            "customer_phone": user.get("phone") or "",
            "source_meta": {
                "job_id": job_id,
                "issue_ids": [d["id"] for d in engineer_docs],
                "channel": "operations_portal",
                "severity": first.get("severity"),
                "machine_count": len(engineer_docs),
                "coverage_status": primary.get("coverage_status", "uncovered"),
                "contract_number": primary.get("contract_number", ""),
                "contract_title": primary.get("contract_title", ""),
                "contract_tier": primary.get("contract_tier", ""),
                "contract_end_date": primary.get("contract_end_date", ""),
                "contract_coverage_type": primary.get("contract_coverage_type", ""),
                "contract_expiring_soon": primary.get("contract_expiring_soon", False),
                "warranty_active": primary.get("warranty_active", False),
                "warranty_expiry": primary.get("warranty_expiry"),
            },
        }
        await _svc_create_case(payload=payload, source="portal", user=user)
    except Exception as e:
        logger.warning(f"_mirror_job_to_svc_case failed: {e}")


async def _resolve_fault_supplier(issue_doc: dict, org_id: str) -> Optional[dict]:
    """Iter 220ea·39 — resolve which supplier a logged fault should be
    dispatched to, in priority order (option C):

      1. The supplier set against the *faulted machine* (equipment.supplier
         / supplier_id) — this is the intuitive "the machine's supplier gets
         the fault" behaviour the operator expects.
      2. The supplier named on the fault itself (issue.supplier).
      3. The org's primary `auto_dispatch` supplier (typically the Partner
         Engineer who referred them) — the original fallback.

    Only ever returns a supplier that has a non-empty email (we can't send a
    card to log the job without one). Returns ``None`` to skip silently.
    """
    proj = {"_id": 0, "id": 1, "name": 1, "email": 1, "partner_engineer_id": 1}

    # 1) Supplier set against the faulted machine.
    equip = None
    equip_id = (issue_doc.get("coverage_meta") or {}).get("equipment_id")
    if equip_id:
        equip = await db.equipment.find_one(
            {"id": equip_id, "organization_id": org_id},
            {"_id": 0, "supplier": 1, "supplier_id": 1},
        )
    if not equip and (issue_doc.get("serial_number") or "").strip():
        serial = issue_doc["serial_number"].strip()
        equip = await db.equipment.find_one(
            {"organization_id": org_id,
             "$or": [{"serial_number": serial}, {"name": serial}]},
            {"_id": 0, "supplier": 1, "supplier_id": 1},
        )
    if equip:
        if (equip.get("supplier_id") or "").strip():
            s = await db.suppliers.find_one(
                {"id": equip["supplier_id"], "organization_id": org_id, "email": {"$ne": ""}}, proj)
            if s:
                return s
        if (equip.get("supplier") or "").strip():
            s = await db.suppliers.find_one(
                {"organization_id": org_id, "name": equip["supplier"], "email": {"$ne": ""}}, proj)
            if s:
                return s

    # 2) Supplier named on the fault.
    fault_supplier = (issue_doc.get("supplier") or "").strip()
    if fault_supplier:
        s = await db.suppliers.find_one(
            {"organization_id": org_id, "name": fault_supplier, "email": {"$ne": ""}}, proj)
        if s:
            return s

    # 3) Org's primary auto-dispatch supplier (partner-referral default).
    return await db.suppliers.find_one(
        {"organization_id": org_id, "auto_dispatch": True, "email": {"$ne": ""}},
        proj, sort=[("is_primary_supplier", -1), ("created_at", 1)],
    )


async def _auto_dispatch_to_primary_supplier(issue_doc: dict, user: dict) -> None:
    """Iter 220ea·39 — on fault submit, automatically create the supplier
    "card to log the job" and **email** it to the right supplier so they can
    accept/schedule the work — no human in the loop.

    Supplier resolution is machine-first with fallbacks (see
    ``_resolve_fault_supplier``). Fires for any *open* (unresolved) fault;
    self-fixed faults are already closed so they're skipped. Silently does
    nothing when no supplier with an email can be resolved.

    Idempotent — one supplier case per fault (keyed by ``issue_id``); safe
    against retries and the multi-machine batch flow.
    """
    try:
        # Only dispatch open faults. Self-fixed faults are already resolved.
        if (issue_doc.get("status") or "") != "open":
            return
        org_id = issue_doc.get("organization_id")
        issue_id = issue_doc.get("id")
        if not org_id or not issue_id:
            return
        # Replay-safe: one supplier case per fault.
        if await db.supplier_cases.find_one({"issue_id": issue_id}, {"_id": 0, "id": 1}):
            return
        supplier = await _resolve_fault_supplier(issue_doc, org_id)
        if not supplier or not (supplier.get("email") or "").strip():
            return
        # Resolve org name for the supplier-facing case page.
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "name": 1})
        org_name = (org or {}).get("name") or "Customer"

        # Create the supplier case (portal + token) and email the supplier a
        # first message so the "card to log the job" lands in their inbox.
        from routes.purchase_orders import _ensure_supplier_case
        case = await _ensure_supplier_case(
            issue_id, supplier.get("name") or "Service Supplier",
            supplier["email"], org_name, user,
        )
        machine = issue_doc.get("machine_type") or "the equipment"
        desc = (issue_doc.get("issue_description") or "").strip()
        body = f"New fault logged for {machine}" + (f": {desc}." if desc else ".")
        body += " Please review the details and log the job in your supplier portal."
        comment = {
            "id": str(uuid.uuid4()), "case_id": case["id"],
            "author_name": user.get("full_name") or "Site Staff", "author_role": "gym",
            "message": body, "attachments": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.supplier_case_comments.insert_one(comment)
        if case.get("supplier_email"):
            try:
                from routes.supplier_portal import _send_comment_notification
                await _send_comment_notification(case, comment, to_supplier=True)
            except Exception as mail_err:
                # Delivery failure must not undo the dispatch — the supplier
                # card still exists and the portal link works.
                logger.warning(f"supplier dispatch email failed: {mail_err}")

        # Tag the issue so the dashboard can render the "dispatched to
        # <supplier>" badge without a second lookup.
        await db.issues.update_one(
            {"id": issue_id},
            {"$set": {
                "auto_dispatched_supplier_id": supplier.get("id"),
                "auto_dispatched_supplier_name": supplier.get("name"),
                "auto_dispatched_supplier_email": supplier["email"],
                "auto_dispatched_partner_engineer_id": supplier.get("partner_engineer_id"),
                "auto_dispatched_at": datetime.now(timezone.utc).isoformat(),
                "supplier_case_token": case.get("token"),
            }},
        )
    except Exception as e:
        # Never block intake on a dispatch failure.
        logger.warning(f"_auto_dispatch_to_primary_supplier failed: {e}")



@router.post("/issues")
async def create_issue(issue: IssueCreate, user: dict = Depends(get_current_user)) -> dict:
    issue_doc = _build_issue_doc(issue, user)
    # Iter 216h199 — Phase 3 auto-warranty-check: stamp coverage meta on
    # the issue row at intake. The downstream svc_case mirror reuses
    # the same meta so the Service Desk case is pre-routed correctly.
    coverage_meta = await _resolve_coverage_for_issue(
        issue.serial_number, user.get("organization_id"),
    )
    issue_doc["coverage_meta"] = coverage_meta
    # Iter 216h208 — inherit site_id from the matched equipment so the
    # fault is visible to a dashboard scoped to that site. Was silently
    # missing on every new issue, so operators with an active site
    # selected reported "fault logged but not on the screen".
    site_id_from_equip = coverage_meta.get("equipment_site_id") if isinstance(coverage_meta, dict) else None
    if site_id_from_equip:
        issue_doc["site_id"] = site_id_from_equip
    await db.issues.insert_one(issue_doc)
    issue_doc.pop('_id', None)

    await store_fix_history(issue, issue_doc['id'], user)
    await handle_engineer_escalation(issue, issue_doc, user)
    await _publish_issue_event(issue_doc, user)
    # Bridge: if escalated to engineer, mirror to Service Desk (best-effort).
    await _mirror_issue_to_svc_case(issue_doc, user)
    # Iter 220n — auto-dispatch to the gym's primary service supplier
    # (set up either by the gym manually OR auto-attached when they
    # signed up with a Partner Engineer's referral code). Best-effort —
    # never blocks intake.
    await _auto_dispatch_to_primary_supplier(issue_doc, user)

    # Iter 216h227 — Operations trial first-win milestone for logging
    # the org's very first fault. Best-effort — never block intake.
    try:
        from routes.activation_events import record_activation_event
        await record_activation_event(
            user.get("organization_id"), "first_fault_logged",
            trigger_user_id=user.get("id"),
            payload={"issue_id": issue_doc.get("id")},
        )
    except Exception:
        pass

    return issue_doc


@router.post("/issues/batch")
async def create_issues_batch(
    payload: IssueBatchCreate,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216d — log multiple machines under one fault job.

    Each entry in `payload.machines` becomes its own `db.issues` row so
    SLA, status transitions, and reports stay per-machine. The shared
    `job_id` (server-generated if omitted) glues them together for the
    grouped fault-list view and the bundled supplier-email path.

    The svc_case mirror is invoked ONCE for the whole job (with all
    sibling machines attached) instead of N times — so Pulse Pro
    suppliers receive a single message listing every machine on the
    job rather than a flood of N near-identical emails.
    """
    if not payload.machines:
        raise HTTPException(status_code=400, detail="machines must be a non-empty list")
    if len(payload.machines) > 50:
        raise HTTPException(status_code=400, detail="cannot log more than 50 machines per job")

    job_id = (payload.job_id or "").strip() or str(uuid.uuid4())

    created: list[dict] = []
    for machine in payload.machines:
        # Stamp every sibling with the shared job_id, regardless of what
        # the client sent on the per-machine entry. This stops the
        # frontend from accidentally splitting siblings across jobs.
        machine.job_id = job_id
        doc = _build_issue_doc(machine, user)
        cov = await _resolve_coverage_for_issue(
            machine.serial_number, user.get("organization_id"),
        )
        doc["coverage_meta"] = cov
        # Iter 216h208 — inherit site_id from equipment (same fix as
        # the single-issue path).
        site_from_equip = cov.get("equipment_site_id") if isinstance(cov, dict) else None
        if site_from_equip:
            doc["site_id"] = site_from_equip
        await db.issues.insert_one(doc)
        doc.pop("_id", None)
        await store_fix_history(machine, doc["id"], user)
        await handle_engineer_escalation(machine, doc, user)
        await _publish_issue_event(doc, user)
        created.append(doc)

    # Bundle the svc_case mirror — one case per job_id covering every
    # machine. The svc_cases schema already supports `equipment_ids` /
    # `equipment_serials` arrays so this is a natural fit.
    await _mirror_job_to_svc_case(created, job_id, user)

    # Iter 220ea·39 — auto-dispatch each open machine fault to its own
    # supplier (machine-first resolution). Idempotent per issue_id.
    for doc in created:
        await _auto_dispatch_to_primary_supplier(doc, user)

    return {"job_id": job_id, "issues": created, "count": len(created)}


@router.get("/issues/jobs/{job_id}")
async def get_issues_for_job(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Iter 216d — return every sibling issue stamped with this job_id.

    Used by the fault-list expandable parent row to show "3 of 5
    machines fixed". Honours org isolation + site-lock so staff only
    see siblings they're allowed to see.
    """
    org_filter = get_organization_filter(user)
    org_filter = apply_site_lock(user, None, org_filter)
    cursor = db.issues.find(
        {**org_filter, "job_id": job_id},
        {"_id": 0},
    ).sort("created_at", 1)
    siblings = await cursor.to_list(length=200)
    fired = sum(1 for i in siblings if i.get("status") == "resolved")
    return {
        "job_id": job_id,
        "issues": siblings,
        "total": len(siblings),
        "resolved": fired,
        "all_resolved": len(siblings) > 0 and fired == len(siblings),
    }


def _parse_ai_triage(issue: dict):
    """Parse raw AI triage JSON into structured fields on the issue dict."""
    raw = issue.pop('ai_triage', None)
    if raw and not issue.get('ai_triage_parsed'):
        # Iter 216h120 — `raw` may be a dict (already-parsed triage
        # written by a previous request), a JSON string, or markdown
        # wrapping JSON. Branch on type rather than blindly slicing.
        if isinstance(raw, dict):
            issue['ai_triage_parsed'] = raw
        elif isinstance(raw, str):
            try:
                import json as json_mod
                cleaned = raw.strip()
                if cleaned.startswith('```'):
                    cleaned = cleaned.split('\n', 1)[1].rsplit('```', 1)[0]
                issue['ai_triage_parsed'] = json_mod.loads(cleaned)
            except Exception:
                issue['ai_triage_summary'] = raw[:200]


async def _batch_enrich_supplier_cases(issues: list[dict]):
    """Attach supplier case summary to each issue via batch lookup."""
    issue_ids = [i["id"] for i in issues]
    if not issue_ids:
        return
    cases = await db.supplier_cases.find(
        {"issue_id": {"$in": issue_ids}},
        {"_id": 0, "issue_id": 1, "token": 1, "current_status": 1, "scheduled_date": 1,
         "engineer_name": 1, "supplier_name": 1, "supplier_email": 1}
    ).to_list(500)
    by_issue = {c["issue_id"]: c for c in cases}
    for issue in issues:
        sc = by_issue.get(issue.get("id"))
        if sc:
            issue["supplier_case"] = {k: v for k, v in sc.items() if k != "issue_id"}


@router.get("/issues")
async def get_issues(user: dict = Depends(get_current_user), site_id: str = None) -> dict:
    # Iter 216h120 — MOD HQ rebind. See utils.mod_scope.
    from utils.mod_scope import resolve_mod_query_filter
    org_filter = await resolve_mod_query_filter(user, site_id)
    issues = await db.issues.find(org_filter, {"_id": 0}).sort("created_at", -1).to_list(1000)

    await _batch_enrich_supplier_cases(issues)

    for issue in issues:
        if 'serial_number' not in issue and 'machine_name' in issue:
            issue['serial_number'] = issue['machine_name']
        _parse_ai_triage(issue)

    return {"issues": issues}


@router.get("/issues/{issue_id}")
async def get_issue_detail(issue_id: str, user: dict = Depends(get_current_user)) -> dict:
    # Iter 216h120 — MOD HQ users may open an issue belonging to any
    # of their child gyms. Use the broad rollup filter.
    from utils.mod_scope import resolve_mod_query_filter
    org_filter = await resolve_mod_query_filter(user, None)
    issue = await db.issues.find_one({"id": issue_id, **org_filter}, {"_id": 0})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    # Iter 216bl — if the user is site-locked, refuse access to issues
    # outside their allowed sites. Done after the org filter so we
    # don't leak existence of an issue across orgs.
    role = (user.get("role") or "").lower()
    is_priv = (
        role in ("owner", "manager", "master_admin", "master")
        or bool(user.get("is_master_admin"))
    )
    allowed = user.get("allowed_site_ids") or []
    if not is_priv and allowed and issue.get("site_id") and issue["site_id"] not in allowed:
        raise HTTPException(status_code=403, detail="You do not have access to that site")
    if 'serial_number' not in issue and 'machine_name' in issue:
        issue['serial_number'] = issue['machine_name']

    # Enrich with supplier case data (comments, scheduled date, etc.)
    supplier_case = await db.supplier_cases.find_one({"issue_id": issue_id}, {"_id": 0})
    if supplier_case:
        issue["supplier_case"] = {
            "token": supplier_case.get("token"),
            "current_status": supplier_case.get("current_status"),
            "scheduled_date": supplier_case.get("scheduled_date"),
            "engineer_name": supplier_case.get("engineer_name"),
            "supplier_name": supplier_case.get("supplier_name"),
            "supplier_email": supplier_case.get("supplier_email", ""),
            "rating": supplier_case.get("rating"),
            "rating_feedback": supplier_case.get("rating_feedback"),
            "status_history": supplier_case.get("status_history", []),
        }
        comments = await db.supplier_case_comments.find(
            {"case_id": supplier_case["id"]}, {"_id": 0}
        ).sort("created_at", 1).to_list(500)
        issue["supplier_case"]["comments"] = comments
        # Mirror read-receipts: mark all unread supplier-authored comments as
        # seen by the gym now that an authenticated gym user has opened the
        # issue. The gym UI doesn't need this flag — it's for the supplier's
        # public case page so the supplier knows their reply was read.
        try:
            from routes.supplier_portal import mark_supplier_comments_read_by_gym
            await mark_supplier_comments_read_by_gym(supplier_case["id"])
        except Exception:  # pragma: no cover — non-blocking
            pass

    # Parse AI triage if raw
    raw = issue.get('ai_triage')
    if raw and not issue.get('ai_triage_parsed'):
        try:
            import json as json_mod
            cleaned = raw.strip()
            if cleaned.startswith('```'):
                cleaned = cleaned.split('\n', 1)[1].rsplit('```', 1)[0]
            issue['ai_triage_parsed'] = json_mod.loads(cleaned)
        except Exception:
            pass

    return issue


# ── update_issue helpers ─────────────────────────────────────────

_KPI_TIMESTAMP_FIELDS = (
    "engineer_assigned_at", "engineer_arrived_at", "work_started_at",
    "work_completed_at", "first_response_at", "resolved_at",
)

_ENGINEER_ACTIVITY_FIELDS = (
    "parts_used", "engineer_notes", "safety_checks_passed",
    "fault_type", "sla_category", "fault_code",
)


def _apply_status_change(data: dict, update_fields: dict, user: dict, now: str) -> dict | None:
    """Apply status transition. Returns a timeline entry if status changed, else None."""
    status = data.get("status")
    if not status:
        return None
    update_fields["status"] = status
    if status == "resolved" and "resolved_at" not in data:
        update_fields["resolved_at"] = now
    return {"event": f"status_changed_to_{status}", "timestamp": now, "by": user.get("full_name", "")}


def _apply_resolution_fields(data: dict, update_fields: dict) -> None:
    for key in ("resolution_type", "resolved_by"):
        if data.get(key):
            update_fields[key] = data[key]


def _apply_kpi_timestamps(data: dict, update_fields: dict, user: dict, now: str) -> dict | None:
    """Copy KPI timestamps from payload. Returns a fallback timeline entry if no prior entry."""
    fallback_entry = None
    for ts_field in _KPI_TIMESTAMP_FIELDS:
        if ts_field not in data:
            continue
        ts_value = data[ts_field] or now
        update_fields[ts_field] = ts_value
        if fallback_entry is None:
            fallback_entry = {"event": ts_field, "timestamp": ts_value, "by": user.get("full_name", "")}
    return fallback_entry


def _apply_engineer_fields(data: dict, update_fields: dict) -> None:
    for field in _ENGINEER_ACTIVITY_FIELDS:
        if field in data:
            update_fields[field] = data[field]


@router.patch("/issues/{issue_id}")
async def update_issue(issue_id: str, data: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    org_filter = get_organization_filter(user)
    now = datetime.now(timezone.utc).isoformat()

    update_fields: dict = {"updated_at": now}

    timeline_entry = _apply_status_change(data, update_fields, user, now)
    _apply_resolution_fields(data, update_fields)
    fallback_entry = _apply_kpi_timestamps(data, update_fields, user, now)
    if timeline_entry is None:
        timeline_entry = fallback_entry
    _apply_engineer_fields(data, update_fields)

    update_ops: dict = {"$set": update_fields}
    if timeline_entry:
        update_ops["$push"] = {"timeline": timeline_entry}

    result = await db.issues.update_one({"id": issue_id, **org_filter}, update_ops)
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Issue not found")
    return {"success": True}


@router.post("/issues/{issue_id}/attachments")
async def add_issue_attachment(issue_id: str, file: UploadFile = File(...), kind: str = Form(None), user: dict = Depends(get_current_user)) -> dict:
    from utils.file_validation import validate_upload, MIME_FAULT_MEDIA
    org_filter = get_organization_filter(user)
    issue = await db.issues.find_one({"id": issue_id, **org_filter})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    path = f"{APP_NAME}/issues/{issue_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    ct = validate_upload(file_bytes=data, filename=file.filename, allowed=MIME_FAULT_MEDIA, max_size=50 * 1024 * 1024)
    result = put_object(path, data, ct)

    attachment = {
        "id": str(uuid.uuid4()),
        "filename": file.filename,
        "storage_path": result["path"],
        "download_url": result.get("url", result["path"]),
        "content_type": ct,
        "size": result.get("size", len(data)),
        "uploaded_by": user.get('full_name'),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        # Iter 216h263 — tag the attachment so the fault detail card
        # can render quote PDFs in a dedicated Quotes section above
        # the Purchase Orders block. `kind` is one of:
        #   "quote"  — supplier quote (PDF/image)
        #   None     — generic job sheet / photo
        "kind": (kind or "").strip().lower() or None,
    }
    await db.issues.update_one({"id": issue_id}, {"$push": {"attachments": attachment}})
    return attachment


@router.patch("/issues/{issue_id}/details")
async def update_issue_details(issue_id: str, data: Dict[str, Any], user: dict = Depends(get_current_user)) -> dict:
    org_filter = get_organization_filter(user)
    allowed_fields = {"supplier_ref", "quote_amount", "engineer_notes"}
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.issues.update_one({"id": issue_id, **org_filter}, {"$set": update_data})
    return {"success": True}


@router.post("/service/request")
async def request_service(request: ServiceRequest, user: dict = Depends(get_current_user)) -> dict:
    service_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "machine_type": request.machine_type,
        "issue_summary": request.issue_summary,
        "site_info": request.site_info,
        "contact_name": request.contact_name,
        "contact_email": request.contact_email,
        "contact_phone": request.contact_phone,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.service_requests.insert_one(service_doc)

    if RESEND_API_KEY and resend:
        try:
            html_content = f'''<h2>New Service Request</h2>
            <p><strong>Machine Type:</strong> {request.machine_type}</p>
            <p><strong>Issue:</strong> {request.issue_summary}</p>
            <p><strong>Site:</strong> {request.site_info}</p>
            <p><strong>Contact:</strong> {request.contact_name}</p>
            <p><strong>Email:</strong> {request.contact_email}</p>
            <p><strong>Phone:</strong> {request.contact_phone}</p>'''
            params = {
                "from": SENDER_EMAIL,
                "to": [request.contact_email],
                "subject": "Service Request Received - Pulse Fitness AI",
                "html": html_content
            }
            await asyncio.to_thread(resend.Emails.send, params)
        except Exception as e:
            logger.error(f"Failed to send email: {e}")

    return {"id": service_doc['id'], "status": "pending"}



def _score_type_match(eq_type: str, machine_lower: str) -> int:
    """Score equipment type match for knowledge docs."""
    if not eq_type or not machine_lower:
        return 0
    if eq_type in machine_lower or machine_lower in eq_type:
        return 10
    if any(w in eq_type for w in machine_lower.split() if len(w) > 3):
        return 5
    return 0


def _score_supplier_relevance(supplier_lower: str, eq_mfr: str, doc_supplier: str) -> int:
    """Score supplier relevance for knowledge docs."""
    if not supplier_lower:
        return 0
    score = 0
    if supplier_lower in eq_mfr or eq_mfr in supplier_lower:
        score += 8
    if supplier_lower in doc_supplier or doc_supplier in supplier_lower:
        score += 8
    return score


_KNOWLEDGE_FIELD_WEIGHTS = {
    "common_faults": 2,
    "troubleshooting_tips": 1,
    "spare_parts": 1,
}


def _score_knowledge_doc(kd: dict, machine_lower: str, supplier_lower: str) -> int:
    """Score a single knowledge document by relevance."""
    ext = kd.get("extraction", {})
    equip_info = ext.get("equipment_info", {})
    eq_type = (equip_info.get("equipment_type") or "").lower()
    eq_mfr = (equip_info.get("manufacturer") or "").lower()
    eq_model = (equip_info.get("model") or "").lower()
    doc_supplier = (kd.get("supplier_name") or "").lower()

    score = _score_type_match(eq_type, machine_lower)
    score += _score_supplier_relevance(supplier_lower, eq_mfr, doc_supplier)
    if eq_model and machine_lower and eq_model in machine_lower:
        score += 6
    for field, weight in _KNOWLEDGE_FIELD_WEIGHTS.items():
        if ext.get(field):
            score += weight
    return score


async def _fetch_relevant_knowledge(machine_type: str, supplier: Optional[str] = None, organization_id: Optional[str] = None) -> list[dict]:
    """Search document knowledge globally + org-specific."""
    org_query: dict = {"$or": [{"organization_id": None}]}
    if organization_id:
        org_query["$or"].append({"organization_id": organization_id})

    all_docs = await db.equipment_knowledge.find(org_query, {"_id": 0}).to_list(100)
    if not all_docs:
        return []

    machine_lower = (machine_type or "").lower()
    supplier_lower = (supplier or "").lower()

    scored = [(s, kd) for kd in all_docs if (s := _score_knowledge_doc(kd, machine_lower, supplier_lower)) > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [kd for _, kd in scored[:5]]
