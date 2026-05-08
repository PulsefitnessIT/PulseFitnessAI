"""Feature-preset engine for Master Admin.

Tender-aware bundles that pre-configure the `organizations.features` map
for a specific customer profile. Admin can apply a preset with one click,
or copy features from an existing org.

Presets are intentionally data-only (no migration needed) so Emergent can
tweak them without a redeploy.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timezone
from typing import Optional

from utils.database import db
from utils.auth import get_current_user


router = APIRouter()


# ── Preset catalogue ─────────────────────────────────────────────
# Each preset is a full override of `organizations.features`.
# Keys not listed default to the account-type default (see feature_guard).
FEATURE_PRESETS: dict = {
    "pulse_basic": {
        "label": "Pulse Basic",
        "description": "Single-site gym, reactive faults only. Minimal feature set.",
        "features": {
            "ai_audits": False, "qr_scanning": True, "multi_site": False,
            "ppm_engine": False, "api_access": False, "white_label": False,
            "crm_pipeline": False, "crm_quotes": False, "crm_tenders": False,
            "crm_ai_tools": False, "crm_workflows": False, "crm_documents": False,
            "kpi_engine": False, "sicon_integration": False, "sage_integration": False,
        },
    },
    "pulse_pro_standard": {
        "label": "Pulse Pro — Standard",
        "description": "Multi-site Pulse Pro. PPM scheduling + QR + AI audits. No enterprise add-ons.",
        "features": {
            "ai_audits": True, "qr_scanning": True, "multi_site": True,
            "ppm_engine": True, "api_access": False, "white_label": False,
            "crm_pipeline": False, "crm_quotes": False, "crm_tenders": False,
            "crm_ai_tools": False, "crm_workflows": False, "crm_documents": False,
            "kpi_engine": False, "sicon_integration": False, "sage_integration": False,
        },
    },
    "pulse_pro_kpi": {
        "label": "Pulse Pro + KPI (Tender Pack)",
        "description": "Pulse Pro with KPI performance reporting unlocked — typical NHS / Leisure tender requirement.",
        "features": {
            "ai_audits": True, "qr_scanning": True, "multi_site": True,
            "ppm_engine": True, "api_access": True, "white_label": False,
            "crm_pipeline": False, "crm_quotes": False, "crm_tenders": False,
            "crm_ai_tools": False, "crm_workflows": False, "crm_documents": False,
            "kpi_engine": True, "sicon_integration": False, "sage_integration": False,
        },
    },
    "pulse_enterprise": {
        "label": "Pulse Enterprise (Full add-ons)",
        "description": "Everything including Sicon + Sage. Top-tier Pulse contract.",
        "features": {
            "ai_audits": True, "qr_scanning": True, "multi_site": True,
            "ppm_engine": True, "api_access": True, "white_label": True,
            "crm_pipeline": True, "crm_quotes": True, "crm_tenders": False,
            "crm_ai_tools": True, "crm_workflows": True, "crm_documents": True,
            "kpi_engine": True, "sicon_integration": True, "sage_integration": True,
        },
    },
    "gymaxis_full": {
        "label": "GymAxis — Full Platform",
        "description": "Everything unlocked. Reserved for GymAxis-branded accounts.",
        "features": {
            "ai_audits": True, "qr_scanning": True, "multi_site": True,
            "ppm_engine": True, "api_access": True, "white_label": True,
            "crm_pipeline": True, "crm_quotes": True, "crm_tenders": True,
            "crm_ai_tools": True, "crm_workflows": True, "crm_documents": True,
            "kpi_engine": True, "sicon_integration": True, "sage_integration": True,
        },
    },
}


def _require_master_admin(user: dict) -> None:
    if not user.get("is_master_admin"):
        raise HTTPException(status_code=403, detail="Master admin required")


async def _log_feature_change(org_id: str, actor_email: str, changes: dict, preset: Optional[str] = None) -> None:
    """Append an audit record into organizations.features_audit."""
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "by": actor_email,
        "changes": changes,
        "preset": preset,
    }
    await db.organizations.update_one(
        {"id": org_id},
        {"$push": {"features_audit": {"$each": [entry], "$slice": -50}}},
    )


@router.get("/master-admin/feature-presets")
async def list_presets(user: dict = Depends(get_current_user)) -> dict:
    _require_master_admin(user)
    return {
        "presets": [
            {"key": k, "label": v["label"], "description": v["description"], "features": v["features"]}
            for k, v in FEATURE_PRESETS.items()
        ],
    }


@router.post("/master-admin/organizations/{org_id}/features/apply-preset")
async def apply_preset(
    org_id: str,
    body: dict = Body(...),
    user: dict = Depends(get_current_user),
) -> dict:
    _require_master_admin(user)
    preset_key = body.get("preset")
    if preset_key not in FEATURE_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset '{preset_key}'")

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "features": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    old_features = org.get("features") or {}
    new_features = dict(FEATURE_PRESETS[preset_key]["features"])
    changes = {k: {"from": old_features.get(k), "to": v}
               for k, v in new_features.items() if old_features.get(k) != v}

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"features": new_features, "features_preset": preset_key}},
    )
    await _log_feature_change(org_id, user.get("email", "?"), changes, preset=preset_key)
    return {"success": True, "features": new_features, "changed": len(changes)}


@router.post("/master-admin/organizations/{org_id}/features/copy-from/{source_org_id}")
async def copy_features_from(
    org_id: str,
    source_org_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    _require_master_admin(user)
    if org_id == source_org_id:
        raise HTTPException(status_code=400, detail="Source and target must differ")

    source = await db.organizations.find_one({"id": source_org_id}, {"_id": 0, "features": 1, "name": 1})
    target = await db.organizations.find_one({"id": org_id}, {"_id": 0, "features": 1})
    if not source or not target:
        raise HTTPException(status_code=404, detail="Organisation not found")

    new_features = dict(source.get("features") or {})
    old_features = target.get("features") or {}
    changes = {k: {"from": old_features.get(k), "to": v}
               for k, v in new_features.items() if old_features.get(k) != v}

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"features": new_features}, "$unset": {"features_preset": ""}},
    )
    await _log_feature_change(
        org_id, user.get("email", "?"), changes,
        preset=f"copy:{source.get('name', source_org_id)}",
    )
    return {"success": True, "features": new_features, "copied_from": source.get("name")}


@router.get("/master-admin/organizations/{org_id}/features/audit")
async def features_audit(org_id: str, user: dict = Depends(get_current_user)) -> dict:
    _require_master_admin(user)
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0, "features_audit": 1, "features_preset": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return {
        "audit": list(reversed(org.get("features_audit") or [])),
        "current_preset": org.get("features_preset"),
    }
