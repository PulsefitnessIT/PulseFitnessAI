"""Supplier catalogue — curated UK fitness equipment suppliers.

Iter 216h193 — Lee's standardisation pass. When a user adds equipment,
the supplier field should be a dropdown populated with well-known UK
fitness equipment suppliers (Pulse, Technogym, Life Fitness, etc.) so
they don't end up with "TechnoGym", "Technogym", "techno gym" all
sitting alongside each other in reports.

The curated list lives in code (not the DB) because it's the same for
every org and we want it available even for brand-new tenants with no
supplier directory of their own yet. It's exposed at:

    GET /api/suppliers/catalogue

…which returns ``{curated: [...], custom: [...], all: [...]}`` so the
UI can render an autocomplete with two groups (curated first, then
the org's own entries).

If an org later adds the same name via ``POST /api/suppliers`` it's
flagged as ``source="custom"`` so the curated entry doesn't double up.

Why these brands?
    Sourced from the UK Active supplier directory + Pulse Fitness's
    own preferred-vendor list. Covers cardio, strength, free weights,
    functional, and accessories — the long tail of "we got this from
    Amazon" entries falls back to free-text via the "Add new…" option
    in the autocomplete.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from utils.auth import get_current_user, get_organization_filter
from utils.database import db


router = APIRouter()


# ────────────────────────────────────────────────────────────────────
# Curated UK fitness equipment supplier list.
#
# Fields:
#   slug          — stable id used by the photo-lookup pipeline.
#   name          — display label.
#   categories    — equipment categories the supplier covers.
#   website       — public site (used for the "Visit website" affordance).
#   logo_url      — hosted on jsDelivr CDN (mirrors the supplier badge
#                   wall on the marketing site; same assets reused).
#   default_callout_fee, labour_rate_per_hour, mileage_rate, parts_markup_pct
#                 — pre-fill suggestions for the supplier add-edit form.
#                   Operators can override per-supplier.
# ────────────────────────────────────────────────────────────────────
CURATED_SUPPLIERS: list[dict] = [
    {"slug": "pulse-fitness", "name": "Pulse Fitness",
     "categories": ["cardio", "strength", "functional"],
     "website": "https://www.pulsefitness.com", "logo_url": ""},
    {"slug": "technogym", "name": "Technogym",
     "categories": ["cardio", "strength", "functional", "wellness"],
     "website": "https://www.technogym.com", "logo_url": ""},
    {"slug": "life-fitness", "name": "Life Fitness",
     "categories": ["cardio", "strength", "free_weights"],
     "website": "https://www.lifefitness.com", "logo_url": ""},
    {"slug": "precor", "name": "Precor",
     "categories": ["cardio", "strength"],
     "website": "https://www.precor.com", "logo_url": ""},
    {"slug": "matrix", "name": "Matrix Fitness",
     "categories": ["cardio", "strength"],
     "website": "https://www.matrixfitness.com", "logo_url": ""},
    {"slug": "cybex", "name": "Cybex",
     "categories": ["strength", "cardio"],
     "website": "https://www.cybexintl.com", "logo_url": ""},
    {"slug": "star-trac", "name": "Star Trac",
     "categories": ["cardio", "strength"],
     "website": "https://www.startrac.com", "logo_url": ""},
    {"slug": "hoist", "name": "Hoist Fitness",
     "categories": ["strength"],
     "website": "https://www.hoistfitness.com", "logo_url": ""},
    {"slug": "concept2", "name": "Concept2",
     "categories": ["rowers", "ergometers"],
     "website": "https://www.concept2.com", "logo_url": ""},
    {"slug": "wattbike", "name": "Wattbike",
     "categories": ["cardio", "indoor_cycling"],
     "website": "https://wattbike.com", "logo_url": ""},
    {"slug": "keiser", "name": "Keiser",
     "categories": ["strength", "indoor_cycling"],
     "website": "https://www.keiser.com", "logo_url": ""},
    {"slug": "trx", "name": "TRX",
     "categories": ["functional", "accessories"],
     "website": "https://www.trxtraining.com", "logo_url": ""},
    {"slug": "eleiko", "name": "Eleiko",
     "categories": ["free_weights", "strength"],
     "website": "https://www.eleiko.com", "logo_url": ""},
    {"slug": "hammer-strength", "name": "Hammer Strength",
     "categories": ["strength"],
     "website": "https://www.lifefitness.com/en-gb/catalog/strength/hammer-strength", "logo_url": ""},
    {"slug": "origin-fitness", "name": "Origin Fitness",
     "categories": ["strength", "functional", "free_weights", "accessories"],
     "website": "https://www.originfitness.com", "logo_url": ""},
    {"slug": "escape-fitness", "name": "Escape Fitness",
     "categories": ["functional", "accessories"],
     "website": "https://escapefitness.com", "logo_url": ""},
    {"slug": "physical-company", "name": "Physical Company",
     "categories": ["functional", "accessories", "free_weights"],
     "website": "https://www.physicalcompany.co.uk", "logo_url": ""},
    {"slug": "fitness-superstore", "name": "Fitness Superstore",
     "categories": ["cardio", "strength", "free_weights"],
     "website": "https://www.fitness-superstore.co.uk", "logo_url": ""},
    {"slug": "sole-fitness", "name": "Sole Fitness",
     "categories": ["cardio"],
     "website": "https://www.solefitness.com", "logo_url": ""},
    {"slug": "nordictrack", "name": "NordicTrack",
     "categories": ["cardio"],
     "website": "https://www.nordictrack.com", "logo_url": ""},
    {"slug": "proform", "name": "ProForm",
     "categories": ["cardio"],
     "website": "https://www.proform.com", "logo_url": ""},
    {"slug": "schwinn", "name": "Schwinn",
     "categories": ["cardio", "indoor_cycling"],
     "website": "https://www.schwinnfitness.com", "logo_url": ""},
    {"slug": "stairmaster", "name": "StairMaster",
     "categories": ["cardio"],
     "website": "https://www.stairmaster.com", "logo_url": ""},
    {"slug": "powerplate", "name": "Power Plate",
     "categories": ["functional", "wellness"],
     "website": "https://www.powerplate.com", "logo_url": ""},
    {"slug": "jordan-fitness", "name": "Jordan Fitness",
     "categories": ["free_weights", "functional", "accessories"],
     "website": "https://www.jordanfitness.com", "logo_url": ""},
]


def _curated_dict() -> dict[str, dict]:
    return {s["name"].lower(): s for s in CURATED_SUPPLIERS}


@router.get("/suppliers/catalogue/public")
async def suppliers_catalogue_public() -> dict:
    """Public, curated-only catalogue for unauth surfaces.

    Iter 216h217 — Craig's audit: the public engineer-apply wizard
    ("which brands do you service?") still used a free-text input.
    Frontends serving anonymous users now drop the same
    `SupplierAutocomplete` component pointed at this endpoint; the
    component multi-select works against the same shape.
    """
    items = [{**s, "source": "curated"} for s in CURATED_SUPPLIERS]
    return {
        "curated": items,
        "custom": [],
        "all": items,
        "total": len(items),
    }


@router.get("/suppliers/catalogue")
async def suppliers_catalogue(user: dict = Depends(get_current_user)):
    """Merged supplier list for autocomplete:
       - ``curated``: the global UK fitness equipment supplier list.
       - ``custom`` : suppliers this org has added (deduped against curated).
       - ``all``    : ``curated + custom`` ordered alphabetically, each item
                      tagged ``source: "curated" | "custom"`` so the UI can
                      show a "Curated" / "Yours" group label.
    """
    org_filter = get_organization_filter(user)
    org_suppliers = await db.suppliers.find(
        org_filter,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "phone": 1,
         "supplier_types": 1, "callout_fee": 1, "labour_rate_per_hour": 1},
    ).sort("name", 1).to_list(500)

    seen = set()
    curated_items = []
    for s in CURATED_SUPPLIERS:
        curated_items.append({**s, "source": "curated"})
        seen.add(s["name"].strip().lower())

    custom_items = []
    for s in org_suppliers:
        key = (s.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        custom_items.append({
            "id": s.get("id"),
            "slug": key.replace(" ", "-"),
            "name": s.get("name"),
            "email": s.get("email"),
            "phone": s.get("phone"),
            "categories": s.get("supplier_types") or [],
            "source": "custom",
        })

    combined = sorted(curated_items + custom_items, key=lambda x: x["name"].lower())
    return {
        "curated": curated_items,
        "custom": custom_items,
        "all": combined,
        "total": len(combined),
    }


@router.get("/suppliers/catalogue/photo-lookup")
async def supplier_photo_lookup(
    supplier: str,
    model: str = "",
    _user: dict = Depends(get_current_user),
):
    """Best-effort photo lookup for newly added equipment.

    Iter 216h193 — Lee's ask: "once the user has selected the supplier
    and saved the equipment the platform should look for the relevant
    photo." We don't crawl the supplier site from this endpoint
    (rate-limit / legal risk); instead we surface the best URL we know
    about from our own spec-sheet library, falling back to an empty
    string. The frontend uses the result to pre-fill ``photo_url`` so
    the operator can confirm-or-replace it.
    """
    supplier_key = (supplier or "").strip().lower()
    model_key = (model or "").strip().lower()
    if not supplier_key:
        return {"photo_url": "", "source": "none"}

    # 1) Exact spec-sheet match on (supplier, model).
    if model_key:
        spec = await db.spec_sheets.find_one(
            {"manufacturer": {"$regex": f"^{supplier_key}$", "$options": "i"},
             "model": {"$regex": f"^{model_key}$", "$options": "i"}},
            {"_id": 0, "photo_url": 1, "image_url": 1},
        )
        if spec:
            url = spec.get("photo_url") or spec.get("image_url") or ""
            if url:
                return {"photo_url": url, "source": "spec_sheet_exact"}

    # 2) Supplier-level fallback: pick *any* spec sheet for this supplier.
    spec = await db.spec_sheets.find_one(
        {"manufacturer": {"$regex": f"^{supplier_key}$", "$options": "i"}},
        {"_id": 0, "photo_url": 1, "image_url": 1},
    )
    if spec:
        url = spec.get("photo_url") or spec.get("image_url") or ""
        if url:
            return {"photo_url": url, "source": "spec_sheet_supplier"}

    return {"photo_url": "", "source": "none"}
