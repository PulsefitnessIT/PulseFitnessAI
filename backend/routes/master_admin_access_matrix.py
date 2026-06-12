"""Master Admin — Access Matrix (Iter 246).

Read-only, LIVE role × capability grid. Instead of a hand-maintained
table that would drift from the code, this endpoint evaluates the REAL
backend guard functions against synthetic persona users and returns
live headcounts per persona. The frontend mirrors the same personas
against `utils/capabilities.js` for the UI capability rows.

Adding a new gate: append to `_gates()` with the actual guard function —
never re-implement the rule here.
"""
from fastapi import APIRouter, Depends, HTTPException

from utils.auth import get_current_user
from utils.database import db

router = APIRouter(prefix="/master-admin/access-matrix", tags=["Master Admin · Access Matrix"])


# Synthetic persona users — minimal dicts that exercise the guard
# functions exactly like a real session user would. `_jwt_mfa_verified`
# is set so an enabled ENFORCE_MASTER_ADMIN_MFA flag doesn't read as
# "no access" for admin personas.
PERSONAS = [
    {"key": "staff", "label": "Staff",
     "user": {"role": "staff"}},
    {"key": "engineer", "label": "Engineer (org)",
     "user": {"role": "engineer"}},
    {"key": "manager", "label": "Manager",
     "user": {"role": "manager"}},
    {"key": "owner", "label": "Owner",
     "user": {"role": "owner"}},
    {"key": "desk_gymaxis", "label": "Desk agent · GymAxis",
     "user": {"role": "service_desk", "is_service_desk": True,
              "service_desk_brand": "gymaxis", "_jwt_mfa_verified": True}},
    {"key": "desk_pulse", "label": "Desk agent · Pulse",
     "user": {"role": "service_desk", "is_service_desk": True,
              "service_desk_brand": "pulse", "_jwt_mfa_verified": True}},
    {"key": "pulse_master_admin", "label": "Pulse Master Admin",
     "user": {"role": "pulse_master_admin", "is_pulse_admin": True,
              "_jwt_mfa_verified": True}},
    {"key": "master_admin", "label": "GymAxis Master Admin",
     "user": {"role": "owner", "is_master_admin": True,
              "_jwt_mfa_verified": True}},
]

# Live headcount per persona (mutually-exclusive-ish buckets).
_COUNT_QUERIES = {
    "staff": {"role": "staff"},
    "engineer": {"role": "engineer"},
    "manager": {"role": "manager", "is_service_desk": {"$ne": True}},
    "owner": {"role": "owner", "is_master_admin": {"$ne": True}},
    "desk_gymaxis": {"is_service_desk": True, "service_desk_brand": {"$ne": "pulse"}},
    "desk_pulse": {"is_service_desk": True, "service_desk_brand": "pulse"},
    "pulse_master_admin": {
        "is_master_admin": {"$ne": True},
        "$or": [{"is_pulse_admin": True}, {"role": "pulse_master_admin"}],
    },
    "master_admin": {"is_master_admin": True},
}


def _gates() -> list[dict]:
    """The real backend guard functions, imported lazily to dodge any
    import-order surprises. Each entry's `fn` is the production code."""
    from utils.service_desk_auth import _is_service_desk, _is_pulse_scoped
    from routes.svc.engineers_admin import _require_admin
    from routes.master_admin import require_master_admin, require_gymaxis_master_only

    return [
        {"key": "service_desk_access",
         "label": "Service Desk hub (/service-desk)",
         "source": "utils/service_desk_auth._is_service_desk",
         "fn": _is_service_desk},
        {"key": "desk_scoped_to_pulse",
         "label": "Desk views filtered to Pulse customers",
         "source": "utils/service_desk_auth._is_pulse_scoped",
         "fn": _is_pulse_scoped,
         # A data filter, not a privilege — rendered differently in the UI.
         "informational": True},
        {"key": "manage_engineer_roster",
         "label": "Manage engineer roster (create / edit / deactivate)",
         "source": "routes/svc/engineers_admin._require_admin",
         "fn": _require_admin},
        {"key": "master_admin_console",
         "label": "Master Admin console (/master-admin)",
         "source": "routes/master_admin.require_master_admin",
         "fn": require_master_admin},
        {"key": "gymaxis_platform_controls",
         "label": "GymAxis-only platform controls",
         "source": "routes/master_admin.require_gymaxis_master_only",
         "fn": require_gymaxis_master_only},
    ]


def _passes(fn, user: dict) -> bool:
    """Run a guard. Bool guards return their value; raise-style guards
    pass unless they raise an HTTPException."""
    try:
        result = fn(dict(user))
    except HTTPException:
        return False
    if isinstance(result, bool):
        return result
    return True


@router.get("")
async def access_matrix(user: dict = Depends(get_current_user)) -> dict:
    from routes.master_admin import require_master_admin
    require_master_admin(user)

    counts: dict[str, int] = {}
    for key, q in _COUNT_QUERIES.items():
        counts[key] = await db.users.count_documents(q)

    gates_out = [
        {
            "key": g["key"],
            "label": g["label"],
            "source": g["source"],
            "informational": g.get("informational", False),
            "access": {p["key"]: _passes(g["fn"], p["user"]) for p in PERSONAS},
        }
        for g in _gates()
    ]
    return {
        "personas": [
            {"key": p["key"], "label": p["label"], "user": p["user"],
             "count": counts.get(p["key"], 0)}
            for p in PERSONAS
        ],
        "gates": gates_out,
    }
