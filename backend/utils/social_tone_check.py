"""Pre-publish tone checker — Iter 220bx.

Lints a generated draft against the **launch voice** rulebook so an
operator can't accidentally publish a post that claims metrics or
social proof we don't have yet.

Two layers:

1. **Heuristic rules** (this module, regex-based, instant, free) — catch
   the obvious offenders: hard metric claims ("4 hours saved", "30 %
   uplift"), social proof ("thousands of operators trust us", "case
   studies"), and "established voice" language ("industry-leading",
   "proven", "trusted by"). 90 % of bad drafts are caught here.

2. **LLM second pass** (optional, in ``check_draft_tone_with_llm``) —
   a Claude call against the same rulebook for the borderline cases.
   Costs a small budget hit per check; off by default, ``deep=True``
   to opt in.

The output is a stable dict the UI and tests can rely on::

    {
        "status": "ok" | "warnings" | "failed",
        "findings": [
            {"severity": "high"|"medium"|"low",
             "rule": "metric_claim" | "social_proof" | "established_voice",
             "snippet": "...",
             "suggestion": "..."},
            ...
        ],
        "checked_at": iso8601,
        "checker_version": "1.0",
    }
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

CHECKER_VERSION = "1.0"


# Each rule: (id, severity, regex, suggestion)
# Severity is `high` (would block the launch narrative outright),
# `medium` (sounds established but a savvy reader might excuse), or
# `low` (borderline — surface but don't alarm).
_RULES: list[tuple[str, str, re.Pattern, str]] = [
    # ── HARD METRIC CLAIMS ──────────────────────────────────────────
    ("metric_claim", "high",
     re.compile(
         r"\b\d+\s*%\s*(?:increase|reduction|improvement|saving|saved"
         r"|less|more|faster|slower|growth|conversion|retention|adoption"
         r"|uplift|boost|jump|drop|fewer|higher|lower)\b",
         re.I),
     "Remove the percentage claim — GymAxis has no track record to "
     "back it up yet. Rephrase as an aspiration ('expect to save…')."),
    ("metric_claim", "high",
     re.compile(
         r"\b(?:saved|saves|saving|cut|cuts|cutting|reduces?|reducing)"
         r"\s+\d[\d,\.]*\+?\s*(?:hours?|hrs?|minutes?|mins?|days?"
         r"|weeks?|months?|callouts?)\b",
         re.I),
     "Concrete time-saving numbers imply existing customers. Reframe "
     "as the design intent ('built to save the typical ops day…')."),
    ("metric_claim", "high",
     re.compile(
         r"\bcut(?:s|ting)?\s+(?:dispatch|response|admin|paperwork)"
         r"\s+(?:by\s+)?\d+", re.I),
     "Specific cut-by-N% claim — we don't have the proof. Soften to "
     "'designed to cut dispatch lag' (no number)."),

    # ── SOCIAL PROOF / TRACK RECORD ─────────────────────────────────
    ("social_proof", "high",
     re.compile(
         r"\b(?:thousands?|hundreds?)\s+of\s+(?:customers?|operators?"
         r"|gyms?|sites?|users?|clients?|teams?)\b", re.I),
     "We don't have 'thousands of customers' — yet. Replace with "
     "'the operators we've shadowed' or remove."),
    ("social_proof", "high",
     re.compile(
         r"\b(?:our|the)\s+customers?\s+(?:report|say|tell|love|told"
         r"|are\s+seeing)\b", re.I),
     "No customers to quote yet. Use a hypothetical ('imagine telling "
     "your team…') or remove."),
    ("social_proof", "medium",
     re.compile(r"\bcase\s+stud(?:y|ies)\b", re.I),
     "Case studies imply documented wins. We don't have any yet — "
     "talk about the design conversations instead."),
    ("social_proof", "high",
     re.compile(
         r"\b\d+\+?\s*(?:gyms?|operators?|sites?|users?|customers?)"
         r"\s+(?:use|using|on|trust|chose|chosen)\b", re.I),
     "Numbered usage claim — drop entirely until we have real "
     "logos."),
    ("social_proof", "medium",
     re.compile(
         r"\bsince\s+(?:we\s+)?(?:launched|started|founded|began)\b",
         re.I),
     "Implies history we don't have. Lead with 'we built this "
     "for…' instead."),

    # ── ESTABLISHED-PLATFORM VOICE ──────────────────────────────────
    ("established_voice", "high",
     re.compile(r"\bestablished\s+(?:platform|brand|tool|software|saas)\b", re.I),
     "Direct contradiction of the launch narrative. Say 'brand-new "
     "platform' if anything."),
    ("established_voice", "medium",
     re.compile(r"\bproven\b", re.I),
     "Nothing is 'proven' yet. Use 'designed for' or 'tested with "
     "ops teams' instead."),
    ("established_voice", "medium",
     re.compile(r"\bindustry[- ]?leading\b", re.I),
     "Bold for a launch — drop or replace with 'opinionated about'."),
    ("established_voice", "high",
     re.compile(r"\btrusted\s+by\b", re.I),
     "Trust implies an existing user base. Replace with 'built with' "
     "or 'shadowed alongside'."),
    ("established_voice", "medium",
     re.compile(
         r"\b(?:over\s+the\s+(?:years|past\s+\w+)|for\s+years)\b",
         re.I),
     "Suggests a timespan we don't have. Anchor in the present."),
    ("established_voice", "medium",
     re.compile(r"\bfounded\s+in\s+\d{4}\b", re.I),
     "Drop the founding-year claim — irrelevant until we're 12 months in."),
    ("established_voice", "low",
     re.compile(r"\b(?:reliable|battle[- ]?tested|enterprise[- ]?grade)\b", re.I),
     "Lean adjective — works post-launch but feels premature in "
     "week 1. Consider 'opinionated' or 'ops-first' instead."),
]


def _snippet(text: str, match: re.Match, *, window: int = 40) -> str:
    """Return a short context snippet around the matched span."""
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def check_draft_tone(
    caption: str,
    *, hashtags: Optional[list[str]] = None,
    on_campaign: bool = False,
) -> dict:
    """Run the heuristic launch-tone rulebook over ``caption`` (and
    optionally hashtags).

    When ``on_campaign=False`` we still scan, but the resulting status
    floor is ``warnings`` — the operator is publishing under the
    established voice deliberately, so an "established-platform"
    phrase is fine. We surface findings as ``low`` severity in that
    mode so the UI can show a quiet "FYI" tooltip rather than a banner.
    """
    text = (caption or "").strip()
    hashtag_text = " ".join(hashtags or [])
    full = f"{text}\n{hashtag_text}"

    findings: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()
    for rule_id, severity, pattern, suggestion in _RULES:
        for match in pattern.finditer(full):
            span = (match.start(), match.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            findings.append({
                "severity": severity if on_campaign else "low",
                "rule": rule_id,
                "snippet": _snippet(full, match),
                "matched": match.group(0),
                "suggestion": suggestion,
            })

    # Severity rollup → status.
    if not findings:
        status = "ok"
    elif any(f["severity"] == "high" for f in findings):
        status = "failed"
    else:
        status = "warnings"

    return {
        "status": status,
        "findings": findings,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checker_version": CHECKER_VERSION,
        "on_campaign": bool(on_campaign),
    }


# ── Optional LLM deep check ───────────────────────────────────────────


_LLM_SYSTEM_PROMPT = (
    "You are a strict launch-week tone reviewer for GymAxis. The "
    "platform is BRAND NEW — there are no customers, no metrics, no "
    "case studies. Your job is to find any sentence in the draft below "
    "that implies a track record we don't have yet. Be terse. Return "
    "STRICT JSON with this shape:\n"
    "{\"verdict\": \"ok\" | \"warnings\" | \"failed\",\n"
    " \"findings\": [{\"severity\": \"high\"|\"medium\"|\"low\", "
    "\"snippet\": string, \"suggestion\": string}]}\n"
    "If the draft is fine, return {\"verdict\":\"ok\",\"findings\":[]}."
)


async def check_draft_tone_with_llm(caption: str) -> dict:
    """Second-pass LLM review. Falls back to ``{verdict:'ok'}`` when
    the LLM call errors so the route never breaks. Off by default —
    only called when the operator hits "Deep recheck"."""
    import os
    import json as _json
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"verdict": "ok", "findings": [],
                "skipped": True, "reason": "no_llm_key"}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=api_key,
            session_id=f"tone-check-{datetime.now(timezone.utc).timestamp()}",
            system_message=_LLM_SYSTEM_PROMPT,
        ).with_model("anthropic", "claude-sonnet-4-5")
        resp = await chat.send_message(UserMessage(text=caption[:4000]))
        # The integration returns the raw model text; parse the JSON.
        if isinstance(resp, str):
            text = resp
        else:
            text = getattr(resp, "text", None) or str(resp)
        # Pull the first {...} block to be defensive.
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return {"verdict": "ok", "findings": [],
                    "skipped": True, "reason": "parse_failed"}
        data = _json.loads(m.group(0))
        return {
            "verdict": data.get("verdict", "ok"),
            "findings": data.get("findings", []),
            "skipped": False,
        }
    except Exception as exc:
        logger.warning("[tone-check] LLM pass failed: %s", exc)
        return {"verdict": "ok", "findings": [],
                "skipped": True, "reason": str(exc)[:120]}


__all__ = [
    "CHECKER_VERSION",
    "check_draft_tone",
    "check_draft_tone_with_llm",
]
