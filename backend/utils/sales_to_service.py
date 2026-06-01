"""Iter 220ea·26 (G2) — Auto sales→service onboarding.

The missing CRM→Service leg: when a maintenance contract is **activated /
signed** in the CRM, this bridges it into the Service Ops world so ops
don't re-key it by hand:

  1. **Customer** — ensure the linked CRM company also exists as a service
     customer (``svc_engineer_customers``) carrying ``company_id``, so the
     engineer app + quoting see it immediately.
  2. **PPM schedule** — write an ``svc_ppm_schedules`` row capturing the
     contract's preventive-maintenance cadence (visits/year, interval,
     start/end, next-due) as the source of truth for recurrence.
  3. **First visit** — seed the first ``case_type='ppm'`` service case via
     the canonical intake creator so it lands in dispatch + the engineer
     queue scheduled for the contract start.

Idempotent: keyed on ``contract_id`` in ``svc_ppm_schedules`` — re-firing
contract activation never double-onboards. Best-effort: never raises into
the contract flow (the caller wraps it, but we also swallow internally).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from utils.database import db

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


async def _ensure_service_customer(org: str, company: dict | None, company_id: str,
                                   fallback_name: str) -> bool:
    """Create a service-customer row for the contract's company if one
    isn't already linked. Returns True when a new row was created."""
    name = (company or {}).get("name") or fallback_name
    if not name:
        return False
    existing = await db.svc_engineer_customers.find_one(
        {"organization_id": org, "company_id": company_id}, {"_id": 0, "id": 1}
    ) if company_id else None
    if existing:
        return False
    # Also avoid a dup by name if an unlinked row already exists — link it.
    by_name = await db.svc_engineer_customers.find_one(
        {"organization_id": org, "name": name}, {"_id": 0, "id": 1})
    if by_name:
        if company_id:
            await db.svc_engineer_customers.update_one(
                {"organization_id": org, "id": by_name["id"]},
                {"$set": {"company_id": company_id, "updated_at": _now()}})
        return False
    await db.svc_engineer_customers.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": org,
        "created_by_id": "system",
        "name": name,
        "email": ((company or {}).get("email") or "").strip().lower() or None,
        "phone": (company or {}).get("phone") or None,
        "site_name": None,
        "site_address": None,
        "postcode": (company or {}).get("postcode") or None,
        "country": "United Kingdom",
        "company_id": company_id or "",
        "equipment_list": [],
        "notes": "Auto-created from an activated CRM maintenance contract.",
        "source": "contract_onboarding",
        "last_job_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    })
    return True


async def onboard_contract_to_service(contract: dict, *, user: dict) -> dict:
    """Bridge an activated maintenance contract into Service Ops.
    Returns a summary dict; safe to call repeatedly (idempotent)."""
    result = {"onboarded": False, "customer_created": False,
              "schedule_created": False, "case_id": None, "reason": ""}
    try:
        org = contract.get("organization_id")
        sla = contract.get("sla") or {}
        visits = int(sla.get("visits_per_year") or 0)
        if not org:
            result["reason"] = "no org"
            return result
        if not sla.get("preventive_maintenance") or visits < 1:
            result["reason"] = "contract has no PPM cover"
            return result

        contract_id = contract.get("id") or ""
        # Idempotency — already onboarded?
        if contract_id and await db.svc_ppm_schedules.find_one(
                {"organization_id": org, "contract_id": contract_id}, {"_id": 1}):
            result["reason"] = "already onboarded"
            return result

        company_id = contract.get("company_id") or ""
        company = None
        if company_id:
            company = await db.crm2_companies.find_one(
                {"organization_id": org, "id": company_id},
                {"_id": 0, "name": 1, "email": 1, "phone": 1, "postcode": 1})
        cust_name = (company or {}).get("name") or contract.get("company_name") or ""
        cust_email = (company or {}).get("email") or ""
        postcode = (company or {}).get("postcode") or ""

        # 1) Service customer.
        result["customer_created"] = await _ensure_service_customer(
            org, company, company_id, cust_name)

        # 2) PPM schedule.
        start = _parse_date(contract.get("start_date") or "") or datetime.now(timezone.utc)
        end = _parse_date(contract.get("end_date") or "")
        interval_days = max(1, round(365 / visits))
        next_due = start
        schedule = {
            "id": str(uuid.uuid4()),
            "organization_id": org,
            "contract_id": contract_id,
            "company_id": company_id,
            "customer_name": cust_name,
            "customer_email": cust_email,
            "site_postcode": postcode,
            "tier": contract.get("tier") or "standard",
            "visits_per_year": visits,
            "interval_days": interval_days,
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat() if end else "",
            "next_due_date": next_due.date().isoformat(),
            "visits_generated": 0,
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.svc_ppm_schedules.insert_one(schedule)
        result["schedule_created"] = True

        # 3) First PPM visit case via the canonical intake creator.
        try:
            from routes.svc.intake import _create_case
            payload = {
                "title": f"PPM visit — {cust_name}".strip(" —"),
                "description": (
                    f"Preventive maintenance visit under contract "
                    f"{contract.get('contract_number') or contract_id}. "
                    f"{visits} visit(s)/year."),
                "priority": "p3",
                "cover_type": "contract",
                "case_type": "ppm",
                "customer_name": cust_name,
                "customer_email": cust_email,
                "site_postcode": postcode,
                "contract_id": contract_id,
                "company_id": company_id,
            }
            case = await _create_case(payload=payload, source="contract_ppm", user=user)
            case_id = case.get("id")
            result["case_id"] = case_id
            if case_id:
                await db.svc_cases.update_one(
                    {"id": case_id},
                    {"$set": {
                        "scheduled_at": next_due.isoformat(),
                        "ppm_schedule_id": schedule["id"],
                        "ppm_due_date": next_due.date().isoformat(),
                    }})
                await db.svc_ppm_schedules.update_one(
                    {"id": schedule["id"]}, {"$set": {"visits_generated": 1}})
        except Exception:
            logger.warning("PPM first-visit seed failed for contract %s",
                           contract_id, exc_info=True)

        result["onboarded"] = True
        return result
    except Exception:
        logger.warning("onboard_contract_to_service failed", exc_info=True)
        return result


__all__ = ["onboard_contract_to_service"]
