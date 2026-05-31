"""Iter 220e8 — CRM lead conversion flow.

Converts an opportunity at the ``lead`` (or any pre-won) stage into
a fully qualified Company + Contact (+ optional Site, + optional
starter artifact: quote draft or contract draft). Operates on the
v2 ``crm2_opportunities`` collection (the source of truth for the
Pipeline UI) and mirrors into the legacy ``crm_*`` collections so
list views stay in lockstep — landing a Friday-closing lead in the
Monday-morning contract drafting queue without any data being
retyped.

Behaviour:

* Operator picks how each downstream record is sourced — *create new*
  or *use existing* — and the endpoint either reuses what's there or
  creates a fresh record.
* All writes are wrapped in audit + an activity feed entry on the
  deal so the conversion is traceable.
* Idempotent: a deal that's already converted returns the previously
  created IDs instead of re-creating duplicate records.
* On success, the opportunity is stamped with ``converted_at``,
  ``conversion_company_id``, ``conversion_contact_id`` etc. and
  moved to the operator-chosen pipeline stage (default
  ``qualified``).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from routes.crm_auth import get_crm_user
from routes.crm_core import log_audit
from utils.database import db


router = APIRouter(prefix="/crm/v2", tags=["CRM Lead Conversion"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _of(user: dict) -> dict:
    org = user.get("organization_id")
    return {"organization_id": org if org else "__NO_ORG__"}


async def _resolve_or_create_company(payload: dict, opp: dict, user: dict) -> dict:
    """Return ``{id, name, source}`` for the company step.

    ``payload`` may be:
      {"mode": "existing", "company_id": "..."}
      {"mode": "create",   "data": {name, industry, website, ...}}
      {"mode": "skip"}    → reuse opp.company_id/name
    """
    mode = (payload or {}).get("mode") or "skip"
    of = _of(user)
    if mode == "existing":
        cid = payload.get("company_id")
        if not cid:
            raise HTTPException(400, "company_id is required when mode=existing")
        co = await db.crm2_companies.find_one({"id": cid, **of}, {"_id": 0})
        if not co:
            raise HTTPException(404, "Company not found")
        return {"id": co["id"], "name": co.get("name"), "source": "existing"}
    if mode == "create":
        data = payload.get("data") or {}
        name = (data.get("name") or opp.get("company_name") or "").strip()
        if not name:
            raise HTTPException(400, "Company name is required")
        co = {
            "id": _id(),
            "organization_id": user.get("organization_id"),
            "name": name,
            "industry": data.get("industry", ""),
            "website": data.get("website", ""),
            "phone": data.get("phone", ""),
            "address": data.get("address", ""),
            "country": data.get("country", "GB"),
            "owner_id": user.get("id"),
            "owner_name": user.get("full_name", ""),
            "created_from_opportunity_id": opp["id"],
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.crm2_companies.insert_one(co)
        # Mirror into legacy crm_companies so existing list views stay
        # in lockstep — keeps a single name in both schemas.
        await db.crm_companies.update_one(
            {"id": co["id"]}, {"$setOnInsert": {**co, "tags": []}}, upsert=True,
        )
        return {"id": co["id"], "name": co["name"], "source": "created"}
    # mode == skip
    return {"id": opp.get("company_id"), "name": opp.get("company_name"), "source": "skip"}


async def _resolve_or_create_contact(payload: dict, opp: dict, company: dict, user: dict) -> dict:
    mode = (payload or {}).get("mode") or "skip"
    of = _of(user)
    if mode == "existing":
        cid = payload.get("contact_id")
        if not cid:
            raise HTTPException(400, "contact_id is required when mode=existing")
        ct = await db.crm2_contacts.find_one({"id": cid, **of}, {"_id": 0})
        if not ct:
            raise HTTPException(404, "Contact not found")
        return {"id": ct["id"],
                "name": f"{ct.get('first_name', '')} {ct.get('last_name', '')}".strip(),
                "source": "existing"}
    if mode == "create":
        data = payload.get("data") or {}
        first = (data.get("first_name") or opp.get("contact_name", "").split(" ")[0] or "").strip()
        last = (data.get("last_name") or " ".join(opp.get("contact_name", "").split(" ")[1:]) or "").strip()
        email = (data.get("email") or "").strip().lower()
        if not first and not email:
            raise HTTPException(400, "Contact requires at least a first name or email")
        ct = {
            "id": _id(),
            "organization_id": user.get("organization_id"),
            "first_name": first, "last_name": last,
            "email": email,
            "phone": data.get("phone", ""),
            "job_title": data.get("job_title", ""),
            "company_id": company.get("id", ""),
            "company_name": company.get("name", ""),
            "owner_id": user.get("id"),
            "owner_name": user.get("full_name", ""),
            "created_from_opportunity_id": opp["id"],
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.crm2_contacts.insert_one(ct)
        await db.crm_contacts.update_one(
            {"id": ct["id"]}, {"$setOnInsert": {**ct, "tags": []}}, upsert=True,
        )
        return {"id": ct["id"], "name": f"{first} {last}".strip(), "source": "created"}
    return {"id": opp.get("contact_id"), "name": opp.get("contact_name"), "source": "skip"}


async def _resolve_or_create_site(payload: dict, opp: dict, company: dict, user: dict) -> dict | None:
    mode = (payload or {}).get("mode") or "skip"
    if mode == "skip":
        return None
    if mode == "existing":
        sid = payload.get("site_id")
        site = await db.crm2_sites.find_one({"id": sid, **_of(user)}, {"_id": 0})
        if not site:
            raise HTTPException(404, "Site not found")
        return {"id": site["id"], "name": site.get("name"), "source": "existing"}
    if mode == "create":
        data = payload.get("data") or {}
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "Site name is required")
        site = {
            "id": _id(),
            "organization_id": user.get("organization_id"),
            "name": name,
            "company_id": company.get("id", ""),
            "company_name": company.get("name", ""),
            "address": data.get("address", ""),
            "city": data.get("city", ""),
            "postcode": data.get("postcode", ""),
            "country": data.get("country", "GB"),
            "created_from_opportunity_id": opp["id"],
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db.crm2_sites.insert_one(site)
        return {"id": site["id"], "name": name, "source": "created"}
    return None


async def _create_starter_artifact(kind: str, opp: dict, company: dict,
                                   contact: dict, site: dict | None, user: dict) -> dict | None:
    """Create an optional starter quote OR contract draft so the
    opportunity lands with a usable next-action artifact, not just a
    record update."""
    if kind not in ("contract_draft", "quote_draft"):
        return None
    if kind == "contract_draft":
        # Lazy import — keeps this module light when nobody picks
        # the contract path.
        try:
            from routes.crm_contracts import _build_contract_doc
        except ImportError:
            return None
        contract = _build_contract_doc({
            "title": f"{company.get('name') or opp.get('title')} — Service Contract",
            "company_id": company.get("id", ""),
            "company_name": company.get("name", ""),
            "contact_id": contact.get("id", ""),
            "billing_contact_id": contact.get("id", ""),
            "site_id": (site or {}).get("id", ""),
            "annual_value": float(opp.get("value") or 0),
            "total_value":  float(opp.get("value") or 0),
            "tier": "silver",
            "opportunity_id": opp["id"],
        }, user)
        await db.crm2_contracts.insert_one(contract)
        return {"type": "contract_draft", "id": contract["id"],
                "contract_number": contract.get("contract_number")}
    # quote_draft — minimal stub so the operator has something to edit.
    quote = {
        "id": _id(),
        "organization_id": user.get("organization_id"),
        "number": f"QUOTE-{_id()[:6].upper()}",
        "title": f"{company.get('name') or opp.get('title')} — Quote",
        "company_id": company.get("id", ""),
        "company_name": company.get("name", ""),
        "contact_id": contact.get("id", ""),
        "status": "draft",
        "amount": float(opp.get("value") or 0),
        "opportunity_id": opp["id"],
        "created_by": user.get("full_name", ""),
        "created_at": _now(), "updated_at": _now(),
    }
    await db.crm2_quotes.insert_one(quote)
    return {"type": "quote_draft", "id": quote["id"], "number": quote["number"]}


@router.post("/opportunities/{opp_id}/convert")
async def convert_lead(opp_id: str, data: dict, user: dict = Depends(get_crm_user)):
    """Convert a lead/early-stage opportunity into qualified Company +
    Contact + (optional) Site + (optional) Quote/Contract draft.

    Body:
        {
          "company":  {"mode": "create|existing|skip", ...},
          "contact":  {"mode": "create|existing|skip", ...},
          "site":     {"mode": "create|existing|skip", ...},
          "artifact": {"kind": "contract_draft|quote_draft|none"},
          "target_stage": "qualified" (default)
        }
    """
    of = _of(user)
    opp = await db.crm2_opportunities.find_one({"id": opp_id, **of}, {"_id": 0})
    if not opp:
        raise HTTPException(404, "Opportunity not found")

    # Idempotency: if already converted, return previous IDs.
    if opp.get("converted_at"):
        return {
            "opportunity_id": opp_id,
            "company_id":  opp.get("conversion_company_id"),
            "company_name": opp.get("conversion_company_name"),
            "contact_id":  opp.get("conversion_contact_id"),
            "contact_name": opp.get("conversion_contact_name"),
            "site_id":     opp.get("conversion_site_id"),
            "artifact":    opp.get("conversion_artifact"),
            "stage_moved": False,
            "target_stage": opp.get("stage"),
            "already_converted": True,
        }

    if opp.get("stage") in ("closed_won", "closed_lost", "won", "lost"):
        raise HTTPException(400, "Cannot convert a closed opportunity")

    company = await _resolve_or_create_company(data.get("company") or {}, opp, user)
    contact = await _resolve_or_create_contact(data.get("contact") or {}, opp, company, user)
    site = await _resolve_or_create_site(data.get("site") or {}, opp, company, user)
    artifact_kind = ((data.get("artifact") or {}).get("kind") or "none")
    artifact = await _create_starter_artifact(artifact_kind, opp, company, contact, site, user)

    target_stage = (data.get("target_stage") or "qualified").lower()
    opp_updates = {
        "converted_at": _now(),
        "converted_by": user.get("id"),
        "converted_by_name": user.get("full_name", ""),
        "conversion_company_id": company.get("id"),
        "conversion_company_name": company.get("name"),
        "conversion_contact_id": contact.get("id"),
        "conversion_contact_name": contact.get("name"),
        "conversion_site_id": (site or {}).get("id"),
        "conversion_artifact": artifact,
        "company_id": company.get("id") or opp.get("company_id"),
        "company_name": company.get("name") or opp.get("company_name"),
        "contact_id": contact.get("id") or opp.get("contact_id"),
        "contact_name": contact.get("name") or opp.get("contact_name"),
        "stage": target_stage,
        "updated_at": _now(),
    }
    await db.crm2_opportunities.update_one({"id": opp_id}, {"$set": opp_updates})

    # Activity row so the opportunity timeline tells the story.
    summary_parts = []
    if company.get("source") == "created":
        summary_parts.append(f"created company {company['name']}")
    elif company.get("source") == "existing":
        summary_parts.append(f"linked to company {company['name']}")
    if contact.get("source") == "created":
        summary_parts.append(f"created contact {contact['name']}")
    elif contact.get("source") == "existing":
        summary_parts.append(f"linked to contact {contact['name']}")
    if site and site.get("source") == "created":
        summary_parts.append(f"created site {site['name']}")
    if artifact:
        summary_parts.append(f"drafted {artifact['type'].replace('_', ' ')} {artifact.get('contract_number') or artifact.get('number') or artifact['id'][:8]}")
    summary = "Lead converted: " + ", ".join(summary_parts) if summary_parts else "Lead converted"

    await db.crm2_activities.insert_one({
        "id": _id(),
        "organization_id": user.get("organization_id"),
        "type": "system",
        "subject": "Lead converted",
        "body": summary,
        "opportunity_id": opp_id,
        "contact_id": contact.get("id"),
        "company_id": company.get("id"),
        "owner_id": user.get("id"),
        "owner_name": user.get("full_name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    })
    await log_audit(user, "opportunity", opp_id, "converted", {
        "company_id": company.get("id"),
        "contact_id": contact.get("id"),
        "site_id": (site or {}).get("id"),
        "artifact": artifact,
        "target_stage": target_stage,
    })

    return {
        "opportunity_id": opp_id,
        "company_id":  company.get("id"),
        "company_name": company.get("name"),
        "contact_id":  contact.get("id"),
        "contact_name": contact.get("name"),
        "site_id":     (site or {}).get("id"),
        "site_name":   (site or {}).get("name"),
        "artifact":    artifact,
        "stage_moved": True,
        "target_stage": target_stage,
        "already_converted": False,
    }
