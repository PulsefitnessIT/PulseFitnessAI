"""Issue route helpers — extracted from triage_issue() and create_issue() for maintainability."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
import asyncio
import logging

from utils.database import db, RESEND_API_KEY, SENDER_EMAIL
from utils.security_plus import safe_regex
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # noqa: F401
import json as json_module
import os

logger = logging.getLogger(__name__)

_LANG_MAP = {"fr": "French", "de": "German", "en": "English"}

_TRIAGE_SYSTEM_TEMPLATE = """You are an expert gym equipment technician performing triage assessment. ONLY respond to queries about gym equipment faults, fitness equipment, and gym environment issues. If asked about anything unrelated, return a generic "not applicable" response.
You must return ONLY valid JSON with no extra text, markdown, or code fences.

Return this exact JSON structure:
{{
  "diagnosis": "Brief analysis of the likely cause",
  "can_fix_onsite": true or false,
  "repair_steps": [
    {{"step": 1, "title": "Step title", "instruction": "Detailed instruction", "safety_note": "Any safety warning or null"}},
    {{"step": 2, "title": "Step title", "instruction": "Detailed instruction", "safety_note": null}}
  ],
  "tools_needed": ["tool1", "tool2"],
  "estimated_time": "15-30 minutes",
  "engineer_reason": "Why an engineer is needed (if can_fix_onsite is false), otherwise null",
  "severity_assessment": "Your assessment of actual severity: operational_minor/operational_fault/limited_use/out_of_order/safety_critical. operational_minor = machine usable with minor annoyance. operational_fault = works but not as intended, could worsen. limited_use = machine partially usable but restricted. out_of_order = cannot be used, must be taken out of service. safety_critical = immediate safety hazard, must isolate immediately.",
  "fault_code": "The BEST matching fault code from the FAULT CODE TAXONOMY provided in the user prompt. Return ONLY the code (e.g. 'BEL-01', 'MOT-02'), exactly as listed. If no code fits well, return null. Prefer specific mechanical/electrical codes over OTH-02 (Unknown)."
}}

CRITICAL — TARGET AUDIENCE: Your repair steps will be read and carried out by GYM STAFF (front-of-house, duty managers, cleaning staff) — NOT qualified engineers. Therefore:
- Use plain, non-technical language. Explain terminology when used (e.g. "the drive belt — the rubber loop that connects the motor to the flywheel").
- Steps must be SAFE for non-technical staff. If a step involves removing panels, accessing electrics, or any risk of injury, mark can_fix_onsite as false and recommend an engineer instead.
- Focus on what staff CAN do: visual inspections, power cycling, checking connections, cleaning, basic adjustments (tightening bolts, lubricating visible parts), and observation/reporting.
- Never ask gym staff to disassemble equipment, work near exposed electrics, adjust motor components, or perform any task that could void the warranty or risk injury.
- Keep steps to 3-5 maximum. Be specific about what to check, how to check it, and what the expected result should be. Include safety notes where relevant.

IMPORTANT — Pulse Fitness Parts Policy: If the diagnosis indicates a replacement part is needed, include this note in your response: "Pulse Fitness will arrange for the replacement part to be sent directly to your site." Do NOT tell the customer to source parts themselves.

PLATFORM CONTEXT — You are running INSIDE the PulseFitness.ai operations portal. The gym staff member is logging THIS fault directly in the portal right now; submitting it automatically raises the job and dispatches it to the assigned engineer / service provider. Therefore you must NOT instruct the user to "log a service call with Pulse Fitness", "contact/call Pulse Fitness", "raise a ticket", "book an engineer" or "report this to the service desk" as a separate action — that is already handled the moment they submit this fault. When an engineer is required, phrase it as the fault "will be sent to the assigned engineer via the portal" (or "leave the remaining checks for the attending engineer"), and keep your repair_steps focused only on what on-site staff can safely check or do before the engineer attends.{lang_instruction}"""


def build_triage_system_message(language: str) -> str:
    """Build the triage system message with optional language instruction."""
    response_lang = _LANG_MAP.get(language, "English")
    if language != "en":
        lang_instruction = f"\n\nIMPORTANT: Respond with ALL text values in {response_lang}. The JSON keys must remain in English, but ALL string values must be written in {response_lang}."
    else:
        lang_instruction = ""
    return _TRIAGE_SYSTEM_TEMPLATE.format(lang_instruction=lang_instruction)


def build_triage_prompt(issue) -> str:
    """Build the base triage prompt from issue data (includes fault-code taxonomy for auto-tag)."""
    from constants.fault_codes import FAULT_CODE_CATEGORIES

    prompt = (
        f"Equipment Type: {issue.machine_type}\n"
        f"Serial Number: {issue.serial_number}\n"
        f"Issue Description: {issue.issue_description}\n"
        f"Reported Severity: {issue.severity}\n"
        f"Supplier: {issue.supplier or 'Not specified'}"
    )
    if issue.steps_taken:
        prompt += (
            f"\n\nSTEPS ALREADY TAKEN BY THE USER (DO NOT repeat these):\n{issue.steps_taken}\n\n"
            "IMPORTANT: Since the user has already attempted the above steps, skip those in your repair steps. "
            "Start from the NEXT logical diagnostic step beyond what they've tried."
        )

    # Inject the fault-code taxonomy so the AI can return a machine-readable code
    prompt += "\n\nFAULT CODE TAXONOMY — pick the single BEST matching code for `fault_code` in your response:"
    for cat in FAULT_CODE_CATEGORIES:
        codes_inline = ", ".join(f"{c} ({label})" for c, label, _d in cat["codes"])
        prompt += f"\n• {cat['label']}: {codes_inline}"
    prompt += "\nReturn null for `fault_code` only if no listed code reasonably matches."

    return prompt


async def append_past_fixes(prompt: str, machine_type: str, org_id: Optional[str]) -> str:
    """Append proven past fixes to the triage prompt."""
    org_filter = {"organization_id": org_id} if org_id else {"organization_id": None}
    past_fixes = await db.fix_history.find(
        {**org_filter, "machine_type": safe_regex(machine_type)}, {"_id": 0}
    ).sort("created_at", -1).to_list(10)

    if not past_fixes:
        return prompt

    prompt += "\n\nPREVIOUSLY SUCCESSFUL FIXES for this equipment type (PRIORITISE these proven solutions):\n"
    for idx, fix in enumerate(past_fixes[:5]):
        prompt += f"\n{idx+1}. Issue: {fix.get('issue_description', 'N/A')}"
        if fix.get('fix_title'):
            prompt += f"\n   Fix that worked: {fix['fix_title']}"
        if fix.get('fix_step'):
            prompt += f"\n   Step detail: {fix['fix_step']}"
        if fix.get('fix_note'):
            prompt += f"\n   Additional notes: {fix['fix_note']}"
    prompt += "\n\nIMPORTANT: If any of the above fixes are relevant, include them as the FIRST repair steps."
    return prompt


def format_knowledge_context(knowledge_docs: list) -> str:
    """Format knowledge documents into a context string for the AI prompt."""
    if not knowledge_docs:
        return ""

    text = "\n\nRELEVANT DOCUMENT KNOWLEDGE (from uploaded equipment manuals, service guides & certificates):\n"
    for idx, kd in enumerate(knowledge_docs[:5]):
        k = kd.get('extraction', {})
        equip_info = k.get('equipment_info', {})
        source = f"{kd.get('supplier_name', '')} {equip_info.get('model', '')}".strip()
        text += f"\n--- Source: {source or kd.get('filename', 'Document ' + str(idx+1))} ---\n"
        if equip_info:
            text += f"Equipment: {equip_info.get('manufacturer', '')} {equip_info.get('model', '')} ({equip_info.get('equipment_type', '')})\n"
        for section, label, fmt in [
            ("common_faults", "Known faults", lambda f: f"  - {f.get('fault','')}: {f.get('symptoms','')} -> Fix: {f.get('fix','')} [Severity: {f.get('severity','N/A')}]"),
            ("troubleshooting_tips", "Troubleshooting tips", lambda t: f"  - {t}"),
            ("spare_parts", "Spare parts", lambda p: f"  - {p.get('part','')}: Part# {p.get('part_number','')}"),
            ("safety_warnings", "Safety warnings", lambda w: f"  - {w}"),
            ("maintenance_schedule", "Maintenance schedule", lambda m: f"  - {m.get('task','')}: {m.get('frequency','')}"),
        ]:
            items = k.get(section)
            if items:
                text += f"{label}:\n"
                for item in items[:5]:
                    text += fmt(item) + "\n"
        if k.get('key_specifications'):
            text += f"Key specs: {', '.join(k['key_specifications'][:4])}\n"
    text += "\nIMPORTANT: Reference the specific manual/document source. If spare parts are needed, include exact part numbers."
    return text


async def call_ai_with_retry(chat: LlmChat, message: UserMessage, max_retries: int = 3) -> str:
    """Call AI with exponential backoff on rate limits."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return await chat.send_message(message)
        except Exception as err:
            last_error = err
            err_str = str(err).lower()
            if 'rate' in err_str or '429' in err_str or 'limit' in err_str:
                wait_time = (attempt + 1) * 2
                logger.warning(f"AI rate limited (attempt {attempt+1}/{max_retries}), retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                raise
    raise Exception(f"AI rate limited after {max_retries} retries. Last error: {last_error}")


def parse_ai_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from AI response."""
    cleaned = raw.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    return json_module.loads(cleaned)


def build_fallback_triage(severity: str, error_msg: str) -> dict:
    """Build a fallback triage response when AI is unavailable."""
    if any(kw in error_msg for kw in ('rate', '429', 'limit', 'budget')):
        diagnosis = "AI triage temporarily unavailable — your Emergent LLM key balance may need topping up. Please go to Profile > Universal Key > Add Balance, then try again."
    else:
        diagnosis = "AI triage temporarily unavailable — please assess manually based on your experience."

    return {
        "diagnosis": diagnosis,
        "can_fix_onsite": None,
        "repair_steps": [
            {"step": 1, "title": "Safety First", "instruction": "Isolate the equipment and place an 'Out of Order' sign.", "safety_note": "Do not use until assessed"},
            {"step": 2, "title": "Visual Inspection", "instruction": "Check for obvious damage, loose parts, or unusual wear.", "safety_note": None},
            {"step": 3, "title": "Report", "instruction": "If you cannot identify the issue, log it for an engineer.", "safety_note": None},
        ],
        "tools_needed": [],
        "estimated_time": "Varies",
        "engineer_reason": None,
        "severity_assessment": severity,
        "fault_code": None,
        "raw_triage": "Triage unavailable - please assess manually",
    }


async def store_fix_history(issue, issue_id: str, user: dict) -> None:
    """Store a self-fix record for AI learning."""
    if issue.resolution_type != "self_fix":
        return
    if not (issue.selected_fix_step or issue.resolution_note):
        return

    import uuid
    await db.fix_history.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": user.get('organization_id'),
        "machine_type": issue.machine_type,
        "issue_description": issue.issue_description,
        "severity": issue.severity,
        "fix_step": issue.selected_fix_step,
        "fix_title": issue.selected_fix_title,
        "fix_note": issue.resolution_note,
        "issue_id": issue_id,
        "fixed_by": user.get('full_name'),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def _severity_badge(severity: str) -> tuple[str, str]:
    """Return (bg_color, label) for a severity value."""
    mapping = {
        "safety_critical": ("#dc2626", "Safety Critical"),
        "out_of_order": ("#ef4444", "Out of Order"),
        "critical": ("#ef4444", "Out of Order"),
        "limited_use": ("#f97316", "Limited Use"),
        "operational_fault": ("#eab308", "Operational - Fault Present"),
        "medium": ("#eab308", "Operational - Fault Present"),
    }
    bg, label = mapping.get(severity, ("#22c55e", "Operational - Minor Issue"))
    return bg, label


_ENGINEER_EMAIL_STYLE = """
  body { margin:0; padding:0; background:#F4F5F7; }
  .wrap { width:100%; background:#F4F5F7; padding:24px 12px; }
  .card { max-width:640px; margin:0 auto; background:#ffffff; border:1px solid #E5E7EB;
          border-radius:12px; overflow:hidden; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif; color:#111827; }
  .hero { padding:28px 32px; text-align:left; color:#ffffff; }
  .hero-brand { font-size:12px; letter-spacing:0.12em; text-transform:uppercase; opacity:0.85; margin:0 0 6px; font-weight:600; }
  .hero-title { font-size:22px; margin:0; font-weight:700; line-height:1.25; }
  .hero-meta  { margin:10px 0 0; font-size:13px; opacity:0.85; }
  .hero-ref   { display:inline-block; padding:4px 10px; background:rgba(0,0,0,0.25);
                color:#ffffff; border-radius:999px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
                font-size:11px; letter-spacing:0.05em; }
  .content { padding:28px 32px; }
  .lead { font-size:15px; line-height:1.55; margin:0 0 20px; color:#1F2937; }
  .kv { width:100%; border-collapse:collapse; margin:4px 0 20px; border:1px solid #E5E7EB; border-radius:10px; overflow:hidden; }
  .kv td { padding:12px 16px; font-size:14px; border-bottom:1px solid #F1F5F9; vertical-align:top; }
  .kv tr:last-child td { border-bottom:0; }
  .kv .lbl { color:#6B7280; width:170px; font-size:12px; text-transform:uppercase; letter-spacing:0.04em; font-weight:600; }
  .kv .val { color:#111827; font-weight:600; }
  .chip-sev { display:inline-block; color:#ffffff; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700; letter-spacing:0.02em; }
  .panel { background:#F8FAFC; border:1px solid #E5E7EB; border-radius:10px; padding:18px 20px; margin:0 0 20px; }
  .panel h4 { margin:0 0 8px; font-size:13px; color:#0F172A; text-transform:uppercase; letter-spacing:0.05em; font-weight:700; }
  .panel p { margin:0; color:#1F2937; font-size:14px; line-height:1.55; white-space:pre-wrap; }
  .triage { background:#EFF6FF; border-color:#BFDBFE; }
  .triage h4 { color:#1D4ED8; }
  .grid { width:100%; border-collapse:separate; border-spacing:0; margin:0 0 20px; }
  .grid > tbody > tr > td { vertical-align:top; width:50%; }
  .grid .col-l { padding:0 8px 0 0; }
  .grid .col-r { padding:0 0 0 8px; }
  .mini { background:#ffffff; border:1px solid #E5E7EB; border-radius:10px; padding:16px 18px; }
  .mini h5 { margin:0 0 10px; font-size:11px; color:#0F172A; text-transform:uppercase; letter-spacing:0.08em; font-weight:700; }
  .mini .name { margin:0 0 10px; font-size:15px; color:#0F172A; font-weight:700; }
  .mini .name .role { margin-left:6px; color:#6B7280; font-size:12px; font-weight:500; }
  .mini .row { margin:6px 0; font-size:13px; line-height:1.45; color:#374151; }
  .mini .row .k { color:#6B7280; font-size:11px; text-transform:uppercase; letter-spacing:0.04em;
                  display:inline-block; width:60px; font-weight:600; }
  .mini a { color:#1D4ED8; text-decoration:none; font-weight:500; }
  .cta-wrap { text-align:center; margin:28px 0 20px; }
  .cta { display:inline-block; color:#ffffff !important; text-decoration:none; padding:14px 32px;
         border-radius:10px; font-weight:700; font-size:15px; letter-spacing:0.02em;
         box-shadow:0 4px 12px rgba(0,0,0,0.08); }
  .attach { margin:16px 0 0; font-size:12px; color:#6B7280; line-height:1.6; }
  .attach strong { color:#1F2937; }
  .footer { background:#F9FAFB; padding:18px 32px; text-align:center; font-size:11px; color:#9CA3AF; border-top:1px solid #E5E7EB; }
  .test-notice { background:#FFF7ED; border:1px solid #FDBA74; color:#9A3412; padding:12px 14px; margin:0 0 18px; border-radius:8px; font-size:13px; }
  @media only screen and (max-width: 600px) {
    .wrap { padding:0 !important; }
    .card { border-radius:0 !important; border:0 !important; }
    .hero { padding:22px 20px !important; }
    .hero-title { font-size:19px !important; }
    .content { padding:22px 20px !important; }
    .kv .lbl { width:110px !important; font-size:11px !important; padding:10px 12px !important; }
    .kv .val { padding:10px 12px !important; font-size:13px !important; }
    table.grid, table.grid > tbody, table.grid > tbody > tr, table.grid > tbody > tr > td { display:block !important; width:100% !important; }
    table.grid > tbody > tr > td { padding:0 !important; margin:0 0 12px 0 !important; }
    .cta { display:block !important; margin:0 12px; }
  }
"""


def _build_engineer_email_html(issue, user: dict, case_result: dict, org_ctx: dict) -> str:
    """Build the HTML body for the engineer callout email.

    Desktop-polished layout (2-column Reporter/Site cards, refined typography)
    with a mobile-first responsive fallback via @media queries for clients
    that support them (iOS Mail, Gmail app, Apple Mail).
    """
    brand_color = org_ctx["brand_color"]
    company_name = org_ctx["company_name"]
    site = org_ctx.get("site") or {}
    reporter = org_ctx.get("reporter") or {}

    job_ref = _resolve_engineer_email_job_ref(issue, case_result, org_ctx)
    case_url = (case_result or {}).get("url", "#")
    site_name = site.get("gym_name") or company_name

    sections = _build_engineer_email_sections(issue, user, reporter, site, org_ctx, job_ref, brand_color, site_name)

    hero = _engineer_email_hero_html(brand_color, company_name, site_name, sections["ref_chip"], org_ctx.get("logo_url"))
    kv_table = _engineer_email_kv_table(issue, sections)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Engineer Callout — {site_name}</title>
<style>{_ENGINEER_EMAIL_STYLE}</style></head>
<body>
<div class="wrap">
  <div class="card">
    {hero}
    <div class="content">
      {sections['test_notice']}
      <p class="lead">Dear {org_ctx['supplier_contact']},<br>A fault has been reported at <strong>{site_name}</strong> that requires engineer attendance. Full details below — you can also view the live fault card online, reply directly, and schedule a visit from the button at the bottom.</p>
      {kv_table}
      <div class="panel"><h4>Fault Description</h4><p>{issue.issue_description}</p></div>
      {sections['triage']}
      {sections['contact']}
      <div class="cta-wrap">
        <a href="{case_url}" class="cta" style="background:{brand_color};">View Fault Card &amp; Respond</a>
      </div>
      <p class="attach">Attached to this email: <strong>{sections['txt_name']}</strong> (structured ticket for your system) &middot; <strong>{sections['vcf_name']}.vcf</strong> (site contact vCard).</p>
    </div>
    <div class="footer">{sections['footer']}</div>
  </div>
</div>
</body></html>"""


def _build_engineer_email_sections(issue, user: dict, reporter: dict, site: dict,
                                   org_ctx: dict, job_ref: str, brand_color: str,
                                   site_name: str) -> dict:
    """Pre-compute the optional HTML fragments consumed by the email template."""
    bg, sev_label = _severity_badge(issue.severity)
    reporter_name = reporter.get("name") or user.get("full_name", "Reporter")
    reporter_email = reporter.get("email") or user.get("email", "")
    reporter_cell = _engineer_email_reporter_cell(reporter_name, reporter_email, brand_color)
    job_row = (f'<tr><td class="lbl">Job Ref</td><td class="val" '
               f'style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">{job_ref}</td></tr>'
               if job_ref else '')
    return {
        "test_notice": _engineer_email_test_notice(org_ctx),
        "triage": _engineer_email_triage_section(issue.ai_triage),
        "contact": _engineer_email_contact_block(reporter, user, site, brand_color),
        "footer": _engineer_email_footer_text(org_ctx["company_name"], org_ctx["platform_name"]),
        "ref_chip": f'<span class="hero-ref">{job_ref}</span>' if job_ref else '',
        "job_row": job_row,
        "sev_bg": bg, "sev_label": sev_label,
        "reporter_cell": reporter_cell,
        "vcf_name": (site_name or 'site').replace(' ', '_'),
        "txt_name": (f"Job_{job_ref}.txt" if job_ref else "Fault_Ticket.txt"),
    }


def _engineer_email_reporter_cell(name: str, email: str, brand_color: str) -> str:
    if not email:
        return name
    return (f'{name} &middot; <a href="mailto:{email}" '
            f'style="color:{brand_color};text-decoration:none;font-weight:500;">{email}</a>')


def _engineer_email_hero_html(brand: str, company: str, site_name: str, ref_chip: str,
                              logo_url: str | None = None) -> str:
    meta_sep = '  ·  ' + ref_chip if ref_chip else ''
    # Customer logo chip (white, so dark logos stay legible on the brand hero).
    logo_html = (
        f'<div style="display:inline-block;background:#FFFFFF;border-radius:6px;'
        f'padding:6px 10px;margin:0 0 12px;">'
        f'<img src="{logo_url}" alt="{company}" height="34" '
        f'style="display:block;height:34px;max-height:34px;width:auto;max-width:170px;'
        f'border:0;outline:none;text-decoration:none;"></div>'
        if logo_url else ''
    )
    return (f'<div class="hero" style="background:{brand};">'
            f'{logo_html}'
            f'<p class="hero-brand">{company}</p>'
            f'<h1 class="hero-title">Engineer Callout Required</h1>'
            f'<p class="hero-meta">{site_name}{meta_sep}</p>'
            f'</div>')


def _engineer_email_kv_table(issue, sections: dict) -> str:
    return (
        '<table class="kv" role="presentation">'
        f'<tr><td class="lbl">Equipment</td><td class="val">{issue.machine_type}</td></tr>'
        f'<tr><td class="lbl">Serial Number</td><td class="val" style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">{issue.serial_number}</td></tr>'
        f'<tr><td class="lbl">Severity</td><td class="val"><span class="chip-sev" style="background:{sections["sev_bg"]};">{sections["sev_label"]}</span></td></tr>'
        f'{sections["job_row"]}'
        f'<tr><td class="lbl">Reporter</td><td class="val">{sections["reporter_cell"]}</td></tr>'
        '</table>'
    )


def _resolve_engineer_email_job_ref(issue, case_result: dict | None, org_ctx: dict) -> str:
    """Resolve the best available job reference for the email subject + body.

    Prefers `case_result.case_id` (the freshly-created supplier case) over the
    preliminary `org_ctx['job_ref']` which can be an empty "JOB" fallback.
    """
    case_id = ((case_result or {}).get("case_id") or (case_result or {}).get("id") or "")
    if case_id:
        return f"JOB-{case_id[:8].upper()}"
    ref = (org_ctx.get("job_ref") or "").strip()
    return "" if ref in ("", "JOB") else ref


def _engineer_email_test_notice(org_ctx: dict) -> str:
    if not org_ctx.get("test_mode"):
        return ''
    target = org_ctx.get("supplier_email") or "no email"
    return f'<div class="test-notice"><strong>Test Mode:</strong> This email would be sent to <strong>{target}</strong> in production.</div>'


def _engineer_email_triage_section(ai_triage: str) -> str:
    if not ai_triage:
        return ''
    return f'<div class="panel triage"><h4>AI Triage Summary</h4><p>{ai_triage[:500]}</p></div>'


def _engineer_email_footer_text(company_name: str, platform_name: str) -> str:
    """Avoid 'Powered by X via X' when company and platform are the same."""
    if not company_name or company_name.strip().lower() == (platform_name or '').strip().lower():
        return f"Powered by {platform_name}"
    return f"Powered by {company_name} via {platform_name}"


def _engineer_email_contact_block(reporter: dict, user: dict, site: dict, brand_color: str) -> str:
    """Reporter + Site cards — 2-column table on desktop, stacks on mobile."""
    reporter_html = _render_reporter_mini_card(reporter, user)
    site_html = _render_site_mini_card(site)
    return (f'<table class="grid" role="presentation"><tbody><tr>'
            f'<td class="col-l">{reporter_html}</td>'
            f'<td class="col-r">{site_html}</td>'
            f'</tr></tbody></table>')


def _render_reporter_mini_card(reporter: dict, user: dict) -> str:
    name = reporter.get("name") or user.get("full_name") or "Reporter"
    email = reporter.get("email") or user.get("email") or ""
    phone = reporter.get("phone") or ""
    role = reporter.get("role") or ""
    role_chip = f'<span class="role">&middot; {role}</span>' if role else ""
    return (f'<div class="mini"><h5>Reporter</h5>'
            f'<p class="name">{name}{role_chip}</p>'
            f'{_contact_row("Email", email, _mailto(email))}'
            f'{_contact_row("Phone", phone, _tel(phone))}'
            f'</div>')


def _render_site_mini_card(site: dict) -> str:
    address = site.get("address") or ""
    site_phone = site.get("phone") or ""
    site_name = site.get("gym_name") or ""
    return (f'<div class="mini"><h5>Site</h5>'
            f'<p class="name">{site_name}</p>'
            f'{_contact_row("Address", address)}'
            f'{_contact_row("Phone", site_phone, _tel(site_phone))}'
            f'</div>')


def _mailto(email: str) -> str | None:
    return f"mailto:{email}" if email else None


def _tel(phone: str) -> str | None:
    return f"tel:{phone.replace(' ', '')}" if phone else None


def _contact_row(label: str, value: str, href: str | None = None) -> str:
    if not value:
        return ""
    inner = (f'<a href="{href}">{value}</a>' if href else f'<span>{value}</span>')
    return f'<div class="row"><span class="k">{label}</span>{inner}</div>'


def _resolve_email_recipient(supplier_email: str, user_email: str) -> tuple[str, bool]:
    """Pick recipient email based on test mode (returns recipient + test_mode flag)."""
    test_mode = not SENDER_EMAIL or 'resend.dev' in (SENDER_EMAIL or '')
    test_recipient = os.environ.get('TEST_RECIPIENT_EMAIL', '')
    recipient = (test_recipient or user_email) if test_mode else (supplier_email or user_email)
    return recipient, test_mode


async def _resolve_email_context(issue, user: dict) -> dict:
    """Resolve org branding and supplier details for engineer email.

    Also attaches reporter + site enrichment and the short job_ref so the
    email can mirror the new fault card design.
    """
    from routes.supplier_portal import _resolve_reporter_contact, _resolve_site_details, _short_case_ref

    org_id = user.get('organization_id')
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    branding = _resolve_org_branding(org)

    supplier_doc = await db.suppliers.find_one(
        {"name": issue.supplier, "organization_id": org_id},
        {"_id": 0, "email": 1, "contact_person": 1}
    )
    # Guarantee delivery — if the machine has no supplier (or the named one has
    # no email), fall back to the org's locked Pulse Fitness default supplier so
    # the fault always reaches Pulse (service.dept@ / MODService@).
    if not supplier_doc or not (supplier_doc.get("email") or "").strip():
        from utils.default_supplier import get_default_pulse_supplier
        default_pulse = await get_default_pulse_supplier(org_id)
        if default_pulse and (default_pulse.get("email") or "").strip():
            supplier_doc = {
                "email": default_pulse["email"],
                "contact_person": default_pulse.get("contact_person") or "Pulse Fitness Service Team",
            }
    supplier_email = (supplier_doc or {}).get('email', '')
    recipient, test_mode = _resolve_email_recipient(supplier_email, user['email'])

    issue_as_dict = _issue_to_email_dict(issue, user)
    reporter = await _resolve_reporter_contact(issue_as_dict)
    site = await _resolve_site_details(org_id)
    preliminary_ref = _short_case_ref({}, issue_as_dict)
    job_ref = "" if preliminary_ref == "JOB" else preliminary_ref

    return {
        "brand_color": branding["primary_color"],
        "company_name": branding["company_name"],
        "supplier_contact": (supplier_doc or {}).get('contact_person', 'Service Team'),
        "supplier_email": supplier_email,
        "test_mode": test_mode,
        "recipient": recipient,
        "platform_name": branding["platform_name"],
        "is_pulse": branding["is_pulse"],
        "reporter": reporter,
        "site": site,
        "job_ref": job_ref,
    }


def _resolve_org_branding(org: dict | None) -> dict:
    """Extract brand/platform fields from an org doc (or safe defaults)."""
    org = org or {}
    org_name = org.get('name', 'Pulse Fitness AI')
    branding = org.get('branding') or {}
    account_type = org.get('account_type')
    is_pulse = account_type in ("pulse_pro", "lite")
    return {
        "primary_color": org.get('brand_color') or branding.get('primary_color', '#0055FF'),
        "company_name": branding.get('company_name', org_name),
        "platform_name": "Pulse Fitness" if is_pulse else "Pulse Fitness AI",
        "is_pulse": is_pulse,
        # Customer's imported logo for the email header (org-level or branding-level).
        "logo_url": org.get('logo_url') or branding.get('logo_url') or None,
    }


def _issue_to_email_dict(issue, user: dict) -> dict:
    """Normalise an issue model/dict to the shape supplier-portal helpers expect."""
    if hasattr(issue, "model_dump"):
        issue_as_dict = issue.model_dump()
    elif hasattr(issue, "dict"):
        issue_as_dict = issue.dict()
    elif hasattr(issue, "__dict__"):
        issue_as_dict = dict(issue.__dict__)
    else:
        issue_as_dict = dict(issue) if isinstance(issue, dict) else {}
    issue_as_dict["organization_id"] = user.get("organization_id")
    issue_as_dict["user_id"] = user.get("id")
    issue_as_dict["reported_by_name"] = issue_as_dict.get("reported_by_name") or user.get("full_name", "")
    issue_as_dict["reported_by_email"] = issue_as_dict.get("reported_by_email") or user.get("email", "")
    return issue_as_dict


async def send_engineer_email(issue, issue_doc: dict, user: dict, case_result: dict) -> None:
    """Send the engineer callout email to the supplier with structured
    ticket + vCard attachments so they can import straight into their
    ticketing system / address book."""
    try:
        import resend as resend_mod
    except ImportError:
        return
    if not RESEND_API_KEY:
        return

    ctx = await _resolve_email_context(issue, user)
    html = _build_engineer_email_html(issue, user, case_result, ctx)
    # Resolve the REAL job reference (from the freshly-created case) for both
    # the subject line and the attachment filename — prevents empty "[JOB]"
    # style subjects when case_id was unavailable at ctx-build time.
    resolved_ref = _resolve_engineer_email_job_ref(issue, case_result, ctx)
    ctx["job_ref"] = resolved_ref or ctx.get("job_ref", "")
    attachments = _build_engineer_email_attachments(issue, user, ctx)

    subject_prefix = f"[{resolved_ref}] " if resolved_ref else ""
    subject = (
        f"{subject_prefix}Engineer Required — {issue.machine_type} "
        f"({issue.serial_number}) — {ctx['company_name']}"
    )
    params = {
        "from": SENDER_EMAIL,
        "to": [ctx["recipient"]],
        "subject": subject,
        "html": html,
    }
    if attachments:
        params["attachments"] = attachments
    await asyncio.to_thread(resend_mod.Emails.send, params)
    logger.info(f"Supplier notification sent to {ctx['recipient']}")


def _build_engineer_email_attachments(issue, user: dict, ctx: dict) -> list[dict]:
    """Build summary.txt + vCard attachments mirroring the supplier fault card."""
    import base64
    from routes.supplier_portal import (
        _case_summary_header, _case_summary_site, _case_summary_reporter, _case_summary_fault,
    )
    reporter = ctx.get("reporter") or {}
    site = ctx.get("site") or {}
    job_ref = ctx.get("job_ref") or ""

    # Build issue dict shape expected by the supplier-portal helpers
    issue_dict = {
        "machine_type": issue.machine_type,
        "serial_number": issue.serial_number,
        "issue_description": issue.issue_description,
        "severity": issue.severity,
        "status": "open",
        "created_at": ctx.get("created_at") or "",
    }
    fake_case = {"current_status": "pending"}
    lines = (
        _case_summary_header(fake_case, issue_dict, job_ref)
        + _case_summary_site(site)
        + _case_summary_reporter(reporter)
        + _case_summary_fault(issue_dict)
    )
    summary_text = "\n".join(lines)
    summary_b64 = base64.b64encode(summary_text.encode("utf-8")).decode("ascii")

    # vCard (minimal — reporter as FN, gym as ORG)
    vcard = _build_simple_vcard(reporter, site)
    vcard_b64 = base64.b64encode(vcard.encode("utf-8")).decode("ascii")

    attachments = [
        {"filename": f"Job_{job_ref or 'ticket'}.txt", "content": summary_b64},
    ]
    if site.get("gym_name"):
        safe_gym = site["gym_name"].replace(" ", "_")
        attachments.append({"filename": f"{safe_gym}.vcf", "content": vcard_b64})
    return attachments


def _build_simple_vcard(reporter: dict, site: dict) -> str:
    name = reporter.get("name") or site.get("gym_name") or "Site Contact"
    gym = site.get("gym_name", "")
    lines = [
        "BEGIN:VCARD", "VERSION:3.0",
        f"FN:{name}",
        f"ORG:{gym}",
    ]
    lines.extend(_vcard_optional_lines(reporter, site))
    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"


def _vcard_optional_lines(reporter: dict, site: dict) -> list[str]:
    phone = reporter.get("phone") or site.get("phone") or ""
    email = reporter.get("email") or site.get("email") or ""
    extras = []
    if reporter.get("role"):
        extras.append(f"TITLE:{reporter['role']}")
    if phone:
        extras.append(f"TEL;TYPE=WORK,VOICE:{phone}")
    if email:
        extras.append(f"EMAIL;TYPE=WORK:{email}")
    if site.get("address"):
        extras.append(f"ADR;TYPE=WORK:;;{site['address']};;;")
    if site.get("website"):
        extras.append(f"URL:{site['website']}")
    return extras


async def handle_engineer_escalation(issue, issue_doc: dict, user: dict) -> None:
    """Handle supplier case creation, email, and Sicon sync for engineer escalation."""
    if issue.resolution_type != "engineer":
        return

    # Supplier case + email
    if issue.supplier:
        try:
            from routes.supplier_portal import create_supplier_case
            org = await db.organizations.find_one({"id": user.get('organization_id')}, {"_id": 0})
            org_name = org.get('name', 'Pulse Fitness AI') if org else 'Pulse Fitness AI'
            base_url = os.environ.get('FRONTEND_URL', '') or 'https://pulsefitness.ai'

            case_result = await create_supplier_case(
                issue_id=issue_doc['id'], supplier_name=issue.supplier,
                supplier_email='', organization_name=org_name, base_url=base_url,
            )
            issue_doc['supplier_case_url'] = case_result.get('url')
            issue_doc['supplier_case_token'] = case_result.get('token')
            await db.issues.update_one(
                {"id": issue_doc['id']},
                {"$set": {"supplier_case_token": case_result.get('token'), "supplier_case_url": case_result.get('url')}}
            )
            await send_engineer_email(issue, issue_doc, user, case_result)
            try:
                from utils.sicon_sync import on_supplier_contacted
                await on_supplier_contacted(issue_doc['id'], issue.supplier)
            except Exception as e:
                logger.warning(f"Sicon supplier-contact note failed (non-blocking): {e}")
        except Exception as e:
            logger.error(f"Supplier case/email failed: {e}")

    # Sicon auto-sync
    try:
        await _sicon_auto_sync(issue_doc, user)
    except Exception as e:
        logger.error(f"Sicon auto-sync failed (non-blocking): {e}")


async def _sicon_auto_sync(issue_doc: dict, user: dict) -> None:
    """Push engineer-escalated fault to Sicon if configured."""
    from utils.sicon_sync import sync_issue_to_sicon
    sicon_id = await sync_issue_to_sicon(issue_doc["id"], user_id=user.get("id", "system"))
    if sicon_id:
        issue_doc["sicon_case_id"] = sicon_id
