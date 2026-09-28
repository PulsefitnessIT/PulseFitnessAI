"""MongoDB index creation invoked at FastAPI startup.

Extracted from ``server.py`` in iter 220dy. Each ``create_index``
call is idempotent — MongoDB no-ops on identical existing
indexes — so the function is safe to run on every boot.

Organised by tier:

  * Tier 1 (core): users, equipment, issues, files, etc.
  * Tier 2 (Apr 2026): performance backfill from `find().sort()` audit.
  * Tier 3 (Feb 2026): every collection with >0 organization_id
    queries that was missing a covering index.
  * Tier 4 (iter 216h170): hottest filter pairs from the structured
    query-pattern audit.

Plus per-module ensure-index calls re-exported from their own
routes (Trust events, MFA, SSO, partners, diary, notifications,
work-report fields, etc).
"""
from __future__ import annotations

import logging

from utils.database import db

logger = logging.getLogger(__name__)


async def create_indexes() -> None:
    """Create MongoDB indexes for performance.

    Idempotent — safe to run on every boot.
    """
    # Core indexes
    await db.issues.create_index([("organization_id", 1), ("created_at", -1)])
    await db.issues.create_index([("organization_id", 1), ("status", 1)])
    await db.issues.create_index("user_id")
    await db.equipment.create_index([("organization_id", 1)])
    await db.equipment.create_index("serial_number")
    await db.files.create_index([("organization_id", 1), ("category", 1)])
    await db.files.create_index([("content_hash", 1)])
    await db.files.create_index([("supplier_name", 1)])
    await db.users.create_index("email", unique=True)
    await db.users.create_index("organization_id")
    await db.suppliers.create_index("organization_id")
    await db.risk_assessments.create_index("organization_id")
    await db.gym_layouts.create_index("organization_id")
    await db.check_sheet_history.create_index([("organization_id", 1), ("created_at", -1)])
    await db.purchase_orders.create_index([("organization_id", 1), ("created_at", -1)])
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.password_reset_tokens.create_index("token")
    # Iter 220as — Stripe webhook idempotency (event_id unique + 30-day TTL).
    try:
        from utils.stripe_idempotency import ensure_indexes as _ensure_stripe_idemp
        await _ensure_stripe_idemp()
    except Exception:
        pass
    # Iter 220at — AI guardrails (token-usage rollup + ai_actions audit).
    try:
        from utils.ai_guardrails import ensure_indexes as _ensure_ai_guardrails
        await _ensure_ai_guardrails()
    except Exception:
        pass
    # Iter 220ax — Audit log indexes (export_events + impersonation_events).
    try:
        from utils.audit_log import ensure_indexes as _ensure_audit_log
        await _ensure_audit_log()
    except Exception:
        pass
    # CRM indexes
    await db.crm_users.create_index("email", unique=True)
    await db.crm_contacts.create_index([("email", 1)])
    await db.crm_contacts.create_index([("company_id", 1)])
    await db.crm_contacts.create_index([("created_at", -1)])
    await db.crm_deals.create_index([("stage", 1)])
    await db.crm_deals.create_index([("pipeline_id", 1)])
    await db.crm_deals.create_index([("contact_id", 1)])
    await db.crm_activities.create_index([("contact_id", 1), ("created_at", -1)])
    await db.crm_activities.create_index([("deal_id", 1)])
    await db.crm_audit_log.create_index([("created_at", -1)])
    await db.crm_conversations.create_index([("status", 1), ("updated_at", -1)])
    await db.crm_conversations.create_index([("assigned_to", 1)])
    await db.crm_messages.create_index([("conversation_id", 1), ("created_at", 1)])
    await db.crm_meetings.create_index([("contact_id", 1), ("created_at", -1)])
    await db.crm_workflows.create_index([("active", 1), ("trigger.type", 1)])
    await db.crm_workflow_logs.create_index([("workflow_id", 1), ("executed_at", -1)])
    await db.crm_quotes.create_index([("status", 1), ("created_at", -1)])
    await db.crm_quotes.create_index([("contact_id", 1)])
    await db.crm_integrations.create_index([("type", 1)], unique=True)
    # Service Desk indexes
    await db.service_desk_audit_log.create_index([("timestamp", -1)])
    await db.service_desk_audit_log.create_index([("actor_id", 1), ("timestamp", -1)])
    await db.service_desk_audit_log.create_index([("target_type", 1), ("target_id", 1)])
    await db.users.create_index("is_service_desk")
    # Trust Backbone indexes
    from utils.trust_events import ensure_trust_event_indexes
    await ensure_trust_event_indexes()
    # Support audit indexes (SOC 2 / ISO 27001 evidence stream)
    from utils.support_audit import ensure_support_audit_indexes
    await ensure_support_audit_indexes()
    from routes.support_escalate import ensure_support_escalate_indexes
    await ensure_support_escalate_indexes()
    # Iter 216h75 — Partner Engineer Network indexes
    from routes.partners import ensure_partner_indexes
    await ensure_partner_indexes()
    # Iter 220aa — Embeddable Widget (iframe Log-a-Fault) indexes
    from routes.widget_embed import init_widget_embed_indexes
    await init_widget_embed_indexes()
    # Iter 220ad — SEO Autopilot indexes
    from routes.marketing.seo_autopilot import init_seo_indexes
    await init_seo_indexes()
    # Iter 216h140 — Engineer Diary indexes
    from routes.svc.diary import ensure_diary_indexes
    await ensure_diary_indexes()
    # Iter 216h142 — Notifications indexes
    from routes.svc.notifications import ensure_notification_indexes
    await ensure_notification_indexes()
    # Iter 216h144 — Engineer independence indexes
    from routes.svc.independence import ensure_independence_indexes
    await ensure_independence_indexes()
    # Iter 216h146 — Inbound email log indexes
    from routes.svc.inbound_email import ensure_inbound_email_indexes
    await ensure_inbound_email_indexes()
    # Iter 216h259 — Engineer Lite CRM indexes
    from routes.svc.engineer_customers import ensure_indexes as ensure_engineer_customer_indexes
    await ensure_engineer_customer_indexes()
    # Iter 220 — Work Report custom fields indexes
    from routes.svc.work_report_fields import ensure_indexes as ensure_work_report_fields_indexes
    await ensure_work_report_fields_indexes()
    # Iter 220c — Engineer job-draft autosave (unique per engineer×case)
    await db.svc_engineer_job_drafts.create_index(
        [("organization_id", 1), ("engineer_id", 1), ("case_id", 1)],
        unique=True,
        name="svc_engineer_job_drafts_unique",
    )
    # Iter 220d — Per-machine reports + note presets
    from routes.svc.per_machine_reports import ensure_indexes as ensure_per_machine_indexes
    await ensure_per_machine_indexes()
    # Iter 220ci — Engineer Equipment list filters
    from routes.svc.engineer_equipment import ensure_indexes as ensure_engineer_equipment_indexes
    await ensure_engineer_equipment_indexes()
    # Iter 220g — Postcode geocode cache
    from routes.svc.scheduling_suggestions import ensure_indexes as ensure_scheduling_indexes
    await ensure_scheduling_indexes()
    # Security hardening indexes (rate-limit TTL, JWT revocations, LLM budgets)
    from utils.security_plus import ensure_security_indexes
    await ensure_security_indexes()
    # MFA replay-protection indexes
    from utils.mfa import ensure_mfa_indexes
    await ensure_mfa_indexes()
    # SSO indexes (state TTL + unique link)
    from utils.sso import ensure_sso_indexes
    await ensure_sso_indexes()
    # Digest preferences index
    from utils.digest import ensure_digest_indexes
    await ensure_digest_indexes()

    # ───────────────────────────────────────────────────────────────
    # Tier-2 performance indexes (added Apr 2026)
    # Every `.find().sort()` in routes/ was audited; collections that
    # sorted without a matching compound index were hitting in-memory
    # sort on large collections. These indexes let the optimiser stream
    # results directly from the B-tree (~10-100× faster on collections
    # with >10 k docs). Safe to create — MongoDB no-ops if the index
    # already exists with the same definition.
    # ───────────────────────────────────────────────────────────────
    # Equipment list sorted by created_at per org
    await db.equipment.create_index([("organization_id", 1), ("created_at", -1)])
    # Audits per-equipment history view
    await db.audits.create_index([("equipment_id", 1), ("created_at", -1)])
    # Master admin org + user listings
    await db.organizations.create_index([("created_at", -1)])
    await db.users.create_index([("created_at", -1)])
    await db.crm_users.create_index([("created_at", -1)])
    # Admin activity & analytics streams
    await db.admin_activity_log.create_index([("timestamp", -1)])
    # Integration observability (logs + bridge records)
    await db.integration_logs.create_index([("timestamp", -1)])
    await db.integration_bridge.create_index([("created_at", -1)])
    # Supplier portal case timeline
    await db.supplier_cases.create_index([("created_at", -1)])
    await db.supplier_case_comments.create_index([("case_id", 1), ("created_at", 1)])
    # CRM v2 contracts + activities
    await db.crm2_contracts.create_index([("created_at", -1)])
    await db.crm2_activities.create_index([("created_at", -1)])
    # Purchase orders: most common query is emailed=true sorted by date
    await db.purchase_orders.create_index([("emailed", 1), ("created_at", -1)])
    # Files with dedupe hash lookup
    await db.files.create_index([("organization_id", 1), ("created_at", -1)])
    try:
        await db.sicon_engineers.create_index([("organization_id", 1), ("is_leaver", 1)])
        await db.sicon_engineers.create_index([("organization_id", 1), ("post_code_area", 1)])
        await db.sicon_engineers.create_index([("id", 1)], unique=True)
        await db.organizations.create_index([("sicon_crm_person_id", 1)])
    except Exception as _e:  # pragma: no cover
        logger.warning(f"sicon_engineers index creation warning: {_e}")

    # Sicon ↔ Pulse external-id link table (spec §7) — the unique key makes
    # every read-side sync idempotent (same external id → same Pulse record).
    try:
        await db.sicon_external_links.create_index(
            [("integration_source", 1), ("external_entity_type", 1), ("external_id", 1)],
            unique=True, name="uniq_sicon_external_link",
        )
        await db.sicon_external_links.create_index([("external_entity_type", 1), ("sync_status", 1)])
        await db.sicon_external_links.create_index([("organization_id", 1), ("external_entity_type", 1)])
    except Exception as _e:  # pragma: no cover
        logger.warning(f"sicon_external_links index creation warning: {_e}")

    # Auto-match lookups (hands-off customer/site resolution).
    try:
        await db.crm2_companies.create_index([("organization_id", 1), ("sage_customer_id", 1)])
        await db.crm2_sites.create_index([("organization_id", 1), ("sicon_sub_location_id", 1)])
    except Exception as _e:  # pragma: no cover
        logger.warning(f"crm2 sicon auto-match index warning: {_e}")

    # ───────────────────────────────────────────────────────────────
    # Tier-3 performance indexes (added Feb 2026)
    # Audited every collection with >0 organization_id queries that
    # was missing a covering index. Each `create_index` is idempotent.
    # ───────────────────────────────────────────────────────────────
    try:
        # Sites: every operator dashboard hits /api/sites which filters by org
        await db.sites.create_index([("organization_id", 1), ("created_at", 1)])
        # Per-org assistant action log queries (Trust Dashboard + Undo flow)
        await db.assistant_action_log.create_index(
            [("organization_id", 1), ("executed_at", -1)],
        )
        await db.assistant_action_log.create_index([("id", 1)], unique=True)
        await db.assistant_action_log.create_index([("executed_at", -1)])
        # CRM v2 service cases — heavy joins from Operations + integration_hub
        await db.crm2_service_cases.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        # Marketing & memberships — campaign lists and segment lookups
        await db.marketing_campaigns.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        await db.marketing_audiences.create_index([("organization_id", 1)])
        await db.marketing_creative_assets.create_index([("organization_id", 1)])
        # Onboarding packets dashboard
        await db.onboarding_packets.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        await db.onboarding_packets.create_index([("status", 1), ("created_at", 1)])
        # Check sheets list per org (already had history; add the live one)
        await db.check_sheets.create_index([("organization_id", 1), ("created_at", -1)])
        # Gym floor: handover diary + sessions both filter by org+date
        await db.gym_floor_sessions.create_index(
            [("organization_id", 1), ("started_at", -1)],
        )
        await db.gym_floor_handover.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        # Faults legacy collection (separate from issues — used by service portal)
        await db.faults.create_index([("organization_id", 1), ("created_at", -1)])
        # AI Creative Director briefs (Phase 1+2)
        await db.marketing_director_briefs.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        await db.marketing_director_briefs.create_index([("id", 1)], unique=True)
        # Integration events (used by Sage 200 + Orbit 4 sync polling)
        await db.integration_events.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
    except Exception as _e:  # pragma: no cover
        logger.warning(f"tier-3 index creation warning: {_e}")

    # ───────────────────────────────────────────────────────────────
    # Tier-4 performance indexes (added iter 216h170 — Feb 2026)
    # Filled gaps surfaced by the structured query-pattern audit:
    # every collection in the top-30 by query volume that lacked a
    # covering index on its hottest filter pair. Each is idempotent.
    # ───────────────────────────────────────────────────────────────
    try:
        # Engineer Service hub — id, case_id and timeline lookups
        await db.svc_cases.create_index([("id", 1)], unique=True)
        await db.svc_cases.create_index(
            [("organization_id", 1), ("status", 1), ("created_at", -1)],
        )
        await db.svc_cases.create_index([("assigned_engineer_id", 1), ("status", 1)])
        await db.svc_cases.create_index([("track_token", 1)], sparse=True)

        # Engineer quotes — id + case_id + status views
        await db.svc_quotes.create_index([("id", 1)], unique=True)
        await db.svc_quotes.create_index([("case_id", 1), ("created_at", -1)])
        await db.svc_quotes.create_index(
            [("organization_id", 1), ("status", 1), ("created_at", -1)],
        )

        # Engineer invoices — id + case_id + organization
        await db.svc_invoices.create_index([("id", 1)], unique=True)
        await db.svc_invoices.create_index([("case_id", 1), ("created_at", -1)])
        await db.svc_invoices.create_index(
            [("organization_id", 1), ("status", 1), ("created_at", -1)],
        )
        # Case timeline events (sub-doc per case)
        await db.svc_case_events.create_index([("case_id", 1), ("created_at", 1)])
        # Visit notes per case
        await db.svc_visit_notes.create_index([("case_id", 1), ("created_at", -1)])

        # Sites: every dashboard hits this by id + by org+name search
        await db.sites.create_index([("id", 1)], unique=True)
        await db.sites.create_index([("organization_id", 1), ("name", 1)])

        # Payment transactions — Stripe session lookups are the hottest
        # path (webhook + session-status polling). User_id + status used
        # by the onboarding dashboard.
        await db.payment_transactions.create_index([("session_id", 1)], sparse=True)
        await db.payment_transactions.create_index(
            [("user_email", 1), ("payment_status", 1)],
        )
        await db.payment_transactions.create_index(
            [("stripe_event_id", 1)], unique=True, sparse=True,
        )

        # Staff: org + active for rota board; id lookups
        await db.staff_members.create_index([("id", 1)], unique=True)
        await db.staff_members.create_index([("organization_id", 1), ("active", 1)])
        await db.staff_shifts.create_index([("id", 1)], unique=True)
        await db.staff_shifts.create_index(
            [("organization_id", 1), ("starts_at", 1)],
        )
        await db.staff_shifts.create_index([("staff_id", 1), ("starts_at", 1)])

        # Memberships sub-tables (the consoles join these heavily)
        await db.membership_class_invoices.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        await db.membership_class_invoices.create_index([("instructor_id", 1)])
        await db.membership_instructors.create_index([("id", 1)], unique=True)
        await db.membership_instructors.create_index([("organization_id", 1)])

        # Audit logs — the Compliance trail viewer (iter 216h161) reads
        # by user_id + by resource pair, both with time sort.
        await db.audit_logs.create_index([("timestamp", -1)])
        await db.audit_logs.create_index(
            [("resource_type", 1), ("resource_id", 1), ("timestamp", 1)],
        )
        await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_logs.create_index([("action", 1), ("timestamp", -1)])

        # Refund events (iter 215c9 + iter 216h165 detail viewer)
        await db.refund_events.create_index([("id", 1)], unique=True)
        await db.refund_events.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )

        # CRM v2 contacts / companies — hot lookup paths
        await db.crm_v2_contacts.create_index([("id", 1)], unique=True, sparse=True)
        await db.crm_v2_contacts.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        await db.crm_v2_companies.create_index([("id", 1)], unique=True, sparse=True)
        await db.crm_v2_companies.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )

        # Engineers (legacy svc_engineers collection)
        await db.svc_engineers.create_index([("organization_id", 1), ("active", 1)])

        # Supplier cases (extra index — existing one only covered timestamp)
        await db.supplier_cases.create_index(
            [("organization_id", 1), ("created_at", -1)],
        )
        await db.supplier_cases.create_index([("supplier_id", 1), ("status", 1)])
    except Exception as _e:  # pragma: no cover
        logger.warning(f"tier-4 index creation warning: {_e}")
    logger.info("MongoDB indexes created/verified")


__all__ = ["create_indexes"]
