"""Per-org Document Branding editor API (Operations → Settings).

Owners + managers configure the header/logo/footer/bank details used on
generated tenant documents (membership statements first). Logo upload reuses
the shared object-storage upload endpoint (POST /files/upload?category=branding)
on the frontend; this router persists the returned storage path/URL.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db
from utils.document_branding import TEXT_FIELDS, empty_profile, get_branding_profile
from utils.pulse_doc_template import PULSE

router = APIRouter()


def _can_edit(user: dict) -> bool:
    return bool(
        user.get("is_master_admin")
        or (user.get("role") or "").lower() in ("owner", "manager")
    )


@router.get("/document-branding")
async def get_document_branding(user: dict = Depends(get_current_user)):
    """Current org's document branding profile (empty template if unset),
    plus the Pulse defaults so the editor can show them as placeholders."""
    org_id = user.get("organization_id")
    profile = (await get_branding_profile(db, org_id)) or empty_profile()
    pulse_defaults = {
        "company_name": PULSE["name"], "tagline": PULSE["tagline"],
        "phone": PULSE["phone"], "email": PULSE["email"], "web": PULSE["web"],
        "registered_office": PULSE["registered_office"],
        "company_reg": PULSE["company_reg"], "vat_reg": PULSE["vat_reg"],
        "bank_name": PULSE["bank_name"], "bank_account_name": PULSE["bank_account_name"],
        "bank_account_number": PULSE["bank_account_number"],
        "bank_sort_code": PULSE["bank_sort_code"], "payment_terms": PULSE["payment_terms"],
    }
    return {"profile": profile, "placeholders": pulse_defaults, "can_edit": _can_edit(user)}


@router.put("/document-branding")
async def set_document_branding(body: dict = Body(...), user: dict = Depends(get_current_user)):
    """Owner / manager: save the org's document branding profile."""
    if not _can_edit(user):
        raise HTTPException(status_code=403, detail="Only owners or managers can edit document branding")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=404, detail="No organisation linked to this account")

    updates: dict = {}
    for field in TEXT_FIELDS:
        if field in body:
            updates[field] = (str(body[field]).strip() if body[field] is not None else "")
    # Logo (uploaded separately via /files/upload -> pass back the result).
    for logo_key in ("logo_file_id", "logo_storage_path", "logo_url"):
        if logo_key in body:
            updates[logo_key] = (str(body[logo_key]).strip() if body[logo_key] else "")

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    updates["organization_id"] = org_id
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updates["updated_by"] = user.get("email")
    await db.org_document_branding.update_one(
        {"organization_id": org_id}, {"$set": updates}, upsert=True)
    profile = await get_branding_profile(db, org_id)
    return {"success": True, "profile": profile}


@router.get("/document-branding/sample.pdf")
async def sample_document_pdf(user: dict = Depends(get_current_user)):
    """Render a sample membership statement using the org's current profile so
    the editor can offer a live 'download sample' preview."""
    from fastapi.responses import Response
    from utils.document_branding import resolve_company
    from routes.memberships.studio_billing import _render_invoice_pdf

    org = await db.organizations.find_one({"id": user.get("organization_id")}, {"_id": 0}) or {}
    company = await resolve_company(db, org)
    sample_invoice = {
        "id": "SAMPLE00-0000-0000", "member_email": "member@example.com",
        "total_pence": 4500,
        "lines": [
            {"description": "Junior Gymnastics — 4 classes", "amount_pence": 3200, "kind": "class"},
            {"description": "Competition costume levy", "amount_pence": 1300, "kind": "extra"},
        ],
        "attendees": [],
    }
    pdf = _render_invoice_pdf(
        org_name=company["name"], period_label="Sample month",
        invoice=sample_invoice, member_name="Alex Sample", company=company,
    )
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=sample-statement.pdf"})
