"""Seed a Staff Portal demo employee + line manager on iso-demo-org.

Run: python scripts/seed_staff_portal_demo.py  (from /app/backend, env sourced)
Idempotent — wipes SPDEMO_* rows first.
"""
import asyncio
import uuid
from datetime import datetime, timezone, date, timedelta

from utils.database import db
from utils.auth import hash_password

ORG = "iso-demo-org"
DEPT = "Operations"


def _now():
    return datetime.now(timezone.utc).isoformat()


async def main():
    # Clean previous demo rows
    for coll in ["users", "staff_members", "staff_onboarding_cases", "staff_shifts",
                 "staff_leave_requests", "staff_access_provisions"]:
        await db[coll].delete_many({"_spdemo": True})

    # 1) Line manager (a real login) — SPDEMO manager
    mgr_uid = "SPDEMO_mgr_user"
    mgr_sid = "SPDEMO_mgr_staff"
    await db.users.insert_one({
        "id": mgr_uid, "_spdemo": True, "organization_id": ORG,
        "email": "portal.manager@pulsedemo.test", "full_name": "Morgan Lee (Manager)",
        "role": "manager", "account_type": "full", "password": hash_password("Manager123!"),
        "allowed_site_ids": [], "created_at": _now(),
    })
    await db.staff_members.insert_one({
        "id": mgr_sid, "_spdemo": True, "organization_id": ORG, "user_id": mgr_uid,
        "email": "portal.manager@pulsedemo.test", "full_name": "Morgan Lee (Manager)",
        "primary_role": "Operations Manager", "department": DEPT, "active": True,
        "lifecycle_stage": "employee", "created_at": _now(),
    })

    # 2) Employee (staff portal)
    emp_uid = "SPDEMO_emp_user"
    emp_sid = "SPDEMO_emp_staff"
    await db.users.insert_one({
        "id": emp_uid, "_spdemo": True, "organization_id": ORG,
        "email": "portal.staff@pulsedemo.test", "full_name": "Alex Rivera",
        "role": "staff", "account_type": "recruit", "password": hash_password("Staff123!"),
        "allowed_site_ids": [], "created_at": _now(), "is_recruit_portal": True,
    })
    await db.staff_members.insert_one({
        "id": emp_sid, "_spdemo": True, "organization_id": ORG, "user_id": emp_uid,
        "email": "portal.staff@pulsedemo.test", "full_name": "Alex Rivera",
        "primary_role": "Fitness Instructor", "department": DEPT, "active": True,
        "lifecycle_stage": "employee", "activated_at": _now(),
        "line_manager_staff_id": mgr_sid, "line_manager_name": "Morgan Lee (Manager)",
    })
    case_id = "SPDEMO_case"
    await db.staff_onboarding_cases.insert_one({
        "id": case_id, "_spdemo": True, "organization_id": ORG, "staff_id": emp_sid,
        "status": "complete", "submitted": True,
        "employment_proposal": {"job_title": "Fitness Instructor", "department": DEPT,
                                "site": "Demo Head Office", "holiday_entitlement": "28 days including bank holidays",
                                "line_manager": "Morgan Lee (Manager)"},
        "offer": {"status": "accepted", "rendered": "Offer letter…"},
        "contract": {"status": "fully_signed", "rendered": "Contract…"},
        "created_at": _now(),
    })
    await db.staff_access_provisions.insert_one({
        "id": str(uuid.uuid4()), "_spdemo": True, "organization_id": ORG, "staff_id": emp_sid,
        "line_manager_staff_id": mgr_sid, "status": "awaiting_manager", "granted_modules": [],
        "updated_at": _now(),
    })

    # 3) Upcoming shifts for the employee
    for i in range(1, 5):
        d = (date.today() + timedelta(days=i)).isoformat()
        await db.staff_shifts.insert_one({
            "id": f"SPDEMO_shift_{i}", "_spdemo": True, "organization_id": ORG, "staff_id": emp_sid,
            "date": d, "start_time": "09:00", "end_time": "17:00", "role": "fitness_instructor",
            "status": "scheduled", "created_at": _now(),
        })

    # 4) A pending holiday request for the employee
    hs = (date.today() + timedelta(days=20)).isoformat()
    he = (date.today() + timedelta(days=24)).isoformat()
    await db.staff_leave_requests.insert_one({
        "id": "SPDEMO_leave_1", "_spdemo": True, "organization_id": ORG, "staff_id": emp_sid,
        "status": "pending", "leave_type": "holiday", "start_date": hs, "end_date": he,
        "reason": "Family trip", "created_at": _now(),
    })

    # 5) A department colleague with an APPROVED holiday (team calendar)
    col_sid = "SPDEMO_col_staff"
    await db.staff_members.insert_one({
        "id": col_sid, "_spdemo": True, "organization_id": ORG, "user_id": "SPDEMO_col_user",
        "email": "portal.colleague@pulsedemo.test", "full_name": "Jamie Fox",
        "primary_role": "Receptionist", "department": DEPT, "active": True,
        "lifecycle_stage": "employee", "created_at": _now(),
    })
    cs = (date.today() + timedelta(days=10)).isoformat()
    ce = (date.today() + timedelta(days=12)).isoformat()
    await db.staff_leave_requests.insert_one({
        "id": "SPDEMO_leave_2", "_spdemo": True, "organization_id": ORG, "staff_id": col_sid,
        "status": "approved", "leave_type": "holiday", "start_date": cs, "end_date": ce,
        "created_at": _now(),
    })

    print("Seeded Staff Portal demo:")
    print("  Employee login  : portal.staff@pulsedemo.test / Staff123!  (/staff-login → /staff-portal)")
    print("  Manager login   : portal.manager@pulsedemo.test / Manager123!  (main app; Staffing → Team Access)")
    print(f"  Case id         : {case_id}  (HR: owner@isodemo.com can assign line manager)")


if __name__ == "__main__":
    asyncio.run(main())
