"""MOD ".ai" sanitiser for outbound email (mirror of frontend/modservice/sanitize.js).

MOD networks and mail filters block ".ai" references, so any email sent for
a MOD organisation is passed through ``sanitize_ai`` before it leaves:

  x@pulsefitness.ai / x@service.pulsefitness.ai → x@pulsefitness.com
  https://www.pulsefitness.ai/...                → https://modservice.pulsefitness.com/...
  "Pulse Fitness AI"                             → "Pulse Fitness"
"""
from __future__ import annotations

import os
import re

_BRANDS = r"(?:pulsefitness|gymaxis)"
_TAIL = r"(?![A-Za-z0-9-])"
_EMAIL_RE = re.compile(rf"([A-Za-z0-9._%+-]+)@(?:[A-Za-z0-9-]+\.)*{_BRANDS}\.ai{_TAIL}", re.I)
_HOST_RE = re.compile(rf"(?:[A-Za-z0-9-]+\.)*{_BRANDS}\.ai{_TAIL}", re.I)
_BRAND_PHRASE_RE = re.compile(r"\b(Pulse ?Fitness|GymAxis) AI\b")
_DETECT_RE = re.compile(rf"{_BRANDS}\.ai{_TAIL}", re.I)


def _mod_host() -> str:
    url = (os.environ.get("MOD_PORTAL_URL") or "https://modservice.pulsefitness.com").strip()
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    return host if host and not _DETECT_RE.search(host) else "modservice.pulsefitness.com"


def sanitize_ai(text: str | None) -> str | None:
    if not text:
        return text
    out = _EMAIL_RE.sub(lambda m: f"{m.group(1)}@pulsefitness.com", text)
    out = _HOST_RE.sub(_mod_host(), out)
    out = _BRAND_PHRASE_RE.sub(lambda m: m.group(1), out)
    return out


def contains_ai(text: str | None) -> bool:
    return bool(text and _DETECT_RE.search(text))
