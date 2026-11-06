"""
docx_helpers.py -- low-level Word building blocks (cover, INDEX table, headings,
tables, page-number fields). Content lives in manual_gen.py / glossary_doc_gen.py.
"""
import re
from pathlib import Path
from collections import Counter

from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


NAVY = RGBColor(0x1F, 0x38, 0x64)
BLUE = RGBColor(0x2E, 0x75, 0xB6)
GREY = RGBColor(0x5A, 0x6A, 0x85)
LGREY_HEX = "F2F2F2"
DASH_HEX = "9AA6B2"


# ---------------------------------------------------------------- low-level helpers

def shade_cell(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def set_cell_border(cell, color="BFBFBF", sz=4):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:color"), color)
        borders.append(el)
    tcPr.append(borders)


def add_toc_field(paragraph, levels="1-2"):
    run = paragraph.add_run()
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f'TOC \\o "{levels}" \\h \\z \\u'
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.text = "Right-click here and choose \u201cUpdate Field\u201d (or press F9) to generate the table of contents with page numbers."
    fld3 = OxmlElement("w:fldChar")
    fld3.set(qn("w:fldCharType"), "end")
    r = run._r
    r.append(fld1)
    r.append(instr)
    r.append(fld2)
    r.append(placeholder)
    r.append(fld3)


def set_update_fields_on_open(document):
    settings = document.settings.element
    el = OxmlElement("w:updateFields")
    el.set(qn("w:val"), "true")
    settings.append(el)


def add_page_number_field(paragraph, total=False):
    run = paragraph.add_run()
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " NUMPAGES " if total else " PAGE "
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "end")
    r = run._r
    r.append(fld1)
    r.append(instr)
    r.append(fld2)


def dashed_border_table(document, width_pct=100):
    """A single-cell table used as a dashed-border placeholder box."""
    t = document.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tcPr = t.rows[0].cells[0]._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "dashed")
        el.set(qn("w:sz"), "8")
        el.set(qn("w:color"), DASH_HEX)
        borders.append(el)
    tcPr.append(borders)
    t.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    return t


# ---------------------------------------------------------------- content helpers

def _log_heading(document, level, text):
    log = getattr(document, "_toc_log", None)
    if log is not None:
        log.append((level, text))


def h1(document, text, log=True):
    if log:
        _log_heading(document, 1, text)
    p = document.add_heading(level=1)
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    r.font.color.rgb = NAVY
    r.font.size = Pt(16)
    r.font.bold = True
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), "2E75B6")
    pbdr.append(bottom)
    pPr.append(pbdr)
    return p


def h2(document, text, log=True):
    if log:
        _log_heading(document, 2, text)
    p = document.add_heading(level=2)
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(text)
    r.font.color.rgb = BLUE
    r.font.size = Pt(13)
    r.font.bold = True
    return p


def para(document, text, italic=False, bold=False, size=11, color=None):
    p = document.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.italic = italic
    r.bold = bold
    if color:
        r.font.color.rgb = color
    return p


def bullets(document, items):
    for it in items:
        p = document.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(it)
        r.font.size = Pt(11)


def kv_table(document, rows, label_hex=LGREY_HEX):
    t = document.add_table(rows=0, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = True
    for label, value in rows:
        row = t.add_row()
        c0, c1 = row.cells
        c0.text = ""
        p0 = c0.paragraphs[0]
        r0 = p0.add_run(label)
        r0.bold = True
        r0.font.size = Pt(10)
        shade_cell(c0, label_hex)
        set_cell_border(c0)
        c1.text = ""
        p1 = c1.paragraphs[0]
        r1 = p1.add_run(value)
        r1.font.size = Pt(10)
        set_cell_border(c1)
    return t


def layout_table(t, fractions=None, total_inches=6.7, header=True):
    """Fixed column widths, rows that never split across pages, and a header
    row that repeats on every page."""
    ncols = len(t.columns)
    fractions = fractions or [1.0 / ncols] * ncols
    t.autofit = False
    tblPr = t._tbl.tblPr
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    tblPr.append(lay)
    for i, f in enumerate(fractions):
        w = Inches(total_inches * f)
        t.columns[i].width = w
        for cell in t.columns[i].cells:
            cell.width = w
    for ri, row in enumerate(t.rows):
        trPr = row._tr.get_or_add_trPr()
        cs = OxmlElement("w:cantSplit")
        trPr.append(cs)
        if header and ri == 0:
            th = OxmlElement("w:tblHeader")
            trPr.append(th)
    return t


NEEDS_MARK = "\u26A0 "


def data_table(document, headers, rows, col_widths=None, mono_cols=None, fills=None):
    """rows: list of list[str]. mono_cols: set of column indices to render
    in a monospace font (for DAX / identifiers)."""
    mono_cols = mono_cols or set()
    t = document.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0]
    for i, htext in enumerate(headers):
        cell = hdr.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        r = p.add_run(htext)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shade_cell(cell, "1F3864")
        set_cell_border(cell)
    for row in rows:
        tr = t.add_row()
        for i, val in enumerate(row):
            cell = tr.cells[i]
            cell.text = ""
            p = cell.paragraphs[0]
            r = p.add_run(str(val) if val not in (None, "") else "\u2014")
            r.font.size = Pt(9)
            if str(val).startswith(NEEDS_MARK):              # a definition still to be written: strong yellow
                shade_cell(cell, "FFE699")
                r.bold = True
            elif fills and (len(t.rows) - 2, i) in fills:    # e.g. a draft to be verified: pale yellow
                shade_cell(cell, fills[(len(t.rows) - 2, i)])
            if i in mono_cols:
                r.font.name = "Consolas"
                r.font.size = Pt(8)
            set_cell_border(cell)
    if col_widths is None:
        col_widths = {2: [0.34, 0.66], 3: [0.22, 0.39, 0.39], 4: [0.17, 0.33, 0.33, 0.17]}.get(len(headers))
    layout_table(t, col_widths)
    return t


def page_break(document):
    document.add_page_break()


# ---------------------------------------------------------------- section builders

def build_cover(document, project_name, subtitle="User Manual"):
    for _ in range(3):
        document.add_paragraph()
    box = dashed_border_table(document, 60)
    c = box.rows[0].cells[0]
    c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = c.paragraphs[0].add_run("[ COMPANY LOGO ]")
    r.bold = True
    r.font.size = Pt(10)
    r.font.color.rgb = GREY
    c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    document.add_paragraph()
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(project_name)
    r.font.size = Pt(32)
    r.font.bold = True
    r.font.color.rgb = NAVY

    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(subtitle)
    r.font.size = Pt(18)

    document.add_paragraph()
    p = document.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Prepared by")
    r.bold = True
    r.font.size = Pt(11)
    box2 = dashed_border_table(document, 40)
    c2 = box2.rows[0].cells[0]
    c2.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = c2.paragraphs[0].add_run("[ NAME / SIGNATURE ]")
    r2.italic = True
    r2.font.size = Pt(9)
    r2.font.color.rgb = GREY
    page_break(document)


def _split_heading_number(text):
    """'1. Data Sources -- ...' -> ('1', 'Data Sources -- ...');
    '6.3 Cards / Fields Available' -> ('6.3', 'Cards / Fields Available');
    'Introduction' -> ('', 'Introduction')."""
    m = re.match(r"^([\d.]+)\.?\s+(.*)$", text)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def build_index(document, toc_page_map=None, toc_entries=None):
    h1(document, "INDEX", log=False)
    if not toc_page_map:
        para(document, "This table of contents updates automatically. In Word: right-click anywhere below "
                        "and choose \u201cUpdate Field\u201d (or select all with Ctrl+A and press F9) to "
                        "populate page numbers.", italic=True, size=9, color=GREY)
        p = document.add_paragraph()
        add_toc_field(p, levels="1-2")
        page_break(document)
        return

    t = document.add_table(rows=1, cols=3)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0]
    for i, htext in enumerate(["S.No", "Section Title", "Page No."]):
        cell = hdr.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        r = p.add_run(htext)
        r.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shade_cell(cell, "1F3864")
        set_cell_border(cell)
    for level, text in (toc_entries or []):
        no, title = _split_heading_number(text)
        page_no = toc_page_map.get(text, "\u2014")
        row = t.add_row()
        c0, c1, c2 = row.cells
        c0.text = ""
        r0 = c0.paragraphs[0].add_run(no)
        r0.font.size = Pt(9)
        set_cell_border(c0)
        c1.text = ""
        c1.paragraphs[0].paragraph_format.left_indent = Pt(14) if level == 2 else Pt(0)
        r1 = c1.paragraphs[0].add_run(title)
        r1.font.size = Pt(9)
        r1.bold = (level == 1)
        set_cell_border(c1)
        c2.text = ""
        p2 = c2.paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r2 = p2.add_run(str(page_no))
        r2.font.size = Pt(9)
        set_cell_border(c2)
    layout_table(t, [0.14, 0.72, 0.14])
    page_break(document)


def build_doc_control(document, project_name, meta, title_suffix="User Manual"):
    h1(document, "Document Control", log=False)
    rows = [
        ("Title", f"{project_name} \u2013 {title_suffix}"),
        ("Author", meta.get("author") or "\u2014"),
        ("Owner", meta.get("owner") or "\u2014"),
        ("Project code", meta.get("project_code") or "\u2014"),
        ("Version", meta.get("version") or "\u2014"),
        ("Date Issued", meta.get("date_issued") or "\u2014"),
        ("Document ID", meta.get("document_id") or "\u2014"),
        ("Location", meta.get("location") or "\u2014"),
    ]
    kv_table(document, rows)
    page_break(document)


