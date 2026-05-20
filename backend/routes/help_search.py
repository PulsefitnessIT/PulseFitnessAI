"""In-app help search (iter 215c0).

Indexes real product capabilities (modules + the most-trafficked features)
plus the static Help docs. Returns a simple ranked list for the existing
HelpCentrePage search bar.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/help", tags=["help"])


# Hand-curated capability catalogue. Each entry has keywords + a deep link
# operators can click straight to the feature.
CATALOG: list[dict] = [
    # CRM
    {"title": "CRM — Contacts", "module": "crm", "url": "/crm/contacts",
     "summary": "Manage all your contacts, leads, and customers in one directory.",
     "keywords": ["contact", "lead", "customer", "crm", "directory", "list"]},
    {"title": "CRM — Pipeline", "module": "crm", "url": "/crm/pipeline",
     "summary": "Drag-and-drop deals through your sales stages.",
     "keywords": ["deal", "pipeline", "kanban", "opportunity", "sales", "stage"]},
    {"title": "CRM — Companies", "module": "crm", "url": "/crm/companies",
     "summary": "Track company accounts and link contacts to them.",
     "keywords": ["company", "account", "organisation", "crm"]},
    {"title": "CRM — Inbox", "module": "crm", "url": "/crm/inbox",
     "summary": "Unified inbox for emails, calls, and tasks.",
     "keywords": ["inbox", "email", "task", "activity"]},
    {"title": "CRM — Quotes (CPQ)", "module": "crm", "url": "/crm/cpq",
     "summary": "Configure, price, and send quotes to customers.",
     "keywords": ["quote", "cpq", "configure", "price", "proposal"]},
    {"title": "CRM — Tenders", "module": "crm", "url": "/crm/tenders",
     "summary": "Bid management and AI-assisted tender response.",
     "keywords": ["tender", "bid", "rfp", "rfq", "procurement"]},
    # CRM Phase 3 (iter 216h-series)
    {"title": "CRM — Territory Tree", "module": "crm", "url": "/crm?tab=territories",
     "summary": "Drag-and-drop territory hierarchy; forecasts re-attribute in real time.",
     "keywords": ["territory", "hierarchy", "region", "owner", "drag", "tree"]},
    {"title": "CRM — AI Next-Best-Action", "module": "crm", "url": "/crm?tab=companies",
     "summary": "Claude-powered single-action recommendation on every company.",
     "keywords": ["next best action", "ai", "recommend", "next", "action", "claude"]},
    {"title": "CRM — Cross-module Timeline", "module": "crm", "url": "/crm?tab=companies",
     "summary": "Every CRM, Service Ops, and Memberships interaction in one timeline.",
     "keywords": ["timeline", "activity", "cross", "history", "interaction"]},
    {"title": "CRM — Reports (with date filters)", "module": "crm", "url": "/crm?tab=reports",
     "summary": "Filter every CRM report by date range — quarterly comparisons without exports.",
     "keywords": ["report", "analytics", "date", "range", "filter", "quarter"]},

    # Memberships
    {"title": "Memberships — Members", "module": "memberships", "url": "/memberships?tab=members",
     "summary": "Add and manage gym members, plans, and family links.",
     "keywords": ["member", "membership", "join", "gym", "family", "child"]},
    {"title": "Memberships — Plans", "module": "memberships", "url": "/memberships?tab=plans",
     "summary": "Create recurring, fixed-term, class-pack, and PAYG plans.",
     "keywords": ["plan", "subscription", "price", "recurring", "payg", "course"]},
    {"title": "Memberships — Classes", "module": "memberships", "url": "/memberships?tab=classes",
     "summary": "Create class templates, schedule sessions, and manage capacity.",
     "keywords": ["class", "schedule", "timetable", "instructor", "capacity"]},
    {"title": "Memberships — Bookings", "module": "memberships", "url": "/memberships?tab=bookings",
     "summary": "View and manage class bookings and waitlists.",
     "keywords": ["booking", "reserve", "attend", "waitlist"]},
    {"title": "Memberships — Performance", "module": "memberships", "url": "/memberships?tab=performance",
     "summary": "Revenue, retention, and churn analytics.",
     "keywords": ["revenue", "performance", "analytics", "report", "churn", "retention"]},

    # Marketing
    {"title": "Marketing — Campaigns", "module": "marketing", "url": "/marketing-suite?tab=campaigns",
     "summary": "Email and SMS campaign builder with segmentation.",
     "keywords": ["campaign", "email", "sms", "broadcast", "marketing"]},
    {"title": "Marketing — Audiences", "module": "marketing", "url": "/marketing-suite?tab=audiences",
     "summary": "Build static and dynamic audience segments.",
     "keywords": ["audience", "segment", "filter", "targeting"]},
    {"title": "Marketing — Journeys", "module": "marketing", "url": "/marketing-suite?tab=journeys",
     "summary": "Multi-step automation flows triggered by behaviour.",
     "keywords": ["journey", "automation", "drip", "flow", "trigger"]},
    {"title": "Marketing — Lead Forms", "module": "marketing", "url": "/marketing-suite?tab=forms",
     "summary": "Embed lead-capture forms anywhere; leads flow into CRM.",
     "keywords": ["form", "lead", "capture", "embed", "signup"]},
    {"title": "Marketing — Brand Kit", "module": "marketing", "url": "/marketing-suite?tab=brand-kit",
     "summary": "Logo, palette, fonts — applied across every send.",
     "keywords": ["brand", "logo", "palette", "font", "kit"]},

    # Operations
    {"title": "Operations — Equipment", "module": "operations", "url": "/dashboard?tab=equipment",
     "summary": "Asset register with QR codes, manuals, and PPM scheduling.",
     "keywords": ["equipment", "asset", "register", "ppm", "maintenance", "qr"]},
    {"title": "Operations — Issues", "module": "operations", "url": "/dashboard?tab=issues",
     "summary": "Fault triage workflow with AI-assisted diagnosis.",
     "keywords": ["issue", "fault", "problem", "report", "triage"]},
    {"title": "Operations — Risk Assessments", "module": "operations", "url": "/dashboard?tab=risk-assessments",
     "summary": "Document, score, and review site risks.",
     "keywords": ["risk", "assessment", "ra", "h&s", "safety"]},
    {"title": "Operations — Suppliers", "module": "operations", "url": "/dashboard?tab=suppliers",
     "summary": "Supplier directory with contracts and audit trail.",
     "keywords": ["supplier", "vendor", "contract", "po", "purchase"]},
    {"title": "Operations — Check Sheets", "module": "operations", "url": "/dashboard?tab=check-sheets",
     "summary": "Daily/weekly compliance walkrounds.",
     "keywords": ["check", "checksheet", "compliance", "walkround", "audit"]},

    # Account / Settings
    {"title": "Settings — Notification Preferences", "module": "account", "url": "/account?tab=notifications",
     "summary": "Granular email & SMS opt-in/out by category.",
     "keywords": ["notification", "email", "sms", "consent", "gdpr", "preference", "opt"]},
    {"title": "Settings — Usage & Billing", "module": "account", "url": "/account?tab=usage",
     "summary": "Live counters for members, AI tokens, SMS, API calls.",
     "keywords": ["usage", "billing", "limit", "quota", "meter", "tokens"]},
    {"title": "Settings — GDPR", "module": "account", "url": "/account?tab=gdpr",
     "summary": "Export your data or close your account.",
     "keywords": ["gdpr", "export", "delete", "privacy", "data"]},

    # Support / Status
    {"title": "What's New", "module": "support", "url": "/whats-new",
     "summary": "Latest releases and feature updates.",
     "keywords": ["changelog", "whats new", "release", "update"]},
    {"title": "System Status", "module": "support", "url": "/status",
     "summary": "Live status of platform services.",
     "keywords": ["status", "health", "outage", "uptime", "live"]},
    # Onboarding / First Wins (iter 216h227)
    {"title": "First Wins — module-tailored activation", "module": "support", "url": "/account?tab=onboarding",
     "summary": "Your First Wins and Setup Checklist tailor to the module you signed up for.",
     "keywords": ["first wins", "onboarding", "activation", "checklist", "milestone", "trial", "primary module"]},
]


@router.get("/capabilities")
async def search_help(q: str = Query("", min_length=0, max_length=120)) -> dict:
    """Score every catalog entry against the query string and return top 10."""
    query = (q or "").strip().lower()
    if not query:
        # Empty query — return a default "popular" subset.
        return {"results": CATALOG[:10], "query": "", "total": len(CATALOG)}

    tokens = [t for t in query.replace(",", " ").split() if t]
    scored: list[tuple[int, dict]] = []
    for entry in CATALOG:
        haystack = " ".join([
            entry["title"].lower(),
            entry.get("summary", "").lower(),
            " ".join(entry.get("keywords", [])).lower(),
            entry.get("module", "").lower(),
        ])
        score = 0
        for tok in tokens:
            if tok in entry["title"].lower():
                score += 5
            elif tok in haystack:
                score += 2
            # bonus for exact keyword hit
            if tok in entry.get("keywords", []):
                score += 3
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: (-x[0], x[1]["title"]))
    results = [entry for _, entry in scored[:10]]
    return {"results": results, "query": q, "total": len(scored)}
