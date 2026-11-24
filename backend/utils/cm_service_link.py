"""Contractual PPM obligations ↔ Service Desk bookings ↔ verified completions.

Contract Management owns the obligation (``crm2_afs_service_schedules.visits[]``),
Service Desk owns the booking/engineer work (``svc_cases``), Sicon evidence arrives
through the existing inbound worker onto those cases and ``sicon_external_links``.
This module only links them by stable ids — it never copies or invents bookings.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from utils.cm_dates import parse_date
from utils.database import db

DONE_CASE = {"repaired", "awaiting_sign_off", "closed", "invoiced"}
CANCELLED_CASE = {"rejected", "cancelled"}
FINAL_VISIT = {"completed", "verified", "cancelled", "excluded"}
BOOK_AHEAD_DAYS = 60
_NS = uuid.UUID("6f1c8f8e-3c1b-4d6a-9a52-0f7d5e2a9c11")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def obligation_id(contract_id: str, year, visit_no, site_id) -> str:
    """Deterministic, so regenerating a schedule keeps the same obligation."""
    return str(uuid.uuid5(_NS, f"{contract_id}|{year}|{visit_no}|{site_id or '*'}"))


def site_scopes(asset_register: list) -> tuple[dict, list]:
    """{site_id: [equipment ids]} for priced assets + assets with no site (scope unclear)."""
    by_site, unsited = {}, []
    for a in asset_register or []:
        if not a.get("id") or float(a.get("annual") or 0) <= 0:
            continue
        if a.get("site_id"):
            by_site.setdefault(a["site_id"], []).append(a["id"])
        else:
            unsited.append(a["id"])
    return by_site, unsited


def plan_obligations(contract_id: str, ag: dict, planned: list) -> list:
    """Expand contract visits to one obligation per covered site (never assume a
    contract-wide visit fulfils every site). Approved ``service_dates`` win."""
    approved = sorted(d for d in (ag.get("service_dates") or []) if parse_date(d))
    if approved:
        start = parse_date(ag.get("start_date"))
        rows, per_year = [], {}
        for d in approved:
            y = max(1, ((parse_date(d) - start).days // 365) + 1) if start else 1
            per_year[y] = per_year.get(y, 0) + 1
            rows.append({"planned_date": d, "status": "planned", "visit_no": per_year[y], "year": y,
                         "date_basis": "agreement"})
        planned = rows
    by_site, unsited = site_scopes(ag.get("asset_register"))
    scopes = [(s, ids) for s, ids in by_site.items()] or [(None, unsited)]
    out = []
    for v in planned:
        for site_id, ids in scopes:
            out.append({**v, "obligation_id": obligation_id(contract_id, v["year"], v["visit_no"], site_id),
                        "scope": "site" if site_id else "contract", "site_id": site_id, "equipment_ids": ids,
                        "date_basis": v.get("date_basis") or "calendar"})
    if unsited and by_site:
        for v in out:
            v["scope_review"] = f"{len(unsited)} covered machine(s) have no site — confirm which visit covers them."
    return out


def merge_obligations(contract_id: str, existing: list, planned: list) -> list:
    """Preserve every booked/linked/completed/excluded visit and its evidence; only
    re-plan untouched ones. Legacy visits get a stable id without changing status."""
    single_site = len({p.get("site_id") for p in planned}) == 1
    kept = []
    for v in existing or []:
        if (v.get("status") or "planned") == "planned" and not v.get("case_id") and not v.get("history"):
            continue
        v = dict(v)
        if not v.get("site_id") and single_site and planned:
            v.setdefault("site_id", planned[0].get("site_id"))
            v.setdefault("equipment_ids", planned[0].get("equipment_ids"))
            v.setdefault("scope", planned[0].get("scope"))
        if not v.get("obligation_id"):
            v["obligation_id"] = obligation_id(contract_id, v.get("year"), v.get("visit_no"), v.get("site_id"))
            if not single_site and not v.get("site_id"):
                v["scope_review"] = "Recorded before site-level planning — confirm which site this visit covered."
        kept.append(v)
    keys = {(v.get("year"), v.get("visit_no"), v.get("site_id")) for v in kept}
    loose = {(v.get("year"), v.get("visit_no")) for v in kept if not v.get("site_id")}
    fresh = [p for p in planned if (p["year"], p["visit_no"], p.get("site_id")) not in keys
             and not (single_site and (p["year"], p["visit_no"]) in loose)]
    return sorted(kept + fresh, key=lambda v: (v.get("planned_date") or "", v.get("site_id") or ""))


def backfill_ids(contract_id: str, visits: list, by_site: dict) -> list:
    """Give legacy visits a stable id/scope without touching status or history."""
    out = []
    for v in visits or []:
        v = dict(v)
        if not v.get("site_id") and len(by_site) == 1:
            sid, ids = next(iter(by_site.items()))
            v.update({"site_id": sid, "equipment_ids": v.get("equipment_ids") or ids, "scope": v.get("scope") or "site"})
        elif not v.get("site_id") and len(by_site) > 1 and not v.get("scope_review"):
            v["scope_review"] = "Recorded before site-level planning — confirm which site this visit covers."
        if not v.get("obligation_id"):
            v["obligation_id"] = obligation_id(contract_id, v.get("year"), v.get("visit_no"), v.get("site_id"))
        out.append(v)
    return out


# ─────────────────────────────────────────── evidence

def completion_date(case: dict) -> tuple[str | None, str]:
    """Actual completion only — never created/assigned/planned dates."""
    rep = case.get("engineer_report") if isinstance(case.get("engineer_report"), dict) else {}
    for val, src in ((case.get("sicon_completed_at"), "sicon"), (case.get("completed_at"), "service_desk"),
                     (rep.get("completed_at"), "engineer_report"), (case.get("closed_at"), "service_desk_closed")):
        if val:
            return str(val)[:10], src
    return None, ""


async def _machines(case_id: str) -> list:
    return await db.svc_work_visit_machines.find(
        {"case_id": case_id}, {"_id": 0, "asset_id": 1, "asset_serial": 1, "serviced": 1}).to_list(500)


async def _sicon_ref(case: dict) -> str | None:
    if case.get("sicon_case_id"):
        return str(case["sicon_case_id"])
    link = await db.sicon_external_links.find_one(
        {"pulse_entity_id": case["id"], "pulse_entity_type": {"$in": ["svc_case", "case"]}},
        {"_id": 0, "external_id": 1})
    return (link or {}).get("external_id")


async def evaluate_completion(case: dict, required: list) -> dict:
    """Is this case verified evidence for the obligation? Returns status + reason."""
    if (case.get("case_type") or "").lower() != "ppm":
        return {"ok": False, "reason": "not_ppm"}
    day, source = completion_date(case)
    rows = await _machines(case["id"])
    serviced = {r.get("asset_id") for r in rows if r.get("serviced")}
    ev = {"case_id": case["id"], "case_reference": case.get("reference"), "completed_date": day,
          "date_source": source, "engineer_name": case.get("assigned_engineer_name") or "",
          "engineer_id": case.get("assigned_engineer_id") or "",
          "machines_serviced": sorted(x for x in serviced if x), "machines_required": sorted(required or []),
          "report": bool(case.get("engineer_report")), "sicon_ref": await _sicon_ref(case),
          "certificate_id": case.get("service_certificate_id") or case.get("certificate_id")}
    if not ev["report"]:
        return {"ok": False, "reason": "report_missing", "evidence": ev}
    if not day:
        return {"ok": False, "reason": "date_missing", "evidence": ev}
    if required:
        missing = set(required) - serviced
        if missing:
            return {"ok": False, "reason": "partial", "evidence": {**ev, "machines_missing": sorted(missing)}}
    return {"ok": True, "evidence": ev}


# ─────────────────────────────────────────── matching

def _window(v: dict, per_year: int) -> tuple[str, str]:
    d = parse_date(v.get("planned_date")) or datetime.now(timezone.utc).date()
    half = max(45, 365 // max(1, per_year) // 2)
    return (d - timedelta(days=half)).isoformat(), (d + timedelta(days=half)).isoformat()


def _case_day(c: dict) -> str:
    return (completion_date(c)[0] or str(c.get("scheduled_at") or "")[:10])


async def candidate_cases(v: dict, contract_id: str, per_year: int, linked_ids: set) -> dict:
    """Canonical refs first; equipment overlap is strong; site+date alone needs review."""
    canon = await db.svc_cases.find(
        {"contract_obligation_id": v["obligation_id"], "status": {"$nin": list(CANCELLED_CASE)}}, {"_id": 0}).to_list(10)
    if canon:
        return {"strong": canon, "weak": []}
    if not v.get("site_id"):
        return {"strong": [], "weak": []}
    lo, hi = _window(v, per_year)
    strong, weak = [], []
    async for c in db.svc_cases.find({"site_id": v["site_id"], "case_type": "ppm",
                                      "status": {"$nin": list(CANCELLED_CASE)},
                                      "contract_obligation_id": {"$in": [None, ""]}}, {"_id": 0}).limit(200):
        if c["id"] in linked_ids or c["id"] in (v.get("rejected_cases") or []):
            continue
        day = _case_day(c)
        if not day or not lo <= day <= hi:
            continue
        if c.get("contract_id") == contract_id or set(c.get("equipment_ids") or []) & set(v.get("equipment_ids") or []):
            strong.append(c)
        else:
            weak.append(c)
    return {"strong": strong, "weak": weak}


def _brief(c: dict) -> dict:
    return {"case_id": c["id"], "reference": c.get("reference"), "status": c.get("status"),
            "scheduled_at": c.get("scheduled_at"), "completed_date": completion_date(c)[0],
            "engineer_name": c.get("assigned_engineer_name") or "", "title": c.get("title")}


# ─────────────────────────────────────────── sync

def _hist(v: dict, event: str, **kw) -> None:
    v.setdefault("history", []).append({"at": _now(), "event": event, **kw})


async def _apply_case(v: dict, case: dict | None) -> None:
    """Re-derive a linked obligation from its Service Desk case."""
    if not case:
        v.update({"status": "planned", "review_reason": "linked_case_missing"})
        return
    st = (case.get("status") or "").lower()
    if st in CANCELLED_CASE:
        _hist(v, "booking_cancelled", case_id=case["id"], reference=case.get("reference"))
        v.setdefault("cancelled_cases", []).append(case["id"])
        for k in ("case_id", "case_reference", "booked_for", "engineer_name", "engineer_id"):
            v.pop(k, None)
        v.update({"status": "planned", "cancelled_without_replacement": True})
        return
    v.update({"case_reference": case.get("reference"), "booked_for": str(case.get("scheduled_at") or "")[:10] or None,
              "engineer_name": case.get("assigned_engineer_name") or "", "engineer_id": case.get("assigned_engineer_id") or "",
              "cancelled_without_replacement": False})
    if st in DONE_CASE:
        res = await evaluate_completion(case, v.get("equipment_ids") or [])
        if res["ok"]:
            if v.get("status") != "completed" or (v.get("completion") or {}).get("case_id") != case["id"]:
                _hist(v, "completed", case_id=case["id"], date=res["evidence"]["completed_date"])
            v.update({"status": "completed", "completion": res["evidence"], "review_reason": None})
        else:
            v.update({"status": "booked", "review_reason": res["reason"], "pending_evidence": res.get("evidence")})
        return
    if v.get("status") == "completed":
        _hist(v, "reopened", case_id=case["id"], previous=v.get("completion"))
        v.setdefault("completion_history", []).append(v.get("completion"))
        v["completion"] = None
    v.update({"status": "booked", "review_reason": None})


async def link_case(org_id: str, contract: dict, v: dict, case: dict, basis: str, actor: str = "auto") -> bool:
    """Atomically tie one Service Desk case to one obligation (never two)."""
    r = await db.svc_cases.update_one(
        {"id": case["id"], "$or": [{"contract_obligation_id": {"$in": [None, ""]}},
                                   {"contract_obligation_id": v["obligation_id"]},
                                   {"contract_obligation_id": {"$exists": False}}]},
        {"$set": {"contract_obligation_id": v["obligation_id"], "contract_id": contract["id"],
                  "contract_number": contract.get("contract_number"), "updated_at": _now()}})
    if not r.matched_count:
        return False
    v.update({"case_id": case["id"], "link_basis": basis, "linked_by": actor, "review_reason": None,
              "review_candidates": None})
    _hist(v, "linked", case_id=case["id"], basis=basis, by=actor)
    return True


async def _linked_org(org_id: str, contract: dict, ag: dict) -> str | None:
    if ag.get("linked_organization_id"):
        return ag["linked_organization_id"]
    co = await db.crm2_companies.find_one({"id": contract.get("company_id"), "organization_id": org_id},
                                          {"_id": 0, "linked_organization_id": 1}) or {}
    return co.get("linked_organization_id")


async def sync_contract(org_id: str, contract: dict, *, dry_run: bool = False, today: str | None = None) -> dict:
    """Reconcile one contract's obligations with Service Desk. Idempotent."""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sched = await db.crm2_afs_service_schedules.find_one({"contract_id": contract["id"], "organization_id": org_id}, {"_id": 0})
    if not sched or not sched.get("visits"):
        return {"contract_id": contract["id"], "visits": [], "report": {}}
    ag = await db.crm2_afs_agreements.find_one({"id": sched.get("agreement_id")}, {"_id": 0, "asset_register": 1,
                                               "linked_organization_id": 1, "start_date": 1}) or {}
    per_year = int(sched.get("visits_per_year") or 1)
    visits = backfill_ids(contract["id"], sched["visits"], site_scopes(ag.get("asset_register"))[0])
    report = {"matched_completed": [], "matched_booked": [], "unmatched": [], "ambiguous": [],
              "possible_duplicates": [], "missing_relationships": []}
    if not await _linked_org(org_id, contract, ag):
        report["missing_relationships"].append({"issue": "customer_not_linked", "detail": "Customer has no operations organisation."})
    linked_ids = {v["case_id"] for v in visits if v.get("case_id")}
    for v in visits:
        if not v.get("site_id"):
            report["missing_relationships"].append({"obligation_id": v["obligation_id"], "issue": "site_missing"})
        if v.get("status") in ("cancelled", "excluded"):
            continue
        if v.get("case_id"):
            case = await db.svc_cases.find_one({"id": v["case_id"]}, {"_id": 0})
            if not dry_run:
                await _apply_case(v, case)
                if not v.get("case_id"):
                    linked_ids.discard(case["id"] if case else None)
            dupes = await db.svc_cases.count_documents({"contract_obligation_id": v["obligation_id"],
                                                        "id": {"$ne": v.get("case_id")},
                                                        "status": {"$nin": list(CANCELLED_CASE)}})
            if dupes:
                report["possible_duplicates"].append({"obligation_id": v["obligation_id"], "extra_cases": dupes})
        elif v.get("status") in ("completed", "verified"):
            pass  # historic completion recorded without a case — preserved as-is
        else:
            cands = await candidate_cases(v, contract["id"], per_year, linked_ids)
            if len(cands["strong"]) == 1 and not dry_run:
                if await link_case(org_id, contract, v, cands["strong"][0], "contract_or_equipment_reference"):
                    linked_ids.add(v["case_id"])
                    await _apply_case(v, cands["strong"][0])
            elif len(cands["strong"]) == 1:
                v["_would_link"] = _brief(cands["strong"][0])
            elif len(cands["strong"]) > 1 or cands["weak"]:
                allc = cands["strong"] + cands["weak"]
                v.update({"review_reason": "ambiguous_match" if len(allc) > 1 or cands["strong"] else "probable_match",
                          "review_candidates": [_brief(c) for c in allc]})
                report["ambiguous"].append({"obligation_id": v["obligation_id"], "planned_date": v.get("planned_date"),
                                            "candidates": v["review_candidates"]})
            else:
                v.pop("review_candidates", None)
                if v.get("review_reason") in ("ambiguous_match", "probable_match"):
                    v["review_reason"] = None
        bucket = obligation_bucket(v, today)
        row = {"obligation_id": v["obligation_id"], "planned_date": v.get("planned_date"), "site_id": v.get("site_id"),
               "case_id": v.get("case_id") or (v.get("_would_link") or {}).get("case_id")}
        if v.get("_would_link"):
            (report["matched_completed"] if v["_would_link"].get("completed_date") else report["matched_booked"]).append(row)
        elif bucket == "completed":
            report["matched_completed"].append(row)
        elif bucket == "booked":
            report["matched_booked"].append(row)
        elif bucket in ("due", "overdue", "planned") and v.get("obligation_id") not in {a["obligation_id"] for a in report["ambiguous"]}:
            report["unmatched"].append(row)
        v.pop("_would_link", None)
    if not dry_run:
        res = await db.crm2_afs_service_schedules.update_one(
            {"contract_id": contract["id"], "organization_id": org_id, "rev": sched.get("rev")},
            {"$set": {"visits": visits, "synced_at": _now()}, "$inc": {"rev": 1}})
        if not res.matched_count:  # a booking/link landed meanwhile — its write wins; next sync re-derives
            return {"contract_id": contract["id"], "visits": sched["visits"], "report": report, "stale": True}
        await sync_actions(org_id, contract, visits, today)
    return {"contract_id": contract["id"], "visits": visits, "report": report}


def obligation_bucket(v: dict, today: str) -> str:
    st = v.get("status") or "planned"
    if st in ("completed", "verified"):
        return "completed"
    if st in ("cancelled", "excluded"):
        return "excluded"
    if v.get("review_reason") or v.get("scope_review"):
        return "review"
    overdue = (v.get("planned_date") or "9999") < today
    if st == "booked" and v.get("case_id"):
        return "booked"
    if overdue:
        return "overdue"
    soon = (parse_date(today) + timedelta(days=BOOK_AHEAD_DAYS)).isoformat()
    return "due" if (v.get("planned_date") or "9999") <= soon else "planned"


_REVIEW_TEXT = {
    "report_missing": "the engineer report is missing — the visit cannot count as completed yet",
    "date_missing": "the case has no actual completion date",
    "partial": "not every covered machine was recorded as serviced",
    "ambiguous_match": "more than one Service Desk visit could be this obligation",
    "probable_match": "a PPM visit at the site may be this obligation but has no contract or equipment reference",
    "linked_case_missing": "the linked Service Desk case no longer exists",
}


async def sync_actions(org_id: str, contract: dict, visits: list, today: str) -> None:
    """One coordinator action per obligation problem; resolved when evidence arrives."""
    from utils.cm_actions import raise_action, resolve_action
    num = contract.get("contract_number") or contract.get("title") or "contract"
    who = contract.get("company_name") or "Customer"
    for v in visits:
        oid, b = v["obligation_id"], obligation_bucket(v, today)
        k = f"svc:{oid}"
        due = v.get("planned_date")
        if b in ("due", "overdue") and not v.get("cancelled_without_replacement"):
            await raise_action(org_id, f"{k}:book", type_="service_booking_required",
                               subject=f"{'Overdue service' if b == 'overdue' else 'Book service visit'}: {num}",
                               body=f"{who} — contractual PPM due {due} has no Service Desk booking.",
                               contract=contract, extra={"obligation_id": oid, "due_date": due, "overdue": b == "overdue"})
        else:
            await resolve_action(org_id, f"{k}:book", "Visit booked or completed in Service Desk." if b in ("booked", "completed")
                                 else "No longer requires booking.")
        if v.get("cancelled_without_replacement") and not v.get("case_id") and b not in ("completed", "excluded"):
            await raise_action(org_id, f"{k}:cancelled", type_="service_booking_cancelled",
                               subject=f"Visit cancelled — rebook: {num}",
                               body=f"{who} — the Service Desk appointment for the PPM due {due} was cancelled with no replacement.",
                               contract=contract, extra={"obligation_id": oid, "due_date": due})
        else:
            await resolve_action(org_id, f"{k}:cancelled", "Replacement appointment confirmed." if v.get("case_id")
                                 else "Resolved.")
        reason = v.get("review_reason") or ("scope" if v.get("scope_review") else None)
        if reason and b not in ("completed", "excluded"):
            text = _REVIEW_TEXT.get(reason) or v.get("scope_review") or reason
            await raise_action(org_id, f"{k}:review", type_="service_review_required",
                               subject=f"Service visit needs review: {num}",
                               body=f"{who} — PPM due {due}: {text}.", contract=contract,
                               extra={"obligation_id": oid, "review_reason": reason})
        else:
            await resolve_action(org_id, f"{k}:review", "Verified completion received or review completed.")


async def sync_all(org_id: str) -> dict:
    n = 0
    async for c in db.crm2_contracts.find({"organization_id": org_id, "status": "active"}, {"_id": 0}):
        if await db.crm2_afs_service_schedules.count_documents({"contract_id": c["id"], "organization_id": org_id}, limit=1):
            await sync_contract(org_id, c)
            n += 1
    return {"contracts_synced": n}


async def contract_covering(equipment: dict) -> dict | None:
    """Active CRM maintenance contract that already governs this machine's PPM."""
    cov = equipment.get("contract_cover") or {}
    if not cov.get("contract_id"):
        return None
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if cov.get("end") and str(cov["end"])[:10] < today:
        return None
    return await db.crm2_contracts.find_one({"id": cov["contract_id"], "status": "active"},
                                            {"_id": 0, "id": 1, "contract_number": 1})


async def sync_for_case(case: dict) -> None:
    sched = await db.crm2_afs_service_schedules.find_one(
        {"visits.obligation_id": case.get("contract_obligation_id")}, {"_id": 0, "contract_id": 1, "organization_id": 1})
    if not sched:
        return
    c = await db.crm2_contracts.find_one({"id": sched["contract_id"]}, {"_id": 0})
    if c:
        await sync_contract(sched["organization_id"], c)


def schedule_case_sync(case: dict) -> None:
    import asyncio
    import logging

    async def _run():
        await asyncio.sleep(0.5)  # let the transition's own writes land
        try:
            await sync_for_case(case)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning("contract obligation sync failed", exc_info=True)
    asyncio.get_event_loop().create_task(_run())
