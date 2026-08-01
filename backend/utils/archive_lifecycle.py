"""
Archive lifecycle management (GDPR right-to-erasure).

Flow:
  1. Master Admin sets org.status = "archived"  ──▶ archived_at stamped.
  2. After RETENTION_DAYS − WARNING_LEAD_DAYS (358 days) a "7-day warning" email
     is sent to the primary admin contact, giving them a chance to restore.
  3. After RETENTION_DAYS (365 days) the org and all its scoped data are
     permanently hard-deleted (right to erasure).
  4. Master Admin can restore (status → active) or force an immediate
     hard-delete any time before the auto-sweep completes.

The sweep is invoked once per outer poller cycle (5 min by default) from
`utils/sicon_poller.py`. An admin-only `POST /api/master-admin/archive/sweep`
endpoint also exists to run it on demand.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from utils.database import db
from utils.email import send_email
import contextlib

logger = logging.getLogger(__name__)

RETENTION_DAYS = 365          # 1 year
WARNING_LEAD_DAYS = 7         # Email users 7 days before permanent deletion

# Statutory financial/tax records. Under GDPR Art. 17(3)(b) the right to
# erasure does NOT override a legal obligation to retain data — UK financial
# records must be kept ~6 years (HMRC). These collections are therefore
# RETAINED (skipped) on org hard-delete rather than purged.
FINANCIAL_RETENTION_COLLECTIONS = frozenset({
    "invoices", "payments", "stripe_charges", "payment_transactions",
    "purchase_orders", "po_defaults", "revenue_distributions",
    "reserve_transactions",
})

# Collections that are strictly org-scoped (field: organization_id).
# Deleting these on hard-delete implements the GDPR right-to-erasure.
ORG_SCOPED_COLLECTIONS = (
    "users", "invites", "api_keys",
    "equipment", "equipment_imports", "equipment_import_batches", "equipment_knowledge",
    "issues", "fix_history", "fault_templates",
    "audits", "audit_logs", "audit_logs_archive",
    "check_sheets", "check_sheet_completions", "custom_check_templates",
    "ppm_schedules", "ppm_tasks", "maintenance_tasks", "predictive_maintenance",
    "suppliers", "supplier_cases", "supplier_case_comments", "service_requests",
    "service_contracts", "purchase_orders", "po_defaults",
    "chat_history", "files", "documents", "gym_layouts", "spec_sheets",
    "commissioning_records", "risk_assessments", "consent_records",
    "notifications", "expiry_notifications", "weekly_digests",
    "sicon_config", "sicon_sync_queue", "sicon_audit_log",
    "capex_config", "capex_justifications", "financial_alerts", "financial_config",
    "operational_costs", "revenue_distributions", "reserve_transactions",
    "payment_transactions",
    # CRM side (same org)
    "sites", "crm_companies", "crm_contacts", "crm_deals", "crm_activities",
    "crm_meetings", "crm_messages", "crm_conversations", "crm_quotes",
    "crm_contracts", "crm_sites", "crm_pipelines", "crm_workflows",
    "crm_workflow_logs", "crm_documents", "crm_audit_log", "crm_integrations",
    "crm_users",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _days_until_deletion(archived_at: datetime | None) -> int | None:
    if not archived_at:
        return None
    deletion_at = archived_at + timedelta(days=RETENTION_DAYS)
    return max(0, (deletion_at - _now()).days)


async def list_archived_organizations() -> List[Dict[str, Any]]:
    """Return all archived orgs annotated with deletion countdown."""
    cursor = db.organizations.find({"status": "archived"}, {"_id": 0})
    result: List[Dict[str, Any]] = []
    async for org in cursor:
        archived_at = _parse_iso(org.get("archived_at"))
        result.append({
            **org,
            "days_until_deletion": _days_until_deletion(archived_at),
            "scheduled_deletion_at": (archived_at + timedelta(days=RETENTION_DAYS)).isoformat()
                if archived_at else None,
            "warning_sent_at": org.get("archive_warning_sent_at"),
        })
    # Sort soonest-to-delete first
    result.sort(key=lambda o: o.get("days_until_deletion") or 9999)
    return result


async def hard_delete_organization(org_id: str, actor_email: str) -> Dict[str, int]:
    """Permanently delete an org and all its scoped data. Irreversible."""
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    if not org:
        return {"deleted": 0}

    counts: Dict[str, int] = {}
    retained: List[str] = []
    for coll in ORG_SCOPED_COLLECTIONS:
        if coll in FINANCIAL_RETENTION_COLLECTIONS:
            # Retained for statutory financial retention (UK 6-year / HMRC).
            retained.append(coll)
            continue
        try:
            res = await db[coll].delete_many({"organization_id": org_id})
            if res.deleted_count:
                counts[coll] = res.deleted_count
        except Exception as e:
            logger.warning(f"[archive_hard_delete] {coll} delete failed for org={org_id}: {e}")

    # Delete the org record itself
    await db.organizations.delete_one({"id": org_id})
    counts["organizations"] = 1

    # Audit trail: keep a minimal record of the erasure event (GDPR accountability).
    try:
        await db.admin_activity_log.insert_one({
            "type": "org_hard_deleted",
            "organization_id": org_id,
            "organization_name_snapshot": org.get("name", "unknown"),
            "by": actor_email,
            "at": _now().isoformat(),
            "collections_purged": counts,
            "financial_records_retained": retained,
            "retention_basis": "GDPR Art. 17(3)(b) — legal obligation (UK financial records, ~6 years)",
        })
    except Exception as e:
        logger.warning(f"[archive_hard_delete] audit insert failed: {e}")

    logger.info(f"[archive_hard_delete] org={org_id} by={actor_email} counts={counts} retained_financial={retained}")
    return counts


async def restore_organization(org_id: str, actor_email: str) -> bool:
    """Bring an archived org back to active status."""
    result = await db.organizations.update_one(
        {"id": org_id, "status": "archived"},
        {"$set": {
            "status": "active",
            "status_updated_at": _now().isoformat(),
            "archived_at": None,
            "archived_by": None,
            "archive_warning_sent_at": None,
        }},
    )
    if result.modified_count:
        with contextlib.suppress(Exception):
            await db.admin_activity_log.insert_one({
                "type": "org_restored_from_archive",
                "organization_id": org_id,
                "by": actor_email,
                "at": _now().isoformat(),
            })
        return True
    return False


async def _send_pre_delete_warning(org: Dict[str, Any]) -> bool:
    """Send a single 7-day warning email to the org's primary admin contact."""
    recipient = org.get("primary_contact_email") or org.get("admin_email") or org.get("owner_email")
    if not recipient:
        return False

    days_left = _days_until_deletion(_parse_iso(org.get("archived_at"))) or 0
    subject = f"[Action required] {org.get('name', 'Your gym')} will be permanently deleted in {days_left} day(s)"
    html = f"""
      <div style="font-family: -apple-system, Segoe UI, sans-serif; max-width: 560px; margin: 0 auto;">
        <h2 style="color: #0055FF;">Your Pulse Fitness workspace is scheduled for permanent deletion</h2>
        <p>Hi team,</p>
        <p>Your gym <strong>{org.get('name', '')}</strong> was archived on
           <strong>{org.get('archived_at', 'a previous date')[:10]}</strong>.</p>
        <p>Under our data retention policy, archived workspaces are permanently deleted
           after {RETENTION_DAYS} days (GDPR right-to-erasure).
           <strong>{org.get('name', 'Your gym')}</strong> is now scheduled for permanent
           deletion in <strong>{days_left} day(s)</strong>.</p>
        <p><strong>If you want to keep your data</strong>, ask your Pulse Fitness administrator
           to restore the workspace from the Archive page before the deadline.</p>
        <p>Once deleted, <em>all equipment, fault history, users, and documents</em> will be
           permanently and irrecoverably removed.</p>
        <p style="margin-top: 32px; color: #71717a; font-size: 12px;">
          This is an automated compliance notification from Pulse Fitness AI.
        </p>
      </div>
    """
    try:
        await send_email(recipient, subject, html)
        return True
    except Exception as e:
        logger.warning(f"[archive_warning] send to {recipient} failed: {e}")
        return False


async def run_archive_lifecycle_once() -> Dict[str, int]:
    """Send warning emails and hard-delete orgs past the retention window.

    Idempotent — safe to run repeatedly. Called every outer poll cycle from
    `utils/sicon_poller.py` and via `POST /api/master-admin/archive/sweep`.
    """
    counts = {"warnings_sent": 0, "deleted": 0, "scanned": 0}
    cursor = db.organizations.find({"status": "archived"}, {"_id": 0})
    async for org in cursor:
        counts["scanned"] += 1
        archived_at = _parse_iso(org.get("archived_at"))
        if not archived_at:
            # Legacy archived row without timestamp — stamp it now so future sweeps work.
            await db.organizations.update_one(
                {"id": org["id"]},
                {"$set": {"archived_at": _now().isoformat()}},
            )
            continue

        age = _now() - archived_at
        days_left = RETENTION_DAYS - age.days

        if days_left <= 0:
            await hard_delete_organization(org["id"], "system@archive-sweep")
            counts["deleted"] += 1
            continue

        if days_left <= WARNING_LEAD_DAYS and not org.get("archive_warning_sent_at"):
            sent = await _send_pre_delete_warning(org)
            if sent:
                await db.organizations.update_one(
                    {"id": org["id"]},
                    {"$set": {"archive_warning_sent_at": _now().isoformat()}},
                )
                counts["warnings_sent"] += 1

    if any(v > 0 for k, v in counts.items() if k != "scanned"):
        logger.info(f"[archive_lifecycle] counts={counts}")
    return counts
