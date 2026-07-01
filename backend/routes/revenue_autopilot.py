"""Revenue Recovery Autopilot — Phase 1 of Pulse Fitness Autopilot.

A supervised agent that continuously runs the revenue-recovery loop an
operator would otherwise do by hand:

  detect at-risk revenue  →  decide the right lever  →  act (or queue)
  →  audit  →  report (daily digest)

It is a THIN orchestration layer over existing, already-tested building
blocks — it never reimplements them:

  * dunning            → ``routes.membership_dunning`` (_at_risk_rows / _fire_reminder)
  * engagement churn   → ``utils.churn_signals.detect_churn_signals``
  * win-back email     → ``utils.memberships_winback.send_winback_for_member``
  * safety / audit     → ``utils.ai_guardrails``

Autonomy ladder (set per org in settings):
  off     — agent does nothing.
  suggest — (L1) agent only proposes actions; a human runs them.
  act     — (L2, DEFAULT) agent auto-runs REVERSIBLE actions (emails) and
            notifies; money actions (Stripe retry) are queued for approval.
  auto    — (L3) as 'act', and money actions auto-run ONLY if the org has
            explicitly opted in via ``allow_money_actions``.

Money never moves without an explicit opt-in. Every action is written to
``autopilot_actions`` (audit) and surfaced in the daily digest.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from utils.auth import get_current_user
from utils.database import db
from utils.email import send_email
from utils.ai_guardrails import (
    enforce_token_budget, record_token_usage, record_ai_action,
)
from utils.churn_signals import detect_churn_signals, SIGNAL_LEVERS
from utils.memberships_winback import send_winback_for_member
from routes.membership_dunning import _at_risk_rows, _fire_reminder, _stage_for, _days_past_due

logger = logging.getLogger("revenue_autopilot")
router = APIRouter(prefix="/autopilot/revenue", tags=["autopilot"])
stripe.api_key = os.environ.get("STRIPE_API_KEY")

_MODEL = ("openai", "gpt-4o")
COOLDOWN_DAYS = 7  # don't re-action the same member+kind within this window
LEVELS = ("off", "suggest", "act", "auto")

DEFAULT_SETTINGS = {
    "revenue_enabled": False,
    "autonomy_level": "act",        # L2 balanced
    "allow_money_actions": False,    # money always needs explicit opt-in
    "daily_digest": True,
    "max_actions_per_run": 25,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


async def _operator_org(user: dict) -> str:
    if not user or user.get("account_type") == "member":
        raise HTTPException(403, "Operators only")
    org_id = user.get("organization_id")
    if not org_id:
        raise HTTPException(403, "No organization context")
    return org_id


# ───────────────────────── settings ─────────────────────────


async def get_settings(org_id: str) -> dict:
    doc = await db.autopilot_settings.find_one({"organization_id": org_id}, {"_id": 0}) or {}
    merged = {**DEFAULT_SETTINGS, **{k: doc.get(k) for k in DEFAULT_SETTINGS if k in doc}}
    return merged


@router.get("/settings")
async def read_settings(user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    return await get_settings(org_id)


@router.put("/settings")
async def update_settings(body: dict = Body(...), user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    patch: dict = {}
    if "revenue_enabled" in body:
        patch["revenue_enabled"] = bool(body["revenue_enabled"])
    if "autonomy_level" in body:
        lvl = str(body["autonomy_level"])
        if lvl not in LEVELS:
            raise HTTPException(400, f"autonomy_level must be one of {LEVELS}")
        patch["autonomy_level"] = lvl
    if "allow_money_actions" in body:
        patch["allow_money_actions"] = bool(body["allow_money_actions"])
    if "daily_digest" in body:
        patch["daily_digest"] = bool(body["daily_digest"])
    if "max_actions_per_run" in body:
        patch["max_actions_per_run"] = max(1, min(200, int(body["max_actions_per_run"])))
    if not patch:
        raise HTTPException(400, "No valid settings supplied")
    patch["updated_at"] = _now_iso()
    await db.autopilot_settings.update_one(
        {"organization_id": org_id},
        {"$set": {**patch, "organization_id": org_id}},
        upsert=True,
    )
    return await get_settings(org_id)


# ───────────────────────── planning ─────────────────────────


async def _recently_actioned(org_id: str, member_id: str, kind: str) -> bool:
    """Idempotency guard: was this member+kind already actioned (executed
    or queued) within the cooldown window?"""
    cutoff = (_now() - timedelta(days=COOLDOWN_DAYS)).isoformat()
    hit = await db.autopilot_actions.find_one({
        "organization_id": org_id,
        "member_id": member_id,
        "kind": kind,
        "status": {"$in": ["executed", "pending_approval", "approved", "suggested"]},
        "created_at": {"$gte": cutoff},
    }, {"_id": 0, "id": 1})
    return bool(hit)


async def _build_plan(org_id: str, limit: int) -> list[dict]:
    """Assemble the de-duplicated list of recovery actions to take.

    Priority: a member with a failed PAYMENT is a dunning target (with a
    money retry option queued); otherwise an engagement-churn member is a
    win-back target. One action kind per member per run.
    """
    plan: list[dict] = []
    seen: set[str] = set()

    # 1. Dunning targets (failed/overdue charges) — highest value.
    dunning_rows = await _at_risk_rows(org_id)
    for r in dunning_rows:
        mid = r.get("member_id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        plan.append({
            "member_id": mid,
            "mm_id": r.get("id"),
            "member_name": r.get("member_name"),
            "member_email": r.get("member_email"),
            "kind": "dunning_reminder",
            "reversible": True,
            "source": "payment",
            "evidence": f"{r.get('days_past_due', 0)} days past due · "
                        f"{r.get('plan_name') or 'membership'} (£{r.get('amount', 0):.2f})",
            "amount": r.get("amount", 0),
            "currency": r.get("currency", "gbp"),
            "has_subscription": r.get("has_subscription"),
            "lever": SIGNAL_LEVERS.get("payment_failure", ""),
        })
        if len(plan) >= limit:
            return plan

    # 2. Engagement-churn targets (win-back email).
    try:
        signals = await detect_churn_signals(org_id, limit=limit)
    except Exception:
        logger.exception("[revenue-autopilot] churn detection failed for %s", org_id)
        signals = []
    for s in signals:
        mid = s.get("member_id")
        if not mid or mid in seen:
            continue
        if s.get("signal") == "payment_failure":
            continue  # handled by dunning path above
        seen.add(mid)
        plan.append({
            "member_id": mid,
            "member_name": s.get("full_name"),
            "member_email": s.get("email"),
            "kind": "winback_email",
            "reversible": True,
            "source": "engagement",
            "signal": s.get("signal"),
            "evidence": s.get("signal_evidence"),
            "lever": s.get("primary_recommendation") or "",
            "lifetime_value_gbp": s.get("lifetime_value_gbp"),
        })
        if len(plan) >= limit:
            break
    return plan


async def _ai_rationales(org_id: str, plan: list[dict]) -> dict[str, str]:
    """One grounded LLM call → a concise rationale per action. Falls back
    to the deterministic lever text if the model is unavailable."""
    fallback = {p["member_id"]: (p.get("lever") or p.get("evidence") or "At-risk member.")
                for p in plan}
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key or not plan:
        return fallback
    try:
        await enforce_token_budget(org_id, est_tokens=1500)
    except HTTPException:
        return fallback
    try:
        import json
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        system = (
            "You are the Pulse Fitness Revenue Recovery Autopilot. For each at-risk "
            "member you are given a recovery action and the evidence behind it. "
            "Return STRICT JSON: an array of objects {\"member_id\": str, "
            "\"rationale\": str}. Each rationale is ONE short sentence (max 18 "
            "words) explaining why this action, in plain operator language. "
            "Never invent figures beyond the evidence."
        )
        compact = [{
            "member_id": p["member_id"],
            "action": p["kind"],
            "evidence": p.get("evidence"),
            "signal": p.get("signal") or p.get("source"),
        } for p in plan[:25]]
        chat = LlmChat(api_key=api_key, session_id=f"rev-autopilot-{org_id}",
                       system_message=system)
        chat.with_model(*_MODEL)
        resp = await chat.send_message(UserMessage(
            text="Members:\n" + json.dumps(compact, indent=2) +
                 "\n\nReturn the JSON array only."))
        await record_token_usage(org_id, len(str(resp)) // 3, surface="revenue_autopilot")
        text = (resp or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("["):]
        if "[" in text:
            text = text[text.find("["): text.rfind("]") + 1]
        parsed = json.loads(text)
        out = dict(fallback)
        for row in parsed:
            mid = row.get("member_id")
            rat = (row.get("rationale") or "").strip()
            if mid and rat:
                out[mid] = rat
        return out
    except Exception as exc:
        logger.info("[revenue-autopilot] AI rationale fallback: %s", exc)
        return fallback


# ───────────────────────── execution ─────────────────────────


async def _execute_charge_retry(org_id: str, mm_id: str) -> dict:
    """Retry the EXISTING open Stripe invoice for a past-due membership
    (mirrors membership_dunning.retry_charge — never a new charge)."""
    mm = await db.member_memberships.find_one({"id": mm_id, "organization_id": org_id}, {"_id": 0})
    if not mm:
        return {"ok": False, "error": "membership_not_found"}
    sub_id = mm.get("stripe_subscription_id")
    if not sub_id:
        return {"ok": False, "error": "no_subscription"}
    try:
        invs = stripe.Invoice.list(subscription=sub_id, status="open", limit=1)
        if not invs.data:
            return {"ok": False, "error": "no_open_invoice"}
        paid = stripe.Invoice.pay(invs.data[0].id)
        if paid.status == "paid":
            await db.member_memberships.update_one(
                {"id": mm_id, "organization_id": org_id},
                {"$set": {"billing_status": "current", "updated_at": _now_iso()}})
        await db.member_memberships.update_one(
            {"id": mm_id, "organization_id": org_id},
            {"$push": {"dunning.retries": {"at": _now_iso(), "invoice": paid.id,
                                           "status": paid.status, "by": "autopilot"}}})
        return {"ok": True, "invoice_status": paid.status}
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        return {"ok": False, "error": getattr(e, "user_message", None) or str(e)}


async def _execute_reversible(org_id: str, item: dict) -> bool:
    """Run a reversible recovery action (an email). Returns True on send."""
    kind = item["kind"]
    if kind == "dunning_reminder":
        mm = await db.member_memberships.find_one(
            {"id": item.get("mm_id"), "organization_id": org_id}, {"_id": 0})
        if not mm or mm.get("billing_status") != "past_due":
            return False
        fired = {r.get("stage") for r in mm.get("dunning", {}).get("reminders", [])} \
            if isinstance(mm.get("dunning"), dict) else set()
        stage = _stage_for(_days_past_due(mm), fired) or (max(fired) if fired else 1)
        return await _fire_reminder(org_id, mm, stage)
    if kind == "winback_email":
        member = await db.members.find_one({"id": item["member_id"]}, {"_id": 0})
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        if not member or not org:
            return False
        res = await send_winback_for_member(member, org)
        return bool(res.get("sent"))
    return False


async def _record_action(org_id: str, item: dict, *, status: str,
                         rationale: str, result: dict | None = None) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "member_id": item.get("member_id"),
        "mm_id": item.get("mm_id"),
        "member_name": item.get("member_name"),
        "member_email": item.get("member_email"),
        "kind": item["kind"],
        "source": item.get("source"),
        "reversible": bool(item.get("reversible")),
        "evidence": item.get("evidence"),
        "rationale": rationale,
        "amount": item.get("amount"),
        "currency": item.get("currency"),
        "status": status,
        "result": result or {},
        "created_at": _now_iso(),
        "executed_at": _now_iso() if status == "executed" else None,
    }
    await db.autopilot_actions.insert_one(dict(row))
    row.pop("_id", None)
    return row


async def run_revenue_cycle(org_id: str, *, triggered_by: str = "manual",
                            dry_run: bool = False, force: bool = False) -> dict:
    """One full recovery cycle for an org. Honours the autonomy ladder."""
    settings = await get_settings(org_id)
    level = settings["autonomy_level"]
    if not force and (not settings["revenue_enabled"] or level == "off"):
        return {"skipped": "disabled", "settings": settings}

    plan = await _build_plan(org_id, int(settings["max_actions_per_run"]))
    # Drop members already actioned within the cooldown.
    fresh = []
    for item in plan:
        if await _recently_actioned(org_id, item["member_id"], item["kind"]):
            continue
        fresh.append(item)
    plan = fresh

    rationales = await _ai_rationales(org_id, plan) if plan else {}

    counts = {"executed": 0, "pending_approval": 0, "suggested": 0, "skipped": 0, "failed": 0}
    actions: list[dict] = []

    for item in plan:
        rationale = rationales.get(item["member_id"]) or item.get("lever") or "At-risk member."
        is_money = (item["kind"] == "dunning_reminder" and item.get("has_subscription"))

        if dry_run:
            counts["suggested"] += 1
            actions.append({**item, "status": "planned", "rationale": rationale})
            continue

        # L1 suggest — never auto-act.
        if level == "suggest":
            row = await _record_action(org_id, item, status="suggested", rationale=rationale)
            counts["suggested"] += 1
            actions.append(row)
            continue

        # Reversible action: auto-run at L2/L3.
        ok = await _execute_reversible(org_id, item)
        if ok:
            row = await _record_action(org_id, item, status="executed", rationale=rationale,
                                       result={"channel": "email"})
            counts["executed"] += 1
        else:
            row = await _record_action(org_id, item, status="failed", rationale=rationale,
                                       result={"error": "send_failed_or_not_eligible"})
            counts["failed"] += 1
        actions.append(row)

        # Money follow-up (Stripe retry) — queue for approval unless the
        # org opted into autonomous money actions at L3.
        if is_money:
            money_item = {**item, "kind": "charge_retry", "reversible": False}
            if level == "auto" and settings["allow_money_actions"]:
                res = await _execute_charge_retry(org_id, item["mm_id"])
                st = "executed" if res.get("ok") else "failed"
                mrow = await _record_action(org_id, money_item, status=st,
                                            rationale="Auto-retried the failed Stripe charge.",
                                            result=res)
                counts["executed" if res.get("ok") else "failed"] += 1
                actions.append(mrow)
            else:
                mrow = await _record_action(
                    org_id, money_item, status="pending_approval",
                    rationale="Retrying this card charge moves money — needs your approval.")
                counts["pending_approval"] += 1
                actions.append(mrow)

    await record_ai_action(
        {"organization_id": org_id, "email": triggered_by},
        action="autopilot.revenue.cycle",
        payload={k: v for k, v in counts.items()},
    )
    summary = {
        "ran_at": _now_iso(),
        "triggered_by": triggered_by,
        "dry_run": dry_run,
        "planned": len(plan),
        "counts": counts,
        "actions": actions,
        "settings": settings,
    }
    if not dry_run:
        await db.autopilot_runs.insert_one({
            "id": str(uuid.uuid4()), "organization_id": org_id,
            **{k: summary[k] for k in ("ran_at", "triggered_by", "planned", "counts")},
        })
        if settings["daily_digest"] and triggered_by == "schedule":
            await _send_digest(org_id, summary)
    return summary


# ───────────────────────── digest ─────────────────────────


async def _owner_email(org_id: str) -> str | None:
    owner = await db.users.find_one(
        {"organization_id": org_id, "role": {"$in": ["owner", "admin"]}},
        {"_id": 0, "email": 1}, sort=[("role", 1)])
    if owner and owner.get("email"):
        return owner["email"]
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "primary_contact": 1})
    pc = (org or {}).get("primary_contact") or {}
    return pc.get("email")


async def _send_digest(org_id: str, summary: dict) -> bool:
    to = await _owner_email(org_id)
    if not to:
        return False
    c = summary["counts"]
    if not any(c.values()):
        return False
    pend = c.get("pending_approval", 0)
    rows = "".join(
        f'<li style="margin:4px 0;">{a.get("member_name") or "Member"} — '
        f'<strong>{a.get("kind","").replace("_"," ")}</strong> · {a.get("rationale","")}</li>'
        for a in summary["actions"][:15])
    pend_block = (
        f'<p style="background:#fef3c7;padding:10px 14px;border-radius:8px;color:#92400e;">'
        f'⚠️ {pend} action(s) need your approval (card retries). Open Memberships → '
        f'Autopilot to review.</p>' if pend else "")
    html = (
        f'<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#0f172a">'
        f'<h2 style="color:#1d4ed8">Revenue Autopilot — daily report</h2>'
        f'<p>Here is what your Revenue Recovery Autopilot did:</p>'
        f'<ul style="list-style:none;padding:0;font-size:14px;">'
        f'<li>✅ Sent automatically: <strong>{c.get("executed",0)}</strong></li>'
        f'<li>⏳ Waiting for your approval: <strong>{pend}</strong></li>'
        f'<li>💡 Suggested: <strong>{c.get("suggested",0)}</strong></li>'
        f'</ul>{pend_block}'
        f'<p style="font-size:13px;color:#475569;">Recent actions:</p>'
        f'<ul style="font-size:13px;color:#475569;">{rows}</ul>'
        f'<p style="font-size:12px;color:#94a3b8;">You can change what Autopilot is allowed '
        f'to do in Memberships → Autopilot → Settings.</p></div>')
    return await send_email(to=to, subject="Your Revenue Autopilot daily report",
                            html=html, organization_id=org_id,
                            kind="autopilot.revenue.digest", category="service")


# ───────────────────────── read APIs ─────────────────────────


@router.get("/overview")
async def overview(user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    settings = await get_settings(org_id)
    dunning_rows = await _at_risk_rows(org_id)
    try:
        churn = await detect_churn_signals(org_id, limit=100)
        churn = [s for s in churn if s.get("signal") != "payment_failure"]
    except Exception:
        churn = []
    pending = await db.autopilot_actions.count_documents(
        {"organization_id": org_id, "status": "pending_approval"})
    recent = await db.autopilot_actions.find(
        {"organization_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(20)
    last_run = await db.autopilot_runs.find_one(
        {"organization_id": org_id}, {"_id": 0}, sort=[("ran_at", -1)])
    return {
        "settings": settings,
        "at_risk": {
            "dunning_count": len(dunning_rows),
            "dunning_revenue": round(sum(r["amount"] for r in dunning_rows), 2),
            "churn_count": len(churn),
            "total": len({*(r["member_id"] for r in dunning_rows),
                          *(s["member_id"] for s in churn)}),
        },
        "pending_approvals": pending,
        "recent_actions": recent,
        "last_run": last_run,
    }


@router.get("/actions")
async def list_actions(status: str | None = Query(default=None),
                       user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    q: dict = {"organization_id": org_id}
    if status:
        q["status"] = status
    rows = await db.autopilot_actions.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"actions": rows}


@router.post("/run")
async def run_now(body: dict = Body(default={}), user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    dry_run = bool(body.get("dry_run"))
    # Manual runs are always allowed (force) so an operator can preview /
    # trigger even before flipping the master switch.
    return await run_revenue_cycle(org_id, triggered_by=user.get("email") or "manual",
                                   dry_run=dry_run, force=True)


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    a = await db.autopilot_actions.find_one(
        {"id": action_id, "organization_id": org_id}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Action not found")
    if a.get("status") != "pending_approval":
        raise HTTPException(400, "This action is not awaiting approval")
    result: dict = {}
    new_status = "approved"
    if a.get("kind") == "charge_retry":
        result = await _execute_charge_retry(org_id, a.get("mm_id"))
        new_status = "executed" if result.get("ok") else "failed"
    elif a.get("reversible"):
        ok = await _execute_reversible(org_id, a)
        new_status = "executed" if ok else "failed"
    await db.autopilot_actions.update_one(
        {"id": action_id, "organization_id": org_id},
        {"$set": {"status": new_status, "result": result,
                  "decided_by": user.get("email"), "executed_at": _now_iso()}})
    await record_ai_action(user, action="autopilot.revenue.approve",
                           payload={"action_id": action_id, "result_status": new_status})
    return {"ok": new_status == "executed", "status": new_status, "result": result}


@router.post("/actions/{action_id}/reject")
async def reject_action(action_id: str, user: dict = Depends(get_current_user)):
    org_id = await _operator_org(user)
    res = await db.autopilot_actions.update_one(
        {"id": action_id, "organization_id": org_id, "status": "pending_approval"},
        {"$set": {"status": "rejected", "decided_by": user.get("email"),
                  "decided_at": _now_iso()}})
    if not res.matched_count:
        raise HTTPException(404, "No pending action to reject")
    return {"ok": True, "status": "rejected"}


# ───────────────────────── scheduler ─────────────────────────


async def run_revenue_autopilot_loop(hour: int = 8) -> None:
    """Daily loop: at `hour` Europe/London, run a cycle for every org with
    the Revenue Autopilot enabled. Idempotent per org+date via the
    daily-run lock so multiple backend processes never double-fire."""
    import asyncio
    from utils.daily_run_lock import claim_daily_run
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/London")
    except Exception:
        tz = timezone.utc
    while True:
        try:
            now = datetime.now(tz)
            if now.hour == hour:
                date_str = now.strftime("%Y-%m-%d")
                async for s in db.autopilot_settings.find(
                        {"revenue_enabled": True}, {"_id": 0, "organization_id": 1}):
                    org_id = s.get("organization_id")
                    if not org_id:
                        continue
                    if not await claim_daily_run(db.autopilot_revenue_runs,
                                                 f"{org_id}:{date_str}"):
                        continue
                    try:
                        await run_revenue_cycle(org_id, triggered_by="schedule")
                    except Exception:
                        logger.exception("[revenue-autopilot] org cycle failed: %s", org_id)
        except Exception:
            logger.exception("[revenue-autopilot] loop iteration failed")
        await asyncio.sleep(3600)  # re-check hourly
