"""
GymAxis Expenses — shared helpers (iter 278, Phase 1).

A connected expenses subsystem: receipt photo scanner (AI OCR), manual
entry, mileage claims, out-of-pocket claims, job/customer/site/vehicle
linking, a per-country rules engine, approval + reimbursement workflow,
accounting export, reports, dashboards and a full audit trail.

Everything is scoped by ``organization_id`` (and ``user_id`` for non
reviewers). Partner-engineer orgs are isolated personal orgs, so their
users only ever see their own expenses.
"""
from __future__ import annotations

import base64
import json as _json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from utils.database import db, put_object, APP_NAME, EMERGENT_LLM_KEY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/expenses", tags=["Expenses (iter 278)"])

# ── status / role constants ──────────────────────────────────────────
DRAFT, SUBMITTED, NEEDS_DETAILS = "draft", "submitted", "needs_details"
APPROVED, REJECTED, EXPORTED = "approved", "rejected", "exported"
REIMBURSED, CANCELLED = "reimbursed", "cancelled"
OPEN_STATUSES = {DRAFT, SUBMITTED, NEEDS_DETAILS, APPROVED, EXPORTED}
LOCKED_STATUSES = {EXPORTED, REIMBURSED}  # not normally editable

REVIEW_ROLES = {"owner", "manager", "finance", "admin", "pulse_master_admin"}
EXPENSE_TYPES = {"receipt", "manual", "mileage", "out_of_pocket"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def org_of(user: dict) -> str:
    org = user.get("organization_id") or user.get("service_org_id")
    if not org:
        raise HTTPException(403, "Organization context required")
    return org


def can_review(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    if role in REVIEW_ROLES:
        return True
    return bool(
        user.get("is_master_admin") or user.get("is_pulse_admin")
        or user.get("is_service_desk") or user.get("is_finance")
    )


def scope_filter(user: dict) -> dict:
    """Reviewers see the whole org; everyone else only their own."""
    f = {"organization_id": org_of(user)}
    if not can_review(user):
        f["user_id"] = user.get("id")
    return f


async def get_org(org_id: str) -> dict:
    return await db.organizations.find_one({"id": org_id}, {"_id": 0}) or {}


def is_solo_org(org: dict) -> bool:
    return bool(org.get("is_engineer_personal_org")
                or org.get("account_type") == "partner_engineer")


def approval_mode(org: dict) -> str:
    """'off' for solo/independent engineers, 'on' for operators."""
    return "off" if is_solo_org(org) else "on"


# ── country mapping + defaults (the rules engine seeds these) ────────
_COUNTRY_MAP = {
    "england": "GB", "uk": "GB", "united kingdom": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB", "gb": "GB", "gbr": "GB",
    "united states": "US", "usa": "US", "us": "US", "america": "US",
    "germany": "DE", "deutschland": "DE", "de": "DE",
    "ireland": "IE", "ie": "IE", "france": "FR", "fr": "FR",
    "spain": "ES", "es": "ES", "netherlands": "NL", "nl": "NL",
}


def country_code_for_org(org: dict) -> str:
    c = (org.get("country") or org.get("country_code") or "").strip().lower()
    return _COUNTRY_MAP.get(c, "GB" if not c else (c.upper()[:2]))


def _rule(code, name, currency, symbol, tax_label, default_rate, rates,
          unit, mileage, **extra):
    base = {
        "country_code": code, "country_name": name, "currency": currency,
        "currency_symbol": symbol, "tax_label": tax_label,
        "default_tax_rate": default_rate, "tax_rates": rates,
        "mileage_unit": unit, "mileage_rates": mileage,
        "receipt_required_threshold": 25.0, "approval_threshold": 100.0,
        "max_claim_limit": 0.0, "meal_allowance": 0.0,
        "overnight_allowance": 0.0, "reimbursement_method": "payroll",
        "accounting_code_default": "", "payroll_code_default": "",
    }
    base.update(extra)
    return base


DEFAULT_COUNTRY_RULES = [
    _rule("GB", "United Kingdom", "GBP", "£", "VAT", 20.0, [0, 5, 20], "mi",
          [{"type": "personal_car", "label": "Personal car", "rate": 0.45},
           {"type": "company_car", "label": "Company car", "rate": 0.14},
           {"type": "electric", "label": "Electric vehicle", "rate": 0.45},
           {"type": "motorcycle", "label": "Motorcycle", "rate": 0.24},
           {"type": "bicycle", "label": "Bicycle", "rate": 0.20}]),
    _rule("US", "United States", "USD", "$", "Sales Tax", 0.0, [0, 6, 7, 8.25], "mi",
          [{"type": "personal_car", "label": "Personal vehicle (IRS)", "rate": 0.67},
           {"type": "motorcycle", "label": "Motorcycle", "rate": 0.65}]),
    _rule("DE", "Germany", "EUR", "€", "VAT (MwSt)", 19.0, [0, 7, 19], "km",
          [{"type": "personal_car", "label": "PKW", "rate": 0.30},
           {"type": "motorcycle", "label": "Motorrad", "rate": 0.20}]),
    _rule("OTHER", "Other / configurable", "USD", "", "Tax", 0.0, [0], "km",
          [{"type": "personal_car", "label": "Vehicle", "rate": 0.30}]),
]

DEFAULT_CATEGORIES = [
    ("Fuel", True, True, True), ("Mileage", False, False, True),
    ("Parking", True, True, True), ("Tolls", True, False, True),
    ("Train", True, True, True), ("Taxi", True, True, True),
    ("Flights", True, True, True), ("Hotel", True, True, True),
    ("Meals", True, True, False), ("Tools", True, True, False),
    ("Parts", True, True, True), ("PPE", True, False, False),
    ("Uniform", True, False, False), ("Phone/Internet", True, False, False),
    ("Office Supplies", True, False, False),
    ("Client Entertainment", True, True, False),
    ("Training", True, True, False), ("Subscriptions", True, False, False),
    ("Miscellaneous", True, True, False),
]


async def ensure_seeded(org_id: str, org: dict) -> None:
    """Idempotently seed default country rules + categories for an org."""
    if await db.expense_country_rules.count_documents({"organization_id": org_id}) == 0:
        default_code = country_code_for_org(org)
        docs = []
        for r in DEFAULT_COUNTRY_RULES:
            doc = {"id": str(uuid.uuid4()), "organization_id": org_id,
                   "is_default": r["country_code"] == default_code,
                   "created_at": now_iso(), "updated_at": now_iso(), **r}
            docs.append(doc)
        if not any(d["is_default"] for d in docs):
            docs[0]["is_default"] = True
        await db.expense_country_rules.insert_many(docs)
    if await db.expense_categories.count_documents({"organization_id": org_id}) == 0:
        cats = []
        for i, (name, receipt_req, approval_req, billable) in enumerate(DEFAULT_CATEGORIES):
            cats.append({
                "id": str(uuid.uuid4()), "organization_id": org_id, "name": name,
                "receipt_required": receipt_req, "approval_required": approval_req,
                "reimbursable": True, "billable_to_customer": billable,
                "accounting_code": "", "payroll_code": "", "claim_limit": 0.0,
                "active": True, "sort_order": i,
                "created_at": now_iso(), "updated_at": now_iso(),
            })
        await db.expense_categories.insert_many(cats)


async def default_country_rule(org_id: str) -> dict:
    rule = await db.expense_country_rules.find_one(
        {"organization_id": org_id, "is_default": True}, {"_id": 0})
    if not rule:
        rule = await db.expense_country_rules.find_one(
            {"organization_id": org_id}, {"_id": 0})
    return rule or {}


# ── audit trail ──────────────────────────────────────────────────────
async def audit(expense: dict, actor: dict, action: str, *, field: str | None = None,
                old=None, new=None, note: str | None = None) -> None:
    try:
        await db.expense_events.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": expense.get("organization_id"),
            "expense_id": expense.get("id"),
            "actor_id": actor.get("id"),
            "actor_name": actor.get("full_name") or actor.get("email") or "",
            "action": action, "field": field,
            "old_value": old, "new_value": new, "note": note,
            "job_id": expense.get("job_id"), "customer_id": expense.get("customer_id"),
            "site_id": expense.get("site_id"),
            "at": now_iso(),
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("[expenses] audit failed: %s", exc)


# ── receipt storage (private — served via authed endpoint) ───────────
async def upload_receipt(data: bytes, content_type: str, org_id: str,
                         filename: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "jpg").lower()[:5]
    path = f"{APP_NAME}/expense-receipts/{org_id}/{uuid.uuid4()}.{ext}"
    put_object(path, data, content_type or "image/jpeg")
    return path


# ── AI receipt OCR (OpenAI gpt-4o vision via Emergent key) ───────────
_OCR_SYSTEM = (
    "You are an expert receipt-scanning assistant for a field-service "
    "expenses app. Extract structured data from the receipt image and "
    "return ONLY valid JSON with these keys: "
    "{\"is_receipt\": bool, \"merchant_name\": str, \"merchant_address\": str, "
    "\"merchant_country\": str (ISO-2 if known else \"\"), \"date\": "
    "\"YYYY-MM-DD\" or \"\", \"time\": str, \"total_amount\": number, "
    "\"tax_amount\": number, \"tax_rate\": number, \"currency\": "
    "\"ISO-4217 e.g. GBP/USD/EUR\", \"receipt_number\": str, "
    "\"payment_method\": str, \"line_items\": [{\"description\": str, "
    "\"amount\": number}], \"category_suggestion\": str, \"confidence\": "
    "number 0-1}. Use 0 for unknown numbers and \"\" for unknown strings. "
    "Never invent values."
)


async def ocr_receipt(image_base64: str) -> dict:
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"expense_ocr_{uuid.uuid4()}",
            system_message=_OCR_SYSTEM,
        ).with_model("openai", "gpt-4o")
        msg = UserMessage(
            text="Extract the expense data from this receipt as JSON.",
            file_contents=[ImageContent(image_base64=image_base64)],
        )
        raw = (await chat.send_message(msg)).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
        data = _json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[expenses] OCR failed: %s", exc)
        return {}


def receipt_warnings(extracted: dict, duplicate: bool) -> list[str]:
    w = []
    if extracted.get("is_receipt") is False:
        w.append("This doesn't look like a receipt — please check the image.")
    if not extracted.get("total_amount"):
        w.append("No total amount detected — add it manually.")
    if not extracted.get("date"):
        w.append("No date detected — add it manually.")
    if not extracted.get("tax_amount"):
        w.append("No tax/VAT detected — confirm if applicable.")
    if not extracted.get("merchant_name"):
        w.append("Merchant name not detected.")
    conf = extracted.get("confidence")
    if isinstance(conf, (int, float)) and conf < 0.5:
        w.append("Low scan confidence — the image may be blurry. Please review.")
    if duplicate:
        w.append("This looks similar to an expense already submitted.")
    return w


async def find_duplicate(org_id: str, user_id: str, merchant: str | None,
                         amount, txn_date: str | None,
                         exclude_id: str | None = None) -> dict | None:
    if not (amount and txn_date):
        return None
    q = {
        "organization_id": org_id, "user_id": user_id,
        "gross_amount": amount, "transaction_date": txn_date,
        "status": {"$ne": CANCELLED},
    }
    if merchant:
        q["merchant"] = {"$regex": f"^{merchant.strip()}$", "$options": "i"}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    dup = await db.expenses.find_one(
        q, {"_id": 0, "id": 1, "reference": 1, "merchant": 1})
    return dup


def public_expense(e: dict) -> dict:
    e = dict(e)
    e.pop("_id", None)
    return e


__all__ = ["router"]
