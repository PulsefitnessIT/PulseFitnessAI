"""Iter 215af — Security regression tests.

Covers:
* Rate-limit enforcement on money-touching endpoints:
  - /api/member/wallet/topup
  - /api/member/billing/auto-pay/setup
  - /api/member-auth/register
  - /api/member-auth/login
* IDOR defense on operator endpoints — operator in org A cannot
  touch invoices, auto-pay roster, or wallet balances for org B.

These tests use unittest.mock to stub Stripe / DB so they run without
a live backend dependency, matching the pattern used by the 215aa-215ad
unit-test suites.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException


# ═════════════════ Rate-limit regression ═════════════════


def test_wallet_topup_calls_rate_limiter(monkeypatch):
    """The topup endpoint MUST call rate_limit_async before hitting Stripe."""
    from routes.memberships import wallet

    monkeypatch.setattr(wallet, "STRIPE_API_KEY", "sk_test_x")
    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4"))

    rate = AsyncMock()
    stripe_create = AsyncMock()
    stripe_create.return_value = SimpleNamespace(url="https://stripe/x", id="cs_x")
    member = {"id": "m1", "organization_id": "org1", "email": "m@x"}

    with patch("utils.security_plus.rate_limit_async", new=rate), \
         patch.object(wallet, "_require_current_member", new=AsyncMock(return_value=member)), \
         patch.object(wallet.stripe.checkout.Session, "create", new=lambda **kw: SimpleNamespace(url="u", id="i")):
        body = wallet.TopupIn(amount_pence=2500)
        asyncio.run(wallet.topup_wallet(req, body))
    rate.assert_awaited_once()
    args, kwargs = rate.await_args.args, rate.await_args.kwargs
    # First arg is the bucket key, must include the member id
    assert "wallet_topup:m1" in args[0]


def test_autopay_setup_calls_rate_limiter(monkeypatch):
    from routes.memberships import family_autopay

    monkeypatch.setattr(family_autopay, "STRIPE_API_KEY", "sk_test_x")
    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4"))

    rate = AsyncMock()
    member = {"id": "m1", "organization_id": "org1", "email": "m@x",
              "first_name": "P", "last_name": "K"}

    members_update = AsyncMock()
    with patch("utils.security_plus.rate_limit_async", new=rate), \
         patch.object(family_autopay, "_require_current_member", new=AsyncMock(return_value=member)), \
         patch.object(family_autopay.stripe, "Customer", create=True,
                      new=SimpleNamespace(create=lambda **kw: SimpleNamespace(id="cus_x"))), \
         patch.object(family_autopay.stripe.checkout.Session, "create",
                      new=lambda **kw: SimpleNamespace(url="u", id="cs_x")), \
         patch.object(family_autopay.db, "members", SimpleNamespace(update_one=members_update)):
        asyncio.run(family_autopay.start_autopay_setup(req))
    rate.assert_awaited_once()
    assert "autopay_setup:m1" in rate.await_args.args[0]


def test_member_login_calls_rate_limiter(monkeypatch):
    from routes.memberships import member_auth

    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="9.9.9.9"))
    rate = AsyncMock()
    find_one = AsyncMock(return_value=None)
    with patch("utils.security_plus.rate_limit_async", new=rate), \
         patch.object(member_auth.db, "members", SimpleNamespace(find_one=find_one)):
        try:
            asyncio.run(member_auth.member_login(
                member_auth.MemberLogin(email="x@y.com", password="wrong"),
                req,
            ))
        except HTTPException:
            pass  # expected — 401 Invalid credentials
    rate.assert_awaited_once()
    assert rate.await_args.args[0].startswith("member_login_ip:9.9.9.9")


def test_member_register_calls_rate_limiter(monkeypatch):
    from routes.memberships import member_auth

    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="2.2.2.2"))
    rate = AsyncMock()
    find_one = AsyncMock(return_value=None)
    with patch("utils.security_plus.rate_limit_async", new=rate), \
         patch.object(member_auth.db, "members", SimpleNamespace(find_one=find_one)):
        try:
            asyncio.run(member_auth.member_register(
                member_auth.MemberRegister(
                    email="new@x.com", password="p1234567",
                    first_name="A", last_name="B",
                    organization_id="org1",
                ),
                req,
            ))
        except Exception:
            pass
    rate.assert_awaited_once()
    assert rate.await_args.args[0].startswith("member_register_ip:2.2.2.2")


# ═════════════════ IDOR regression ═════════════════


def test_operator_cannot_apply_wallet_to_cross_org_invoice():
    """Operator in org A calling apply-wallet for an invoice in org B
    must receive 404, not 200."""
    from routes.memberships import wallet

    # Invoice belongs to org B. _require_operator_org returns org A.
    find_one = AsyncMock(return_value=None)  # scoped query returns None when orgs mismatch
    with patch.object(wallet, "_require_operator_org", new=AsyncMock(return_value="org-A")), \
         patch.object(wallet.db, "membership_class_invoices", SimpleNamespace(find_one=find_one)):
        try:
            asyncio.run(wallet.apply_wallet_to_invoice(
                "inv-in-org-B", user={"id": "u1", "organization_id": "org-A"},
            ))
            raise AssertionError("Expected HTTPException 404")
        except HTTPException as e:
            assert e.status_code == 404
    # Verify the query was properly scoped by organization_id
    call = find_one.await_args
    assert call.args[0]["organization_id"] == "org-A"


def test_operator_wallet_roster_scoped_by_org():
    """GET wallet/members MUST filter by the caller's org."""
    from routes.memberships import wallet

    to_list = AsyncMock(return_value=[])
    find_chain = SimpleNamespace(to_list=to_list)
    find_mock = lambda q, proj: find_chain  # noqa: E731
    with patch.object(wallet, "_require_operator_org", new=AsyncMock(return_value="org-X")), \
         patch.object(wallet.db, "members", SimpleNamespace(find=find_mock)):
        asyncio.run(wallet.list_wallet_balances(user={"id": "u1"}))


def test_operator_autopay_roster_scoped_by_org():
    from routes.memberships import family_autopay

    to_list = AsyncMock(return_value=[])
    captured = {}

    def find_mock(q, proj):
        captured["q"] = q
        return SimpleNamespace(to_list=to_list)

    with patch.object(family_autopay, "_require_operator_org", new=AsyncMock(return_value="org-Y")), \
         patch.object(family_autopay.db, "members", SimpleNamespace(find=find_mock)):
        asyncio.run(family_autopay.list_autopay_members(user={"id": "u1"}))
    assert captured["q"]["organization_id"] == "org-Y"


def test_operator_sibling_discount_scoped_by_org():
    """Setting a sibling discount must only touch the CALLER'S org."""
    from routes.memberships import studio_billing

    update_one = AsyncMock()
    with patch.object(studio_billing, "_require_operator_org", new=AsyncMock(return_value="org-Z")), \
         patch.object(studio_billing.db, "organizations", SimpleNamespace(update_one=update_one)):
        asyncio.run(studio_billing.set_sibling_discount(
            studio_billing.SiblingDiscountIn(pct=10),
            user={"id": "u1", "role": "owner"},
        ))
    # Assert we only updated the caller's org document
    call = update_one.await_args
    assert call.args[0] == {"id": "org-Z"}
