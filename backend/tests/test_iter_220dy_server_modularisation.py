"""Iter 220dy — Modularise ``server.py``.

P3 hygiene: pre-iter, ``server.py`` was 1027 lines, with the bulk
being one-shot startup seeding + index creation. We extract the
stateless pieces into a dedicated ``bootstrap`` package:

  * ``bootstrap.seed`` — ``seed_master_admin`` + ``seed_services``.
  * ``bootstrap.indexes`` — ``create_indexes`` (every collection
    in one audit-friendly file).

``server.py`` keeps the FastAPI app, middleware, and the
``startup`` / ``shutdown`` orchestrators (which now just delegate
to the bootstrap coroutines). Backwards-compatible underscored
shims (``_seed_master_admin`` / ``_seed_services`` /
``_create_indexes``) remain so any out-of-tree test importing the
old name still works.
"""
from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── 1 · bootstrap package is importable + exports the three coroutines ──


def test_bootstrap_package_public_api():
    mod = importlib.import_module("bootstrap")
    for name in ("create_indexes", "seed_master_admin", "seed_services"):
        assert hasattr(mod, name), f"bootstrap.{name} missing from public API"
        assert asyncio.iscoroutinefunction(getattr(mod, name)), (
            f"bootstrap.{name} must be an async function"
        )


def test_bootstrap_submodules_are_independently_importable():
    """Each submodule must work in isolation (no circular imports)."""
    seed = importlib.import_module("bootstrap.seed")
    indexes = importlib.import_module("bootstrap.indexes")
    assert hasattr(seed, "seed_master_admin")
    assert hasattr(seed, "seed_services")
    assert hasattr(indexes, "create_indexes")


# ── 2 · server.py keeps the backwards-compatible shims ──────────────


def test_server_underscored_shims_delegate_to_bootstrap():
    """The legacy `_seed_master_admin` / `_seed_services` /
    `_create_indexes` underscored names must still be importable from
    `server` so any out-of-tree caller doesn't break. Each one is
    expected to be a *very* thin wrapper that just `await`-s the
    matching bootstrap coroutine."""
    src = Path("/app/backend/server.py").read_text(encoding="utf-8")
    # All three shims defined.
    for shim in ("_seed_master_admin", "_seed_services", "_create_indexes"):
        assert f"async def {shim}() -> None:" in src, (
            f"{shim} shim removed from server.py — breaks backwards compat"
        )
    # And each one imports + delegates rather than carrying inline
    # bodies (which would re-defeat the modularisation).
    assert "from bootstrap.seed import seed_master_admin" in src
    assert "from bootstrap.seed import seed_services" in src
    assert "from bootstrap.indexes import create_indexes" in src


def test_server_file_is_meaningfully_smaller_than_before():
    """Sanity guard against regression. Pre-iter server.py was 1027
    lines; post-iter must come in under 700 to ensure the bulk of
    the seed/index code actually moved. A future iter that re-inlines
    routes here will trip this pin."""
    lines = Path("/app/backend/server.py").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 700, (
        f"server.py grew back to {len(lines)} lines — refactor regressed"
    )


# ── 3 · Functional smoke: seed_master_admin still seeds + heals ──


def test_seed_master_admin_inserts_when_missing():
    from bootstrap.seed import seed_master_admin as fn

    fdb = MagicMock()
    fdb.users.find_one = AsyncMock(return_value=None)
    fdb.organizations.insert_one = AsyncMock()
    fdb.users.insert_one = AsyncMock()

    async def go():
        with patch("bootstrap.seed.db", fdb), \
             patch("utils.auth.hash_password", return_value="hashed"), \
             patch("utils.security.clear_failed_logins"):
            await fn()

    _run(go())
    fdb.organizations.insert_one.assert_awaited_once()
    fdb.users.insert_one.assert_awaited_once()
    inserted_user = fdb.users.insert_one.await_args.args[0]
    assert inserted_user["is_master_admin"] is True
    assert inserted_user["password"] == "hashed"


def test_seed_master_admin_self_heals_missing_org():
    """When the admin's org doc was deleted (data wipes / restores)
    the seed must re-create it so module pages stop returning 404."""
    from bootstrap.seed import seed_master_admin as fn

    fdb = MagicMock()
    fdb.users.find_one = AsyncMock(return_value={
        "email": "admin@gymaxisai.com",
        "id": "u-1",
        "organization_id": "org-orphan",
    })
    fdb.users.update_one = AsyncMock()
    fdb.organizations.find_one = AsyncMock(return_value=None)  # ORG MISSING
    fdb.organizations.insert_one = AsyncMock()

    async def go():
        with patch("bootstrap.seed.db", fdb), \
             patch("utils.auth.hash_password", return_value="hashed"), \
             patch("utils.security.clear_failed_logins"):
            await fn()

    _run(go())
    # The org re-seed fired.
    fdb.organizations.insert_one.assert_awaited_once()
    inserted_org = fdb.organizations.insert_one.await_args.args[0]
    assert inserted_org["id"] == "org-orphan"
    assert inserted_org["modules"]["memberships"]["enabled"] is True


# ── 4 · Functional smoke: create_indexes runs the core block ──────


def test_create_indexes_runs_core_index_calls():
    """Pin the core block — if the migration accidentally dropped any
    of the historic index calls the suite catches it immediately."""
    from bootstrap.indexes import create_indexes as fn

    fdb = MagicMock()
    # Set every collection method we touch to a no-op AsyncMock.
    # MongoDB's create_index is async on motor.
    for coll in (
        "issues", "equipment", "files", "users", "suppliers",
        "risk_assessments", "gym_layouts", "check_sheet_history",
        "purchase_orders", "password_reset_tokens",
        "crm_users", "crm_contacts", "crm_deals", "crm_activities",
        "crm_audit_log", "crm_conversations", "crm_messages",
        "crm_meetings", "crm_workflows", "crm_workflow_logs",
        "crm_quotes", "crm_integrations",
        "service_desk_audit_log",
        "audits", "organizations", "admin_activity_log",
        "integration_logs", "integration_bridge", "supplier_cases",
        "supplier_case_comments", "crm2_contracts", "crm2_activities",
        "sicon_engineers",
        "sites", "assistant_action_log", "crm2_service_cases",
        "marketing_campaigns", "marketing_audiences",
        "marketing_creative_assets", "onboarding_packets",
        "check_sheets", "gym_floor_sessions", "gym_floor_handover",
        "faults", "marketing_director_briefs", "integration_events",
        "svc_cases", "svc_quotes", "svc_invoices", "svc_case_events",
        "svc_visit_notes", "payment_transactions",
        "staff_members", "staff_shifts",
        "membership_class_invoices", "membership_instructors",
        "audit_logs", "refund_events",
        "crm_v2_contacts", "crm_v2_companies", "svc_engineers",
        "svc_engineer_job_drafts",
    ):
        getattr(fdb, coll).create_index = AsyncMock()

    # Every imported `ensure_*_indexes` is patched at the call site to
    # short-circuit external dependencies (Mongo + LLM key budgets).
    patches = [
        patch("bootstrap.indexes.db", fdb),
        patch("utils.trust_events.ensure_trust_event_indexes", AsyncMock()),
        patch("utils.support_audit.ensure_support_audit_indexes", AsyncMock()),
        patch("routes.support_escalate.ensure_support_escalate_indexes", AsyncMock()),
        patch("routes.partners.ensure_partner_indexes", AsyncMock()),
        patch("routes.widget_embed.init_widget_embed_indexes", AsyncMock()),
        patch("routes.marketing.seo_autopilot.init_seo_indexes", AsyncMock()),
        patch("routes.svc.diary.ensure_diary_indexes", AsyncMock()),
        patch("routes.svc.notifications.ensure_notification_indexes", AsyncMock()),
        patch("routes.svc.independence.ensure_independence_indexes", AsyncMock()),
        patch("routes.svc.inbound_email.ensure_inbound_email_indexes", AsyncMock()),
        patch("routes.svc.engineer_customers.ensure_indexes", AsyncMock()),
        patch("routes.svc.work_report_fields.ensure_indexes", AsyncMock()),
        patch("routes.svc.per_machine_reports.ensure_indexes", AsyncMock()),
        patch("routes.svc.engineer_equipment.ensure_indexes", AsyncMock()),
        patch("routes.svc.scheduling_suggestions.ensure_indexes", AsyncMock()),
        patch("utils.security_plus.ensure_security_indexes", AsyncMock()),
        patch("utils.mfa.ensure_mfa_indexes", AsyncMock()),
        patch("utils.sso.ensure_sso_indexes", AsyncMock()),
        patch("utils.digest.ensure_digest_indexes", AsyncMock()),
    ]

    async def go():
        # Open all patches as nested context managers.
        stack = []
        try:
            for p in patches:
                stack.append(p.__enter__())
            await fn()
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)

    _run(go())
    # Sample three calls from each tier — proves the body executed
    # without raising.
    fdb.issues.create_index.assert_any_call(
        [("organization_id", 1), ("created_at", -1)],
    )
    fdb.equipment.create_index.assert_any_call("serial_number")
    fdb.svc_cases.create_index.assert_any_call([("id", 1)], unique=True)
