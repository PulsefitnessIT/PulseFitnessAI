"""Iter 216h252 — Setup Wizard redesign.

User feedback:
- Operators don't know what a "slug" is. Rename to "App address" and
  auto-derive from the studio name with a live availability check.
- Timezone must be a dropdown, not free text.
- Logo upload must be drag-and-drop.
- Capture studio address + contact details that weren't pulled in at
  signup.
- Fix the light-mode leakage on the Payment step's "Soon" cards.
- Add a functional "Add instructor" step.
- The class step should expose instructors via a dropdown.
"""
from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Backend: /memberships/setup/check-slug ────────────────────────

def test_check_slug_rejects_too_short():
    from routes import memberships_ops as ops

    fake = MagicMock()
    fake.users = MagicMock()
    fake.users.find_one = AsyncMock(return_value={"id": "u1", "organization_id": "org1", "role": "owner"})
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value=None)
    user = {"id": "u1", "organization_id": "org1", "role": "owner"}
    with patch.object(ops, "db", fake), \
         patch.object(ops, "_require_operator_org", AsyncMock(return_value="org1")):
        out = _run(ops.setup_check_slug(slug="ab", user=user))
    assert out == {"available": False, "slug": "ab", "reason": "too_short"}


def test_check_slug_returns_available_when_unique():
    from routes import memberships_ops as ops

    fake = MagicMock()
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value=None)
    user = {"id": "u1", "organization_id": "org1", "role": "owner"}
    with patch.object(ops, "db", fake), \
         patch.object(ops, "_require_operator_org", AsyncMock(return_value="org1")):
        out = _run(ops.setup_check_slug(slug="Bella Dance!!", user=user))
    assert out["available"] is True
    assert out["slug"] == "bella-dance"


def test_check_slug_returns_suggestion_when_taken():
    from routes import memberships_ops as ops

    fake = MagicMock()
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value={"id": "other-org"})
    user = {"id": "u1", "organization_id": "org1", "role": "owner"}
    with patch.object(ops, "db", fake), \
         patch.object(ops, "_require_operator_org", AsyncMock(return_value="org1")):
        out = _run(ops.setup_check_slug(slug="bella-dance", user=user))
    assert out["available"] is False
    assert out["slug"] == "bella-dance"
    assert out["reason"] == "taken"
    assert out["suggestion"].startswith("bella-dance-")


# ─── Backend: BasicsBody captures address + contact ────────────────

def test_basics_body_accepts_address_and_contact():
    from routes.memberships_ops import BasicsBody

    body = BasicsBody(
        name="Bella Dance",
        address_line1="1 Studio Lane",
        city="Leeds",
        postcode="LS1 2AB",
        country="United Kingdom",
        contact_email="hello@belladance.co",
        contact_phone="+44 1234 567890",
    )
    assert body.address_line1 == "1 Studio Lane"
    assert body.city == "Leeds"
    assert body.contact_email == "hello@belladance.co"


def test_setup_status_returns_new_fields():
    """`/memberships/setup/status` must surface the new fields so the
    wizard can pre-populate Step 1 on reload."""
    src = pathlib.Path("/app/backend/routes/memberships_ops.py").read_text()
    assert '"address_line1"' in src
    assert '"city"' in src
    assert '"postcode"' in src
    assert '"contact_email"' in src
    assert '"contact_phone"' in src


# ─── Frontend: SetupWizard rewrites ───────────────────────────────

def test_wizard_uses_friendly_app_address_label():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/SetupWizard.js").read_text()
    # Old "App URL slug" string is gone.
    assert "App URL slug" not in src
    # New friendly label is present.
    assert "Your member app address" in src
    # SlugField component drives live availability.
    assert "function SlugField" in src
    assert "/memberships/setup/check-slug" in src


def test_wizard_uses_timezone_dropdown():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/SetupWizard.js").read_text()
    # Timezone is rendered via the shared Select component.
    assert 'options={TIMEZONES}' in src
    assert 'Europe/London' in src
    assert 'America/New_York' in src
    assert 'Australia/Sydney' in src


def test_wizard_has_logo_dropzone():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/SetupWizard.js").read_text()
    assert "function LogoDropzone" in src
    assert "onDrop=" in src
    assert "/account/logo" in src
    assert 'data-testid="mbr-setup-logo-drop"' in src


def test_wizard_captures_address_and_contact():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/SetupWizard.js").read_text()
    for tid in (
        "mbr-setup-addr1", "mbr-setup-city", "mbr-setup-postcode",
        "mbr-setup-country", "mbr-setup-contact-email", "mbr-setup-contact-phone",
    ):
        assert f'testid="{tid}"' in src, f"missing {tid} field"


def test_wizard_payment_cards_no_longer_use_light_bg():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/SetupWizard.js").read_text()
    # The previous bg-white/[0.02] + border-white/10 combo was the
    # source of the light-mode leak on the "Soon" cards.
    assert "bg-white/[0.02]" not in src
    # New explicit rgba dark fills are present.
    assert "rgba(255,255,255,0.04)" in src
    # The selected state is the brand cyan tint, not a default white.
    assert "rgba(25,205,255,0.10)" in src


def test_wizard_has_instructor_step():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/SetupWizard.js").read_text()
    assert "function InstructorStep" in src
    # The new step is wired in the STEPS array between plans and class.
    assert "{ id: 'instructor', label: 'Instructor' }" in src
    # Required fields enforced before save.
    assert "GDPR consent required to add an instructor" in src
    # Posts to the real endpoint.
    assert "/memberships/instructors" in src


def test_wizard_class_step_uses_instructor_dropdown():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/SetupWizard.js").read_text()
    assert 'data-testid="mbr-setup-class-instructor-select"' in src
    # Custom-name escape hatch present.
    assert '__custom__' in src
    # Fetches instructors from the API.
    assert "axios.get(`${API}/memberships/instructors`" in src
