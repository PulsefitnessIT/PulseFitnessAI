# Email HTML palette regression: banned legacy colours must not appear in rendered email bodies.
from tests._paths import REPO  # noqa: E402
import asyncio
import glob
import os
import re
import sys

import pytest
import requests

sys.path.insert(0, REPO + "/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in open(REPO + "/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

BANNED = ["#0055FF", "#0F172A", "#64748B", "#E5E7EB", "#6B7280", "#2563EB", "#7C3AED", "#6366F1"]
GUIDE = ["#19CDFF", "#0091CA", "#0073A4", "#1B1C1D", "#26292B", "#393E41", "#565B5E", "#6E7476",
         "#9A9FA1", "#E0E0E0", "#F0F0F0", "#F7F7F7", "#FFFFFF", "#000000", "#00121A", "#E4F9FF"]
STATUS_OK = re.compile(r"#(f59e0b|dc2626|ef4444|10b981|b91c1c|991b1b|fef3c7|fee2e2|fef2f2|b45309|78350f|22c55e|"
                       r"fef9c3|d97706|047857|fff7ed|fde68a|fde047|ea580c|92400e|854d0e|16a34a|059669|fffbeb|fff3cd|ffc107|"
                       r"ecfdf5|d1fae5|065f46|166534|dcfce7|f0fdf4|15803d|fecaca|fca5a5|7f1d1d|f87171|fbbf24|34d399|bbf7d0)", re.I)


def _no_banned(html: str):
    up = html.upper()
    return [c for c in BANNED if c in up]


def _off_palette(html: str):
    found = set(h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}\b", html))
    return sorted(c for c in found if c not in GUIDE and not STATUS_OK.fullmatch(c))


# Health
def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=20)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# vehicle_checks reminder email
def test_reminder_html_palette():
    from routes.vehicle_checks import _reminder_html
    html = _reminder_html("TEST_Lee", "2026-W02", [
        {"reg_no": "AB12 CDE", "make_model": "Ford Transit", "link": "https://example.com/x"},
        {"reg_no": "XY34 ZZZ", "make_model": None, "link": "https://example.com/y"},
    ])
    assert "AB12 CDE" in html
    assert _no_banned(html) == []
    assert "#19CDFF" in html.upper()
    print("reminder off-palette:", _off_palette(html))


# wrap_branded shell (header/footer)
def test_wrap_branded_palette():
    from utils.email import wrap_branded
    html = asyncio.get_event_loop().run_until_complete(wrap_branded("<p>TEST_body</p>", None)) \
        if False else asyncio.run(wrap_branded("<p>TEST_body</p>", None))
    assert "TEST_body" in html
    assert _no_banned(html) == []
    up = html.upper()
    assert "#000000" in up or "#1B1C1D" in up
    print("wrap off-palette:", _off_palette(html))


# reminder wrapped in branded shell
def test_wrapped_reminder_palette():
    from routes.vehicle_checks import _reminder_html
    from utils.email import wrap_branded
    html = asyncio.run(wrap_branded(_reminder_html("TEST", "W1", [{"reg_no": "R1", "make_model": "M", "link": "https://e.x"}]), None))
    assert _no_banned(html) == []


# Static scan: no banned colours in any html-ish string in backend python (excluding reportlab PDFs)
def test_static_scan_email_strings():
    hits = []
    pat = re.compile(r"#(0055FF|0F172A|64748B|E5E7EB|6B7280|2563EB|7C3AED|6366F1)\b", re.I)
    for f in glob.glob(REPO + "/backend/**/*.py", recursive=True):
        if "/tests/" in f or "/scripts/" in f:
            continue
        for i, line in enumerate(open(f, errors="ignore"), 1):
            if pat.search(line) and ("style" in line or "<" in line) and "HexColor" not in line and "<font" not in line:
                hits.append(f"{f}:{i}")
    assert hits == [], hits


# Core Blue link text on white should be #0091CA, not #19CDFF (styled <a> with color:#19CDFF and no background)
def test_no_core_blue_link_text():
    hits = []
    pat = re.compile(r"<a[^>]*style=\"(?![^\"]*background)[^\"]*(?<![-\w])color:\s*#19CDFF", re.I)
    for f in glob.glob(REPO + "/backend/**/*.py", recursive=True):
        if "/tests/" in f or f.endswith("routes/contact.py"):  # contact.py rows render inside a #1B1C1D email (dark)
            continue
        src = open(f, errors="ignore").read()
        for m in pat.finditer(src):
            # skip when the nearest enclosing table/div background before the link is dark
            ctx = src[max(0, m.start() - 1200):m.start()]
            bgs = re.findall(r"(?:div|table)[^>]*background:\s*(#[0-9A-Fa-f]{3,6})", ctx)
            if bgs and bgs[-1].upper() in ("#1B1C1D", "#000000", "#000", "#26292B", "#393E41"):
                continue
            hits.append(f"{f}:{src[:m.start()].count(chr(10)) + 1}")
    print("core-blue link text hits:", hits)
    assert hits == [], hits
