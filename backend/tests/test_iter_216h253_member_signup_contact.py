"""Iter 216h253 — Public member sign-up captures full contact details.

User feedback (Feb 20, 2026):
"When a member requested to join via the app it didn't ask for any
contact details — all the contact fields within the add member option
needs to be completed. Ensure new member forms are easy to complete
with date dropdown boxes where possible."

Fixes:
1. Backend `MemberRegister` extended with address, emergency contact,
   GDPR + marketing consent.
2. `/api/member-auth/register` now enforces phone + GDPR consent
   (parity with the operator AddMemberModal).
3. Member doc gets every captured field persisted on first save with
   a proper consent audit trail.
4. Frontend `RegisterForm` (member portal) redesigned: phone + DOB
   (day/month/year selects) + address + emergency contact + consent
   checkboxes are all surfaced.
5. Operator-side `AddMemberModal` upgrades the Country field from a
   free-text + datalist to a proper Select.
"""
from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Backend: MemberRegister schema ─────────────────────────────────

def test_member_register_schema_accepts_new_fields():
    from routes.memberships.member_auth import MemberRegister

    body = MemberRegister(
        email="ada@example.com",
        password="hunter22hunter",
        first_name="Ada",
        last_name="Lovelace",
        phone="+44 7700 900000",
        dob="1990-12-10",
        address_line1="1 Studio Lane",
        city="Leeds",
        postcode="LS1 2AB",
        country="United Kingdom",
        emergency_contact_name="Bella",
        emergency_contact_phone="+44 7700 900111",
        gdpr_consent=True,
        marketing_consent=True,
        organization_slug="bella-dance",
    )
    assert body.address_line1 == "1 Studio Lane"
    assert body.emergency_contact_name == "Bella"
    assert body.gdpr_consent is True


def test_member_register_requires_phone():
    """Register without phone → 400."""
    from routes.memberships import member_auth as ma
    from fastapi import HTTPException

    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.find_one = AsyncMock(return_value=None)
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value={"id": "org1"})

    request = MagicMock()
    request.client = MagicMock(host="127.0.0.1")
    body = ma.MemberRegister(
        email="x@x.com", password="hunter22hunter",
        first_name="X", last_name="Y",
        organization_slug="bella-dance",
        gdpr_consent=True,
        # phone missing
    )
    with patch.object(ma, "db", fake), \
         patch("utils.security_plus.rate_limit_async", AsyncMock()):
        try:
            _run(ma.member_register(body=body, request=request))
            raise AssertionError("expected 400")
        except HTTPException as e:
            assert e.status_code == 400
            assert "phone" in str(e.detail).lower()


def test_member_register_requires_gdpr_consent():
    """Register without gdpr_consent → 400."""
    from routes.memberships import member_auth as ma
    from fastapi import HTTPException

    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.find_one = AsyncMock(return_value=None)
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value={"id": "org1"})

    request = MagicMock()
    request.client = MagicMock(host="127.0.0.1")
    body = ma.MemberRegister(
        email="x@x.com", password="hunter22hunter",
        first_name="X", last_name="Y",
        phone="+44 7700 900000",
        organization_slug="bella-dance",
        # gdpr_consent default False
    )
    with patch.object(ma, "db", fake), \
         patch("utils.security_plus.rate_limit_async", AsyncMock()):
        try:
            _run(ma.member_register(body=body, request=request))
            raise AssertionError("expected 400")
        except HTTPException as e:
            assert e.status_code == 400
            assert "gdpr" in str(e.detail).lower()


def test_member_register_persists_full_record():
    """All extended fields land on the member doc with a consent trail."""
    from routes.memberships import member_auth as ma

    inserted = {}

    async def _capture(doc):
        inserted.update(doc)

    fake = MagicMock()
    fake.members = MagicMock()
    fake.members.find_one = AsyncMock(return_value=None)
    fake.members.insert_one = AsyncMock(side_effect=_capture)
    fake.organizations = MagicMock()
    fake.organizations.find_one = AsyncMock(return_value={"id": "org1"})
    fake.qr_rotation_secret = MagicMock()
    fake.qr_rotation_secret.insert_one = AsyncMock()
    fake.referrals = MagicMock()
    fake.referrals.insert_one = AsyncMock()

    request = MagicMock()
    request.client = MagicMock(host="127.0.0.1")
    body = ma.MemberRegister(
        email="Bella@Example.com",
        password="hunter22hunter",
        first_name="Bella", last_name="Khan",
        phone="+44 7700 900000",
        dob="2010-05-12",
        address_line1="1 Studio Lane",
        city="Leeds",
        postcode="ls1 2ab",
        country="United Kingdom",
        emergency_contact_name="Aunt Daisy",
        emergency_contact_phone="+44 7700 900111",
        gdpr_consent=True,
        marketing_consent=True,
        organization_slug="bella-dance",
    )

    with patch.object(ma, "db", fake), \
         patch("utils.security_plus.rate_limit_async", AsyncMock()):
        _run(ma.member_register(body=body, request=request))

    # Persistence sanity checks.
    assert inserted["email"] == "bella@example.com"
    assert inserted["phone"] == "+44 7700 900000"
    assert inserted["dob"] == "2010-05-12"
    assert inserted["address_line1"] == "1 Studio Lane"
    assert inserted["city"] == "Leeds"
    assert inserted["postcode"] == "LS1 2AB"  # auto-uppercased
    assert inserted["country"] == "United Kingdom"
    assert inserted["emergency_contact_name"] == "Aunt Daisy"
    assert inserted["emergency_contact_phone"] == "+44 7700 900111"
    assert inserted["gdpr_consent"] is True
    assert inserted["gdpr_consent_at"]
    assert inserted["marketing_consent"] is True
    assert inserted["marketing_consent_at"]


# ─── Frontend: RegisterForm captures full contact + uses DOB dropdowns ─

def test_member_portal_register_has_dob_dropdowns():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MemberPortal.js").read_text()
    for tid in ("member-reg-dob-day", "member-reg-dob-month", "member-reg-dob-year"):
        assert f'testid="{tid}"' in src, f"missing {tid}"
    # DOB recombined into ISO before POSTing.
    assert "${f.dob_year}-${String(f.dob_month).padStart(2, '0')}-${String(f.dob_day).padStart(2, '0')}" in src


def test_member_portal_register_captures_full_contact():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MemberPortal.js").read_text()
    for tid in (
        "member-reg-addr1", "member-reg-city", "member-reg-postcode", "member-reg-country",
        "member-reg-eg-name", "member-reg-eg-phone",
        "member-reg-gdpr", "member-reg-mkt",
    ):
        assert f'testid="{tid}"' in src, f"missing {tid}"


def test_member_portal_register_enforces_phone_and_gdpr_clientside():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/MemberPortal.js").read_text()
    assert "Phone number required" in src
    assert "Please accept the Terms" in src
    assert "Emergency contact phone required" in src


# ─── Frontend: AddMemberModal country upgraded to Select ───────────

def test_add_member_modal_country_uses_select():
    src = pathlib.Path("/app/frontend/src/pages/Memberships/modals/AddMemberModal.js").read_text()
    # The previous datalist-driven free text is gone.
    assert 'list="mbr-new-country-list"' not in src
    assert "<datalist id=\"mbr-new-country-list\"" not in src
    # A proper select with COUNTRIES powers the field now.
    assert 'data-testid="mbr-new-country"' in src
    assert "{COUNTRIES.map((c) =>" in src
    assert "<option key={c} value={c}>{c}</option>" in src
