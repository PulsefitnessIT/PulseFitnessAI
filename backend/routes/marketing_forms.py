"""Marketing — Forms + Landing Pages (Iter 228).

MVP scope: list-based form builder + single-template landing pages.
Closes the top P1 gap from the HubSpot Parity audit (no form builder,
no landing-page builder).

Endpoints:
  Forms (operator-facing, /api/marketing/forms):
    GET    /forms                       — list forms in this org
    POST   /forms                       — create a new form
    GET    /forms/{id}                  — get a single form (full schema)
    PUT    /forms/{id}                  — update form fields/settings
    DELETE /forms/{id}                  — soft-delete (status=archived)
    GET    /forms/{id}/submissions      — paginated submissions
    GET    /forms/by-slug/{slug}        — UNAUTH — used by hosted /forms/{slug} page
    POST   /forms/by-slug/{slug}/submit — UNAUTH — public submit

  Landing Pages (operator-facing, /api/marketing/pages):
    GET    /pages                       — list pages in this org
    POST   /pages                       — create
    GET    /pages/{id}                  — get
    PUT    /pages/{id}                  — update
    DELETE /pages/{id}                  — soft-delete
    GET    /pages/by-slug/{slug}        — UNAUTH — used by /p/{slug}
    POST   /pages/by-slug/{slug}/visit  — UNAUTH — pageview tracking ping

Submission flow on a form:
  1. Validate against the form's field definitions.
  2. Insert a row in form_submissions.
  3. Auto-create a CRM contact (lifecycle=Lead, source=form:<form_name>).
  4. Send confirmation email if `send_confirmation` is enabled.
  5. Notify the form's `notify_emails` list (defaults to creator's email).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from utils.auth import get_current_user
from utils.database import db

logger = logging.getLogger(__name__)
router = APIRouter()

# ────────────────────────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────────────────────────

VALID_FIELD_TYPES = {
    "text", "email", "phone", "textarea", "select", "checkbox", "number",
}


class FormField(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str
    field_type: str
    required: bool = False
    placeholder: str = ""
    options: list[str] = []  # for select fields
    crm_property: Optional[str] = None  # which CRM contact field this maps to


class FormSchema(BaseModel):
    name: str
    description: str = ""
    fields: list[FormField] = []
    submit_button_label: str = "Submit"
    success_message: str = "Thanks — we've received your details."
    redirect_url: Optional[str] = None
    require_consent: bool = True
    consent_text: str = (
        "I agree to be contacted by GymAxis and consent to my data being "
        "processed in line with the privacy policy."
    )
    send_confirmation: bool = False
    confirmation_subject: str = "Thanks for getting in touch"
    confirmation_body: str = "We'll be in touch shortly."
    notify_emails: list[EmailStr] = []  # CC list — creator added automatically


class PageSchema(BaseModel):
    title: str
    subtitle: str = ""
    body_markdown: str = ""
    hero_image_url: Optional[str] = None
    cta_label: Optional[str] = None
    cta_url: Optional[str] = None
    form_id: Optional[str] = None  # embedded form
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

SLUG_RX = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    s = SLUG_RX.sub("-", (text or "").lower()).strip("-")
    return s[:60] or str(uuid.uuid4())[:8]


async def _ensure_unique_slug(coll_name: str, base: str) -> str:
    """Append `-2`, `-3`, … until the slug is free in the given collection."""
    slug = base
    n = 1
    while await db[coll_name].find_one({"slug": slug}, {"_id": 1}):
        n += 1
        slug = f"{base}-{n}"
    return slug


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ────────────────────────────────────────────────────────────────────
# Forms — authenticated CRUD
# ────────────────────────────────────────────────────────────────────

@router.get("/forms")
async def list_forms(user: dict = Depends(get_current_user)) -> dict:
    org_id = user.get("organization_id")
    cursor = db.marketing_forms.find(
        {"organization_id": org_id, "status": {"$ne": "archived"}}, {"_id": 0},
    ).sort("created_at", -1)
    forms = await cursor.to_list(length=200)
    # Surface submission counts cheaply (one round-trip per form is fine for MVP scale).
    for f in forms:
        f["submission_count"] = await db.form_submissions.count_documents({"form_id": f["id"]})
    return {"forms": forms, "count": len(forms)}


@router.post("/forms")
async def create_form(payload: FormSchema, user: dict = Depends(get_current_user)) -> dict:
    form_id = str(uuid.uuid4())
    base_slug = _slugify(payload.name)
    slug = await _ensure_unique_slug("marketing_forms", base_slug)
    notify = list({user["email"], *(payload.notify_emails or [])}) if user.get("email") else list(payload.notify_emails or [])
    doc = {
        **payload.model_dump(),
        "id": form_id,
        "slug": slug,
        "organization_id": user.get("organization_id"),
        "created_by": user["id"],
        "created_by_email": user.get("email"),
        "created_at": _now(),
        "updated_at": _now(),
        "status": "active",
        "notify_emails": notify,
    }
    await db.marketing_forms.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/forms/{form_id}")
async def get_form(form_id: str, user: dict = Depends(get_current_user)) -> dict:
    doc = await db.marketing_forms.find_one(
        {"id": form_id, "organization_id": user.get("organization_id")}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Form not found")
    doc["submission_count"] = await db.form_submissions.count_documents({"form_id": form_id})
    return doc


@router.put("/forms/{form_id}")
async def update_form(form_id: str, payload: FormSchema, user: dict = Depends(get_current_user)) -> dict:
    existing = await db.marketing_forms.find_one(
        {"id": form_id, "organization_id": user.get("organization_id")}, {"_id": 1},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Form not found")
    update = {**payload.model_dump(), "updated_at": _now()}
    await db.marketing_forms.update_one({"id": form_id}, {"$set": update})
    out = await db.marketing_forms.find_one({"id": form_id}, {"_id": 0})
    return out


@router.delete("/forms/{form_id}")
async def archive_form(form_id: str, user: dict = Depends(get_current_user)) -> dict:
    res = await db.marketing_forms.update_one(
        {"id": form_id, "organization_id": user.get("organization_id")},
        {"$set": {"status": "archived", "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Form not found")
    return {"archived": True}


@router.get("/forms/{form_id}/submissions")
async def list_submissions(
    form_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),
) -> dict:
    # Ownership check
    form = await db.marketing_forms.find_one(
        {"id": form_id, "organization_id": user.get("organization_id")}, {"_id": 1},
    )
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    skip = (page - 1) * page_size
    total = await db.form_submissions.count_documents({"form_id": form_id})
    cursor = db.form_submissions.find({"form_id": form_id}, {"_id": 0}).sort("submitted_at", -1).skip(skip).limit(page_size)
    rows = await cursor.to_list(page_size)
    return {"submissions": rows, "total": total, "page": page, "page_size": page_size}


# ────────────────────────────────────────────────────────────────────
# Forms — public (UNAUTH) endpoints
# ────────────────────────────────────────────────────────────────────

@router.get("/forms/by-slug/{slug}")
async def get_form_by_slug(slug: str) -> dict:
    """Public — used by the hosted /forms/{slug} page. Returns only the
    fields the public page needs (no notify list, no creator info)."""
    doc = await db.marketing_forms.find_one(
        {"slug": slug, "status": "active"}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Form not found")
    public = {
        "id": doc["id"],
        "slug": doc["slug"],
        "name": doc["name"],
        "description": doc.get("description", ""),
        "fields": doc.get("fields", []),
        "submit_button_label": doc.get("submit_button_label", "Submit"),
        "success_message": doc.get("success_message", "Thanks!"),
        "redirect_url": doc.get("redirect_url"),
        "require_consent": doc.get("require_consent", True),
        "consent_text": doc.get("consent_text", ""),
    }
    return public


@router.post("/forms/by-slug/{slug}/submit")
async def submit_form(slug: str, payload: dict = Body(...)) -> dict:
    """Public — accepts a form submission, validates against the schema,
    creates the CRM contact, and queues notifications.
    """
    form = await db.marketing_forms.find_one(
        {"slug": slug, "status": "active"}, {"_id": 0},
    )
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    values = payload.get("values") or {}
    consent = bool(payload.get("consent"))
    if form.get("require_consent") and not consent:
        raise HTTPException(status_code=400, detail="Consent is required.")

    # Validate required fields are present.
    missing = []
    for f in form.get("fields", []):
        if f.get("required") and not str(values.get(f["id"], "")).strip():
            missing.append(f["label"])
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    # Build CRM contact mapping.
    crm = {"first_name": "", "last_name": "", "email": "", "phone": "", "company_name": "", "notes": ""}
    custom_fields: dict = {}
    extra_notes_lines: list[str] = []
    for f in form.get("fields", []):
        v = str(values.get(f["id"], "")).strip()
        if not v:
            continue
        prop = f.get("crm_property") or ""
        if prop in crm:
            crm[prop] = v
        elif prop.startswith("custom."):
            # Iter 232 — route into the contact's custom_fields map.
            ckey = prop[len("custom."):]
            if ckey:
                custom_fields[ckey] = v
        else:
            extra_notes_lines.append(f"{f['label']}: {v}")
    if extra_notes_lines:
        crm["notes"] = "\n".join(extra_notes_lines)

    submission_id = str(uuid.uuid4())
    submission = {
        "id": submission_id,
        "form_id": form["id"],
        "form_name": form["name"],
        "organization_id": form.get("organization_id"),
        "values": values,
        "consent": consent,
        "submitted_at": _now(),
        "ip_address": payload.get("ip_address"),
        "user_agent": payload.get("user_agent"),
        "utm": payload.get("utm") or {},
    }
    await db.form_submissions.insert_one(submission)

    # Auto-create CRM contact if email present (the only PII we need to create one).
    # Iter 215bx — write to v2 collection so the active CRM portal sees the lead.
    if crm.get("email"):
        from utils.crm_sync import upsert_crm_contact, upsert_crm_company, log_crm_activity
        try:
            company_id = None
            if crm.get("company_name"):
                company_id = await upsert_crm_company(
                    form.get("organization_id"),
                    name=crm["company_name"],
                    source=f"form:{form['slug']}",
                )
            contact_id = await upsert_crm_contact(
                form.get("organization_id"),
                email=crm["email"],
                first_name=crm.get("first_name"),
                last_name=crm.get("last_name"),
                phone=crm.get("phone"),
                source=f"form:{form['name']}",
                lifecycle="Lead",
                tags=[f"form:{form['slug']}"],
                notes=crm.get("notes"),
                company_id=company_id,
                company_name=crm.get("company_name"),
                custom_fields=custom_fields,
                communication_preferences={
                    "marketing_email_opt_in": True,
                    "consent_source": f"form:{form['slug']}",
                    "consent_at": _now(),
                },
            )
            if contact_id:
                await log_crm_activity(
                    form.get("organization_id"),
                    contact_id=contact_id,
                    type="form_submission",
                    subject=f"Form: {form['name']}",
                    body=crm.get("notes") or "",
                )
                await db.form_submissions.update_one(
                    {"id": submission_id}, {"$set": {"crm_contact_id": contact_id}},
                )
        except Exception as exc:
            logger.info("CRM sync from form failed (non-fatal): %s", exc)

    # Queue email notifications + confirmation. Best-effort.
    notify_to = list(form.get("notify_emails") or [])
    if notify_to:
        try:
            from utils.email import send_email
            body_lines = [f"<p>New submission for <b>{form['name']}</b></p><ul>"]
            for f in form.get("fields", []):
                v = values.get(f["id"], "")
                if v:
                    body_lines.append(f"<li><b>{f['label']}</b>: {v}</li>")
            body_lines.append("</ul>")
            html = "".join(body_lines)
            for addr in notify_to:
                try:
                    await send_email(to=addr, subject=f"New form submission — {form['name']}", html=html)
                except Exception as exc:
                    logger.info("notify email to %s failed: %s", addr, exc)
        except Exception as exc:
            logger.info("notify email setup failed (non-fatal): %s", exc)

    if form.get("send_confirmation") and crm.get("email"):
        try:
            from utils.email import send_email
            await send_email(
                to=crm["email"],
                subject=form.get("confirmation_subject") or "Thanks!",
                html=f"<p>{form.get('confirmation_body') or 'Thanks!'}</p>",
            )
        except Exception as exc:
            logger.info("confirmation email failed (non-fatal): %s", exc)

    return {
        "submitted": True,
        "submission_id": submission_id,
        "success_message": form.get("success_message"),
        "redirect_url": form.get("redirect_url"),
    }


# ────────────────────────────────────────────────────────────────────
# Landing Pages — authenticated CRUD
# ────────────────────────────────────────────────────────────────────

@router.get("/pages")
async def list_pages(user: dict = Depends(get_current_user)) -> dict:
    org_id = user.get("organization_id")
    cursor = db.marketing_pages.find(
        {"organization_id": org_id, "status": {"$ne": "archived"}}, {"_id": 0},
    ).sort("created_at", -1)
    pages = await cursor.to_list(length=200)
    return {"pages": pages, "count": len(pages)}


@router.post("/pages")
async def create_page(payload: PageSchema, user: dict = Depends(get_current_user)) -> dict:
    page_id = str(uuid.uuid4())
    base_slug = _slugify(payload.title)
    slug = await _ensure_unique_slug("marketing_pages", base_slug)
    doc = {
        **payload.model_dump(),
        "id": page_id,
        "slug": slug,
        "organization_id": user.get("organization_id"),
        "created_by": user["id"],
        "created_at": _now(),
        "updated_at": _now(),
        "status": "draft",  # Pages start as drafts; user explicitly publishes.
        "view_count": 0,
    }
    await db.marketing_pages.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/pages/{page_id}")
async def get_page(page_id: str, user: dict = Depends(get_current_user)) -> dict:
    doc = await db.marketing_pages.find_one(
        {"id": page_id, "organization_id": user.get("organization_id")}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Page not found")
    return doc


@router.put("/pages/{page_id}")
async def update_page(page_id: str, payload: dict = Body(...), user: dict = Depends(get_current_user)) -> dict:
    existing = await db.marketing_pages.find_one(
        {"id": page_id, "organization_id": user.get("organization_id")}, {"_id": 1},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Page not found")
    # Whitelist updatable fields — including status (publish/unpublish).
    allowed = {"title", "subtitle", "body_markdown", "hero_image_url", "cta_label",
               "cta_url", "form_id", "seo_title", "seo_description", "status"}
    update = {k: v for k, v in payload.items() if k in allowed}
    if "status" in update and update["status"] not in ("draft", "published", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status")
    update["updated_at"] = _now()
    await db.marketing_pages.update_one({"id": page_id}, {"$set": update})
    out = await db.marketing_pages.find_one({"id": page_id}, {"_id": 0})
    return out


@router.delete("/pages/{page_id}")
async def archive_page(page_id: str, user: dict = Depends(get_current_user)) -> dict:
    res = await db.marketing_pages.update_one(
        {"id": page_id, "organization_id": user.get("organization_id")},
        {"$set": {"status": "archived", "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Page not found")
    return {"archived": True}


# ────────────────────────────────────────────────────────────────────
# Landing Pages — public (UNAUTH) endpoints
# ────────────────────────────────────────────────────────────────────

@router.get("/pages/by-slug/{slug}")
async def get_page_by_slug(slug: str) -> dict:
    """Public — used by /p/{slug}. Only published pages are visible."""
    doc = await db.marketing_pages.find_one(
        {"slug": slug, "status": "published"}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Page not found or not published")
    # If the page embeds a form, include the public form payload too.
    embedded_form = None
    if doc.get("form_id"):
        f = await db.marketing_forms.find_one(
            {"id": doc["form_id"], "status": "active"}, {"_id": 0},
        )
        if f:
            embedded_form = {
                "id": f["id"], "slug": f["slug"], "name": f["name"],
                "fields": f.get("fields", []),
                "submit_button_label": f.get("submit_button_label", "Submit"),
                "success_message": f.get("success_message", "Thanks!"),
                "require_consent": f.get("require_consent", True),
                "consent_text": f.get("consent_text", ""),
            }
    public = {
        "id": doc["id"], "slug": doc["slug"], "title": doc["title"],
        "subtitle": doc.get("subtitle", ""), "body_markdown": doc.get("body_markdown", ""),
        "hero_image_url": doc.get("hero_image_url"),
        "cta_label": doc.get("cta_label"), "cta_url": doc.get("cta_url"),
        "seo_title": doc.get("seo_title") or doc["title"],
        "seo_description": doc.get("seo_description") or doc.get("subtitle", ""),
        "form": embedded_form,
    }
    return public


@router.post("/pages/by-slug/{slug}/visit")
async def track_visit(slug: str, payload: dict = Body(default=None)) -> dict:
    """Public — increment pageview counter and record optional UTM params."""
    payload = payload or {}
    utm = payload.get("utm") or {}
    inc = {"view_count": 1}
    set_doc = {"last_visit_at": _now()}
    await db.marketing_pages.update_one(
        {"slug": slug, "status": "published"},
        {"$inc": inc, "$set": set_doc},
    )
    if utm:
        # Daily-bucketed UTM tally — keeps metrics queryable without
        # blowing up the page document.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await db.marketing_page_visits.insert_one({
            "id": str(uuid.uuid4()),
            "slug": slug,
            "date": today,
            "utm": utm,
            "user_agent": payload.get("user_agent"),
            "at": _now(),
        })
    return {"tracked": True}
