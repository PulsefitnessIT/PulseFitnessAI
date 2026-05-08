"""End-to-end test for the True 1:1 Churn Rescue pipeline.

Creates a synthetic org with members exhibiting each of the 6 churn
signals, runs the detector, and validates that each signal type is
correctly identified.

Run:  cd /app/backend && python -m pytest tests/test_churn_rescue.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# Ensure /app/backend is on the path so utils.* imports work when run by pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.churn_signals import detect_churn_signals  # noqa: E402
from utils.database import db  # noqa: E402

ORG_ID = "test-churn-org-001"


def _iso(dt):
    return dt.isoformat()


async def _wipe_test_data():
    await asyncio.gather(
        db.members.delete_many({"organization_id": ORG_ID}),
        db.member_checkins.delete_many({"organization_id": ORG_ID}),
        db.bookings.delete_many({"organization_id": ORG_ID}),
        db.payment_transactions.delete_many({"organization_id": ORG_ID}),
        db.class_occurrences.delete_many({"organization_id": ORG_ID}),
        db.class_templates.delete_many({"organization_id": ORG_ID}),
        db.marketing_churn_rescues.delete_many({"organization_id": ORG_ID}),
    )


async def _seed():
    """Create 6 members, one per signal."""
    now = datetime.now(timezone.utc)

    # Class templates so we can derive class_name
    spin_tpl = "test-tpl-spin"
    yoga_tpl = "test-tpl-yoga"
    await db.class_templates.insert_many([
        {"id": spin_tpl, "name": "Spin", "organization_id": ORG_ID},
        {"id": yoga_tpl, "name": "Yoga Flow", "organization_id": ORG_ID},
    ])

    # Members
    members = [
        {
            "id": "m-payment",     "first_name": "Pay", "last_name": "Failed",
            "email": "pay@x.com", "status": "active",
            "created_at": _iso(now - timedelta(days=200)),
            "lifetime_value_pence": 50000,
        },
        {
            "id": "m-frozen",      "first_name": "Fro", "last_name": "Zen",
            "email": "frozen@x.com", "status": "frozen",
            "created_at": _iso(now - timedelta(days=400)),
            "lifetime_value_pence": 80000,
        },
        {
            "id": "m-cancel",      "first_name": "Can", "last_name": "Cell",
            "email": "cancel@x.com", "status": "active",
            "created_at": _iso(now - timedelta(days=120)),
            "lifetime_value_pence": 30000,
        },
        {
            "id": "m-affinity",    "first_name": "Aff", "last_name": "Inity",
            "email": "affinity@x.com", "status": "active",
            "created_at": _iso(now - timedelta(days=300)),
            "lifetime_value_pence": 100000,
        },
        {
            "id": "m-frequency",   "first_name": "Fre", "last_name": "Quency",
            "email": "freq@x.com", "status": "active",
            "created_at": _iso(now - timedelta(days=180)),
            "lifetime_value_pence": 40000,
        },
        {
            "id": "m-lapsed",      "first_name": "Lap", "last_name": "Sed",
            "email": "lapsed@x.com", "status": "active",
            "created_at": _iso(now - timedelta(days=90)),
            "lifetime_value_pence": 20000,
        },
        # Healthy member — should NOT be flagged
        {
            "id": "m-healthy",     "first_name": "Hea", "last_name": "Lthy",
            "email": "healthy@x.com", "status": "active",
            "created_at": _iso(now - timedelta(days=200)),
            "lifetime_value_pence": 60000,
        },
    ]
    for m in members:
        m["organization_id"] = ORG_ID
    await db.members.insert_many(members)

    # ── Signal 1: payment_failure (recent failed txn)
    await db.payment_transactions.insert_one({
        "id": "ptx-1", "organization_id": ORG_ID, "member_id": "m-payment",
        "payment_status": "failed",
        "created_at": _iso(now - timedelta(days=5)),
    })

    # ── Signal 3: late_cancel_streak — last 2 bookings were cancelled / no-show
    occ_cancel_a = "occ-cancel-a"
    occ_cancel_b = "occ-cancel-b"
    await db.class_occurrences.insert_many([
        {"id": occ_cancel_a, "organization_id": ORG_ID, "template_id": spin_tpl,
         "starts_at": _iso(now - timedelta(days=3))},
        {"id": occ_cancel_b, "organization_id": ORG_ID, "template_id": spin_tpl,
         "starts_at": _iso(now - timedelta(days=7))},
    ])
    await db.bookings.insert_many([
        {"id": "bkg-c1", "organization_id": ORG_ID, "member_id": "m-cancel",
         "occurrence_id": occ_cancel_a, "status": "no_show",
         "booked_at": _iso(now - timedelta(days=3))},
        {"id": "bkg-c2", "organization_id": ORG_ID, "member_id": "m-cancel",
         "occurrence_id": occ_cancel_b, "status": "late_cancel",
         "booked_at": _iso(now - timedelta(days=7))},
    ])

    # ── Signal 4: class_affinity_drop — booked Spin 4× in 90d, none in last 25d
    occs_aff = []
    for i, days_ago in enumerate([60, 50, 40, 28]):
        occ_id = f"occ-aff-{i}"
        await db.class_occurrences.insert_one({
            "id": occ_id, "organization_id": ORG_ID, "template_id": spin_tpl,
            "starts_at": _iso(now - timedelta(days=days_ago)),
        })
        occs_aff.append((occ_id, days_ago))
    await db.bookings.insert_many([
        {"id": f"bkg-aff-{i}", "organization_id": ORG_ID,
         "member_id": "m-affinity", "occurrence_id": occ_id, "status": "attended",
         "booked_at": _iso(now - timedelta(days=days))}
        for i, (occ_id, days) in enumerate(occs_aff)
    ])

    # ── Signal 5: frequency_drop — 5 visits in 14-28d window, 1 in last 14d
    for i, d in enumerate([26, 24, 22, 18, 15]):
        await db.member_checkins.insert_one({
            "organization_id": ORG_ID, "member_id": "m-frequency",
            "at": _iso(now - timedelta(days=d)),
        })
    await db.member_checkins.insert_one({
        "organization_id": ORG_ID, "member_id": "m-frequency",
        "at": _iso(now - timedelta(days=10)),
    })

    # ── Signal 6: lapsed_visit — joined 90d ago, last visit 30d ago
    await db.member_checkins.insert_one({
        "organization_id": ORG_ID, "member_id": "m-lapsed",
        "at": _iso(now - timedelta(days=30)),
    })

    # Healthy: 5 visits in last 14d, no signal should trigger
    for d in [13, 10, 7, 4, 1]:
        await db.member_checkins.insert_one({
            "organization_id": ORG_ID, "member_id": "m-healthy",
            "at": _iso(now - timedelta(days=d)),
        })


def test_churn_signal_detection_end_to_end():
    """Sync wrapper that drives the async detector via asyncio.run."""

    async def _run():
        await _wipe_test_data()
        try:
            await _seed()
            results = await detect_churn_signals(ORG_ID, limit=50)
            by_member = {r["member_id"]: r for r in results}

            assert "m-payment"   in by_member, f"payment_failure not detected — got {list(by_member)}"
            assert by_member["m-payment"]["signal"] == "payment_failure"

            assert "m-frozen"    in by_member
            assert by_member["m-frozen"]["signal"] == "frozen_membership"

            assert "m-cancel"    in by_member
            assert by_member["m-cancel"]["signal"] == "late_cancel_streak"
            assert by_member["m-cancel"]["last_class_name"] == "Spin"

            assert "m-affinity"  in by_member
            assert by_member["m-affinity"]["signal"] == "class_affinity_drop"
            assert by_member["m-affinity"]["last_class_name"] == "Spin"

            assert "m-frequency" in by_member
            assert by_member["m-frequency"]["signal"] == "frequency_drop"
            assert by_member["m-frequency"]["visits_14_28d"] == 5
            assert by_member["m-frequency"]["visits_14d"] == 1

            assert "m-lapsed"    in by_member
            assert by_member["m-lapsed"]["signal"] == "lapsed_visit"
            assert by_member["m-lapsed"]["days_since_last_visit"] == 30

            assert "m-healthy" not in by_member, (
                "Healthy member was incorrectly flagged — "
                f"got signal {by_member.get('m-healthy', {}).get('signal')}"
            )

            sev = [r["signal_severity"] for r in results]
            assert sev == sorted(sev, reverse=True)
        finally:
            await _wipe_test_data()

    asyncio.run(_run())
