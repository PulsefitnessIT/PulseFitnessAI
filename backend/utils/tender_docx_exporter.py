"""Submission-ready tender DOCX exporter.

Turns a tender's answered questions into a Word pack. Two modes:
  * build_templated_submission — inherit an uploaded client/house .docx template
    (header, footer, logo, styles) and inject a cover + contents + answers.
  * build_itt_plain — a clean, lightweight branded answers document for pasting
    into a portal / ITT that needs no template.
  * build_traceability — an evidence traceability matrix (claim -> source).

Design notes:
  * Header/footer/logo/section setup of an uploaded template are preserved
    verbatim; only find-&-replace tokens are applied to them.
  * The template's own paragraph styles are reused where present (Title,
    Heading 1/2/3, Normal) so answers adopt the house style.
  * Inline images use single line spacing to avoid the "exact" line-rule clip.
  * Contents uses a real Word TOC field (updates on open) so the pack stays
    fully editable.
"""
from __future__ import annotations
import copy
import re
import zipfile
import io
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
INK = RGBColor(0x22, 0x26, 0x2B)


# ───────────────────────── helpers ─────────────────────────

def _apply_tokens(text: str, tokens: list[dict]) -> str:
    for t in tokens or []:
        f = (t.get("find") or "").strip()
        if f:
            text = text.replace(f, t.get("replace") or "")
    return text


def _style_names(doc) -> set:
    names = set()
    for s in doc.styles:
        try:
            names.add(s.name)
        except Exception:
            pass
    return names


def _pick(names: set, *cands):
    for c in cands:
        if c in names:
            return c
    return None


def _merge_runs_and_patch(xml_bytes: bytes, tokens: list[dict]) -> bytes:
    from lxml import etree
    root = etree.fromstring(xml_bytes)
    for p in root.iter('{%s}p' % W):
        runs = [r for r in p if r.tag == '{%s}r' % W]
        i = 0
        while i < len(runs) - 1:
            a, b = runs[i], runs[i + 1]

            def simple(r):
                kids = list(r)
                ts = [k for k in kids if k.tag == '{%s}t' % W]
                other = [k for k in kids if k.tag not in ('{%s}t' % W, '{%s}rPr' % W)]
                return len(ts) == 1 and not other

            def rpr(r):
                e = r.find('{%s}rPr' % W)
                return etree.tostring(e) if e is not None else b''

            if simple(a) and simple(b) and rpr(a) == rpr(b):
                ta, tb = a.find('{%s}t' % W), b.find('{%s}t' % W)
                ta.text = (ta.text or '') + (tb.text or '')
                ta.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                p.remove(b)
                runs.pop(i + 1)
            else:
                i += 1
    s = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True).decode('utf-8')
    for t in tokens or []:
        f = (t.get("find") or "").strip()
        if f:
            s = s.replace(f, t.get("replace") or "")
    return s.encode('utf-8')


def _patch_headers_footers(docx_bytes: bytes, tokens: list[dict]) -> bytes:
    if not tokens:
        return docx_bytes
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx_bytes), 'r') as zin, \
            zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if re.match(r'word/(header|footer)\d+\.xml', item):
                data = _merge_runs_and_patch(data, tokens)
            zout.writestr(item, data)
    return out.getvalue()


def _set_update_fields(doc):
    """Force Word to refresh the TOC page numbers when the file is opened."""
    settings = doc.settings.element
    if settings.find(qn('w:updateFields')) is None:
        el = OxmlElement('w:updateFields')
        el.set(qn('w:val'), 'true')
        settings.append(el)


def _add_toc(doc, levels="1-3"):
    p = doc.add_paragraph()
    run = p.add_run()
    fld_begin = OxmlElement('w:fldChar'); fld_begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText'); instr.set(qn('xml:space'), 'preserve')
    instr.text = f' TOC \\o "{levels}" \\h \\z \\u '
    fld_sep = OxmlElement('w:fldChar'); fld_sep.set(qn('w:fldCharType'), 'separate')
    t = OxmlElement('w:t'); t.text = "Right-click and choose 'Update Field' to build the contents."
    fld_end = OxmlElement('w:fldChar'); fld_end.set(qn('w:fldCharType'), 'end')
    for el in (fld_begin, instr, fld_sep, t, fld_end):
        run._r.append(el)


def _no_number(p):
    """Strip any inherited list/heading auto-numbering from a paragraph."""
    pPr = p._p.get_or_add_pPr()
    numPr = OxmlElement('w:numPr')
    il = OxmlElement('w:ilvl'); il.set(qn('w:val'), '0')
    ni = OxmlElement('w:numId'); ni.set(qn('w:val'), '0')
    numPr.append(il); numPr.append(ni); pPr.append(numPr)


def _page_break(doc):
    p = doc.add_paragraph()
    r = p.add_run()
    br = OxmlElement('w:br'); br.set(qn('w:type'), 'page')
    r._r.append(br)


def _answered(questions):
    ok = []
    for q in questions:
        ans = (q.get("response") or q.get("ai_draft") or "").strip()
        if ans:
            ok.append((q, ans))
    ok.sort(key=lambda x: x[0].get("order", 0))
    return ok


def _q_heading(q, idx):
    num = q.get("number") or q.get("ref") or f"{idx}"
    title = (q.get("title") or q.get("category") or q.get("text") or "").strip()
    if len(title) > 90:
        title = title[:90].rsplit(" ", 1)[0] + "…"
    return f"{num}. {title}" if title else f"Question {num}"


def _add_body_text(doc, text, body_style, tokens):
    for para in re.split(r'\n{2,}', _apply_tokens(text, tokens)):
        para = para.strip()
        if not para:
            continue
        bullet = para.lstrip().startswith(("- ", "• ", "* "))
        for line in para.split("\n"):
            line = line.strip()
            if not line:
                continue
            is_b = line.startswith(("- ", "• ", "* "))
            clean = re.sub(r'^[-•*]\s+', '', line)
            if is_b:
                try:
                    p = doc.add_paragraph(clean, style='List Bullet')
                except Exception:
                    p = doc.add_paragraph("• " + clean)
            else:
                p = doc.add_paragraph(style=body_style) if body_style else doc.add_paragraph()
                r = p.add_run(clean)
                if not body_style:
                    r.font.name = 'Arial'; r.font.size = Pt(11); r.font.color.rgb = INK


# ───────────────────────── templated pack ─────────────────────────

def build_templated_submission(template_bytes: bytes, tender: dict, questions: list,
                               tokens: list[dict] | None = None,
                               logo_bytes: bytes | None = None) -> bytes:
    tokens = tokens or []
    doc = Document(io.BytesIO(template_bytes))
    body = doc.element.body
    sectPr = body.find(qn('w:sectPr'))
    for ch in list(body):
        if ch is not sectPr:
            body.remove(ch)

    names = _style_names(doc)
    title_style = _pick(names, 'Title', 'Heading 1')
    h_cover = _pick(names, 'Heading 1', 'Heading 2', 'Title')
    h_section = _pick(names, 'Heading 2', 'Heading 3', 'Heading 1')
    body_style = _pick(names, 'Normal')

    def centered(add):
        add.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return add

    # ---- cover ----
    if logo_bytes:
        try:
            doc.add_picture(io.BytesIO(logo_bytes), width=Cm(6))
            lp = doc.paragraphs[-1]
            lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            lp.paragraph_format.line_spacing = 1.0
            lp.paragraph_format.space_after = Pt(18)
        except Exception:
            pass

    tp = doc.add_paragraph(style=title_style) if title_style else doc.add_paragraph()
    _no_number(tp)
    tr = tp.add_run(_apply_tokens(tender.get("title") or "Tender Response", tokens))
    if not title_style:
        tr.font.name = 'Arial'; tr.bold = True; tr.font.size = Pt(24); tr.font.color.rgb = INK
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta = []
    if tender.get("issuer"):
        meta.append(f"Issued by: {tender['issuer']}")
    if tender.get("reference") or tender.get("ref"):
        meta.append(f"Reference: {tender.get('reference') or tender.get('ref')}")
    if tender.get("client") or tender.get("customer"):
        meta.append(f"Prepared for: {tender.get('client') or tender.get('customer')}")
    for m in meta:
        mp = doc.add_paragraph(); mp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = mp.add_run(_apply_tokens(m, tokens)); r.font.name = 'Arial'; r.font.size = Pt(12); r.font.color.rgb = INK

    _page_break(doc)

    # ---- contents ----
    cp = doc.add_paragraph(style=h_cover) if h_cover else doc.add_paragraph()
    _no_number(cp)
    cr = cp.add_run("Contents")
    if not h_cover:
        cr.font.name = 'Arial'; cr.bold = True; cr.font.size = Pt(18); cr.font.color.rgb = INK
    _add_toc(doc, "1-3")
    _page_break(doc)

    # ---- answers ----
    answered = _answered(questions)
    for idx, (q, ans) in enumerate(answered, start=1):
        hp = doc.add_paragraph(style=h_section) if h_section else doc.add_paragraph()
        _no_number(hp)
        hr = hp.add_run(_apply_tokens(_q_heading(q, idx), tokens))
        if not h_section:
            hr.font.name = 'Arial'; hr.bold = True; hr.font.size = Pt(14); hr.font.color.rgb = INK
        _add_body_text(doc, ans, body_style, tokens)

    body.remove(sectPr)
    body.append(sectPr)
    _set_update_fields(doc)

    buf = io.BytesIO()
    doc.save(buf)
    return _patch_headers_footers(buf.getvalue(), tokens)


# ───────────────────────── plain ITT-direct ─────────────────────────

def _plain_doc(brand: dict | None):
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Cm(2.2); sec.bottom_margin = Cm(2.2)
    sec.left_margin = Cm(2.2); sec.right_margin = Cm(2.2)
    st = doc.styles['Normal']; st.font.name = 'Arial'; st.font.size = Pt(11)
    return doc


def build_itt_plain(tender: dict, questions: list, brand: dict | None = None,
                    tokens: list[dict] | None = None) -> bytes:
    tokens = tokens or []
    doc = _plain_doc(brand)
    accent = RGBColor(0x2F, 0x54, 0x96)
    tp = doc.add_paragraph()
    tr = tp.add_run(_apply_tokens(tender.get("title") or "Tender Response", tokens))
    tr.font.name = 'Arial'; tr.bold = True; tr.font.size = Pt(18); tr.font.color.rgb = accent
    if tender.get("issuer") or tender.get("reference"):
        sp = doc.add_paragraph()
        r = sp.add_run(_apply_tokens(" · ".join(
            [x for x in [tender.get("issuer"), tender.get("reference") or tender.get("ref")] if x]), tokens))
        r.font.name = 'Arial'; r.font.size = Pt(10); r.font.color.rgb = RGBColor(0x55, 0x5B, 0x66)
    doc.add_paragraph()

    for idx, (q, ans) in enumerate(_answered(questions), start=1):
        hp = doc.add_paragraph()
        hr = hp.add_run(_apply_tokens(_q_heading(q, idx), tokens))
        hr.font.name = 'Arial'; hr.bold = True; hr.font.size = Pt(13); hr.font.color.rgb = accent
        hp.paragraph_format.space_before = Pt(10)
        if q.get("weighting"):
            wp = doc.add_paragraph()
            wr = wp.add_run(f"Weighting: {q.get('weighting')}%")
            wr.font.name = 'Arial'; wr.italic = True; wr.font.size = Pt(9); wr.font.color.rgb = RGBColor(0x55, 0x5B, 0x66)
        _add_body_text(doc, ans, 'Normal', tokens)
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()


# ───────────────────────── traceability matrix ─────────────────────────

def build_traceability(tender: dict, questions: list, brand: dict | None = None,
                       tokens: list[dict] | None = None) -> bytes:
    tokens = tokens or []
    doc = _plain_doc(brand)
    accent = RGBColor(0x2F, 0x54, 0x96)
    tp = doc.add_paragraph()
    tr = tp.add_run("Evidence Traceability Matrix")
    tr.font.name = 'Arial'; tr.bold = True; tr.font.size = Pt(17); tr.font.color.rgb = accent
    sp = doc.add_paragraph()
    sr = sp.add_run(_apply_tokens(tender.get("title") or "", tokens) + " — maps each answer to its supporting knowledge-base sources.")
    sr.font.name = 'Arial'; sr.font.size = Pt(10); sr.font.color.rgb = RGBColor(0x55, 0x5B, 0x66)
    doc.add_paragraph()

    table = doc.add_table(rows=1, cols=3); table.style = 'Table Grid'; table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, h in enumerate(["Question", "Response summary", "Supporting sources"]):
        c = table.rows[0].cells[j]
        tcPr = c._tc.get_or_add_tcPr(); shd = OxmlElement('w:shd'); shd.set(qn('w:val'), 'clear'); shd.set(qn('w:fill'), '2F5496'); tcPr.append(shd)
        c.text = ''; r = c.paragraphs[0].add_run(h); r.font.name = 'Arial'; r.bold = True; r.font.size = Pt(9.5); r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for idx, (q, ans) in enumerate(_answered(questions), start=1):
        cells = table.add_row().cells
        cells[0].text = _apply_tokens(_q_heading(q, idx), tokens)
        summary = re.sub(r'\s+', ' ', ans).strip()
        cells[1].text = (summary[:240] + "…") if len(summary) > 240 else summary
        cites = q.get("ai_citations") or []
        src = "; ".join([f"[{c.get('index')}] {c.get('title', '')}" for c in cites]) if cites else "Author knowledge / to be cited"
        cells[2].text = src
        for cc in cells:
            for pp in cc.paragraphs:
                for rr in pp.runs:
                    rr.font.name = 'Arial'; rr.font.size = Pt(9)
    for r in table.rows:
        r.cells[0].width = Cm(4.6); r.cells[1].width = Cm(8.0); r.cells[2].width = Cm(4.6)
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()


_TOKEN_RE = re.compile(r"\{\{\s*[A-Za-z0-9_ .\-]+\s*\}\}")


def detect_template_tokens(template_bytes: bytes) -> list[str]:
    """Scan the whole .docx (body + headers + footers) for {{PLACEHOLDER}}
    tokens so the library can pre-seed find/replace rows for the user."""
    found: list[str] = []
    seen: set = set()
    try:
        with zipfile.ZipFile(io.BytesIO(template_bytes)) as z:
            for name in z.namelist():
                if not (name.endswith(".xml") and (
                    name.startswith("word/document")
                    or "header" in name or "footer" in name)):
                    continue
                try:
                    text = z.read(name).decode("utf-8", "ignore")
                except Exception:
                    continue
                # strip XML tags so tokens split across runs still match
                stripped = re.sub(r"<[^>]+>", "", text)
                for m in _TOKEN_RE.findall(stripped):
                    key = re.sub(r"\s+", " ", m).strip()
                    if key not in seen:
                        seen.add(key)
                        found.append(key)
    except Exception:
        pass
    return found


def detect_template_styles(template_bytes: bytes) -> dict:
    try:
        doc = Document(io.BytesIO(template_bytes))
        names = _style_names(doc)
        headers = []
        for i in range(1, 4):
            try:
                sec = doc.sections[0]
                for p in sec.header.paragraphs:
                    if p.text.strip():
                        headers.append(p.text.strip())
            except Exception:
                pass
            break
        return {
            "styles": sorted([n for n in names if n.startswith(('Heading', 'Title', 'Normal'))]),
            "header_text": " | ".join(headers[:3]),
            "has_title": 'Title' in names,
            "detected_tokens": detect_template_tokens(template_bytes),
        }
    except Exception as e:
        return {"styles": [], "header_text": "", "error": str(e)}
