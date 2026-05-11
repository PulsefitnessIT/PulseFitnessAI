"""Master Admin — Unified Audit Log (iter 215ah).

Merges security-relevant events from several live collections into a
single, filterable timeline the platform's Master Admin (or a delegated
Pulse Master Admin) can hand to the pentest team / SOC 2 auditor:

  * ``login_events``            — logins, MFA, password resets
  * ``wallet_ledger``           — parent wallet topups, debits, refunds
  * ``membership_class_invoices`` — invoices paid (all paths) + generated
  * ``system_jobs`` (autopay_sweep) — monthly Auto-Bill runs

Everything is normalised into a common event shape so the React panel
doesn't have to understand 4 different schemas. Filtering is done
server-side (per-kind, per-org, since-days) and the endpoint supports
CSV export for offline evidence.

Design decisions:

* Read-only. No mutation endpoints — an audit-log viewer that can
  write would itself be a liability.
* ``limit`` is capped at 2000 per request to keep the response bounded.
  The CSV endpoint can widen this via ``export=true`` (cap 10 000).
* Org name is joined in memory so we don't pay a cross-collection
  lookup per event; a single batched ``$in`` query covers the page.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from utils.auth import get_current_user
from utils.database import db

from routes.master_admin import require_master_admin

router = APIRouter(prefix="/master-admin/audit-log", tags=["master-admin-audit-log"])


_EVENT_KINDS = {
    "login", "login_failed", "mfa_verify", "mfa_failed", "password_reset",
    "wallet_topup", "wallet_debit", "wallet_refund",
    "invoice_paid", "invoice_generated",
    "autopay_charge", "autopay_retry", "autopay_exhausted",
    "autopay_sweep",
}

_SEVERITY = {
    "login": "info", "logout": "info", "password_reset": "info",
    "mfa_verify": "info", "wallet_topup": "info", "invoice_paid": "info",
    "invoice_generated": "info", "autopay_sweep": "info",
    "wallet_debit": "info", "wallet_refund": "warning",
    "login_failed": "warning", "mfa_failed": "warning",
    "autopay_retry": "warning",
    "autopay_exhausted": "critical",
    "autopay_charge": "info",
}


def _severity_for(kind: str) -> str:
    return _SEVERITY.get(kind, "info")


async def _enrich_orgs(events: list[dict]) -> list[dict]:
    """One batched join from organization_id → name."""
    org_ids = {e.get("organization_id") for e in events if e.get("organization_id")}
    if not org_ids:
        return events
    docs = await db.organizations.find(
        {"id": {"$in": list(org_ids)}}, {"_id": 0, "id": 1, "name": 1},
    ).to_list(len(org_ids))
    name_of = {d["id"]: d.get("name", "") for d in docs}
    for e in events:
        oid = e.get("organization_id")
        if oid:
            e["organization_name"] = name_of.get(oid, "")
    return events


async def _gather(
    *, since_iso: str, kinds: Optional[set[str]],
    org_id: Optional[str], actor_email: Optional[str], limit: int,
    brand_org_ids: Optional[set] = None,
) -> list[dict]:
    """Pull candidate events from each source collection, normalise them,
    and return a merged+sorted list. Each source is capped at ``limit``
    so a single noisy collection can't starve the others.

    Iter 216h25 — ``brand_org_ids`` is an optional pre-resolved set of
    org IDs from the BrandPicker filter. When provided, every per-org
    query is intersected with this set so Pulse Master Admins cannot
    see GymAxis events and vice versa.
    """
    out: list[dict] = []

    def _apply_brand(q: dict) -> dict:
        if brand_org_ids is None:
            return q
        # Caller-supplied org_id takes precedence (already pinned to one).
        if "organization_id" in q and isinstance(q["organization_id"], str):
            return q if q["organization_id"] in brand_org_ids else {**q, "organization_id": "___no_match___"}
        return {**q, "organization_id": {"$in": list(brand_org_ids)}}

    # ── login_events ────────────────────────────────────────────────
    if kinds is None or any(k in kinds for k in (
        "login", "login_failed", "logout", "mfa_verify", "mfa_failed", "password_reset"
    )):
        q: dict = {"created_at": {"$gte": since_iso}}
        if org_id:
            q["organization_id"] = org_id
        if actor_email:
            q["email"] = actor_email
        if kinds is not None:
            q["action"] = {"$in": list(kinds & {
                "login", "login_failed", "logout", "mfa_verify", "mfa_failed", "password_reset",
            })}
        cursor = db.login_events.find(_apply_brand(q), {"_id": 0}).sort("created_at", -1).limit(limit)
        async for ev in cursor:
            out.append({
                "timestamp": ev.get("created_at"),
                "kind": ev.get("action") or "login",
                "severity": _severity_for(ev.get("action") or "login"),
                "organization_id": ev.get("organization_id"),
                "actor_email": ev.get("email"),
                "actor_type": ev.get("actor_type") or "operator",
                "summary": (
                    f"{ev.get('action', 'login').replace('_', ' ').title()}"
                    + (f" from {ev['ip']}" if ev.get("ip") else "")
                ),
                "details": {k: ev.get(k) for k in (
                    "ip", "user_agent", "mfa_method", "reason",
                ) if ev.get(k)},
            })

    # ── wallet_ledger (topups + debits + refunds) ───────────────────
    if kinds is None or any(k in kinds for k in (
        "wallet_topup", "wallet_debit", "wallet_refund",
    )):
        q = {"created_at": {"$gte": since_iso}}
        if org_id:
            q["organization_id"] = org_id
        if kinds is not None:
            wanted = [k.replace("wallet_", "") for k in kinds if k.startswith("wallet_")]
            if wanted:
                q["kind"] = {"$in": wanted}
        cursor = db.wallet_ledger.find(_apply_brand(q), {"_id": 0}).sort("created_at", -1).limit(limit)
        async for ev in cursor:
            kind = f"wallet_{ev.get('kind') or 'debit'}"
            amt = int(ev.get("amount_pence") or 0)
            sign = "+" if amt >= 0 else "−"
            out.append({
                "timestamp": ev.get("created_at"),
                "kind": kind,
                "severity": _severity_for(kind),
                "organization_id": ev.get("organization_id"),
                "actor_email": None,  # wallet actions are system / attributed via member_id
                "actor_type": "system",
                "member_id": ev.get("member_id"),
                "summary": (
                    f"{sign}£{abs(amt) / 100:.2f} — {ev.get('note') or ev.get('kind', '').upper()}"
                ),
                "details": {
                    "amount_pence": amt,
                    "balance_after_pence": ev.get("balance_after_pence"),
                    "invoice_id": ev.get("invoice_id"),
                    "stripe_session_id": ev.get("stripe_session_id"),
                },
            })

    # ── membership_class_invoices (paid events) ─────────────────────
    if kinds is None or any(k in kinds for k in (
        "invoice_paid", "invoice_generated", "autopay_charge",
        "autopay_retry", "autopay_exhausted",
    )):
        q = {"$or": [
            {"paid_at": {"$gte": since_iso}},
            {"created_at": {"$gte": since_iso}},
            {"auto_pay_retry_exhausted_at": {"$gte": since_iso}},
        ]}
        if org_id:
            q["organization_id"] = org_id
        cursor = db.membership_class_invoices.find(_apply_brand(q), {"_id": 0}).sort(
            "paid_at", -1,
        ).limit(limit * 2)  # 2× so we can split into "paid" + "generated" rows
        async for inv in cursor:
            period = inv.get("period") or "-"
            total_gbp = f"£{int(inv.get('total_pence') or 0) / 100:.2f}"
            if inv.get("paid_at") and (not kinds or (
                "invoice_paid" in kinds or
                "autopay_charge" in kinds or "autopay_retry" in kinds
            )):
                kind = "autopay_retry" if inv.get("paid_via") == "stripe_autopay_retry" else (
                    "autopay_charge" if inv.get("paid_via") == "stripe_autopay" else "invoice_paid"
                )
                out.append({
                    "timestamp": inv["paid_at"],
                    "kind": kind,
                    "severity": _severity_for(kind),
                    "organization_id": inv.get("organization_id"),
                    "actor_email": None,
                    "actor_type": "system",
                    "member_id": inv.get("member_id"),
                    "summary": f"Invoice {period} paid {total_gbp} via {inv.get('paid_via') or 'manual'}",
                    "details": {
                        "invoice_id": inv.get("id"),
                        "paid_via": inv.get("paid_via"),
                        "payment_intent_id": inv.get("auto_pay_payment_intent_id"),
                    },
                })
            if inv.get("created_at") and inv["created_at"] >= since_iso and (
                not kinds or "invoice_generated" in kinds
            ):
                out.append({
                    "timestamp": inv["created_at"],
                    "kind": "invoice_generated",
                    "severity": "info",
                    "organization_id": inv.get("organization_id"),
                    "actor_email": None,
                    "actor_type": "system",
                    "member_id": inv.get("member_id"),
                    "summary": f"Invoice {period} generated ({total_gbp})",
                    "details": {"invoice_id": inv.get("id")},
                })
            if inv.get("auto_pay_retry_exhausted_at") and inv["auto_pay_retry_exhausted_at"] >= since_iso:
                out.append({
                    "timestamp": inv["auto_pay_retry_exhausted_at"],
                    "kind": "autopay_exhausted",
                    "severity": "critical",
                    "organization_id": inv.get("organization_id"),
                    "actor_email": None,
                    "actor_type": "system",
                    "member_id": inv.get("member_id"),
                    "summary": f"Auto-Bill retry ladder exhausted · {period} · {total_gbp}",
                    "details": {
                        "invoice_id": inv.get("id"),
                        "last_error": inv.get("auto_pay_last_error"),
                    },
                })

    # ── system_jobs (autopay sweep completions) ─────────────────────
    if kinds is None or "autopay_sweep" in kinds:
        q = {"kind": "autopay_sweep", "started_at": {"$gte": since_iso}}
        cursor = db.system_jobs.find(_apply_brand(q), {"_id": 0}).sort("started_at", -1).limit(limit)
        async for j in cursor:
            s = j.get("stats") or {}
            out.append({
                "timestamp": j.get("finished_at") or j.get("started_at"),
                "kind": "autopay_sweep",
                "severity": "info",
                "organization_id": None,
                "actor_email": None,
                "actor_type": "system",
                "summary": (
                    f"Auto-Bill sweep — attempted {s.get('attempted', 0)}, "
                    f"charged {s.get('charged', 0)}, failed {s.get('failed', 0)}"
                ),
                "details": s,
            })

    # Sort + cap.
    out.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return out[:limit]


async def _resolve_brand_org_ids(user: dict, brand: str) -> Optional[set]:
    """Iter 216h25 — Resolve the BrandPicker setting into a set of
    organisation IDs.

    Returns:
      * ``None`` when no scope restriction is needed (GymAxis admin
        chose 'all') — `_gather` skips its brand intersection.
      * a ``set[str]`` of org IDs when restriction applies. Pulse
        Master Admins are forced to ``pulse`` regardless of the
        request param.
    """
    from utils.brand_filter import normalise_brand, brand_filter_clause

    if _is_pulse_only(user):
        canonical = "pulse"
    else:
        canonical = normalise_brand(brand)
        if canonical == "all":
            return None

    clause = brand_filter_clause(canonical, collection="organizations")
    if not clause:
        return None
    orgs = await db.organizations.find(clause, {"_id": 0, "id": 1}).to_list(length=None)
    return {o["id"] for o in orgs}


def _is_pulse_only(user: dict) -> bool:
    return bool(user.get("is_pulse_admin") and not user.get("is_master_admin"))


@router.get("")
async def list_audit_events(
    user: dict = Depends(get_current_user),
    since_days: int = Query(7, ge=1, le=90),
    kinds: Optional[str] = Query(None, description="comma-separated event kinds"),
    organization_id: Optional[str] = Query(None),
    actor_email: Optional[str] = Query(None),
    brand: str = Query("all", description="all | pulse | gymaxis — top-bar BrandPicker scope"),
    limit: int = Query(200, ge=1, le=2000),
):
    """Return recent audit events, newest first. Free-form filters
    collapse to no-op when omitted so the default is "last 7 days,
    every kind, every org".

    Iter 216h25 — ``brand`` resolves the BrandPicker top-bar setting
    into an org-id intersection. Pulse Master Admins are forced to
    ``pulse`` regardless of the query param.
    """
    require_master_admin(user)
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    kind_set: Optional[set[str]] = None
    if kinds:
        kind_set = {k.strip() for k in kinds.split(",") if k.strip() in _EVENT_KINDS}
    brand_org_ids = await _resolve_brand_org_ids(user, brand)
    events = await _gather(
        since_iso=since, kinds=kind_set,
        org_id=organization_id,
        actor_email=(actor_email or "").lower().strip() or None,
        limit=limit,
        brand_org_ids=brand_org_ids,
    )
    events = await _enrich_orgs(events)
    return {
        "count": len(events),
        "since": since,
        "events": events,
        "brand": "pulse" if (brand_org_ids is not None and _is_pulse_only(user)) else brand,
    }


@router.get("/summary")
async def audit_summary(
    user: dict = Depends(get_current_user),
    since_days: int = Query(7, ge=1, le=90),
    brand: str = Query("all"),
):
    """Small counts-per-kind summary — feeds the panel's top-row tiles."""
    require_master_admin(user)
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    brand_org_ids = await _resolve_brand_org_ids(user, brand)
    events = await _gather(since_iso=since, kinds=None, org_id=None,
                           actor_email=None, limit=2000, brand_org_ids=brand_org_ids)
    counts: dict[str, int] = {}
    by_sev = {"info": 0, "warning": 0, "critical": 0}
    for e in events:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        by_sev[e["severity"]] = by_sev.get(e["severity"], 0) + 1
    return {
        "total": len(events),
        "by_kind": counts,
        "by_severity": by_sev,
        "since": since,
    }


@router.get("/export.csv")
async def export_audit_csv(
    user: dict = Depends(get_current_user),
    since_days: int = Query(30, ge=1, le=90),
    kinds: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    actor_email: Optional[str] = Query(None),
    brand: str = Query("all"),
    limit: int = Query(10000, ge=1, le=10000),
):
    """CSV export for SOC 2 / pentest / support desk evidence packets."""
    require_master_admin(user)
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    kind_set: Optional[set[str]] = None
    if kinds:
        kind_set = {k.strip() for k in kinds.split(",") if k.strip() in _EVENT_KINDS}
    brand_org_ids = await _resolve_brand_org_ids(user, brand)
    events = await _gather(
        since_iso=since, kinds=kind_set,
        org_id=organization_id,
        actor_email=(actor_email or "").lower().strip() or None,
        limit=limit,
        brand_org_ids=brand_org_ids,
    )
    events = await _enrich_orgs(events)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "timestamp", "kind", "severity", "organization_id", "organization_name",
        "actor_email", "actor_type", "member_id", "summary",
    ])
    for e in events:
        writer.writerow([
            e.get("timestamp", ""),
            e.get("kind", ""),
            e.get("severity", ""),
            e.get("organization_id", "") or "",
            e.get("organization_name", "") or "",
            e.get("actor_email", "") or "",
            e.get("actor_type", "") or "",
            e.get("member_id", "") or "",
            e.get("summary", "") or "",
        ])
    buf.seek(0)

    filename = f"gymaxis-audit-log-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
