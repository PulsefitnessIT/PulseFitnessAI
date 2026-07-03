"""Centralised MongoDB index bootstrap.

Run once at FastAPI startup to guarantee every high-volume, org-scoped
collection has the compound indexes we rely on. Adding these takes query
latency from O(N) collection scans down to O(log N) index seeks — the
single biggest cost/performance win available to a multi-tenant Mongo app.

Rules:
  * Every collection that stores tenant data has a
    ``(organization_id, <most-common-sort-key>)`` compound index.
  * We use ``create_index`` (idempotent — no-op if the index already exists).
  * We never create unique indexes here; uniqueness must be proven before
    promotion to avoid breaking existing data.
  * Each helper swallows its own errors so one missing collection can't
    stop the whole bootstrap.

Adding a new collection? Drop it into ``INDEXES`` below. The list is kept
narrowly focused on collections that appear in hot-path endpoints — ad-hoc
audit / log tables aren't worth the write penalty.
"""
from __future__ import annotations

import logging
from typing import Iterable, Sequence, Tuple

logger = logging.getLogger(__name__)

# (collection_name, [index_spec, …])
# index_spec = list of (field, direction) tuples; same shape as pymongo.
INDEXES: Sequence[Tuple[str, Sequence[Sequence[Tuple[str, int]]]]] = [
    # ── Ops / Equipment hot paths ───────────────────────────────────────
    ("check_sheet_completions", [
        [("organization_id", 1), ("created_at", -1)],
        [("equipment_id", 1), ("created_at", -1)],
    ]),
    ("fix_history", [
        [("equipment_id", 1), ("created_at", -1)],
        [("organization_id", 1), ("created_at", -1)],
    ]),
    ("spec_sheets", [
        [("organization_id", 1), ("manufacturer", 1)],
        [("product_level", 1), ("manufacturer", 1)],
    ]),
    ("service_requests", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
        [("supplier_id", 1), ("status", 1)],
    ]),
    ("commissioning_records", [
        [("organization_id", 1), ("created_at", -1)],
        [("equipment_id", 1), ("created_at", -1)],
    ]),
    ("ppm_schedules", [
        [("organization_id", 1), ("next_due_at", 1)],
    ]),
    ("ppm_tasks", [
        [("organization_id", 1), ("status", 1), ("due_at", 1)],
    ]),

    # ── Audit / observability ──────────────────────────────────────────
    ("audit_logs", [
        [("organization_id", 1), ("created_at", -1)],
        [("user_id", 1), ("created_at", -1)],
    ]),
    ("notifications", [
        [("user_id", 1), ("read", 1), ("created_at", -1)],
        [("organization_id", 1), ("created_at", -1)],
    ]),
    ("integration_logs", [
        [("organization_id", 1), ("timestamp", -1)],
    ]),

    # ── Marketing ──────────────────────────────────────────────────────
    ("marketing_messages", [
        [("organization_id", 1), ("created_at", -1)],
        [("campaign_id", 1), ("status", 1)],
        [("member_id", 1), ("created_at", -1)],
    ]),
    ("marketing_attributions", [
        [("organization_id", 1), ("created_at", -1)],
        [("campaign_id", 1), ("member_id", 1)],
    ]),
    ("marketing_campaigns", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
    ]),
    ("marketing_journeys", [
        [("organization_id", 1), ("status", 1)],
    ]),

    # ── Memberships / bookings ─────────────────────────────────────────
    ("memberships_bookings", [
        [("organization_id", 1), ("status", 1), ("starts_at", -1)],
        [("member_id", 1), ("status", 1)],
        [("occurrence_id", 1), ("status", 1)],
    ]),
    ("member_memberships", [
        [("organization_id", 1), ("status", 1)],
        [("member_id", 1), ("status", 1)],
    ]),
    ("class_occurrences", [
        [("organization_id", 1), ("starts_at", -1)],
        # (template_id, starts_at) already exists as a UNIQUE index — don't
        # try to recreate it; Mongo rejects the duplicate spec.
    ]),
    ("payment_transactions", [
        [("organization_id", 1), ("created_at", -1)],
        [("member_id", 1), ("created_at", -1)],
        [("status", 1), ("created_at", -1)],
    ]),

    # ── Staffing ───────────────────────────────────────────────────────
    ("staff_members", [
        [("organization_id", 1), ("active", 1)],
    ]),
    ("staff_shifts", [
        [("organization_id", 1), ("start_at", -1)],
        [("staff_id", 1), ("start_at", -1)],
    ]),
    ("staff_leave_requests", [
        [("organization_id", 1), ("status", 1), ("start_date", 1)],
        [("staff_id", 1), ("status", 1)],
    ]),
    ("staff_swap_requests", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
    ]),
    ("cover_requests", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
    ]),

    # ── CRM (legacy v1) ────────────────────────────────────────────────
    ("crm_companies", [
        [("organization_id", 1), ("created_at", -1)],
        [("owner_id", 1), ("created_at", -1)],
    ]),
    ("crm_contacts", [
        [("organization_id", 1), ("created_at", -1)],
        [("company_id", 1), ("created_at", -1)],
    ]),
    ("crm_deals", [
        [("organization_id", 1), ("stage", 1), ("created_at", -1)],
        [("pipeline_id", 1), ("stage", 1)],
        [("owner_id", 1), ("stage", 1)],
    ]),
    ("crm_activities", [
        [("organization_id", 1), ("created_at", -1)],
        [("deal_id", 1), ("created_at", -1)],
    ]),

    # ── CRM v2 (current — used by Master Admin CRM analytics + portal) ─
    ("crm2_companies", [
        [("organization_id", 1), ("updated_at", -1)],
        [("owner_id", 1), ("updated_at", -1)],
    ]),
    ("crm2_contacts", [
        [("organization_id", 1), ("created_at", -1)],
        [("company_id", 1), ("created_at", -1)],
        [("email", 1)],
    ]),
    ("crm2_opportunities", [
        # Most analytics queries filter stage + sort by created_at; risk-board
        # also probes (probability, value, close_date, updated_at).
        [("organization_id", 1), ("stage", 1), ("created_at", -1)],
        [("stage", 1), ("close_date", 1)],
        [("stage", 1), ("updated_at", -1)],
        [("owner_id", 1), ("stage", 1)],
    ]),
    ("crm2_activities", [
        [("organization_id", 1), ("created_at", -1)],
        [("type", 1), ("created_at", -1)],
        [("opportunity_id", 1), ("created_at", -1)],
    ]),
    ("crm2_quotes", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
        [("opportunity_id", 1), ("created_at", -1)],
    ]),
    ("crm2_cases", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
    ]),
    ("crm2_tenders", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
    ]),
    ("crm2_tender_questions", [
        [("tender_id", 1), ("created_at", -1)],
    ]),
    ("crm2_workflows", [
        [("organization_id", 1), ("active", 1)],
    ]),
    ("crm2_workflow_runs", [
        [("organization_id", 1), ("created_at", -1)],
        [("workflow_id", 1), ("created_at", -1)],
    ]),
    ("crm2_documents", [
        [("organization_id", 1), ("created_at", -1)],
    ]),
    ("crm2_assets", [
        [("organization_id", 1), ("created_at", -1)],
    ]),

    # ── Memberships / Operations hot paths (post-wipe gaps) ────────────
    ("members", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
        [("organization_id", 1), ("email", 1)],
        [("parent_member_id", 1)],
    ]),
    ("bookings", [
        [("organization_id", 1), ("starts_at", -1)],
        [("member_id", 1), ("starts_at", -1)],
        [("occurrence_id", 1), ("status", 1)],
    ]),
    ("class_bookings", [
        [("organization_id", 1), ("created_at", -1)],
        [("member_id", 1), ("created_at", -1)],
    ]),
    ("equipment", [
        [("organization_id", 1), ("site_id", 1)],
        [("organization_id", 1), ("status", 1)],
    ]),
    ("issues", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
        [("organization_id", 1), ("site_id", 1), ("status", 1)],
        [("equipment_id", 1), ("created_at", -1)],
    ]),
    ("sites", [
        [("organization_id", 1), ("created_at", 1)],
    ]),
    ("documents", [
        [("organization_id", 1), ("created_at", -1)],
    ]),
    ("form_submissions", [
        [("organization_id", 1), ("created_at", -1)],
        [("form_id", 1), ("created_at", -1)],
    ]),
    ("marketing_journey_runs", [
        [("organization_id", 1), ("created_at", -1)],
        [("journey_id", 1), ("status", 1)],
    ]),
    ("marketing_pages", [
        [("organization_id", 1), ("status", 1)],
    ]),
    ("org_billing_invoices", [
        [("organization_id", 1), ("created_at", -1)],
        [("organization_id", 1), ("status", 1)],
    ]),
    ("member_inbox", [
        [("organization_id", 1), ("created_at", -1)],
        [("member_id", 1), ("read", 1)],
    ]),
    ("invoices", [
        [("organization_id", 1), ("status", 1), ("issued_at", -1)],
        [("member_id", 1), ("issued_at", -1)],
    ]),
    ("payments", [
        [("organization_id", 1), ("created_at", -1)],
        [("member_id", 1), ("created_at", -1)],
    ]),

    # ── Support / trust ────────────────────────────────────────────────
    ("support_conversations", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
        [("user_id", 1), ("created_at", -1)],
    ]),
    ("supplier_cases", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
        [("supplier_id", 1), ("status", 1)],
    ]),

    # ── Iter 220ba — Pre-pen-test hot-collection sweep ─────────────────
    # SEO Autopilot (master-admin self-promo). Lookups are NOT
    # organization-scoped — the SEO blog is the single Pulse Fitness-owned
    # tenant. Status + updated_at and status + metrics.views cover the
    # top-performer + recent list endpoints.
    ("seo_articles", [
        [("status", 1), ("updated_at", -1)],
        [("status", 1), ("metrics.views", -1)],
        [("slug", 1)],
    ]),
    ("seo_article_view_snapshots", [
        [("article_id", 1), ("date", 1)],
        [("date", -1)],
    ]),
    ("seo_view_snapshots", [
        [("date", -1)],
    ]),
    # Growth Hub alerts (master-admin notification stream).
    ("growth_alerts", [
        [("created_at", -1)],
        [("status", 1), ("created_at", -1)],
    ]),
    # CRM journey enrolments (B2B + inbound demo funnel).
    ("marketing_journey_enrolments", [
        [("organization_id", 1), ("created_at", -1)],
        [("journey_id", 1), ("status", 1)],
        [("contact_id", 1), ("status", 1)],
    ]),
    # Marketing chat sessions (assistant + funnel analytics).
    ("mkt_chat_sessions", [
        [("organization_id", 1), ("created_at", -1)],
        [("created_at", -1)],
    ]),
    # Email send audit stream — sparklines + deliverability dashboards.
    ("email_send_events", [
        [("status", 1), ("created_at", -1)],
        [("organization_id", 1), ("created_at", -1)],
        [("recipient", 1), ("created_at", -1)],
    ]),
    # Service Ops case backbone (in addition to indexes set up in server.py).
    ("svc_cases", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
        [("organization_id", 1), ("updated_at", -1)],
    ]),
    ("svc_quotes", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
    ]),
    ("svc_invoices", [
        [("organization_id", 1), ("status", 1), ("created_at", -1)],
    ]),

    # Bulk-action audit events (F-10 Iter 220be) — one row per
    # affected resource id; mirrors the export_events shape so the
    # master-admin audit dashboard can fold both streams together.
    ("bulk_action_events", [
        [("action", 1), ("created_at", -1)],
        [("organization_id", 1), ("created_at", -1)],
        [("actor_id", 1), ("created_at", -1)],
        [("resource_id", 1)],
    ]),

    # Public widget access log (F-21 Iter 220be) — every public
    # widget config lookup writes a row so SOC can detect brute-force
    # token enumeration.
    ("widget_access_log", [
        [("ip", 1), ("ts", -1)],
        [("token", 1), ("ts", -1)],
        [("found", 1), ("ts", -1)],
    ]),
]


async def _ensure_one(db, collection: str, specs: Iterable[Sequence[Tuple[str, int]]]) -> int:
    """Create every spec on ``collection``; return how many were created."""
    from pymongo.errors import OperationFailure
    created = 0
    col = db[collection]
    for spec in specs:
        try:
            await col.create_index(list(spec), background=True)
            created += 1
        except OperationFailure as exc:
            # 85 IndexOptionsConflict / 86 IndexKeySpecsConflict — a
            # compatible index already exists under a different name or
            # options (common on Atlas across redeploys). Not an error.
            if exc.code in (85, 86):
                logger.info(
                    "Index on %s %s already satisfied by an existing index (code %s)",
                    collection, spec, exc.code,
                )
            else:
                logger.warning("Index create failed on %s %s: %s", collection, spec, exc)
        except Exception as exc:  # noqa: BLE001 — single failure must not stop bootstrap
            logger.warning("Index create failed on %s %s: %s", collection, spec, exc)
    return created


async def ensure_all_indexes(db) -> None:
    """Ensure every compound index in :data:`INDEXES` exists on ``db``.

    Idempotent; safe to run on every boot. Logs a summary so ops can verify
    the bootstrap ran cleanly.
    """
    total = 0
    for collection, specs in INDEXES:
        total += await _ensure_one(db, collection, specs)
    logger.info("ensure_all_indexes: attempted %d indexes across %d collections", total, len(INDEXES))
