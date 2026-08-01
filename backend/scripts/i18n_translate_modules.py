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
    os.path.join(FE, "components", "shared"),
]
NAMESPACES = ("memberships_console", "mkt", "service", "sicon", "settings")


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
    # PartsInventoryPage tabs rendered via t(`service.parts_tab_${tb.id}`, tb.label).
    pairs.update({
        "service.parts_tab_catalogue": "Catalogue",
        "service.parts_tab_stock": "Stock & reorder",
        "service.parts_tab_pos": "Purchase orders",
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
    # MarketingSuite top-tab strip labels (template-literal keys mkt.tab_<tabId>).
    pairs.update({
        "mkt.tab_start": "Start",
        "mkt.tab_performance": "Dashboard",
        "mkt.tab_insights": "Insights",
        "mkt.tab_campaigns": "Campaigns",
        "mkt.tab_journeys": "Journeys",
        "mkt.tab_contacts": "Contacts",
        "mkt.tab_audiences": "Audiences",
        "mkt.tab_dynamic-lists": "Dynamic Lists",
        "mkt.tab_forms-pages": "Forms & Pages",
        "mkt.tab_creative": "Creative Studio",
        "mkt.tab_brand-kit": "Brand Kit",
        "mkt.tab_social": "Social",
    })
    # CampaignWizard template-literal keys (step defs, goals, audiences, channels, time slots).
    pairs.update({
        "mkt.wz_step_goal_title": "Goal",
        "mkt.wz_step_audience_title": "Audience",
        "mkt.wz_step_creative_title": "Creative",
        "mkt.wz_step_schedule_title": "Schedule",
        "mkt.wz_step_review_title": "Review",
        "mkt.wz_step_goal_headline": "What do you want to achieve?",
        "mkt.wz_step_goal_sub": "Pick a goal so we can tailor audience + copy.",
        "mkt.wz_step_audience_headline": "Who should receive this?",
        "mkt.wz_step_audience_sub": "Segment your members — AI suggests a default.",
        "mkt.wz_step_creative_headline": "What is the message?",
        "mkt.wz_step_creative_sub": "Subject + body. AI writes variants in your brand voice.",
        "mkt.wz_step_schedule_headline": "When + where should it go?",
        "mkt.wz_step_schedule_sub": "Channel + time. AI predicts the best slot.",
        "mkt.wz_step_review_headline": "Ready to launch?",
        "mkt.wz_step_review_sub": "One last look before the send.",
        "mkt.wz_goal_fill-classes_label": "Fill empty classes",
        "mkt.wz_goal_fill-classes_hint": "Boost attendance on under-booked sessions",
        "mkt.wz_goal_win-back_label": "Win back inactive",
        "mkt.wz_goal_win-back_hint": "Re-engage members dormant 30+ days",
        "mkt.wz_goal_promote-class_label": "Promote a new class",
        "mkt.wz_goal_promote-class_hint": "Announce to likely-interested members",
        "mkt.wz_goal_upsell-pt_label": "Upsell Personal Training",
        "mkt.wz_goal_upsell-pt_hint": "Offer PT to consistent attendees",
        "mkt.wz_goal_retention_label": "Retention touch",
        "mkt.wz_goal_retention_hint": "Quarterly check-in / appreciation",
        "mkt.wz_goal_custom_label": "Custom goal",
        "mkt.wz_goal_custom_hint": "Define your own objective",
        "mkt.wz_aud_low-bookings-7d_label": "Members with no bookings in 7 days",
        "mkt.wz_aud_inactive-30d_label": "Inactive 30+ days",
        "mkt.wz_aud_class-lovers_label": "Regular class attendees",
        "mkt.wz_aud_consistent-2w_label": "2+ weeks of consistent attendance",
        "mkt.wz_aud_all-active_label": "All active members",
        "mkt.wz_aud_custom_label": "Define with the rule builder",
        "mkt.wz_chan_email": "Email",
        "mkt.wz_chan_sms": "SMS",
        "mkt.wz_time_now": "Send now",
        "mkt.wz_time_best-time": "AI-optimised (Tue 7:00 AM)",
        "mkt.wz_time_custom": "Pick a time…",
    })
    # CreativeStudioTab template-literal keys (types, styles, moods, prompt ideas, categories).
    pairs.update({
        "mkt.cs_type_social_post": "Social post",
        "mkt.cs_type_poster": "Poster",
        "mkt.cs_type_email_hero": "Email hero",
        "mkt.cs_style_photorealistic": "Photorealistic",
        "mkt.cs_style_editorial": "Editorial / magazine",
        "mkt.cs_style_cinematic": "Cinematic film still",
        "mkt.cs_style_illustrated": "Bold illustrated",
        "mkt.cs_style_minimal": "Minimal flat design",
        "mkt.cs_style_duotone": "Duotone print",
        "mkt.cs_mood_0": "Energetic",
        "mkt.cs_mood_1": "Calm & welcoming",
        "mkt.cs_mood_2": "Premium / aspirational",
        "mkt.cs_mood_3": "Bold & confident",
        "mkt.cs_mood_4": "Playful",
        "mkt.cs_mood_5": "Disciplined",
        "mkt.cs_idea_0": "High-energy spin class promotion for Saturday morning",
        "mkt.cs_idea_1": "Empowering kettlebell workout — natural light, motivational",
        "mkt.cs_idea_2": "Premium 1-on-1 PT session — clean studio, deliberate lighting",
        "mkt.cs_idea_3": "Welcome new members — warm, inviting gym lobby",
        "mkt.cs_cat_logo": "Logos",
        "mkt.cs_cat_face": "Faces",
        "mkt.cs_cat_equipment": "Equipment",
        "mkt.cs_cat_photo": "Photos",
        "mkt.cs_cat_brand": "Brand library",
    })
    # AIDirectorPanel template-literal keys (channels, tones, goals, segments, quickstarts, refine actions).
    pairs.update({
        "mkt.dir_chan_email": "Email", "mkt.dir_chan_instagram": "Instagram",
        "mkt.dir_chan_facebook": "Facebook", "mkt.dir_chan_sms": "SMS",
        "mkt.dir_chan_push": "Push", "mkt.dir_chan_poster": "Poster",
        "mkt.dir_tone_high_energy": "High Energy", "mkt.dir_tone_motivational": "Motivational",
        "mkt.dir_tone_premium": "Premium", "mkt.dir_tone_community": "Community",
        "mkt.dir_tone_urgent": "Urgent", "mkt.dir_tone_friendly": "Friendly",
        "mkt.dir_tone_wellness": "Wellness", "mkt.dir_tone_expert_coach": "Expert Coach",
        "mkt.dir_tone_family": "Family", "mkt.dir_tone_mod_military": "MOD / Military",
        "mkt.dir_tone_corporate": "Corporate",
        "mkt.dir_goal_promote_class": "Promote a class", "mkt.dir_goal_winback_lapsed": "Winback lapsed members",
        "mkt.dir_goal_upgrade_pt": "Upsell to PT", "mkt.dir_goal_new_member_welcome": "New member welcome",
        "mkt.dir_goal_open_day": "Open day / event", "mkt.dir_goal_referral": "Drive referrals",
        "mkt.dir_goal_renewal": "Renewals", "mkt.dir_goal_off_peak": "Off-peak fill",
        "mkt.dir_goal_challenge": "Fitness challenge", "mkt.dir_goal_newsletter": "Newsletter",
        "mkt.dir_seg_lapsed_30d_label": "Lapsed 30d", "mkt.dir_seg_lapsed_30d_hint": "Has not visited in 30+ days",
        "mkt.dir_seg_active_regulars_label": "Active regulars", "mkt.dir_seg_active_regulars_hint": "Visits 3+/week",
        "mkt.dir_seg_new_members_30d_label": "New members", "mkt.dir_seg_new_members_30d_hint": "Joined in last 30 days",
        "mkt.dir_seg_pt_eligible_label": "PT eligible", "mkt.dir_seg_pt_eligible_hint": "Regular but no PT yet",
        "mkt.dir_seg_off_peak_visitors_label": "Off-peak crowd", "mkt.dir_seg_off_peak_visitors_hint": "Pre-10am or post-7pm",
        "mkt.dir_seg_frozen_members_label": "Frozen members", "mkt.dir_seg_frozen_members_hint": "Plan currently on freeze",
        "mkt.dir_refine_0": "Make it punchier", "mkt.dir_refine_1": "Add urgency",
        "mkt.dir_refine_2": "Less salesy", "mkt.dir_refine_3": "More premium",
        "mkt.dir_refine_4": "Highlight the offer", "mkt.dir_refine_5": "Friendlier voice",
        "mkt.dir_qs_join_now_label": "Join now", "mkt.dir_qs_join_now_tagline": "Headline join offer — works year-round",
        "mkt.dir_qs_refer_a_friend_label": "Refer a friend", "mkt.dir_qs_refer_a_friend_tagline": "Member-get-member referral push",
        "mkt.dir_qs_pt_kickstart_label": "PT kickstart", "mkt.dir_qs_pt_kickstart_tagline": "Free intro PT session for engaged members",
        "mkt.dir_qs_open_day_label": "Open day", "mkt.dir_qs_open_day_tagline": "Free guest day to drive walk-ins",
        "mkt.dir_qs_winback_label": "Win-back lapsed", "mkt.dir_qs_winback_tagline": "Reactivate members inactive 30+ days",
        "mkt.dir_qs_class_promo_label": "Class promo", "mkt.dir_qs_class_promo_tagline": "Fill an under-booked signature class",
        "mkt.dir_qs_newsletter_label": "Monthly newsletter", "mkt.dir_qs_newsletter_tagline": "House-style monthly digest cover",
        "mkt.dir_qs_challenge_label": "30-day challenge", "mkt.dir_qs_challenge_tagline": "Community fitness challenge launch",
    })
    # PricingMarketingPage (mkt.pr_) — bundle perks, module cards, FAQ (template-literal keys).
    pairs.update({
        "mkt.pr_bundle_tagline": "The full operating system. All modules. All AI. All integrations.",
        "mkt.pr_bundle_perk_0": "All six modules unlocked — Operations, CRM, Memberships, Marketing, Staffing & Reporting",
        "mkt.pr_bundle_perk_1": "AI built into every module — fault triage, lead scoring, churn early-warning, campaign autopilot, RA generator",
        "mkt.pr_bundle_perk_2": "Stripe + Mailchimp + Twilio + Sage 200 / Sicon bridge + open API",
        "mkt.pr_bundle_perk_3": "Master Admin multi-site console with head-office onboarding wizard",
        "mkt.pr_bundle_perk_4": "Real-time KPIs and tamper-evident audit log across every site",
        "mkt.pr_bundle_perk_5": "Family Auto-Bill, Family Wallet, sibling discounts",
        "mkt.pr_bundle_perk_6": "Six selling models, six payroll exports, six reporting cohorts — one platform",
        "mkt.pr_bundle_perk_7": "Priority support + white-glove onboarding",
        "mkt.pr_mod_memberships_name": "Memberships",
        "mkt.pr_mod_memberships_tagline": "For studios that just need members + bookings.",
        "mkt.pr_mod_memberships_feat_0": "Drop-ins, monthly plans, class packs",
        "mkt.pr_mod_memberships_feat_1": "Public booking page + embed widget",
        "mkt.pr_mod_memberships_feat_2": "Branded PWA member portal",
        "mkt.pr_mod_memberships_feat_3": "Stripe payments + email receipts",
        "mkt.pr_mod_memberships_feat_4": "Family Auto-Bill (add-on)",
        "mkt.pr_mod_marketing_name": "Marketing + CRM Lite",
        "mkt.pr_mod_marketing_tagline": "Everything you need to capture, segment, and convert leads.",
        "mkt.pr_mod_marketing_badge": "Includes contact directory",
        "mkt.pr_mod_marketing_feat_0": "Email + SMS campaigns",
        "mkt.pr_mod_marketing_feat_1": "Audience builder + segments",
        "mkt.pr_mod_marketing_feat_2": "AI Director (campaign autopilot)",
        "mkt.pr_mod_marketing_feat_3": "Brand Kit + content templates",
        "mkt.pr_mod_marketing_feat_4": "Contact directory + lead capture forms",
        "mkt.pr_mod_marketing_feat_5": "CSV import + custom properties",
        "mkt.pr_mod_marketing_footnote": "Need pipelines, deals & shared inbox? Upgrade to full CRM (+£49) any time.",
        "mkt.pr_mod_crm_name": "CRM (Full)",
        "mkt.pr_mod_crm_tagline": "Pipelines, deals, shared inbox — for sales-led studios.",
        "mkt.pr_mod_crm_badge": "Most powerful",
        "mkt.pr_mod_crm_feat_0": "Pipeline + deals + lead scoring",
        "mkt.pr_mod_crm_feat_1": "Shared inbox for the whole team",
        "mkt.pr_mod_crm_feat_2": "Email sequences + templates",
        "mkt.pr_mod_crm_feat_3": "Calendar + task automation",
        "mkt.pr_mod_crm_feat_4": "CPQ + quotes (add-on)",
        "mkt.pr_mod_crm_feat_5": "Custom properties + reporting",
        "mkt.pr_mod_crm_footnote": "Already on Marketing? CRM Full adds pipelines + deals + inbox on top of your contact directory.",
        "mkt.pr_mod_operations_name": "Operations",
        "mkt.pr_mod_operations_tagline": "Assets, faults, RAs, supplier portal — keep your sites safe.",
        "mkt.pr_mod_operations_feat_0": "Asset register + barcode/QR scan",
        "mkt.pr_mod_operations_feat_1": "Fault triage with AI",
        "mkt.pr_mod_operations_feat_2": "Risk Assessments + PPM",
        "mkt.pr_mod_operations_feat_3": "Supplier portal + work orders",
        "mkt.pr_mod_operations_feat_4": "Audit log + compliance reports",
        "mkt.pr_faq_0_q": "Is there a free trial?",
        "mkt.pr_faq_0_a": "Yes — every plan includes a 3-day free trial with all modules unlocked. No credit card required. Bring your data, kick the tires, cancel any time.",
        "mkt.pr_faq_1_q": "Can I add or remove sites later?",
        "mkt.pr_faq_1_a": "Yes. Add a site any time and your subscription updates automatically with prorated billing. Remove a site at the end of the billing period — no penalties, no lock-ins.",
        "mkt.pr_faq_2_q": "Can I start with just one module and add more?",
        "mkt.pr_faq_2_a": "Absolutely. Start with the module that solves your biggest pain. When you outgrow it, upgrade to Pulse Fitness Pro and unlock everything else for £150/mo — usually cheaper than two individual modules.",
        "mkt.pr_faq_3_q": "How does multi-site billing work?",
        "mkt.pr_faq_3_a": "Pulse Fitness Pro is £150/mo and includes one site. Every additional site is £50/mo, billed on the same invoice. So 3 sites is £250/mo, 5 sites is £350/mo. Sites can have separate branding, staff, and reports.",
        "mkt.pr_faq_4_q": "What happens after my 3-day trial?",
        "mkt.pr_faq_4_a": "You will be invited to add a card to keep your modules. If you do not convert, your account moves to read-only — your data is preserved for 30 days so you never lose it.",
        "mkt.pr_faq_5_q": "Do you offer Enterprise pricing?",
        "mkt.pr_faq_5_a": "Yes. For chains, franchises, or 10+ sites with advanced needs (SSO, dedicated CSM, custom DPA, ERP sync) — talk to our team.",
    })
    # SecurityMarketingPage (mkt.sec_) — pillars, hardening list, posture links (template-literal keys).
    pairs.update({
        "mkt.sec_pillar_0_title": "Authentication & sessions",
        "mkt.sec_pillar_0_body": "Rotated JWT secret with cryptographic strength, HttpOnly cookies, password reset rate-limits, and brute-force protection on every auth endpoint.",
        "mkt.sec_pillar_1_title": "Encryption everywhere",
        "mkt.sec_pillar_1_body": "TLS 1.3 in transit, AES-256 at rest. Fernet field-level encryption for integration secrets. Stripe handles PCI scope; we never see raw card numbers.",
        "mkt.sec_pillar_2_title": "IDOR-tested endpoints",
        "mkt.sec_pillar_2_body": "Every operator endpoint filters by the caller organisation_id before any read or write. Cross-tenant access returns 404 (never 403) so attackers cannot enumerate IDs by status code. Regression-tested on every deploy.",
        "mkt.sec_pillar_3_title": "Tamper-evident audit log",
        "mkt.sec_pillar_3_body": "Append-only master-admin audit trail with CSV export, dedicated impersonation + export event streams, and hash-chain verification — evidence-grade for SOC 2 and pentests.",
        "mkt.sec_pillar_4_title": "Hardened infrastructure",
        "mkt.sec_pillar_4_body": "Strict CSP, security headers, SSRF allow-list with IMDS + DNS-rebind guards, AV scanning on uploads (ClamAV + static-signature), and dependency CVE auditing on every release.",
        "mkt.sec_pillar_5_title": "Responsible disclosure",
        "mkt.sec_pillar_5_body": "Published security.txt with a canonical contact, expiry date and 90-day safe-harbour. Researchers welcome; we acknowledge within 24 hours.",
        "mkt.sec_hardening_0": "Pen-test ready — 7 hardening waves landed (auth, AI guardrails, web scrubbers, SSRF, AV, audit hygiene, sandbox tenant).",
        "mkt.sec_hardening_1": "AI prompt-injection guardrails on every LLM round-trip (OWASP LLM01-10) — per-tenant token budgets, jailbreak detection, output sanitisation.",
        "mkt.sec_hardening_2": "JWT_SECRET rotated to a 64-hex cryptographically random value. Role-tiered access TTLs; MFA enforceable on every master-admin route.",
        "mkt.sec_hardening_3": "Rate-limits on every auth + money endpoint (login, register, top-up, auto-pay, public demo-request).",
        "mkt.sec_hardening_4": "Stripe webhook hard-requires STRIPE_WEBHOOK_SECRET in production; idempotency keys on every event.",
        "mkt.sec_hardening_5": "Global 500 handler — never leaks raw exception details to the client. /api/health returns ok only (no version / build / commit info).",
        "mkt.sec_hardening_6": "CORS pinned per-environment; wildcard disallowed in production. HSTS preload-ready.",
        "mkt.sec_hardening_7": "/.well-known/security.txt published with a 12-month expiry and rolling refresh.",
        "mkt.sec_hardening_8": "GDPR Art. 17 erasure workflow with 30-day cooling-off; gdpr_erased rows excluded from operator lists + AI RAG contexts.",
        "mkt.sec_posture_link_0": "Data Processing Agreement (DPA)",
        "mkt.sec_posture_link_1": "Sub-processors register",
        "mkt.sec_posture_link_2": "Service Level Agreement (SLA)",
        "mkt.sec_posture_link_3": "Privacy Policy",
        "mkt.sec_posture_link_4": "Terms of Service",
        "mkt.sec_posture_link_5": "security.txt (RFC 9116)",
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
