"""Authoritative customer identity + provisioning for every Pulse-managed customer creation path.

Identity rules (organisations):
  1. External account reference (Sage AccountNumber = Sicon CustomerCode), scoped by Sage company, is authoritative.
     It is bound to exactly one organisation in `customer_account_refs` (unique) and mirrored on the org.
  2. Without a reference, an organisation is never matched automatically: similar names / postcodes are returned as
     duplicate suggestions and the caller must explicitly confirm the customer is new.
  3. New Pulse-managed customers receive Pulse Fitness LITE only, pending activation, with no users or emails.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError

from utils.database import db

LITE_MODULES = ["operations"]


class DuplicateSuspected(Exception):
    def __init__(self, suggestions: list[dict]):
        super().__init__("Possible existing customer")
        self.suggestions = suggestions


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_ref(v) -> str:
    return re.sub(r"\s+", "", str(v or "")).upper()


def norm_name(n: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", (n or "").lower())
    n = re.sub(r"\b(ltd|limited|plc|llp|inc|co|the|uk|group)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


async def find_orgs_by_ref(ref: str, company: str = "") -> list[str]:
    ref = clean_ref(ref)
    if not ref:
        return []
    ids = {d["org_id"] async for d in db.customer_account_refs.find({"system": "sage", "company": company, "ref": ref}, {"org_id": 1})}
    q = {"$or": [{"customer_account_number": ref}, {"sage_customer_number": ref}, {"sicon_customer_number": ref},
                 {"sage_account_refs": ref}]}
    async for o in db.organizations.find(q, {"_id": 0, "id": 1, "sage_company": 1}):
        if (o.get("sage_company") or "") == company:
            ids.add(o["id"])
    async for s in db.sites.find({"$or": [{"invoice_customer_ref": ref}, {"sicon_customer_ref": ref}]}, {"_id": 0, "organization_id": 1}):
        if s.get("organization_id"):
            ids.add(s["organization_id"])
    return sorted(ids)


async def claim_ref(ref: str, company: str, org_id: str, job_id: Optional[str] = None, source: str = "") -> str:
    """Bind an account reference to one organisation (unique). Returns the organisation that owns it."""
    try:
        await db.customer_account_refs.insert_one({"system": "sage", "company": company, "ref": clean_ref(ref), "org_id": org_id,
                                                   "job_id": job_id, "source": source, "created_at": _now()})
        return org_id
    except DuplicateKeyError:
        d = await db.customer_account_refs.find_one({"system": "sage", "company": company, "ref": clean_ref(ref)}, {"_id": 0, "org_id": 1})
        return d["org_id"]


async def duplicate_suggestions(name: str, postcode: str = "", limit: int = 8) -> list[dict]:
    """Possible existing customers — suggestions for a human, never an automatic match."""
    nn, pc = norm_name(name), re.sub(r"\s+", "", (postcode or "").upper())
    if not nn and not pc:
        return []
    words = [w for w in nn.split() if len(w) > 1][:6]
    ors = [{"$and": [{"name": {"$regex": re.escape(w), "$options": "i"}} for w in words]}] if words else []
    if pc:
        ors.append({"postcode": {"$regex": f"^{re.escape(pc[:-3] if len(pc) > 4 else pc)}", "$options": "i"}})
    if not ors:
        return []
    out = []
    async for o in db.organizations.find({"$or": ors}, {"_id": 0, "id": 1, "name": 1, "postcode": 1, "city": 1,
                                                         "customer_account_number": 1, "account_type": 1}).limit(200):
        on = norm_name(o.get("name"))
        same_pc = pc and re.sub(r"\s+", "", (o.get("postcode") or "").upper()) == pc
        score = 1.0 if on == nn else (0.7 if nn and (nn in on or on in nn) else 0.0) + (0.5 if same_pc else 0.0)
        if score >= 0.7:
            out.append({**o, "reason": "same name" if on == nn else "similar name" if score < 1.2 and not same_pc else
                        "similar name and same postcode", "score": round(score, 2)})
    return sorted(out, key=lambda x: -x["score"])[:limit]


def lite_org_doc(org_id: str, fields: dict, *, ref: str = "", company: str = "", source: str, job_id: Optional[str] = None) -> dict:
    lines = [fields.get(k, "") for k in ("address_line1", "address_line2", "address_line3", "address_line4", "city", "county", "postcode")]
    return {
        "id": org_id, "name": fields["name"].strip(), "short_name": fields.get("short_name", ""),
        "portal_type": "operations", "enabled_modules": list(LITE_MODULES),
        "modules": {"operations": {"enabled": True, "tier": "lite", "source": source}},
        "subscription_tier": "free", "account_type": "lite", "status": "active",
        "onboarding_status": "pending_activation", "portal_access": "not_activated", "provisioning_state": "importing",
        "company_code": str(uuid.uuid4())[:8].upper(),
        "customer_account_number": ref, "sage_customer_number": ref, "sage_account_refs": [ref] if ref else [],
        "sage_company": company,
        **{k: fields.get(k, "") for k in ("currency", "sage_country_code", "website", "phone", "address_line1", "address_line2",
                                          "address_line3", "address_line4", "city", "county", "postcode", "address_country_code",
                                          "sage_office_type", "sage_head_office_ref")},
        "phone_parts": fields.get("phone_parts") or {}, "fax_parts": fields.get("fax_parts") or {},
        "country": fields.get("address_country_code", ""), "address": ", ".join(x for x in lines if x),
        "primary_contact_name": fields.get("primary_contact_name", ""), "primary_contact_email": fields.get("primary_contact_email", ""),
        "features": {}, "notes": fields.get("notes", ""),
        "created_via": source, "created_via_job_id": job_id, "created_at": _now(),
    }


async def provision_customer_org(fields: dict, *, source: str, actor: str, ref: str = "", company: str = "",
                                 job_id: Optional[str] = None, confirmed_new: bool = False) -> tuple[str, bool]:
    """The one way to create a Pulse-managed customer organisation. Returns (org_id, created)."""
    ref = clean_ref(ref)
    if ref:
        ids = await find_orgs_by_ref(ref, company)
        if len(ids) > 1:
            raise ValueError(f"Account {ref} is linked to {len(ids)} organisations — resolve in the Review Centre")
        if ids:
            await claim_ref(ref, company, ids[0], job_id, source)
            return ids[0], False
    elif not confirmed_new:
        sugg = await duplicate_suggestions(fields.get("name", ""), fields.get("postcode", ""))
        if sugg:
            raise DuplicateSuspected(sugg)
    new_id = str(uuid.uuid4())
    if ref:
        owner = await claim_ref(ref, company, new_id, job_id, source)
        if owner != new_id:
            return owner, False
    await db.organizations.insert_one(lite_org_doc(new_id, fields, ref=ref, company=company, source=source, job_id=job_id))
    await db.onboarding_audit_events.insert_one({"id": str(uuid.uuid4()), "action": "customer_org_provisioned",
                                                 "detail": {"org_id": new_id, "ref": ref, "company": company, "source": source,
                                                            "job_id": job_id, "confirmed_new": confirmed_new},
                                                 "actor_email": actor, "at": _now()})
    return new_id, True


async def mark_complete(org_id: str) -> None:
    await db.organizations.update_one({"id": org_id, "provisioning_state": "importing"}, {"$set": {"provisioning_state": "complete"}})
