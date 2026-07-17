"""Pulse Fitness — premium deck building toolkit (python-pptx).
Brand: Core Blue #19CDFF, Soft Black #1B1C1D, navy/grey text, Proxima Nova.
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.oxml.ns import qn
import copy

# ---------- palette ----------
CORE      = RGBColor(0x19, 0xCD, 0xFF)   # Core Blue (accent)
CORE_DK   = RGBColor(0x0B, 0x7A, 0x9E)   # deep cyan (accessible text on light)
NAVY      = RGBColor(0x11, 0x2A, 0x38)   # dark blue-grey (headings)
INK       = RGBColor(0x1B, 0x1C, 0x1D)   # soft black
SLATE     = RGBColor(0x5C, 0x66, 0x6B)   # secondary text
SLATE_LT  = RGBColor(0x8A, 0x93, 0x97)
SILVER    = RGBColor(0xDD, 0xE5, 0xEA)   # borders
CARD      = RGBColor(0xF4, 0xF9, 0xFB)   # light card fill
CARD_2    = RGBColor(0xEC, 0xF6, 0xFA)
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
DARKBG    = RGBColor(0x14, 0x17, 0x19)   # near soft-black for dark slides
DARKBG_2  = RGBColor(0x0E, 0x2A, 0x36)   # deep teal-navy panel
MIST      = RGBColor(0xF7, 0xFA, 0xFC)   # page tint

FONT  = "Proxima Nova"
ICON  = "Font Awesome 6 Free"

ASSETS = "/app/decks/assets/"

# slide geometry (16:9)
SW, SH = 13.333, 7.5
LM, RM = 0.75, 0.75
CW = SW - LM - RM  # content width


def new_prs():
    prs = Presentation()
    prs.slide_width  = Inches(SW)
    prs.slide_height = Inches(SH)
    return prs


def slide(prs, bg=WHITE):
    s = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    if bg is not None:
        fill_bg(s, bg)
    return s


def fill_bg(s, color):
    r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(SW), Inches(SH))
    r.fill.solid(); r.fill.fore_color.rgb = color
    r.line.fill.background()
    r.shadow.inherit = False
    # send to back
    sp = r._element
    sp.getparent().remove(sp)
    s.shapes._spTree.insert(2, sp)
    return r


def rect(s, x, y, w, h, fill=None, line=None, line_w=1.0, shape=MSO_SHAPE.RECTANGLE, shadow=False):
    sh = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid(); sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line; sh.line.width = Pt(line_w)
    sh.shadow.inherit = False
    if shadow:
        _soft_shadow(sh)
    return sh


def _round_radius(sh, frac):
    """Set corner radius on a rounded rectangle (frac of shorter side)."""
    try:
        sh.adjustments[0] = frac
    except Exception:
        pass


def _soft_shadow(sh):
    spPr = sh._element.spPr
    # remove existing effectLst
    for tag in ('a:effectLst',):
        for e in spPr.findall(qn(tag)):
            spPr.remove(e)
    el = spPr.makeelement(qn('a:effectLst'), {})
    sh_el = el.makeelement(qn('a:outerShdw'), {
        'blurRad': '90000', 'dist': '38000', 'dir': '5400000', 'rotWithShape': '0'})
    clr = sh_el.makeelement(qn('a:srgbClr'), {'val': '11324A'})
    alpha = clr.makeelement(qn('a:alpha'), {'val': '22000'})
    clr.append(alpha); sh_el.append(clr); el.append(sh_el)
    spPr.append(el)


def text(s, x, y, w, h, paras, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, wrap=True):
    """paras: list of dicts -> {text, size, color, bold, font, spacing_after, line, space_before, align}"""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = p.get('align', align)
        if p.get('space_before') is not None:
            para.space_before = Pt(p['space_before'])
        para.space_after = Pt(p.get('spacing_after', 0))
        if p.get('line'):
            para.line_spacing = p['line']
        segs = p['text'] if isinstance(p['text'], list) else [p]
        for seg in segs:
            run = para.add_run()
            run.text = seg.get('text', p.get('text') if not isinstance(p['text'], list) else '')
            run.font.name = seg.get('font', p.get('font', FONT))
            run.font.size = Pt(seg.get('size', p.get('size', 14)))
            run.font.bold = seg.get('bold', p.get('bold', False))
            run.font.color.rgb = seg.get('color', p.get('color', INK))
            _set_latin(run, seg.get('font', p.get('font', FONT)))
    return tb


def _set_latin(run, name):
    rPr = run._r.get_or_add_rPr()
    for tag in ('a:latin', 'a:cs'):
        e = rPr.find(qn(tag))
        if e is None:
            e = rPr.makeelement(qn(tag), {})
            rPr.append(e)
        e.set('typeface', name)


def para(txt, size=14, color=INK, bold=False, font=FONT, spacing_after=0,
         line=None, space_before=None, align=None):
    d = dict(text=txt, size=size, color=color, bold=bold, font=font,
             spacing_after=spacing_after)
    if line: d['line'] = line
    if space_before is not None: d['space_before'] = space_before
    if align is not None: d['align'] = align
    return d


# ---------- composite elements ----------

def logo(s, dark_bg=False, x=LM, y=0.42, w=2.15):
    img = ASSETS + ("logo_light.png" if dark_bg else "logo_dark.png")
    h = w * (259 / 1200.0)
    s.shapes.add_picture(img, Inches(x), Inches(y), Inches(w), Inches(h))


def kicker_line(s, kicker, x=LM, y=0.62):
    # small core-blue tick + uppercase kicker
    rect(s, x, y + 0.02, 0.32, 0.055, fill=CORE)
    text(s, x + 0.42, y - 0.11, 6.0, 0.35,
         [para(kicker.upper(), size=11.5, color=CORE_DK, bold=True)])


def header(s, kicker, title, subtitle=None, title_size=30):
    kicker_line(s, kicker, x=LM, y=0.64)
    text(s, LM, 0.92, CW, 0.9,
         [para(title, size=title_size, color=NAVY, bold=True, line=1.02)])
    ty = 1.62
    if subtitle:
        text(s, LM, ty, CW - 1.0, 0.7,
             [para(subtitle, size=13.5, color=SLATE, line=1.15)])
    return 2.35  # content top


def footer(s, page_no, note="pulsefitness.ai", dark=False):
    y = 7.06
    line_c = SILVER if not dark else RGBColor(0x2A, 0x33, 0x38)
    txt_c = SLATE_LT if not dark else RGBColor(0x7C, 0x88, 0x8D)
    rect(s, LM, y - 0.04, CW, 0.014, fill=line_c)
    text(s, LM, y, 5.0, 0.3, [para(note, size=9, color=txt_c, bold=True)])
    text(s, SW - RM - 3.0, y, 3.0, 0.3,
         [para(str(page_no), size=9, color=txt_c, bold=True, align=PP_ALIGN.RIGHT)])


def confid_footer(s, page_no):
    y = 7.06
    rect(s, LM, y - 0.04, CW, 0.014, fill=SILVER)
    text(s, LM, y, 6.0, 0.3, [para("Pulse Fitness  ·  Commercial in Confidence",
                                    size=9, color=SLATE_LT, bold=True)])
    text(s, SW - RM - 3.0, y, 3.0, 0.3,
         [para(str(page_no), size=9, color=SLATE_LT, bold=True, align=PP_ALIGN.RIGHT)])


def icon_chip(s, x, y, glyph, size=0.62, chip=CORE, glyph_color=WHITE, gsize=17):
    c = rect(s, x, y, size, size, fill=chip, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    _round_radius(c, 0.28)
    tb = text(s, x, y, size, size, [para(glyph, size=gsize, color=glyph_color,
              bold=True, font=ICON, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
    return c


def feature_grid(s, items, cols=3, top=2.35, bottom=6.85, gap=0.32,
                 icon_glyphs=None, card=True, left=LM, width=CW):
    """items: list of (glyph, title, desc)."""
    n = len(items)
    rows = (n + cols - 1) // cols
    cw = (width - gap * (cols - 1)) / cols
    ch = (bottom - top - gap * (rows - 1)) / rows
    for i, (glyph, title, desc) in enumerate(items):
        r, cidx = divmod(i, cols)
        x = left + cidx * (cw + gap)
        y = top + r * (ch + gap)
        if card:
            bx = rect(s, x, y, cw, ch, fill=CARD, line=SILVER, line_w=1.0,
                      shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True)
            _round_radius(bx, 0.055)
        pad = 0.26
        icon_chip(s, x + pad, y + pad, glyph, size=0.58, gsize=16)
        text(s, x + pad, y + pad + 0.72, cw - 2 * pad, 0.4,
             [para(title, size=13.5, color=NAVY, bold=True, line=1.0)])
        text(s, x + pad, y + pad + 1.14, cw - 2 * pad, ch - (pad + 1.14) - 0.12,
             [para(desc, size=10.5, color=SLATE, line=1.14)])


def stat_row(s, stats, top=2.35, gap=0.32, h=1.35):
    """stats: list of (big, label). Rounded cards."""
    n = len(stats)
    cw = (CW - gap * (n - 1)) / n
    for i, (big, label) in enumerate(stats):
        x = LM + i * (cw + gap)
        bx = rect(s, x, top, cw, h, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True)
        _round_radius(bx, 0.09)
        rect(s, x, top, 0.09, h, fill=CORE)
        text(s, x + 0.32, top + 0.18, cw - 0.5, 0.6,
             [para(big, size=30, color=CORE, bold=True)])
        text(s, x + 0.34, top + 0.86, cw - 0.5, 0.4,
             [para(label, size=11, color=WHITE, bold=True, line=1.05)])


def bullet_list(s, x, y, w, items, size=12.5, color=INK, gap=10, glyph="\uf058",
                glyph_color=CORE_DK, bold_lead=False):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(1))
    tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = 0; tf.margin_top = 0; tf.margin_right = 0
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap); p.line_spacing = 1.12
        r0 = p.add_run(); r0.text = glyph + "  "
        r0.font.name = ICON; r0.font.size = Pt(size - 1.5)
        r0.font.color.rgb = glyph_color; r0.font.bold = True
        _set_latin(r0, ICON)
        if isinstance(it, tuple):
            lead, rest = it
            r1 = p.add_run(); r1.text = lead
            r1.font.name = FONT; r1.font.size = Pt(size); r1.font.bold = True
            r1.font.color.rgb = NAVY; _set_latin(r1, FONT)
            r2 = p.add_run(); r2.text = rest
            r2.font.name = FONT; r2.font.size = Pt(size); r2.font.color.rgb = color
            _set_latin(r2, FONT)
        else:
            r1 = p.add_run(); r1.text = it
            r1.font.name = FONT; r1.font.size = Pt(size); r1.font.color.rgb = color
            _set_latin(r1, FONT)
    return tb


def picture_cover(s, img, x, y, w, h, radius=0.04):
    """Add a picture cropped to fill x,y,w,h (center-crop)."""
    from PIL import Image
    iw, ih = Image.open(img).size
    tgt = w / h
    src = iw / ih
    pic = s.shapes.add_picture(img, Inches(x), Inches(y), Inches(w), Inches(h))
    if src > tgt:  # image wider -> crop left/right
        crop = (1 - tgt / src) / 2
        pic.crop_left = crop; pic.crop_right = crop
    else:          # taller -> crop top/bottom
        crop = (1 - src / tgt) / 2
        pic.crop_top = crop; pic.crop_bottom = crop
    return pic


def rounded_image(s, img, x, y, w, h):
    """Image with a subtle rounded frame overlay (border)."""
    picture_cover(s, img, x, y, w, h)
    fr = rect(s, x, y, w, h, fill=None, line=WHITE, line_w=3, shape=MSO_SHAPE.RECTANGLE)
    return fr


# ---------- UI mockups (drawn as vector shapes) ----------

def window_frame(s, x, y, w, h, title="pulsefitness.ai", accent=CORE):
    """Browser-style window. Returns (inner_x, inner_y, inner_w, inner_h)."""
    card = rect(s, x, y, w, h, fill=WHITE, line=SILVER, line_w=1.0,
                shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True)
    _round_radius(card, 0.035)
    bar_h = 0.42
    bar = rect(s, x, y, w, bar_h, fill=RGBColor(0xF1, 0xF5, 0xF8),
               shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    _round_radius(bar, 0.12)
    rect(s, x, y + bar_h/2, w, bar_h/2, fill=RGBColor(0xF1, 0xF5, 0xF8))
    for i, c in enumerate([RGBColor(0xE0,0x6C,0x60), RGBColor(0xF2,0xC0,0x4E), RGBColor(0x60,0xC0,0x6A)]):
        rect(s, x + 0.22 + i * 0.22, y + bar_h/2 - 0.055, 0.11, 0.11, fill=c,
             shape=MSO_SHAPE.OVAL)
    # url pill
    pill = rect(s, x + 1.05, y + 0.09, w - 1.6, bar_h - 0.18, fill=WHITE, line=SILVER,
                line_w=0.75, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    _round_radius(pill, 0.5)
    text(s, x + 1.25, y + 0.085, w - 1.9, bar_h - 0.16,
         [para(title, size=9, color=SLATE, align=PP_ALIGN.LEFT)], anchor=MSO_ANCHOR.MIDDLE)
    return x, y + bar_h, w, h - bar_h


def sidebar(s, x, y, w, h, items, active=0):
    rect(s, x, y, w, h, fill=NAVY)
    # brand mark
    s.shapes.add_picture(ASSETS + "mark.png", Inches(x + 0.22), Inches(y + 0.2),
                         Inches(0.3), Inches(0.3))
    text(s, x + 0.58, y + 0.19, w - 0.6, 0.32,
         [para("Pulse", size=11, color=WHITE, bold=True)], anchor=MSO_ANCHOR.MIDDLE)
    iy = y + 0.75
    for i, it in enumerate(items):
        if i == active:
            hl = rect(s, x + 0.12, iy - 0.04, w - 0.24, 0.34, fill=RGBColor(0x1D,0x3E,0x4E),
                      shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(hl, 0.3)
            rect(s, x + 0.12, iy - 0.04, 0.045, 0.34, fill=CORE)
        col = WHITE if i == active else RGBColor(0x9A,0xAE,0xB8)
        text(s, x + 0.3, iy - 0.05, w - 0.4, 0.34,
             [para(it, size=9.5, color=col, bold=(i == active))], anchor=MSO_ANCHOR.MIDDLE)
        iy += 0.44


def kpi_tile(s, x, y, w, h, value, label, glyph, delta=None, up=True):
    bx = rect(s, x, y, w, h, fill=CARD, line=SILVER, line_w=0.75,
              shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(bx, 0.09)
    icon_chip(s, x + 0.16, y + 0.16, glyph, size=0.4, gsize=11)
    text(s, x + 0.16, y + 0.66, w - 0.3, 0.4,
         [para(value, size=20, color=NAVY, bold=True)])
    text(s, x + 0.17, y + 1.08, w - 0.3, 0.3,
         [para(label, size=8.5, color=SLATE, line=1.0)])
    if delta:
        dc = RGBColor(0x1F,0x9D,0x55) if up else RGBColor(0xD1,0x5B,0x4E)
        g = "\uf062" if up else "\uf063"
        text(s, x + w - 0.95, y + 0.2, 0.85, 0.3,
             [para([{'text': g + " ", 'font': ICON, 'size': 8, 'color': dc, 'bold': True},
                    {'text': delta, 'size': 9, 'color': dc, 'bold': True}]) ],
             align=PP_ALIGN.RIGHT)


def mini_bars(s, x, y, w, h, values, labels=None, hi=None):
    n = len(values)
    gap = w * 0.05 / n
    bw = (w - gap * (n - 1)) / n
    mx = max(values)
    for i, v in enumerate(values):
        bh = h * (v / mx) * 0.9
        bx = x + i * (bw + gap)
        col = CORE if (hi is None or i != hi) else CORE_DK
        b = rect(s, bx, y + h - bh, bw, bh, fill=(CORE if hi != i else NAVY),
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(b, 0.06)
        if labels:
            text(s, bx - 0.1, y + h + 0.03, bw + 0.2, 0.2,
                 [para(labels[i], size=7, color=SLATE_LT, align=PP_ALIGN.CENTER)])


def list_rows(s, x, y, w, rows, rh=0.44):
    """rows: list of (title, meta, tag, tagcolor)"""
    cy = y
    for (title, meta, tag, tc) in rows:
        rect(s, x, cy, w, rh - 0.06, fill=WHITE, line=SILVER, line_w=0.6,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        rect(s, x, cy, 0.05, rh - 0.06, fill=tc)
        text(s, x + 0.2, cy + 0.04, w * 0.6, 0.2,
             [para(title, size=9, color=NAVY, bold=True)])
        text(s, x + 0.2, cy + 0.21, w * 0.6, 0.18,
             [para(meta, size=7.5, color=SLATE_LT)])
        tp = rect(s, x + w - 1.15, cy + 0.08, 0.95, rh - 0.22, fill=None, line=tc,
                  line_w=0.9, shape=MSO_SHAPE.ROUNDED_RECTANGLE); _round_radius(tp, 0.5)
        text(s, x + w - 1.15, cy + 0.055, 0.95, rh - 0.18,
             [para(tag, size=7.5, color=tc, bold=True, align=PP_ALIGN.CENTER)],
             anchor=MSO_ANCHOR.MIDDLE)
        cy += rh


def feature_list(s, items, x, y, w, row_h=0.62, chip=CORE, title_size=12.5, desc_size=10):
    """Compact vertical list: icon chip + bold title + one-line desc per row."""
    cy = y
    for glyph, title, desc in items:
        icon_chip(s, x, cy + (row_h - 0.46)/2, glyph, size=0.46, chip=chip, gsize=13)
        text(s, x + 0.66, cy + 0.02, w - 0.7, 0.28,
             [para(title, size=title_size, color=NAVY, bold=True)])
        text(s, x + 0.66, cy + 0.3, w - 0.7, 0.26,
             [para(desc, size=desc_size, color=SLATE, line=1.05)])
        cy += row_h


SHOT_RATIO = 1900 / 1193.0  # width/height of captured module screenshots

def shot(s, img, x, y, w, h=None, label=None):
    """Place a real screenshot as a floating, shadowed app window (no crop if h omitted)."""
    if h is None:
        h = w / SHOT_RATIO
    back = rect(s, x, y, w, h, fill=WHITE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True)
    _round_radius(back, 0.03)
    picture_cover(s, img, x + 0.02, y + 0.02, w - 0.04, h - 0.04)
    fr = rect(s, x, y, w, h, fill=None, line=SILVER, line_w=1.0, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    _round_radius(fr, 0.03)
    if label:
        tag = rect(s, x + 0.28, y + h - 0.5, 0.1 + len(label) * 0.085, 0.34, fill=NAVY,
                   shape=MSO_SHAPE.ROUNDED_RECTANGLE, shadow=True); _round_radius(tag, 0.5)
        text(s, x + 0.28, y + h - 0.52, 0.2 + len(label) * 0.085, 0.34,
             [para(label, size=9, color=WHITE, bold=True, align=PP_ALIGN.CENTER)], anchor=MSO_ANCHOR.MIDDLE)
    return h

def image_panel(s, img, x, y, w, h, overlay=0x0E2A36, alpha=55):
    """Cover-fit photo with a dark brand overlay (for title/divider)."""
    picture_cover(s, img, x, y, w, h)
    ov = rect(s, x, y, w, h, fill=RGBColor((overlay >> 16) & 255, (overlay >> 8) & 255, overlay & 255))
    _set_alpha(ov, alpha)
    return ov

def _set_alpha(shape, pct):
    sp = shape.fill.fore_color._xFill
    srgb = sp.find(qn('a:srgbClr'))
    if srgb is not None:
        a = srgb.makeelement(qn('a:alpha'), {'val': str(int(pct * 1000))})
        srgb.append(a)
