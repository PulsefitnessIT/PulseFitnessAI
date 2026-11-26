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


SAGE_PAGE = 500
SAGE_MAX_RECORDS = 50000  # same documented capacity as customer account files; never silently truncated


def sage_api_customer_values(c: dict) -> dict:
    """Map a Sage 200 API customer onto the Sage Customer Accounts template fields so the same parser, validation,
    matching and review apply. Field names follow the Sage 200 API customer resource; requires live verification."""
    def g(*keys):
        for k in keys:
            v = c.get(k)
            if v not in (None, ""):
                return v
        return ""
    contacts = c.get("contacts") or []
    p = contacts[0] if contacts and isinstance(contacts[0], dict) else {}
    addr = c.get("main_address") if isinstance(c.get("main_address"), dict) else c
    return {
        "AccountNumber": g("reference"), "AccountName": g("name"), "ShortName": g("short_name"),
        "AccountBalance": g("balance"), "CreditLimit": g("credit_limit"),
        "CurrencyISOCode": (c.get("currency") or {}).get("code", "") if isinstance(c.get("currency"), dict) else g("currency_code"),
        "AccountIsOnHold": "1" if c.get("on_hold") else "0",
        "ActiveStatus": "1" if str(g("account_status_type")).lower() in ("hidden", "1") else "0",
        "AddressLine1": addr.get("address_1", ""), "AddressLine2": addr.get("address_2", ""),
        "AddressLine3": addr.get("address_3", ""), "AddressLine4": addr.get("address_4", ""),
        "City": addr.get("city", ""), "County": addr.get("county", ""), "PostCode": addr.get("postcode", ""),
        "CountryCode": g("country_code"),
        "MainTelephoneCountryCode": g("telephone_country_code"), "MainTelephoneAreaCode": g("telephone_area_code"),
        "MainTelephoneSubscriberNumber": g("telephone_subscriber_number"), "MainWebsite": g("website"),
        "ContactFirstName": p.get("first_name", ""), "ContactLastName": p.get("last_name", ""),
        "ContactEmail": p.get("email", "") or g("email"),
    }


async def fetch_all_sage_customers(base: str, headers: dict) -> list:
    """Every page ($top/$skip) — stops on a short page, fails loudly above the documented capacity."""
    out: list = []
    skip = 0
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            resp = await client.get(f"{base}/customers", params={"$top": SAGE_PAGE, "$skip": skip}, headers=headers)
            resp.raise_for_status()
            body = resp.json()
            page = body if isinstance(body, list) else body.get("value", [])
            out.extend(page)
            if len(out) > SAGE_MAX_RECORDS:
                raise ValueError(f"Sage returned more than {SAGE_MAX_RECORDS} customers — split the import by company")
            if len(page) < SAGE_PAGE:
                return out
            skip += SAGE_PAGE


@router.post("/sync/customers")
async def sync_customers_to_crm(source_company: str = "", user=Depends(get_crm_user)):
    """Pull every Sage 200 customer into an Import Centre job for review. Nothing is written to customers until a
    Pulse admin approves it (same matching, LITE-only provisioning, approval and Undo as spreadsheet imports)."""
    if not (user.get("is_master_admin") or user.get("is_pulse_admin")):
        raise HTTPException(status_code=403, detail="Only Pulse admins can import Sage customers")
    if not source_company.strip():
        raise HTTPException(status_code=400, detail="Choose the Sage company these customers belong to")
    config = await get_sage_config()
    headers = await get_sage_headers(config)
    if not headers:
        raise HTTPException(status_code=503, detail="Sage 200 not configured")
    try:
        customers = await fetch_all_sage_customers(get_base_url(config), headers)
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Sync failed: {str(e)[:200]}")
    from routes import customer_account_import as CAI
    records = [{"row": i + 1, "role": "record", "values": sage_api_customer_values(c)} for i, c in enumerate(customers)]
    job = await CAI.create_job("sage_accounts", records, user, source_company=source_company,
                               filename=f"Sage 200 API ({len(records)} customers)", file_type="api",
                               checksum=f"sage-api-{datetime.now(timezone.utc).isoformat()}", size=len(records),
                               detection={"format": "sage_accounts", "source": "sage_200_api", "records": len(records)},
                               source="sage_200_api")
    await db.crm_integrations.update_one({"type": "sage200"}, {"$set": {"last_sync": datetime.now(timezone.utc).isoformat(),
                                                                        "last_import_job_id": job["id"]}})
    return {"job_id": job["id"], "records": len(records), "status": job.get("status"),
            "message": "Customers retrieved — review and approve them in Onboarding → Import Centre"}


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
