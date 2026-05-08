from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
import logging

from utils.database import db
from utils.auth import get_current_user, get_organization_filter
from utils.email import send_email
from utils.helpers import get_equipment_stats

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/digest/preview")
async def preview_weekly_digest(user: dict = Depends(get_current_user)):
    org_filter = get_organization_filter(user)

    open_issues = await db.issues.find({**org_filter, "status": "open"}, {"_id": 0}).to_list(50)
    in_progress = await db.issues.find({**org_filter, "status": "in_progress"}, {"_id": 0}).to_list(50)

    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    recent_sheets = await db.check_sheets.find(
        {**org_filter, "created_at": {"$gte": week_ago}}, {"_id": 0}
    ).to_list(100)

    equipment_list = await db.equipment.find(org_filter, {"_id": 0}).to_list(200)
    equipment_health = []
    for equip in equipment_list[:20]:
        stats = await get_equipment_stats(equip['id'], user)
        health_score = 100
        if stats.get('open_issues', 0) > 0:
            health_score -= stats['open_issues'] * 15
        if not stats.get('warranty_active'):
            health_score -= 10
        health_score = max(0, health_score)
        equipment_health.append({
            "name": equip['name'],
            "type": equip.get('equipment_type'),
            "health_score": health_score,
            "open_issues": stats.get('open_issues', 0),
            "warranty_active": stats.get('warranty_active', False)
        })

    recent_ras = await db.risk_assessments.find(
        {**org_filter, "created_at": {"$gte": week_ago}}, {"_id": 0}
    ).to_list(10)

    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": f"{(datetime.now(timezone.utc) - timedelta(days=7)).strftime('%d %b')} - {datetime.now(timezone.utc).strftime('%d %b %Y')}",
        "summary": {
            "open_issues": len(open_issues),
            "in_progress_issues": len(in_progress),
            "critical_issues": len([i for i in open_issues if i.get('severity') == 'critical']),
            "check_sheets_completed": len(recent_sheets),
            "risk_assessments_completed": len(recent_ras),
            "avg_health_score": round(sum(e['health_score'] for e in equipment_health) / max(len(equipment_health), 1))
        },
        "open_issues": [{"serial_number": i.get('serial_number', i.get('machine_name', 'N/A')), "machine_type": i.get('machine_type'), "severity": i.get('severity'), "created_at": i.get('created_at')} for i in open_issues[:10]],
        "equipment_health": sorted(equipment_health, key=lambda x: x['health_score'])[:10],
        "check_sheets_completed": len(recent_sheets),
    }
    return digest


@router.post("/digest/send")
async def send_weekly_digest(user: dict = Depends(get_current_user)):
    digest = await preview_weekly_digest(user)

    html = f"""<div style="font-family: Arial; max-width: 600px; margin: 0 auto;">
    <div style="background: #0055FF; padding: 20px; text-align: center;">
        <h2 style="color: white; margin: 0;">Weekly Maintenance Digest</h2>
        <p style="color: rgba(255,255,255,0.8); margin: 5px 0 0;">{digest['period']}</p>
    </div>
    <div style="padding: 30px; background: #f9f9f9;">
        <h3>Summary</h3>
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;">Open Issues</td><td style="padding: 8px; text-align: right; font-weight: bold; border-bottom: 1px solid #ddd;">{digest['summary']['open_issues']}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;">Critical Issues</td><td style="padding: 8px; text-align: right; font-weight: bold; color: red; border-bottom: 1px solid #ddd;">{digest['summary']['critical_issues']}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;">In Progress</td><td style="padding: 8px; text-align: right; font-weight: bold; border-bottom: 1px solid #ddd;">{digest['summary']['in_progress_issues']}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;">Check Sheets This Week</td><td style="padding: 8px; text-align: right; font-weight: bold; border-bottom: 1px solid #ddd;">{digest['summary']['check_sheets_completed']}</td></tr>
            <tr><td style="padding: 8px;">Avg Equipment Health</td><td style="padding: 8px; text-align: right; font-weight: bold;">{digest['summary']['avg_health_score']}%</td></tr>
        </table>

        <h3 style="margin-top: 20px;">Equipment Requiring Attention</h3>
        {''.join(f'<div style="padding: 8px; margin: 4px 0; background: white; border-left: 3px solid {"red" if e["health_score"] < 50 else "orange" if e["health_score"] < 80 else "green"};"><strong>{e["name"]}</strong> - Health: {e["health_score"]}% | Open Issues: {e["open_issues"]}</div>' for e in digest['equipment_health'][:5]) or '<p>All equipment in good condition</p>'}

        <p style="margin-top: 20px; text-align: center;">
            <a href="#" style="display: inline-block; background: #0055FF; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">View Full Dashboard</a>
        </p>
    </div>
    </div>"""

    sent = await send_email(user['email'], f"GymAxis AI - Weekly Digest ({digest['period']})", html)
    return {"sent": sent, "digest": digest, "message": "Digest sent" if sent else "Email not configured - preview available above"}


# ─── P4 — Configurable digest with per-channel toggles ───────────
# The /digest/preview endpoint above is the legacy one-off preview. These new
# routes let owners/managers pick WHAT they see and HOW OFTEN they receive it.

from fastapi import HTTPException
from utils.digest import (
    dispatch_due_digests,
    get_preferences,
    send_for_user,
    set_preferences,
)


def _require_manager(u: dict) -> None:
    if u.get("is_master_admin"):
        return
    if u.get("role") not in ("owner", "manager"):
        raise HTTPException(status_code=403, detail="Only owners or managers can manage digests")


@router.get("/digest/preferences")
async def read_preferences(user: dict = Depends(get_current_user)) -> dict:
    return await get_preferences(user["id"])


@router.put("/digest/preferences")
async def update_preferences(patch: dict, user: dict = Depends(get_current_user)) -> dict:
    _require_manager(user)
    return await set_preferences(user["id"], patch or {})


@router.post("/digest/send-now")
async def send_now(user: dict = Depends(get_current_user)) -> dict:
    """Fire a test digest across every enabled channel. Soft-fails when there
    are no open nudges."""
    _require_manager(user)
    prefs = await get_preferences(user["id"])
    fresh_user = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or user
    result = await send_for_user(fresh_user, prefs)
    return {"success": True, **result, "sent": bool(result.get("email") or result.get("teams"))}


@router.post("/digest/test-teams")
async def test_teams(user: dict = Depends(get_current_user)) -> dict:
    """Send a small hand-crafted card to the user's Teams webhook. Useful for
    the 'Send test' button next to the webhook input before real data exists."""
    _require_manager(user)
    prefs = await get_preferences(user["id"])
    url = (prefs.get("teams_webhook_url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="No Teams webhook URL saved")
    from utils.teams_webhook import render_adaptive_card, post_to_teams
    fresh_user = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or user
    sample_payload = {
        "summary": "This is a sample test from your digest preferences",
        "items": [{
            "type": "nudge.warranty_expiring",
            "severity": "low",
            "customer_safe_message": "If you see this card in Teams, your webhook is wired up correctly!",
        }],
    }
    card = render_adaptive_card(fresh_user, sample_payload, "test")
    delivered = await post_to_teams(url, card)
    return {"success": True, "delivered": delivered}


@router.post("/digest/run")
async def run_all(user: dict = Depends(get_current_user)) -> dict:
    """Master-admin manual trigger — runs the full dispatcher for all users."""
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin only")
    totals = await dispatch_due_digests()
    return {"success": True, **totals}
