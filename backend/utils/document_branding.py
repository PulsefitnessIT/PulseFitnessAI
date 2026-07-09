"""Per-tenant document branding profile.

Lets each organisation define its own logo / company details / bank details /
footer for generated PDFs (membership statements first, other doc types next),
so a tenant's documents never carry Pulse Fitness's hard-coded details.

The resolved "company" dict is fed straight into ``utils.pulse_doc_template``
(``pulse_header`` / ``pulse_footer_factory`` / ``make_pulse_doc``).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Editable text fields on the branding profile (whitelist for PUT).
TEXT_FIELDS = [
    "company_name", "tagline", "phone", "email", "web",
    "registered_office", "company_reg", "vat_reg",
    "bank_name", "bank_account_name", "bank_account_number", "bank_sort_code",
    "payment_terms", "footer_note", "accent_color",
]


def empty_profile() -> dict:
    return {k: "" for k in TEXT_FIELDS} | {
        "logo_file_id": "", "logo_storage_path": "", "logo_url": "",
    }


async def get_branding_profile(db, organization_id: str | None) -> dict | None:
    if not organization_id:
        return None
    return await db.org_document_branding.find_one(
        {"organization_id": organization_id}, {"_id": 0})


def _has_any_details(profile: dict) -> bool:
    return any((profile or {}).get(k) for k in TEXT_FIELDS) or bool((profile or {}).get("logo_storage_path"))


async def resolve_company(db, org: dict | None, *, with_logo: bool = True) -> dict:
    """Build a ``company`` dict for the PDF shell from the org's branding
    profile. Falls back to the org name so a tenant that hasn't configured
    branding still gets a clean, white-label (non-Pulse) document."""
    org = org or {}
    org_id = org.get("id")
    profile = await get_branding_profile(db, org_id) or {}

    company = {
        "name": profile.get("company_name") or org.get("name") or "Statement",
        "tagline": profile.get("tagline") or "",
        "phone": profile.get("phone") or "",
        "email": profile.get("email") or "",
        "web": profile.get("web") or "",
        "hashtag": "",
        "registered_office": profile.get("registered_office") or "",
        "company_reg": profile.get("company_reg") or "",
        "vat_reg": profile.get("vat_reg") or "",
        "bank_name": profile.get("bank_name") or "",
        "bank_account_name": profile.get("bank_account_name") or "",
        "bank_account_number": profile.get("bank_account_number") or "",
        "bank_sort_code": profile.get("bank_sort_code") or "",
        "payment_terms": profile.get("payment_terms") or "",
        "footer_note": profile.get("footer_note") or "",
        "accent_color": profile.get("accent_color") or "",
        "use_default_logo": False,
        "logo_bytes": None,
        "has_profile": _has_any_details(profile),
    }

    if with_logo and profile.get("logo_storage_path"):
        try:
            from utils.database import get_object
            data, _ct = get_object(profile["logo_storage_path"])
            company["logo_bytes"] = data
        except Exception as e:  # noqa: BLE001
            logger.warning("Logo fetch failed for org %s: %s", org_id, e)

    return company
