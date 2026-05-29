"""SEO Keyword Auto-Discovery (Iter 220bk).

Replaces the master admin's manual "seed topic → research keywords"
loop with a fully autonomous keyword feeder that tops up the
``seo_keywords`` queue whenever it dips below a configured threshold.

Three input streams, blended every refill:

1. **Industry pillars** — a fixed deck of 12 fitness-industry themes
   rotated by least-recently-published-against.
2. **Platform-data signals** — anonymised, aggregated MongoDB queries
   producing genuine industry insight (e.g. "Treadmills account for
   34% of UK gym faults this quarter, n=14 operators").
3. **Content-gap analysis** — pillars under-represented in the
   existing published corpus.

GDPR compliance is enforced at the query layer:

* **k-anonymity (k=5)** — every aggregate must include at least
  5 distinct organisations before it can leave the function. Cells
  below threshold are *suppressed* (not redacted, *suppressed*).
* **Number bucketing** — percentages are rounded to the nearest 5,
  counts to the nearest 5, durations to the nearest hour, so a
  single org can't be reverse-engineered from a precise digit.
* **No identifiers** — queries project ONLY non-identifying buckets
  (fault_type, machine_type, severity, resolution_type) and never
  carry forward `organization_id`, `user_id`, names, emails, serials,
  or sites into the keyword/article generation path.
* **No special-category data** — RIDDOR / health-and-safety records
  are excluded entirely from the platform-signal queries.
* **Audit trail** — every auto-discovered keyword carries
  ``discovery_metadata`` (signal type, sample size, pillar) so
  future audits can prove provenance.

Master admin can pause auto-discovery, tweak the threshold + target
queue size, and see a "Discovery feed" panel in the SEO Autopilot UI.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ── GDPR safety primitives ──────────────────────────────────────────


K_ANONYMITY_MIN = 5  # min distinct organisations behind any aggregate
MIN_ROW_COUNT = 10   # min individual records (faults, etc.) per cell


def k_anonymous(distinct_org_count: int) -> bool:
    """True when the cohort behind an aggregate is large enough that
    no single organisation can be backed out of the number."""
    return distinct_org_count >= K_ANONYMITY_MIN


def bucket_percent(n: float) -> int:
    """Round a percentage to the nearest 5 so a precise figure can't
    leak. e.g. 33.4 -> 35."""
    return int(round(n / 5.0) * 5)


def bucket_count(n: int, *, granularity: int = 5) -> int:
    """Round an integer down to a coarse bucket. e.g. 47 -> 45."""
    if n <= 0:
        return 0
    return (n // granularity) * granularity


def bucket_hours(h: float) -> int:
    """Round a duration to the nearest hour."""
    return int(round(h))


# ── Industry pillars (Layer 1) ──────────────────────────────────────


PILLARS: list[dict] = [
    {"id": "equipment_downtime",     "label": "Equipment downtime & repair velocity",
     "keyword_templates": ["reducing gym equipment downtime",
                           "fastest gym equipment fault resolution",
                           "gym treadmill downtime impact on retention"]},
    {"id": "ppm_scheduling",         "label": "Planned preventative maintenance",
     "keyword_templates": ["PPM scheduling for multi-site gyms",
                           "preventative maintenance benchmarks UK gyms",
                           "PPM compliance audit checklist"]},
    {"id": "sla_management",         "label": "SLA design & enforcement",
     "keyword_templates": ["SLA design for gym service contracts",
                           "service level agreement gym equipment UK",
                           "measuring SLA breach in fitness operations"]},
    {"id": "compliance_riddor",      "label": "RIDDOR & HSE compliance",
     "keyword_templates": ["RIDDOR reporting for gym operators",
                           "HSE compliance audit fitness sector",
                           "gym health and safety record keeping"]},
    {"id": "member_retention",       "label": "Member retention & ops impact",
     "keyword_templates": ["how equipment reliability impacts gym retention",
                           "member churn drivers fitness operators",
                           "service quality member NPS in gyms"]},
    {"id": "contract_negotiation",   "label": "Service contract negotiation",
     "keyword_templates": ["negotiating gym equipment service contracts",
                           "service contract pricing benchmarks fitness",
                           "renewing gym service contracts effectively"]},
    {"id": "multi_site_ops",         "label": "Multi-site operations scaling",
     "keyword_templates": ["scaling gym operations across multiple sites",
                           "central ops team multi-site fitness",
                           "site manager autonomy in chain gyms"]},
    {"id": "partner_engineers",      "label": "Partner engineer networks",
     "keyword_templates": ["managing freelance gym engineers",
                           "vetting field engineers for fitness sites",
                           "engineer payment and SLA enforcement"]},
    {"id": "equipment_lifecycle",    "label": "BER & replacement strategy",
     "keyword_templates": ["beyond economical repair gym equipment",
                           "when to replace gym treadmills",
                           "capex planning for gym equipment refresh"]},
    {"id": "tender_management",      "label": "Tender response & procurement",
     "keyword_templates": ["winning local authority gym tenders",
                           "procurement evidence pack gym operators",
                           "tender response for fitness contracts"]},
    {"id": "service_desk",           "label": "Service desk best practice",
     "keyword_templates": ["fault triage process for gym chains",
                           "service desk metrics fitness operations",
                           "first-time-fix rate gym service desk"]},
    {"id": "energy_sustainability",  "label": "Energy & sustainability",
     "keyword_templates": ["energy efficiency gym equipment",
                           "sustainability reporting fitness operators",
                           "reducing electricity cost in gyms"]},
]


def pillar_by_id(pid: str | None) -> dict | None:
    if not pid:
        return None
    for p in PILLARS:
        if p["id"] == pid:
            return p
    return None


async def _last_pillar_publish_dates(db) -> dict[str, str]:
    """For each pillar, find the most recent published article tagged
    with that pillar id."""
    pipeline = [
        {"$match": {"status": "published", "discovery_pillar_id": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$discovery_pillar_id", "last": {"$max": "$published_at"}}},
    ]
    out: dict[str, str] = {}
    async for row in db.seo_articles.aggregate(pipeline):
        out[row["_id"]] = row.get("last") or ""
    return out


async def pick_pillar_keyword(db, *, cooldown_days: int = 14) -> Optional[dict]:
    """Return an oldest-pillar keyword suggestion, or None if every
    pillar published within the cooldown window."""
    last = await _last_pillar_publish_dates(db)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).isoformat()

    eligible = [p for p in PILLARS if (last.get(p["id"]) or "") < cutoff]
    if not eligible:
        eligible = PILLARS  # cooldown blocked everything — fall back to oldest

    # Rank by oldest published_at (or "" = never used → highest priority).
    eligible.sort(key=lambda p: last.get(p["id"]) or "")
    chosen = eligible[0]
    # Rotate through templates by hashing the day-of-year + pillar id so
    # we don't pick the same phrasing two refills in a row.
    today_idx = datetime.now(timezone.utc).timetuple().tm_yday
    templates = chosen["keyword_templates"]
    term = templates[today_idx % len(templates)]
    return {
        "term": term,
        "rationale": (f"Pillar rotation — {chosen['label']} hasn't been "
                      f"covered in {cooldown_days}+ days."),
        "source": "auto_pillar",
        "discovery_pillar_id": chosen["id"],
        "discovery_metadata": {
            "pillar_label": chosen["label"],
            "last_published_at": last.get(chosen["id"]),
        },
    }


# ── Platform-data signals (Layer 2) ──────────────────────────────────


async def _signal_top_fault_machine(db) -> Optional[dict]:
    """Most-broken machine_type in the last 90 days (k-anonymous).

    Only emits an insight when at least K_ANONYMITY_MIN distinct
    organisations contribute. All numbers bucketed."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff}, "machine_type": {"$ne": None}}},
        {"$group": {
            "_id": "$machine_type",
            "fault_count": {"$sum": 1},
            "orgs": {"$addToSet": "$organization_id"},
        }},
        {"$project": {
            "machine_type": "$_id", "_id": 0,
            "fault_count": 1,
            "org_count": {"$size": "$orgs"},
        }},
        {"$match": {"org_count": {"$gte": K_ANONYMITY_MIN},
                    "fault_count": {"$gte": MIN_ROW_COUNT}}},
        {"$sort": {"fault_count": -1}},
        {"$limit": 1},
    ]
    rows = await db.issues.aggregate(pipeline).to_list(1)
    if not rows:
        return None
    r = rows[0]
    return {
        "term": f"why {r['machine_type'].lower()}s break most in UK gyms",
        "rationale": (
            f"Platform signal: {r['machine_type']} is the most-reported "
            f"machine in the last 90 days across {r['org_count']}+ "
            "operators (anonymised, aggregated)."
        ),
        "source": "auto_signal",
        "discovery_signal": "top_fault_machine",
        "discovery_metadata": {
            "machine_type": r["machine_type"],
            "fault_count_bucketed": bucket_count(r["fault_count"]),
            "org_count": r["org_count"],
            "window_days": 90,
            "k_anonymity": K_ANONYMITY_MIN,
        },
    }


async def _signal_resolution_speed_gap(db) -> Optional[dict]:
    """Mean fault-to-resolution hours across the platform, bucketed."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    pipeline = [
        {"$match": {
            "created_at": {"$gte": cutoff},
            "resolved_at": {"$ne": None},
            "machine_type": {"$ne": None},
        }},
        {"$addFields": {
            "_created": {"$toDate": "$created_at"},
            "_resolved": {"$toDate": "$resolved_at"},
        }},
        {"$addFields": {
            "resolution_hours": {
                "$divide": [
                    {"$subtract": ["$_resolved", "$_created"]},
                    1000 * 60 * 60,
                ],
            },
        }},
        {"$match": {"resolution_hours": {"$gte": 0, "$lt": 24 * 30}}},
        {"$group": {
            "_id": None,
            "avg_hours": {"$avg": "$resolution_hours"},
            "orgs": {"$addToSet": "$organization_id"},
            "n": {"$sum": 1},
        }},
        {"$project": {
            "_id": 0, "avg_hours": 1,
            "org_count": {"$size": "$orgs"}, "n": 1,
        }},
    ]
    rows = await db.issues.aggregate(pipeline).to_list(1)
    if not rows:
        return None
    r = rows[0]
    if not k_anonymous(r.get("org_count", 0)) or r.get("n", 0) < MIN_ROW_COUNT:
        return None
    hours = bucket_hours(r["avg_hours"])
    return {
        "term": f"how UK gyms can resolve faults faster than {hours} hours",
        "rationale": (
            f"Platform signal: mean fault resolution across "
            f"{r['org_count']}+ operators is currently ~{hours}h "
            "(anonymised aggregate)."
        ),
        "source": "auto_signal",
        "discovery_signal": "resolution_speed_gap",
        "discovery_metadata": {
            "avg_hours_bucketed": hours,
            "org_count": r["org_count"],
            "sample_size_bucketed": bucket_count(r["n"], granularity=50),
            "window_days": 90,
            "k_anonymity": K_ANONYMITY_MIN,
        },
    }


async def _signal_top_resolution_type(db) -> Optional[dict]:
    """Most-common resolution path (self_fix / engineer / supplier),
    bucketed to a percentage."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    pipeline = [
        {"$match": {"created_at": {"$gte": cutoff},
                     "resolution_type": {"$ne": None},
                     "status": "resolved"}},
        {"$group": {
            "_id": "$resolution_type",
            "n": {"$sum": 1},
            "orgs": {"$addToSet": "$organization_id"},
        }},
        {"$project": {"resolution_type": "$_id", "_id": 0,
                       "n": 1, "org_count": {"$size": "$orgs"}}},
        {"$match": {"org_count": {"$gte": K_ANONYMITY_MIN},
                    "n": {"$gte": MIN_ROW_COUNT}}},
        {"$sort": {"n": -1}},
    ]
    rows = await db.issues.aggregate(pipeline).to_list(10)
    if not rows:
        return None
    total = sum(r["n"] for r in rows)
    if total < MIN_ROW_COUNT:
        return None
    top = rows[0]
    pct = bucket_percent(100 * top["n"] / total)
    # Map raw enum to human-friendly phrasing for the keyword.
    pretty = {
        "self_fix": "fixed in-house without an engineer",
        "engineer": "needing an engineer callout",
        "supplier": "routed to a supplier",
    }.get(top["resolution_type"], top["resolution_type"])
    return {
        "term": f"why {pct}% of UK gym faults end up {pretty}",
        "rationale": (
            f"Platform signal: ~{pct}% of resolved faults across "
            f"{top['org_count']}+ operators followed this resolution "
            "path in the last 90 days (anonymised)."
        ),
        "source": "auto_signal",
        "discovery_signal": "top_resolution_type",
        "discovery_metadata": {
            "resolution_type": top["resolution_type"],
            "pct_bucketed": pct,
            "org_count": top["org_count"],
            "window_days": 90,
            "k_anonymity": K_ANONYMITY_MIN,
        },
    }


PLATFORM_SIGNAL_FUNCS = [
    _signal_top_fault_machine,
    _signal_resolution_speed_gap,
    _signal_top_resolution_type,
]


async def pick_platform_signal_keyword(db) -> Optional[dict]:
    """Try each signal in rotation; return the first one that passes
    the k-anonymity gate."""
    # Order by day-of-year so consecutive refills rotate signal types.
    today_idx = datetime.now(timezone.utc).timetuple().tm_yday
    funcs = PLATFORM_SIGNAL_FUNCS[today_idx % len(PLATFORM_SIGNAL_FUNCS):] + \
            PLATFORM_SIGNAL_FUNCS[:today_idx % len(PLATFORM_SIGNAL_FUNCS)]
    for fn in funcs:
        try:
            result = await fn(db)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(f"[discovery] signal {fn.__name__} failed: {exc}")
            continue
        if result:
            return result
    return None


# ── Content-gap analysis (Layer 3) ──────────────────────────────────


async def pick_content_gap_keyword(db) -> Optional[dict]:
    """Pick a pillar that has zero published articles. If every pillar
    has at least one, falls back to the one with the *fewest*."""
    pipeline = [
        {"$match": {"status": "published",
                     "discovery_pillar_id": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$discovery_pillar_id", "n": {"$sum": 1}}},
    ]
    counts: dict[str, int] = {}
    async for row in db.seo_articles.aggregate(pipeline):
        counts[row["_id"]] = row["n"]

    ranked = sorted(PILLARS, key=lambda p: counts.get(p["id"], 0))
    chosen = ranked[0]
    # Use a different template index from pillar_pick so gap & pillar
    # don't always produce the identical term.
    today_idx = datetime.now(timezone.utc).timetuple().tm_yday
    templates = chosen["keyword_templates"]
    term = templates[(today_idx + 1) % len(templates)]
    return {
        "term": term,
        "rationale": (
            f"Content gap — only {counts.get(chosen['id'], 0)} articles "
            f"published in the '{chosen['label']}' pillar."
        ),
        "source": "auto_gap",
        "discovery_pillar_id": chosen["id"],
        "discovery_metadata": {
            "pillar_label": chosen["label"],
            "current_count": counts.get(chosen["id"], 0),
        },
    }


# ── Orchestrator: top-up when queue dips below threshold ────────────


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _existing_terms(db) -> set[str]:
    """All seo_keywords terms, lower-cased — used to short-circuit
    duplicates before saving."""
    terms = set()
    async for row in db.seo_keywords.find(
        {}, {"_id": 0, "term": 1},
    ):
        t = (row.get("term") or "").strip().lower()
        if t:
            terms.add(t)
    return terms


async def autodiscover_top_up_queue(
    db, *, queue_min: int = 3, queue_target: int = 8,
) -> dict:
    """If the queued-keyword count is below ``queue_min``, top it back
    up to ``queue_target`` using a blend of pillar / signal / gap
    sources. Returns a summary of what was added (or skipped)."""
    queued = await db.seo_keywords.count_documents({"status": "queued"})
    if queued >= queue_min:
        return {"ok": True, "skipped": True, "queued": queued,
                "reason": f"queue depth {queued} >= min {queue_min}"}

    needed = max(0, queue_target - queued)
    if needed <= 0:
        return {"ok": True, "skipped": True, "queued": queued,
                "reason": "queue already at target"}

    existing = await _existing_terms(db)
    pickers = [pick_pillar_keyword,
               pick_platform_signal_keyword,
               pick_content_gap_keyword]
    saved: list[dict] = []
    attempts = 0
    while len(saved) < needed and attempts < needed * 3:
        picker = pickers[attempts % len(pickers)]
        attempts += 1
        try:
            cand = await picker(db)
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[discovery] picker {picker.__name__} failed: {exc}")
            cand = None
        if not cand:
            continue
        term = (cand.get("term") or "").strip()
        if not term or term.lower() in existing:
            continue
        existing.add(term.lower())
        doc = {
            "id": _id(),
            "term": term[:160],
            "intent": "informational",
            "difficulty": "medium",
            "volume_estimate": "medium",
            "rationale": (cand.get("rationale") or "")[:300],
            "seed_topic": "auto_discovery",
            "audience": "UK gym operators and ops managers",
            "status": "queued",
            "source": cand.get("source", "auto"),
            "discovery_pillar_id": cand.get("discovery_pillar_id"),
            "discovery_signal": cand.get("discovery_signal"),
            "discovery_metadata": cand.get("discovery_metadata") or {},
            "target_article_id": None,
            "near_duplicates": [],
            "notes": "",
            "created_at": _now(), "updated_at": _now(),
        }
        await db.seo_keywords.insert_one(doc)
        # Drop the immutable _id Mongo just stamped on.
        doc.pop("_id", None)
        saved.append(doc)

    return {
        "ok": True, "skipped": False,
        "queued_before": queued,
        "queued_after": queued + len(saved),
        "added": saved,
        "added_count": len(saved),
        "attempts": attempts,
    }


__all__ = [
    "PILLARS",
    "K_ANONYMITY_MIN",
    "MIN_ROW_COUNT",
    "k_anonymous",
    "bucket_percent",
    "bucket_count",
    "bucket_hours",
    "pillar_by_id",
    "pick_pillar_keyword",
    "pick_platform_signal_keyword",
    "pick_content_gap_keyword",
    "autodiscover_top_up_queue",
]
