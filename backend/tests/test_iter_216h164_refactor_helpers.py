"""Iter 216h164 — high-complexity refactor regression tests.

These cover the pure helper functions extracted from
`routes/admin_refunds.py` and `routes/account.py` so we lock in their
behaviour before any further refactor or revert can land.
"""
import pytest
from fastapi import HTTPException

from routes import account, admin_refunds


# ── admin_refunds helpers ────────────────────────────────────────

class TestValidateRefundPayload:
    def test_rejects_missing_charge_id(self):
        with pytest.raises(HTTPException) as exc:
            admin_refunds._validate_refund_payload({"reason": "duplicate"})
        assert exc.value.status_code == 400
        assert "charge_id" in exc.value.detail

    def test_rejects_unknown_reason(self):
        with pytest.raises(HTTPException) as exc:
            admin_refunds._validate_refund_payload({
                "charge_id": "ch_1", "reason": "vibes",
            })
        assert exc.value.status_code == 400
        assert "reason" in exc.value.detail.lower()

    def test_rejects_zero_or_negative_amount(self):
        for bad in (0, -10, "abc"):
            with pytest.raises(HTTPException) as exc:
                admin_refunds._validate_refund_payload({
                    "charge_id": "ch_1", "reason": "duplicate",
                    "amount_pence": bad,
                })
            assert exc.value.status_code == 400

    def test_accepts_full_refund_with_other_reason(self):
        v = admin_refunds._validate_refund_payload({
            "charge_id": " ch_abc ", "reason": " Other ",
            "notes": "x" * 2000, "organization_id": "org-1",
        })
        assert v["charge_id"] == "ch_abc"
        assert v["reason"] == "other"
        assert v["amount_pence"] is None
        assert len(v["notes"]) == 1000  # trimmed to 1000 chars
        assert v["organization_id"] == "org-1"


class TestBuildRefundKwargs:
    def test_charge_id_uses_charge_field(self):
        kw = admin_refunds._build_refund_kwargs("ch_1", None, "duplicate")
        assert kw == {"charge": "ch_1", "reason": "duplicate"}

    def test_payment_intent_uses_pi_field(self):
        kw = admin_refunds._build_refund_kwargs("pi_2", 500, "fraudulent")
        assert kw == {
            "payment_intent": "pi_2", "amount": 500, "reason": "fraudulent",
        }

    def test_other_reason_is_stripped(self):
        """Stripe rejects unknown enum values — we strip our internal 'other'."""
        kw = admin_refunds._build_refund_kwargs("ch_1", None, "other")
        assert "reason" not in kw


# ── account helpers ──────────────────────────────────────────────

class TestParseInvitePayload:
    def test_rejects_missing_email(self):
        with pytest.raises(HTTPException) as exc:
            account._parse_invite_payload({"full_name": "X"})
        assert exc.value.status_code == 400

    def test_rejects_missing_full_name(self):
        with pytest.raises(HTTPException) as exc:
            account._parse_invite_payload({"email": "x@y.com"})
        assert exc.value.status_code == 400

    def test_normalises_role_and_delivery(self):
        p = account._parse_invite_payload({
            "email": "  X@Y.COM ", "full_name": " Test User ",
            "role": "OWNER", "delivery": "magic",
            "allowed_site_ids": ["a", "", "b"],
        })
        assert p["email"] == "x@y.com"
        assert p["full_name"] == "Test User"
        # 'owner' is never assignable via invite, so it normalises to staff
        assert p["role"] == "staff"
        # Unknown delivery falls back to temp_password
        assert p["delivery"] == "temp_password"
        # Empty strings stripped from site list
        assert p["allowed_site_ids"] == ["a", "b"]

    def test_accepts_manager_role(self):
        p = account._parse_invite_payload({
            "email": "m@y.com", "full_name": "Mgr",
            "role": "manager", "delivery": "reset_link",
        })
        assert p["role"] == "manager"
        assert p["delivery"] == "reset_link"


class TestEnforceInviteRole:
    def test_manager_may_only_invite_staff(self):
        with pytest.raises(HTTPException) as exc:
            account._enforce_invite_role(
                {"role": "manager"}, "manager",
            )
        assert exc.value.status_code == 403

    def test_owner_may_invite_anything(self):
        # Should not raise.
        account._enforce_invite_role({"role": "owner"}, "manager")
        account._enforce_invite_role({"role": "owner"}, "staff")


class TestTeamMemberUpdates:
    def test_empty_body_returns_empty_dict(self):
        assert account._team_member_updates({"role": "owner"}, {"role": "staff"}, {}) == {}

    def test_invalid_status_falls_back_to_active(self):
        out = account._team_member_updates({}, {}, {"status": "BANNED"})
        assert out == {"status": "active"}

    def test_full_name_blank_keeps_existing(self):
        out = account._team_member_updates({}, {"full_name": "Old"}, {"full_name": "   "})
        assert out == {"full_name": "Old"}

    def test_manager_promoting_to_manager_blocked(self):
        with pytest.raises(HTTPException) as exc:
            account._team_member_updates(
                {"role": "manager"}, {"role": "staff"}, {"role": "manager"},
            )
        assert exc.value.status_code == 403


class TestSerialiseOrg:
    def test_empty_org_returns_all_fields(self):
        p = account._serialise_org(None)
        # Includes every allowed field, even when org is None
        for k in account.ORG_ALLOWED_FIELDS:
            assert k in p
        assert p["id"] == ""
        assert p["brand_palette"] == []
        assert p["primary_color"] == ""

    def test_primary_color_falls_through_legacy_fields(self):
        # branding.primary_color wins over the other two
        p = account._serialise_org({
            "id": "o-1", "name": "ACME",
            "branding": {"primary_color": "#111111"},
            "primary_brand_colour": "#222222",
            "brand_color": "#333333",
        })
        assert p["primary_color"] == "#111111"

    def test_primary_color_uses_primary_brand_colour_fallback(self):
        p = account._serialise_org({
            "primary_brand_colour": "#222222",
            "brand_color": "#333333",
        })
        assert p["primary_color"] == "#222222"

    def test_primary_color_uses_brand_color_fallback(self):
        p = account._serialise_org({"brand_color": "#333333"})
        assert p["primary_color"] == "#333333"
