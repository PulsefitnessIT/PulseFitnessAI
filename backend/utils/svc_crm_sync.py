"""
Pulse Fitness Service Ops ↔ CRM sync — Iter 216h152 (Feb 2026).

Emits CRM2 activity rows when service cases close or invoices finalise,
so the CRM company timeline and forecast can see service revenue
alongside sales pipeline.

This is the missing "SVC → CRM" leg identified in the Feb 2026 process
audit. The reverse leg (CRM → SVC) already worked — `crm2_activities`
already accepts `case_id` as a foreign key — but no service code was
writing those rows.

Design:
  * Best-effort: never blocks the service flow. Wrapped in try/except
    at the call site.
  * Match by name (case-insensitive) then email — both fall back to
    company name+postcode if the customer record is sparse.
  * Idempotent on (case_id, kind) — re-running the close hook does
    not duplicate the activity row.

Activity kinds emitted:
  * `service_visit`   — when a case transitions to `closed`.
  * `service_invoice` — when a quote is finalised to invoiced.
                        `metadata.amount_net` carries the net total
                        for the YTD-revenue rollup tile.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from utils.database import db

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _find_company(organization_id: str, *, name: str = "",
                        email: str = "", postcode: str = "") -> Optional[dict]:
    """Best-effort customer → CRM company match. Returns the lean
    company doc `{id, name}` or None."""
    if not (name or email):
        return None
    q_base = {"organization_id": organization_id}
    # 1) Exact name match (case-insensitive).
    if name:
        co = await db.crm2_companies.find_one(
            {**q_base, "name": {"$regex": f"^{_re_escape(name)}$", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1},
        )
        if co:
            return co
    # 2) Exact email match.
    if email:
        co = await db.crm2_companies.find_one(
            {**q_base, "email": {"$regex": f"^{_re_escape(email)}$", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1},
        )
        if co:
            return co
    # 3) Name + postcode (handles "Tottenham Green LC" with two sites).
    if name and postcode:
        co = await db.crm2_companies.find_one(
            {**q_base,
             "name": {"$regex": _re_escape(name), "$options": "i"},
             "postcode": {"$regex": f"^{_re_escape(postcode)}", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1},
        )
        if co:
            return co
    return None


def _re_escape(s: str) -> str:
    """Minimal regex escape for the special characters we encounter in
    customer names / emails. Avoids pulling in `re` just for this."""
    return (s or "").replace("\\", "\\\\").replace(".", "\\.").replace(
        "+", "\\+").replace("?", "\\?").replace("*", "\\*").replace(
        "(", "\\(").replace(")", "\\)").replace("[", "\\[").replace(
        "]", "\\]").replace("$", "\\$").replace("^", "\\^")


async def resolve_sage_customer_id(
    organization_id: str, *, name: str = "", email: str = "",
    company_id: str = "",
) -> str:
    """Iter 220ea·26 (G3) — resolve a case's Sage customer account id.

    Historically service intake / billing read ``sage_customer_id`` only
    from the **v1** ``crm_companies`` shadow, matched by **name only**.
    A company created directly in the live **v2** CRM (``crm2_companies``)
    has no v1 shadow, so the Sage link silently came back empty.

    This resolver closes that seam:
      1. If ``company_id`` is known (the canonical link added in G1),
         read the v2 company directly, then its v1 twin by name.
      2. Otherwise match v2 by name → email, then v1 by name → email.
    Reads ``sage_customer_id`` from whichever store carries it (only v1
    holds it today, but checking v2 first future-proofs the bridge).
    Best-effort: returns ``""`` on any miss or error — never raises.
    """
    try:
        of = {"organization_id": organization_id}

        async def _sid_from(coll, query):
            doc = await coll.find_one(
                {**of, **query}, {"_id": 0, "sage_customer_id": 1, "name": 1})
            return ((doc or {}).get("sage_customer_id") or "",
                    (doc or {}).get("name") or "")

        # 1) Canonical id path.
        if company_id:
            sid, v2name = await _sid_from(db.crm2_companies, {"id": company_id})
            if sid:
                return sid
            if v2name:
                sid, _ = await _sid_from(
                    db.crm_companies,
                    {"name": {"$regex": f"^{_re_escape(v2name)}$", "$options": "i"}})
                if sid:
                    return sid

        # 2) Name / email matching across v2 then v1.
        for coll in (db.crm2_companies, db.crm_companies):
            if name:
                sid, _ = await _sid_from(
                    coll, {"name": {"$regex": f"^{_re_escape(name)}$", "$options": "i"}})
                if sid:
                    return sid
            if email:
                sid, _ = await _sid_from(
                    coll, {"email": {"$regex": f"^{_re_escape(email)}$", "$options": "i"}})
                if sid:
                    return sid
    except Exception:  # pragma: no cover - best-effort bridge
        logger.debug("resolve_sage_customer_id failed", exc_info=True)
    return ""


async def find_company_id(
    organization_id: str, *, name: str = "", email: str = "",
    postcode: str = "",
) -> str:
    """Iter 220ea·26 (G1) — resolve the canonical CRM (v2) company id for
    a service customer. Returns the ``crm2_companies.id`` or ``""``.

    This is the shared spine that lets a service case / engineer customer
    point at one CRM company instead of being matched by free-text name
    every time. Best-effort, never raises."""
    try:
        co = await _find_company(
            organization_id, name=name, email=email, postcode=postcode)
        return (co or {}).get("id") or ""
    except Exception:  # pragma: no cover - best-effort bridge
        logger.debug("find_company_id failed", exc_info=True)
        return ""


async def push_customer_to_crm(customer: dict, *, user: dict | None = None) -> dict:
    """Iter 220ea·26 (G4) — reconcile a field-added service customer
    (``svc_engineer_customers``) into the CRM so it stops being an island.

    If the customer is already linked (``company_id`` resolves to a live
    CRM company) this is a no-op. Otherwise it tries to match an existing
    CRM company by name/email first (avoids duplicates); failing that it
    creates a new ``crm2_companies`` record (``type='customer'``,
    ``source='service_field'``), logs a CRM activity, and links the
    engineer customer back via ``company_id``.

    Returns ``{created, linked, company_id, company_name, reason}``.
    """
    org = customer.get("organization_id")
    out = {"created": False, "linked": False, "company_id": "",
           "company_name": "", "reason": ""}
    if not org:
        out["reason"] = "no org"
        return out
    cust_id = customer.get("id") or ""

    async def _link_back(company_id: str):
        if cust_id and company_id:
            await db.svc_engineer_customers.update_one(
                {"organization_id": org, "id": cust_id},
                {"$set": {"company_id": company_id, "updated_at": _now()}})

    # 1) Already linked to a live CRM company?
    existing_id = customer.get("company_id") or ""
    if existing_id:
        co = await db.crm2_companies.find_one(
            {"organization_id": org, "id": existing_id}, {"_id": 0, "id": 1, "name": 1})
        if co:
            out.update(company_id=co["id"], company_name=co.get("name") or "",
                       reason="already linked")
            return out

    name = (customer.get("name") or "").strip()
    email = (customer.get("email") or "").strip()
    if not name:
        out["reason"] = "customer has no name"
        return out

    # 2) Match an existing CRM company by name/email before creating one.
    match_id = await find_company_id(org, name=name, email=email,
                                     postcode=customer.get("postcode") or "")
    if match_id:
        await _link_back(match_id)
        out.update(linked=True, company_id=match_id, company_name=name,
                   reason="linked to existing CRM company")
        return out

    # 3) Create a new CRM (v2) company from the field customer.
    company_id = str(uuid.uuid4())
    owner_id = (user or {}).get("id") or "system"
    owner_name = (user or {}).get("full_name") or "Service field"
    company = {
        "id": company_id,
        "organization_id": org,
        "name": name,
        "type": "customer",
        "sector": "",
        "website": "",
        "phone": customer.get("phone") or "",
        "email": email,
        "address": customer.get("site_address") or "",
        "address_line1": customer.get("address_line1") or customer.get("site_address") or "",
        "address_line2": customer.get("address_line2") or "",
        "address_line3": "",
        "city": customer.get("city") or "",
        "postcode": customer.get("postcode") or "",
        "county": customer.get("county") or "",
        "country": customer.get("country") or "United Kingdom",
        "company_number": customer.get("company_number") or "",
        "description": "",
        "directors": [],
        "account_owner_id": owner_id,
        "account_owner_name": owner_name,
        "sla_tier": "standard",
        "revenue_band": "",
        "status": "active",
        "tags": ["service-field"],
        "notes": customer.get("notes") or "Reconciled from a field-added service customer.",
        "territory_id": None,
        "owner_id": owner_id,
        "owner_name": owner_name,
        "region": "",
        "source": "service_field",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.crm2_companies.insert_one(company)
    try:
        await db.crm2_activities.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org,
            "type": "system", "subject": "Company created from Service field",
            "body": f"{owner_name} reconciled service customer “{name}” into the CRM.",
            "company_id": company_id, "owner_id": owner_id,
            "owner_name": owner_name, "created_at": _now(), "updated_at": _now(),
        })
    except Exception:  # pragma: no cover
        logger.debug("push_customer_to_crm activity failed", exc_info=True)
    await _link_back(company_id)
    out.update(created=True, linked=True, company_id=company_id,
               company_name=name, reason="created new CRM company")
    return out


async def _upsert_activity(
    *, organization_id: str, case_id: str, kind: str, doc: dict,
) -> dict:
    """Idempotent insert keyed on (case_id, type=kind). If a row
    already exists we update `metadata` + `updated_at` so re-emits are
    not destructive (useful when the user re-closes after re-opening)."""
    existing = await db.crm2_activities.find_one(
        {"organization_id": organization_id, "case_id": case_id, "type": kind},
        {"_id": 0, "id": 1},
    )
    if existing:
        await db.crm2_activities.update_one(
            {"id": existing["id"]},
            {"$set": {**doc, "updated_at": _now()}},
        )
        out = {**doc, "id": existing["id"]}
        return out
    record = {
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "type": kind,
        "case_id": case_id,
        "created_at": _now(),
        "updated_at": _now(),
        **doc,
    }
    await db.crm2_activities.insert_one(record)
    record.pop("_id", None)
    return record


async def emit_case_close_activity(case: dict, actor: dict) -> Optional[dict]:
    """Fire-and-forget — call from cases.transition_case when the
    target state is `closed`. Returns the activity row or None when
    no CRM match was found (still safe — the service flow continues)."""
    org = case.get("organization_id")
    if not org:
        return None
    company = await _find_company(
        org,
        name=case.get("customer_name") or "",
        email=case.get("customer_email") or "",
        postcode=case.get("site_postcode") or "",
    )
    body = (
        f"Service case {case.get('reference') or case.get('id')} closed"
        + (f" at {case['site_name']}" if case.get("site_name") else "")
        + (f" — {case['title']}" if case.get("title") else "")
    )
    payload = {
        "subject": f"Service visit closed: {case.get('reference') or ''}".strip(),
        "body": body,
        "company_id": (company or {}).get("id"),
        "owner_id": (actor or {}).get("id") or case.get("assigned_engineer_id"),
        "owner_name": (actor or {}).get("full_name", "") or case.get("assigned_engineer_name", ""),
        "metadata": {
            "site_name": case.get("site_name"),
            "site_postcode": case.get("site_postcode"),
            "priority": case.get("priority"),
            "asset_id": case.get("asset_id"),
            "asset_name": case.get("asset_name"),
            "engineer_id": case.get("assigned_engineer_id"),
            "engineer_name": case.get("assigned_engineer_name"),
            "reference": case.get("reference"),
        },
    }
    return await _upsert_activity(
        organization_id=org, case_id=case["id"],
        kind="service_visit", doc=payload,
    )


async def emit_invoice_activity(case: dict, quote: dict,
                                actor: dict) -> Optional[dict]:
    """Fire-and-forget — call from billing.finalise_invoice after the
    quote is flipped to `invoiced`. Carries `amount_net` and
    `amount_gross` in metadata so the `service-revenue-ytd` tile can
    sum without re-joining svc_quotes."""
    org = case.get("organization_id")
    if not org:
        return None
    company = await _find_company(
        org,
        name=case.get("customer_name") or "",
        email=case.get("customer_email") or "",
        postcode=case.get("site_postcode") or "",
    )
    net = float(quote.get("net") or quote.get("subtotal") or 0)
    gross = float(quote.get("gross") or quote.get("total") or net)
    payload = {
        "subject": f"Invoice raised: {case.get('reference') or ''} — £{net:,.2f}".strip(),
        "body": (
            f"Service invoice raised for {case.get('customer_name') or 'customer'}"
            f" · case {case.get('reference') or case.get('id')}"
            + (f" · {case.get('site_name')}" if case.get("site_name") else "")
        ),
        "company_id": (company or {}).get("id"),
        "owner_id": (actor or {}).get("id") or case.get("assigned_engineer_id"),
        "owner_name": (actor or {}).get("full_name", "") or case.get("assigned_engineer_name", ""),
        "metadata": {
            "amount_net": round(net, 2),
            "amount_gross": round(gross, 2),
            "currency": quote.get("currency") or "GBP",
            "quote_id": quote.get("id"),
            "quote_reference": quote.get("reference"),
            "site_name": case.get("site_name"),
            "site_postcode": case.get("site_postcode"),
            "asset_id": case.get("asset_id"),
            "engineer_id": case.get("assigned_engineer_id"),
            "engineer_name": case.get("assigned_engineer_name"),
            "reference": case.get("reference"),
        },
    }
    return await _upsert_activity(
        organization_id=org, case_id=case["id"],
        kind="service_invoice", doc=payload,
    )


__all__ = ["emit_case_close_activity", "emit_invoice_activity"]
