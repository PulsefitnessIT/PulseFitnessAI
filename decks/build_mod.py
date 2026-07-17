"""Deck 2 — Pulsefitness.ai MOD Service Portal (tender submission)."""
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

MOD_NAVY = RGBColor(0x0C, 0x24, 0x30)

# ============================================================ 1 · TITLE
s = slide(prs, bg=MOD_NAVY)
rect(s, 0, 0, SW, 0.09, fill=CORE)
rect(s, 8.7, 0, SW - 8.7, SH, fill=RGBColor(0x0A, 0x1D, 0x27))
pic = s.shapes.add_picture(ASSETS + "mark.png", Inches(9.7), Inches(1.15), Inches(3.7), Inches(3.7))
logo(s, dark_bg=True, x=LM, y=0.6, w=2.6)
text(s, LM, 2.4, 8.0, 0.4, [para("MOD SERVICE PORTAL", size=13, color=CORE, bold=True)])
text(s, LM, 2.88, 8.3, 2.2,
     [para("A secure service and equipment", size=37, color=WHITE, bold=True, line=1.05),
      para("portal for MOD fitness and", size=37, color=WHITE, bold=True, line=1.05),
      para("rehabilitation environments.", size=37, color=WHITE, bold=True, line=1.05)])
text(s, LM, 5.15, 7.6, 1.0,
     [para("Structured, auditable management of physical training equipment (PTE) — "
           "supporting uptime, safety, service delivery and long-term asset planning.",
           size=14, color=RGBColor(0xB2,0xC3,0xCB), line=1.35)])
rect(s, LM, 6.45, 3.2, 0.02, fill=RGBColor(0x28,0x3C,0x45))
text(s, LM, 6.62, 9.0, 0.4,
     [para([{'text': "pulsefitness.ai", 'size': 12, 'color': WHITE, 'bold': True},
            {'text': "      Commercial in Confidence  ·  Prepared for tender evaluation",
             'size': 11.5, 'color': SLATE_LT}])])

# ============================================================ 2 · MOD SERVICE CHALLENGE
s = slide(prs, bg=MIST)
top = header(s, "The requirement", "Clear visibility across MOD fitness estates",
             "Sites need dependable oversight of equipment, faults, safety events and service — with evidence that stands up to scrutiny.")
text(s, LM, 2.55, 5.5, 2.2,
     [para("Physical training and rehabilitation depend on equipment being safe, "
           "available and properly maintained. Without a single, auditable record, "
           "that assurance is hard to demonstrate.", size=13.5, color=INK, line=1.4)])
bullet_list(s, LM, 4.35, 5.5, [
    ("Equipment & PTE status  ", "know what's in service and what isn't"),
    ("Faults & downtime  ", "logged, tracked and evidenced"),
    ("Safety events  ", "captured against equipment and site"),
    ("Replacement evidence  ", "a defensible basis for investment"),
], size=12.5, glyph="\uf00c")
needs = [("\uf3c5","Site visibility"),("\uf071","Fault & downtime"),
         ("\uf132","Safety events"),("\uf1da","Service history"),
         ("\uf46c","Compliance"),("\uf201","Replacement case")]
cw2 = 2.55; ch2 = 0.92; gp = 0.22; fx = 7.0
for i, (g, lab) in enumerate(needs):
    r, c = divmod(i, 2)
    x = fx + c * (cw2 + gp); y = 2.6 + r * (ch2 + gp)
    bx = rect(s, x, y, cw2, ch2, fill=WHITE, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.12)
    icon_chip(s, x + 0.18, y + ch2/2 - 0.22, g, size=0.44, gsize=12)
    text(s, x + 0.76, y, cw2 - 0.8, ch2, [para(lab, size=11.5, color=NAVY, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
confid_footer(s, pg())

# ============================================================ 3 · PORTAL OVERVIEW
s = slide(prs, bg=WHITE)
top = header(s, "Portal overview", "One secure place for authorised site users",
             "The MOD Service Portal brings equipment, faults, service updates and reporting into a single, permission-controlled system.")
ix, iy, iw, ih = window_frame(s, 6.5, 2.45, 6.1, 4.05, "mod.pulsefitness.ai/dashboard")
sidebar(s, ix, iy, 1.35, ih, ["Overview", "Equipment", "Faults", "ASER", "Reports", "PPM"], active=0)
cx = ix + 1.55; cw = iw - 1.7
kpw = (cw - 0.4) / 3
kpi_tile(s, cx, iy + 0.18, kpw, 1.25, "8", "Open faults", "\uf071")
kpi_tile(s, cx + kpw + 0.2, iy + 0.18, kpw, 1.25, "142", "PTE tracked", "\uf02b")
kpi_tile(s, cx + 2*(kpw + 0.2), iy + 0.18, kpw, 1.25, "3", "ASER this month", "\uf132")
text(s, cx, iy + 1.6, cw, 0.25, [para("Faults & downtime trend", size=9, color=SLATE, bold=True)])
mini_bars(s, cx, iy + 1.9, cw, 0.85, [5,7,4,8,6,3], ["Feb","Mar","Apr","May","Jun","Jul"], hi=5)
bullet_list(s, LM, 2.6, 5.3, [
    ("Equipment & faults  ", "managed against every item of PTE"),
    ("Service updates  ", "clear status from report to resolution"),
    ("Safety & reporting  ", "ASER, compliance and service evidence"),
    ("Permission-controlled  ", "users see only what they should"),
], size=13, glyph="\uf058")
confid_footer(s, pg())

# ============================================================ 4 · SITE-BASED ACCESS
s = slide(prs, bg=MIST)
top = header(s, "Site-based access", "Users see only their permitted sites",
             "Access is scoped to the sites a user is authorised for — nothing more.")
bullet_list(s, LM, 2.65, 5.4, [
    ("Scoped by site  ", "equipment, faults and reports are site-restricted"),
    ("Single or multiple sites  ", "managers can be granted several locations"),
    ("No cross-site visibility  ", "data does not leak between sites"),
    ("Central oversight  ", "Pulse Fitness supports across the estate as needed"),
], size=12.5)
# access diagram
dx = 6.6
usr = rect(s, dx, 2.75, 1.9, 0.85, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(usr, 0.16)
icon_chip(s, dx + 0.2, 2.98, "\uf508", size=0.4, gsize=12)
text(s, dx + 0.72, 2.75, 1.2, 0.85, [para("Site user", size=10.5, color=WHITE, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
for i, (lab, ok) in enumerate([("Site A — permitted", True), ("Site B — permitted", True), ("Site C — not permitted", False)]):
    y = 2.75 + i * 0.95
    col = RGBColor(0x1F,0x9D,0x55) if ok else RGBColor(0xC6,0x55,0x49)
    bx = rect(s, dx + 3.0, y, 3.0, 0.72, fill=WHITE, line=col, line_w=1.3, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(bx, 0.14)
    g = "\uf00c" if ok else "\uf00d"
    icon_chip(s, dx + 3.18, y + 0.16, g, size=0.4, chip=col, gsize=11)
    text(s, dx + 3.72, y, 2.2, 0.72, [para(lab, size=10.5, color=NAVY, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
    # connector
    cn = rect(s, dx + 1.92, y + 0.28, 1.05, 0.02, fill=(col if True else SILVER))
confid_footer(s, pg())

# ============================================================ 5 · EQUIPMENT REGISTER
s = slide(prs, bg=WHITE)
top = header(s, "Equipment register", "A complete record for every item of PTE",
             "One reliable, auditable record per machine — the foundation for service, safety and planning.")
ix, iy, iw, ih = window_frame(s, LM, 2.55, 5.9, 3.9, "mod.pulsefitness.ai/equipment/TRD-002")
rect(s, ix + 0.3, iy + 0.25, 1.4, 1.4, fill=CARD, line=SILVER, line_w=1, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
icon_chip(s, ix + 0.75, iy + 0.62, "\uf44b", size=0.55, chip=RGBColor(0xEE,0xF3,0xF6), glyph_color=CORE_DK, gsize=16)
text(s, ix + 1.9, iy + 0.28, iw - 2.1, 0.35, [para("Treadmill — Rehab Suite", size=13, color=NAVY, bold=True)])
for i, (k, v) in enumerate([("Serial", "TRD-QA-002"), ("Site", "MOD Site A — Rehab"),
                            ("Warranty", "Active · exp 05/27"), ("Last service", "22 Jun 2026")]):
    yy = iy + 0.72 + i * 0.28
    text(s, ix + 1.9, yy, 1.4, 0.25, [para(k, size=9, color=SLATE_LT, bold=True)])
    text(s, ix + 3.15, yy, iw - 3.3, 0.25, [para(v, size=9.5, color=INK)])
rect(s, ix + 0.3, iy + 2.0, iw - 0.6, 0.012, fill=SILVER)
for i, (g, lab) in enumerate([("\uf1da","Service history"),("\uf15b","Documents"),("\uf132","ASER links")]):
    x = ix + 0.3 + i * ((iw - 0.6)/3)
    icon_chip(s, x, iy + 2.2, g, size=0.36, chip=CARD, glyph_color=CORE_DK, gsize=10)
    text(s, x + 0.46, iy + 2.2, (iw-0.6)/3 - 0.5, 0.36, [para(lab, size=8.5, color=NAVY, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
feats = [
    ("\uf02b", "Make, model & serial", "Each item of PTE identified precisely."),
    ("\uf3c5", "Site & location", "Where the equipment is held and used."),
    ("\uf3ed", "Warranty & cover", "Cover status and expiry, clearly shown."),
    ("\uf1da", "Service history", "Every visit and fault against the item."),
    ("\uf15b", "Images & documents", "Photos, manuals and certificates on file."),
    ("\uf132", "Linked safety events", "ASER entries connected to the asset."),
]
feature_list(s, feats, x=6.9, y=2.62, w=SW - RM - 6.9, row_h=0.63)
confid_footer(s, pg())

# ============================================================ 6 · FAULT LOGGING
s = slide(prs, bg=MIST)
top = header(s, "Fault logging", "Report faults against the right equipment",
             "Authorised users log faults directly against PTE, attach evidence and follow progress.")
bullet_list(s, LM, 2.6, 5.4, [
    ("Linked to equipment  ", "faults sit against the correct item and site"),
    ("Evidence attached  ", "photos and detail so the issue is understood"),
    ("Priority & status  ", "flag out-of-service equipment and urgency"),
    ("Progress tracked  ", "a clear trail from report to resolution"),
    ("Audit-ready  ", "every fault and change is recorded"),
], size=12.5)
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "mod.pulsefitness.ai/faults")
text(s, ix + 0.3, iy + 0.2, iw - 0.6, 0.3, [para("Site A — open faults", size=12, color=NAVY, bold=True)])
btn = rect(s, ix + iw - 1.7, iy + 0.18, 1.4, 0.36, fill=CORE, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(btn, 0.5)
text(s, ix + iw - 1.7, iy + 0.15, 1.4, 0.36, [para("+  Log a fault", size=9.5, color=INK, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
list_rows(s, ix + 0.3, iy + 0.72, iw - 0.6, [
    ("Treadmill 02 — belt fault", "Rehab suite · out of service", "High", RGBColor(0xC6,0x55,0x49)),
    ("Rower 01 — display fault", "Main gym · reported today", "In progress", CORE_DK),
    ("Bike 05 — resistance", "Studio · awaiting part", "On hold", SLATE),
    ("Cable machine — resolved", "Strength area · closed", "Resolved", RGBColor(0x1F,0x9D,0x55)),
], rh=0.62)
confid_footer(s, pg())

# ============================================================ 7 · SHARED SITE LOGIN
s = slide(prs, bg=WHITE)
top = header(s, "Shared site login & staff selection", "Shared access, individual accountability",
             "Where a shared login is appropriate, the portal still captures the individual staff member raising each fault.")
bullet_list(s, LM, 2.7, 5.5, [
    ("Shared site access  ", "one login for a site where that suits operations"),
    ("Named on every action  ", "the individual staff member is still recorded"),
    ("Optional PIN  ", "confirm the person behind a shared session"),
    ("Clear accountability  ", "who logged what, and when, is never lost"),
], size=12.5)
# staff selection mockup
ix, iy, iw, ih = window_frame(s, 6.6, 2.5, 5.95, 3.9, "mod.pulsefitness.ai/login")
text(s, ix + 0.35, iy + 0.25, iw - 0.7, 0.3, [para("Who is logging this fault?", size=12.5, color=NAVY, bold=True)])
staff = [("Sarah Jones", "General Manager"), ("D. Patel", "PTI"), ("M. Owens", "Rehab lead")]
for i, (nm, rl) in enumerate(staff):
    y = iy + 0.75 + i * 0.72
    sel = i == 0
    bx = rect(s, ix + 0.35, y, iw - 0.7, 0.6, fill=(CARD_2 if sel else WHITE), line=(CORE if sel else SILVER), line_w=(1.4 if sel else 0.8), shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(bx, 0.14)
    icon_chip(s, ix + 0.5, y + 0.1, "\uf007", size=0.4, chip=(CORE if sel else CARD), glyph_color=(INK if sel else SLATE), gsize=11)
    text(s, ix + 1.05, y + 0.09, iw - 2.0, 0.22, [para(nm, size=10.5, color=NAVY, bold=True)])
    text(s, ix + 1.05, y + 0.31, iw - 2.0, 0.2, [para(rl, size=8.5, color=SLATE_LT)])
    if sel:
        icon_chip(s, ix + iw - 0.85, y + 0.14, "\uf00c", size=0.34, chip=RGBColor(0x1F,0x9D,0x55), gsize=10)
text(s, ix + 0.35, iy + ih - 0.5, iw - 0.7, 0.3, [para([{'text':"\uf023  ",'font':ICON,'size':9,'color':CORE_DK,'bold':True},{'text':"PIN confirmation available where required",'size':9,'color':SLATE,'bold':True}])])
confid_footer(s, pg())

# ============================================================ 8 · SUPPLIER / SERVICE DESK CARDS
s = slide(prs, bg=MIST)
top = header(s, "Supplier & service desk cards", "Structured job cards to Pulse Fitness",
             "Faults are sent to Pulse Fitness as consistent, complete job cards — nothing important is left out.")
# left: what's on the card. right: card mockup
items = [("\uf3c5","Site"),("\uf44b","Equipment"),("\uf02b","Serial number"),
         ("\uf071","Fault detail"),("\uf03e","Photos & evidence"),("\uf095","Contact information")]
cwf = (5.5 - 0.24) / 2
for i, (g, lab) in enumerate(items):
    r, c = divmod(i, 2)
    x = LM + c * (cwf + 0.24); y = 2.65 + r * 0.86
    bx = rect(s, x, y, cwf, 0.72, fill=WHITE, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.14)
    icon_chip(s, x + 0.16, y + 0.13, g, size=0.44, gsize=12)
    text(s, x + 0.74, y, cwf - 0.8, 0.72, [para(lab, size=11, color=NAVY, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
# job card mockup
ix, iy, iw, ih = window_frame(s, 6.85, 2.5, 5.7, 3.95, "Job card — SVC-00147")
rect(s, ix, iy, iw, 0.5, fill=NAVY)
text(s, ix + 0.3, iy + 0.06, iw - 0.6, 0.4, [para("Job card · SVC-00147", size=11, color=WHITE, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
rows = [("Site", "MOD Site A — Rehab Suite"), ("Equipment", "Treadmill — Model X9"),
        ("Serial", "TRD-QA-002"), ("Fault", "Belt slipping — out of service"),
        ("Priority", "High"), ("Contact", "Site PTI · 01xxx xxxxxx")]
ry = iy + 0.7
for k, v in rows:
    text(s, ix + 0.35, ry, 1.5, 0.25, [para(k, size=9, color=SLATE_LT, bold=True)])
    text(s, ix + 1.85, ry, iw - 2.1, 0.25, [para(v, size=9.5, color=INK, bold=(k in ("Fault","Priority")))])
    ry += 0.47
confid_footer(s, pg())

# ============================================================ 9 · ENGINEER UPDATES
s = slide(prs, bg=WHITE)
top = header(s, "Engineer updates", "Work recorded from the field",
             "Engineers update status, add notes, record parts and complete reports from the Engineer App.")
bullet_list(s, LM, 2.6, 5.9, [
    ("Status updates  ", "keep the site informed as work progresses"),
    ("Notes & findings  ", "capture what was done and what was found"),
    ("Photos  ", "before-and-after evidence on the job"),
    ("Parts used  ", "components recorded against the equipment"),
    ("Completed reports  ", "a clear service record on every visit"),
], size=12.5)
# phone mockup (reuse inline)
def phone(s, x, y, w):
    h = w * 2.02
    body = rect(s, x, y, w, h, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(body, 0.14)
    scr = rect(s, x + 0.09, y + 0.16, w - 0.18, h - 0.32, fill=CARD, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(scr, 0.07)
    rect(s, x + w/2 - 0.28, y + 0.075, 0.56, 0.05, fill=RGBColor(0x2A,0x33,0x38), shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    return x + 0.09, y + 0.16, w - 0.18, h - 0.32
px, py, pw, ph = phone(s, 8.4, 2.35, 2.2)
text(s, px + 0.2, py + 0.16, pw - 0.4, 0.3, [para("Job · Treadmill 02", size=11, color=NAVY, bold=True)])
text(s, px + 0.2, py + 0.46, pw - 0.4, 0.2, [para("MOD Site A · Rehab", size=8, color=SLATE_LT)])
stg = [("Status", "On site", RGBColor(0x1F,0x9D,0x55)), ("Parts", "Drive belt ×1", CORE_DK), ("Notes", "Belt replaced, tested", SLATE)]
jy = py + 0.85
for k, v, c in stg:
    rc = rect(s, px + 0.16, jy, pw - 0.32, 0.6, fill=WHITE, line=SILVER, line_w=0.6, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(rc, 0.1)
    rect(s, px + 0.16, jy, 0.05, 0.6, fill=c)
    text(s, px + 0.3, jy + 0.07, pw - 0.5, 0.2, [para(k, size=7, color=SLATE_LT, bold=True)])
    text(s, px + 0.3, jy + 0.26, pw - 0.5, 0.25, [para(v, size=8.5, color=NAVY, bold=True)])
    jy += 0.7
cb = rect(s, px + 0.16, jy + 0.05, pw - 0.32, 0.42, fill=CORE, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(cb, 0.3)
text(s, px + 0.16, jy + 0.02, pw - 0.32, 0.42, [para("Complete report", size=8.5, color=INK, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
confid_footer(s, pg())

# ============================================================ 10 · REQUEST PARTS
s = slide(prs, bg=MIST)
top = header(s, "Request parts", "Order the right part against the right PTE",
             "Part requests are tied to the exact item of equipment, with drawings and photos to remove guesswork.")
feats = [
    ("\uf05b", "Against the machine", "Requests linked to a specific item and serial number."),
    ("\uf5fd", "Exploded drawings", "Select the correct part from diagrams where available."),
    ("\uf03e", "Photo support", "Upload images to confirm the component needed."),
    ("\uf3ed", "Cover visibility", "See warranty and cover before requesting."),
    ("\uf1d8", "Straight to Pulse", "Requests routed directly to the Pulse Fitness team."),
    ("\uf1da", "Recorded history", "Every request kept against the equipment record."),
]
feature_grid(s, feats, cols=3, top=2.55, bottom=6.5, gap=0.3)
confid_footer(s, pg())

# ============================================================ 11 · WARRANTY & COVER
s = slide(prs, bg=WHITE)
top = header(s, "Warranty & cover visibility", "Know what's covered before work begins",
             "Each equipment record shows warranty, contract cover, exclusions and chargeable review status.")
bullet_list(s, LM, 2.65, 5.4, [
    ("Warranty  ", "active cover and expiry dates at a glance"),
    ("Contract cover  ", "the agreement in place for each site and item"),
    ("Exclusions  ", "what falls outside cover, clearly shown"),
    ("Chargeable review  ", "transparent, evidenced billing decisions"),
], size=12.5)
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "mod.pulsefitness.ai/equipment/TRD-002/cover")
text(s, ix + 0.3, iy + 0.22, iw - 0.6, 0.3, [para("Cover summary — Treadmill 02", size=12.5, color=NAVY, bold=True)])
rows = [("Contract", "Comprehensive · MOD Site A", RGBColor(0x1F,0x9D,0x55), "Active"),
        ("Warranty", "Parts & labour · exp 05/2027", RGBColor(0x1F,0x9D,0x55), "Active"),
        ("Exclusions", "Consumables · misuse", SLATE, "Noted"),
        ("This fault", "Belt wear — within cover", CORE_DK, "Covered")]
ry = iy + 0.7
for k, v, tc, tag in rows:
    rc = rect(s, ix + 0.3, ry, iw - 0.6, 0.6, fill=WHITE, line=SILVER, line_w=0.7, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(rc, 0.1)
    text(s, ix + 0.5, ry + 0.09, 1.6, 0.2, [para(k, size=9, color=SLATE_LT, bold=True)])
    text(s, ix + 0.5, ry + 0.28, iw - 2.6, 0.25, [para(v, size=9.5, color=INK)])
    tp = rect(s, ix + iw - 1.5, ry + 0.16, 1.1, 0.28, fill=None, line=tc, line_w=0.9, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(tp, 0.5)
    text(s, ix + iw - 1.5, ry + 0.13, 1.1, 0.28, [para(tag, size=8, color=tc, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
    ry += 0.7
confid_footer(s, pg())

# ============================================================ 12 · ASER
s = slide(prs, bg=MIST)
top = header(s, "ASER", "Activity Safety Events Register",
             "A dedicated, MOD-only register for PTE risks, incidents and near-misses that affect the delivery of training and rehabilitation.")
bullet_list(s, LM, 2.65, 5.4, [
    ("PTE risks & incidents  ", "recorded against equipment and site"),
    ("Near-misses  ", "captured before they become incidents"),
    ("Delivery impact  ", "on rehab, group and individual programmes"),
    ("Clinical & activity output  ", "the effect on training outcomes noted"),
    ("MOD-only  ", "a register built specifically for defence use"),
], size=12, glyph="\uf132")
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "mod.pulsefitness.ai/aser")
text(s, ix + 0.3, iy + 0.2, iw - 0.6, 0.3, [para("Activity Safety Events Register", size=11.5, color=NAVY, bold=True)])
list_rows(s, ix + 0.3, iy + 0.6, iw - 0.6, [
    ("Treadmill 02 — belt slip risk", "Rehab · impacts programme delivery", "Incident", RGBColor(0xC6,0x55,0x49)),
    ("Rower 01 — worn handle", "Main gym · near-miss logged", "Near-miss", RGBColor(0xD1,0x8A,0x2E)),
    ("Bike 05 — instability", "Studio · under review", "Risk", CORE_DK),
    ("Cable machine — resolved", "Strength · action closed", "Closed", RGBColor(0x1F,0x9D,0x55)),
], rh=0.66)
confid_footer(s, pg())

# ============================================================ 13 · ASER REPLACEMENT EVIDENCE
s = slide(prs, bg=WHITE)
top = header(s, "ASER — replacement evidence", "When equipment repeatedly affects delivery",
             "ASER builds a clear, defensible record where old or unreliable PTE keeps disrupting rehabilitation and training.")
# left narrative + right link to CAPEX
bullet_list(s, LM, 2.6, 5.6, [
    ("Pattern of events  ", "repeated risks and incidents on the same item"),
    ("Impact on rehab  ", "evidence of disruption to programme delivery"),
    ("Linked to the asset  ", "events tied to equipment, age and service"),
    ("Supports CAPEX review  ", "a basis for repair-or-replace decisions"),
], size=12.5)
# flow: ASER -> evidence -> CAPEX review
stages = [("\uf132", "ASER events", "Risks, incidents and near-misses recorded"),
          ("\uf1da", "Evidence", "Pattern, impact and service history combined"),
          ("\uf201", "CAPEX review", "A defensible case for replacement")]
by = 2.7
for i, (g, t, d) in enumerate(stages):
    y = by + i * 1.15
    bx = rect(s, 7.1, y, 5.4, 1.0, fill=CARD, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.09)
    icon_chip(s, 7.3, y + 0.2, g, size=0.6, gsize=17)
    text(s, 8.1, y + 0.14, 4.2, 0.3, [para(t, size=12.5, color=NAVY, bold=True)])
    text(s, 8.1, y + 0.46, 4.2, 0.4, [para(d, size=10, color=SLATE, line=1.1)])
    if i < 2:
        text(s, 9.5, y + 0.95, 0.5, 0.3, [para("\uf063", size=13, color=CORE, bold=True, font=ICON, align=PP_ALIGN.CENTER)])
confid_footer(s, pg())

# ============================================================ 14 · CAPEX REPORTING
s = slide(prs, bg=MIST)
top = header(s, "CAPEX reporting", "A clear case for equipment replacement",
             "Replacement reporting drawing on age, faults, downtime, service history, ASER evidence and condition.")
bullet_list(s, LM, 2.6, 5.3, [
    ("Age & condition  ", "identify PTE nearing end of life"),
    ("Faults & downtime  ", "quantify unreliability and lost availability"),
    ("Service history  ", "the full maintenance picture per item"),
    ("ASER evidence  ", "safety and delivery impact factored in"),
    ("Replacement case  ", "a defensible basis for investment"),
], size=12.5)
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "mod.pulsefitness.ai/reports/capex")
text(s, ix + 0.3, iy + 0.2, iw - 0.6, 0.3, [para("Replacement priority — PTE", size=11.5, color=NAVY, bold=True)])
mini_bars(s, ix + 0.35, iy + 0.65, iw - 0.7, 1.5, [3,5,6,10,12,8,4], hi=4)
text(s, ix + 0.3, iy + 2.3, iw - 0.6, 0.25, [para("Flagged for review", size=10, color=SLATE, bold=True)])
list_rows(s, ix + 0.3, iy + 2.6, iw - 0.6, [
    ("Treadmill 02 — 9 yrs", "14 faults · 3 ASER events", "Replace", RGBColor(0xC6,0x55,0x49)),
    ("Rower 01 — 7 yrs", "8 faults · rising downtime", "Review", RGBColor(0xD1,0x8A,0x2E)),
], rh=0.48)
confid_footer(s, pg())

# ============================================================ 15 · SERVICE HISTORY REPORTS
s = slide(prs, bg=WHITE)
top = header(s, "Service history reports", "The full record, on demand",
             "Authorised users can access historical service records and downtime evidence whenever needed.")
feats = [
    ("\uf1da", "Service records", "Every visit and outcome per item of PTE."),
    ("\uf05a", "Job status", "Open, in-progress and completed work."),
    ("\uf021", "Repeat faults", "Recurring issues surfaced clearly."),
    ("\uf466", "Parts used", "Components fitted, recorded against the asset."),
    ("\uf017", "Downtime evidence", "Time out of service, quantified."),
    ("\uf56d", "Exportable", "Reports available to share and retain."),
]
feature_grid(s, feats, cols=3, top=2.55, bottom=6.5, gap=0.3)
confid_footer(s, pg())

# ============================================================ 16 · COMPLIANCE & SAFETY REPORTS
s = slide(prs, bg=MIST)
top = header(s, "Compliance & safety reports", "Evidence that stands up to scrutiny",
             "Capture safety and compliance records with a complete, time-stamped trail.")
feats = [
    ("\uf0fe", "Accident reports", "Incidents recorded with the detail required."),
    ("\uf46c", "RIDDOR reports", "Support reportable incident requirements."),
    ("\uf132", "Risk assessments", "Documented and stored against sites and tasks."),
    ("\uf0ae", "Check sheets", "Routine safety checks recorded and reviewable."),
    ("\uf1da", "Audit trail", "Every entry and change logged and traceable."),
    ("\uf3ed", "Evidence storage", "Records kept together and retrievable."),
]
feature_grid(s, feats, cols=3, top=2.55, bottom=6.5, gap=0.3)
confid_footer(s, pg())

# ============================================================ 17 · PLANNED MAINTENANCE
s = slide(prs, bg=WHITE)
top = header(s, "Planned maintenance", "Keep PTE safe and available",
             "Preventative maintenance schedules, site visits and service records — planned, tracked and evidenced.")
bullet_list(s, LM, 2.7, 5.6, [
    ("PPM schedules  ", "planned maintenance across every item of PTE"),
    ("Site visits  ", "coordinated attendance for scheduled work"),
    ("Engineer reports  ", "each visit documented and stored"),
    ("Service records  ", "a continuous, auditable maintenance history"),
], size=12.5)
ix, iy, iw, ih = window_frame(s, 6.6, 2.5, 5.95, 3.9, "mod.pulsefitness.ai/ppm")
text(s, ix + 0.3, iy + 0.2, iw - 0.6, 0.3, [para("Upcoming PPM — Site A", size=12, color=NAVY, bold=True)])
list_rows(s, ix + 0.3, iy + 0.6, iw - 0.6, [
    ("Quarterly service — Cardio", "Due 24 Jul · engineer booked", "Scheduled", CORE_DK),
    ("Safety checks — Rehab suite", "Due 31 Jul", "Due soon", RGBColor(0xD1,0x8A,0x2E)),
    ("Annual service — Strength", "Completed 12 Jun", "Done", RGBColor(0x1F,0x9D,0x55)),
    ("Monthly checks — Studio", "Completed 01 Jul", "Done", RGBColor(0x1F,0x9D,0x55)),
], rh=0.66)
confid_footer(s, pg())

# ============================================================ 18 · DASHBOARDS & VISIBILITY
s = slide(prs, bg=MIST)
top = header(s, "Dashboards & visibility", "Site and multi-site oversight",
             "Clear dashboards for open faults, overdue jobs, repeat issues, equipment status and safety concerns.")
ix, iy, iw, ih = window_frame(s, LM, 2.5, 7.1, 4.0, "mod.pulsefitness.ai/dashboard")
kpw = (iw - 0.6 - 0.4) / 3
kpi_tile(s, ix + 0.3, iy + 0.2, kpw, 1.2, "8", "Open faults", "\uf071")
kpi_tile(s, ix + 0.3 + kpw + 0.2, iy + 0.2, kpw, 1.2, "2", "Overdue jobs", "\uf252", delta="1", up=False)
kpi_tile(s, ix + 0.3 + 2*(kpw+0.2), iy + 0.2, kpw, 1.2, "3", "ASER open", "\uf132")
text(s, ix + 0.3, iy + 1.6, iw-0.6, 0.25, [para("Faults by month — estate", size=9.5, color=SLATE, bold=True)])
mini_bars(s, ix + 0.35, iy + 1.95, iw - 0.7, 1.35, [9,7,6,8,5,4], ["Feb","Mar","Apr","May","Jun","Jul"], hi=5)
caps = [("\uf071","Open faults"),("\uf252","Overdue jobs"),("\uf021","Repeat issues"),
        ("\uf02b","Equipment status"),("\uf132","Safety concerns")]
cy = 2.7
for g, lab in caps:
    icon_chip(s, 8.05, cy, g, size=0.44, chip=CARD, glyph_color=CORE_DK, gsize=12)
    text(s, 8.6, cy, SW - RM - 8.6, 0.44, [para(lab, size=12, color=NAVY, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
    cy += 0.72
confid_footer(s, pg())

# ============================================================ 19 · SECURE PERMISSIONS
s = slide(prs, bg=WHITE)
top = header(s, "Secure permissions", "The right access for every role",
             "Role-based access keeps information in the right hands across sites, service teams and administration.")
roles = [("\uf508","MOD site users","Their permitted site(s) only — equipment, faults and reports."),
         ("\uf0c0","Multi-site managers","Oversight across the sites they are authorised for."),
         ("\uf0ad","Pulse service desk & engineers","Access to assigned jobs and service records."),
         ("\uf023","Administrators","Manage users, permissions and configuration.")]
cwf = (CW - 0.32) / 2
for i, (g, t, d) in enumerate(roles):
    r, c = divmod(i, 2)
    x = LM + c * (cwf + 0.32); y = 2.7 + r * 1.85
    bx = rect(s, x, y, cwf, 1.65, fill=CARD, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.07)
    icon_chip(s, x + 0.3, y + 0.3, g, size=0.62, gsize=17)
    text(s, x + 1.1, y + 0.28, cwf - 1.4, 0.55, [para(t, size=13.5, color=NAVY, bold=True, line=1.0)])
    text(s, x + 1.1, y + 0.86, cwf - 1.4, 0.7, [para(d, size=10.5, color=SLATE, line=1.2)])
confid_footer(s, pg())

# ============================================================ 20 · AUDIT TRAIL
s = slide(prs, bg=MIST)
top = header(s, "Audit trail", "Every action recorded and traceable",
             "Faults, ASER entries, reports, status changes, document uploads and service updates are all logged.")
bullet_list(s, LM, 2.7, 5.3, [
    ("Complete  ", "every material action is captured"),
    ("Attributed  ", "who did what, and when, is recorded"),
    ("Immutable  ", "the record cannot be quietly changed"),
    ("Retrievable  ", "history available for review and assurance"),
], size=12.5)
# timeline mockup
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "mod.pulsefitness.ai/equipment/TRD-002/audit")
events = [("Fault logged", "S. Jones · 14 Jul 09:32"), ("ASER entry created", "M. Owens · 14 Jul 09:40"),
          ("Engineer assigned", "Service desk · 14 Jul 10:05"), ("Part recorded", "D. Patel · 15 Jul 11:20"),
          ("Report completed", "D. Patel · 15 Jul 11:45")]
lx = ix + 0.55; ey = iy + 0.35
rect(s, lx, ey, 0.02, 3.0, fill=SILVER)
for i, (t, m) in enumerate(events):
    y = ey + i * 0.62
    dot = rect(s, lx - 0.09, y, 0.2, 0.2, fill=CORE, shape=MSO_SHAPE.OVAL)
    text(s, lx + 0.35, y - 0.05, iw - 1.2, 0.25, [para(t, size=10.5, color=NAVY, bold=True)])
    text(s, lx + 0.35, y + 0.2, iw - 1.2, 0.2, [para(m, size=8.5, color=SLATE_LT)])
confid_footer(s, pg())

# ============================================================ 21 · BENEFITS FOR MOD
s = slide(prs, bg=WHITE)
top = header(s, "Benefits for MOD", "Clearer, safer, more accountable",
             "The portal supports equipment uptime, safety and rehabilitation continuity — with the evidence to back it up.")
bens = [("\uf06e","Better visibility","One clear view of equipment, faults and safety."),
        ("\uf0e7","Faster fault reporting","Issues raised and actioned without delay."),
        ("\uf1da","Stronger service evidence","A complete, auditable service record."),
        ("\uf132","Safer PTE management","Safety events captured and acted upon."),
        ("\uf21e","Rehabilitation continuity","Less disruption to training and rehab."),
        ("\uf201","Clearer replacement case","Defensible justification for investment.")]
feature_grid(s, bens, cols=3, top=2.55, bottom=6.5, gap=0.3)
confid_footer(s, pg())

# ============================================================ 22 · TENDER SUMMARY
s = slide(prs, bg=MIST)
top = header(s, "Tender summary", "A structured, auditable MOD-focused portal",
             "Pulsefitness.ai supports equipment uptime, safety, service delivery and long-term asset planning.")
pillars = [("\uf3ed","Secure & permission-controlled","Site-scoped access with role-based permissions and a full audit trail."),
           ("\uf132","Safety-focused","ASER and compliance reporting built around MOD requirements."),
           ("\uf201","Evidence-led planning","Service history and ASER combined into a defensible replacement case.")]
cwf = (CW - 2 * 0.4) / 3
for i, (g, t, d) in enumerate(pillars):
    x = LM + i * (cwf + 0.4)
    bx = rect(s, x, 2.8, cwf, 3.15, fill=WHITE, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(bx, 0.05)
    icon_chip(s, x + 0.35, 3.15, g, size=0.8, gsize=22)
    text(s, x + 0.35, 4.2, cwf - 0.7, 0.8, [para(t, size=15, color=NAVY, bold=True, line=1.08)])
    text(s, x + 0.35, 5.15, cwf - 0.7, 0.8, [para(d, size=11, color=SLATE, line=1.3)])
confid_footer(s, pg())

# ============================================================ 23 · FINAL
s = slide(prs, bg=MOD_NAVY)
rect(s, 0, 0, SW, 0.09, fill=CORE)
pic = s.shapes.add_picture(ASSETS + "mark.png", Inches(10.4), Inches(0.75), Inches(2.3), Inches(2.3))
logo(s, dark_bg=True, x=LM, y=0.7, w=2.5)
text(s, LM, 2.75, 10.0, 1.6,
     [para("Pulsefitness.ai MOD Service Portal", size=33, color=WHITE, bold=True, line=1.05)])
text(s, LM, 3.75, 9.5, 1.0,
     [para("Built to support safer, clearer and more accountable PTE management.",
           size=17, color=CORE, bold=True, line=1.2)])
text(s, LM, 4.85, 8.8, 0.8,
     [para("We would welcome the opportunity to demonstrate the portal against your sites, "
           "equipment and service requirements.", size=14, color=RGBColor(0xB2,0xC3,0xCB), line=1.35)])
chips = [("\uf073","Arrange a demonstration"),("\uf0ac","pulsefitness.ai"),("\uf0e0","Contact the Pulse team")]
for i, (g, lab) in enumerate(chips):
    x = LM + i * 3.9
    bx = rect(s, x, 5.95, 3.6, 0.7, fill=RGBColor(0x12,0x2C,0x37), line=RGBColor(0x27,0x40,0x4A), line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(bx, 0.5)
    icon_chip(s, x + 0.18, 6.07, g, size=0.46, chip=CORE, glyph_color=INK, gsize=13)
    text(s, x + 0.8, 5.95, 2.7, 0.7, [para(lab, size=11.5, color=WHITE, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
text(s, LM, 7.05, 6.0, 0.3, [para("Commercial in Confidence", size=9, color=SLATE_LT, bold=True)])

prs.save("/app/decks/Pulsefitness_MOD_Service_Portal_Tender.pptx")
print("MOD deck saved —", PAGE[0] + 1, "slides")
