"""Seed routines invoked at FastAPI startup.

Extracted from ``server.py`` in iter 220dy. Two coroutines:

* ``seed_master_admin`` — idempotent self-heal of the master
  admin account (password reset is opt-out via
  ``MASTER_ADMIN_RESET_ON_BOOT=0``).
* ``seed_services`` — fans out every service-desk / CRM /
  memberships seed + index-ensurer. Each branch is wrapped in
  ``try`` so a single failing extra (e.g. demo-seed flag) can't
  bring the whole startup down.

Both functions take no arguments and depend only on
``utils.database.db`` + the standard library.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from utils.database import db

logger = logging.getLogger(__name__)


async def seed_master_admin() -> None:
    """Seed/heal master admin account on every startup.

    The seed is **self-healing**: on every boot we make sure the master
    admin's password matches the ``MASTER_ADMIN_PASSWORD`` env var,
    clear any lockouts / temp-password flags, and ensure
    ``is_master_admin=True``. This means a fresh deployment is always
    recoverable: just set ``MASTER_ADMIN_PASSWORD`` in the deployment
    env (or rely on the documented default) and the user can always
    sign in.

    Set ``MASTER_ADMIN_RESET_ON_BOOT=0`` to opt out (e.g. once you've
    rotated the admin password through the UI and want it to stick).
    """
    from utils.auth import hash_password
    from utils.security import clear_failed_logins

    master_email = os.environ.get("MASTER_ADMIN_EMAIL", "admin@pulsefitness.ai")
    master_pwd = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
    reset_on_boot = os.environ.get("MASTER_ADMIN_RESET_ON_BOOT", "1") != "0"
    # Resolve (and de-duplicate) the master-admin user. A manual email rename
    # in the UI can collide with a seed-created account, leaving TWO users
    # with the same email — login then matches an account whose password we
    # never reset, so the operator appears "locked out with the right
    # password". Keep ONE (prefer an existing master admin, then oldest) and
    # remove the duplicates so login + the password reset target the same row.
    dupes = await db.users.find({"email": master_email}).to_list(length=100)
    existing = None
    if dupes:
        dupes.sort(key=lambda u: (0 if u.get("is_master_admin") else 1, u.get("created_at") or ""))
        existing = dupes[0]
        for extra in dupes[1:]:
            await db.users.delete_one({"id": extra.get("id")})
            logger.warning(
                "Removed duplicate master-admin user (email=%s, id=%s)",
                master_email, extra.get("id"),
            )
    if not existing:
        admin_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        await db.organizations.insert_one({
            "id": org_id, "name": "Pulse Fitness AI Admin",
            "subscription_tier": "premium",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.users.insert_one({
            "id": admin_id, "email": master_email,
            "full_name": "Master Admin",
            "password": hash_password(master_pwd),
            "role": "owner", "organization_id": org_id,
            "is_master_admin": True,
            "active": True,
            "must_change_password": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Master admin seeded: {master_email}")
        return

    # Always clear states that could permanently lock the master admin out
    # (stuck "must change password", expired temp password, lockout). The
    # password VALUE is only re-synced when reset_on_boot is enabled.
    set_doc = {
        "is_master_admin": True,
        "active": True,
        "must_change_password": False,
        "temp_password_expires_at": None,
    }
    if reset_on_boot:
        set_doc.update({
            "password": hash_password(master_pwd),
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        })
    await db.users.update_one(
        {"email": master_email},
        {"$set": set_doc, "$unset": {"lockout_until": "", "failed_login_attempts": ""}},
    )
    # Also drop any in-memory rate-limit lockout against this email so a
    # fresh deploy after a brute-force test doesn't lock the admin out.
    clear_failed_logins(master_email)

    # Iter 216h272 — self-heal the master admin's home org if the
    # org doc was deleted out from under the user (data-wipe scripts,
    # restored backups, partial migrations). Without this guard the
    # operator-facing `/api/me/module-trials` endpoint 404s and the
    # whole Memberships / CRM / Marketing module pages render the
    # raw "Organisation not found" string.
    org_id = existing.get("organization_id")
    if org_id:
        org_doc = await db.organizations.find_one(
            {"id": org_id}, {"_id": 0, "id": 1},
        )
        if not org_doc:
            await db.organizations.insert_one({
                "id": org_id,
                "name": "Pulse Fitness AI Admin",
                "account_type": "full",
                "subscription_tier": "premium",
                "modules": {
                    "memberships": {"enabled": True, "source": "seed"},
                    "crm": {"enabled": True, "source": "seed"},
                    "marketing": {"enabled": True, "source": "seed"},
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.warning(
                "Master admin org doc %s was missing — re-seeded so module pages can render",
                org_id,
            )

    if reset_on_boot:
        logger.info(f"Master admin healed (password re-synced): {master_email}")
    else:
        logger.info(
            f"Master admin verified (password reset on boot disabled): {master_email}",
        )

    # ── White-label handover — decommission legacy GymAxis records ──────
    # Production's DB predates the Pulse Fitness conversion and may still
    # contain the old `admin@gymaxisai.com` master admin and "GymAxis*"
    # organisations. Remove them on every boot (idempotent) so a redeploy
    # cleans production automatically. Never touches the configured master
    # admin (master_email) or any Pulse-named record.
    try:
        async for legacy in db.users.find(
            {"email": {"$regex": "@gymaxisai\\.com$", "$options": "i"}},
            {"_id": 0, "id": 1, "email": 1},
        ):
            if (legacy.get("email") or "").lower() == master_email.lower():
                continue
            await db.users.delete_one({"id": legacy["id"]})
            logger.info("Decommissioned legacy GymAxis user: %s", legacy.get("email"))

        async for org in db.organizations.find(
            {"name": {"$regex": "^gym\\s*axis", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1},
        ):
            await db.organizations.delete_one({"id": org["id"]})
            await db.users.delete_many(
                {"organization_id": org["id"], "email": {"$ne": master_email}},
            )
            logger.info("Decommissioned legacy GymAxis org: %s", org.get("name"))
    except Exception as e:  # pragma: no cover — best-effort cleanup
        logger.warning("Legacy GymAxis decommission skipped: %s", e)




async def seed_services() -> None:
    """Seed integrations, CRM admin, picklists, memberships & indexes."""
    from routes.integrations import seed_integrations
    await seed_integrations()
    from routes.crm_auth import seed_crm_admin
    await seed_crm_admin()
    logger.info("CRM admin seeded")
    # Iter 216h223 — CRM Picklists global defaults + Stakeholder map indexes.
    # Iter 216h224 — CRM Products (master price list) indexes.
    try:
        from routes.crm_picklists import seed_global_picklists
        from routes.crm_stakeholders import ensure_stakeholder_indexes
        from routes.crm_products import ensure_product_indexes
        from routes.crm_price_list import ensure_price_list_indexes
        from routes.crm_price_changes import ensure_price_change_indexes
        from routes.crm_quote_sage import ensure_quote_sage_indexes
        from routes.crm_price_backup import ensure_price_backup_indexes
        from routes.crm_website_recognize import ensure_website_cache_indexes
        from utils.tenant_mirror import ensure_tenant_mirror_indexes, mirror_pulse_tenants_to_crm
        from routes.incidents import ensure_incident_indexes
        await seed_global_picklists()
        await ensure_stakeholder_indexes()
        await ensure_product_indexes()
        await ensure_price_list_indexes()
        await ensure_price_change_indexes()
        await ensure_quote_sage_indexes()
        await ensure_price_backup_indexes()
        await ensure_website_cache_indexes()
        await ensure_tenant_mirror_indexes()
        await ensure_incident_indexes()
        # Iter 216h276 — mirror Pulse tenants into the master admin's
        # CRM so paying customers (Pulse Fitness Limited, Third Space)
        # show up in CRM Companies. Idempotent on every boot.
        try:
            await mirror_pulse_tenants_to_crm()
        except Exception:
            logger.exception("tenant mirror reconciliation failed (non-fatal)")
        logger.info("CRM picklists + stakeholder + products indexes ready")
    except Exception as e:  # pragma: no cover
        logger.warning(
            "CRM picklists / stakeholder / products seed failed (non-fatal): %s",
            e,
        )
    # MOD demo tree (idempotent) — disabled in fresh-platform mode
    if os.environ.get("ENABLE_DEMO_SEED", "0") == "1":
        try:
            from utils.mod_seed import seed_mod_demo, ensure_mod_indexes
            await ensure_mod_indexes()
            await seed_mod_demo()
            logger.info("MOD demo tree seeded")
        except Exception as e:  # pragma: no cover
            logger.warning("MOD demo seed failed: %s", e)
    # Pulse Fitness Memberships — indexes always; demo seed only when ENABLE_DEMO_SEED=1
    try:
        from routes.memberships import ensure_memberships_indexes
        await ensure_memberships_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Memberships index ensure failed: %s", e)
    try:
        from routes.memberships_phase4 import ensure_phase4_indexes
        await ensure_phase4_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Memberships Phase 4 index ensure failed: %s", e)
    try:
        from routes.memberships_phase6 import ensure_phase6_indexes
        await ensure_phase6_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Memberships Phase 6 index ensure failed: %s", e)
    try:
        from routes.master_admin_pricing import ensure_pricing_indexes
        from routes.master_admin_billing import ensure_org_billing_indexes
        from routes.activation_events import ensure_activation_indexes
        from routes.master_admin_documents_lib import ensure_documents_indexes
        from routes.invoice_share import ensure_invoice_share_indexes
        from routes.email_health import ensure_email_send_events_indexes
        from routes.triage_feedback import ensure_triage_attempts_indexes
        await ensure_pricing_indexes()
        await ensure_org_billing_indexes()
        await ensure_activation_indexes()
        await ensure_documents_indexes()
        await ensure_invoice_share_indexes()
        await ensure_email_send_events_indexes()
        await ensure_triage_attempts_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Pricing / billing index ensure failed: %s", e)
    if os.environ.get("ENABLE_DEMO_SEED", "0") == "1":
        try:
            from utils.memberships_seed import seed_memberships_demo
            from utils.memberships_analytics_seed import seed_memberships_analytics_demo
            await seed_memberships_demo()
            await seed_memberships_analytics_demo()
            logger.info("Memberships demo seeded")
        except Exception as e:  # pragma: no cover
            logger.warning("Memberships seed failed: %s", e)
    try:
        await backfill_service_org_ids()
    except Exception as e:  # pragma: no cover
        logger.warning("Service-org backfill failed: %s", e)
    try:
        from routes.svc.ai_scheduling import ensure_scheduling_indexes
        await ensure_scheduling_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("AI scheduling index ensure failed: %s", e)
    try:
        from routes.equipment_transfer import ensure_indexes as _eq_transfer_indexes
        await _eq_transfer_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Equipment transfer index ensure failed: %s", e)
    try:
        from routes.machine_manuals import ensure_machine_manuals_indexes
        await ensure_machine_manuals_indexes()
    except Exception as e:  # pragma: no cover
        logger.warning("Machine manuals index ensure failed: %s", e)


async def backfill_service_org_ids() -> None:
    """Iter 244 — Service Desk for Pulse Fitness.

    Platform-level Service Desk agents and Pulse Master Admins are stored
    with ``organization_id: None``, but the Service-Ops surfaces (cases,
    scheduler, engineers…) scope every query by organization. Org-less
    desk/pulse users therefore need a ``service_org_id`` — the organization
    whose service operation they run (defaults to the master admin's org,
    where the Sicon case data lives). Idempotent: only fills users that
    don't already have one.
    """
    master = await db.users.find_one(
        {"is_master_admin": True, "organization_id": {"$nin": [None, ""]}},
        {"_id": 0, "organization_id": 1},
        sort=[("created_at", 1)],
    )
    if not master:
        return
    service_org = master["organization_id"]
    res = await db.users.update_many(
        {
            "organization_id": {"$in": [None, ""]},
            "service_org_id": {"$in": [None, ""]},
            "$or": [
                {"is_service_desk": True},
                {"is_pulse_admin": True},
                {"role": {"$in": ["service_desk", "pulse_master_admin"]}},
            ],
        },
        {"$set": {"service_org_id": service_org}},
    )
    if res.modified_count:
        logger.info(
            "Backfilled service_org_id for %s org-less desk/pulse users → %s",
            res.modified_count, service_org,
        )


__all__ = ["seed_master_admin", "seed_services", "backfill_service_org_ids", "seed_test_accounts"]


async def seed_test_accounts() -> None:
    """Idempotently seed regression test fixture accounts (non-prod data,
    harmless in prod). Self-healing like ``seed_master_admin``: each boot
    re-syncs the password and clears lockouts so CI/preview always sign in.

    Currently: ``lee.somers@pulsefitness.com`` — a *regular* (non-admin)
    Pulse Pro user used by `test_p1c_security.py` to prove that ordinary
    Pulse users are denied master-admin audit endpoints yet can still use
    the support assistant + conversation export.

    Gate with ``SEED_TEST_ACCOUNTS=0`` to skip entirely.
    """
    if os.environ.get("SEED_TEST_ACCOUNTS", "1") == "0":
        return
    from utils.auth import hash_password
    from utils.security import clear_failed_logins

    email = "lee.somers@pulsefitness.com"
    pwd = "TempPass123!"
    now = datetime.now(timezone.utc).isoformat()

    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "organization_id": 1})
    if existing:
        org_id = existing.get("organization_id")
    else:
        org_id = str(uuid.uuid4())
        await db.organizations.insert_one({
            "id": org_id,
            "name": "Pulse Fitness — Somers (test)",
            "account_type": "pulse_pro",
            "subscription_tier": "pulse_pro",
            "created_at": now,
        })

    await db.users.update_one(
        {"email": email},
        {"$set": {
            "email": email,
            "full_name": "Lee Somers",
            "password": hash_password(pwd),
            "role": "owner",
            "account_type": "pulse_pro",
            "organization_id": org_id,
            "is_master_admin": False,
            "is_pulse_admin": False,
            "active": True,
            "must_change_password": False,
            "password_changed_at": now,
        },
         "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
         "$unset": {"lockout_until": "", "temp_password_expires_at": ""}},
        upsert=True,
    )
    clear_failed_logins(email)
    logger.info("Test account seeded/healed: %s", email)
