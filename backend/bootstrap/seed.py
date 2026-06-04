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

    master_email = os.environ.get("MASTER_ADMIN_EMAIL", "admin@gymaxisai.com")
    master_pwd = os.environ.get("MASTER_ADMIN_PASSWORD", "MasterAdmin123!")
    reset_on_boot = os.environ.get("MASTER_ADMIN_RESET_ON_BOOT", "1") != "0"
    existing = await db.users.find_one({"email": master_email})
    if not existing:
        admin_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        await db.organizations.insert_one({
            "id": org_id, "name": "GymAxis AI Admin",
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

    set_doc = {"is_master_admin": True, "active": True}
    if reset_on_boot:
        set_doc.update({
            "password": hash_password(master_pwd),
            "must_change_password": False,
            "temp_password_expires_at": None,
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        })
    await db.users.update_one(
        {"email": master_email},
        {"$set": set_doc, "$unset": {"lockout_until": ""}},
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
                "name": "GymAxis AI Admin",
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
        from routes.crm_website_recognize import ensure_website_cache_indexes
        from utils.tenant_mirror import ensure_tenant_mirror_indexes, mirror_pulse_tenants_to_crm
        from routes.incidents import ensure_incident_indexes
        await seed_global_picklists()
        await ensure_stakeholder_indexes()
        await ensure_product_indexes()
        await ensure_price_list_indexes()
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
    # GymAxis Memberships — indexes always; demo seed only when ENABLE_DEMO_SEED=1
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


__all__ = ["seed_master_admin", "seed_services"]
