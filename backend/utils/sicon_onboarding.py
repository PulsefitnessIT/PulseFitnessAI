"""Sicon → Pulse onboarding sync: customers, sites, equipment, contracts, cases.

Read-only from Sicon. Two modes over the same pass:
  preview — classify everything, write NOTHING, return counts per entity;
  apply   — create new records, link matches, fill EMPTY Pulse fields only.
A populated Pulse field that differs from Sicon is never changed; the
difference is queued in db.sicon_import_differences for review.
Customers + sites have no Sicon list endpoint, so they are derived from the
customer / sub-location carried on every equipment and case record.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from utils.database import db
from utils import sicon_links as links
from utils import sicon_import as imp
from utils.sicon_client import _extract_records

logger = logging.getLogger(__name__)

ENTITY_CONTRACT = "contract"
ENTITIES = ("customers", "sites", "equipment", "contracts", "cases")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty(v) -> bool:
    return v in (None, "", 0, [], {})


def _cmp(v) -> str:
    s = str(v).strip().lower()
    return s[:10] if _DATE.match(s) else s


def _first(rec: Dict[str, Any], keys) -> Any:
    for k in keys:
        if not _empty(rec.get(k)):
            return rec.get(k)
    return None


def _blank_counts() -> Dict[str, Dict[str, int]]:
    return {e: {"new": 0, "matched": 0, "differences": 0, "conflicts": 0, "failed": 0} for e in ENTITIES}


async def gap_fill(org_id: str, entity: str, external_id, pulse_id: str, existing: Dict[str, Any],
                   incoming: Dict[str, Any], run_id: str = "", record: bool = True) -> Dict[str, Any]:
    """$set for EMPTY Pulse fields only; differing populated fields are queued."""
    setdoc: Dict[str, Any] = {}
    for field, val in incoming.items():
        if _empty(val):
            continue
        cur = existing.get(field)
        if _empty(cur):
            setdoc[field] = val
        elif _cmp(cur) != _cmp(val) and record:
            key = {"organization_id": org_id, "entity": entity, "external_id": str(external_id), "field": field}
            await db.sicon_import_differences.update_one(key, {"$set": {
                **key, "pulse_id": pulse_id, "pulse_value": cur, "sicon_value": val,
                "status": "open", "run_id": run_id, "updated_at": _now()},
                "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()}}, upsert=True)
    return setdoc


def _has_diff(existing: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    return any(not _empty(v) and not _empty(existing.get(f)) and _cmp(existing.get(f)) != _cmp(v)
               for f, v in incoming.items())


async def _queue_conflict(org_id: str, entity: str, external_id, record: Dict[str, Any],
                          reasons, candidates, run_id: str) -> None:
    key = {"organization_id": org_id, "external_entity_type": entity, "external_id": str(external_id)}
    await db.sicon_import_conflicts.update_one(key, {"$set": {
        **key, "sicon_record": record, "candidates": candidates, "reasons": reasons,
        "status": "open", "run_id": run_id, "updated_at": _now()},
        "$setOnInsert": {"created_at": _now()}}, upsert=True)


# ── Customers ─────────────────────────────────────────────────────
async def classify_customer(org_id: str, cid, code: Optional[str], name: Optional[str]) -> Dict[str, Any]:
    if cid is not None:
        pid = await links.get_pulse_id(links.ENTITY_CUSTOMER, cid, org_id)
        if pid:
            return {"bucket": "matched", "pulse_id": pid}
    if code:
        rows = await db.crm2_companies.find({"organization_id": org_id, "sage_customer_id": code},
                                            {"_id": 0, "id": 1}).to_list(3)
        if len(rows) == 1:
            return {"bucket": "matched", "pulse_id": rows[0]["id"]}
        if len(rows) > 1:
            return {"bucket": "conflict", "reasons": [f"{len(rows)} Pulse customers share Sage code '{code}'"],
                    "candidates": [r["id"] for r in rows]}
    if name:
        rows = await db.crm2_companies.find(
            {"organization_id": org_id, "name": {"$regex": f"^{re.escape(name.strip())}$", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1}).to_list(3)
        if rows:
            return {"bucket": "conflict", "reasons": ["A Pulse customer with the same name exists but has no Sage code"],
                    "candidates": [r["id"] for r in rows]}
    return {"bucket": "new"}


async def sync_customer(org_id: str, cid, code, name, apply: bool, run_id: str) -> Dict[str, Any]:
    cls = await classify_customer(org_id, cid, code, name)
    incoming = {"name": name, "sage_customer_id": code, "sicon_customer_id": cid}
    ext = cid if cid is not None else code
    if cls["bucket"] == "conflict":
        if apply:
            await _queue_conflict(org_id, links.ENTITY_CUSTOMER, ext, incoming, cls["reasons"], cls["candidates"], run_id)
        return {"bucket": "conflict"}
    if cls["bucket"] == "matched":
        existing = await db.crm2_companies.find_one({"id": cls["pulse_id"]}, {"_id": 0}) or {}
        diff = _has_diff(existing, incoming)
        if apply:
            setdoc = await gap_fill(org_id, "customer", ext, cls["pulse_id"], existing, incoming, run_id)
            if setdoc:
                await db.crm2_companies.update_one({"id": cls["pulse_id"]}, {"$set": {**setdoc, "updated_at": _now()}})
            if cid is not None:
                await links.upsert_link(links.ENTITY_CUSTOMER, cid, "crm2_company", cls["pulse_id"],
                                        organization_id=org_id, sync_status="linked")
        return {"bucket": "matched", "diff": diff, "pulse_id": cls["pulse_id"]}
    if apply:
        doc = {"id": str(uuid.uuid4()), "organization_id": org_id,
               "name": name or f"Sicon customer {code or cid}", "type": "customer", "status": "active",
               "sage_customer_id": code or "", "sicon_customer_id": cid, "country": "United Kingdom",
               "source": "sicon_import", "tags": ["sicon"], "created_at": _now(), "updated_at": _now()}
        await db.crm2_companies.insert_one(doc)
        if cid is not None:
            await links.upsert_link(links.ENTITY_CUSTOMER, cid, "crm2_company", doc["id"],
                                    organization_id=org_id, sync_status="linked")
        return {"bucket": "new", "pulse_id": doc["id"]}
    return {"bucket": "new"}


# ── Sites (Sicon sub-locations) ───────────────────────────────────
async def sync_site(org_id: str, sub_id, label: Optional[str], company_id: Optional[str],
                    apply: bool, run_id: str) -> Dict[str, Any]:
    pid = await links.get_pulse_id(links.ENTITY_SITE, sub_id, org_id)
    if not pid:
        rows = await db.crm2_sites.find({"organization_id": org_id, "sicon_sub_location_id": sub_id},
                                        {"_id": 0, "id": 1}).to_list(3)
        if len(rows) > 1:
            if apply:
                await _queue_conflict(org_id, links.ENTITY_SITE, sub_id, {"sicon_sub_location_id": sub_id, "name": label},
                                      [f"{len(rows)} Pulse sites share this Sicon sub-location"],
                                      [r["id"] for r in rows], run_id)
            return {"bucket": "conflict"}
        pid = rows[0]["id"] if rows else None
    company = await db.crm2_companies.find_one({"id": company_id}, {"_id": 0, "name": 1}) if company_id else None
    incoming = {"name": label, "address": label, "company_id": company_id,
                "company_name": (company or {}).get("name"), "sicon_sub_location_id": sub_id}
    if pid:
        existing = await db.crm2_sites.find_one({"id": pid}, {"_id": 0}) or {}
        diff = _has_diff(existing, {"name": label, "company_id": company_id})
        if apply:
            setdoc = await gap_fill(org_id, "site", sub_id, pid, existing, incoming, run_id)
            if setdoc:
                await db.crm2_sites.update_one({"id": pid}, {"$set": {**setdoc, "updated_at": _now()}})
            await links.upsert_link(links.ENTITY_SITE, sub_id, "crm2_site", pid,
                                    organization_id=org_id, sync_status="linked")
        return {"bucket": "matched", "diff": diff}
    if apply:
        doc = {"id": str(uuid.uuid4()), "organization_id": org_id, **{k: v for k, v in incoming.items() if v is not None},
               "name": label or f"Sicon site {sub_id}", "country": "GB", "source": "sicon_import",
               "created_at": _now(), "updated_at": _now()}
        await db.crm2_sites.insert_one(doc)
        await links.upsert_link(links.ENTITY_SITE, sub_id, "crm2_site", doc["id"],
                                organization_id=org_id, sync_status="linked")
    return {"bucket": "new"}


class _Run:
    """Per-run counters + 'seen' sets so each customer/site is counted once."""

    def __init__(self, org_id: str, run_id: str, apply: bool, config: Dict[str, Any]):
        self.org_id, self.run_id, self.apply, self.config = org_id, run_id, apply, config
        self.counts = _blank_counts()
        self.seen_customers: Dict[str, Optional[str]] = {}
        self.seen_sites: set = set()
        self.totals: Dict[str, Any] = {}

    def tally(self, entity: str, res: Dict[str, Any]) -> None:
        b = res.get("bucket")
        c = self.counts[entity]
        c[{"new": "new", "matched": "matched", "linked": "matched", "match": "matched",
           "conflict": "conflicts"}.get(b, "failed")] += 1
        if res.get("diff"):
            c["differences"] += 1

    async def customer_and_site(self, cid, code, name, sub_id, label) -> None:
        key = str(cid if cid is not None else code or "")
        if key and key not in self.seen_customers:
            try:
                res = await sync_customer(self.org_id, cid, code, name, self.apply, self.run_id)
                self.seen_customers[key] = res.get("pulse_id")
                self.tally("customers", res)
            except Exception as e:
                self.counts["customers"]["failed"] += 1
                self.seen_customers[key] = None
                logger.warning("onboarding customer %s failed: %s", key, e)
        if sub_id is not None and str(sub_id) not in self.seen_sites:
            self.seen_sites.add(str(sub_id))
            try:
                self.tally("sites", await sync_site(self.org_id, sub_id, label, self.seen_customers.get(key),
                                                    self.apply, self.run_id))
            except Exception as e:
                self.counts["sites"]["failed"] += 1
                logger.warning("onboarding site %s failed: %s", sub_id, e)


# ── Phases ────────────────────────────────────────────────────────
async def _equipment_phase(run: _Run, client) -> None:
    async for meta, records in client.svc_paginate("equipment"):
        run.totals.setdefault("equipment", meta.get("totalRecords"))
        for rec in records:
            try:
                norm = imp.normalise_equipment(rec)
                await run.customer_and_site(norm.get("sicon_customer_id"), norm.get("sicon_customer_code"),
                                            norm.get("customer_name"), norm.get("sicon_sub_location_id"),
                                            norm.get("location_full"))
                cls = await imp.classify_equipment(norm, run.org_id)
                diff = False
                if cls["bucket"] in ("linked", "match"):
                    existing = await db.equipment.find_one({"id": cls["pulse_asset_id"]}, {"_id": 0}) or {}
                    diff = _has_diff(existing, {f: norm.get(f) for f in (*imp.SICON_SYNCED_FIELDS, "model")})
                if run.apply:
                    await imp.apply_equipment_record(run.org_id, norm, cls, run.run_id, fill_gaps=True)
                run.tally("equipment", {"bucket": cls["bucket"], "diff": diff})
            except Exception as e:
                run.counts["equipment"]["failed"] += 1
                logger.warning("onboarding equipment failed: %s", e)
        await _checkpoint(run, "equipment")


async def _cases_phase(run: _Run, client) -> None:
    async for meta, records in client.svc_paginate("cases"):
        run.totals.setdefault("cases", meta.get("totalRecords"))
        for rec in records:
            try:
                norm = imp.normalise_case(rec)
                await run.customer_and_site(norm.get("sicon_customer_id"), norm.get("sicon_customer_code"),
                                            norm.get("customer_name"), norm.get("sicon_sub_location_id"), None)
                cls = await imp.classify_case(norm, run.org_id)
                diff = False
                if cls["bucket"] == "linked":
                    existing = await db.issues.find_one({"id": cls["issue_id"]}, {"_id": 0, "status": 1}) or {}
                    diff = _has_diff(existing, {"status": imp.resolve_case_fields(norm, run.config).get("status")})
                if run.apply:
                    res = await imp.apply_case_record(run.org_id, norm, cls, run.config, run.run_id, fill_gaps=True)
                    if res.get("issue_id"):
                        await imp.sync_case_relationships(run.org_id, client, norm.get("si_sm_case_id"),
                                                          res["issue_id"], run.run_id)
                run.tally("cases", {"bucket": "matched" if cls["bucket"] == "linked" else "new", "diff": diff})
            except Exception as e:
                run.counts["cases"]["failed"] += 1
                logger.warning("onboarding case failed: %s", e)
        await _checkpoint(run, "cases")


def normalise_contract(rec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sicon_contract_id": _first(rec, ("siconContractId", "siconContractID", "SiconContractID", "contractId", "id")),
        "contract_number": _first(rec, ("contractNumber", "siconContractNumber", "SiconContractNumber", "number", "reference")),
        "title": _first(rec, ("description", "name", "contractName", "title")),
        "sicon_customer_id": _first(rec, ("customerId", "slCustomerAccountId", "SLCustomerAccountID")),
        "sicon_customer_code": _first(rec, ("customerCode", "customerReference", "accountReference")),
        "customer_name": _first(rec, ("customerName", "customer")),
        "start_date": _first(rec, ("startDate", "contractStartDate", "dateFrom")),
        "end_date": _first(rec, ("endDate", "contractEndDate", "expiryDate", "dateTo")),
        "sicon_status": _first(rec, ("status", "statusName", "contractStatus")),
    }


async def fetch_contracts(client):
    """Contract read route is not yet confirmed by Sicon — try the known
    candidates; None means the contract API isn't available."""
    for fn in (client.svc_get_contracts, lambda: client._svc_get("/api/v1/SiconService/Contract")):
        try:
            return _extract_records(await fn())
        except Exception as e:
            logger.info("sicon contract source unavailable: %s", e)
    return None


async def _contracts_phase(run: _Run, client) -> None:
    records = await fetch_contracts(client)
    if records is None:
        run.totals["contracts"] = "unavailable"
        return
    run.totals["contracts"] = len(records)
    for rec in records:
        try:
            n = normalise_contract(rec)
            if isinstance(n["customer_name"], dict):
                n["customer_name"] = n["customer_name"].get("name")
            await run.customer_and_site(n["sicon_customer_id"], n["sicon_customer_code"], n["customer_name"], None, None)
            run.tally("contracts", await sync_contract(run, n))
        except Exception as e:
            run.counts["contracts"]["failed"] += 1
            logger.warning("onboarding contract failed: %s", e)
    await _checkpoint(run, "contracts")


async def sync_contract(run: _Run, n: Dict[str, Any]) -> Dict[str, Any]:
    org_id, scid = run.org_id, n["sicon_contract_id"]
    pid = await links.get_pulse_id(ENTITY_CONTRACT, scid, org_id) if scid is not None else None
    if not pid and scid is not None:
        row = await db.crm2_contracts.find_one({"organization_id": org_id, "sicon_contract_id": scid}, {"_id": 0, "id": 1})
        pid = row["id"] if row else None
    if not pid and n["contract_number"]:
        rows = await db.crm2_contracts.find({"organization_id": org_id, "contract_number": n["contract_number"]},
                                            {"_id": 0, "id": 1}).to_list(3)
        if len(rows) > 1:
            if run.apply:
                await _queue_conflict(org_id, ENTITY_CONTRACT, scid or n["contract_number"], n,
                                      [f"{len(rows)} Pulse contracts share number '{n['contract_number']}'"],
                                      [r["id"] for r in rows], run.run_id)
            return {"bucket": "conflict"}
        pid = rows[0]["id"] if rows else None
    company_id = run.seen_customers.get(str(n["sicon_customer_id"] if n["sicon_customer_id"] is not None
                                             else n["sicon_customer_code"] or ""))
    company = await db.crm2_companies.find_one({"id": company_id}, {"_id": 0, "name": 1}) if company_id else None
    incoming = {"title": n["title"], "start_date": n["start_date"], "end_date": n["end_date"],
                "company_id": company_id, "company_name": (company or {}).get("name"), "sicon_contract_id": scid}
    if pid:
        existing = await db.crm2_contracts.find_one({"id": pid}, {"_id": 0}) or {}
        diff = _has_diff(existing, {k: incoming[k] for k in ("title", "start_date", "end_date")})
        if run.apply:
            setdoc = await gap_fill(org_id, "contract", scid, pid, existing, incoming, run.run_id)
            await db.crm2_contracts.update_one({"id": pid}, {"$set": {
                **setdoc, "sicon_status": n["sicon_status"], "sicon_last_synced_at": _now(), "updated_at": _now()}})
            if scid is not None:
                await links.upsert_link(ENTITY_CONTRACT, scid, "crm2_contract", pid, organization_id=org_id)
        return {"bucket": "matched", "diff": diff}
    if run.apply:
        doc = {"id": str(uuid.uuid4()), "organization_id": org_id,
               "contract_number": n["contract_number"] or f"SICON-{scid}",
               "title": n["title"] or f"Sicon contract {n['contract_number'] or scid}",
               "type": "service", "tier": "standard", "status": "active",
               "company_id": company_id or "", "company_name": (company or {}).get("name") or n["customer_name"] or "",
               "start_date": n["start_date"], "end_date": n["end_date"], "sicon_contract_id": scid,
               "sicon_status": n["sicon_status"], "source": "sicon_import", "version": 1,
               "created_by": "Sicon onboarding", "created_at": _now(), "updated_at": _now(),
               "sicon_last_synced_at": _now()}
        await db.crm2_contracts.insert_one(doc)
        if scid is not None:
            await links.upsert_link(ENTITY_CONTRACT, scid, "crm2_contract", doc["id"], organization_id=org_id)
    return {"bucket": "new"}


async def _checkpoint(run: _Run, phase: str) -> None:
    await db.sicon_sync_runs.update_one({"id": run.run_id}, {"$set": {
        "counts": run.counts, "totals": run.totals, "phase": phase, "updated_at": _now()}})
    if run.apply:
        await imp.touch_sync_lock(run.org_id, "onboarding", run.run_id)


async def run_onboarding(org_id: str, client, config: Dict[str, Any], run_id: str,
                         apply: bool, user_id: str = "system") -> Dict[str, Any]:
    """One full pass: equipment (+customers/sites) → contracts → cases."""
    mode = "apply" if apply else "preview"
    if apply and not await imp.acquire_sync_lock(org_id, "onboarding", run_id):
        await db.sicon_sync_runs.update_one({"id": run_id}, {"$set": {
            "status": "skipped_locked", "finished_at": _now(),
            "error": "Another Sicon sync is already running"}})
        return {"status": "skipped_locked"}
    run = _Run(org_id, run_id, apply, config)
    await db.sicon_sync_runs.update_one({"id": run_id}, {"$set": {
        "status": "running", "mode": mode, "counts": run.counts, "phase": "equipment", "started_at": _now()}})
    status, error = "completed", None
    try:
        for phase, fn in (("equipment", _equipment_phase), ("contracts", _contracts_phase), ("cases", _cases_phase)):
            await db.sicon_sync_runs.update_one({"id": run_id}, {"$set": {"phase": phase}})
            await fn(run, client)
    except Exception as e:
        status, error = "failed", str(e)[:300]
        logger.error("onboarding %s run %s failed: %s", mode, run_id, e)
    finally:
        if apply:
            await imp.release_sync_lock(org_id, "onboarding", run_id)
    await db.sicon_sync_runs.update_one({"id": run_id}, {"$set": {
        "status": status, "error": error, "counts": run.counts, "totals": run.totals,
        "phase": "done", "finished_at": _now()}})
    return {"status": status, "counts": run.counts}


# ── Review queues ─────────────────────────────────────────────────
DIFF_COLLECTIONS = {"customer": "crm2_companies", "site": "crm2_sites", "equipment": "equipment",
                    "case": "issues", "contract": "crm2_contracts"}
_CONFLICT_TARGETS = {links.ENTITY_CUSTOMER: ("crm2_companies", "crm2_company"),
                     links.ENTITY_SITE: ("crm2_sites", "crm2_site"),
                     ENTITY_CONTRACT: ("crm2_contracts", "crm2_contract")}


async def resolve_difference(org_id: str, diff_id: str, action: str, user_id: str) -> Dict[str, Any]:
    d = await db.sicon_import_differences.find_one({"id": diff_id, "organization_id": org_id}, {"_id": 0})
    if not d:
        raise LookupError("Difference not found")
    if action == "use_sicon":
        await db[DIFF_COLLECTIONS[d["entity"]]].update_one(
            {"id": d["pulse_id"], "organization_id": org_id},
            {"$set": {d["field"]: d["sicon_value"], "updated_at": _now()}})
    elif action != "keep_pulse":
        raise ValueError("action must be keep_pulse|use_sicon")
    await db.sicon_import_differences.update_one({"id": diff_id}, {"$set": {
        "status": "resolved", "resolution": action, "resolved_by": user_id, "resolved_at": _now()}})
    return {"success": True, "resolution": action}


async def resolve_record_conflict(org_id: str, entity: str, external_id: str, record: Dict[str, Any],
                                  action: str, pulse_id: Optional[str]) -> str:
    """Customer / site / contract conflicts: link to a chosen Pulse record,
    create a new one, or ignore."""
    coll, pulse_type = _CONFLICT_TARGETS[entity]
    if action == "link":
        if not pulse_id or not await db[coll].find_one({"id": pulse_id, "organization_id": org_id}, {"_id": 1}):
            raise LookupError("Pulse record not found")
        await links.upsert_link(entity, external_id, pulse_type, pulse_id, organization_id=org_id)
        return f"linked to {pulse_id}"
    if action == "create_new":
        doc = {"id": str(uuid.uuid4()), "organization_id": org_id,
               **{k: v for k, v in record.items() if not _empty(v)},
               "source": "sicon_import", "created_at": _now(), "updated_at": _now()}
        if entity == links.ENTITY_CUSTOMER:
            doc.update({"type": "customer", "status": "active"})
        doc.setdefault("name", doc.get("title") or f"Sicon {entity} {external_id}")
        await db[coll].insert_one(doc)
        await links.upsert_link(entity, external_id, pulse_type, doc["id"], organization_id=org_id)
        return f"created {doc['id']}"
    if action == "ignore":
        await links.set_status(entity, external_id, "ignored", reason="resolved: ignored by admin",
                               organization_id=org_id)
        return "ignored"
    raise ValueError("action must be link|create_new|ignore")
