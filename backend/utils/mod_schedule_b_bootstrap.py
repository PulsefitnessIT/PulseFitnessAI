"""Make the approved MOD Schedule B (LSLDC0186 Amdt 3, Year 4 prices) live in any environment that lacks it.

Approved by Pulse Fitness management on 25/11/2026. The workbook is held in private object storage (not in
the repository); its SHA-256 is pinned so only that exact file can be applied.
"""
import hashlib
import logging
import os
import uuid

from utils.database import APP_NAME, db, get_object

log = logging.getLogger(__name__)

OBJECT_PATH = f"{APP_NAME}/restricted/mod-schedule-b/LSLDC0186-amdt3-year4.xlsx"
SHA256 = "3944e545b98fa5261e41b780caa02169d874ba48260bd2b98ae514703b6630d9"
EFFECTIVE_FROM = "2026-11-25"
AUTHORITY = "Approved MOD service prices — LSLDC0186 Schedule of Requirement Amdt 3, Year 4 (Pulse Fitness management, 25/11/2026)"
APPROVER = {"full_name": "Pulse Fitness management (instruction 25/11/2026)", "email": ""}


async def ensure_year4_schedule_b() -> str:
    if os.environ.get("MOD_SCHEDULE_B_BOOTSTRAP", "").lower() == "off":
        return "disabled"
    if await db.mod_sor_price_lists.find_one({"sha256": SHA256, "status": {"$in": ["live", "superseded"]}}, {"_id": 1}):
        return "already_applied"
    # A later genuine (non-test) approval made by a manager always wins.
    if await db.mod_sor_price_lists.find_one({"status": "live", "synthetic": {"$ne": True},
                                               "filename": {"$nin": ["sor.xlsx", None]}}, {"_id": 1}):
        return "other_live_list"
    from routes.mod_ops_quotes import approve_price_list
    from utils.mod_quote_engine import parse_schedule_b
    content, _ = get_object(OBJECT_PATH)
    if hashlib.sha256(content).hexdigest() != SHA256:
        log.error("[mod-sor-bootstrap] stored workbook does not match the approved file — not applied")
        return "hash_mismatch"
    parsed = parse_schedule_b(content)
    pl = {"id": str(uuid.uuid4()), "status": "preview", "filename": "LSLDC0186 Schedule of Requirement Amdt 3 yr4 pricing proposal.xlsx",
          "sha256": SHA256, "entries": parsed["entries"], "issues": parsed["issues"], "uploaded_by": APPROVER["full_name"],
          "uploaded_at": EFFECTIVE_FROM, "synthetic": False, "price_year": parsed.get("price_year"), "authority": AUTHORITY}
    await db.mod_sor_price_lists.insert_one(dict(pl))
    res = await approve_price_list(pl, EFFECTIVE_FROM, None, APPROVER)
    log.info("[mod-sor-bootstrap] Year 4 Schedule B live: %s", res)
    return "applied"
