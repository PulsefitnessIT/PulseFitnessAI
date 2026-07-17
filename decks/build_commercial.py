"""Deck 1 — Pulsefitness.ai for Commercial Customers."""
import sys
sys.path.insert(0, "/app/decks")
from pulse_deck import *
from pulse_deck import _round_radius, _soft_shadow, _set_latin
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

prs = new_prs()
PAGE = [0]

def pg():
    PAGE[0] += 1
    return PAGE[0]

def phone(s, x, y, w, screen_fill=CARD):
    h = w * 2.02
    body = rect(s, x, y, w, h, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True)
    _round_radius(body, 0.14)
    scr = rect(s, x + 0.09, y + 0.16, w - 0.18, h - 0.32, fill=screen_fill,
               shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(scr, 0.07)
    rect(s, x + w/2 - 0.28, y + 0.075, 0.56, 0.05, fill=RGBColor(0x2A,0x33,0x38),
         shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    return x + 0.09, y + 0.16, w - 0.18, h - 0.32

# ============================================================ 1 · TITLE
s = slide(prs, bg=DARKBG)
# deep panel accent on right
rect(s, 8.9, 0, SW - 8.9, SH, fill=RGBColor(0x0E, 0x22, 0x2C))
# subtle core-blue mark motif large, faint on right
pic = s.shapes.add_picture(ASSETS + "mark.png", Inches(9.9), Inches(1.2), Inches(3.6), Inches(3.6))
# thin accent
rect(s, 0, 0, SW, 0.09, fill=CORE)
logo(s, dark_bg=True, x=LM, y=0.6, w=2.6)
text(s, LM, 2.55, 8.2, 0.4, [para("THE CONNECTED OPERATIONS PLATFORM", size=13, color=CORE, bold=True)])
text(s, LM, 3.02, 8.4, 2.2,
     [para("Fitness facilities, equipment and", size=40, color=WHITE, bold=True, line=1.04),
      para("service teams — in one place.", size=40, color=WHITE, bold=True, line=1.04)])
text(s, LM, 4.95, 7.7, 1.0,
     [para("Bring equipment, faults, assets, suppliers, staff, reporting and service "
           "history together in a single connected portal.", size=14.5,
           color=RGBColor(0xB8,0xC6,0xCD), line=1.3)])
rect(s, LM, 6.35, 3.2, 0.02, fill=RGBColor(0x2E,0x3A,0x40))
text(s, LM, 6.55, 9.0, 0.4,
     [para([{'text': "pulsefitness.ai", 'size': 12, 'color': WHITE, 'bold': True},
            {'text': "      Built by fitness equipment and service specialists", 'size': 12,
             'color': SLATE_LT}])])

# ============================================================ 2 · THE PROBLEM
s = slide(prs, bg=MIST)
top = header(s, "The challenge", "Too much runs through disconnected tools",
             "Equipment, faults and service history are spread across inboxes, spreadsheets and messages "
             "— so nothing is truly visible.")
# left narrative
text(s, LM, 2.55, 5.6, 3.0,
     [para("When information lives in separate places, jobs get missed, response times slip, "
           "and it becomes hard to prove what happened to a machine and when.", size=14, color=INK, line=1.4)])
bullet_list(s, LM, 4.05, 5.6, [
    ("No single record  ", "— history is scattered across people and systems"),
    ("Slow fault handling  ", "— logged by phone or message, easily lost"),
    ("Weak reporting  ", "— downtime and repeat faults are hard to evidence"),
    ("No audit trail  ", "— limited visibility for managers and stakeholders"),
], size=12.5, glyph="\uf071", glyph_color=RGBColor(0xD1,0x5B,0x4E))
# right fragmented tools visual
fx = 7.0
fragments = [("\uf0e0", "Email threads"), ("\uf1c3", "Spreadsheets"),
             ("\uf232", "WhatsApp"), ("\uf095", "Phone calls"),
             ("\uf15c", "Paper notes"), ("\uf07b", "Local files")]
cw2 = 2.55; ch2 = 0.92; gp = 0.22
for i, (g, lab) in enumerate(fragments):
    r, c = divmod(i, 2)
    x = fx + c * (cw2 + gp); y = 2.6 + r * (ch2 + gp)
    bx = rect(s, x, y, cw2, ch2, fill=WHITE, line=SILVER, line_w=1.0,
              shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.12)
    icon_chip(s, x + 0.18, y + ch2/2 - 0.22, g, size=0.44, chip=RGBColor(0xEE,0xF3,0xF6),
              glyph_color=SLATE, gsize=13)
    text(s, x + 0.76, y, cw2 - 0.8, ch2, [para(lab, size=11.5, color=NAVY, bold=True)],
         anchor=MSO_ANCHOR.MIDDLE)
footer(s, pg())

# ============================================================ 3 · THE SOLUTION
s = slide(prs, bg=WHITE)
top = header(s, "The platform", "One connected portal for the whole operation",
             "Pulsefitness.ai joins equipment, faults, suppliers, engineers, stock and reporting "
             "so every team works from the same information.")
# dashboard mockup right
ix, iy, iw, ih = window_frame(s, 6.55, 2.45, 6.05, 4.05, "app.pulsefitness.ai/dashboard")
sidebar(s, ix, iy, 1.35, ih, ["Dashboard", "Equipment", "Faults", "Parts", "Reports", "CRM"], active=0)
cx = ix + 1.55; cw = iw - 1.7
kpw = (cw - 0.4) / 3
kpi_tile(s, cx, iy + 0.18, kpw, 1.25, "12", "Open faults", "\uf071", delta="8%", up=False)
kpi_tile(s, cx + kpw + 0.2, iy + 0.18, kpw, 1.25, "98%", "SLA on time", "\uf058", delta="3%", up=True)
kpi_tile(s, cx + 2*(kpw + 0.2), iy + 0.18, kpw, 1.25, "247", "Assets tracked", "\uf02b")
text(s, cx, iy + 1.6, cw, 0.25, [para("Faults by month", size=9, color=SLATE, bold=True)])
mini_bars(s, cx, iy + 1.9, cw, 0.85, [6,9,7,11,8,5], ["Feb","Mar","Apr","May","Jun","Jul"], hi=3)
# left bullets
bullet_list(s, LM, 2.6, 5.3, [
    ("Everything linked  ", "— faults, parts and reports sit against the right machine"),
    ("Live visibility  ", "— see status across one site or your whole estate"),
    ("Shared with your team  ", "— staff, engineers and suppliers stay aligned"),
    ("Full history  ", "— every action recorded and easy to retrieve"),
], size=13, glyph="\uf058")
footer(s, pg())

# ============================================================ 4 · CUSTOMER PORTAL
s = slide(prs, bg=MIST)
top = header(s, "Customer portal", "A clear front door for your facility",
             "Your team logs faults, tracks progress and manages equipment without chasing emails or calls.")
bullet_list(s, LM, 2.6, 5.4, [
    ("Log faults in seconds  ", "against the correct machine, with photos and video"),
    ("Track every update  ", "from report through to resolution"),
    ("Request parts  ", "directly against equipment when needed"),
    ("View equipment history  ", "service records, documents and warranty"),
    ("Upload evidence  ", "images and clips that help engineers arrive prepared"),
], size=12.5)
# portal window mockup
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "portal.pulsefitness.ai/faults")
text(s, ix + 0.3, iy + 0.2, iw - 0.6, 0.3, [para("My faults", size=12, color=NAVY, bold=True)])
btn = rect(s, ix + iw - 1.7, iy + 0.2, 1.4, 0.36, fill=CORE, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(btn, 0.5)
text(s, ix + iw - 1.7, iy + 0.17, 1.4, 0.36, [para("+  Log a fault", size=9.5, color=INK, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
list_rows(s, ix + 0.3, iy + 0.75, iw - 0.6, [
    ("Treadmill 07 — belt slipping", "Cardio suite · reported 2h ago", "In progress", CORE_DK),
    ("Leg press — cable fault", "Strength floor · engineer assigned", "Assigned", RGBColor(0xD1,0x8A,0x2E)),
    ("Rower 03 — screen blank", "Studio · awaiting part", "On hold", SLATE),
    ("Bike 12 — resolved", "Spin room · closed today", "Resolved", RGBColor(0x1F,0x9D,0x55)),
], rh=0.62)
footer(s, pg())

# ============================================================ 5 · ASSET MANAGEMENT
s = slide(prs, bg=WHITE)
top = header(s, "Asset management", "Every machine has a complete record",
             "One reliable source of truth for each item of equipment across all of your sites.")
# asset record mockup (left)
ix, iy, iw, ih = window_frame(s, LM, 2.55, 5.9, 3.9, "app.pulsefitness.ai/equipment/TM-07")
rect(s, ix + 0.3, iy + 0.25, 1.4, 1.4, fill=CARD, line=SILVER, line_w=1, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
icon_chip(s, ix + 0.75, iy + 0.62, "\uf44b", size=0.55, chip=RGBColor(0xEE,0xF3,0xF6), glyph_color=CORE_DK, gsize=16)
text(s, ix + 1.9, iy + 0.28, iw - 2.1, 0.35, [para("Treadmill — Model X9", size=13, color=NAVY, bold=True)])
for i, (k, v) in enumerate([("Serial", "TMX9-4471-08"), ("Site", "Riverside Leisure"),
                            ("Warranty", "Active · exp 03/27"), ("Last service", "12 May 2026")]):
    yy = iy + 0.72 + i * 0.28
    text(s, ix + 1.9, yy, 1.3, 0.25, [para(k, size=9, color=SLATE_LT, bold=True)])
    text(s, ix + 3.05, yy, iw - 3.2, 0.25, [para(v, size=9.5, color=INK)])
rect(s, ix + 0.3, iy + 2.0, iw - 0.6, 0.012, fill=SILVER)
for i, (g, lab) in enumerate([("\uf1da","Service history"),("\uf15b","Manuals & docs"),("\uf03e","Photos")]):
    x = ix + 0.3 + i * ((iw - 0.6)/3)
    icon_chip(s, x, iy + 2.2, g, size=0.36, chip=CARD, glyph_color=CORE_DK, gsize=10)
    text(s, x + 0.46, iy + 2.2, (iw-0.6)/3 - 0.5, 0.36, [para(lab, size=8.5, color=NAVY, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
# right grid of what's captured
feats = [
    ("\uf02b", "Make, model & serial", "Every machine identified precisely across the estate."),
    ("\uf3c5", "Site & location", "Know exactly where each item lives, room by room."),
    ("\uf3ed", "Warranty & cover", "Warranty dates and contract cover at a glance."),
    ("\uf1da", "Service history", "Every visit, fault and part recorded on the asset."),
    ("\uf15b", "Manuals & documents", "Guides, certificates and files kept in one place."),
    ("\uf03e", "Images", "Reference photos to support faults and identification."),
]
feature_list(s, feats, x=6.9, y=2.62, w=SW - RM - 6.9, row_h=0.63)
footer(s, pg())

# ============================================================ 6 · FAULT LOGGING
s = slide(prs, bg=MIST)
top = header(s, "Fault logging", "Report faults against the right machine",
             "Structured fault capture means engineers arrive informed and nothing gets lost in translation.")
bullet_list(s, LM, 2.6, 5.4, [
    ("Linked to equipment  ", "every fault sits against the correct asset and site"),
    ("Photos & video  ", "attach evidence so the issue is understood up front"),
    ("Priority & severity  ", "flag out-of-order machines and urgent safety issues"),
    ("Notes & contact  ", "capture context and the right person to reach"),
    ("Status you can follow  ", "a clear trail from reported to resolved"),
], size=12.5)
# fault form mockup
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "portal.pulsefitness.ai/faults/new")
text(s, ix + 0.3, iy + 0.22, iw - 0.6, 0.3, [para("Log a fault", size=13, color=NAVY, bold=True)])
fields = [("Equipment", "Treadmill 07 — Cardio suite"), ("Fault type", "Belt slipping under load"),
          ("Priority", "High · out of order")]
fy = iy + 0.68
for k, v in fields:
    text(s, ix + 0.3, fy, 2.0, 0.25, [para(k, size=9, color=SLATE_LT, bold=True)])
    bx = rect(s, ix + 0.3, fy + 0.24, iw - 0.6, 0.4, fill=WHITE, line=SILVER, line_w=0.8,
              shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(bx, 0.18)
    text(s, ix + 0.45, fy + 0.22, iw - 0.9, 0.4, [para(v, size=9.5, color=INK)], anchor=MSO_ANCHOR.MIDDLE)
    fy += 0.78
# attach chips
text(s, ix + 0.3, fy, 2.0, 0.25, [para("Attachments", size=9, color=SLATE_LT, bold=True)])
for i, (g, lab) in enumerate([("\uf03e","2 photos"),("\uf03d","1 video")]):
    x = ix + 0.3 + i * 1.6
    ch = rect(s, x, fy + 0.24, 1.45, 0.4, fill=CARD, line=SILVER, line_w=0.8, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(ch, 0.3)
    icon_chip(s, x + 0.1, fy + 0.29, g, size=0.3, chip=CORE, glyph_color=INK, gsize=9)
    text(s, x + 0.5, fy + 0.22, 0.95, 0.4, [para(lab, size=9, color=NAVY, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
sb = rect(s, ix + iw - 1.9, fy + 0.24, 1.6, 0.4, fill=CORE, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(sb, 0.3)
text(s, ix + iw - 1.9, fy + 0.22, 1.6, 0.4, [para("Submit fault", size=9.5, color=INK, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
footer(s, pg())

# ============================================================ 7 · SUPPLIER / SERVICE DESK FLOW
s = slide(prs, bg=WHITE)
top = header(s, "Supplier & service desk flow", "Faults reach the right team, first time",
             "Every fault is routed with a structured job card — to a supplier, an engineer or your internal service desk.")
stages = [("\uf071", "Fault logged", "Captured against the machine with photos and detail"),
          ("\uf074", "Routed", "Sent to the right owner based on cover and type"),
          ("\uf0d1", "Actioned", "Supplier, engineer or service desk takes the job"),
          ("\uf46c", "Resolved", "Work, parts and outcome recorded on the asset")]
cwf = (CW - 3 * 0.75) / 4
for i, (g, t, d) in enumerate(stages):
    x = LM + i * (cwf + 0.75)
    bx = rect(s, x, 2.75, cwf, 2.0, fill=CARD, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.07)
    icon_chip(s, x + cwf/2 - 0.32, 2.98, g, size=0.64, gsize=18)
    text(s, x + 0.2, 3.78, cwf - 0.4, 0.35, [para(t, size=13, color=NAVY, bold=True, align=PP_ALIGN.CENTER)])
    text(s, x + 0.2, 4.15, cwf - 0.4, 0.55, [para(d, size=9.5, color=SLATE, line=1.15, align=PP_ALIGN.CENTER)])
    if i < 3:
        ar = rect(s, x + cwf + 0.16, 3.6, 0.42, 0.42, fill=CORE, shape=MSO_SHAPE.OVAL)
        text(s, x + cwf + 0.16, 3.57, 0.42, 0.42, [para("\uf061", size=12, color=INK, bold=True, font=ICON, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
# structured card note
nb = rect(s, LM, 5.1, CW, 1.35, fill=DARKBG_2, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(nb, 0.06)
rect(s, LM, 5.1, 0.1, 1.35, fill=CORE)
text(s, LM + 0.4, 5.28, 4.0, 0.4, [para("Structured supplier job card", size=13, color=WHITE, bold=True)])
text(s, LM + 0.4, 5.68, CW - 0.8, 0.6,
     [para("Site  ·  equipment  ·  serial number  ·  fault detail  ·  photos  ·  contact  —  "
           "everything a supplier or engineer needs, sent in one clear, consistent card.",
           size=11.5, color=RGBColor(0xC4,0xD2,0xD9), line=1.3)])
footer(s, pg())

# ============================================================ 8 · REQUEST PARTS
s = slide(prs, bg=MIST)
top = header(s, "Request parts", "Order the right part against the right machine",
             "Part requests are tied to the exact asset, with drawings and photos to remove guesswork.")
feats = [
    ("\uf05b", "Against the machine", "Requests are linked to a specific asset and serial number."),
    ("\uf5fd", "Exploded drawings", "Select the correct part from diagrams where available."),
    ("\uf03e", "Photo support", "Upload images to confirm the component needed."),
    ("\uf3ed", "Warranty visibility", "See cover status before a request is submitted."),
    ("\uf1d8", "Straight to Pulse", "Requests are sent directly to the Pulse Fitness team."),
    ("\uf1da", "Tracked history", "Every request recorded against the equipment record."),
]
feature_grid(s, feats, cols=3, top=2.55, bottom=6.5, gap=0.3)
footer(s, pg())

# ============================================================ 9 · ENGINEER APP
s = slide(prs, bg=WHITE)
top = header(s, "Engineer app", "Everything the engineer needs, on site",
             "Jobs, history, parts and manuals in one app — updated from mobile or desktop.")
bullet_list(s, LM, 2.6, 5.9, [
    ("Today's jobs  ", "a clear, ordered view of what's due and where"),
    ("Full asset history  ", "past faults, services and notes before arrival"),
    ("Photos, notes & parts  ", "record work and components used on the job"),
    ("Manuals & documents  ", "reference guides available at the machine"),
    ("Route & site detail  ", "location, access and contact information"),
    ("Update anywhere  ", "complete work from the field or the office"),
], size=12.5)
# phone mockup
px, py, pw, ph = phone(s, 8.4, 2.35, 2.2)
text(s, px + 0.2, py + 0.18, pw - 0.4, 0.3, [para("My day", size=12, color=NAVY, bold=True)])
text(s, px + 0.2, py + 0.5, pw - 0.4, 0.2, [para("Tue 14 Jul · 5 jobs", size=8, color=SLATE_LT)])
jr = py + 0.85
for (t, m, tag, tc) in [("Treadmill 07", "Riverside · 09:30", "Next", CORE_DK),
                        ("Leg press cable", "Riverside · 11:00", "Due", RGBColor(0xD1,0x8A,0x2E)),
                        ("Rower 03 screen", "Central · 13:30", "Part", SLATE),
                        ("Bike 12 service", "Central · 15:00", "PPM", RGBColor(0x1F,0x9D,0x55))]:
    rc = rect(s, px + 0.16, jr, pw - 0.32, 0.5, fill=WHITE, line=SILVER, line_w=0.6, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(rc, 0.12)
    rect(s, px + 0.16, jr, 0.05, 0.5, fill=tc)
    text(s, px + 0.3, jr + 0.05, pw - 0.9, 0.2, [para(t, size=8, color=NAVY, bold=True)])
    text(s, px + 0.3, jr + 0.24, pw - 0.9, 0.18, [para(m, size=6.5, color=SLATE_LT)])
    text(s, px + pw - 0.62, jr + 0.13, 0.5, 0.25, [para(tag, size=6.5, color=tc, bold=True, align=PP_ALIGN.CENTER)])
    jr += 0.6
footer(s, pg())

# ============================================================ 10 · AI SCHEDULING
s = slide(prs, bg=MIST)
top = header(s, "Scheduling", "Smarter planning, with planners in control",
             "Optimise engineer schedules while protecting live jobs, SLAs and the plans your team has already made.")
bullet_list(s, LM, 2.6, 5.3, [
    ("Protect live jobs  ", "in-progress and committed work is never disrupted"),
    ("Reduce travel  ", "group nearby jobs to save time and mileage"),
    ("Protect SLAs  ", "prioritise work against agreed response times"),
    ("Balance the day  ", "sensible workloads across the team"),
    ("You stay in control  ", "recommendations to accept, adjust or override"),
], size=12.5)
# schedule board mockup
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "app.pulsefitness.ai/scheduler")
cols = ["Mon", "Tue", "Wed", "Thu", "Fri"]
colw = (iw - 0.6) / 5
for i, c in enumerate(cols):
    text(s, ix + 0.3 + i * colw, iy + 0.2, colw, 0.25, [para(c, size=9, color=SLATE, bold=True, align=PP_ALIGN.CENTER)])
import random
random.seed(4)
palette = [CORE, CORE_DK, RGBColor(0x2E,0x8B,0xA6), RGBColor(0x0E,0x6E,0x8C)]
for i in range(5):
    yy = iy + 0.55
    for j in range(random.randint(2,4)):
        bh = 0.4 + random.random()*0.35
        bx = rect(s, ix + 0.34 + i*colw, yy, colw - 0.16, bh, fill=palette[(i+j) % 4], shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(bx, 0.14)
        yy += bh + 0.12
# highlight protected job
text(s, ix + 0.3, iy + ih - 0.45, iw - 0.6, 0.3,
     [para([{'text':"\uf023  ",'font':ICON,'size':9,'color':CORE_DK,'bold':True},
            {'text':"Live jobs locked — recommendations fit around them",'size':9,'color':SLATE,'bold':True}])])
footer(s, pg())

# ============================================================ 11 · STOCK & PARTS CONTROL
s = slide(prs, bg=WHITE)
top = header(s, "Stock & parts control", "Full visibility of parts, everywhere",
             "From van stock to remote stores — manage what you hold, what's used and what to reorder.")
feats = [
    ("\uf466", "Parts catalogue", "A clean, consistent record of every part and code."),
    ("\uf0d1", "Van stock", "See what each engineer is carrying in the field."),
    ("\uf291", "Customer requests", "Handle part requests raised from the customer portal."),
    ("\uf494", "Dealer & remote stores", "Track stock held across dealers and store locations."),
    ("\uf021", "Usage & replenishment", "Monitor consumption and trigger sensible reordering."),
    ("\uf201", "Global failure trends", "Spot parts that fail often and plan ahead."),
]
feature_grid(s, feats, cols=3, top=2.55, bottom=6.5, gap=0.3)
footer(s, pg())

# ============================================================ 12 · CONTRACTS & WARRANTY
s = slide(prs, bg=MIST)
top = header(s, "Contracts & warranty", "Cover and chargeability, made clear",
             "See exactly what's covered before work begins — no ambiguity over who pays.")
bullet_list(s, LM, 2.6, 5.4, [
    ("Contract type  ", "the agreement in place for each site and asset"),
    ("Warranty status  ", "active cover and expiry dates at a glance"),
    ("Exclusions  ", "what falls outside cover, clearly shown"),
    ("Cover levels  ", "the scope of service tied to each machine"),
    ("Chargeable decisions  ", "confident, evidenced calls on billing"),
], size=12.5)
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "app.pulsefitness.ai/equipment/TM-07/cover")
text(s, ix + 0.3, iy + 0.22, iw - 0.6, 0.3, [para("Cover summary — Treadmill 07", size=12.5, color=NAVY, bold=True)])
rows = [("Contract", "Comprehensive · Riverside estate", RGBColor(0x1F,0x9D,0x55), "Active"),
        ("Warranty", "Parts & labour · expires 03/2027", RGBColor(0x1F,0x9D,0x55), "Active"),
        ("Exclusions", "Consumables · accidental damage", SLATE, "Noted"),
        ("This fault", "Belt wear — within cover", CORE_DK, "Covered")]
ry = iy + 0.7
for k, v, tc, tag in rows:
    rc = rect(s, ix + 0.3, ry, iw - 0.6, 0.6, fill=WHITE, line=SILVER, line_w=0.7, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(rc, 0.1)
    text(s, ix + 0.5, ry + 0.09, 1.6, 0.2, [para(k, size=9, color=SLATE_LT, bold=True)])
    text(s, ix + 0.5, ry + 0.28, iw - 2.6, 0.25, [para(v, size=9.5, color=INK)])
    tp = rect(s, ix + iw - 1.5, ry + 0.16, 1.1, 0.28, fill=None, line=tc, line_w=0.9, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(tp, 0.5)
    text(s, ix + iw - 1.5, ry + 0.13, 1.1, 0.28, [para(tag, size=8, color=tc, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
    ry += 0.7
footer(s, pg())

# ============================================================ 13 · CAPEX REPORTING
s = slide(prs, bg=WHITE)
top = header(s, "CAPEX reporting", "Build the evidence for replacement",
             "Turn service history into a clear, defensible case for repairing or replacing ageing equipment.")
bullet_list(s, LM, 2.6, 5.3, [
    ("Age & condition  ", "identify equipment nearing end of life"),
    ("Fault frequency  ", "surface machines that break down repeatedly"),
    ("Downtime  ", "quantify time out of service and its impact"),
    ("Cost to serve  ", "see the true running cost of each asset"),
    ("Replacement evidence  ", "a clear case for capital investment"),
], size=12.5)
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "app.pulsefitness.ai/reports/capex")
text(s, ix + 0.3, iy + 0.2, iw - 0.6, 0.3, [para("Replacement risk by asset", size=11.5, color=NAVY, bold=True)])
mini_bars(s, ix + 0.35, iy + 0.65, iw - 0.7, 1.5, [3,4,6,9,11,7,5], hi=4)
text(s, ix + 0.3, iy + 2.3, iw - 0.6, 0.25, [para("Flagged for review", size=10, color=SLATE, bold=True)])
list_rows(s, ix + 0.3, iy + 2.6, iw - 0.6, [
    ("Treadmill 07 — 9 yrs", "18 faults · 34h downtime", "Replace", RGBColor(0xD1,0x5B,0x4E)),
    ("Cross-trainer 04 — 7 yrs", "9 faults · rising cost", "Review", RGBColor(0xD1,0x8A,0x2E)),
], rh=0.48)
footer(s, pg())

# ============================================================ 14 · REPORTS & DASHBOARDS
s = slide(prs, bg=MIST)
top = header(s, "Reports & dashboards", "The numbers that run your operation",
             "Operational reporting across faults, response, downtime, engineers and asset condition.")
ix, iy, iw, ih = window_frame(s, LM, 2.5, 7.1, 4.0, "app.pulsefitness.ai/reports")
kpw = (iw - 0.6 - 0.4) / 3
kpi_tile(s, ix + 0.3, iy + 0.2, kpw, 1.2, "1.8h", "Avg response", "\uf017", delta="12%", up=True)
kpi_tile(s, ix + 0.3 + kpw + 0.2, iy + 0.2, kpw, 1.2, "96%", "Jobs on time", "\uf058", delta="4%", up=True)
kpi_tile(s, ix + 0.3 + 2*(kpw+0.2), iy + 0.2, kpw, 1.2, "5.2%", "Repeat faults", "\uf021", delta="2%", up=False)
text(s, ix + 0.3, iy + 1.6, iw-0.6, 0.25, [para("Downtime hours by month", size=9.5, color=SLATE, bold=True)])
mini_bars(s, ix + 0.35, iy + 1.95, iw - 0.7, 1.35, [22,18,15,19,12,9], ["Feb","Mar","Apr","May","Jun","Jul"], hi=5)
# right captions
caps = [("\uf071","Faults & repeat issues"),("\uf017","Response & resolution times"),
        ("\uf0c0","Engineer activity"),("\uf02b","Asset condition"),("\uf1da","Service performance")]
cy = 2.7
for g, lab in caps:
    icon_chip(s, 8.05, cy, g, size=0.44, chip=CARD, glyph_color=CORE_DK, gsize=12)
    text(s, 8.6, cy, SW - RM - 8.6, 0.44, [para(lab, size=12, color=NAVY, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
    cy += 0.72
footer(s, pg())

# ============================================================ 15 · SAFETY & COMPLIANCE
s = slide(prs, bg=WHITE)
top = header(s, "Safety & compliance", "Evidence you can stand behind",
             "Capture safety events and compliance records with a complete, time-stamped audit trail.")
feats = [
    ("\uf0fe", "Accident reports", "Record incidents with the detail you need on file."),
    ("\uf46c", "RIDDOR reports", "Support reportable incident requirements clearly."),
    ("\uf132", "Risk assessments", "Document and store assessments against sites and tasks."),
    ("\uf0ae", "Check sheets", "Routine safety checks recorded and easy to review."),
    ("\uf1da", "Audit trail", "Every entry and change logged and traceable."),
    ("\uf3ed", "Evidence storage", "Files and records kept together and retrievable."),
]
feature_grid(s, feats, cols=3, top=2.55, bottom=6.5, gap=0.3)
footer(s, pg())

# ============================================================ 16 · STAFFING & OPERATIONS
s = slide(prs, bg=MIST)
top = header(s, "Staffing & operations", "Keep the day-to-day joined up",
             "Bring people, tasks and communication into the same platform as your equipment and service.")
feats = [
    ("\uf2bb", "Staff records", "Hold people, roles and details in one place."),
    ("\uf075", "Communication", "Keep messages and updates alongside the work."),
    ("\uf542", "Org charts", "See structure and responsibilities at a glance."),
    ("\uf571", "Expenses", "Capture and track operational spend."),
    ("\uf0ae", "Site tasks", "Assign and follow up on day-to-day jobs."),
    ("\uf06e", "Operational visibility", "A clear view across sites and teams."),
]
feature_grid(s, feats, cols=3, top=2.55, bottom=6.5, gap=0.3)
footer(s, pg())

# ============================================================ 17 · CRM & CORPORATE
s = slide(prs, bg=WHITE)
top = header(s, "CRM & corporate", "Manage relationships and growth",
             "A built-in CRM connects your commercial activity to the equipment and service that underpins it.")
feats = [
    ("\uf1ad", "Companies & contacts", "Organised customer and contact records."),
    ("\uf3c5", "Sites", "Every site linked to its equipment and history."),
    ("\uf0eb", "Opportunities", "Track pipeline from enquiry to won."),
    ("\uf571", "Quotes", "Create and manage branded quotations."),
    ("\uf56c", "Contracts", "Hold agreements against companies and sites."),
    ("\uf0a1", "Campaigns", "Run and record marketing and comms activity."),
    ("\uf5a0", "Pre-install surveys", "Structured site surveys before installation."),
    ("\uf1da", "Communication history", "A full record of contact over time."),
]
feature_grid(s, feats, cols=4, top=2.55, bottom=6.5, gap=0.26)
footer(s, pg())

# ============================================================ 18 · ONBOARDING & PHOTO ONBOARDING
s = slide(prs, bg=MIST)
top = header(s, "Onboarding", "Add your equipment quickly — two ways",
             "Import by spreadsheet, or simply photograph a machine and let Pulse extract the detail for review.")
steps = [("\uf574", "Upload", "Add equipment by spreadsheet, or take a photo of the machine and data plate."),
         ("\uf0eb", "Extract", "Pulse reads make, model and serial number and drafts the asset record."),
         ("\uf46c", "Review & confirm", "Your team checks the detail and approves it into the register.")]
cwf = (CW - 2 * 0.9) / 3
for i, (g, t, d) in enumerate(steps):
    x = LM + i * (cwf + 0.9)
    bx = rect(s, x, 2.75, cwf, 2.4, fill=WHITE, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.06)
    rect(s, x, 2.75, cwf, 0.09, fill=CORE)
    text(s, x + 0.3, 2.98, 1.5, 0.4, [para(f"0{i+1}", size=22, color=RGBColor(0xC9,0xD6,0xDC), bold=True)])
    icon_chip(s, x + cwf - 0.9, 3.0, g, size=0.6, gsize=17)
    text(s, x + 0.3, 3.7, cwf - 0.6, 0.35, [para(t, size=15, color=NAVY, bold=True)])
    text(s, x + 0.3, 4.12, cwf - 0.6, 0.9, [para(d, size=11, color=SLATE, line=1.25)])
    if i < 2:
        text(s, x + cwf + 0.2, 3.7, 0.5, 0.5, [para("\uf061", size=16, color=CORE, bold=True, font=ICON, align=PP_ALIGN.CENTER)])
nb = rect(s, LM, 5.45, CW, 1.0, fill=DARKBG_2, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(nb, 0.07)
rect(s, LM, 5.45, 0.1, 1.0, fill=CORE)
text(s, LM + 0.4, 5.68, CW - 0.8, 0.6,
     [para([{'text':"Nothing is added automatically.  ",'size':11.5,'color':WHITE,'bold':True},
            {'text':"AI drafts the record; your team always reviews and confirms before it enters the register.",
             'size':11.5,'color':RGBColor(0xC4,0xD2,0xD9)}])], anchor=MSO_ANCHOR.MIDDLE)
footer(s, pg())

# ============================================================ 19 · AI SUPPORT
s = slide(prs, bg=WHITE)
top = header(s, "AI support", "Practical help, not gimmicks",
             "AI assists your team with the routine, while people stay firmly in control of every decision.")
feats = [
    ("\uf0ae", "Summaries", "Condense long histories into a quick, clear picture."),
    ("\uf0fa", "Triage", "Suggest likely causes and next steps for a fault."),
    ("\uf15c", "Reports", "Help draft clear, consistent operational reports."),
    ("\uf274", "Scheduling suggestions", "Recommend sensible plans that protect live jobs."),
    ("\uf201", "CAPEX evidence", "Assemble the case for repair or replacement."),
    ("\uf00c", "Onboarding checks", "Read data plates and pre-fill records for review."),
]
feature_grid(s, feats, cols=3, top=2.55, bottom=6.5, gap=0.3)
footer(s, pg())

# ============================================================ 20 · WHY PULSE
s = slide(prs, bg=MIST)
top = header(s, "Why Pulsefitness.ai", "Built for real operational problems",
             "Not another disconnected tool — a platform shaped by people who service fitness equipment for a living.")
pillars = [("\uf0c1", "One connected platform", "Equipment, faults, parts, service and reporting in a single, joined-up system."),
           ("\uf0ad", "Built by specialists", "Designed by fitness equipment and service experts who know the work."),
           ("\uf058", "Designed for the day-to-day", "Focused on the practical problems facilities face, every single day.")]
cwf = (CW - 2 * 0.4) / 3
for i, (g, t, d) in enumerate(pillars):
    x = LM + i * (cwf + 0.4)
    bx = rect(s, x, 2.8, cwf, 3.2, fill=WHITE, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.05)
    icon_chip(s, x + 0.35, 3.15, g, size=0.8, gsize=22)
    text(s, x + 0.35, 4.2, cwf - 0.7, 0.7, [para(t, size=16.5, color=NAVY, bold=True, line=1.05)])
    text(s, x + 0.35, 5.05, cwf - 0.7, 0.9, [para(d, size=11.5, color=SLATE, line=1.3)])
footer(s, pg())

# ============================================================ 21 · IDEAL CUSTOMERS
s = slide(prs, bg=WHITE)
top = header(s, "Who it's for", "Built for the whole sector",
             "From a single independent gym to national multi-site operators and their service partners.")
customers = [("\uf44b","Commercial gyms"),("\uf1ad","Multi-site operators"),("\uf0c0","Leisure trusts"),
             ("\uf19c","Councils"),("\uf549","Universities"),("\uf236","Hotels"),
             ("\uf3c5","Studios"),("\uf0d1","Suppliers & service teams")]
cwf = (CW - 3 * 0.3) / 4
for i, (g, lab) in enumerate(customers):
    r, c = divmod(i, 4)
    x = LM + c * (cwf + 0.3); y = 2.7 + r * (1.55 + 0.35)
    bx = rect(s, x, y, cwf, 1.55, fill=CARD, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.08)
    icon_chip(s, x + cwf/2 - 0.32, y + 0.28, g, size=0.64, gsize=18)
    text(s, x + 0.15, y + 1.02, cwf - 0.3, 0.4, [para(lab, size=12, color=NAVY, bold=True, align=PP_ALIGN.CENTER, line=1.05)])
footer(s, pg())

# ============================================================ 22 · CTA
s = slide(prs, bg=DARKBG)
rect(s, 0, 0, SW, 0.09, fill=CORE)
pic = s.shapes.add_picture(ASSETS + "mark.png", Inches(10.4), Inches(0.7), Inches(2.4), Inches(2.4))
logo(s, dark_bg=True, x=LM, y=0.7, w=2.5)
text(s, LM, 2.7, 9.5, 1.6,
     [para("See Pulsefitness.ai", size=40, color=WHITE, bold=True, line=1.03),
      para("working for your facility.", size=40, color=CORE, bold=True, line=1.03)])
text(s, LM, 4.5, 8.6, 0.8,
     [para("Arrange a walkthrough with our team and we'll show you the platform against your own "
           "equipment, sites and service setup.", size=15, color=RGBColor(0xB8,0xC6,0xCD), line=1.35)])
# contact chips
chips = [("\uf073","Book a demo"),("\uf0ac","pulsefitness.ai"),("\uf0e0","Talk to our team")]
for i, (g, lab) in enumerate(chips):
    x = LM + i * 3.4
    bx = rect(s, x, 5.75, 3.1, 0.7, fill=RGBColor(0x18,0x30,0x3C), line=RGBColor(0x2C,0x44,0x4E), line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(bx, 0.5)
    icon_chip(s, x + 0.18, 5.87, g, size=0.46, chip=CORE, glyph_color=INK, gsize=13)
    text(s, x + 0.8, 5.75, 2.2, 0.7, [para(lab, size=12, color=WHITE, bold=True)], anchor=MSO_ANCHOR.MIDDLE)

prs.save("/app/decks/Pulsefitness_Commercial_Presentation.pptx")
print(f"Commercial deck saved — {len(prs.slides.__iter__.__self__._sldIdLst)} slides")
