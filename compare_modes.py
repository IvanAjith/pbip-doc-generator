"""compare_modes.py -- put two runs side by side (for example offline vs AI).

  python run.py --compare-glossaries gl_offline gl_ai [FILE.xlsx]

Each folder is the glossary folder of one run (it holds my_definitions.csv). Two files come out, both for testing only:
  Offline_vs_AI.docx   a Word document: what each run says a KPI means, side by side, differences first
  Offline_vs_AI.xlsx   the same as a spreadsheet with a filter (needs openpyxl; a .csv is written without it)
"""
import csv
import re
from collections import Counter
from pathlib import Path

CSV_NAME = "my_definitions.csv"


def _kind(origin, text):
    o = (origin or "").lower()
    if not text:
        return "Needs your definition"
    if o.startswith("built-in") or o.startswith("shared"):
        return "Built-in glossary"
    if "formula" in o:
        return "Draft from the formula"
    if "kpi name" in o:
        return "Draft from the name"
    if o.startswith("web"):
        return "Web"
    if "ai" in o:
        return "AI draft"
    return "Your own" if not o else origin


def _from_documents(rows, out):
    """The glossary document is what people read. Fill in what the CSV leaves empty (status badges are described from the report's
    own colour rules, so the CSV has no sentence for them)."""
    try:
        from docx import Document
        doc = Document(str(next(Path(out).glob("*KPI_Glossary.docx"))))
    except Exception:
        return
    for t in doc.tables:
        if not t.rows or t.rows[0].cells[0].text.strip() != "KPI":
            continue
        for r in t.rows[1:]:
            c = [x.text.strip() for x in r.cells]
            term, text = c[0], re.sub(r"\s+", " ", c[1]).strip() if len(c) > 1 else ""
            if not text or text.startswith("\u26A0") or text == "\u2014":
                continue
            k = term.lower()
            if k in rows and not rows[k]["text"]:
                rows[k].update(text=text, kind="From the report (status badge)")
            elif k not in rows:
                rows[k] = {"term": term, "text": text, "kind": "From the report", "origin": "", "page": "", "calc": c[2] if len(c) > 2 else ""}


def read_run(folder, out=None):
    p = Path(folder)
    p = p / CSV_NAME if p.is_dir() else p
    if not p.exists():
        raise SystemExit(f"Cannot find {p}. Run the tool with --glossary {Path(folder)}\\glossary.json first.")
    rows = {}
    with open(p, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            term = (r.get("Term") or "").strip()
            if not term:
                continue
            mine = (r.get("Your definition (type here)") or "").strip()
            sugg = (r.get("Suggested definition") or "").strip()
            origin = (r.get("Where the suggestion came from") or "").strip()
            text = mine or sugg
            rows[term.lower()] = {"term": term, "text": text, "kind": "Your own" if mine else _kind(origin, text),
                                  "origin": origin, "page": r.get("Page", ""), "calc": r.get("Report formula (for reference)", "")}
    if out:
        _from_documents(rows, out)
    return rows


def compare(a_folder, b_folder, a_name="Offline", b_name="AI", a_out=None, b_out=None):
    a, b = read_run(a_folder, a_out), read_run(b_folder, b_out)
    out = []
    for k in sorted(set(a) | set(b)):
        x = a.get(k) or {"term": b[k]["term"], "text": "", "kind": "(not in this run)", "origin": "", "page": "", "calc": ""}
        y = b.get(k) or {"term": a[k]["term"], "text": "", "kind": "(not in this run)", "origin": "", "page": "", "calc": ""}
        same = x["text"].strip() == y["text"].strip()
        out.append({"term": x["term"], "page": x["page"] or y["page"], "formula": x["calc"] or y["calc"],
                    "a_kind": x["kind"], "a_text": x["text"], "b_kind": y["kind"], "b_text": y["text"], "same": same})
    return out, Counter(r["a_kind"] for r in out), Counter(r["b_kind"] for r in out)


def write(a_folder, b_folder, path="Offline_vs_AI.xlsx", a_name="Offline", b_name="AI", a_out=None, b_out=None):
    rows, ca, cb = compare(a_folder, b_folder, a_name, b_name, a_out, b_out)
    changed = [r for r in rows if not r["same"]]
    kinds = sorted(set(ca) | set(cb))
    summary = [("Terms compared", len(rows), ""), ("Same definition in both runs", len(rows) - len(changed), ""),
               ("Different definition", len(changed), "")]
    summary += [(f"Source: {k}", ca.get(k, 0), cb.get(k, 0)) for k in kinds]
    head = ["Term", "Page", f"{a_name} source", f"{a_name} definition", f"{b_name} source", f"{b_name} definition", "Same?"]

    def line(r):
        return [r["term"], r["page"], r["a_kind"], r["a_text"], r["b_kind"], r["b_text"], "yes" if r["same"] else "NO"]

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        path = str(Path(path).with_suffix(".csv"))
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(head); w.writerows(line(r) for r in rows)
        return path, len(rows), len(changed)
    wb = Workbook()
    ws = wb.active; ws.title = "Summary"
    ws.append(["", a_name, b_name]); ws.append(["Terms compared", len(rows)]); ws.append(["Same definition in both runs", len(rows) - len(changed)])
    ws.append(["Different definition", len(changed)]); ws.append([])
    ws.append(["Where the definition came from", a_name, b_name])
    for k in kinds:
        ws.append([k, ca.get(k, 0), cb.get(k, 0)])
    for c in ws[1] + ws[6]:
        c.font = Font(bold=True)
    ws.column_dimensions["A"].width = 36; ws.column_dimensions["B"].width = 14; ws.column_dimensions["C"].width = 14
    for title, data in (("Changed", changed), ("All terms", rows)):
        s = wb.create_sheet(title)
        s.append(head)
        for c in s[1]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F4E79")
        for r in data:
            s.append(line(r))
        for col, w in zip("ABCDEFG", (28, 18, 20, 60, 20, 60, 8)):
            s.column_dimensions[col].width = w
        for row in s.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        s.freeze_panes = "A2"; s.auto_filter.ref = s.dimensions
    wb.save(path)
    return path, len(rows), len(changed)


# ---------------------------------------------------------------------------------------------- Word document
def _shade(cell, hex_color):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_color)
    tc.append(shd)


def _cell(cell, text, bold=False, size=9, color=None, tag=None):
    from docx.shared import Pt, RGBColor
    cell.text = ""
    p = cell.paragraphs[0]
    r = p.add_run(text or "\u2014")
    r.bold = bold; r.font.size = Pt(size)
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    if tag:
        q = cell.add_paragraph()
        t = q.add_run(tag)
        t.italic = True; t.font.size = Pt(7.5); t.font.color.rgb = RGBColor(0x7F, 0x7F, 0x7F)


def write_docx(a_folder, b_folder, path="Offline_vs_AI.docx", a_name="Offline", b_name="AI", a_out=None, b_out=None):
    """Word document for testing: for every KPI what each run says it means. -> (path, n_terms, n_different)."""
    from datetime import date
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.shared import Inches, Pt
    rows, ca, cb = compare(a_folder, b_folder, a_name, b_name, a_out, b_out)
    changed = [r for r in rows if not r["same"]]
    agree = [r for r in rows if r["same"]]
    d = Document()
    sec = d.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(0.7))
    d.styles["Normal"].font.name = "Calibri"; d.styles["Normal"].font.size = Pt(10)
    d.add_heading(f"{a_name} vs {b_name}: what each run says a KPI means", 0)
    p = d.add_paragraph()
    p.add_run("For testing only. ").bold = True
    p.add_run(f"Created {date.today():%d/%m/%Y} from two runs of the tool: {a_name} (folder {Path(a_folder).name}) and "
              f"{b_name} (folder {Path(b_folder).name}). Each run had its own Needs_Your_Clarification.txt and its own answers.")
    d.add_paragraph(f"{len(rows)} KPIs compared: {len(agree)} read the same in both runs, {len(changed)} read differently. "
                    "Definitions from the built-in glossary or typed by you are the same in both runs by design; the "
                    "difference you are looking for is in the KPIs that had no built-in definition.")

    d.add_heading("Where each definition came from", 1)
    kinds = sorted(set(ca) | set(cb))
    t = d.add_table(rows=1, cols=3); t.style = "Table Grid"
    for c, h in zip(t.rows[0].cells, ("Source of the definition", a_name, b_name)):
        _cell(c, h, bold=True, color="FFFFFF"); _shade(c, "1F4E79")
    for k in kinds:
        cells = t.add_row().cells
        _cell(cells[0], k); _cell(cells[1], str(ca.get(k, 0))); _cell(cells[2], str(cb.get(k, 0)))

    def table(title, data, same):
        d.add_heading(title, 1)
        if not data:
            d.add_paragraph("None.")
            return
        heads = ("KPI", "Definition", "How it is calculated") if same else ("KPI", f"{a_name} says", f"{b_name} says", "How it is calculated")
        t = d.add_table(rows=1, cols=len(heads)); t.style = "Table Grid"
        for c, h in zip(t.rows[0].cells, heads):
            _cell(c, h, bold=True, color="FFFFFF"); _shade(c, "1F4E79")
        for r in data:
            cells = t.add_row().cells
            _cell(cells[0], r["term"], bold=True, tag=r["page"] or None)
            if same:
                _cell(cells[1], r["a_text"], tag="Source: " + r["a_kind"])
                _cell(cells[2], r["formula"], size=8, color="595959")
            else:
                for cell, kind, text in ((cells[1], r["a_kind"], r["a_text"]), (cells[2], r["b_kind"], r["b_text"])):
                    _cell(cell, text if text else "(no definition)", tag="Source: " + kind)
                    if not text:
                        _shade(cell, "FFE699")
                _cell(cells[3], r["formula"], size=8, color="595959")
        widths = (1.7, 3.6, 3.6, 2.4) if not same else (2.2, 5.6, 3.4)
        for row in t.rows:
            for c, w in zip(row.cells, widths):
                c.width = Inches(w)

    table(f"KPIs where {a_name} and {b_name} differ", changed, False)
    table("KPIs that read the same in both runs", agree, True)
    d.save(path)
    return path, len(rows), len(changed)


def write_all(a_folder, b_folder, base="Offline_vs_AI", a_name="Offline", b_name="AI", a_out=None, b_out=None):
    """The Word document plus the spreadsheet. -> ([paths], n_terms, n_different)."""
    base = str(Path(base).with_suffix(""))
    docx_path, n, changed = write_docx(a_folder, b_folder, base + ".docx", a_name, b_name, a_out, b_out)
    sheet_path, _, _ = write(a_folder, b_folder, base + ".xlsx", a_name, b_name, a_out, b_out)
    return [docx_path, sheet_path], n, changed
