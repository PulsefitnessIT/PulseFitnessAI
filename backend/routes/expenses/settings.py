"""Expenses — config, country-rules engine & category settings (iter 278)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from utils.auth import get_current_user
from utils.database import db

from .common import (
    router, org_of, can_review, get_org, ensure_seeded, approval_mode,
    default_country_rule, now_iso, country_code_for_org,
)


def _require_admin(user: dict) -> None:
    if not can_review(user):
        raise HTTPException(403, "Finance / manager access required")


# ── Config bundle for the current user (drives the mobile UI) ────────
@router.get("/config")
async def expenses_config(user=Depends(get_current_user)):
    org_id = org_of(user)
    org = await get_org(org_id)
    await ensure_seeded(org_id, org)

    rules = await db.expense_country_rules.find(
        {"organization_id": org_id}, {"_id": 0}).sort("country_name", 1).to_list(200)
    cats = await db.expense_categories.find(
        {"organization_id": org_id, "active": True}, {"_id": 0}
    ).sort("sort_order", 1).to_list(200)
    default_rule = await default_country_rule(org_id)

    # Recent linkable records for quick selection on mobile.
    jobs = await db.svc_cases.find(
        {"organization_id": org_id, "assigned_engineer_id": user.get("id")},
        {"_id": 0, "id": 1, "reference": 1, "title": 1, "site_name": 1,
         "customer_name": 1, "asset_id": 1},
    ).sort("created_at", -1).limit(20).to_list(20)
    vehicles = await db.svc_vehicles.find(
        {"organization_id": org_id}, {"_id": 0, "id": 1, "name": 1, "registration": 1},
    ).limit(50).to_list(50)

    return {
        "organization_id": org_id,
        "currency": (default_rule or {}).get("currency") or org.get("currency") or "GBP",
        "approval_mode": approval_mode(org),
        "can_review": can_review(user),
        "default_country_code": (default_rule or {}).get("country_code") or country_code_for_org(org),
        "country_rules": rules,
        "categories": cats,
        "recent_jobs": jobs,
        "vehicles": vehicles,
        "user": {"id": user.get("id"), "name": user.get("full_name") or user.get("email")},
    }


# ── Country rules engine ─────────────────────────────────────────────
class CountryRuleBody(BaseModel):
    country_code: str
    country_name: str
    currency: str
    currency_symbol: Optional[str] = ""
    tax_label: str = "VAT"
    default_tax_rate: float = 0.0
    tax_rates: list[float] = []
    mileage_unit: str = "mi"
    mileage_rates: list[dict] = []
    receipt_required_threshold: float = 25.0
    approval_threshold: float = 100.0
    max_claim_limit: float = 0.0
    meal_allowance: float = 0.0
    overnight_allowance: float = 0.0
    reimbursement_method: str = "payroll"
    accounting_code_default: Optional[str] = ""
    payroll_code_default: Optional[str] = ""
    is_default: bool = False


@router.get("/settings/country-rules")
async def list_country_rules(user=Depends(get_current_user)):
    org_id = org_of(user)
    await ensure_seeded(org_id, await get_org(org_id))
    rules = await db.expense_country_rules.find(
        {"organization_id": org_id}, {"_id": 0}).sort("country_name", 1).to_list(200)
    return {"country_rules": rules}


@router.post("/settings/country-rules")
async def create_country_rule(body: CountryRuleBody, user=Depends(get_current_user)):
    _require_admin(user)
    org_id = org_of(user)
    doc = {"id": str(uuid.uuid4()), "organization_id": org_id,
           "created_at": now_iso(), "updated_at": now_iso(), **body.model_dump()}
    doc["country_code"] = doc["country_code"].upper()
    if doc["is_default"]:
        await db.expense_country_rules.update_many(
            {"organization_id": org_id}, {"$set": {"is_default": False}})
    await db.expense_country_rules.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/settings/country-rules/{rule_id}")
async def update_country_rule(rule_id: str, body: CountryRuleBody, user=Depends(get_current_user)):
    _require_admin(user)
    org_id = org_of(user)
    existing = await db.expense_country_rules.find_one({"id": rule_id, "organization_id": org_id})
    if not existing:
        raise HTTPException(404, "Rule not found")
    update = body.model_dump()
    update["country_code"] = update["country_code"].upper()
    update["updated_at"] = now_iso()
    if update["is_default"]:
        await db.expense_country_rules.update_many(
            {"organization_id": org_id}, {"$set": {"is_default": False}})
    await db.expense_country_rules.update_one(
        {"id": rule_id, "organization_id": org_id}, {"$set": update})
    return {"ok": True}


@router.delete("/settings/country-rules/{rule_id}")
async def delete_country_rule(rule_id: str, user=Depends(get_current_user)):
    _require_admin(user)
    org_id = org_of(user)
    r = await db.expense_country_rules.delete_one({"id": rule_id, "organization_id": org_id})
    if not r.deleted_count:
        raise HTTPException(404, "Rule not found")
    return {"ok": True}


# ── Category settings ────────────────────────────────────────────────
class CategoryBody(BaseModel):
    name: str
    receipt_required: bool = True
    approval_required: bool = False
    reimbursable: bool = True
    billable_to_customer: bool = False
    accounting_code: Optional[str] = ""
    payroll_code: Optional[str] = ""
    claim_limit: float = 0.0
    active: bool = True
    sort_order: int = 100


@router.get("/settings/categories")
async def list_categories(user=Depends(get_current_user)):
    org_id = org_of(user)
    await ensure_seeded(org_id, await get_org(org_id))
    cats = await db.expense_categories.find(
        {"organization_id": org_id}, {"_id": 0}).sort("sort_order", 1).to_list(300)
    return {"categories": cats}


@router.post("/settings/categories")
async def create_category(body: CategoryBody, user=Depends(get_current_user)):
    _require_admin(user)
    org_id = org_of(user)
    doc = {"id": str(uuid.uuid4()), "organization_id": org_id,
           "created_at": now_iso(), "updated_at": now_iso(), **body.model_dump()}
    await db.expense_categories.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/settings/categories/{cat_id}")
async def update_category(cat_id: str, body: CategoryBody, user=Depends(get_current_user)):
    _require_admin(user)
    org_id = org_of(user)
    update = {**body.model_dump(), "updated_at": now_iso()}
    r = await db.expense_categories.update_one(
        {"id": cat_id, "organization_id": org_id}, {"$set": update})
    if not r.matched_count:
        raise HTTPException(404, "Category not found")
    return {"ok": True}


@router.delete("/settings/categories/{cat_id}")
async def delete_category(cat_id: str, user=Depends(get_current_user)):
    _require_admin(user)
    org_id = org_of(user)
    # Soft-delete to preserve historical expense links.
    r = await db.expense_categories.update_one(
        {"id": cat_id, "organization_id": org_id}, {"$set": {"active": False}})
    if not r.matched_count:
        raise HTTPException(404, "Category not found")
    return {"ok": True}
