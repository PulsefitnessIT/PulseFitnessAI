"""
GymAxis — "9 Reasons Gym Operators Are Switching" Instagram campaign generator.

Generates 9 cohesive square (1:1) minimal-flat-illustration posts using
Gemini Nano Banana via the Emergent universal key. The GymAxis full logo is
passed as a reference image on every call to lock brand fidelity.
"""
import asyncio
import base64
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent  # noqa: E402

OUT = Path("/app/marketing/instagram_campaign")
LOGO = OUT / "gymaxis_logo.png"
MODEL = "gemini-3.1-flash-image-preview"

# --- shared visual DNA ---------------------------------------------------
BRAND_DNA = (
    "Cohesive Instagram-feed series in minimal flat-illustration style. "
    "Square 1:1 composition. Soft off-white background (#F8FAFC) with a subtle "
    "diagonal blue-to-deep-purple gradient block in one corner echoing the "
    "GymAxis logo gradient (electric blue #2563EB transitioning to deep "
    "indigo #1E3A8A, with electric cyan #19CDFF micro-accents). "
    "Typography: bold geometric sans-serif (Proxima Nova / Maax Rounded feel), "
    "tight tracking, all-caps for headlines. "
    "Generous whitespace, asymmetric editorial layout. NO photographs, NO 3D "
    "renders, NO emoji, NO clip-art. Crisp vector flat shapes only. "
    "Place a small 'GYMAXIS' wordmark with the gradient GA mark in the top-"
    "left corner (matching the supplied logo). Place a circular number badge "
    "in the bottom-right corner with the post number on a deep-indigo disc."
)

POSTS = [
    {
        "n": "01",
        "slug": "01_cover",
        "hook": "9 REASONS GYM OPERATORS ARE SWITCHING TO GYMAXIS",
        "scene": (
            "Hero cover slide. Centered: the words '9 REASONS' in massive "
            "tight-tracked gradient type (blue-to-purple), with 'GYM OPERATORS "
            "ARE SWITCHING TO GYMAXIS' beneath in slimmer black uppercase. "
            "Beneath the headline a single thin horizontal line and the "
            "subtitle 'A SHORT THREAD — SAVE FOR LATER' in 60% gray. "
            "Decorative element: a stylised flat barbell silhouette tilted at "
            "15° in the lower-left, rendered in the brand gradient. "
            "Bottom-right number badge: '01 / 09'."
        ),
    },
    {
        "n": "02",
        "slug": "02_multi_fault",
        "hook": "ONE JOB. EVERY BROKEN MACHINE. ONE TAP.",
        "scene": (
            "Flat illustration of three abstract gym machines (treadmill, "
            "rower, cable cross — geometric simplified silhouettes) connected "
            "by a single glowing cyan thread to one rounded card labelled "
            "'JOB #4958' on the right. Above the machines, three tiny red "
            "warning triangles. Below the card: a green checkmark and the "
            "text 'INDIVIDUAL SLA — SHARED CONTEXT'. Headline (top-left, "
            "uppercase): 'BATCH FAULT LOGGING.' Sub-line: 'Stop chasing five "
            "broken machines across three email threads.' Bottom-right "
            "number badge: '02 / 09'."
        ),
    },
    {
        "n": "03",
        "slug": "03_sla_clock",
        "hook": "EVERY FAULT HAS A NAMED OWNER AND A LIVE SLA CLOCK.",
        "scene": (
            "Flat illustration: a large circular SLA timer ring, three-"
            "quarters filled with the brand gradient and a remaining slice "
            "in pale gray. Inside the ring the time '02:47' in bold "
            "monospace black. To the right of the ring, a small avatar "
            "circle with the initials 'JM' in cyan, and the line "
            "'Owner: James M. · Sicon job linked'. Headline (top-left): "
            "'NO MORE BLACK HOLES.' Sub-line: 'Accountability, baked in.' "
            "Bottom-right number badge: '03 / 09'."
        ),
    },
    {
        "n": "04",
        "slug": "04_check_sheets",
        "hook": "YOUR CHECK SHEETS JUST WENT PAPERLESS.",
        "scene": (
            "Split composition. Left half: a faded gray paper clipboard "
            "with handwritten ticks, slightly crumpled, slashed with a "
            "subtle red diagonal line. Right half: a clean rounded-corner "
            "phone outline showing five green circular tick rows with cyan "
            "checkmarks and the heading 'DAILY · COMPLETE'. Between the two "
            "halves a thick gradient arrow pointing right. Headline (top): "
            "'PAPER → PIXELS.' Sub-line: 'Preventive maintenance your "
            "engineers actually finish.' Bottom-right number badge: '04 / 09'."
        ),
    },
    {
        "n": "05",
        "slug": "05_spec_autopull",
        "hook": "SPEC SHEETS AUTO-PULLED FROM THE MANUFACTURER.",
        "scene": (
            "Flat illustration: a stylised globe of internet domains on the "
            "left (cyan dotted lines connecting flat domain rectangles "
            "labelled 'pulsefitness.com', 'lifefitness.com', 'technogym.com'). "
            "A bold gradient arrow flows right into a clean equipment card "
            "on the right showing a tiny treadmill silhouette, a serial "
            "number stub, and a 'SPEC SHEET ATTACHED' green pill. Headline "
            "(top-left): 'ZERO DATA ENTRY.' Sub-line: 'Catalogue ingest "
            "in seconds, not weeks.' Bottom-right number badge: '05 / 09'."
        ),
    },
    {
        "n": "06",
        "slug": "06_one_ledger",
        "hook": "MEMBERSHIPS, BILLING & ERP — ONE SOURCE OF TRUTH.",
        "scene": (
            "Three flat rounded cards stacked diagonally from upper-left to "
            "lower-right: card 1 'MEMBERSHIPS' (cyan tint, with a tiny "
            "person-icon row), card 2 'BILLING' (gradient tint, with a "
            "currency '£' glyph), card 3 'SICON / SAGE 200' (deep-indigo, "
            "with a tiny ledger icon). A single thin gradient thread "
            "stitches all three together. Headline (top): 'ONE LEDGER. ZERO "
            "DOUBLE-ENTRY.' Sub-line: 'Native ERP — not a CSV export.' "
            "Bottom-right number badge: '06 / 09'."
        ),
    },
    {
        "n": "07",
        "slug": "07_classes",
        "hook": "CLASSES FILL THEMSELVES. WAITLISTS TOO.",
        "scene": (
            "Flat illustration of a weekly calendar grid, 5 columns × 4 rows. "
            "Cells are filled progressively with gradient blocks (most are "
            "fully filled in the brand gradient; two cells show a small "
            "cyan '+3' waitlist badge). On the left side of the grid, a "
            "cluster of three small abstract member avatars. Headline "
            "(top-left): 'GROUP FITNESS, ON AUTOPILOT.' Sub-line: 'Smart "
            "scheduling, smart waitlists, smart no-show recovery.' "
            "Bottom-right number badge: '07 / 09'."
        ),
    },
    {
        "n": "08",
        "slug": "08_multi_site",
        "hook": "EVERY SITE ON ONE DASHBOARD.",
        "scene": (
            "A simplified flat map silhouette of the United Kingdom in pale "
            "gray, with five glowing cyan location pins at distinct cities. "
            "Each pin connects upward via thin gradient lines to a single "
            "floating dashboard card at the top showing a tiny KPI grid "
            "(four stat tiles: 'UPTIME 99.2%', 'OPEN FAULTS 4', 'NPS 71', "
            "'£42K MRR'). Headline (left): 'MULTI-SITE, ONE PANE.' Sub-line: "
            "'See your whole estate without opening five tabs.' Bottom-"
            "right number badge: '08 / 09'."
        ),
    },
    {
        "n": "09",
        "slug": "09_cta",
        "hook": "MIGRATE IN A WEEKEND. START FREE.",
        "scene": (
            "Bold final CTA slide. Centered: a thick rounded-rectangle button "
            "filled with the brand gradient containing the white uppercase "
            "label 'START A FREE TRIAL'. Below the button in slimmer black "
            "text: 'gymaxis.ai · Link in bio'. Above the button: the words "
            "'BUILT BY OPERATORS, FOR OPERATORS.' in deep-indigo uppercase. "
            "Decorative: two thin gradient arcs sweeping from the top-left "
            "and bottom-right corners towards the button, suggesting "
            "convergence. Bottom-right number badge: '09 / 09'."
        ),
    },
]


def encode_logo() -> str:
    return base64.b64encode(LOGO.read_bytes()).decode("utf-8")


async def generate_one(post: dict, logo_b64: str) -> tuple[str, bool, str]:
    slug = post["slug"]
    out_path = OUT / f"{slug}.png"
    if out_path.exists() and out_path.stat().st_size > 50_000:
        return slug, True, f"skipped (already exists, {out_path.stat().st_size // 1024} KB)"
    prompt = (
        f"{BRAND_DNA}\n\n"
        f"This is post {post['n']} of 9 in the series.\n"
        f"HEADLINE TEXT TO RENDER ON THE IMAGE: \"{post['hook']}\"\n"
        f"SCENE BRIEF: {post['scene']}\n\n"
        "CRITICAL: Render the headline text crisply and legibly inside the "
        "image. The 'GYMAXIS' wordmark and gradient GA mark must visually "
        "match the supplied reference logo (kept in the top-left corner, "
        "small but readable). Do not invent alternate logos."
    )
    try:
        chat = LlmChat(
            api_key=os.getenv("EMERGENT_LLM_KEY"),
            session_id=f"gymaxis-ig-{slug}-{int(time.time())}",
            system_message="You are a senior brand designer producing a cohesive Instagram campaign for the SaaS GymAxis.",
        )
        chat.with_model("gemini", MODEL).with_params(modalities=["image", "text"])
        msg = UserMessage(text=prompt, file_contents=[ImageContent(logo_b64)])
        text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            return slug, False, f"no images returned. text={text[:200]}"
        out_path.write_bytes(base64.b64decode(images[0]["data"]))
        return slug, True, f"saved {out_path.name} ({out_path.stat().st_size // 1024} KB)"
    except Exception as exc:  # noqa: BLE001
        return slug, False, f"error: {exc}"


async def main() -> None:
    logo_b64 = encode_logo()
    print(f"[start] generating {len(POSTS)} posts in parallel...", flush=True)
    results = await asyncio.gather(*[generate_one(p, logo_b64) for p in POSTS])
    print("\n[results]")
    ok = 0
    for slug, success, msg in results:
        flag = "OK " if success else "FAIL"
        print(f"  {flag} {slug}: {msg}")
        if success:
            ok += 1
    print(f"\n[done] {ok}/{len(POSTS)} succeeded.")


if __name__ == "__main__":
    asyncio.run(main())
