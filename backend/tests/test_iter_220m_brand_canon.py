"""
test_iter_220m_brand_canon — pin the canonical GymAxis brand palette
into the regression suite so it cannot silently drift.

History: the Partner Engineer Instagram launch shipped twice with the
**wrong** palette (legacy `#0055FF` / `#19CDFF` / `#0A0C10` from the
Pulse Fitness portal) because the design docs in /app/marketing/ and
/app/memory/ baked the wrong hex codes into prose, and every fresh
agent who read them re-locked the mistake in.

Fix: a dedicated canonical doc at /app/BRAND_PALETTE.md is now the
single source of truth, every other doc defers to it, and the
marketing generator imports the canon directly. This test file:

  1. Asserts the canonical hex codes are present in BRAND_PALETTE.md.
  2. Asserts the marketing generator (`partner_engineer_launch/generate.py`)
     uses those hex codes and does NOT use the legacy/Pulse hex codes
     in any token assignment.
  3. Asserts the design system + partner-engineer README defer to the
     canon (so future grep-led agents land on the right doc).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/app")
BRAND_PALETTE_MD = ROOT / "BRAND_PALETTE.md"
PULSE_BRAND_PALETTE_MD = ROOT / "PULSE_BRAND_PALETTE.md"
DESIGN_SYSTEM_MD = ROOT / "DESIGN_SYSTEM.md"
PARTNER_README = ROOT / "marketing" / "partner_engineer_launch" / "README.md"
GENERATOR_PY = ROOT / "marketing" / "partner_engineer_launch" / "generate.py"
BRAND_PREVIEW_SCRIPT = ROOT / "scripts" / "build_brand_preview.py"
BRAND_PREVIEW_HTML = ROOT / "BRAND_PALETTE_PREVIEW.html"

CANONICAL_HEXES = {
    "#F8FAFC",  # gx-bg
    "#2563EB",  # gx-brand-from (navy)
    "#5B5BF5",  # gx-brand-mid (indigo)
    "#9D4CDD",  # gx-brand-to (purple)
    "#0F172A",  # gx-text (slate-900)
}

# Pulse Fitness canonical hexes (sourced from PulseDesignTab.js)
PULSE_CANONICAL_HEXES = {
    "#19CDFF",  # color-brand-cyan (primary CTA)
    "#0BB0DD",  # color-brand-cyan-deep
    "#212721",  # color-pulse-black
    "#F8F9FA",  # pulse-bg
    "#0B1220",  # pulse ink heading
}

LEGACY_PULSE_HEXES = {
    "#0055FF",  # legacy GymAxis electric blue
    "#19CDFF",  # Pulse Fitness cyan
    "#0A0C10",  # Pulse Fitness dark canvas
}


def test_brand_palette_md_exists_and_contains_every_canonical_hex():
    assert BRAND_PALETTE_MD.exists(), "/app/BRAND_PALETTE.md missing — it is the canonical source of truth"
    text = BRAND_PALETTE_MD.read_text()
    missing = sorted(h for h in CANONICAL_HEXES if h not in text)
    assert not missing, f"BRAND_PALETTE.md is missing canonical hex(es): {missing}"


def test_brand_palette_md_explicitly_lists_legacy_hexes_in_do_not_use_section():
    text = BRAND_PALETTE_MD.read_text()
    # The §2 "DO NOT USE" table must enumerate every legacy hex by name
    # so a future agent searching for one of them lands on the warning.
    for legacy in LEGACY_PULSE_HEXES:
        assert legacy in text, (
            f"BRAND_PALETTE.md must explicitly call out the legacy hex "
            f"`{legacy}` in its DO NOT USE table — agents grep for these."
        )
    assert "DO NOT USE" in text, "BRAND_PALETTE.md must contain the literal `DO NOT USE` header"


def _color_assignments(source: str) -> list[str]:
    """Return every right-hand-side hex literal assigned to a variable
    or used inside a CSS/HTML colour declaration. Comment lines are
    stripped first so doc/anti-pattern callouts inside the file are
    not flagged as colour usage."""
    cleaned: list[str] = []
    for line in source.splitlines():
        stripped = line.strip()
        # Drop Python comment-only lines + Markdown blockquote lines.
        if stripped.startswith("#") and "=" not in stripped:
            continue
        cleaned.append(line)
    body = "\n".join(cleaned)
    return re.findall(r"#[0-9A-Fa-f]{6}\b", body)


def test_generator_uses_canonical_hexes_and_no_legacy_hexes():
    source = GENERATOR_PY.read_text()
    used = set(h.upper() for h in _color_assignments(source))
    # Every canonical hex used by the live `.theme-gymaxis` block must
    # appear in the generator.
    missing = sorted(h for h in CANONICAL_HEXES if h not in used)
    assert not missing, (
        f"generate.py must use the canonical hex(es) {missing} from "
        "/app/BRAND_PALETTE.md so tiles match the live site."
    )
    # And no legacy / Pulse-only hex may be referenced as a colour
    # in the generator (a textual mention inside a comment is fine —
    # the helper above strips comments).
    leaked = sorted(h for h in LEGACY_PULSE_HEXES if h in used)
    assert not leaked, (
        f"generate.py is referencing legacy/Pulse hex(es) {leaked} as a "
        "colour value. These are NEVER GymAxis colours — use the "
        "navy→purple gradient (#2563EB → #9D4CDD). See BRAND_PALETTE.md."
    )


def test_partner_engineer_readme_defers_to_brand_palette_md():
    text = PARTNER_README.read_text()
    assert "BRAND_PALETTE.md" in text, (
        "partner_engineer_launch/README.md must link to /app/BRAND_PALETTE.md "
        "so a fresh agent crawling marketing/ lands on the canon."
    )
    # And it must NOT recommend the legacy tokens — those references are
    # only allowed inside an explicit DO NOT USE / warning block.
    # Quick proxy: the literal "DO NOT" warning must appear above any
    # legacy hex mention.
    if any(h in text for h in LEGACY_PULSE_HEXES):
        # Anywhere a legacy hex appears, there must be a "DO NOT"
        # warning earlier in the file.
        first_legacy_pos = min(
            text.find(h) for h in LEGACY_PULSE_HEXES if h in text
        )
        warning_pos = text.find("DO NOT")
        assert warning_pos != -1 and warning_pos < first_legacy_pos, (
            "partner_engineer_launch/README.md must place a `DO NOT` warning "
            "before any legacy hex mention."
        )


def test_design_system_md_defers_to_brand_palette_md():
    text = DESIGN_SYSTEM_MD.read_text()
    assert "BRAND_PALETTE.md" in text, (
        "DESIGN_SYSTEM.md must link to /app/BRAND_PALETTE.md — that is the "
        "canonical source of truth for hex codes."
    )


def test_pulse_brand_palette_md_exists_and_contains_canonical_hexes():
    assert PULSE_BRAND_PALETTE_MD.exists(), "/app/PULSE_BRAND_PALETTE.md missing — it is the canonical source of truth for Pulse Fitness"
    text = PULSE_BRAND_PALETTE_MD.read_text()
    missing = sorted(h for h in PULSE_CANONICAL_HEXES if h not in text)
    assert not missing, f"PULSE_BRAND_PALETTE.md is missing canonical hex(es): {missing}"


def test_pulse_palette_cross_links_to_gymaxis_canon():
    text = PULSE_BRAND_PALETTE_MD.read_text()
    assert "BRAND_PALETTE.md" in text, (
        "PULSE_BRAND_PALETTE.md must link back to /app/BRAND_PALETTE.md so a "
        "fresh agent crawling either doc lands on the full two-brand picture."
    )


def test_gymaxis_palette_cross_links_to_pulse_canon():
    text = BRAND_PALETTE_MD.read_text()
    assert "PULSE_BRAND_PALETTE.md" in text, (
        "BRAND_PALETTE.md must link to /app/PULSE_BRAND_PALETTE.md so the "
        "two-brand split is discoverable from either side."
    )


def test_brand_preview_script_pins_all_canonical_hexes():
    """The preview script keeps an in-file mirror of each canon for
    deterministic rendering — pin both GymAxis + Pulse hexes are present
    so any future drift in the script is caught immediately."""
    text = BRAND_PREVIEW_SCRIPT.read_text()
    for hx in CANONICAL_HEXES | PULSE_CANONICAL_HEXES:
        assert hx in text, (
            f"build_brand_preview.py must pin the canonical hex `{hx}` so the "
            "rendered preview matches the canon docs verbatim."
        )


def test_brand_preview_html_is_generated_and_contains_both_brands():
    assert BRAND_PREVIEW_HTML.exists(), (
        "/app/BRAND_PALETTE_PREVIEW.html missing — run `make brand-preview` "
        "to generate it from the canon docs."
    )
    html = BRAND_PREVIEW_HTML.read_text()
    # Both brand sections must be present in the live preview.
    assert "GymAxis tokens" in html, "preview HTML missing the GymAxis section"
    assert "Pulse Fitness tokens" in html, "preview HTML missing the Pulse Fitness section"
    assert "DO NOT USE" in html, "preview HTML must include the DO NOT USE guard table"
    # Every canonical hex from BOTH brands must render in the swatch grid.
    for hx in CANONICAL_HEXES | PULSE_CANONICAL_HEXES:
        assert hx in html, f"preview HTML missing canonical hex `{hx}` — re-run `make brand-preview`"
