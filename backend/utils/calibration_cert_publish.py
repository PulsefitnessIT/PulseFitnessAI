"""Publish calibration certificates into the customer's Documents section.

When a service case that captured a calibration is OK'd by the service desk
operator (case transitions to ``closed``), we persist the calibration
certificate PDF into ``db.files`` under the CUSTOMER estate's own
organization so it shows up in that customer's Operations Portal →
Documents → Service Certificates.

Linkage: svc_cases.company_id → crm2_companies.linked_organization_id →
organizations.id of the customer estate. That estate org id is what the
customer's portal users carry as ``organization_id``, so files stamped with
it become visible to them the moment their portal accounts are created —
even if the certificate was generated before they were onboarded.

Idempotent per calibration record (source_calibration_id).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from utils.database import db, APP_NAME, put_object
from utils.calibration_certificate_pdf import build_calibration_certificate_pdf

logger = logging.getLogger(__name__)


async def _resolve_customer_org_id(case: dict) -> str | None:
    """Find the customer estate's own organization_id for a service case."""
    company_id = case.get("company_id")
    if not company_id:
        try:
            from utils.svc_crm_sync import find_company_id
            company_id = await find_company_id(
                case.get("organization_id"),
                name=case.get("customer_name"),
                email=case.get("customer_email"),
                postcode=case.get("site_postcode"),
            )
        except Exception:
            company_id = None
    if not company_id:
        return None
    company = await db.crm2_companies.find_one(
        {"id": company_id}, {"_id": 0, "linked_organization_id": 1})
    return (company or {}).get("linked_organization_id") or None


async def publish_calibration_certificate(case: dict) -> dict | None:
    """Persist a calibration certificate into the customer's Documents.

    Best-effort — callers should swallow exceptions. Returns the file doc
    on success, or None when there is nothing to publish."""
    if not case or not case.get("calibration_captured"):
        return None
    case_id = case.get("id")
    if not case_id:
        return None

    cal = await db.svc_case_calibrations.find_one(
        {"case_id": case_id}, {"_id": 0}, sort=[("created_at", -1)])
    if not cal:
        return None

    customer_org_id = await _resolve_customer_org_id(case)
    if not customer_org_id:
        logger.info("[calib-cert] case %s has no linked customer org — skipping publish", case_id)
        return None

    cal_key = cal.get("id") or cal.get("created_at") or case_id
    existing = await db.files.find_one({
        "organization_id": customer_org_id,
        "source": "calibration_certificate",
        "source_calibration_id": cal_key,
    })
    if existing:
        return existing

    pdf = build_calibration_certificate_pdf(
        case_ref=case.get("reference") or case_id,
        customer_name=case.get("customer_name") or "",
        site_name=case.get("site_name") or "",
        equipment_name=cal.get("equipment_name") or case.get("asset_name") or "",
        service_type=cal.get("service_type") or case.get("service_type") or "Calibration",
        readings=cal.get("readings") or [],
        overall_result=cal.get("overall_result") or "",
        engineer_name=cal.get("engineer_name") or "",
        issued_at=(cal.get("created_at") or "")[:16].replace("T", " "),
        notes=cal.get("notes") or "",
        signature_data_url=cal.get("signature") or None,
    )

    path = f"{APP_NAME}/certificates/{customer_org_id}/{uuid.uuid4()}.pdf"
    result = put_object(path, pdf, "application/pdf")
    ref = case.get("reference") or case_id
    fname = f"Calibration Certificate — {ref}.pdf"
    now = datetime.now(timezone.utc).isoformat()
    file_doc = {
        "id": str(uuid.uuid4()),
        "user_id": cal.get("engineer_id") or "",
        "organization_id": customer_org_id,
        "category": "certificates",
        "storage_path": result["path"],
        "download_url": result.get("url", result["path"]),
        "original_filename": fname,
        "content_type": "application/pdf",
        "size": result.get("size", len(pdf)),
        "content_hash": "",
        "source": "calibration_certificate",
        "source_case_id": case_id,
        "source_company_id": case.get("company_id") or "",
        "source_calibration_id": cal_key,
        "calibration_result": cal.get("overall_result") or "",
        "created_at": now,
    }
    await db.files.insert_one(file_doc)
    file_doc.pop("_id", None)
    file_doc["_created"] = True
    logger.info("[calib-cert] published cert for case %s → customer org %s", case_id, customer_org_id)
    return file_doc


async def backfill_calibration_certificates(operator_org_id: str | None = None) -> dict:
    """Publish any missing certificates for already-closed calibration cases.

    Lets historical certificates surface once a customer estate has been
    linked/onboarded. Idempotent and best-effort per case."""
    q: dict = {"calibration_captured": True, "status": {"$in": ["closed", "invoiced"]}}
    if operator_org_id:
        q["organization_id"] = operator_org_id
    published = 0
    scanned = 0
    async for case in db.svc_cases.find(q, {"_id": 0}):
        scanned += 1
        try:
            result = await publish_calibration_certificate(case)
            if result and result.get("_created"):
                published += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[calib-cert] backfill failed for case %s: %s", case.get("id"), exc)
    return {"scanned": scanned, "published": published}


__all__ = ["publish_calibration_certificate", "backfill_calibration_certificates"]
