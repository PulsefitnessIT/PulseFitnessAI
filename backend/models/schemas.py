from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    # Trial signup fields (optional — landing-page funnel)
    is_trial: Optional[bool] = False
    trial_duration_days: Optional[int] = 3
    # Iter 215bc — when true (default), the trial unlocks every module so
    # prospects can evaluate the entire GymAxis platform during the
    # 3-day window. Legacy bolt-on funnels (per-module trials) pass false.
    trial_unlock_all_modules: Optional[bool] = True
    phone: Optional[str] = None
    # Cloudflare Turnstile token — required for trial signups only.
    cf_turnstile_response: Optional[str] = None
    # Iter 216h75 — Partner Engineer Network referral attribution.
    # When supplied (and matches an approved partner_engineers row), the
    # new organisation is permanently linked to that partner for
    # commission accrual on the first cleared Operations invoice.
    ref_code: Optional[str] = None
    # Iter 216h219 — Trial signup org-profile enrichment.
    # Captured on the new "Tell us about your gym" step of the trial
    # modal so Master Admin → Organisations → Details has Industry /
    # Employees / Website / Referral-source pre-filled the moment a
    # prospect lands. All optional — empty values are ignored.
    website: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[str] = None
    # Free-text "How did you hear about us?" — feeds the marketing
    # attribution dashboard alongside the silent UTM tags below.
    referral_source: Optional[str] = None
    # Silent marketing attribution. Captured by the trial modal from
    # `window.location.search` and forwarded here so the org doc
    # records the exact campaign that drove the signup.
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None


class UserLogin(BaseModel):
    # Use `str` (not EmailStr) so invalid-format emails return a generic
    # 401 "Invalid credentials" from the route rather than a 422 validation
    # error that reveals whether the email is malformed (user enumeration
    # hardening — security audit medium finding).
    email: str
    password: str
    # Iter 216h113f — portal scope. When set to "mod" the login is
    # only honoured for MOD account types (`mod_site` / `mod_branch` /
    # `mod_org`); any other account is rejected with a portal-mismatch
    # error so the MODService surface stays isolated from the
    # commercial Pulse Fitness customer base. When unset / "pulse",
    # MOD accounts are bounced back so they end up on /MODService
    # rather than inside a Third Space tenant.
    portal: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    company_name: Optional[str]
    subscription_tier: str
    created_at: str
    role: str
    organization_id: Optional[str]


class InviteStaff(BaseModel):
    email: EmailStr
    role: str
    full_name: Optional[str] = None


class ChatMessage(BaseModel):
    message: str
    equipment_type: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    severity: Optional[str] = None
    can_fix_onsite: Optional[bool] = None


class AuditRequest(BaseModel):
    equipment_id: Optional[str] = None
    equipment_type: str
    usage_frequency: str
    last_maintenance: str
    notes: Optional[str] = None


class AuditResponse(BaseModel):
    id: str
    report: str
    rating: str
    recommendations: List[str]
    created_at: str


class IssueCreate(BaseModel):
    serial_number: str
    machine_type: str
    issue_description: str
    severity: str
    supplier: Optional[str] = None
    steps_taken: Optional[str] = None
    language: Optional[str] = "en"
    resolution_type: Optional[str] = None
    resolution_note: Optional[str] = None
    ai_triage: Optional[str] = None
    can_fix_onsite: Optional[bool] = None
    selected_fix_step: Optional[str] = None
    selected_fix_title: Optional[str] = None
    fix_method: Optional[str] = None
    fault_code: Optional[str] = None
    # Iter 216d — optional `job_id` lets the operator log multiple
    # machines in one workflow; each machine becomes its own issue
    # (so SLA + reports stay per-machine) but they share a `job_id`
    # for grouped display in the fault list and a single bundled
    # supplier email. Defaults to None for legacy single-machine logs.
    job_id: Optional[str] = None


class IssueBatchCreate(BaseModel):
    """Iter 216d — log a single fault job covering multiple machines.

    The `job_id` (server-generated if omitted) is stamped on every issue
    document in `machines`, letting the fault list group them under one
    expandable parent row and the supplier-email flow bundle all
    machines into a single message. Each machine still becomes its own
    `db.issues` row so per-machine SLA, status, and reporting all stay
    untouched — just the *intake* fans out to N rows in one call.
    """
    machines: List[IssueCreate]
    job_id: Optional[str] = None


class IssueResponse(BaseModel):
    id: str
    serial_number: str
    machine_type: str
    issue_description: str
    severity: str
    status: str
    ai_triage: Optional[str] = None
    can_fix_onsite: Optional[bool] = None
    supplier: Optional[str] = None
    created_at: str
    updated_at: str


class ServiceRequest(BaseModel):
    machine_type: str
    issue_summary: str
    site_info: str
    contact_name: str
    contact_email: EmailStr
    contact_phone: str


class CheckoutRequest(BaseModel):
    package_id: str
    origin_url: str


class EmailRequest(BaseModel):
    recipient_email: EmailStr
    subject: str
    html_content: str


class EquipmentPosition(BaseModel):
    x: float
    y: float
    rotation: Optional[float] = 0


class EquipmentCreate(BaseModel):
    name: str
    equipment_type: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    purchase_date: Optional[str] = None
    warranty_expiry: Optional[str] = None
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    notes: Optional[str] = None
    location: Optional[str] = None
    sla_response_time: Optional[str] = None
    sla_contract_ref: Optional[str] = None
    sla_expiry: Optional[str] = None
    # Iter 216h225 — accept site_id from the create form so multi-site
    # orgs (Pulse Fitness Pro, MOD HQ children, etc.) tag the row with
    # the active site. Optional — single-site orgs leave it null and
    # the list endpoint's lazy backfill heals it on first load.
    site_id: Optional[str] = None
    supplier: Optional[str] = None
    supplier_email: Optional[str] = None


class EquipmentResponse(BaseModel):
    id: str
    name: str
    equipment_type: str
    manufacturer: Optional[str]
    model: Optional[str]
    serial_number: Optional[str]
    purchase_date: Optional[str]
    warranty_expiry: Optional[str]
    length: Optional[float]
    width: Optional[float]
    height: Optional[float]
    notes: Optional[str]
    manuals: List[Dict]
    stats: Dict
    created_at: str


class GymLayoutCreate(BaseModel):
    name: str
    gym_length: float
    gym_width: float
    equipment_positions: List[Dict]
    floor_plan_url: Optional[str] = None


class GymLayoutResponse(BaseModel):
    id: str
    name: str
    gym_length: float
    gym_width: float
    equipment_positions: List[Dict]
    created_at: str
    updated_at: str


class RiskAssessmentCreate(BaseModel):
    title: str
    site_name: str
    assessor: str
    assessment_date: str
    validity_period: Optional[str] = "12 months"
    hazards: List[Dict[str, Any]] = []
    recommendations: List[Dict[str, Any]] = []
    notes: Optional[str] = None
