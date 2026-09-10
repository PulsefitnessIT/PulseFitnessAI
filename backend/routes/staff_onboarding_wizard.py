"""Staff Onboarding, Offer Letter & Employment Contract Wizard (Phase 1 spine).

Extends Operations → Staffing → People. The single person record is
``staff_members`` (never duplicated) which progresses:
    candidate → recruit → onboarding → offer_issued → contract_issued → employee.

All legal wording is uploaded/approved by Pulse HR & legal; anything seeded here
is a clearly-marked NON-BINDING SAMPLE placeholder.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.responses import Response as FileResponse
from pydantic import BaseModel

from utils.database import db
from utils.auth import get_current_user, get_current_user_portal, hash_password, create_token, verify_password

logger = logging.getLogger(__name__)

try:
    from utils.email import send_email
except Exception:  # pragma: no cover
    async def send_email(*a, **k):
        return False

FRONTEND_URL = os.environ.get("FRONTEND_URL", "").rstrip("/")

router = APIRouter()

# ───────────────────────── object storage ─────────────────────────
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "pulsefitness"
_storage_key: Optional[str] = None


def _init_storage() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _put_object(path: str, data: bytes, content_type: str) -> dict:
    key = _init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type},
                        data=data, timeout=120)
    if resp.status_code == 403:  # key expired
        globals()["_storage_key"] = None
        key = _init_storage()
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": key, "Content-Type": content_type},
                            data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()


def _get_object(path: str):
    key = _init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
        "pdf": "application/pdf", "heic": "image/heic", "gif": "image/gif"}

# ───────────────────────── helpers ─────────────────────────
HR_ROLES = {"owner", "manager", "master_admin"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _org(user: dict) -> str:
    return user.get("organization_id")


def _require_hr(user: dict):
    if user.get("role") not in HR_ROLES:
        raise HTTPException(403, "HR access required")


def _strip(d):
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items() if k != "_id"}
    if isinstance(d, list):
        return [_strip(x) for x in d]
    return d


def _doc_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _audit(org: str, case_id: str, event: str, user: dict, **extra):
    await db.staff_onboarding_audit_events.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case_id,
        "event": event, "user_id": user.get("id"), "user_name": user.get("full_name"),
        "user_role": user.get("role"), "at": _now(),
        **{k: v for k, v in extra.items() if v is not None},
    })


SENSITIVE_FORM_FIELDS = {"ni_number", "bank_account", "sort_code", "bank_sort_code", "account_number"}


def _mask(val) -> str:
    s = str(val or "")
    if len(s) <= 4:
        return "••••"
    return "••••" + s[-4:]


def _mask_forms(forms: list, reveal: bool):
    if reveal:
        return forms
    out = []
    for f in forms:
        data = dict(f.get("data") or {})
        for k in list(data.keys()):
            if k.lower() in SENSITIVE_FORM_FIELDS and data[k]:
                data[k] = _mask(data[k])
        f = {**f, "data": data}
        out.append(f)
    return out


def _email_shell(title: str, lines: list[str], cta_url: str | None = None, cta_label: str | None = None) -> str:
    body = "".join(f'<p style="margin:0 0 12px;color:#334;line-height:1.5">{ln}</p>' for ln in lines)
    cta = ""
    if cta_url:
        cta = (f'<a href="{cta_url}" style="display:inline-block;margin-top:8px;background:#19CDFF;'
               f'color:#0b2530;font-weight:700;text-decoration:none;padding:12px 22px;border-radius:10px">'
               f'{cta_label or "Open portal"}</a>')
    return (
        f'<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:auto;'
        f'border:1px solid #e3ebf0;border-radius:16px;overflow:hidden">'
        f'<div style="background:#0c2430;padding:18px 24px"><span style="color:#fff;font-weight:800;font-size:18px">'
        f'Pulse Fitness</span></div>'
        f'<div style="padding:24px"><h2 style="margin:0 0 14px;color:#11222c">{title}</h2>{body}{cta}'
        f'<p style="margin:18px 0 0;color:#889;font-size:12px">This is a secure notification from Pulse Fitness. '
        f'It contains no confidential terms — please sign in to your portal to view details.</p></div></div>'
    )


async def _notify(org, case_id, audience, staff_id, event, message,
                  email_to=None, email_subject=None, email_html=None, attachments=None):
    """Record an in-app notification and (best-effort) send a neutral email."""
    await db.staff_onboarding_notifications.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case_id,
        "audience": audience, "staff_id": staff_id, "event": event, "message": message,
        "read": False, "created_at": _now(),
    })
    if email_to and email_subject and email_html:
        try:
            await send_email(to=email_to, subject=email_subject, html=email_html,
                             attachments=attachments,
                             organization_id=org, kind="staff_onboarding")
        except Exception:
            pass


def _render(template_body: str, ctx: dict) -> str:
    out = template_body or ""
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", "" if v is None else str(v))
    return out


def _merge_ctx(case: dict, staff: dict) -> dict:
    ep = case.get("employment_proposal", {})
    nm = staff.get("full_name") or ""
    return {
        "legal_name": nm, "preferred_name": ep.get("preferred_name") or nm.split(" ")[0],
        "home_address": staff.get("address") or ep.get("home_address") or "",
        "date": datetime.now(timezone.utc).strftime("%d %B %Y"),
        "company": ep.get("employing_company") or "Pulse Fitness",
        "job_title": ep.get("job_title") or ep.get("position") or "",
        "department": ep.get("department") or "", "site": ep.get("site") or ep.get("place_of_work") or "",
        "line_manager": ep.get("line_manager") or "", "start_date": ep.get("proposed_start_date") or "",
        "salary": ep.get("salary") or "", "pay_frequency": ep.get("pay_frequency") or "Monthly",
        "hours": ep.get("hours_per_week") or "", "employment_type": ep.get("employment_type") or "",
        "probation": ep.get("probation_period") or "", "notice_period": ep.get("notice_period") or "",
        "holiday": ep.get("holiday_entitlement") or "", "benefits": ep.get("benefits") or "",
        "pension": ep.get("pension") or "", "bonus": ep.get("bonus_commission") or "",
        "hr_contact": case.get("hr_contact") or "", "signatory": ep.get("authorised_signatory") or "",
    }


# fields compared for the offer↔contract consistency check
CONSISTENCY_FIELDS = ["job_title", "company", "start_date", "site", "salary", "hours",
                      "employment_type", "probation", "holiday", "notice_period", "benefits", "bonus"]

# ───────────────────────── models ─────────────────────────
class DupCheck(BaseModel):
    personal_email: Optional[str] = None
    work_email: Optional[str] = None
    mobile: Optional[str] = None
    candidate_reference: Optional[str] = None
    legal_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    ni_number: Optional[str] = None


class CaseCreate(BaseModel):
    link_staff_id: Optional[str] = None          # existing person/candidate
    candidate_reference: Optional[str] = None
    title: Optional[str] = None
    legal_first_name: Optional[str] = None
    middle_names: Optional[str] = None
    surname: Optional[str] = None
    preferred_name: Optional[str] = None
    personal_email: Optional[str] = None
    mobile: Optional[str] = None
    position: Optional[str] = None
    proposed_start_date: Optional[str] = None
    override_duplicate: bool = False


class CasePatch(BaseModel):
    employment_proposal: Optional[dict] = None
    role_requirements: Optional[dict] = None
    package: Optional[str] = None
    hr_contact: Optional[str] = None


class InviteBody(BaseModel):
    message: Optional[str] = None
    deadline: Optional[str] = None
    mfa_required: bool = False
    expiry_days: int = 14


class OfferCreate(BaseModel):
    template_id: str
    conditions: list[dict] = []
    offer_expiry_date: Optional[str] = None
    overrides: dict = {}


class ContractCreate(BaseModel):
    template_id: str
    schedules: list[str] = []
    override_reason: Optional[str] = None
    difference_ack: dict = {}


class ApproveBody(BaseModel):
    comment: Optional[str] = None


class AcceptInvite(BaseModel):
    token: str
    password: str


class FormSave(BaseModel):
    form_key: str
    data: dict


class Ack(BaseModel):
    signature_name: Optional[str] = None


class SignBody(BaseModel):
    signature_name: str
    signature_method: str = "typed"   # typed | drawn | click
    signature_image: Optional[str] = None
    acknowledge: bool = True


class OfferRespond(BaseModel):
    action: str                        # accept | decline | clarify
    signature_name: Optional[str] = None
    intended_start_date: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None


# ───────────────────────── settings / seed ─────────────────────────
PACKAGES = [
    {"id": "standard", "name": "Standard Employee"},
    {"id": "engineer", "name": "Field Service Engineer"},
    {"id": "warehouse", "name": "Warehouse / Stores"},
    {"id": "office", "name": "Office / Administration"},
    {"id": "sales", "name": "Sales"},
    {"id": "manager", "name": "Manager"},
    {"id": "director", "name": "Director"},
    {"id": "temporary", "name": "Temporary Worker"},
    {"id": "custom", "name": "Custom Package"},
]

SAMPLE_NOTE = "SAMPLE — non-binding placeholder. Pulse Fitness HR/legal must upload and approve final wording."

SEED_OFFER_TEMPLATES = [
    ("standard_offer", "Standard Employee Offer", ["standard", "office"]),
    ("engineer_offer", "Field Service Engineer Offer", ["engineer"]),
    ("sales_offer", "Sales Offer", ["sales"]),
    ("manager_offer", "Manager Offer", ["manager"]),
    ("director_offer", "Director Offer", ["director"]),
    ("temp_offer", "Temporary Employment Offer", ["temporary"]),
]
OFFER_BODY = (
    "{{date}}\n\n"
    "PRIVATE & CONFIDENTIAL\n"
    "{{legal_name}}\n"
    "{{home_address}}\n\n"
    "Dear {{preferred_name}},\n\n"
    "OFFER OF EMPLOYMENT — {{job_title}}\n\n"
    "We are delighted to offer you the position of {{job_title}} in the {{department}} "
    "department at {{company}}, based at {{site}} and reporting to {{line_manager}}.\n\n"
    "The principal terms of our offer are as follows:\n\n"
    "  • Position: {{job_title}} ({{employment_type}})\n"
    "  • Proposed start date: {{start_date}}\n"
    "  • Salary: {{salary}}, paid {{pay_frequency}}\n"
    "  • Hours of work: {{hours}} hours per week\n"
    "  • Probationary period: {{probation}}\n"
    "  • Notice period: {{notice_period}}\n"
    "  • Holiday entitlement: {{holiday}}\n"
    "  • Pension: {{pension}}\n"
    "  • Other benefits: {{benefits}}\n\n"
    "This offer is conditional upon:\n"
    "  1. Receipt of satisfactory employment references;\n"
    "  2. Verification of your right to work in the UK;\n"
    "  3. Where applicable, a satisfactory DBS (Disclosure & Barring Service) check; and\n"
    "  4. Completion of your onboarding documentation.\n\n"
    "Your full terms and conditions will be set out in your Contract of Employment, which "
    "will be issued once you have accepted this offer.\n\n"
    "To accept, please review and sign this letter electronically in your Pulse Fitness "
    "New Starter Portal.\n\n"
    "We look forward to welcoming you to the team.\n\n"
    "Yours sincerely,\n\n"
    "{{signatory}}\n"
    "For and on behalf of {{company}}\n\n"
    "[Pulse Fitness placeholder wording — HR may edit this template in Operations → "
    "Staffing → Staff Onboarding → Templates before issue.]"
)

SEED_CONTRACT_TEMPLATES = [
    ("perm_ft", "Permanent Full-Time", ["standard", "office", "manager"]),
    ("perm_pt", "Permanent Part-Time", ["standard", "office"]),
    ("engineer_contract", "Field Service Engineer", ["engineer"]),
    ("sales_contract", "Sales / Commission", ["sales"]),
    ("manager_contract", "Manager", ["manager"]),
    ("director_contract", "Director", ["director"]),
    ("fixed_term", "Fixed-Term", ["temporary"]),
]
CONTRACT_BODY = (
    "CONTRACT OF EMPLOYMENT\n"
    "(Written Statement of Employment Particulars — Employment Rights Act 1996)\n\n"
    "This agreement is made between {{company}} (\"the Employer\") and {{legal_name}} "
    "(\"the Employee\").\n\n"
    "1. COMMENCEMENT\n"
    "   Your employment begins on {{start_date}}. No previous employment counts towards "
    "your period of continuous employment unless stated otherwise in writing.\n\n"
    "2. JOB TITLE & DUTIES\n"
    "   You are employed as {{job_title}} in the {{department}} department, reporting to "
    "{{line_manager}}. You may be required to carry out other reasonable duties.\n\n"
    "3. PLACE OF WORK\n"
    "   Your normal place of work is {{site}}. You may be required to work at other "
    "Company locations from time to time.\n\n"
    "4. HOURS OF WORK\n"
    "   Your normal hours of work are {{hours}} hours per week. This is a "
    "{{employment_type}} position.\n\n"
    "5. REMUNERATION\n"
    "   Your salary is {{salary}}, paid {{pay_frequency}} in arrears by BACS.\n\n"
    "6. PROBATIONARY PERIOD\n"
    "   Your employment is subject to a probationary period of {{probation}}.\n\n"
    "7. HOLIDAY\n"
    "   Your holiday entitlement is {{holiday}} (inclusive of statutory bank holidays), "
    "based on the Company's holiday year.\n\n"
    "8. SICKNESS ABSENCE\n"
    "   Sick pay arrangements, including Statutory Sick Pay, are set out in the Employee "
    "Handbook.\n\n"
    "9. PENSION\n"
    "   {{pension}} You will be auto-enrolled into the Company's workplace pension scheme "
    "in accordance with statutory requirements.\n\n"
    "10. NOTICE\n"
    "    Either party may terminate this employment by giving {{notice_period}} written "
    "notice, subject to statutory minimum notice periods.\n\n"
    "11. BENEFITS & VARIABLE PAY\n"
    "    {{benefits}} {{bonus}}\n\n"
    "12. POLICIES & PROCEDURES\n"
    "    You must comply with the Company's policies and procedures (including "
    "disciplinary, grievance, equality, data protection, IT and anti-bribery), as amended "
    "from time to time.\n\n"
    "13. CONFIDENTIALITY & INTELLECTUAL PROPERTY\n"
    "    You must keep the Company's confidential information secure. All intellectual "
    "property created in the course of your employment belongs to the Company.\n\n"
    "14. DATA PROTECTION\n"
    "    The Company processes your personal data in accordance with UK GDPR and the "
    "Data Protection Act 2018.\n\n"
    "15. GOVERNING LAW\n"
    "    This contract is governed by the law of England and Wales.\n\n"
    "By signing below, both parties agree to the terms set out above and in any schedules "
    "attached to this contract.\n\n"
    "Signed for and on behalf of {{company}}: ____________________   Date: __________\n"
    "Employee ({{legal_name}}): ____________________   Date: __________\n\n"
    "[Pulse Fitness placeholder wording — HR/Legal must review and adapt this template "
    "before use. Edit in Operations → Staffing → Staff Onboarding → Templates.]"
)

SEED_POLICIES = [
    ("anti_bribery", "Anti-Bribery Policy"),
    ("equality", "Equality and Diversity Policy"),
    ("it_policy", "IT Policy"),
    ("modern_slavery", "Modern Slavery and Human Trafficking Policy"),
    ("whistleblowing", "Whistleblowing Policy"),
]
SEED_AGREEMENTS = [
    ("opt_out_48", "48-Hour Opt-Out Agreement"),
    ("vehicle_rules", "Company Vehicle Rules"),
    ("deductions", "Deductions From Pay Agreement"),
    ("restrictive_covenant", "Restrictive Covenant Agreement"),
]


async def _ensure_seed(org: str, user: dict):
    if await db.staff_onboarding_settings.find_one({"organization_id": org}):
        return
    await db.staff_onboarding_settings.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org, "packages": PACKAGES,
        "mfa_default": False, "invite_expiry_days": 14, "sample_notice": SAMPLE_NOTE,
        "email_pack_on_activation": True, "pack_recipient_emails": [],
        "created_at": _now(),
    })
    for tid, name, roles in SEED_OFFER_TEMPLATES:
        await db.staff_offer_templates.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "key": tid, "title": name,
            "target_roles": roles, "version": 1, "status": "published", "is_sample": True,
            "body": OFFER_BODY, "note": SAMPLE_NOTE, "created_at": _now()})
    for tid, name, roles in SEED_CONTRACT_TEMPLATES:
        await db.staff_contract_templates.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "key": tid, "title": name,
            "target_roles": roles, "version": 1, "status": "published", "is_sample": True,
            "body": CONTRACT_BODY, "note": SAMPLE_NOTE, "created_at": _now()})
    for pid, name in SEED_POLICIES:
        await db.staff_policy_versions.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "key": pid, "title": name,
            "version": 1, "effective_date": _now(), "acknowledgement_required": True,
            "summary": f"{name} — {SAMPLE_NOTE}",
            "body": f"{name}\n\n{SAMPLE_NOTE}\n\n(Full policy text to be uploaded by HR.)",
            "is_sample": True, "created_at": _now()})
    for aid, name in SEED_AGREEMENTS:
        await db.staff_agreement_versions.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "key": aid, "title": name,
            "version": 1, "effective_date": _now(), "requires_signature": True,
            "body": f"{name}\n\n{SAMPLE_NOTE}\n\n(Full agreement wording to be uploaded by HR.)",
            "is_sample": True, "created_at": _now()})


# ═════════════════════════ HR ENDPOINTS ═════════════════════════
@router.get("/staff-onboarding/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user); await _ensure_seed(org, user)
    s = await db.staff_onboarding_settings.find_one({"organization_id": org})
    s = dict(s or {})
    s.setdefault("email_pack_on_activation", True)
    s.setdefault("pack_recipient_emails", [])
    return _strip(s)


class SettingsPatch(BaseModel):
    email_pack_on_activation: Optional[bool] = None
    pack_recipient_emails: Optional[list[str]] = None


@router.put("/staff-onboarding/settings")
async def update_settings(body: SettingsPatch, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user); await _ensure_seed(org, user)
    upd = {"updated_at": _now()}
    if body.email_pack_on_activation is not None:
        upd["email_pack_on_activation"] = body.email_pack_on_activation
    if body.pack_recipient_emails is not None:
        cleaned = [e.strip() for e in body.pack_recipient_emails if e and "@" in e]
        upd["pack_recipient_emails"] = cleaned
    await db.staff_onboarding_settings.update_one({"organization_id": org}, {"$set": upd})
    s = await db.staff_onboarding_settings.find_one({"organization_id": org})
    return _strip(s)


@router.get("/staff-onboarding/packages")
async def get_packages(user: dict = Depends(get_current_user)):
    _require_hr(user); return {"packages": PACKAGES}


@router.get("/staff-onboarding/templates")
async def get_templates(user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user); await _ensure_seed(org, user)
    return {
        "offer": [_strip(t) for t in await db.staff_offer_templates.find({"organization_id": org}).to_list(100)],
        "contract": [_strip(t) for t in await db.staff_contract_templates.find({"organization_id": org}).to_list(100)],
        "policies": [_strip(t) for t in await db.staff_policy_versions.find({"organization_id": org}).to_list(100)],
        "agreements": [_strip(t) for t in await db.staff_agreement_versions.find({"organization_id": org}).to_list(100)],
    }


# ───────── company policies & agreements (multi-tenant document management) ─────────
def _slugify(title: str) -> str:
    base = "".join(ch if ch.isalnum() else "_" for ch in (title or "").lower()).strip("_")
    return (base or "doc")[:32] + "_" + uuid.uuid4().hex[:6]


def _extract_pdf_text(data: bytes) -> str:
    try:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        return "\n".join(p.get_text() for p in doc)[:20000]
    except Exception:
        logger.exception("pdf text extraction failed")
        return ""


async def _detect_signature_fields(text: str, session: str) -> dict:
    """AI reads an uploaded document's text and reports where signatures/initials/dates are required."""
    if not (text or "").strip():
        return {"requires_signature": False, "signature_fields": [], "summary": "No readable text found in document."}
    system = ("You are a document analyst for a UK employer. Given the text of an HR / employment / policy "
              "document, identify every place where a person must SIGN, INITIAL or DATE (e.g. 'Signature:', "
              "'Signed', 'Initials', 'Employee signature', 'Date', signature blocks). Return STRICT JSON only: "
              '{"requires_signature": true|false, "signature_fields": [{"label": "", "type": "signature|initial|date"}], '
              '"summary": "one short sentence"}. If none are found, requires_signature=false with an empty list.')
    try:
        raw = await _ai_chat(system, text[:12000], session)
        parsed = _ai_json(raw)
        if not parsed:
            return {"requires_signature": False, "signature_fields": [], "summary": (raw or "")[:150]}
        parsed.setdefault("signature_fields", [])
        parsed["requires_signature"] = bool(parsed.get("requires_signature")) or len(parsed["signature_fields"]) > 0
        return parsed
    except Exception as e:
        return {"requires_signature": False, "signature_fields": [], "summary": f"AI detection unavailable: {e}"}


class PolicyBody(BaseModel):
    title: str
    acknowledgement_required: bool = True
    body: Optional[str] = None


class PolicyPatch(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    acknowledgement_required: Optional[bool] = None


class AgreementBody(BaseModel):
    title: str
    requires_signature: bool = True
    body: Optional[str] = None


class AgreementPatch(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    requires_signature: Optional[bool] = None


_DOC_KIND = {
    "policies": ("staff_policy_versions", "acknowledgement_required"),
    "agreements": ("staff_agreement_versions", "requires_signature"),
}


def _doc_coll(kind: str):
    if kind not in _DOC_KIND:
        raise HTTPException(400, "kind must be 'policies' or 'agreements'")
    return getattr(db, _DOC_KIND[kind][0]), _DOC_KIND[kind][1]


@router.post("/staff-onboarding/policies")
async def create_policy(body: PolicyBody, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user); await _ensure_seed(org, user)
    key = _slugify(body.title)
    doc = {"id": str(uuid.uuid4()), "organization_id": org, "key": key, "title": body.title,
           "version": 1, "effective_date": _now(), "acknowledgement_required": body.acknowledgement_required,
           "summary": "", "body": body.body or "", "is_sample": False, "created_at": _now()}
    await db.staff_policy_versions.insert_one(dict(doc))
    return _strip(doc)


@router.put("/staff-onboarding/policies/{key}")
async def update_policy(key: str, body: PolicyPatch, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    pol = await db.staff_policy_versions.find_one({"organization_id": org, "key": key})
    if not pol:
        raise HTTPException(404, "Policy not found")
    upd = {"updated_at": _now(), "is_sample": False}
    if body.title is not None: upd["title"] = body.title
    if body.body is not None: upd["body"] = body.body
    if body.acknowledgement_required is not None: upd["acknowledgement_required"] = body.acknowledgement_required
    await db.staff_policy_versions.update_one({"id": pol["id"]}, {"$set": upd})
    return _strip(await db.staff_policy_versions.find_one({"id": pol["id"]}))


@router.delete("/staff-onboarding/policies/{key}")
async def delete_policy(key: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    r = await db.staff_policy_versions.delete_one({"organization_id": org, "key": key})
    return {"ok": True, "deleted": r.deleted_count}


@router.post("/staff-onboarding/agreements")
async def create_agreement(body: AgreementBody, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user); await _ensure_seed(org, user)
    key = _slugify(body.title)
    doc = {"id": str(uuid.uuid4()), "organization_id": org, "key": key, "title": body.title,
           "version": 1, "effective_date": _now(), "requires_signature": body.requires_signature,
           "body": body.body or "", "is_sample": False, "created_at": _now()}
    await db.staff_agreement_versions.insert_one(dict(doc))
    return _strip(doc)


@router.put("/staff-onboarding/agreements/{key}")
async def update_agreement(key: str, body: AgreementPatch, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    ag = await db.staff_agreement_versions.find_one({"organization_id": org, "key": key})
    if not ag:
        raise HTTPException(404, "Agreement not found")
    upd = {"updated_at": _now(), "is_sample": False}
    if body.title is not None: upd["title"] = body.title
    if body.body is not None: upd["body"] = body.body
    if body.requires_signature is not None: upd["requires_signature"] = body.requires_signature
    await db.staff_agreement_versions.update_one({"id": ag["id"]}, {"$set": upd})
    return _strip(await db.staff_agreement_versions.find_one({"id": ag["id"]}))


@router.delete("/staff-onboarding/agreements/{key}")
async def delete_agreement(key: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    r = await db.staff_agreement_versions.delete_one({"organization_id": org, "key": key})
    return {"ok": True, "deleted": r.deleted_count}


@router.post("/staff-onboarding/cases/{case_id}/upload")
async def hr_upload(case_id: str, file: UploadFile = File(...), document_type: str = Form("other"),
                    user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    return await _store_upload(org, case_id, c["staff_id"], file, document_type, user)


@router.post("/staff-onboarding/{kind}/{key}/upload")
async def upload_company_doc(kind: str, key: str, file: UploadFile = File(...),
                             user: dict = Depends(get_current_user)):
    """Upload a company's own policy/agreement PDF. Extracts the text so recruits can
    read it, then runs AI to detect where signatures/initials/dates are required."""
    _require_hr(user); org = _org(user); await _ensure_seed(org, user)
    coll, flag = _doc_coll(kind)
    doc = await coll.find_one({"organization_id": org, "key": key})
    if not doc:
        raise HTTPException(404, "Document not found")
    data = await file.read()
    ext = (file.filename or "f.pdf").rsplit(".", 1)[-1].lower()
    path = f"{APP_NAME}/onboarding/{org}/{kind}/{key}-{uuid.uuid4().hex[:8]}.{ext}"
    result = _put_object(path, data, file.content_type or MIME.get(ext, "application/pdf"))
    text = _extract_pdf_text(data) if ext == "pdf" else ""
    ai = await _detect_signature_fields(text, f"{kind}-{org}-{key}")
    upd = {"pdf_path": result["path"], "pdf_filename": file.filename, "updated_at": _now(),
           "is_sample": False, "version": (doc.get("version", 1) + 1),
           "signature_fields": ai.get("signature_fields", []), "ai_summary": ai.get("summary")}
    if text:
        upd["body"] = text
    if kind == "agreements":
        upd["requires_signature"] = bool(ai.get("requires_signature"))
    await coll.update_one({"id": doc["id"]}, {"$set": upd})
    return {"ok": True, "ai": ai, "text_chars": len(text), "filename": file.filename}



# ───────────────────────── template builder (Phase 2) ─────────────────────────
MERGE_FIELDS = [
    ("legal_name", "Employee legal full name"),
    ("preferred_name", "Preferred / first name"),
    ("home_address", "Home address"),
    ("date", "Document date (today)"),
    ("company", "Employing company"),
    ("job_title", "Job title"),
    ("department", "Department"),
    ("site", "Site / place of work"),
    ("line_manager", "Line manager"),
    ("start_date", "Proposed start date"),
    ("salary", "Salary"),
    ("pay_frequency", "Pay frequency"),
    ("hours", "Hours per week"),
    ("employment_type", "Employment type"),
    ("probation", "Probation period"),
    ("notice_period", "Notice period"),
    ("holiday", "Holiday entitlement"),
    ("benefits", "Benefits"),
    ("pension", "Pension"),
    ("bonus", "Bonus / commission"),
    ("hr_contact", "HR contact name"),
    ("signatory", "Authorised signatory"),
]

_TMPL_COLL = {"offer": "staff_offer_templates", "contract": "staff_contract_templates"}


class TemplateCreate(BaseModel):
    title: str
    target_roles: list[str] = []
    body: str


class TemplateUpdate(BaseModel):
    title: Optional[str] = None
    target_roles: Optional[list[str]] = None
    body: Optional[str] = None


class TemplatePreview(BaseModel):
    body: str
    case_id: Optional[str] = None


def _tmpl_coll(kind: str):
    coll = _TMPL_COLL.get(kind)
    if not coll:
        raise HTTPException(400, "kind must be 'offer' or 'contract'")
    return getattr(db, coll)


@router.get("/staff-onboarding/merge-fields")
async def merge_fields(user: dict = Depends(get_current_user)):
    _require_hr(user)
    return {"fields": [{"key": k, "label": lbl, "token": "{{" + k + "}}"} for k, lbl in MERGE_FIELDS]}


@router.post("/staff-onboarding/templates/preview")
async def preview_template(body: TemplatePreview, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    if body.case_id:
        c = await db.staff_onboarding_cases.find_one({"id": body.case_id, "organization_id": org})
        staff = await db.staff_members.find_one({"id": c.get("staff_id")}) if c else None
        ctx = _merge_ctx(c or {}, staff or {})
    else:
        ctx = {k: f"[{lbl}]" for k, lbl in MERGE_FIELDS}
    return {"rendered": _render(body.body, ctx)}


@router.post("/staff-onboarding/templates/reset-defaults")
async def reset_default_templates(user: dict = Depends(get_current_user)):
    """Re-seed the Pulse offer & contract templates to the latest built-in UK
    placeholder wording (only touches the built-in seed keys, leaves any custom
    or already-edited templates untouched)."""
    _require_hr(user); org = _org(user); await _ensure_seed(org, user)
    reset = 0
    for tid, name, roles in SEED_OFFER_TEMPLATES:
        r = await db.staff_offer_templates.update_one(
            {"organization_id": org, "key": tid},
            {"$set": {"body": OFFER_BODY, "title": name, "target_roles": roles,
                      "is_sample": True, "updated_at": _now()}})
        reset += r.modified_count
    for tid, name, roles in SEED_CONTRACT_TEMPLATES:
        r = await db.staff_contract_templates.update_one(
            {"organization_id": org, "key": tid},
            {"$set": {"body": CONTRACT_BODY, "title": name, "target_roles": roles,
                      "is_sample": True, "updated_at": _now()}})
        reset += r.modified_count
    return {"ok": True, "reset": reset}


@router.post("/staff-onboarding/templates/{kind}")
async def create_template(kind: str, body: TemplateCreate, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user); await _ensure_seed(org, user)
    coll = _tmpl_coll(kind)
    key = "custom_" + uuid.uuid4().hex[:8]
    doc = {
        "id": str(uuid.uuid4()), "organization_id": org, "key": key, "title": body.title,
        "target_roles": body.target_roles, "version": 1, "status": "published", "is_sample": False,
        "body": body.body, "created_by": user.get("full_name"), "created_at": _now(), "updated_at": _now(),
    }
    await coll.insert_one(dict(doc))
    return _strip(doc)


@router.put("/staff-onboarding/templates/{kind}/{template_id}")
async def update_template(kind: str, template_id: str, body: TemplateUpdate, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    coll = _tmpl_coll(kind)
    tmpl = await coll.find_one({"id": template_id, "organization_id": org})
    if not tmpl:
        raise HTTPException(404, "Template not found")
    # snapshot the current version before editing (immutable history)
    await db.staff_template_versions.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org, "template_kind": kind,
        "template_id": template_id, "key": tmpl.get("key"), "version": tmpl.get("version", 1),
        "title": tmpl.get("title"), "body": tmpl.get("body"),
        "archived_at": _now(), "archived_by": user.get("full_name"),
    })
    upd = {"updated_at": _now(), "version": (tmpl.get("version", 1) + 1),
           "is_sample": False, "last_edited_by": user.get("full_name")}
    if body.title is not None:
        upd["title"] = body.title
    if body.target_roles is not None:
        upd["target_roles"] = body.target_roles
    if body.body is not None:
        upd["body"] = body.body
    await coll.update_one({"id": template_id}, {"$set": upd})
    return _strip(await coll.find_one({"id": template_id}))


@router.get("/staff-onboarding/templates/{kind}/{template_id}/versions")
async def template_versions(kind: str, template_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    vers = await db.staff_template_versions.find(
        {"organization_id": org, "template_kind": kind, "template_id": template_id}
    ).sort("version", -1).to_list(100)
    return {"versions": [_strip(v) for v in vers]}





@router.post("/staff-onboarding/cases/duplicate-check")
async def duplicate_check(body: DupCheck, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    ors = []
    for em in filter(None, [body.personal_email, body.work_email]):
        ors.append({"email": em.lower()})
    if body.mobile:
        ors.append({"mobile": body.mobile})
    if body.legal_name:
        ors.append({"full_name": {"$regex": f"^{body.legal_name.strip()}$", "$options": "i"}})
    matches = []
    if ors:
        for m in await db.staff_members.find({"organization_id": org, "$or": ors}).to_list(20):
            matches.append({
                "staff_id": m["id"], "full_name": m.get("full_name"), "email": m.get("email"),
                "lifecycle_stage": m.get("lifecycle_stage", "employee" if m.get("active") else "candidate"),
                "active_employee": bool(m.get("active")),
            })
    return {"matches": matches, "has_active_employee": any(x["active_employee"] for x in matches)}


@router.post("/staff-onboarding/cases")
async def create_case(body: CaseCreate, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user); await _ensure_seed(org, user)
    staff_id = body.link_staff_id
    if staff_id:
        staff = await db.staff_members.find_one({"id": staff_id, "organization_id": org})
        if not staff:
            raise HTTPException(404, "Person not found")
        if staff.get("active") and not body.override_duplicate:
            raise HTTPException(409, "An active staff record already exists for this person")
        await db.staff_members.update_one({"id": staff_id}, {"$set": {"lifecycle_stage": "recruit"}})
    else:
        # duplicate guard on email
        if body.personal_email:
            existing = await db.staff_members.find_one({"organization_id": org, "email": body.personal_email.lower()})
            if existing and not body.override_duplicate:
                raise HTTPException(409, "A person with this email already exists — link instead of creating")
        full_name = " ".join(filter(None, [body.legal_first_name, body.middle_names, body.surname])) or "New Recruit"
        staff_id = str(uuid.uuid4())
        await db.staff_members.insert_one({
            "id": staff_id, "organization_id": org, "user_id": None,
            "email": (body.personal_email or "").lower(), "mobile": body.mobile,
            "full_name": full_name, "preferred_name": body.preferred_name,
            "title": body.title, "candidate_reference": body.candidate_reference,
            "primary_role": None, "site_ids": [], "active": False,
            "lifecycle_stage": "recruit", "created_at": _now(), "source": "onboarding_wizard",
        })
    case_id = str(uuid.uuid4())
    case = {
        "id": case_id, "organization_id": org, "staff_id": staff_id,
        "status": "not_started", "package": None,
        "employment_proposal": {"position": body.position, "proposed_start_date": body.proposed_start_date,
                                "preferred_name": body.preferred_name},
        "role_requirements": {}, "hr_contact": user.get("full_name"),
        "paperwork_complete": None, "offer": None, "contract": None,
        "submitted": False, "created_by": user.get("id"), "created_at": _now(), "updated_at": _now(),
    }
    await db.staff_onboarding_cases.insert_one(case)
    await _audit(org, case_id, "case_created", user, staff_id=staff_id)
    return _strip(case)


@router.get("/staff-onboarding/cases")
async def list_cases(user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    out = []
    for c in await db.staff_onboarding_cases.find({"organization_id": org}).sort("created_at", -1).to_list(500):
        staff = await db.staff_members.find_one({"id": c.get("staff_id")}) or {}
        c = _strip(c)
        c["person"] = {"full_name": staff.get("full_name"), "email": staff.get("email"),
                       "lifecycle_stage": staff.get("lifecycle_stage")}
        out.append(c)
    return {"cases": out}


@router.get("/staff-onboarding/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    cases = await db.staff_onboarding_cases.find({"organization_id": org}).to_list(1000)
    def count(pred): return sum(1 for c in cases if pred(c))
    cards = {
        "paperwork_awaiting_review": count(lambda c: c.get("status") in ("submitted", "awaiting_hr_review")),
        "ready_for_offer": count(lambda c: c.get("status") == "awaiting_offer"),
        "offers_issued": count(lambda c: (c.get("offer") or {}).get("status") == "issued"),
        "offers_accepted": count(lambda c: (c.get("offer") or {}).get("status") == "accepted"),
        "offers_declined": count(lambda c: (c.get("offer") or {}).get("status") == "declined"),
        "contracts_issued": count(lambda c: (c.get("contract") or {}).get("status") == "issued"),
        "contracts_awaiting_signature": count(lambda c: (c.get("contract") or {}).get("status") in ("issued", "employee_signed")),
        "contracts_fully_signed": count(lambda c: (c.get("contract") or {}).get("status") == "fully_signed"),
        "ready_to_activate": count(lambda c: c.get("status") == "ready_to_activate"),
        "total_cases": len(cases),
    }
    return {"cards": cards}


@router.get("/staff-onboarding/cases/{case_id}")
async def get_case(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    staff = await db.staff_members.find_one({"id": c.get("staff_id")}) or {}
    forms = await db.staff_form_submissions.find({"onboarding_case_id": case_id}).to_list(50)
    reveal = user.get("role") in ("owner", "master_admin")  # payroll/DBS role gating (Phase 2 expands)
    docs = await db.staff_onboarding_documents.find({"onboarding_case_id": case_id, "is_deleted": {"$ne": True}}).to_list(100)
    acks = await db.staff_policy_acknowledgements.find({"onboarding_case_id": case_id}).to_list(50)
    agr = await db.staff_agreement_assignments.find({"onboarding_case_id": case_id}).to_list(50)
    invite = await db.staff_onboarding_invites.find_one({"onboarding_case_id": case_id})
    return {
        "case": _strip(c), "person": _strip(staff),
        "forms": _mask_forms([_strip(f) for f in forms], reveal), "sensitive_masked": not reveal,
        "documents": [_strip(d) for d in docs],
        "policy_acknowledgements": [_strip(a) for a in acks], "agreements": [_strip(a) for a in agr],
        "invite": {"status": invite.get("status"), "expires_at": invite.get("expires_at")} if invite else None,
    }


@router.patch("/staff-onboarding/cases/{case_id}")
async def patch_case(case_id: str, body: CasePatch, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    upd = {"updated_at": _now()}
    if body.employment_proposal is not None:
        upd["employment_proposal"] = {**(c.get("employment_proposal") or {}), **body.employment_proposal}
    if body.role_requirements is not None:
        upd["role_requirements"] = {**(c.get("role_requirements") or {}), **body.role_requirements}
    if body.package is not None:
        upd["package"] = body.package
    if body.hr_contact is not None:
        upd["hr_contact"] = body.hr_contact
    await db.staff_onboarding_cases.update_one({"id": case_id}, {"$set": upd})
    await _audit(org, case_id, "case_updated", user)
    return _strip(await db.staff_onboarding_cases.find_one({"id": case_id}))


@router.post("/staff-onboarding/cases/{case_id}/invite")
async def create_invite(case_id: str, body: InviteBody, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    token = uuid.uuid4().hex + uuid.uuid4().hex
    inv = {
        "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case_id,
        "staff_id": c["staff_id"], "token": token, "status": "sent",
        "mfa_required": body.mfa_required, "message": body.message, "deadline": body.deadline,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=body.expiry_days)).isoformat(),
        "created_by": user.get("id"), "created_at": _now(),
    }
    await db.staff_onboarding_invites.delete_many({"onboarding_case_id": case_id})
    await db.staff_onboarding_invites.insert_one(inv)
    await db.staff_onboarding_cases.update_one({"id": case_id}, {"$set": {"status": "in_progress", "updated_at": _now()}})
    await _audit(org, case_id, "invite_sent", user)
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    portal_url = f"{FRONTEND_URL}/new-starter/{token}"
    if staff.get("email"):
        await _notify(org, case_id, "recruit", c["staff_id"], "invite_sent",
                      "Your Pulse Fitness onboarding portal is ready.",
                      email_to=staff["email"], email_subject="Welcome to Pulse Fitness — start your onboarding",
                      email_html=_email_shell(
                          f"Hello {staff.get('preferred_name') or staff.get('full_name') or 'there'},",
                          ["Welcome to Pulse Fitness. Your secure New Starter Portal is ready.",
                           "Please set a password and complete your onboarding forms, documents and policies.",
                           f"Your invitation expires on {inv['expires_at'][:10]}."],
                          cta_url=portal_url, cta_label="Open my portal"))
    return {"invite_token": token, "portal_path": f"/new-starter/{token}",
            "recruit_email": staff.get("email"), "expires_at": inv["expires_at"]}


PAPERWORK_CHECKS = ["personal_details", "emergency_contact", "payroll", "identity_documents",
                    "right_to_work", "policies", "agreements"]


async def _paperwork_state(case: dict) -> dict:
    cid = case["id"]
    forms = {f["form_key"]: f for f in await db.staff_form_submissions.find({"onboarding_case_id": cid}).to_list(50)}
    docs = await db.staff_onboarding_documents.count_documents({"onboarding_case_id": cid, "is_deleted": {"$ne": True}})
    pol_req = await db.staff_policy_versions.count_documents({"organization_id": case["organization_id"], "acknowledgement_required": True})
    pol_done = await db.staff_policy_acknowledgements.count_documents({"onboarding_case_id": cid})
    agr = await db.staff_agreement_assignments.find({"onboarding_case_id": cid}).to_list(50)
    rtw = await db.staff_right_to_work_checks.find_one({"onboarding_case_id": cid})
    return {
        "personal_details": bool(forms.get("new_starter")),
        "emergency_contact": bool((forms.get("new_starter", {}).get("data") or {}).get("emergency_contact_name")),
        "payroll": bool(forms.get("new_starter") and (forms.get("new_starter", {}).get("data") or {}).get("bank_account")),
        "identity_documents": docs > 0,
        "right_to_work": bool(rtw and rtw.get("result") in ("verified", "time_limited")),
        "policies": pol_req == 0 or pol_done >= pol_req,
        "agreements": all(a.get("status") == "signed" for a in agr) if agr else True,
    }


@router.get("/staff-onboarding/cases/{case_id}/paperwork-state")
async def paperwork_state(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    st = await _paperwork_state(c)
    return {"checks": st, "all_complete": all(st.values())}


@router.post("/staff-onboarding/cases/{case_id}/paperwork-complete")
async def paperwork_complete(case_id: str, body: ApproveBody, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    st = await _paperwork_state(c)
    if not all(st.values()):
        raise HTTPException(400, {"message": "Mandatory paperwork incomplete", "checks": st})
    pw = {"completed_by": user.get("full_name"), "completed_at": _now(), "comments": body.comment}
    await db.staff_onboarding_cases.update_one({"id": case_id},
        {"$set": {"paperwork_complete": pw, "status": "awaiting_offer", "updated_at": _now()}})
    await _audit(org, case_id, "paperwork_complete", user, reason=body.comment)
    return {"status": "awaiting_offer", "paperwork_complete": pw}


# ───────────────────────── offer ─────────────────────────
@router.post("/staff-onboarding/cases/{case_id}/offer")
async def create_offer(case_id: str, body: OfferCreate, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    if not c.get("paperwork_complete"):
        raise HTTPException(400, "Paperwork must be marked complete before creating an offer")
    tmpl = await db.staff_offer_templates.find_one({"id": body.template_id, "organization_id": org})
    if not tmpl:
        raise HTTPException(404, "Offer template not found")
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    ctx = {**_merge_ctx(c, staff), **(body.overrides or {})}
    rendered = _render(tmpl["body"], ctx)
    conditional = bool(body.conditions)
    offer = {
        "version": 1, "template_id": body.template_id, "template_title": tmpl["title"],
        "status": "draft", "rendered": rendered, "merge_context": ctx,
        "conditions": body.conditions, "conditional": conditional,
        "offer_expiry_date": body.offer_expiry_date, "is_sample": tmpl.get("is_sample", True),
        "approvals": [], "history": [{"status": "draft", "at": _now(), "by": user.get("full_name")}],
        "created_at": _now(),
    }
    await db.staff_onboarding_cases.update_one({"id": case_id}, {"$set": {"offer": offer, "updated_at": _now()}})
    await _audit(org, case_id, "offer_created", user, version=1)
    return offer


@router.post("/staff-onboarding/cases/{case_id}/offer/approve")
async def approve_offer(case_id: str, body: ApproveBody, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c or not c.get("offer"):
        raise HTTPException(404, "Offer not found")
    offer = c["offer"]
    offer["approvals"].append({"by": user.get("full_name"), "role": user.get("role"), "at": _now(), "comment": body.comment})
    offer["status"] = "approved"
    offer["history"].append({"status": "approved", "at": _now(), "by": user.get("full_name")})
    await db.staff_onboarding_cases.update_one({"id": case_id}, {"$set": {"offer": offer, "updated_at": _now()}})
    await _audit(org, case_id, "offer_approved", user)
    return offer


@router.post("/staff-onboarding/cases/{case_id}/offer/issue")
async def issue_offer(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c or not c.get("offer"):
        raise HTTPException(404, "Offer not found")
    offer = c["offer"]
    if offer["status"] not in ("approved", "draft"):
        raise HTTPException(400, "Offer must be approved before issue")
    offer["status"] = "issued"
    offer["issued_at"] = _now()
    offer["doc_hash"] = _doc_hash(offer["rendered"])
    offer["history"].append({"status": "issued", "at": _now(), "by": user.get("full_name")})
    await db.staff_onboarding_cases.update_one({"id": case_id},
        {"$set": {"offer": offer, "status": "offer_issued", "updated_at": _now()}})
    await _audit(org, case_id, "offer_issued", user)
    await db.staff_members.update_one({"id": c["staff_id"]}, {"$set": {"lifecycle_stage": "offer_issued"}})
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    if staff.get("email"):
        inv = await db.staff_onboarding_invites.find_one({"onboarding_case_id": case_id})
        url = f"{FRONTEND_URL}/new-starter/{inv['token']}" if inv else FRONTEND_URL
        await _notify(org, case_id, "recruit", c["staff_id"], "offer_issued",
                      "Your offer letter is ready to review in your portal.",
                      email_to=staff["email"], email_subject="Your Pulse Fitness offer is ready to review",
                      email_html=_email_shell(f"Hello {staff.get('preferred_name') or staff.get('full_name')},",
                          ["Good news — your offer letter is now available in your Pulse Fitness portal.",
                           "Please sign in to review it and accept or decline."],
                          cta_url=url, cta_label="Review my offer"))
    return offer


# ───────────────────────── contract ─────────────────────────
def _offer_terms(offer: dict) -> dict:
    return {k: (offer.get("merge_context") or {}).get(k) for k in CONSISTENCY_FIELDS}


@router.post("/staff-onboarding/cases/{case_id}/contract")
async def create_contract(case_id: str, body: ContractCreate, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    offer = c.get("offer") or {}
    if offer.get("status") != "accepted" and not body.override_reason:
        raise HTTPException(400, "Offer must be accepted before creating a contract (or provide an override reason)")
    tmpl = await db.staff_contract_templates.find_one({"id": body.template_id, "organization_id": org})
    if not tmpl:
        raise HTTPException(404, "Contract template not found")
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    ctx = _merge_ctx(c, staff)
    # consistency check vs accepted offer
    offer_terms = _offer_terms(offer) if offer else {}
    diffs = []
    for f in CONSISTENCY_FIELDS:
        ov, cv = offer_terms.get(f), ctx.get(f)
        if offer and str(ov or "") != str(cv or ""):
            diffs.append({"field": f, "offer_value": ov, "contract_value": cv})
    rendered = _render(tmpl["body"], ctx)
    contract = {
        "version": 1, "template_id": body.template_id, "template_title": tmpl["title"],
        "status": "draft", "rendered": rendered, "merge_context": ctx,
        "schedules": body.schedules, "is_sample": tmpl.get("is_sample", True),
        "differences": diffs, "difference_ack": body.difference_ack,
        "override_reason": body.override_reason, "approvals": [],
        "signatures": [], "history": [{"status": "draft", "at": _now(), "by": user.get("full_name")}],
        "created_at": _now(),
    }
    await db.staff_onboarding_cases.update_one({"id": case_id}, {"$set": {"contract": contract, "updated_at": _now()}})
    await _audit(org, case_id, "contract_created", user, differences=len(diffs))
    return contract


@router.get("/staff-onboarding/cases/{case_id}/consistency")
async def consistency(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c or not c.get("contract"):
        raise HTTPException(404, "Contract not found")
    return {"differences": c["contract"].get("differences", [])}


@router.post("/staff-onboarding/cases/{case_id}/contract/approve")
async def approve_contract(case_id: str, body: ApproveBody, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c or not c.get("contract"):
        raise HTTPException(404, "Contract not found")
    con = c["contract"]
    con["approvals"].append({"by": user.get("full_name"), "role": user.get("role"), "at": _now(), "comment": body.comment})
    con["status"] = "approved"
    con["history"].append({"status": "approved", "at": _now(), "by": user.get("full_name")})
    await db.staff_onboarding_cases.update_one({"id": case_id}, {"$set": {"contract": con, "updated_at": _now()}})
    await _audit(org, case_id, "contract_approved", user)
    return con


@router.post("/staff-onboarding/cases/{case_id}/contract/issue")
async def issue_contract(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c or not c.get("contract"):
        raise HTTPException(404, "Contract not found")
    con = c["contract"]
    if con["status"] not in ("approved", "draft"):
        raise HTTPException(400, "Contract must be approved before issue")
    con["status"] = "issued"
    con["issued_at"] = _now()
    con["history"].append({"status": "issued", "at": _now(), "by": user.get("full_name")})
    await db.staff_onboarding_cases.update_one({"id": case_id},
        {"$set": {"contract": con, "status": "contract_issued", "updated_at": _now()}})
    await db.staff_members.update_one({"id": c["staff_id"]}, {"$set": {"lifecycle_stage": "contract_issued"}})
    await _audit(org, case_id, "contract_issued", user)
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    if staff.get("email"):
        inv = await db.staff_onboarding_invites.find_one({"onboarding_case_id": case_id})
        url = f"{FRONTEND_URL}/new-starter/{inv['token']}" if inv else FRONTEND_URL
        await _notify(org, case_id, "recruit", c["staff_id"], "contract_issued",
                      "Your employment contract is ready to sign in your portal.",
                      email_to=staff["email"], email_subject="Your Pulse Fitness contract is ready to sign",
                      email_html=_email_shell(f"Hello {staff.get('preferred_name') or staff.get('full_name')},",
                          ["Your employment contract (and any schedules) is now available in your portal.",
                           "Please review the full document and sign electronically."],
                          cta_url=url, cta_label="Review & sign my contract"))
    return con


async def _sign_and_cert(org, case, doc_kind, signer_name, signer_role, method, image, req: Request, rendered):
    ev = {
        "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case["id"],
        "document_kind": doc_kind, "signer_name": signer_name, "signer_role": signer_role,
        "method": method, "signature_image": image,
        "signed_at": _now(), "ip": (req.client.host if req and req.client else None),
        "user_agent": (req.headers.get("user-agent") if req else None),
        "document_hash": _doc_hash(rendered),
        "acceptance_statement": "I have read and agree to this document.",
    }
    await db.staff_electronic_signatures.insert_one(dict(ev))
    cert = {
        "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case["id"],
        "document_kind": doc_kind, "signatures": [ev["id"]], "document_hash": ev["document_hash"],
        "created_at": _now(),
    }
    await db.staff_signature_certificates.insert_one(dict(cert))
    return _strip(ev), _strip(cert)


@router.post("/staff-onboarding/cases/{case_id}/contract/countersign")
async def countersign_contract(case_id: str, body: SignBody, request: Request, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c or not c.get("contract"):
        raise HTTPException(404, "Contract not found")
    con = c["contract"]
    if con["status"] not in ("employee_signed", "awaiting_employer_countersignature", "issued"):
        raise HTTPException(400, "Employee must sign before employer countersignature")
    ev, cert = await _sign_and_cert(org, c, "contract", body.signature_name, "employer",
                                    body.signature_method, body.signature_image, request, con["rendered"])
    con.setdefault("signatures", []).append({"party": "employer", **ev})
    con["status"] = "fully_signed"
    con["locked"] = True
    con["fully_signed_at"] = _now()
    con["certificate_id"] = cert["id"]
    con["history"].append({"status": "fully_signed", "at": _now(), "by": user.get("full_name")})
    await db.staff_onboarding_cases.update_one({"id": case_id},
        {"$set": {"contract": con, "status": "ready_to_activate", "updated_at": _now()}})
    await _audit(org, case_id, "contract_fully_signed", user)
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    if staff.get("email"):
        await _notify(org, case_id, "recruit", c["staff_id"], "contract_fully_signed",
                      "Your contract is fully signed and stored in your portal.",
                      email_to=staff["email"], email_subject="Your Pulse Fitness contract is complete",
                      email_html=_email_shell(f"Hello {staff.get('preferred_name') or staff.get('full_name')},",
                          ["Your employment contract has been countersigned and is now fully signed.",
                           "A copy is saved securely in your portal for your records."]))
    return con


# ───────────────────────── activation ─────────────────────────
@router.get("/staff-onboarding/cases/{case_id}/activation-state")
async def activation_state(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    offer = c.get("offer") or {}; con = c.get("contract") or {}
    rtw = await db.staff_right_to_work_checks.find_one({"onboarding_case_id": case_id})
    checks = {
        "offer_accepted": offer.get("status") == "accepted",
        "contract_fully_signed": con.get("status") == "fully_signed",
        "right_to_work_verified": bool(rtw and rtw.get("result") in ("verified", "time_limited")),
        "paperwork_complete": bool(c.get("paperwork_complete")),
    }
    if (c.get("role_requirements") or {}).get("dbs_required"):
        dbs = await db.staff_dbs_checks.find_one({"onboarding_case_id": case_id})
        checks["dbs_cleared"] = bool(dbs and dbs.get("status") == "clear")
    return {"checks": checks, "ready": all(checks.values())}


@router.post("/staff-onboarding/cases/{case_id}/activate")
async def activate(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    st = (await activation_state(case_id, user))["checks"]
    if not all(st.values()):
        raise HTTPException(400, {"message": "Activation prerequisites not met", "checks": st})
    staff = await db.staff_members.find_one({"id": c["staff_id"]})
    ep = c.get("employment_proposal", {})
    # promote recruit user → staff (reuse same account, no new user)
    if staff.get("user_id"):
        await db.users.update_one({"id": staff["user_id"]}, {"$set": {"role": "staff", "onboarding_active": True}})
    await db.staff_members.update_one({"id": c["staff_id"]}, {"$set": {
        "active": True, "lifecycle_stage": "employee", "primary_role": ep.get("job_title") or "staff",
        "contract_type": ep.get("employment_type"), "activated_at": _now(),
        "department": ep.get("department") or "",
    }})
    # pre-start tasks (light)
    tasks = [("HR", "Confirm start date"), ("Manager", "Prepare induction & first-day plan"),
             ("IT", "Create email & PulseFitness.ai access"), ("Stores", "Prepare uniform / PPE"),
             ("Training", "Assign company induction & H&S")]
    for owner, title in tasks:
        await db.staff_onboarding_tasks.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case_id,
            "staff_id": c["staff_id"], "owner_group": owner, "title": title,
            "status": "open", "created_at": _now()})
    await db.staff_onboarding_cases.update_one({"id": case_id},
        {"$set": {"status": "complete", "activated_at": _now(), "updated_at": _now()}})
    await _audit(org, case_id, "employee_activated", user)
    staff2 = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    if staff2.get("email"):
        inv = await db.staff_onboarding_invites.find_one({"onboarding_case_id": case_id})
        url = f"{FRONTEND_URL}/new-starter/{inv['token']}" if inv else FRONTEND_URL
        # Attach the Staff Portal handbook PDF with the welcome/login email.
        handbook_attachment = None
        try:
            from routes.staff_portal import _build_handbook_pdf
            hb = _build_handbook_pdf(staff2.get("preferred_name") or staff2.get("full_name"))
            handbook_attachment = [{"filename": "pulse-staff-portal-handbook.pdf",
                                    "content": base64.b64encode(hb).decode("ascii")}]
        except Exception:
            handbook_attachment = None
        await _notify(org, case_id, "recruit", c["staff_id"], "activated",
                      "Welcome to the team! Your Staff Portal is now active.",
                      email_to=staff2["email"], email_subject="Welcome to Pulse Fitness — your first day",
                      email_html=_email_shell(f"Welcome, {staff2.get('preferred_name') or staff2.get('full_name')}!",
                          ["Your onboarding is complete and your account is now your Pulse Fitness Staff Portal.",
                           "All your completed documents, offer letter and contract remain available there.",
                           "We've attached your Staff Portal Handbook (PDF) — a quick guide to logging in and using the portal.",
                           f"Your start date: {ep.get('proposed_start_date') or 'to be confirmed'}."],
                          cta_url=url, cta_label="Open my Staff Portal"),
                      attachments=handbook_attachment)
    # Email the audit-ready Onboarding Pack PDF to HR/payroll on activation.
    try:
        await _email_pack_on_activation(org, c, staff2, user)
    except Exception:
        logger.exception("onboarding pack email failed (non-fatal)")
    return {"status": "complete", "staff_id": c["staff_id"]}


async def _email_pack_on_activation(org: str, case: dict, staff: dict, user: dict) -> None:
    settings = await db.staff_onboarding_settings.find_one({"organization_id": org}) or {}
    if settings.get("email_pack_on_activation") is False:
        return
    recipients = list(settings.get("pack_recipient_emails") or [])
    if user.get("email"):
        recipients.append(user["email"])
    recipients = list(dict.fromkeys([r for r in recipients if r and "@" in r]))
    if not recipients:
        return
    from utils.onboarding_pdf import build_pack_pdf
    data = await _gather_pack_data(case)
    pdf = build_pack_pdf(case, staff, data)
    attachment = [{"filename": f"onboarding-pack-{staff.get('full_name', 'employee').replace(' ', '-')}.pdf",
                   "content": base64.b64encode(pdf).decode("ascii")}]
    name = staff.get("full_name") or "New employee"
    ep = case.get("employment_proposal") or {}
    html = _email_shell(
        f"Onboarding complete — {name}",
        [f"{name} has been activated as an employee. The audit-ready Onboarding Pack is attached (PDF).",
         f"Role: {ep.get('job_title') or ep.get('position') or '—'}  ·  Start date: {ep.get('proposed_start_date') or 'to be confirmed'}.",
         "It bundles the completed new-starter form, ID/RTW/DBS summary, policy acknowledgements, signed agreements, offer letter and contract."])
    from utils.email import send_email
    for rcpt in recipients:
        await send_email(rcpt, f"Onboarding pack — {name}", html, attachments=attachment,
                         organization_id=org, kind="staff_onboarding")
    await _audit(org, case["id"], "onboarding_pack_emailed", user, recipients=len(recipients))


@router.get("/staff-onboarding/cases/{case_id}/audit")
async def case_audit(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    evs = await db.staff_onboarding_audit_events.find(
        {"organization_id": org, "onboarding_case_id": case_id}).sort("at", -1).to_list(500)
    return {"events": [_strip(e) for e in evs]}


# ═════════════════════════ RECRUIT PORTAL ═════════════════════════
async def _recruit_case(user: dict) -> dict:
    staff = await db.staff_members.find_one({"user_id": user.get("id")})
    if not staff:
        raise HTTPException(404, "No onboarding record for this account")
    case = await db.staff_onboarding_cases.find_one({"staff_id": staff["id"]})
    if not case:
        raise HTTPException(404, "No onboarding case")
    return case, staff


@router.get("/new-starter/invite/{token}")
async def invite_status(token: str):
    """Public: lets the portal show 'Create a password' (first time) vs
    'Welcome back, log in' (returning) without exposing sensitive data."""
    inv = await db.staff_onboarding_invites.find_one({"token": token})
    if not inv:
        return {"found": False}
    expired = bool(inv.get("expires_at") and inv["expires_at"] < _now())
    staff = await db.staff_members.find_one({"id": inv["staff_id"]}) or {}
    user = await db.users.find_one({"id": staff.get("user_id")}) if staff.get("user_id") else None
    has_password = bool(user and user.get("password"))
    return {"found": True, "expired": expired,
            "accepted": inv.get("status") == "accepted" and has_password,
            "full_name": staff.get("full_name"),
            "activated": bool(staff.get("active"))}


@router.post("/new-starter/login")
async def recruit_login(body: AcceptInvite, response: Response):
    """Returning recruit logs in on the invite URL by verifying their password."""
    inv = await db.staff_onboarding_invites.find_one({"token": body.token})
    if not inv:
        raise HTTPException(404, "Invalid invitation link")
    if inv.get("expires_at") and inv["expires_at"] < _now():
        raise HTTPException(410, "This invitation link has expired — please ask your HR contact to resend it.")
    staff = await db.staff_members.find_one({"id": inv["staff_id"]}) or {}
    uid = staff.get("user_id")
    user = await db.users.find_one({"id": uid}) if uid else None
    if not user or not user.get("password"):
        raise HTTPException(400, "Please set up your portal password first.")
    if not verify_password(body.password or "", user["password"]):
        raise HTTPException(401, "Incorrect password — please try again.")
    token = create_token(uid, expires_hours=24)
    return {"token": token, "user": {"id": uid, "full_name": staff.get("full_name"), "role": "recruit"}}


@router.post("/new-starter/accept-invite")
async def accept_invite(body: AcceptInvite, response: Response):
    inv = await db.staff_onboarding_invites.find_one({"token": body.token})
    if not inv:
        raise HTTPException(404, "Invalid invitation")
    if inv.get("expires_at") and inv["expires_at"] < _now():
        raise HTTPException(410, "Invitation expired")
    if len(body.password or "") < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    staff = await db.staff_members.find_one({"id": inv["staff_id"]})
    org = inv["organization_id"]
    uid = staff.get("user_id")
    existing = await db.users.find_one({"id": uid}) if uid else None
    # Portal already set up → don't reset the password; ask them to log in.
    if inv.get("status") == "accepted" and existing and existing.get("password"):
        raise HTTPException(409, "You've already set up your portal — please log in with your password.")
    if not uid:
        uid = str(uuid.uuid4())
        await db.users.insert_one({
            "id": uid, "organization_id": org, "email": (staff.get("email") or f"recruit+{uid}@pulse.local").lower(),
            "full_name": staff.get("full_name"), "role": "recruit", "account_type": "recruit",
            "password": hash_password(body.password), "allowed_site_ids": [], "created_at": _now(),
            "is_recruit_portal": True,
        })
        await db.staff_members.update_one({"id": staff["id"]}, {"$set": {"user_id": uid}})
    else:
        await db.users.update_one({"id": uid}, {"$set": {"password": hash_password(body.password)}})
    await db.staff_onboarding_invites.update_one({"id": inv["id"]}, {"$set": {"status": "accepted", "accepted_at": _now()}})
    await _audit(org, inv["onboarding_case_id"], "invite_accepted",
                 {"id": uid, "full_name": staff.get("full_name"), "role": "recruit"})
    token = create_token(uid, expires_hours=24)
    return {"token": token, "user": {"id": uid, "full_name": staff.get("full_name"), "role": "recruit"}}


# ───────────── staff portal login + password reset (email + password) ─────────────
class StaffLoginBody(BaseModel):
    email: str
    password: str


class ForgotBody(BaseModel):
    email: str


class ResetBody(BaseModel):
    token: str
    password: str


async def _resolve_staff_for_user(user: dict) -> dict | None:
    """Find the employee's staff_members record for a signed-in platform user.

    A person is "staff" if a staff_members row is linked to them by user_id OR by
    email (case-insensitive), scoped to their org. Historically /staff-login only
    matched user_id, so employees whose record was linked by email (or had a null/
    stale user_id) were wrongly told "This account does not have a staff portal".
    When we resolve by email we self-heal the user_id link so it's fast next time.
    """
    staff = await db.staff_members.find_one({"user_id": user["id"]})
    if staff:
        return staff
    email = (user.get("email") or "").strip()
    if not email:
        return None
    q = {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}
    if user.get("organization_id"):
        q["organization_id"] = user["organization_id"]
    staff = await db.staff_members.find_one(q)
    if staff and staff.get("user_id") != user["id"]:
        await db.staff_members.update_one({"id": staff["id"]}, {"$set": {"user_id": user["id"]}})
    return staff


@router.post("/new-starter/staff-login")
async def staff_login(body: StaffLoginBody):
    """Activated employees (and recruits) log in with email + password at /staff-login."""
    email = (body.email or "").strip().lower()
    user = await db.users.find_one({"email": email}) if email else None
    if not user or not user.get("password") or not verify_password(body.password or "", user["password"]):
        raise HTTPException(401, "Incorrect email or password.")
    staff = await _resolve_staff_for_user(user)
    if not staff:
        raise HTTPException(403, "This account does not have a staff portal.")
    token = create_token(user["id"], expires_hours=24)
    return {"token": token, "user": {"id": user["id"], "full_name": staff.get("full_name"),
                                     "role": user.get("role"), "activated": bool(staff.get("active"))}}


@router.post("/new-starter/forgot-password")
async def forgot_password(body: ForgotBody):
    """Emails a reset link. Always returns a generic success (no account enumeration)."""
    email = (body.email or "").strip().lower()
    user = await db.users.find_one({"email": email}) if email else None
    if user and user.get("password"):
        staff = await _resolve_staff_for_user(user)
        if staff:
            reset_token = secrets.token_urlsafe(32)
            await db.staff_password_resets.insert_one({
                "id": str(uuid.uuid4()), "user_id": user["id"], "token": reset_token,
                "organization_id": user.get("organization_id"), "used": False,
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "created_at": _now()})
            link = f"{FRONTEND_URL}/staff-reset/{reset_token}"
            html = _email_shell("Reset your Pulse Fitness portal password",
                                [f"Hi {staff.get('full_name', 'there')},",
                                 "We received a request to reset your staff portal password. This link expires in 1 hour.",
                                 "If you didn't request this, you can safely ignore this email."],
                                cta_url=link, cta_label="Reset my password")
            try:
                await send_email(user["email"], "Reset your Pulse Fitness portal password", html,
                                 organization_id=user.get("organization_id"), kind="staff_onboarding")
            except Exception:
                logger.exception("password reset email failed")
    return {"ok": True, "message": "If an account exists for that email, a reset link has been sent."}


@router.post("/new-starter/reset-password")
async def reset_password(body: ResetBody):
    if len(body.password or "") < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    rec = await db.staff_password_resets.find_one({"token": body.token})
    if not rec or rec.get("used"):
        raise HTTPException(400, "This reset link is invalid or has already been used.")
    if rec.get("expires_at") and rec["expires_at"] < _now():
        raise HTTPException(410, "This reset link has expired — please request a new one.")
    await db.users.update_one({"id": rec["user_id"]}, {"$set": {"password": hash_password(body.password)}})
    await db.staff_password_resets.update_one({"id": rec["id"]}, {"$set": {"used": True, "used_at": _now()}})
    return {"ok": True, "message": "Your password has been reset — you can now log in."}



PROGRESS_STEPS = ["forms", "documents", "verification", "policies", "agreements", "offer", "contract", "ready_to_start"]


@router.get("/new-starter/me")
async def recruit_me(user: dict = Depends(get_current_user_portal)):
    case, staff = await _recruit_case(user)
    org = case["organization_id"]; cid = case["id"]
    activated = bool(staff.get("active"))
    forms = {f["form_key"]: _strip(f) for f in await db.staff_form_submissions.find({"onboarding_case_id": cid}).to_list(50)}
    docs = [_strip(d) for d in await db.staff_onboarding_documents.find({"onboarding_case_id": cid, "is_deleted": {"$ne": True}}).to_list(100)]
    policies = [_strip(p) for p in await db.staff_policy_versions.find({"organization_id": org}).to_list(50)]
    acks = {a["policy_key"]: _strip(a) for a in await db.staff_policy_acknowledgements.find({"onboarding_case_id": cid}).to_list(50)}
    agreements = [_strip(a) for a in await db.staff_agreement_versions.find({"organization_id": org}).to_list(50)]
    agr_state = {a["agreement_key"]: _strip(a) for a in await db.staff_agreement_assignments.find({"onboarding_case_id": cid}).to_list(50)}
    offer = case.get("offer") if (case.get("offer") or {}).get("status") in ("issued", "accepted", "declined") else None
    con = case.get("contract") if (case.get("contract") or {}).get("status") in ("issued", "employee_signed", "fully_signed") else None
    pol_req = [p for p in policies if p.get("acknowledgement_required")]
    progress = {
        "forms": "submitted" if case.get("submitted") else ("in_progress" if forms else "not_started"),
        "documents": "submitted" if docs else "not_started",
        "verification": case.get("status") in ("awaiting_offer", "offer_issued", "contract_issued", "ready_to_activate", "complete") and "verified" or "in_progress",
        "policies": "submitted" if pol_req and len(acks) >= len(pol_req) else ("in_progress" if acks else "not_started"),
        "agreements": "submitted" if agreements and all(agr_state.get(a["key"], {}).get("status") == "signed" for a in agreements) else ("in_progress" if agr_state else "not_started"),
        "offer": (case.get("offer") or {}).get("status", "not_started"),
        "contract": (case.get("contract") or {}).get("status", "not_started"),
        "ready_to_start": "complete" if activated else "not_started",
    }
    return {
        "portal_name": "Pulse Fitness Staff Portal" if activated else "Pulse Fitness New Starter Portal",
        "activated": activated, "status": case.get("status"), "submitted": bool(case.get("submitted")),
        "person": {"full_name": staff.get("full_name"), "email": staff.get("email"),
                   "photo_url": staff.get("photo_url")},
        "employment": case.get("employment_proposal", {}), "progress": progress, "steps": PROGRESS_STEPS,
        "forms": forms, "documents": docs, "policies": policies, "acknowledgements": acks,
        "agreements": agreements, "agreement_state": agr_state,
        "offer": _strip(offer) if offer else None, "contract": _strip(con) if con else None,
    }


@router.put("/new-starter/forms")
async def save_form(body: FormSave, user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    existing = await db.staff_form_submissions.find_one({"onboarding_case_id": case["id"], "form_key": body.form_key})
    payload = {"onboarding_case_id": case["id"], "organization_id": case["organization_id"],
               "staff_id": staff["id"], "form_key": body.form_key, "data": body.data, "updated_at": _now()}
    if existing:
        await db.staff_form_submissions.update_one({"id": existing["id"]}, {"$set": payload})
    else:
        payload["id"] = str(uuid.uuid4()); payload["created_at"] = _now()
        await db.staff_form_submissions.insert_one(payload)
    await _audit(case["organization_id"], case["id"], "form_submitted", user, document=body.form_key)
    return {"ok": True}


@router.post("/new-starter/policies/{policy_key}/acknowledge")
async def ack_policy(policy_key: str, body: Ack, request: Request, user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    pol = await db.staff_policy_versions.find_one({"organization_id": case["organization_id"], "key": policy_key})
    if not pol:
        raise HTTPException(404, "Policy not found")
    await db.staff_policy_acknowledgements.delete_many({"onboarding_case_id": case["id"], "policy_key": policy_key})
    await db.staff_policy_acknowledgements.insert_one({
        "id": str(uuid.uuid4()), "organization_id": case["organization_id"], "onboarding_case_id": case["id"],
        "staff_id": staff["id"], "policy_key": policy_key, "policy_version": pol.get("version"),
        "signature_name": body.signature_name, "acknowledged_at": _now(),
        "ip": request.client.host if request.client else None})
    await _audit(case["organization_id"], case["id"], "policy_acknowledged", user, document=policy_key)
    return {"ok": True}


@router.post("/new-starter/agreements/{agreement_key}/sign")
async def sign_agreement(agreement_key: str, body: SignBody, request: Request, user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    agr = await db.staff_agreement_versions.find_one({"organization_id": case["organization_id"], "key": agreement_key})
    if not agr:
        raise HTTPException(404, "Agreement not found")
    if not body.acknowledge:
        raise HTTPException(400, "You must confirm acceptance")
    ev, cert = await _sign_and_cert(case["organization_id"], case, f"agreement:{agreement_key}",
                                    body.signature_name, "employee", body.signature_method,
                                    body.signature_image, request, agr.get("body", ""))
    await db.staff_agreement_assignments.delete_many({"onboarding_case_id": case["id"], "agreement_key": agreement_key})
    await db.staff_agreement_assignments.insert_one({
        "id": str(uuid.uuid4()), "organization_id": case["organization_id"], "onboarding_case_id": case["id"],
        "staff_id": staff["id"], "agreement_key": agreement_key, "agreement_version": agr.get("version"),
        "status": "signed", "signature_id": ev["id"], "certificate_id": cert["id"],
        "document_hash": ev["document_hash"], "signed_at": _now()})
    await _audit(case["organization_id"], case["id"], "agreement_signed", user, document=agreement_key)
    return {"ok": True, "certificate_id": cert["id"]}


@router.post("/new-starter/submit")
async def submit_pack(user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    await db.staff_onboarding_cases.update_one({"id": case["id"]},
        {"$set": {"submitted": True, "submitted_at": _now(), "status": "awaiting_hr_review", "updated_at": _now()}})
    await db.staff_members.update_one({"id": staff["id"]}, {"$set": {"lifecycle_stage": "onboarding"}})
    await _audit(case["organization_id"], case["id"], "pack_submitted", user)
    return {"ok": True, "status": "awaiting_hr_review"}


@router.post("/new-starter/offer/respond")
async def offer_respond(body: OfferRespond, request: Request, user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    offer = case.get("offer") or {}
    if offer.get("status") not in ("issued",):
        raise HTTPException(400, "No offer awaiting response")
    if body.action == "decline":
        offer["status"] = "declined"; offer["declined_reason"] = body.reason
        offer["history"].append({"status": "declined", "at": _now()})
        await db.staff_onboarding_cases.update_one({"id": case["id"]}, {"$set": {"offer": offer, "status": "offer_declined", "updated_at": _now()}})
        await _audit(case["organization_id"], case["id"], "offer_declined", user, reason=body.reason)
        return {"status": "declined"}
    if body.action == "clarify":
        await db.staff_onboarding_messages.insert_one({
            "id": str(uuid.uuid4()), "organization_id": case["organization_id"], "onboarding_case_id": case["id"],
            "from": "recruit", "message": body.message, "at": _now()})
        await _audit(case["organization_id"], case["id"], "clarification_requested", user)
        return {"status": "clarification_requested"}
    # accept
    if not body.signature_name:
        raise HTTPException(400, "Signature name required to accept")
    ev, cert = await _sign_and_cert(case["organization_id"], case, "offer", body.signature_name,
                                    "employee", "typed", None, request, offer["rendered"])
    offer["status"] = "accepted"; offer["locked"] = True
    offer["accepted_at"] = _now(); offer["acceptance"] = {"signature": ev, "intended_start_date": body.intended_start_date}
    offer["history"].append({"status": "accepted", "at": _now()})
    await db.staff_onboarding_cases.update_one({"id": case["id"]},
        {"$set": {"offer": offer, "status": "offer_accepted", "updated_at": _now()}})
    await db.staff_members.update_one({"id": staff["id"]}, {"$set": {"lifecycle_stage": "offer_accepted"}})
    await _audit(case["organization_id"], case["id"], "offer_accepted", user)
    await _notify(case["organization_id"], case["id"], "hr", staff["id"], "offer_accepted",
                  f"{staff.get('full_name')} accepted their offer — ready to create the contract.")
    return {"status": "accepted", "certificate_id": cert["id"]}


@router.post("/new-starter/contract/sign")
async def recruit_sign_contract(body: SignBody, request: Request, user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    con = case.get("contract") or {}
    if con.get("status") not in ("issued",):
        raise HTTPException(400, "No contract awaiting signature")
    if not body.acknowledge:
        raise HTTPException(400, "You must confirm you have read the contract and schedules")
    ev, cert = await _sign_and_cert(case["organization_id"], case, "contract", body.signature_name,
                                    "employee", body.signature_method, body.signature_image, request, con["rendered"])
    con.setdefault("signatures", []).append({"party": "employee", **ev})
    con["status"] = "employee_signed"
    con["employee_signed_at"] = _now()
    con["history"].append({"status": "employee_signed", "at": _now()})
    await db.staff_onboarding_cases.update_one({"id": case["id"]},
        {"$set": {"contract": con, "status": "awaiting_employer_signature", "updated_at": _now()}})
    await _audit(case["organization_id"], case["id"], "contract_employee_signed", user)
    return {"status": "employee_signed"}


# ───────────────────────── uploads ─────────────────────────
async def _store_upload(org, case_id, staff_id, file: UploadFile, doc_type, user):
    ext = (file.filename or "f.bin").rsplit(".", 1)[-1].lower()
    data = await file.read()
    path = f"{APP_NAME}/onboarding/{org}/{case_id}/{uuid.uuid4()}.{ext}"
    ct = file.content_type or MIME.get(ext, "application/octet-stream")
    result = _put_object(path, data, ct)
    doc = {
        "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case_id, "staff_id": staff_id,
        "document_type": doc_type or "other", "storage_path": result["path"],
        "original_filename": file.filename, "content_type": ct, "size": result.get("size", len(data)),
        "file_hash": hashlib.sha256(data).hexdigest(), "verification_status": "pending",
        "is_deleted": False, "uploaded_by": user.get("id"), "upload_date": _now(),
    }
    await db.staff_onboarding_documents.insert_one(dict(doc))
    await _audit(org, case_id, "document_uploaded", user, document=doc_type)
    return _strip(doc)


@router.post("/new-starter/upload")
async def recruit_upload(file: UploadFile = File(...), document_type: str = Form("other"),
                         user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    return await _store_upload(case["organization_id"], case["id"], staff["id"], file, document_type, user)


@router.get("/staff-onboarding/files/{doc_id}/download")
async def download_file(doc_id: str, user: dict = Depends(get_current_user)):
    doc = await db.staff_onboarding_documents.find_one({"id": doc_id, "is_deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(404, "File not found")
    # HR of same org, or the recruit who owns it
    ok = (user.get("role") in HR_ROLES and user.get("organization_id") == doc["organization_id"])
    if not ok:
        staff = await db.staff_members.find_one({"user_id": user.get("id")})
        ok = staff and staff["id"] == doc.get("staff_id")
    if not ok:
        raise HTTPException(403, "Not authorised")
    await db.staff_onboarding_documents.update_one({"id": doc_id}, {"$inc": {"download_count": 1}})
    data, ct = _get_object(doc["storage_path"])
    return FileResponse(content=data, media_type=doc.get("content_type", ct))


# ───────────── Right to Work + DBS verification workflow (Phase 2) ─────────────
RTW_METHODS = [
    {"id": "share_code", "label": "Online right-to-work check (share code)"},
    {"id": "manual_document", "label": "Manual document check (passport / BRP)"},
    {"id": "idsp", "label": "Identity Service Provider (IDVT)"},
]
RTW_RESULTS = [
    {"id": "verified", "label": "Verified — has right to work"},
    {"id": "time_limited", "label": "Verified — time-limited (follow-up required)"},
    {"id": "follow_up", "label": "Follow-up check required"},
    {"id": "not_verified", "label": "Not verified"},
]
DBS_LEVELS = [
    {"id": "none", "label": "Not required"},
    {"id": "basic", "label": "Basic"},
    {"id": "standard", "label": "Standard"},
    {"id": "enhanced", "label": "Enhanced"},
    {"id": "enhanced_barred", "label": "Enhanced with barred list"},
]
DBS_STATUSES = [
    {"id": "not_required", "label": "Not required"},
    {"id": "requested", "label": "Requested"},
    {"id": "in_progress", "label": "In progress"},
    {"id": "clear", "label": "Cleared"},
    {"id": "not_clear", "label": "Not clear — review required"},
]


class RTWBody(BaseModel):
    method: Optional[str] = None
    result: str = "verified"    # verified | time_limited | follow_up | not_verified
    document_type: Optional[str] = None
    share_code: Optional[str] = None
    expiry: Optional[str] = None
    notes: Optional[str] = None
    provider: Optional[str] = None          # manual | <provider key> (scaffold)
    provider_reference: Optional[str] = None
    provider_status: Optional[str] = None


class DBSBody(BaseModel):
    level: str = "basic"        # none | basic | standard | enhanced | enhanced_barred
    status: str = "requested"   # not_required | requested | in_progress | clear | not_clear
    certificate_number: Optional[str] = None
    issue_date: Optional[str] = None
    notes: Optional[str] = None
    provider: Optional[str] = None          # manual | <provider key> (scaffold)
    provider_reference: Optional[str] = None
    provider_status: Optional[str] = None


@router.get("/staff-onboarding/checks/options")
async def check_options(user: dict = Depends(get_current_user)):
    _require_hr(user)
    return {"rtw_methods": RTW_METHODS, "rtw_results": RTW_RESULTS,
            "dbs_levels": DBS_LEVELS, "dbs_statuses": DBS_STATUSES}


@router.get("/staff-onboarding/cases/{case_id}/checks")
async def get_checks(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    rtw = await db.staff_right_to_work_checks.find_one({"onboarding_case_id": case_id})
    dbs = await db.staff_dbs_checks.find_one({"onboarding_case_id": case_id})
    dbs_required = bool((c.get("role_requirements") or {}).get("dbs_required"))
    return {"right_to_work": _strip(rtw) if rtw else None,
            "dbs": _strip(dbs) if dbs else None, "dbs_required": dbs_required}


@router.post("/staff-onboarding/cases/{case_id}/right-to-work")
async def set_rtw(case_id: str, body: RTWBody, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    await db.staff_right_to_work_checks.delete_many({"onboarding_case_id": case_id})
    await db.staff_right_to_work_checks.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case_id,
        "staff_id": c["staff_id"], "check_method": body.method, "result": body.result,
        "document_type": body.document_type, "share_code": body.share_code,
        "provider": body.provider or "manual", "provider_reference": body.provider_reference,
        "provider_status": body.provider_status,
        "checker": user.get("full_name"), "check_date": _now(), "expiry": body.expiry, "notes": body.notes})
    await _audit(org, case_id, "right_to_work_verified", user, new_value=body.result)
    return {"ok": True, "result": body.result}


@router.post("/staff-onboarding/cases/{case_id}/dbs")
async def set_dbs(case_id: str, body: DBSBody, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    await db.staff_dbs_checks.delete_many({"onboarding_case_id": case_id})
    await db.staff_dbs_checks.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case_id,
        "staff_id": c["staff_id"], "level": body.level, "status": body.status,
        "certificate_number": body.certificate_number, "issue_date": body.issue_date,
        "provider": body.provider or "manual", "provider_reference": body.provider_reference,
        "provider_status": body.provider_status,
        "checker": user.get("full_name"), "updated_at": _now(), "notes": body.notes})
    await _audit(org, case_id, "dbs_updated", user, new_value=f"{body.level}/{body.status}")
    return {"ok": True, "status": body.status, "level": body.level}


@router.post("/staff-onboarding/cases/{case_id}/dbs-required")
async def set_dbs_required(case_id: str, required: bool = True, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    rr = {**(c.get("role_requirements") or {}), "dbs_required": bool(required)}
    await db.staff_onboarding_cases.update_one({"id": case_id}, {"$set": {"role_requirements": rr, "updated_at": _now()}})
    return {"ok": True, "dbs_required": bool(required)}


# ───────────── verification provider scaffold (RTW/DBS integrations) ─────────────
# Provider-agnostic: manual workflow works today; a real provider is wired by
# setting its API key env var + implementing an initiate call. Statuses flow back
# via the signed webhook below (matched on provider_reference).
VERIFICATION_PROVIDERS = [
    {"key": "manual", "name": "Manual / in-person check", "types": ["rtw", "dbs"],
     "env_key": None, "always_available": True},
    {"key": "govuk_rtw", "name": "GOV.UK — View a job applicant's right to work (share code)",
     "types": ["rtw"], "env_key": "GOVUK_RTW_API_KEY"},
    {"key": "idsp", "name": "Identity Service Provider (IDVT)", "types": ["rtw"], "env_key": "IDSP_API_KEY"},
    {"key": "dbs_umbrella", "name": "DBS umbrella body (Basic/Standard/Enhanced)",
     "types": ["dbs"], "env_key": "DBS_PROVIDER_API_KEY"},
]


@router.get("/staff-onboarding/verification/providers")
async def verification_providers(user: dict = Depends(get_current_user)):
    _require_hr(user)
    out = []
    for p in VERIFICATION_PROVIDERS:
        configured = bool(p.get("always_available")) or bool(os.environ.get(p.get("env_key") or ""))
        out.append({"key": p["key"], "name": p["name"], "types": p["types"], "configured": configured})
    return {"providers": out, "webhook_path": "/api/staff-onboarding/verification/webhook",
            "webhook_secured": bool(os.environ.get("ONBOARDING_WEBHOOK_SECRET"))}


class VerificationWebhook(BaseModel):
    check_type: str                       # rtw | dbs
    provider: str
    provider_reference: str
    status: Optional[str] = None          # raw provider status
    result: Optional[str] = None          # mapped result (rtw) / dbs status
    expiry: Optional[str] = None
    certificate_number: Optional[str] = None
    raw: dict = {}


def _verify_webhook_sig(raw_body: bytes, signature: str | None) -> bool:
    secret = os.environ.get("ONBOARDING_WEBHOOK_SECRET")
    if not secret:
        # No secret configured yet (scaffold): accept only outside production.
        return os.environ.get("APP_ENV") != "production"
    if not signature:
        return False
    import hmac
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().replace("sha256=", ""))


@router.post("/staff-onboarding/verification/webhook")
async def verification_webhook(request: Request):
    """Provider status callback (public). Matches an existing RTW/DBS record by
    provider_reference and updates its status. Verifies an HMAC-SHA256 signature
    from the X-Onboarding-Signature header when ONBOARDING_WEBHOOK_SECRET is set."""
    raw = await request.body()
    if not _verify_webhook_sig(raw, request.headers.get("X-Onboarding-Signature")):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        payload = VerificationWebhook(**(await request.json()))
    except Exception:
        raise HTTPException(400, "Malformed webhook payload")
    coll = db.staff_right_to_work_checks if payload.check_type == "rtw" else db.staff_dbs_checks
    rec = await coll.find_one({"provider_reference": payload.provider_reference, "provider": payload.provider})
    if not rec:
        raise HTTPException(404, "No matching verification record")
    upd = {"provider_status": payload.status, "provider_callback_at": _now(), "provider_raw": payload.raw}
    if payload.check_type == "rtw" and payload.result:
        upd["result"] = payload.result
    if payload.check_type == "dbs" and payload.result:
        upd["status"] = payload.result
    if payload.expiry:
        upd["expiry"] = payload.expiry
    if payload.certificate_number:
        upd["certificate_number"] = payload.certificate_number
    await coll.update_one({"id": rec["id"]}, {"$set": upd})
    await _audit(rec["organization_id"], rec["onboarding_case_id"], f"{payload.check_type}_provider_update",
                 {"id": None, "full_name": f"provider:{payload.provider}", "role": "system"},
                 new_value=payload.status)
    return {"ok": True, "matched": rec["id"]}



# ───────────────────────── offer / contract PDF (Phase 2) ─────────────────────────
def _pdf_response(data: bytes, filename: str) -> FileResponse:
    return FileResponse(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/staff-onboarding/cases/{case_id}/offer.pdf")
async def hr_offer_pdf(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c or not c.get("offer"):
        raise HTTPException(404, "Offer not found")
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    from utils.onboarding_pdf import build_offer_pdf
    return _pdf_response(build_offer_pdf(c, staff, c["offer"]), f"offer-{case_id}.pdf")


@router.get("/staff-onboarding/cases/{case_id}/contract.pdf")
async def hr_contract_pdf(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c or not c.get("contract"):
        raise HTTPException(404, "Contract not found")
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    from utils.onboarding_pdf import build_contract_pdf
    return _pdf_response(build_contract_pdf(c, staff, c["contract"]), f"contract-{case_id}.pdf")


async def _gather_pack_data(case: dict) -> dict:
    cid = case["id"]
    forms = {f["form_key"]: _strip(f) for f in await db.staff_form_submissions.find({"onboarding_case_id": cid}).to_list(50)}
    docs = [_strip(d) for d in await db.staff_onboarding_documents.find({"onboarding_case_id": cid, "is_deleted": {"$ne": True}}).to_list(100)]
    acks = [_strip(a) for a in await db.staff_policy_acknowledgements.find({"onboarding_case_id": cid}).to_list(50)]
    agr = [_strip(a) for a in await db.staff_agreement_assignments.find({"onboarding_case_id": cid}).to_list(50)]
    rtw = await db.staff_right_to_work_checks.find_one({"onboarding_case_id": cid})
    dbs = await db.staff_dbs_checks.find_one({"onboarding_case_id": cid})
    return {"forms": forms, "documents": docs, "policy_acknowledgements": acks, "agreements": agr,
            "right_to_work": _strip(rtw) if rtw else {}, "dbs": _strip(dbs) if dbs else {}}


@router.get("/staff-onboarding/cases/{case_id}/forms.pdf")
async def hr_forms_pdf(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    forms = {f["form_key"]: _strip(f) for f in await db.staff_form_submissions.find({"onboarding_case_id": case_id}).to_list(50)}
    from utils.onboarding_pdf import build_forms_pdf
    return _pdf_response(build_forms_pdf(c, staff, forms), f"new-starter-form-{case_id}.pdf")


@router.get("/staff-onboarding/cases/{case_id}/pack.pdf")
async def hr_pack_pdf(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    staff = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    data = await _gather_pack_data(c)
    from utils.onboarding_pdf import build_pack_pdf
    await _audit(org, case_id, "onboarding_pack_generated", user)
    return _pdf_response(build_pack_pdf(c, staff, data), f"onboarding-pack-{case_id}.pdf")



@router.get("/new-starter/offer.pdf")
async def recruit_offer_pdf(user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    offer = case.get("offer") or {}
    if offer.get("status") not in ("issued", "accepted", "declined"):
        raise HTTPException(404, "No offer available")
    from utils.onboarding_pdf import build_offer_pdf
    return _pdf_response(build_offer_pdf(case, staff, offer), "your-offer.pdf")


@router.get("/new-starter/contract.pdf")
async def recruit_contract_pdf(user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    con = case.get("contract") or {}
    if con.get("status") not in ("issued", "employee_signed", "fully_signed"):
        raise HTTPException(404, "No contract available")
    from utils.onboarding_pdf import build_contract_pdf
    return _pdf_response(build_contract_pdf(case, staff, con), "your-contract.pdf")


# ───────────────────────── AI assist (Emergent LLM key) ─────────────────────────
AI_MODEL = ("anthropic", "claude-sonnet-4-5-20250929")


def _llm_key() -> str:
    k = os.environ.get("EMERGENT_LLM_KEY") or ""
    if not k:
        raise HTTPException(503, "AI service not configured (EMERGENT_LLM_KEY missing)")
    return k


async def _ai_chat(system: str, user_text: str, session_id: str) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(api_key=_llm_key(), session_id=session_id, system_message=system).with_model(*AI_MODEL)
    return await chat.send_message(UserMessage(text=user_text))


def _ai_json(text: str):
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[:-3]
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    try:
        return json.loads(s)
    except Exception:
        a, b = s.find("{"), s.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(s[a:b + 1])
            except Exception:
                return None
    return None


@router.post("/staff-onboarding/cases/{case_id}/ai/duplicate-scan")
async def ai_duplicate_scan(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    subject = await db.staff_members.find_one({"id": c["staff_id"]}) or {}
    # candidate pool: other people in the org (cap 60 for prompt size)
    pool = await db.staff_members.find(
        {"organization_id": org, "id": {"$ne": c["staff_id"]}}).to_list(60)
    subj = {"full_name": subject.get("full_name"), "email": subject.get("email"),
            "mobile": subject.get("mobile"), "dob": (subject.get("date_of_birth") or "")}
    pool_slim = [{"staff_id": p["id"], "full_name": p.get("full_name"), "email": p.get("email"),
                  "mobile": p.get("mobile"), "active": bool(p.get("active")),
                  "lifecycle_stage": p.get("lifecycle_stage")} for p in pool]
    system = ("You are an HR data-quality assistant for a UK employer. Identify likely DUPLICATE person "
              "records for a new recruit versus existing staff. Consider name variants/typos, shared or "
              "similar email/mobile, and nicknames. Return STRICT JSON only: "
              '{"matches":[{"staff_id":"","full_name":"","confidence":0-100,"reasons":["..."]}],'
              '"summary":"one sentence"}. Only include matches with confidence >= 40. If none, return an empty list.')
    user_text = json.dumps({"recruit": subj, "existing_staff": pool_slim})[:12000]
    try:
        raw = await _ai_chat(system, user_text, f"onb-dup-{case_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"AI request failed: {e}")
    parsed = _ai_json(raw) or {"matches": [], "summary": raw[:200]}
    # enrich matches with a live record snapshot (id validity guard)
    valid = {p["id"]: p for p in pool}
    for m in parsed.get("matches", []):
        rec = valid.get(m.get("staff_id"))
        if rec:
            m["active_employee"] = bool(rec.get("active"))
            m["lifecycle_stage"] = rec.get("lifecycle_stage")
    await _audit(org, case_id, "ai_duplicate_scan", user, matches=len(parsed.get("matches", [])))
    return parsed


@router.post("/staff-onboarding/cases/{case_id}/ai/consistency")
async def ai_consistency(case_id: str, user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    offer = c.get("offer") or {}
    contract = c.get("contract") or {}
    if not offer.get("rendered") and not contract.get("rendered"):
        raise HTTPException(400, "Create an offer and/or contract first")
    offer_terms = _offer_terms(offer) if offer else {}
    contract_terms = {k: (contract.get("merge_context") or {}).get(k) for k in CONSISTENCY_FIELDS} if contract else {}
    deterministic = contract.get("differences", []) if contract else []
    system = ("You are an HR compliance assistant for a UK employer. Compare the key terms of an OFFER LETTER "
              "with the EMPLOYMENT CONTRACT and flag any inconsistencies (salary, hours, start date, job title, "
              "probation, notice, holiday, benefits, employment type, site, company). Return STRICT JSON only: "
              '{"risk_level":"low|medium|high","inconsistencies":[{"field":"","offer":"","contract":"","note":""}],'
              '"summary":"plain-English HR summary (max 3 sentences)"}.')
    user_text = json.dumps({"offer_terms": offer_terms, "contract_terms": contract_terms,
                            "deterministic_differences": deterministic})[:8000]
    try:
        raw = await _ai_chat(system, user_text, f"onb-cons-{case_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"AI request failed: {e}")
    parsed = _ai_json(raw) or {"risk_level": "unknown", "inconsistencies": [], "summary": raw[:300]}
    parsed["deterministic_differences"] = deterministic
    await _audit(org, case_id, "ai_consistency_check", user, risk=parsed.get("risk_level"))
    return parsed



# ───────────────────────── notifications ─────────────────────────
@router.get("/staff-onboarding/notifications")
async def hr_notifications(user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    items = await db.staff_onboarding_notifications.find(
        {"organization_id": org, "audience": "hr"}).sort("created_at", -1).to_list(100)
    unread = sum(1 for n in items if not n.get("read"))
    return {"notifications": [_strip(n) for n in items], "unread": unread}


@router.post("/staff-onboarding/notifications/read")
async def hr_notifications_read(user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    await db.staff_onboarding_notifications.update_many(
        {"organization_id": org, "audience": "hr", "read": False}, {"$set": {"read": True}})
    return {"ok": True}


@router.get("/new-starter/notifications")
async def recruit_notifications(user: dict = Depends(get_current_user)):
    case, staff = await _recruit_case(user)
    items = await db.staff_onboarding_notifications.find(
        {"onboarding_case_id": case["id"], "audience": "recruit"}).sort("created_at", -1).to_list(100)
    unread = sum(1 for n in items if not n.get("read"))
    return {"notifications": [_strip(n) for n in items], "unread": unread}
