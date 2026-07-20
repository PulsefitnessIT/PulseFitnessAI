"""Staff Onboarding, Offer Letter & Employment Contract Wizard (Phase 1 spine).

Extends Operations → Staffing → People. The single person record is
``staff_members`` (never duplicated) which progresses:
    candidate → recruit → onboarding → offer_issued → contract_issued → employee.

All legal wording is uploaded/approved by Pulse HR & legal; anything seeded here
is a clearly-marked NON-BINDING SAMPLE placeholder.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.responses import Response as FileResponse
from pydantic import BaseModel

from utils.database import db
from utils.auth import get_current_user, hash_password, create_token

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
                  email_to=None, email_subject=None, email_html=None):
    """Record an in-app notification and (best-effort) send a neutral email."""
    await db.staff_onboarding_notifications.insert_one({
        "id": str(uuid.uuid4()), "organization_id": org, "onboarding_case_id": case_id,
        "audience": audience, "staff_id": staff_id, "event": event, "message": message,
        "read": False, "created_at": _now(),
    })
    if email_to and email_subject and email_html:
        try:
            await send_email(to=email_to, subject=email_subject, html=email_html,
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
    "Dear {{preferred_name}},\n\n"
    "[SAMPLE OFFER LETTER — replace with approved Pulse Fitness wording]\n\n"
    "We are pleased to offer you the position of {{job_title}} in the {{department}} "
    "department at {{company}}, based at {{site}}, reporting to {{line_manager}}.\n\n"
    "Proposed start date: {{start_date}}\n"
    "Salary: {{salary}} ({{pay_frequency}})\n"
    "Hours: {{hours}} per week — {{employment_type}}\n"
    "Probation: {{probation}}    Notice: {{notice_period}}\n"
    "Holiday entitlement: {{holiday}}\n"
    "Benefits: {{benefits}}\n\n"
    "This offer is issued on {{date}}. Please review and respond via your Pulse Fitness "
    "New Starter Portal.\n\nYours sincerely,\n{{signatory}} — {{company}}"
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
    "CONTRACT OF EMPLOYMENT — [SAMPLE, non-binding]\n\n"
    "Between {{company}} (the Employer) and {{legal_name}} (the Employee).\n\n"
    "1. Job title: {{job_title}}, {{department}}.\n"
    "2. Reporting to: {{line_manager}}.\n"
    "3. Start date: {{start_date}}.  Place of work: {{site}}.\n"
    "4. Salary: {{salary}} ({{pay_frequency}}).  Hours: {{hours}}/week — {{employment_type}}.\n"
    "5. Probation: {{probation}}.  Notice: {{notice_period}}.\n"
    "6. Holiday entitlement: {{holiday}}.  Pension: {{pension}}.\n"
    "7. Benefits: {{benefits}}.  Bonus/commission: {{bonus}}.\n\n"
    "This is a SAMPLE contract skeleton. Approved clauses (confidentiality, IP, restrictive "
    "covenants, disciplinary, grievance, data protection, governing law) must be uploaded and "
    "approved by Pulse Fitness HR and legal advisers before use.\n\n"
    "Signed by the Employer: ____________________\n"
    "Signed by the Employee: ____________________"
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
        "right_to_work": bool(rtw and rtw.get("result") == "verified"),
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
        "right_to_work_verified": bool(rtw and rtw.get("result") == "verified"),
        "paperwork_complete": bool(c.get("paperwork_complete")),
    }
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
        await _notify(org, case_id, "recruit", c["staff_id"], "activated",
                      "Welcome to the team! Your Staff Portal is now active.",
                      email_to=staff2["email"], email_subject="Welcome to Pulse Fitness — your first day",
                      email_html=_email_shell(f"Welcome, {staff2.get('preferred_name') or staff2.get('full_name')}!",
                          ["Your onboarding is complete and your account is now your Pulse Fitness Staff Portal.",
                           "All your completed documents, offer letter and contract remain available there.",
                           f"Your start date: {ep.get('proposed_start_date') or 'to be confirmed'}."],
                          cta_url=url, cta_label="Open my Staff Portal"))
    return {"status": "complete", "staff_id": c["staff_id"]}


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


PROGRESS_STEPS = ["forms", "documents", "verification", "policies", "agreements", "offer", "contract", "ready_to_start"]


@router.get("/new-starter/me")
async def recruit_me(user: dict = Depends(get_current_user)):
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
        "activated": activated, "status": case.get("status"), "person": {"full_name": staff.get("full_name"), "email": staff.get("email")},
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


@router.post("/staff-onboarding/cases/{case_id}/upload")
async def hr_upload(case_id: str, file: UploadFile = File(...), document_type: str = Form("other"),
                    user: dict = Depends(get_current_user)):
    _require_hr(user); org = _org(user)
    c = await db.staff_onboarding_cases.find_one({"id": case_id, "organization_id": org})
    if not c:
        raise HTTPException(404, "Case not found")
    return await _store_upload(org, case_id, c["staff_id"], file, document_type, user)


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


# ───────────────────────── right to work (light Phase 1) ─────────────────────────
class RTWBody(BaseModel):
    method: Optional[str] = None
    result: str = "verified"    # verified | follow_up | not_verified
    expiry: Optional[str] = None
    notes: Optional[str] = None


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
        "checker": user.get("full_name"), "check_date": _now(), "expiry": body.expiry, "notes": body.notes})
    await _audit(org, case_id, "right_to_work_verified", user, new_value=body.result)
    return {"ok": True, "result": body.result}


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
