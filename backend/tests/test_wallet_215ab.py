"""Iter 215ab — Family Wallet unit tests.

Covers the pure debit helper ``try_wallet_debit_for_invoice`` with a
mocked DB adapter so we don't need a live Mongo fixture.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _make_invoice(total=5000, applied=0, status="draft"):
    return {
        "id": "inv-1",
        "member_id": "m-1",
        "organization_id": "org-1",
        "total_pence": total,
        "wallet_applied_pence": applied,
        "status": status,
        "period": "2026-04",
    }


def test_zero_balance_is_noop():
    from routes.memberships import wallet

    with patch.object(wallet, "_get_balance", new=AsyncMock(return_value=0)), \
         patch.object(wallet.db, "members", SimpleNamespace(update_one=AsyncMock())), \
         patch.object(wallet.db, "membership_class_invoices", SimpleNamespace(update_one=AsyncMock())), \
         patch.object(wallet.db, "wallet_ledger", SimpleNamespace(insert_one=AsyncMock())):
        inv = _make_invoice(total=5000)
        r = asyncio.run(wallet.try_wallet_debit_for_invoice("m-1", inv))
        assert r["applied_pence"] == 0
        assert r["remaining_pence"] == 5000


def test_wallet_fully_covers_invoice():
    from routes.memberships import wallet

    members_update = AsyncMock()
    invoice_update = AsyncMock()
    ledger_insert = AsyncMock()
    with patch.object(wallet, "_get_balance", new=AsyncMock(return_value=6000)), \
         patch.object(wallet.db, "members", SimpleNamespace(update_one=members_update)), \
         patch.object(wallet.db, "membership_class_invoices", SimpleNamespace(update_one=invoice_update)), \
         patch.object(wallet.db, "wallet_ledger", SimpleNamespace(insert_one=ledger_insert)):
        inv = _make_invoice(total=5000)
        r = asyncio.run(wallet.try_wallet_debit_for_invoice("m-1", inv))
        assert r["applied_pence"] == 5000
        assert r["remaining_pence"] == 0
        assert r["status"] == "paid"
        assert r["wallet_balance_after_pence"] == 1000
        # Invoice was flipped to paid
        call = invoice_update.await_args
        sets = call.args[1]["$set"]
        assert sets["status"] == "paid"
        assert sets["paid_via"] == "wallet"


def test_wallet_partial_cover():
    from routes.memberships import wallet

    with patch.object(wallet, "_get_balance", new=AsyncMock(return_value=2000)), \
         patch.object(wallet.db, "members", SimpleNamespace(update_one=AsyncMock())), \
         patch.object(wallet.db, "membership_class_invoices", SimpleNamespace(update_one=AsyncMock())), \
         patch.object(wallet.db, "wallet_ledger", SimpleNamespace(insert_one=AsyncMock())):
        inv = _make_invoice(total=5000)
        r = asyncio.run(wallet.try_wallet_debit_for_invoice("m-1", inv))
        assert r["applied_pence"] == 2000
        assert r["remaining_pence"] == 3000
        assert r["status"] != "paid"
        assert r["wallet_balance_after_pence"] == 0


def test_respects_already_applied_portion():
    """If the invoice already had wallet_applied_pence, the remaining
    owed should exclude that portion."""
    from routes.memberships import wallet

    with patch.object(wallet, "_get_balance", new=AsyncMock(return_value=10000)), \
         patch.object(wallet.db, "members", SimpleNamespace(update_one=AsyncMock())), \
         patch.object(wallet.db, "membership_class_invoices", SimpleNamespace(update_one=AsyncMock())), \
         patch.object(wallet.db, "wallet_ledger", SimpleNamespace(insert_one=AsyncMock())):
        inv = _make_invoice(total=5000, applied=3000)  # only 2000 owed
        r = asyncio.run(wallet.try_wallet_debit_for_invoice("m-1", inv))
        assert r["applied_pence"] == 2000
        assert r["remaining_pence"] == 0
        assert r["status"] == "paid"
        assert r["wallet_balance_after_pence"] == 8000


def test_fully_paid_invoice_returns_noop():
    from routes.memberships import wallet

    with patch.object(wallet, "_get_balance", new=AsyncMock(return_value=5000)), \
         patch.object(wallet.db, "members", SimpleNamespace(update_one=AsyncMock())), \
         patch.object(wallet.db, "membership_class_invoices", SimpleNamespace(update_one=AsyncMock())), \
         patch.object(wallet.db, "wallet_ledger", SimpleNamespace(insert_one=AsyncMock())):
        inv = _make_invoice(total=5000, applied=5000)  # nothing owed
        r = asyncio.run(wallet.try_wallet_debit_for_invoice("m-1", inv))
        assert r["applied_pence"] == 0
        assert r["remaining_pence"] == 0
