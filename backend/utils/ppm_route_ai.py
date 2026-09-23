"""AI-assisted PPM route grouping.

Given a list of sites (name + free-text address), cluster them into
geographic "runs" so that sites close together are serviced together, and
order the runs (and the sites within each run) into a sensible visiting
sequence. Uses Claude (Sonnet 4.6) via the Emergent universal key; falls back
to a deterministic postcode/town grouping if the LLM is unavailable.
"""
from __future__ import annotations

import json
import logging
import os
import re
import asyncio

logger = logging.getLogger("ppm_route_ai")

_MODEL = ("anthropic", "claude-sonnet-4-6")
_LLM_TIMEOUT = 60

# UK outward postcode, e.g. "EX39", "SW1A", "M1" — the routing-relevant part.
_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*\d[A-Z]{2}\b", re.I)
_OUTWARD_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\b", re.I)


def _outward(address: str) -> str:
    a = (address or "").upper()
    m = _POSTCODE_RE.search(a)
    if m:
        return m.group(1).upper()
    # No full postcode — take the last token that looks like an outward code.
    outs = _OUTWARD_RE.findall(a)
    return (outs[-1].upper() if outs else "")


def _postcode_area(outward: str) -> str:
    """The alpha area of an outward code (EX39 -> EX, SW1A -> SW)."""
    m = re.match(r"[A-Z]+", outward or "")
    return m.group(0) if m else ""


def _fallback_groups(sites: list[dict]) -> list[dict]:
    """Group by postcode area (fallback to first word of the town/address)."""
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for s in sites:
        out = _outward(s.get("address") or "")
        area = _postcode_area(out)
        if not area:
            # crude town fallback from address text
            toks = re.findall(r"[A-Za-z]{3,}", s.get("address") or s.get("name") or "")
            area = (toks[-1][:12].title() if toks else "Unsorted")
        key = area
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(s)
    groups = []
    for key in sorted(order):
        members = sorted(buckets[key], key=lambda x: _outward(x.get("address") or ""))
        groups.append({
            "name": f"{key} area",
            "area": key,
            "site_ids": [m["id"] for m in members],
        })
    return groups


async def group_sites_by_proximity(sites: list[dict]) -> dict:
    """Return {"groups": [{name, area, site_ids:[...]}], "engine": "ai"|"fallback"}.

    `sites` = [{id, name, address}]. Site ids in the output are always a subset
    of the inputs (every input site appears exactly once)."""
    sites = [s for s in (sites or []) if s.get("id")]
    if not sites:
        return {"groups": [], "engine": "empty"}

    key = os.environ.get("EMERGENT_LLM_KEY")
    if key and len(sites) > 1:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            system = (
                "You are a UK field-service route planner for a gym equipment "
                "maintenance company. You will get a JSON list of sites, each with an "
                "id, a name and a free-text address (usually containing a UK town and/or "
                "postcode). Cluster the sites into geographic RUNS so an engineer can "
                "service nearby sites on the same trip — group by postcode area/district "
                "and town proximity. Then order the runs sensibly (roughly geographic), "
                "and order sites within each run so the driving is efficient. "
                "Give each run a short human name based on the area (e.g. 'Devon — "
                "Barnstaple & Bideford (EX31/EX39)'). EVERY input site id must appear in "
                "exactly ONE run. Never invent ids. Respond with STRICT JSON only: "
                '{"groups":[{"name":"","area":"","site_ids":["id1","id2"]}]}'
            )
            payload = [{"id": s["id"], "name": s.get("name") or "", "address": s.get("address") or ""}
                       for s in sites]
            chat = LlmChat(api_key=key, session_id="ppm-route-group",
                           system_message=system).with_model(*_MODEL)
            prompt = "Group these sites into runs:\n" + json.dumps(payload)[:14000]
            raw = (await asyncio.wait_for(
                chat.send_message(UserMessage(text=prompt)), timeout=_LLM_TIMEOUT)).strip()
            m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
            if m:
                raw = m.group(1).strip()
            i, j = raw.find("{"), raw.rfind("}")
            data = json.loads(raw[i:j + 1]) if i != -1 else {}
            valid_ids = {s["id"] for s in sites}
            seen: set = set()
            groups = []
            for g in data.get("groups", []):
                ids = [x for x in (g.get("site_ids") or []) if x in valid_ids and x not in seen]
                for x in ids:
                    seen.add(x)
                if ids:
                    groups.append({"name": (g.get("name") or "Run").strip(),
                                   "area": (g.get("area") or "").strip(), "site_ids": ids})
            # append any sites the model dropped
            missing = [s for s in sites if s["id"] not in seen]
            if missing:
                for grp in _fallback_groups(missing):
                    groups.append(grp)
            if groups:
                return {"groups": groups, "engine": "ai"}
        except Exception as exc:
            logger.warning("[ppm-route-ai] LLM grouping failed, using fallback: %s", exc)

    return {"groups": _fallback_groups(sites), "engine": "fallback"}
