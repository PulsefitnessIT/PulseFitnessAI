"""Sales CRM → Contract Management handover.

An accepted EQUIPMENT sale (``crm_quotes``) becomes ONE maintenance opportunity
task once its equipment is confirmed on the customer's own register. The task
carries the stable references Build Quote needs (customer, sites, equipment)
so the coordinator never re-enters them. No equipment → no opportunity.
"""
from __future__ import annotations

from utils.database import db
from utils.cm_actions import raise_action

SALE_DONE = ("accepted", "won", "completed", "invoiced", "paid")


async def _customer_company(org_id: str, quote: dict) -> dict:
    if not quote.get("company_id"):
        return {}
    return await db.crm2_companies.find_one({"id": quote["company_id"], "organization_id": org_id}, {"_id": 0}) or {}


async def confirmed_equipment(org_id: str, quote: dict, company: dict) -> list:
    """Equipment from this sale confirmed on the customer's register."""
    tenant = company.get("linked_organization_id") or company.get("tenant_org_id")
    if not tenant:
        return []
    return await db.equipment.find(
        {"organization_id": tenant, "quote_id": quote["id"], "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "name": 1, "model": 1, "serial_number": 1, "site_id": 1, "contract_cover": 1},
    ).to_list(1000)


async def raise_sales_handover(org_id: str, quote: dict) -> dict:
    """Idempotent: one task per sales quote (dedupe ``cm:sale-handover:{id}``)."""
    if (quote.get("status") or "").lower() not in SALE_DONE:
        return {"created": False, "reason": "sale_not_accepted"}
    if quote.get("quote_kind") == "maintenance" or quote.get("source") == "aftersales":
        return {"created": False, "reason": "not_an_equipment_sale"}
    company = await _customer_company(org_id, quote)
    if not company:
        return {"created": False, "reason": "no_customer"}
    eq = await confirmed_equipment(org_id, quote, company)
    uncovered = [e for e in eq if not (e.get("contract_cover") or {}).get("contract_id")]
    if not uncovered:
        return {"created": False, "reason": "no_confirmed_uncovered_equipment", "equipment": len(eq)}
    if await db.crm2_afs_quotes.find_one({"organization_id": org_id, "source_sales_quote_id": quote["id"],
                                          "status": {"$nin": ["cancelled", "superseded", "declined"]}}, {"_id": 1}):
        return {"created": False, "reason": "maintenance_quote_exists"}
    # Build Quote reads the estate via linked_organization_id — link once if only the portal id is set.
    tenant = company.get("linked_organization_id") or company.get("tenant_org_id")
    if not company.get("linked_organization_id"):
        await db.crm2_companies.update_one({"id": company["id"]}, {"$set": {"linked_organization_id": tenant}})
    with_serial = sum(1 for e in uncovered if e.get("serial_number"))
    site_ids = sorted({e["site_id"] for e in uncovered if e.get("site_id")})
    aid = await raise_action(
        org_id, f"cm:sale-handover:{quote['id']}", type_="sales_handover",
        subject=f"Maintenance opportunity: {company.get('name')}",
        body=(f"Equipment sale {quote.get('quote_number') or ''} delivered — {len(uncovered)} confirmed machine(s) "
              f"({with_serial} with serial numbers) not yet under a maintenance contract. Build a maintenance quote."),
        contract={"id": None, "company_id": company["id"], "contract_number": quote.get("quote_number")},
        extra={"source_sales_quote_id": quote["id"], "sales_quote_number": quote.get("quote_number"),
               "company_name": company.get("name"), "site_ids": site_ids,
               "equipment_ids": [e["id"] for e in uncovered], "equipment_count": len(uncovered),
               "serials_confirmed": with_serial})
    return {"created": True, "action_id": aid, "equipment": len(uncovered)}


async def scan_sales_handovers(org_id: str) -> dict:
    """Daily catch-up for sales whose equipment was confirmed elsewhere."""
    raised = 0
    async for q in db.crm_quotes.find({"organization_id": org_id, "status": {"$in": list(SALE_DONE)}},
                                      {"_id": 0}).sort("updated_at", -1).limit(500):
        if await db.crm2_activities.find_one({"organization_id": org_id, "dedupe_key": f"cm:sale-handover:{q['id']}"}, {"_id": 1}):
            continue
        if (await raise_sales_handover(org_id, q)).get("created"):
            raised += 1
    return {"raised": raised}
