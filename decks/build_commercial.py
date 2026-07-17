"""Deck 1 (v2) — Pulsefitness.ai for Commercial Customers (front-of-house, screenshot-led)."""
import sys
sys.path.insert(0, "/app/decks")
from pulse_deck import *
from pulse_deck import _round_radius, _soft_shadow, _set_latin, _set_alpha
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

prs = new_prs()
PAGE = [0]
def pg():
    PAGE[0] += 1
    return PAGE[0]

A = ASSETS

# ============================================================ 1 · TITLE
s = slide(prs, bg=DARKBG)
image_panel(s, A + "pulse_gym.jpg", 8.15, 0, SW - 8.15, SH, overlay=0x0B1D26, alpha=42)
rect(s, 8.15, 0, 0.03, SH, fill=CORE)
rect(s, 0, 0, SW, 0.09, fill=CORE)
logo(s, dark_bg=True, x=LM, y=0.62, w=2.6)
text(s, LM, 2.55, 7.4, 0.4, [para("THE CONNECTED OPERATIONS PLATFORM", size=12.5, color=CORE, bold=True)])
text(s, LM, 3.0, 7.6, 2.0,
     [para("Your equipment,", size=41, color=WHITE, bold=True, line=1.02),
      para("faults and history —", size=41, color=WHITE, bold=True, line=1.02),
      para("in one clear portal.", size=41, color=CORE, bold=True, line=1.02)])
text(s, LM, 5.35, 6.9, 1.0,
     [para("Log faults, track equipment, request parts and see your whole estate at a glance — "
           "purpose-built for fitness facilities.", size=14, color=RGBColor(0xC2,0xCF,0xD6), line=1.35)])
rect(s, LM, 6.55, 3.0, 0.02, fill=RGBColor(0x2E,0x3A,0x40))
text(s, LM, 6.72, 7.5, 0.4,
     [para([{'text': "pulsefitness.ai", 'size': 12, 'color': WHITE, 'bold': True},
            {'text': "     Built by fitness equipment and service specialists", 'size': 11.5,
             'color': SLATE_LT}])])

# ============================================================ 2 · THE PROBLEM
s = slide(prs, bg=MIST)
header(s, "The challenge", "Too much runs through disconnected tools",
       "Equipment, faults and history end up spread across inboxes, spreadsheets and messages — so nothing is truly visible.")
text(s, LM, 2.6, 5.5, 1.4,
     [para("When information lives in separate places, jobs get missed, response slips, and it's "
           "hard to prove what happened to a machine and when.", size=13.5, color=INK, line=1.4)])
bullet_list(s, LM, 4.2, 5.5, [
    ("No single record  ", "history scattered across people and systems"),
    ("Slow fault handling  ", "logged by phone or message, easily lost"),
    ("Weak reporting  ", "downtime and repeat faults hard to evidence"),
    ("No audit trail  ", "limited visibility for managers and owners"),
], size=12.5, glyph="\uf071", glyph_color=RGBColor(0xD1,0x5B,0x4E))
frags = [("\uf0e0","Email threads"),("\uf1c3","Spreadsheets"),("\uf232","WhatsApp"),
         ("\uf095","Phone calls"),("\uf15c","Paper notes"),("\uf07b","Local files")]
cw2, ch2, gp, fx = 2.55, 0.92, 0.22, 7.0
for i,(g,lab) in enumerate(frags):
    r,c = divmod(i,2); x=fx+c*(cw2+gp); y=2.6+r*(ch2+gp)
    bx=rect(s,x,y,cw2,ch2,fill=WHITE,line=SILVER,line_w=1.0,shape=MSO_SHAPE.ROUNDED_RECTANGLE,shadow=True);_round_radius(bx,0.12)
    icon_chip(s,x+0.18,y+ch2/2-0.22,g,size=0.44,chip=RGBColor(0xEE,0xF3,0xF6),glyph_color=SLATE,gsize=13)
    text(s,x+0.76,y,cw2-0.8,ch2,[para(lab,size=11.5,color=NAVY,bold=True)],anchor=MSO_ANCHOR.MIDDLE)
footer(s, pg())

# ============================================================ 3 · THE SOLUTION
s = slide(prs, bg=WHITE)
header(s, "The platform", "One connected portal for your facility",
       "Pulsefitness.ai brings equipment, faults, parts, compliance and reporting into a single place your team actually uses.")
shot(s, A + "shot_overview.jpg", 6.15, 2.5, 6.45, label="Operations dashboard")
bullet_list(s, LM, 2.7, 5.0, [
    ("A live health score  ", "see how your estate is performing at a glance"),
    ("Everything linked  ", "faults and parts sit against the right machine"),
    ("One or many sites  ", "switch between locations in a click"),
    ("Full history  ", "every action recorded and easy to retrieve"),
], size=12.5)
footer(s, pg())

# ============================================================ 4 · ASSET MANAGEMENT
s = slide(prs, bg=MIST)
header(s, "Asset management", "Every machine has a complete record",
       "A reliable source of truth for each item of Pulse Fitness equipment across all of your sites.")
shot(s, A + "shot_equipment.jpg", 6.15, 2.5, 6.45, label="Equipment register")
bullet_list(s, LM, 2.7, 5.0, [
    ("Make, model & serial  ", "each machine identified precisely"),
    ("Warranty at a glance  ", "cover status shown on every item"),
    ("Photos & location  ", "know exactly what it is and where"),
    ("Service history  ", "faults, visits and parts on the record"),
], size=12.5)
footer(s, pg())

# ============================================================ 5 · FAULT LOGGING
s = slide(prs, bg=WHITE)
header(s, "Fault logging", "Report faults against the right machine",
       "Structured fault capture means issues are clear, tracked and never lost in a message thread.")
shot(s, A + "shot_faults.jpg", 6.15, 2.5, 6.45, label="Reactive faults")
bullet_list(s, LM, 2.7, 5.0, [
    ("Linked to equipment  ", "every fault against the correct asset"),
    ("Priority & status  ", "flag out-of-service machines and urgency"),
    ("Photos & notes  ", "evidence so the fix arrives prepared"),
    ("Tracked to resolution  ", "a clear trail from reported to resolved"),
], size=12.5)
footer(s, pg())

# ============================================================ 6 · REQUEST PARTS
s = slide(prs, bg=MIST)
header(s, "Request parts", "Order the right part, first time",
       "Part requests are tied to the exact machine, with drawings and photos to remove the guesswork.")
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "portal.pulsefitness.ai/request-a-part")
text(s, ix+0.3, iy+0.2, iw-0.6, 0.3, [para("Request a part — Pulse 260G Treadmill", size=11.5, color=NAVY, bold=True)])
dg = rect(s, ix+0.3, iy+0.6, 2.7, 2.55, fill=CARD, line=SILVER, line_w=1, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(dg, 0.05)
text(s, ix+0.3, iy+0.6, 2.7, 0.3, [para("Exploded drawing", size=8.5, color=SLATE_LT, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
import random; random.seed(7)
for n in range(6):
    cx = ix+0.55+random.random()*2.1; cy = iy+1.0+random.random()*2.0
    rect(s, cx, cy, 0.34, 0.34, fill=CORE, shape=MSO_SHAPE.OVAL)
    text(s, cx, cy-0.02, 0.34, 0.34, [para(str(n+1), size=8, color=INK, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
rows=[("Drive belt","#3 · in warranty",RGBColor(0x1F,0x9D,0x55)),("Console board","#5 · chargeable",SLATE),("Roller kit","#2 · in warranty",RGBColor(0x1F,0x9D,0x55))]
ry=iy+0.6
for t,m,c in rows:
    rc=rect(s, ix+3.2, ry, iw-3.5, 0.62, fill=WHITE, line=SILVER, line_w=0.7, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(rc,0.12)
    rect(s, ix+3.2, ry, 0.05, 0.62, fill=c)
    text(s, ix+3.4, ry+0.09, iw-3.9, 0.22, [para(t, size=9.5, color=NAVY, bold=True)])
    text(s, ix+3.4, ry+0.31, iw-3.9, 0.2, [para(m, size=8, color=SLATE_LT)])
    ry+=0.72
sb=rect(s, ix+3.2, ry+0.02, iw-3.5, 0.42, fill=CORE, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(sb,0.3)
text(s, ix+3.2, ry, iw-3.5, 0.42, [para("Submit to Pulse Fitness", size=9, color=INK, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
bullet_list(s, LM, 2.7, 5.0, [
    ("Against the machine  ", "requests tied to the exact asset & serial"),
    ("Exploded drawings  ", "pick the correct part from a diagram"),
    ("Warranty visibility  ", "see cover before you request"),
    ("Straight to Pulse  ", "submitted directly to our team"),
], size=12.5)
footer(s, pg())

# ============================================================ 7 · CONTRACTS & WARRANTY
s = slide(prs, bg=WHITE)
header(s, "Contracts & warranty", "Know what's covered before work begins",
       "Warranty, contract cover, exclusions and chargeable status — all visible against the equipment.")
ix, iy, iw, ih = window_frame(s, 6.5, 2.5, 6.1, 3.95, "portal.pulsefitness.ai/equipment/PF-TM-260-01/cover")
text(s, ix+0.3, iy+0.22, iw-0.6, 0.3, [para("Cover summary — Pulse 260G Treadmill", size=12, color=NAVY, bold=True)])
rows=[("Contract","Comprehensive · Riverside estate",RGBColor(0x1F,0x9D,0x55),"Active"),
      ("Warranty","Parts & labour · exp 03/2027",RGBColor(0x1F,0x9D,0x55),"Active"),
      ("Exclusions","Consumables · accidental damage",SLATE,"Noted"),
      ("This request","Drive belt — within cover",CORE_DK,"Covered")]
ry=iy+0.7
for k,v,tc,tag in rows:
    rc=rect(s, ix+0.3, ry, iw-0.6, 0.6, fill=WHITE, line=SILVER, line_w=0.7, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(rc,0.1)
    text(s, ix+0.5, ry+0.09, 1.7, 0.2, [para(k, size=9, color=SLATE_LT, bold=True)])
    text(s, ix+0.5, ry+0.28, iw-2.7, 0.25, [para(v, size=9.5, color=INK)])
    tp=rect(s, ix+iw-1.5, ry+0.16, 1.1, 0.28, fill=None, line=tc, line_w=0.9, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(tp,0.5)
    text(s, ix+iw-1.5, ry+0.13, 1.1, 0.28, [para(tag, size=8, color=tc, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
    ry+=0.7
bullet_list(s, LM, 2.7, 5.0, [
    ("Warranty  ", "active cover and expiry dates at a glance"),
    ("Contract cover  ", "the agreement in place for each site"),
    ("Exclusions  ", "what falls outside cover, clearly shown"),
    ("Chargeable decisions  ", "confident, evidenced calls on billing"),
], size=12.5)
footer(s, pg())

# ============================================================ 8 · SAFETY & COMPLIANCE
s = slide(prs, bg=MIST)
header(s, "Safety & compliance", "Routine checks and records, done properly",
       "Daily check sheets, risk assessments and incident records — with a complete, time-stamped trail.")
shot(s, A + "shot_checksheets.jpg", 6.15, 2.5, 6.45, label="Check sheets")
bullet_list(s, LM, 2.7, 5.0, [
    ("Daily check sheets  ", "per-machine safety checks, quick to complete"),
    ("Accident & RIDDOR  ", "incident records captured and stored"),
    ("Risk assessments  ", "documented against sites and tasks"),
    ("Audit trail  ", "every entry logged and easy to evidence"),
], size=12.5)
footer(s, pg())

# ============================================================ 9 · DOCUMENTS & KNOWLEDGE
s = slide(prs, bg=WHITE)
header(s, "Documents & manuals", "Every manual, certificate and contract in reach",
       "Keep equipment documentation together — and ask questions of it in plain English.")
shot(s, A + "shot_documents.jpg", 6.15, 2.5, 6.45, label="Documents")
bullet_list(s, LM, 2.7, 5.0, [
    ("Manuals & guides  ", "technical docs stored against the estate"),
    ("Certificates & contracts  ", "organised and quick to find"),
    ("Ask your documents  ", "get answers from your manuals instantly"),
    ("Always to hand  ", "the right document at the machine"),
], size=12.5)
footer(s, pg())

# ============================================================ 10 · REPORTS & DASHBOARDS
s = slide(prs, bg=MIST)
header(s, "Reports & dashboards", "The numbers that run your operation",
       "Clear reporting across faults, response times, downtime, availability and safety performance.")
shot(s, A + "shot_reports.jpg", 6.15, 2.5, 6.45, label="Performance KPIs")
bullet_list(s, LM, 2.7, 5.0, [
    ("Availability & downtime  ", "see equipment uptime across the estate"),
    ("Response times  ", "how quickly faults are actioned"),
    ("Repeat issues  ", "surface the machines that keep breaking"),
    ("Safety performance  ", "SLA and incident visibility"),
], size=12.5)
footer(s, pg())

# ============================================================ 11 · CAPEX
s = slide(prs, bg=WHITE)
header(s, "CAPEX reporting", "Build the evidence for replacement",
       "Turn service history into a clear, defensible case for repairing or replacing ageing equipment.")
shot(s, A + "shot_capex.jpg", 6.15, 2.5, 6.45, label="CAPEX intelligence")
bullet_list(s, LM, 2.7, 5.0, [
    ("Age & condition  ", "identify equipment nearing end of life"),
    ("Faults & downtime  ", "quantify unreliability and its impact"),
    ("Replacement spend  ", "forecast the year ahead with confidence"),
    ("Board-ready report  ", "a clear case for capital investment"),
], size=12.5)
footer(s, pg())

# ============================================================ 12 · ONBOARDING
s = slide(prs, bg=MIST)
header(s, "Onboarding", "Add your equipment quickly — two ways",
       "Import by spreadsheet, or photograph a machine and let Pulse draft the record for your review.")
steps=[("\uf574","Upload","Add equipment by spreadsheet, or photograph the machine and data plate."),
       ("\uf0eb","Extract","Pulse reads make, model and serial and drafts the asset record."),
       ("\uf46c","Review & confirm","Your team checks the detail and approves it into the register.")]
cwf=(CW-2*0.9)/3
for i,(g,t,d) in enumerate(steps):
    x=LM+i*(cwf+0.9)
    bx=rect(s,x,2.85,cwf,2.4,fill=WHITE,line=SILVER,line_w=1.0,shape=MSO_SHAPE.ROUNDED_RECTANGLE,shadow=True);_round_radius(bx,0.06)
    rect(s,x,2.85,cwf,0.09,fill=CORE)
    text(s,x+0.3,3.08,1.5,0.4,[para(f"0{i+1}",size=22,color=RGBColor(0xC9,0xD6,0xDC),bold=True)])
    icon_chip(s,x+cwf-0.9,3.1,g,size=0.6,gsize=17)
    text(s,x+0.3,3.8,cwf-0.6,0.35,[para(t,size=15,color=NAVY,bold=True)])
    text(s,x+0.3,4.22,cwf-0.6,0.9,[para(d,size=11,color=SLATE,line=1.25)])
    if i<2: text(s,x+cwf+0.2,3.8,0.5,0.5,[para("\uf061",size=16,color=CORE,bold=True,font=ICON,align=PP_ALIGN.CENTER)])
nb=rect(s,LM,5.5,CW,0.95,fill=DARKBG_2,shape=MSO_SHAPE.ROUNDED_RECTANGLE);_round_radius(nb,0.07)
rect(s,LM,5.5,0.1,0.95,fill=CORE)
text(s,LM+0.4,5.72,CW-0.8,0.6,[para([{'text':"Nothing is added automatically.  ",'size':11.5,'color':WHITE,'bold':True},{'text':"AI drafts the record; your team always reviews and confirms first.",'size':11.5,'color':RGBColor(0xC4,0xD2,0xD9)}])],anchor=MSO_ANCHOR.MIDDLE)
footer(s, pg())

# ============================================================ 13 · AI SUPPORT
s = slide(prs, bg=WHITE)
header(s, "AI support", "Practical help, with people in control",
       "AI assists your team with the routine — from reading manuals to building replacement cases — but never decides on its own.")
feats=[("\uf0fa","Ask your documents","Plain-English answers pulled from your manuals."),
       ("\uf0eb","Fault triage","Likely causes and next steps suggested for a fault."),
       ("\uf201","CAPEX evidence","Assembles the case for repair or replacement."),
       ("\uf00c","Onboarding checks","Reads data plates and pre-fills records for review."),
       ("\uf0ae","Summaries","Condenses long histories into a clear picture."),
       ("\uf15c","Report drafting","Helps produce clear, consistent reports.")]
feature_grid(s, feats, cols=3, top=2.55, bottom=6.5, gap=0.3)
footer(s, pg())

# ============================================================ 14 · WHY PULSE
s = slide(prs, bg=MIST)
header(s, "Why Pulsefitness.ai", "Built for real operational problems",
       "Not another disconnected tool — a platform shaped by people who service fitness equipment for a living.")
pillars=[("\uf0c1","One connected platform","Equipment, faults, parts, compliance and reporting in one joined-up system."),
         ("\uf0ad","Built by specialists","Designed by fitness equipment and service experts who know the work."),
         ("\uf058","Designed for the day-to-day","Focused on the practical problems facilities face, every single day.")]
cwf=(CW-2*0.4)/3
for i,(g,t,d) in enumerate(pillars):
    x=LM+i*(cwf+0.4)
    bx=rect(s,x,2.85,cwf,3.15,fill=WHITE,line=SILVER,line_w=1.0,shape=MSO_SHAPE.ROUNDED_RECTANGLE,shadow=True);_round_radius(bx,0.05)
    icon_chip(s,x+0.35,3.2,g,size=0.8,gsize=22)
    text(s,x+0.35,4.25,cwf-0.7,0.7,[para(t,size=16,color=NAVY,bold=True,line=1.05)])
    text(s,x+0.35,5.15,cwf-0.7,0.9,[para(d,size=11.5,color=SLATE,line=1.3)])
footer(s, pg())

# ============================================================ 15 · IDEAL CUSTOMERS
s = slide(prs, bg=WHITE)
header(s, "Who it's for", "Built for the whole sector",
       "From a single independent gym to national multi-site operators.")
customers=[("\uf44b","Commercial gyms"),("\uf1ad","Multi-site operators"),("\uf0c0","Leisure trusts"),
           ("\uf19c","Councils"),("\uf549","Universities"),("\uf236","Hotels"),
           ("\uf3c5","Studios"),("\uf19d","Colleges")]
cwf=(CW-3*0.3)/4
for i,(g,lab) in enumerate(customers):
    r,c=divmod(i,4); x=LM+c*(cwf+0.3); y=2.75+r*(1.55+0.35)
    bx=rect(s,x,y,cwf,1.55,fill=CARD,line=SILVER,line_w=1.0,shape=MSO_SHAPE.ROUNDED_RECTANGLE,shadow=True);_round_radius(bx,0.08)
    icon_chip(s,x+cwf/2-0.32,y+0.28,g,size=0.64,gsize=18)
    text(s,x+0.15,y+1.02,cwf-0.3,0.4,[para(lab,size=12,color=NAVY,bold=True,align=PP_ALIGN.CENTER,line=1.05)])
footer(s, pg())

# ============================================================ 16 · CTA
s = slide(prs, bg=DARKBG)
image_panel(s, A + "pulse_strength.jpg", 8.15, 0, SW - 8.15, SH, overlay=0x0B1D26, alpha=48)
rect(s, 8.15, 0, 0.03, SH, fill=CORE)
rect(s, 0, 0, SW, 0.09, fill=CORE)
logo(s, dark_bg=True, x=LM, y=0.7, w=2.5)
text(s, LM, 2.75, 7.2, 1.6,
     [para("See it working", size=41, color=WHITE, bold=True, line=1.03),
      para("for your facility.", size=41, color=CORE, bold=True, line=1.03)])
text(s, LM, 4.55, 6.9, 0.9,
     [para("Arrange a walkthrough and we'll show you the platform against your own equipment, "
           "sites and service setup.", size=14.5, color=RGBColor(0xC2,0xCF,0xD6), line=1.35)])
chips=[("\uf073","Book a demo"),("\uf0ac","pulsefitness.ai"),("\uf0e0","Talk to our team")]
for i,(g,lab) in enumerate(chips):
    x=LM+i*2.45
    bx=rect(s,x,5.9,2.25,0.7,fill=RGBColor(0x18,0x30,0x3C),line=RGBColor(0x2C,0x44,0x4E),line_w=1.0,shape=MSO_SHAPE.ROUNDED_RECTANGLE);_round_radius(bx,0.5)
    icon_chip(s,x+0.16,6.02,g,size=0.46,chip=CORE,glyph_color=INK,gsize=12)
    text(s,x+0.72,5.9,1.5,0.7,[para(lab,size=10.5,color=WHITE,bold=True)],anchor=MSO_ANCHOR.MIDDLE)

prs.save("/app/decks/Pulsefitness_Commercial_Presentation.pptx")
print("Commercial deck v2 saved —", len(prs.slides._sldIdLst), "slides")
