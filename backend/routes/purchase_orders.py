from fastapi import APIRouter, HTTPException, Depends
from utils.security_plus import safe_regex_exact
from fastapi.responses import Response
from datetime import datetime, timezone
from typing import Dict, Any
import uuid
import logging
import os

from utils.database import db
from utils.auth import get_current_user, get_organization_filter
from utils.email import send_email

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/purchase-orders")
async def create_purchase_order(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    custom_po = data.get('po_number', '').strip()
    po_doc = {
        "id": str(uuid.uuid4()),
        "po_number": custom_po if custom_po else f"PO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}",
        "user_id": user['id'],
        "organization_id": user.get('organization_id'),
        "issue_id": data.get('issue_id'),
        "supplier_name": data.get('supplier_name', ''),
        "supplier_email": data.get('supplier_email', ''),
        "delivery_address": data.get('delivery_address', ''),
        "items": data.get('items', []),
        "subtotal": sum(float(i.get('quantity', 0)) * float(i.get('unit_price', 0)) for i in data.get('items', [])),
        "vat_rate": data.get('vat_rate', 20),
        "notes": data.get('notes', ''),
        "status": "draft",
        "created_by": user.get('full_name'),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    po_doc['vat_amount'] = round(po_doc['subtotal'] * po_doc['vat_rate'] / 100, 2)
    po_doc['total'] = round(po_doc['subtotal'] + po_doc['vat_amount'], 2)

    await db.purchase_orders.insert_one(po_doc)
    po_doc.pop('_id', None)
    return po_doc


@router.get("/purchase-orders")
async def get_purchase_orders(issue_id: str = None, user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    query = {**org_filter}
    if issue_id:
        query["issue_id"] = issue_id
    pos = await db.purchase_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"purchase_orders": pos}


def _resolve_po_email_context(po: dict, user: dict, org: dict | None) -> dict:
    """Resolve branding, recipient, and test mode for PO email."""
    branding = (org or {}).get('branding', {}) or {}
    brand_color = branding.get('primary_color', '#0055FF')
    company_name = branding.get('company_name') or (org.get('name', 'GymAxis AI') if org else 'GymAxis AI')

    sender = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
    test_mode = 'resend.dev' in sender
    intended_recipient = po.get('supplier_email', '')
    test_recipient = os.environ.get('TEST_RECIPIENT_EMAIL', '')
    actual_recipient = (test_recipient or user['email']) if test_mode else (intended_recipient or user['email'])

    return {
        "brand_color": brand_color, "company_name": company_name,
        "test_mode": test_mode, "intended_recipient": intended_recipient,
        "actual_recipient": actual_recipient,
    }


def _build_po_email_html(po: dict, ctx: dict) -> str:
    """Build the HTML email body for a purchase order."""
    brand_color, company_name = ctx["brand_color"], ctx["company_name"]
    items_html = "".join(
        f"<tr><td style='padding:8px;border:1px solid #ddd;'>{i.get('description','')}</td>"
        f"<td style='padding:8px;border:1px solid #ddd;text-align:center;'>{i.get('quantity','')}</td>"
        f"<td style='padding:8px;border:1px solid #ddd;text-align:right;'>£{float(i.get('unit_price',0)):.2f}</td>"
        f"<td style='padding:8px;border:1px solid #ddd;text-align:right;'>£{float(i.get('quantity',0))*float(i.get('unit_price',0)):.2f}</td></tr>"
        for i in po.get('items', [])
    )
    test_notice = f'<div style="background:#FFF3CD;border:1px solid #FFC107;padding:12px;margin-bottom:16px;border-radius:6px;font-size:13px;"><strong>Test Mode:</strong> This PO would be sent to <strong>{ctx["intended_recipient"] or "no email"}</strong> ({po["supplier_name"]}) in production.</div>' if ctx["test_mode"] else ''

    return f"""<div style="font-family:Arial;max-width:700px;margin:0 auto;border:1px solid #e5e5e5;border-radius:8px;overflow:hidden;">
    <div style="background:{brand_color};padding:24px;"><h2 style="color:white;margin:0;">{company_name}</h2><p style="color:rgba(255,255,255,0.8);margin:4px 0 0;">Purchase Order: {po['po_number']}</p></div>
    <div style="padding:24px;">
        {test_notice}
        <table style="width:100%;margin-bottom:16px;">
        <tr><td style="padding:4px;color:#666;">To:</td><td style="padding:4px;font-weight:bold;">{po['supplier_name']}</td></tr>
        <tr><td style="padding:4px;color:#666;">From:</td><td style="padding:4px;">{po.get('created_by','')} — {company_name}</td></tr>
        <tr><td style="padding:4px;color:#666;">Date:</td><td style="padding:4px;">{po['created_at'][:10]}</td></tr>
        {f"<tr><td style='padding:4px;color:#666;'>Delivery:</td><td style='padding:4px;'>{po['delivery_address']}</td></tr>" if po.get('delivery_address') else ''}
        </table>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
            <thead><tr style="background:{brand_color};color:white;"><th style="padding:10px;text-align:left;">Description</th><th style="padding:10px;">Qty</th><th style="padding:10px;">Unit Price</th><th style="padding:10px;">Total</th></tr></thead>
            <tbody>{items_html}</tbody>
        </table>
        <div style="text-align:right;padding:12px;background:#f9f9f9;border-radius:8px;">
            <p style="margin:4px 0;">Subtotal: £{po['subtotal']:.2f}</p>
            <p style="margin:4px 0;">VAT ({po['vat_rate']}%): £{po['vat_amount']:.2f}</p>
            <p style="font-size:20px;font-weight:bold;margin:8px 0 0;">Total: £{po['total']:.2f}</p>
        </div>
        {f"<p style='margin-top:16px;'><strong>Notes:</strong> {po['notes']}</p>" if po.get('notes') else ''}
    </div>
    <div style="background:#f5f5f5;padding:16px;text-align:center;font-size:12px;color:#999;">Powered by {company_name} via GymAxis AI</div>
    </div>"""


@router.post("/purchase-orders/{po_id}/send")
async def send_purchase_order(po_id: str, user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)
    po = await db.purchase_orders.find_one({"id": po_id, **org_filter}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    org = await db.organizations.find_one({"id": user.get('organization_id')}, {"_id": 0}) if user.get('organization_id') else None
    ctx = _resolve_po_email_context(po, user, org)
    html = _build_po_email_html(po, ctx)

    sent = await send_email(ctx["actual_recipient"], f"Purchase Order {po['po_number']} — {ctx['company_name']}", html)
    await db.purchase_orders.update_one({"id": po_id}, {"$set": {"status": "sent", "sent_at": datetime.now(timezone.utc).isoformat()}})
    return {"sent": sent, "message": "Purchase order sent" if sent else "Email not configured - PO saved as sent"}


def _build_po_items_html(items: list) -> tuple[str, float]:
    """Build HTML rows and subtotal from PO line items."""
    rows, subtotal = "", 0.0
    for item in items:
        qty, price = float(item.get('quantity', 0)), float(item.get('unit_price', 0))
        total = qty * price
        subtotal += total
        rows += f"<tr><td>{item.get('description','')}</td><td class='center'>{int(qty)}</td><td class='right'>£{price:.2f}</td><td class='right'>£{total:.2f}</td></tr>"
    return rows, subtotal


def _render_po_html(po: dict, org_name: str, org_logo: str | None, items_html: str, subtotal: float) -> str:
    """Render the full PO HTML page."""
    vat, total = subtotal * 0.2, subtotal * 1.2
    logo = f'<img src="{org_logo}" style="height:50px;margin-right:15px;" />' if org_logo else ""
    notes = f'<div class="notes"><strong>Notes:</strong> {po.get("notes","")}</div>' if po.get('notes') else ''
    return f"""<!DOCTYPE html><html><head><title>PO {po.get('po_number','')}</title>
    <style>body{{font-family:Arial;color:#333;max-width:800px;margin:0 auto;padding:30px;}}.header{{display:flex;justify-content:space-between;align-items:start;border-bottom:3px solid #0055FF;padding-bottom:15px;margin-bottom:20px;}}.header-left{{display:flex;align-items:center;}}.company{{font-size:22px;font-weight:bold;color:#0055FF;}}.po-number{{font-size:14px;color:#666;}}.meta{{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-bottom:25px;}}.meta-box{{background:#f9f9f9;padding:12px;border-radius:6px;}}.meta-box strong{{display:block;font-size:11px;text-transform:uppercase;color:#999;margin-bottom:4px;}}table{{width:100%;border-collapse:collapse;margin-bottom:20px;}}th{{background:#0055FF;color:white;text-align:left;padding:10px 12px;font-size:12px;}}td{{padding:10px 12px;border-bottom:1px solid #eee;font-size:13px;}}.center{{text-align:center;}}.right{{text-align:right;}}.totals{{text-align:right;}}.totals p{{margin:4px 0;font-size:14px;}}.totals .total{{font-size:20px;font-weight:bold;color:#0055FF;}}.notes{{background:#f9f9f9;padding:12px;border-radius:6px;margin-top:15px;font-size:13px;}}</style></head><body>
    <div class="header"><div class="header-left">{logo}<div><div class="company">{org_name}</div><div class="po-number">Purchase Order: {po.get('po_number','')}</div></div></div><div style="text-align:right;font-size:13px;color:#666;">Date: {po.get('created_at','')[:10]}<br/>Status: {po.get('status','draft').upper()}</div></div>
    <div class="meta"><div class="meta-box"><strong>Supplier</strong>{po.get('supplier_name','N/A')}<br/>{po.get('supplier_email','')}</div><div class="meta-box"><strong>Delivery Address</strong>{po.get('delivery_address','N/A')}</div></div>
    <table><thead><tr><th>Description</th><th class="center">Qty</th><th class="right">Unit Price</th><th class="right">Total</th></tr></thead><tbody>{items_html}</tbody></table>
    <div class="totals"><p>Subtotal: £{subtotal:.2f}</p><p>VAT (20%): £{vat:.2f}</p><p class="total">Total: £{total:.2f}</p></div>{notes}</body></html>"""


@router.get("/purchase-orders/{po_id}/pdf")
async def get_po_pdf_view(po_id: str, token: str = None, user: dict = Depends(get_current_user)):
    po = await db.purchase_orders.find_one({"id": po_id, **get_organization_filter(user)}, {"_id": 0})
    if not po:
        raise HTTPException(status_code=404, detail="PO not found")
    org = await db.organizations.find_one({"id": user.get('organization_id')}, {"_id": 0}) if user.get('organization_id') else None
    items_html, subtotal = _build_po_items_html(po.get('items', []))
    return Response(content=_render_po_html(po, (org or {}).get('name', 'GymAxis AI'), (org or {}).get('logo_url'), items_html, subtotal), media_type="text/html")


# --- Default PO Prices Settings ---

@router.get("/purchase-orders/supplier-lookup")
async def lookup_supplier_for_po(equipment_serial: str = "", supplier_name: str = "", user: dict = Depends(get_current_user)):
    """Look up supplier email and pricing for PO auto-population based on equipment or supplier name"""
    org_id = user.get('organization_id')
    result = {"supplier_name": supplier_name, "supplier_email": "", "pricing": {}}

    # If we have a serial number, find the equipment's service_provider or manufacturer
    if equipment_serial and org_id:
        equip = await db.equipment.find_one(
            {"serial_number": equipment_serial, "organization_id": org_id},
            {"_id": 0, "service_provider": 1, "manufacturer": 1}
        )
        if equip:
            result["supplier_name"] = equip.get("service_provider") or equip.get("manufacturer") or supplier_name

    # Look up the supplier from suppliers collection (including pricing fields)
    if result["supplier_name"] and org_id:
        supplier_doc = await db.suppliers.find_one(
            {"organization_id": org_id, "name": safe_regex_exact(result['supplier_name'])},
            {"_id": 0}
        )
        if supplier_doc:
            result["supplier_email"] = supplier_doc.get("email", "")
            result["supplier_name"] = supplier_doc.get("name", result["supplier_name"])
            result["pricing"] = {
                "callout_fee": supplier_doc.get("callout_fee", 0),
                "labour_rate_per_hour": supplier_doc.get("labour_rate_per_hour", 0),
                "mileage_rate": supplier_doc.get("mileage_rate", 0),
                "parts_markup_pct": supplier_doc.get("parts_markup_pct", 0),
                "custom_items": supplier_doc.get("custom_items", [])
            }

    return result


@router.get("/settings/po-defaults")
async def get_po_defaults(user: dict = Depends(get_current_user)):
    org_id = user.get('organization_id')
    if not org_id:
        return {"defaults": {}}
    doc = await db.po_defaults.find_one({"organization_id": org_id}, {"_id": 0})
    return {"defaults": doc or {}}


@router.put("/settings/po-defaults")
async def save_po_defaults(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    org_id = user.get('organization_id')
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization")
    doc = {
        "organization_id": org_id,
        "callout_fee": float(data.get("callout_fee", 0)),
        "labour_rate_per_hour": float(data.get("labour_rate_per_hour", 0)),
        "mileage_rate": float(data.get("mileage_rate", 0)),
        "parts_markup_pct": float(data.get("parts_markup_pct", 0)),
        "custom_items": data.get("custom_items", []),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user.get("full_name")
    }
    await db.po_defaults.update_one(
        {"organization_id": org_id},
        {"$set": doc},
        upsert=True
    )
    return {"message": "Default prices saved", "defaults": doc}


# --- Org details for PO auto-fill ---

@router.get("/settings/org-details")
async def get_org_details_for_po(user: dict = Depends(get_current_user)):
    org_id = user.get('organization_id')
    if not org_id:
        return {}
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        return {}
    return {
        "name": org.get("name", ""),
        "address": org.get("address", ""),
        "phone": org.get("phone", ""),
        "email": org.get("email", ""),
        "contact_person": org.get("contact_person", ""),
    }


@router.put("/settings/org-details")
async def save_org_details(data: Dict[str, Any], user: dict = Depends(get_current_user)):
    org_id = user.get('organization_id')
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization")
    update = {}
    for field in ["address", "phone", "email", "contact_person"]:
        if field in data:
            update[field] = data[field]
    if update:
        await db.organizations.update_one({"id": org_id}, {"$set": update})
    return {"message": "Organization details saved"}


# --- Supplier request info email ---

async def _resolve_supplier_contact(supplier_name: str, org_id: str | None) -> str:
    """Look up supplier email from the suppliers collection."""
    if not supplier_name or not org_id:
        return ""
    doc = await db.suppliers.find_one(
        {"organization_id": org_id, "name": safe_regex_exact(supplier_name)},
        {"_id": 0, "email": 1},
    )
    return (doc or {}).get("email", "")


def _render_contact_html(issue: dict, message: str, company_name: str, brand_color: str, test_notice: str, supplier_name: str) -> str:
    """Render supplier contact email."""
    return f"""<div style="font-family:Arial;max-width:600px;margin:0 auto;border:1px solid #e5e5e5;border-radius:8px;overflow:hidden;">
    <div style="background:{brand_color};padding:24px;text-align:center;"><h2 style="color:white;margin:0;">{company_name}</h2><p style="color:rgba(255,255,255,0.8);margin:4px 0 0;font-size:14px;">Service Request Communication</p></div>
    <div style="padding:24px;">{test_notice}<p>Dear {supplier_name},</p><p><strong>{company_name}</strong> has a question regarding:</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;"><tr style="border-bottom:1px solid #eee;"><td style="padding:10px;color:#666;width:140px;">Equipment</td><td style="padding:10px;font-weight:bold;">{issue.get('machine_type','N/A')}</td></tr><tr style="border-bottom:1px solid #eee;"><td style="padding:10px;color:#666;">Serial</td><td style="padding:10px;font-weight:bold;">{issue.get('serial_number','N/A')}</td></tr><tr style="border-bottom:1px solid #eee;"><td style="padding:10px;color:#666;">Severity</td><td style="padding:10px;">{issue.get('severity','N/A').upper()}</td></tr><tr style="border-bottom:1px solid #eee;"><td style="padding:10px;color:#666;">Issue</td><td style="padding:10px;">{issue.get('issue_description','N/A')[:200]}</td></tr></table>
    <div style="background:#f0f7ff;padding:16px;border-radius:8px;margin:16px 0;"><h4 style="margin:0 0 8px;">Message:</h4><p style="margin:0;color:#333;">{message}</p></div>
    <p style="color:#666;font-size:13px;">Please reply to this email.</p></div>
    <div style="background:#f5f5f5;padding:16px;text-align:center;font-size:12px;color:#999;">Powered by {company_name} via GymAxis AI</div></div>"""


async def _resolve_site_name(data: dict, user: dict, org: dict | None) -> str:
    """Resolve the site name for supplier communication."""
    site_name = data.get("site_name", "")
    if not site_name:
        sites = await db.sites.find({"organization_id": user.get("organization_id")}, {"_id": 0, "name": 1}).to_list(1)
        if sites:
            site_name = sites[0].get("name", "")
    if not site_name:
        branding = (org or {}).get('branding', {}) or {}
        site_name = branding.get('company_name') or (org or {}).get('name', 'Site')
    return site_name


async def _refresh_existing_supplier_case(existing: dict, supplier_email: str,
                                         site_name: str, user: dict) -> dict:
    """Patch an existing supplier case with any missing contact/org info."""
    updates = {}
    if supplier_email and not existing.get("supplier_email"):
        updates["supplier_email"] = supplier_email
    if not existing.get("site_contact_email"):
        updates["site_contact_email"] = user.get("email", "")
    org_id = user.get('organization_id')
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) if org_id else None
    org_name = (org or {}).get("name")
    if not existing.get("organization_name") or existing.get("organization_name") == org_name:
        updates["organization_name"] = site_name
    if updates:
        await db.supplier_cases.update_one({"id": existing["id"]}, {"$set": updates})
        existing.update(updates)
    return existing


async def _ensure_supplier_case(issue_id: str, supplier_name: str, supplier_email: str,
                                site_name: str, user: dict) -> dict:
    """Return existing supplier case or create a new one."""
    existing = await db.supplier_cases.find_one({"issue_id": issue_id}, {"_id": 0})
    if existing:
        return await _refresh_existing_supplier_case(existing, supplier_email, site_name, user)

    from routes.supplier_portal import create_supplier_case, FRONTEND_URL
    base_url = FRONTEND_URL or os.environ.get('REACT_APP_BACKEND_URL', '')
    await create_supplier_case(
        issue_id=issue_id, supplier_name=supplier_name,
        supplier_email=supplier_email, organization_name=site_name,
        base_url=base_url.replace('/api', ''),
    )
    await db.supplier_cases.update_one({"issue_id": issue_id}, {"$set": {
        "site_contact_email": user.get("email", ""),
    }})
    return await db.supplier_cases.find_one({"issue_id": issue_id}, {"_id": 0})


@router.post("/issues/{issue_id}/contact-supplier")
async def contact_supplier(issue_id: str, data: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Gym user contacts supplier about a fault — auto-creates supplier case and sends via portal system."""
    issue = await db.issues.find_one({"id": issue_id, **get_organization_filter(user)}, {"_id": 0})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    org = await db.organizations.find_one({"id": user.get('organization_id')}, {"_id": 0}) if user.get('organization_id') else None
    site_name = await _resolve_site_name(data, user, org)

    supplier_name = issue.get("supplier", "Supplier")
    supplier_email = data.get("supplier_email", "") or await _resolve_supplier_contact(supplier_name, user.get('organization_id'))
    message = data.get("message", "We need more information about this fault.")

    case = await _ensure_supplier_case(issue_id, supplier_name, supplier_email, site_name, user)

    # Post as gym comment
    from routes.supplier_portal import _send_comment_notification
    comment = {
        "id": str(uuid.uuid4()), "case_id": case["id"],
        "author_name": user.get("full_name", "Site Staff"), "author_role": "gym",
        "message": message, "attachments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.supplier_case_comments.insert_one(comment)

    email_sent = False
    if case.get("supplier_email"):
        await _send_comment_notification(case, comment, to_supplier=True)
        email_sent = True

    return {
        "sent": True, "email_sent": email_sent,
        "supplier_case_token": case.get("token"),
        "needs_supplier_email": not case.get("supplier_email"),
        "message": f"Message sent to {supplier_name}" + ("" if email_sent else " (no supplier email — share the portal link)"),
    }
