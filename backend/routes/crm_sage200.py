"""
Sage 200 UK Integration Client
================================
Scaffolded integration layer for Sage 200 UK REST API.
Requires: client_id, client_secret, site_id, company_id from the user.

API Base URLs:
  - Standard: https://api.columbus.sage.com/uk/sage200/accounts/v1/
  - Professional: https://api.columbus.sage.com/uk/sage200extra/accounts/v1/

Auth: OAuth2 (Confidential Client) — access tokens expire after 480 mins.
Headers required: Authorization, X-Site, X-Company, Content-Type: application/json
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import uuid
import logging
import httpx

from utils.database import db
from routes.crm_auth import get_crm_user

router = APIRouter(prefix="/crm/sage200", tags=["CRM Sage 200"])
logger = logging.getLogger(__name__)

# Base URLs
SAGE_STANDARD_BASE = "https://api.columbus.sage.com/uk/sage200/accounts/v1"
SAGE_PROFESSIONAL_BASE = "https://api.columbus.sage.com/uk/sage200extra/accounts/v1"


async def get_sage_config():
    """Retrieve stored Sage 200 config from DB."""
    config = await db.crm_integrations.find_one({"type": "sage200"}, {"_id": 0})
    return config


async def get_sage_headers(config: dict) -> dict:
    """Build request headers with access token, X-Site, X-Company."""
    if not config or not config.get("access_token"):
        return None
    return {
        "Authorization": f"Bearer {config['access_token']}",
        "X-Site": config.get("site_id", ""),
        "X-Company": str(config.get("company_id", "")),
        "Content-Type": "application/json",
    }


def get_base_url(config: dict) -> str:
    edition = config.get("edition", "standard")
    return SAGE_PROFESSIONAL_BASE if edition == "professional" else SAGE_STANDARD_BASE


# ==================== CONFIGURATION ====================
@router.get("/config")
async def sage_config(user=Depends(get_crm_user)):
    """Get current Sage 200 integration configuration."""
    config = await get_sage_config()
    if not config:
        return {"configured": False}
    return {
        "configured": True,
        "edition": config.get("edition", "standard"),
        "site_id": config.get("site_id", ""),
        "company_id": config.get("company_id", ""),
        "company_name": config.get("company_name", ""),
        "last_sync": config.get("last_sync"),
        "connected": bool(config.get("access_token")),
    }


@router.post("/config")
async def update_sage_config(data: dict, user=Depends(get_crm_user)):
    """Store Sage 200 configuration (credentials provided by user)."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    config = {
        "type": "sage200",
        "edition": data.get("edition", "standard"),
        "client_id": data.get("client_id", ""),
        "client_secret": data.get("client_secret", ""),
        "site_id": data.get("site_id", ""),
        "company_id": data.get("company_id", ""),
        "company_name": data.get("company_name", ""),
        "access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", ""),
        "token_expires_at": data.get("token_expires_at"),
        "updated_by": user["id"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_sync": None,
    }
    await db.crm_integrations.update_one(
        {"type": "sage200"},
        {"$set": config},
        upsert=True
    )
    return {"status": "configured"}


# ==================== SYNC ENDPOINTS ====================
@router.get("/customers")
async def list_sage_customers(skip: int = 0, limit: int = 100, user=Depends(get_crm_user)):
    """Fetch customers from Sage 200."""
    config = await get_sage_config()
    headers = await get_sage_headers(config)
    if not headers:
        raise HTTPException(status_code=503, detail="Sage 200 not configured. Please add credentials in Settings.")

    base = get_base_url(config)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{base}/customers?$top={limit}&$skip={skip}", headers=headers)
            if resp.status_code == 401:
                raise HTTPException(status_code=401, detail="Sage token expired. Re-authenticate.")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Sage API error: {e.response.text[:200]}")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Sage connection failed: {str(e)}")


def _map_sage_customer_to_contact(cust: dict, user_id: str) -> dict:
    """Map a Sage 200 customer record to a CRM contact document."""
    contact_data = {
        "company_name": cust.get("name", ""),
        "sage_ref": cust.get("reference", ""),
        "sage_id": cust.get("id"),
        "phone": cust.get("telephone_subscriber_number", ""),
        "website": cust.get("website", ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    contacts = cust.get("contacts", [])
    if contacts:
        primary = contacts[0]
        contact_data["first_name"] = primary.get("first_name", "")
        contact_data["last_name"] = primary.get("last_name", "")
    return contact_data


async def _upsert_crm_contact(contact_data: dict, user_id: str) -> str:
    """Insert or update a CRM contact from Sage data. Returns 'created' or 'updated'."""
    ref = contact_data.get("sage_ref", "")
    existing = await db.crm_contacts.find_one({"sage_ref": ref})
    if existing:
        await db.crm_contacts.update_one({"sage_ref": ref}, {"$set": contact_data})
        return "updated"
    contact_data.update({
        "id": str(uuid.uuid4()), "email": "", "tags": ["sage200"], "source": "sage200",
        "lead_score": 0, "owner_id": user_id, "notes": "", "linkedin_url": "",
        "address": "", "title": "", "created_by": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.crm_contacts.insert_one(contact_data)
    return "created"


@router.post("/sync/customers")
async def sync_customers_to_crm(user=Depends(get_crm_user)):
    """Pull customers from Sage 200 and create/update CRM contacts."""
    config = await get_sage_config()
    headers = await get_sage_headers(config)
    if not headers:
        raise HTTPException(status_code=503, detail="Sage 200 not configured")

    base = get_base_url(config)
    created = 0
    updated = 0
    errors = []

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(f"{base}/customers?$top=500", headers=headers)
            resp.raise_for_status()
            customers = resp.json() if isinstance(resp.json(), list) else resp.json().get("value", [])

            for cust in customers:
                try:
                    contact_data = _map_sage_customer_to_contact(cust, user["id"])
                    result = await _upsert_crm_contact(contact_data, user["id"])
                    if result == "created":
                        created += 1
                    else:
                        updated += 1
                except Exception as e:
                    errors.append(str(e)[:100])

        await db.crm_integrations.update_one(
            {"type": "sage200"},
            {"$set": {"last_sync": datetime.now(timezone.utc).isoformat()}},
        )

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Sync failed: {str(e)}")

    return {"created": created, "updated": updated, "errors": errors[:10]}


@router.post("/sync/customers-to-sage")
async def push_contacts_to_sage(user=Depends(get_crm_user)):
    """Push CRM contacts (without sage_ref) to Sage 200 as new customers."""
    config = await get_sage_config()
    headers = await get_sage_headers(config)
    if not headers:
        raise HTTPException(status_code=503, detail="Sage 200 not configured")

    base = get_base_url(config)
    pushed = 0
    errors = []

    contacts = await db.crm_contacts.find({"sage_ref": {"$exists": False}}, {"_id": 0}).limit(100).to_list(100)

    async with httpx.AsyncClient(timeout=30) as client:
        for contact in contacts:
            try:
                payload = {
                    "reference": f"CRM-{contact['id'][:8].upper()}",
                    "name": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip() or contact.get('company_name', 'Unknown'),
                    "contacts": [{
                        "name": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
                        "first_name": contact.get("first_name", ""),
                        "last_name": contact.get("last_name", ""),
                        "is_default": True,
                    }]
                }
                resp = await client.post(f"{base}/customers", json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    sage_data = resp.json()
                    await db.crm_contacts.update_one(
                        {"id": contact["id"]},
                        {"$set": {"sage_ref": payload["reference"], "sage_id": sage_data.get("id")}}
                    )
                    pushed += 1
                else:
                    errors.append(f"{contact.get('first_name', '')} {contact.get('last_name', '')}: {resp.status_code}")
            except Exception as e:
                errors.append(str(e)[:100])

    return {"pushed": pushed, "errors": errors[:10]}
