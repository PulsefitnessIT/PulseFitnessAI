"""Iter 216h249 — Module-tailored signup routing + Pulse logout + Memberships logo step.

User feedback (Feb 20, 2026):
- Pulse Portal logout dropped operators on the GymAxis marketing page
  instead of /pulse.
- Trial sign-up via the Memberships CTA still routed the new operator
  to /dashboard (Operations) and prompted them to upload equipment —
  not the journey for a dance studio.
- Memberships onboarding checklist should start with branding (logo)
  followed by add-members + CSV import.

Three fixes:

1. **/auth/login + /auth/me** now surface `primary_module` so the
   frontend can branch.
2. **Memberships studio onboarding** prepends an `add_logo` checklist
   step (driven by `org.logo_url`) before the existing 5 steps.
3. **Frontend assertions** confirm:
   • `TrialSignupModal` uses module-aware navigation (no hardcoded
     `/dashboard`).
   • `App.js` logout routes Pulse account types to `/pulse`.
   • `DashboardPage` suppresses the Operations WelcomeHero for
     non-operations primary_module trials.
   • `MembershipsStartTab` renders an inline logo upload modal.
"""
from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Backend: /memberships/studio/onboarding adds add_logo step ───

def test_studio_onboarding_includes_add_logo_step_first():
    from routes.memberships import studio as studio_mod

    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.count_documents = AsyncMock(return_value=0)
    fake.class_templates = MagicMock()
    fake.class_templates.count_documents = AsyncMock(return_value=0)
    fake.membership_plans = MagicMock()
    fake.membership_plans.count_documents = AsyncMock(return_value=0)
    fake.bookings = MagicMock()
    fake.bookings.count_documents = AsyncMock(return_value=0)
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value={
        "id": "org-test", "studio_onboarding_dismissed_at": None,
        "logo_url": None, "name": "Test Studio",
    })

    user = {
        "id": "u-test", "organization_id": "org-test",
        "role": "owner", "account_type": "full",
    }

    with patch.object(studio_mod, "db", fake), \
         patch.object(studio_mod, "_require_operator_org", AsyncMock(return_value="org-test")):
        out = _run(studio_mod.get_studio_onboarding(user=user))

    step_ids = [s["id"] for s in out["steps"]]
    assert step_ids[0] == "add_logo", f"add_logo must be Step 1, got {step_ids}"
    assert "add_members" in step_ids
    assert out["total"] == len(step_ids)
    # No logo → step not done.
    logo_step = next(s for s in out["steps"] if s["id"] == "add_logo")
    assert logo_step["done"] is False


def test_studio_onboarding_marks_logo_done_when_present():
    from routes.memberships import studio as studio_mod

    fake = MagicMock()
    for coll in ("members", "class_templates", "membership_plans", "bookings"):
        m = MagicMock()
        m.count_documents = AsyncMock(return_value=0)
        setattr(fake, coll, m)
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value={
        "id": "org-test", "logo_url": "/api/account/logo/org-test?v=abc",
    })

    user = {"id": "u-test", "organization_id": "org-test", "role": "owner"}
    with patch.object(studio_mod, "db", fake), \
         patch.object(studio_mod, "_require_operator_org", AsyncMock(return_value="org-test")):
        out = _run(studio_mod.get_studio_onboarding(user=user))

    logo_step = next(s for s in out["steps"] if s["id"] == "add_logo")
    assert logo_step["done"] is True
    assert logo_step["count"] == 1


# ─── Frontend code assertions ──────────────────────────────────────

def test_trial_signup_modal_routes_by_module():
    src = pathlib.Path("/app/frontend/src/pages/Marketing/TrialSignupModal.js").read_text()
    # The hardcoded /dashboard navigation must be replaced.
    assert "navigate('/dashboard'" not in src, (
        "TrialSignupModal must not hard-navigate every signup to /dashboard"
    )
    # Module-aware destination switch.
    assert "moduleHome" in src
    assert "'memberships': return '/memberships'" in src
    assert "'crm':         return '/crm'" in src
    assert "'marketing':   return '/marketing'" in src
    # Default fallback still goes to /dashboard for operations.
    assert "default:            return '/dashboard'" in src


def test_app_logout_routes_pulse_to_pulse_portal():
    src = pathlib.Path("/app/frontend/src/App.js").read_text()
    assert "const wasPulse = ['pulse_pro', 'lite'].includes(user?.account_type);" in src
    assert "window.location.replace('/pulse')" in src


def test_dashboard_suppresses_welcomehero_for_non_ops_trials():
    src = pathlib.Path("/app/frontend/src/pages/DashboardPage.js").read_text()
    # The guard checks user.primary_module is set and != 'operations'.
    assert "user?.primary_module && user.primary_module !== 'operations'" in src


def test_memberships_start_tab_has_logo_upload_modal():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MembershipsStartTab.js").read_text()
    assert "LogoUploadModal" in src
    assert 'data-testid="mbr-logo-modal"' in src
    assert "/account/logo" in src
    # The CTA tab "settings" routes to the inline modal, not setTab.
    assert "if (ctaTab === 'settings') { setLogoModalOpen(true); return; }" in src


def test_auth_response_exposes_primary_module():
    src = pathlib.Path("/app/backend/routes/auth.py").read_text()
    # /auth/login response includes primary_module.
    occurrences = src.count('"primary_module": (org or {}).get(\'primary_module\') or \'\'')
    assert occurrences >= 2, (
        f"primary_module must be in both /auth/login and /auth/me, found {occurrences}"
    )
