"""Seed Marketing (Apex) + Engineer van stock so the last two deck slides
can use real screenshots. Idempotent."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

APEX = "apex-demo-org"
ENG_ORG = "9fa701ef-5cc2-4db6-8795-bbfd2c85179d"  # engineer.smoke org (GymAxis Admin)
ENG_ID = "7cc0455f-3206-4069-ab95-6db51276a553"


def main():
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    def iso(d=None):
        return (d or now).isoformat()
    def nid():
        return str(uuid.uuid4())

    # ─────────────── MARKETING (Apex) ───────────────
    db.marketing_audiences.delete_many({"organization_id": APEX, "demo_seed_apex": True})
    db.marketing_campaigns.delete_many({"organization_id": APEX, "demo_seed_apex": True})

    auds = [
        ("Lapsed members", 214), ("Active members", 1180),
        ("New leads", 96), ("Class no-shows", 58),
    ]
    aud_ids = {}
    for name, size in auds:
        aid = nid()
        aud_ids[name] = aid
        db.marketing_audiences.insert_one({
            "id": aid, "organization_id": APEX, "created_by": "apex-owner",
            "name": name, "type": "dynamic",
            "rules": {"op": "and", "conditions": []},
            "estimated_size": size, "computed_at": iso(), "tags": [],
            "created_at": iso(now - timedelta(days=20)), "updated_at": iso(),
            "demo_seed_apex": True,
        })

    def variant(vid, name, subject):
        return {"id": vid, "name": name, "subject": subject, "body_html": "<p>…</p>", "weight": 1}

    CAMPS = [
        # name, status, audience, sent, opened, clicked, converted, revenue, days_ago, two_variants
        ("Win-back — Lapsed members", "sent", "Lapsed members", 214, 103, 31, 12, 588, 4, True),
        ("New Year Challenge launch", "sent", "Active members", 1180, 642, 214, 73, 4015, 11, True),
        ("Spring class timetable refresh", "scheduled", "Active members", 0, 0, 0, 0, 0, -2, False),
        ("Refer-a-friend boost", "sent", "New leads", 96, 51, 19, 8, 392, 6, False),
        ("Win back no-shows", "draft", "Class no-shows", 0, 0, 0, 0, 0, 0, True),
    ]
    for (name, status, aud, sent, opened, clicked, conv, rev, days_ago, ab) in CAMPS:
        if ab:
            variants = [variant("a", "Variant A", name), variant("b", "Variant B", name)]
            mbv = {
                "a": {"sent": sent // 2, "opened": int(opened * 0.45), "clicked": int(clicked * 0.4), "bounced": 1},
                "b": {"sent": sent - sent // 2, "opened": opened - int(opened * 0.45),
                      "clicked": clicked - int(clicked * 0.4), "bounced": 2},
            }
        else:
            variants = [variant("default", "Default", name)]
            mbv = {"default": {"sent": sent, "opened": opened, "clicked": clicked, "bounced": 3}}
        created = now - timedelta(days=abs(days_ago) + 1)
        sent_at = iso(now - timedelta(days=days_ago)) if status == "sent" else None
        sched = {}
        if status == "scheduled":
            sched = {"send_at": iso(now + timedelta(days=2, hours=3))}
        db.marketing_campaigns.insert_one({
            "id": nid(), "organization_id": APEX, "created_by": "apex-owner",
            "name": name, "status": status, "channel": "email",
            "audience_id": aud_ids[aud], "audience_inline": None, "dynamic_list_id": None,
            "content": {"subject": name, "body_html": "<p>…</p>"},
            "variants": variants,
            "ab_test": {"enabled": ab, "sample_pct": 30, "metric": "opened",
                        "decide_after_hours": 4} if ab else {"enabled": False},
            "winner_variant_id": "a" if (ab and status == "sent") else None,
            "winner_decided_at": sent_at if (ab and status == "sent") else None,
            "pending_recipients": [], "schedule": sched,
            "tracking": {"utm_source": "gymaxis_marketing"},
            "metrics": {"sent": sent, "delivered": max(sent - 3, 0), "opened": opened,
                        "clicked": clicked, "bounced": 3, "converted": conv, "revenue_gbp": rev},
            "metrics_by_variant": mbv,
            "created_at": iso(created), "updated_at": iso(), "sent_at": sent_at,
            "demo_seed_apex": True,
        })

    # ─────────────── ENGINEER VAN STOCK ───────────────
    db.svc_van_stock.delete_many({"engineer_id": ENG_ID, "demo_seed_apex": True})
    db.svc_part_movements.delete_many({"engineer_id": ENG_ID, "demo_seed_apex": True})

    VAN = [
        # sku, qty, min_qty, bin
        ("000-0171", 6, 2, "A1"),    # Belt — in stock
        ("10012", 8, 3, "A2"),       # Bearing 6205ZZ
        ("07DT-INTXX-01", 1, 3, "C1"),  # 7in LCD Tread Console — LOW
        ("120-154-1", 14, 4, "B2"),  # End Cap Roller
        ("100-118-2", 0, 2, "B4"),   # Cable Splice — OUT
        ("26/1350", 2, 1, "D1"),     # Motor Assby
        ("002114", 4, 2, "C3"),      # Back Pad
        ("100-208", 1, 2, "B1"),     # Weight Stack Sensor — LOW
        ("003-1508", 3, 1, "D2"),    # Bottom Bracket
    ]
    for sku, qty, minq, bin_loc in VAN:
        db.svc_van_stock.insert_one({
            "id": nid(), "organization_id": ENG_ORG, "engineer_id": ENG_ID,
            "part_sku": sku, "qty": qty, "min_qty": minq, "bin_location": bin_loc,
            "last_replenished_at": iso(now - timedelta(days=3)),
            "created_at": iso(), "updated_at": iso(), "demo_seed_apex": True,
        })

    # a few consume movements → usage + history populated
    USAGE = [("000-0171", 2, 1), ("10012", 3, 2), ("120-154-1", 4, 5), ("002114", 1, 8)]
    for sku, qty, days in USAGE:
        db.svc_part_movements.insert_one({
            "id": nid(), "organization_id": ENG_ORG, "engineer_id": ENG_ID,
            "part_sku": sku, "movement_type": "consume", "qty": qty,
            "case_reference": f"JOB-{1000 + days}", "at": iso(now - timedelta(days=days)),
            "demo_seed_apex": True,
        })

    print("Marketing+VanStock seed:")
    print("  apex audiences:", db.marketing_audiences.count_documents({"organization_id": APEX}))
    print("  apex campaigns:", db.marketing_campaigns.count_documents({"organization_id": APEX}))
    print("  van stock rows:", db.svc_van_stock.count_documents({"engineer_id": ENG_ID}))


if __name__ == "__main__":
    main()
