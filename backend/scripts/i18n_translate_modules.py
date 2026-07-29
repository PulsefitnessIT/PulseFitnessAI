#!/usr/bin/env python3
"""
Generalised i18n helper for the Memberships / Marketing / ServiceOps modules.

Scans the configured module dirs for t('ns.key','English default') calls in the
listed namespaces, translates any NEW/untranslated key EN->FR & EN->DE via Claude,
and merges into i18n/locales/{en,fr,de}.json.

Reuses the exact extraction + translation logic from i18n_translate_ops.py.

Run: cd /app/backend && python scripts/i18n_translate_modules.py
     cd /app/backend && python scripts/i18n_translate_modules.py --check   (guard only)
"""
import os, re, json, asyncio, sys

FE = "/app/frontend/src"
LOCALES = os.path.join(FE, "i18n", "locales")

# Module dirs to scan and the namespaces they own. Add more as batches land.
SCAN_DIRS = [
    os.path.join(FE, "pages", "Memberships"),
    os.path.join(FE, "pages", "Marketing"),
    os.path.join(FE, "pages", "ServiceOps"),
    os.path.join(FE, "pages", "ServiceDesk"),
]
NAMESPACES = ("memberships_console", "mkt", "service", "sicon")


def read_quoted(s, i):
    q = s[i]
    if q not in "'\"`":
        return None, i
    i += 1
    buf = []
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            mp = {"n": "\n", "t": "\t", "'": "'", '"': '"', "`": "`", "\\": "\\"}
            buf.append(mp.get(nxt, nxt))
            i += 2
            continue
        if c == q:
            return "".join(buf), i + 1
        buf.append(c)
        i += 1
    return None, i


def extract_pairs(text):
    pairs = {}
    for m in re.finditer(r"\bt\(\s*(['\"])", text):
        start = m.end() - 1
        key, j = read_quoted(text, start)
        if key is None or not key.startswith(tuple(n + "." for n in NAMESPACES)):
            continue
        while j < len(text) and text[j] in " \t\n\r":
            j += 1
        if j >= len(text) or text[j] != ",":
            continue
        j += 1
        while j < len(text) and text[j] in " \t\n\r":
            j += 1
        if j >= len(text) or text[j] not in "'\"`":
            continue
        default, _ = read_quoted(text, j)
        if default is None:
            continue
        pairs[key] = default
    return pairs


def scan():
    pairs = {}
    for d in SCAN_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                if fn.endswith(".js") or fn.endswith(".jsx"):
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        pairs.update(extract_pairs(f.read()))
    return pairs


_NS_T_CALL = re.compile(r"\bt\(\s*['\"](?:%s)\." % "|".join(NAMESPACES))


def guard_missing_hook():
    offenders = []
    for d in SCAN_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                if not (fn.endswith(".js") or fn.endswith(".jsx")):
                    continue
                path = os.path.join(root, fn)
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                if not _NS_T_CALL.search(text):
                    continue
                if "useTranslation" not in text:
                    offenders.append(os.path.relpath(path, FE))
    return offenders


def load(name):
    with open(os.path.join(LOCALES, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, data):
    with open(os.path.join(LOCALES, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_nested(d, dotted):
    ns, _, key = dotted.partition(".")
    return d.get(ns, {}).get(key)


def set_nested(d, dotted, value):
    ns, _, key = dotted.partition(".")
    d.setdefault(ns, {})[key] = value


async def translate_batch(pairs, target_lang_name):
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    key = os.environ.get("EMERGENT_LLM_KEY") or "sk-emergent-8E60eC543A620FcAaE"
    chat = LlmChat(
        api_key=key,
        session_id=f"i18n-modules-{target_lang_name}",
        system_message=(
            f"You are a professional software UI translator. Translate the given JSON object's "
            f"English UI string VALUES into {target_lang_name}. Keep the JSON keys EXACTLY the same. "
            f"Preserve placeholders, punctuation, leading/trailing spaces, em-dashes, and symbols "
            f"(e.g. '·', '—', '£', '%', ':'). Do NOT translate brand/product names (Pulse, Sage, "
            f"Sicon, Claude, CSV, PIN, NI Number, AI, GDPR). Return ONLY a valid JSON object, no prose."
        ),
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    items = list(pairs.items())
    out = {}
    CH = 60
    for i in range(0, len(items), CH):
        chunk = dict(items[i:i + CH])
        msg = "Translate the VALUES of this JSON to " + target_lang_name + ":\n" + json.dumps(chunk, ensure_ascii=False)
        resp = await chat.send_message(UserMessage(text=msg))
        raw = resp if isinstance(resp, str) else str(resp)
        s = raw.find("{"); e = raw.rfind("}")
        try:
            out.update(json.loads(raw[s:e + 1]))
        except Exception as ex:
            print(f"  ! parse fail chunk {i}: {ex}", file=sys.stderr)
    return out


async def main():
    offenders = guard_missing_hook()
    if offenders:
        print("\n\033[1;31m✗ i18n GUARD FAILED\033[0m — files call namespaced t() but never wire useTranslation():")
        for o in offenders:
            print(f"    • {o}")
        if "--check" in sys.argv:
            sys.exit(1)
    else:
        print("✓ i18n guard: every scanned file using namespaced t() wires useTranslation().")
    if "--check" in sys.argv:
        return

    pairs = scan()
    # Explicit nav labels for the Service Desk shell (rendered via template-literal
    # keys t(`service.nav_${id}`, label) which the static scanner can't extract).
    service_nav = {
        "service.nav_dashboard": "Dashboard", "service.nav_cases": "Cases",
        "service.nav_scheduler": "Scheduler", "service.nav_customers": "Customers",
        "service.nav_equipment": "Equipment", "service.nav_maintenance": "Maintenance",
        "service.nav_stores": "Stores", "service.nav_billing": "Billing",
        "service.nav_analytics": "Analytics", "service.nav_expenses": "Expenses",
        "service.nav_safety": "H&S checklist", "service.nav_compliance": "Compliance",
        "service.nav_overview": "Analytics", "service.nav_suppliers": "Supplier health",
        "service.nav_reports": "Reports", "service.nav_imports": "Import data",
        "service.nav_integrations": "Integrations", "service.nav_audit": "Audit log",
        "service.nav_account": "Account settings", "service.nav_engineers": "Engineers",
        "service.nav_brand": "Service Desk", "service.nav_brand_sub": "Field service ops",
        "service.nav_inventory_distribution": "Inventory & Distribution",
        "service.nav_insights_group": "Insights", "service.nav_options": "Options",
    }
    pairs.update(service_nav)
    # Invoice status chips rendered via t(`memberships_console.inv_status_${status}`, status).
    pairs.update({
        "memberships_console.inv_status_draft": "draft",
        "memberships_console.inv_status_sent": "sent",
        "memberships_console.inv_status_paid": "paid",
        "memberships_console.inv_status_void": "void",
    })
    # Events: kind labels + costume statuses (rendered via template-literal keys).
    pairs.update({
        "memberships_console.evt_kind_recital": "Recital",
        "memberships_console.evt_kind_showcase": "Showcase",
        "memberships_console.evt_kind_competition": "Competition",
        "memberships_console.evt_kind_workshop": "Workshop",
        "memberships_console.evt_kind_camp": "Camp",
        "memberships_console.evt_kind_other": "Event",
        "memberships_console.evt_costume_needed": "needed",
        "memberships_console.evt_costume_ordered": "ordered",
        "memberships_console.evt_costume_arrived": "arrived",
        "memberships_console.evt_costume_fitted": "fitted",
        "memberships_console.evt_costume_paid": "paid",
        "memberships_console.evt_costume_refunded": "refunded",
    })
    # CRM Loop signal-kind labels (rendered via template-literal keys).
    pairs.update({
        "memberships_console.crml_kind_missed_class": "Missed class",
        "memberships_console.crml_kind_inactive_30d": "Inactive 30d",
        "memberships_console.crml_kind_low_attendance": "Low attendance",
        "memberships_console.crml_kind_high_engagement": "High engagement",
    })
    # MemberPortal bottom-nav + more-sheet labels (rendered via template-literal keys).
    pairs.update({
        "memberships_console.mp_tab_home": "Home",
        "memberships_console.mp_tab_book": "Book",
        "memberships_console.mp_tab_bookings": "Bookings",
        "memberships_console.mp_tab_pass": "Pass",
        "memberships_console.mp_tab_more": "More",
        "memberships_console.mp_more_plan": "My plan",
        "memberships_console.mp_more_family": "Family accounts",
        "memberships_console.mp_more_events": "Events & shows",
        "memberships_console.mp_more_profile": "Profile & settings",
    })
    # StudioBuilder day abbreviations (rendered via template-literal keys sb_day_{i}).
    pairs.update({
        "memberships_console.sb_day_0": "Mon",
        "memberships_console.sb_day_1": "Tue",
        "memberships_console.sb_day_2": "Wed",
        "memberships_console.sb_day_3": "Thu",
        "memberships_console.sb_day_4": "Fri",
        "memberships_console.sb_day_5": "Sat",
        "memberships_console.sb_day_6": "Sun",
    })
    # AnalyticsTab section + role labels (rendered via template-literal keys).
    pairs.update({
        "memberships_console.an_sec_overview": "Overview",
        "memberships_console.an_sec_retention": "Retention",
        "memberships_console.an_sec_classes": "Classes",
        "memberships_console.an_sec_operations": "Operations",
        "memberships_console.an_sec_studio-brain": "Studio Brain",
        "memberships_console.an_sec_ai-insights": "AI Insights",
        "memberships_console.an_role_manager": "Gym manager",
        "memberships_console.an_role_regional": "Regional mgr",
        "memberships_console.an_role_director": "Director",
    })
    # DynamicListsTab refresh-interval options (template-literal keys dl_refresh_opt_{minutes}).
    pairs.update({
        "mkt.dl_refresh_opt_15": "Every 15 minutes",
        "mkt.dl_refresh_opt_60": "Hourly (default)",
        "mkt.dl_refresh_opt_240": "Every 4 hours",
        "mkt.dl_refresh_opt_1440": "Daily",
    })
    # ProductPreviewModal scene titles + captions (template-literal keys mkt.pp_title_/caption_<sceneId>).
    pairs.update({
        "mkt.pp_title_fault-triage": "Operations · AI fault triage",
        "mkt.pp_title_rota": "Staffing · AI rota in seconds",
        "mkt.pp_title_campaign": "Marketing · AI Director writes your campaign",
        "mkt.pp_title_memberships": "Memberships · Family Auto-Bill",
        "mkt.pp_title_crm": "CRM · AI lead scoring",
        "mkt.pp_title_reporting": "Reporting · One-screen weekly digest",
        "mkt.pp_caption_fault-triage": "Snap the fault. Claude triages it, suggests parts, routes the ticket — in under 6 seconds.",
        "mkt.pp_caption_rota": "Claude builds a fair, compliant week. £-cost roll-up. One-click apply. Sage CSV export.",
        "mkt.pp_caption_campaign": "Pick a goal. AI drafts copy + audience + send time. Approve. Send. £14 average revenue lift per member.",
        "mkt.pp_caption_memberships": "One household. Multiple plans. Sibling discounts auto-applied. One Stripe invoice.",
        "mkt.pp_caption_crm": "Prioritise the lead most likely to close. AI explains why. Drop into a sequence. One click.",
        "mkt.pp_caption_reporting": "Revenue. Churn. Faults. Cohort retention. Auto-emailed every Monday — to you and your owner.",
    })
    # StarterPackPanel email meta labels + hints (template-literal keys mkt.sp_email_<id>_label/hint).
    pairs.update({
        "mkt.sp_email_welcome_label": "Welcome",
        "mkt.sp_email_welcome_hint": "For new sign-ups",
        "mkt.sp_email_win_back_label": "Win-back",
        "mkt.sp_email_win_back_hint": "For lapsed members",
        "mkt.sp_email_promo_label": "Promo",
        "mkt.sp_email_promo_hint": "Current campaign push",
    })
    # MarketingTour step titles + bodies (template-literal keys mkt.mt_<stepId>_title/body).
    pairs.update({
        "mkt.mt_welcome_title": "Your AI marketing co-pilot",
        "mkt.mt_welcome_body": "Built for fitness operators — segmentation, campaigns, AI creatives, and visual journeys, all in one place. The next 60 seconds will show you the four things that get a Pulse club its first £1k of recovered revenue.",
        "mkt.mt_audiences_title": "Audiences in plain English",
        "mkt.mt_audiences_body": "Type high spenders at risk of churning — AI builds a live, dynamic segment that updates as members come and go. No SQL. No spreadsheets. Just intent.",
        "mkt.mt_campaigns_title": "Quick-start campaign templates",
        "mkt.mt_campaigns_body": "6 pre-built recipes — Welcome new member, Win-back, Class promo, PT upsell, Failed payment, Referral — auto-target the right audience with copy already filled in. Ship in 60 seconds.",
        "mkt.mt_creative_title": "AI-generated marketing imagery",
        "mkt.mt_creative_body": "Type a mood — high-energy spin Saturday morning — and gpt-image-1 generates branded posters, social tiles, and email heroes in ~30 seconds. Or upload your own photos.",
        "mkt.mt_journeys_title": "Visual automation journeys",
        "mkt.mt_journeys_body": "Drag-and-drop trigger → wait → send → branch → tag. Welcome series, win-back sequences, post-class follow-ups — design them like a flowchart and they run themselves.",
        "mkt.mt_performance_title": "Attribution that actually works",
        "mkt.mt_performance_body": "Every booking and payment within 7 days of an opened/clicked email auto-attributes back to the campaign. See which messages drive real money — not just clicks.",
        "mkt.mt_demo_title": "Want to see it with your data?",
        "mkt.mt_demo_body": "I can spin up disposable demo data right now — one VIP audience, a draft Saturday-spin campaign, an AI-generated poster, and a Welcome-new-member journey. Tagged demo and removable in one click.",
    })
    # TrialSignupModal module labels + blurbs (template-literal keys mkt.ts_mod_<key>_label/blurb).
    pairs.update({
        "mkt.ts_mod_operations_label": "Operations",
        "mkt.ts_mod_operations_blurb": "Equipment, faults, maintenance & asset management",
        "mkt.ts_mod_memberships_label": "Memberships",
        "mkt.ts_mod_memberships_blurb": "Members, plans, classes & bookings",
        "mkt.ts_mod_crm_label": "CRM",
        "mkt.ts_mod_crm_blurb": "Sales pipeline, contacts & deals",
        "mkt.ts_mod_marketing_label": "Marketing",
        "mkt.ts_mod_marketing_blurb": "Campaigns, automations & content",
    })
    # MobileAppBuilder font / button-style / share-format labels (template-literal keys).
    pairs.update({
        "memberships_console.mab_font_inter": "Clean",
        "memberships_console.mab_font_poppins": "Friendly",
        "memberships_console.mab_font_manrope": "Modern",
        "memberships_console.mab_font_nunito": "Rounded",
        "memberships_console.mab_font_space": "Techy",
        "memberships_console.mab_btn_soft": "Soft",
        "memberships_console.mab_btn_pill": "Pill",
        "memberships_console.mab_btn_sharp": "Sharp",
        "memberships_console.mab_fmt_square": "Square (post)",
        "memberships_console.mab_fmt_story": "Story",
    })
    print(f"Extracted {len(pairs)} t() keys in namespaces {NAMESPACES} (incl. {len(service_nav)} service_nav)")
    en, fr, de = load("en.json"), load("fr.json"), load("de.json")

    for k, v in pairs.items():
        if get_nested(en, k) != v:
            set_nested(en, k, v)

    need_fr = {k: v for k, v in pairs.items() if not get_nested(fr, k) or get_nested(fr, k) == v}
    need_de = {k: v for k, v in pairs.items() if not get_nested(de, k) or get_nested(de, k) == v}
    print(f"Need FR: {len(need_fr)} · Need DE: {len(need_de)}")

    if need_fr:
        fr_tr = await translate_batch(need_fr, "French")
        for k, v in fr_tr.items():
            if k in pairs:
                set_nested(fr, k, v)
        print(f"FR translated: {len(fr_tr)}")
    if need_de:
        de_tr = await translate_batch(need_de, "German")
        for k, v in de_tr.items():
            if k in pairs:
                set_nested(de, k, v)
        print(f"DE translated: {len(de_tr)}")

    save("en.json", en)
    save("fr.json", fr)
    save("de.json", de)
    print("Merged en/fr/de.json")


if __name__ == "__main__":
    asyncio.run(main())
