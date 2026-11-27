"""Run:  python tests/test_kpi_document.py -- the company's KPI document: read from Excel / CSV / Word in different layouts, its definitions come
first in the glossary, and the run ends with KPI_Document_Check.txt (what came from the document, what is missing, where it may disagree with the formula)."""
import sys, re, csv, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import kpi_document as K
import openpyxl
from docx import Document

t = Path(tempfile.mkdtemp())

# ---- 1. a layout like the Timex KPI library: cover page, header on row 2 with a blank first row and column, calculation-only rows,
#         a hidden legend, a hidden list that is not KPIs
wb = openpyxl.Workbook()
cover = wb.active; cover.title = "Cover Page"
cover["C3"], cover["C4"] = "Acme", "KPI Library"
ws = wb.create_sheet("KPI Library")
ws.append([])
ws.append([None, "#", "Functional Area", "Attribute / KPI", "Key Performance Indicator (KPI)", "KPI Definition", "Calculation Methodology", "Unit of Measure (UoM)", "Time Measures"])
rows = [
    ["Primary", "KPI", "Stock On Hand", "Units of stock physically in the warehouses on the snapshot date", "Sum of units on hand", "Units", "MTD"],
    ["Primary", "KPI", "Inventory Turnover", None, "Count of distinct SKUs shipped in the month", "x", "YTD"],
    ["Secondary", "KPI", "Days of Supply", None, "Average daily shipments for the last 3 months", "Days", ""],
    ["Primary", "KPI", "# of Outlets\n(IDDs)", "Count of IDD outlets", "Sum of IDD outlets", None, None],
    ["Secondary", "KPI", "Primary Achievement or  Primary Billing", "Value of goods sold to partners", "=Sum of value", None, None],
    ["Not in report", "KPI", "Customer Complaints", "Complaints received from customers", "Count of complaints", None, None],
]
for i, r in enumerate(rows, 1):
    ws.append([None, i] + r)
leg = wb.create_sheet("Sheet1"); leg.sheet_state = "hidden"
for r in ([], [], [None, None, "Legend"], [None, None, "TP", "Time period (eg: MTD)"], [None, None, "MTD", "Month Till Date"], [None, None, "BILLING", "Primary"]):
    leg.append(r)
reg = wb.create_sheet("Region"); reg.sheet_state = "hidden"
reg.append([None, "Region", "State"]); reg.append([None, "North", "Punjab"]); reg.append([None, "North", "Haryana"])
xl = t / "Acme_KPI_Library.xlsx"; wb.save(xl)

res = K.read_document(xl)
assert not res.error and len(res.entries) == 6, (res.error, res.notes, res.skipped)
assert "header on row 2" in res.notes[0], res.notes
kd = K.KpiDocument([res])
e = kd.find("Stock On Hand")
assert e.definition == "Units of stock physically in the warehouses on the snapshot date." and e.calc == "Sum of units on hand" and e.area == "Primary"
assert kd.find("Number of Outlets (IDDs)").definition.startswith("Count of IDD outlets")            # '# of' and a line break in the name
assert kd.find("Primary Billing").definition.startswith("Value of goods")                           # 'A or B' gives two names
assert kd.find("Days of Supply").definition == "" and kd.find("Days of Supply").calc.startswith("Average daily")   # calculation only
assert kd.find("Something Else Entirely") is None
assert res.abbreviations == {"TP": "Time period", "MTD": "Month Till Date"}, res.abbreviations      # BILLING = Primary is a synonym, not an abbreviation
assert any("Cover Page" in s for s in res.skipped) and any("Region" in s and "hidden" in s for s in res.skipped)

# ---- 2. other layouts: no header, CSV with semicolons, Word table, Word headings, Word 'name: definition' lines
wb2 = openpyxl.Workbook(); w = wb2.active; w.title = "Notes"
for n, d in [("Stock On Hand", "The units that are in the warehouses at the end of the day."), ("Days of Supply", "How many days the stock lasts at the current sales speed."),
             ("Stockout Rate", "The share of products with no stock at all on the snapshot date."), ("Open Purchase Orders", "Units ordered from suppliers and not yet received.")]:
    w.append([n, d])
p = t / "no_header.xlsx"; wb2.save(p)
r = K.read_document(p); assert len(r.entries) == 4 and "guessed" in r.notes[0], (r.notes, r.skipped)

p = t / "kpis.csv"
p.write_text("Metric;Description;Formula\nStock On Hand;Units in the warehouses;SUM(qty)\nStockout Rate;Share of products with no stock;a / b\n", encoding="utf-8")
r = K.read_document(p); assert [x.name for x in r.entries] == ["Stock On Hand", "Stockout Rate"] and r.entries[1].calc == "a / b", r.notes

d = Document(); tb = d.add_table(rows=3, cols=3)
for i, row in enumerate([("KPI", "Meaning", "How it is calculated"), ("Lapse Rate", "Policies that ended because premium stopped", "Lapsed / in force"), ("Claims Paid", "Money paid out on claims", "Sum of payments")]):
    for j, c in enumerate(row):
        tb.cell(i, j).text = c
p = t / "table.docx"; d.save(p)
r = K.read_document(p); assert [x.name for x in r.entries] == ["Lapse Rate", "Claims Paid"] and r.entries[0].calc == "Lapsed / in force", r.notes

d = Document()
for n, x in [("Lapse Rate", "The share of policies that ended because premiums stopped being paid."), ("Claims Paid", "The money paid out to settle claims in the period."),
             ("Persistency", "The share of policies still in force after a given period.")]:
    d.add_heading(n, level=2); d.add_paragraph(x)
p = t / "headings.docx"; d.save(p)
r = K.read_document(p); assert [x.name for x in r.entries] == ["Lapse Rate", "Claims Paid", "Persistency"], r.notes

d = Document()
for l in ["Lapse Rate: The share of policies that ended because premiums stopped being paid.", "Claims Paid - The money paid out to settle claims in the period.",
          "Persistency: The share of policies still in force after a given period.", "This line is just a sentence about nothing in particular."]:
    d.add_paragraph(l)
p = t / "lines.docx"; d.save(p)
r = K.read_document(p); assert [x.name for x in r.entries] == ["Lapse Rate", "Claims Paid", "Persistency"], r.notes

bad = t / "broken.xlsx"; bad.write_bytes(b"not a workbook")
assert K.read_document(bad).error                                                  # a broken file never stops a run
nothing = t / "data.csv"; nothing.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
assert not K.read_document(nothing).entries

# the folders and files the tool itself writes are not mistaken for KPI documents
src = t / "src"; (src / "X.Report").mkdir(parents=True); (src / "X.Report" / "list.csv").write_text("a,b\n")
(src / "my_definitions.csv").write_text("a"); (src / "Needs_Your_Clarification.txt").write_text("a"); (src / "old.doc").write_text("a")
(src / "KPIs.xlsx").write_bytes(xl.read_bytes())
found, unreadable = K.find_documents(src)
assert [p.name for p in found] == ["KPIs.xlsx"] and [p.name for p in unreadable] == ["old.doc"], (found, unreadable)

# ---- 3. end to end on the made-up inventory project
subprocess.run([sys.executable, str(ROOT / "tests" / "make_synthetic_projects.py"), str(t / "syn")], check=True, capture_output=True)
proj = t / "syn" / "inventory"
(proj / "Acme_KPI_Library.xlsx").write_bytes(xl.read_bytes())
def run(source, out, gl, *extra):
    r = subprocess.run([sys.executable, str(ROOT / "run.py"), "--no-prompt", "--offline", "--skip-drafts", "--source", str(source), "--output", str(out),
                        "--glossary", str(gl), *extra], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout
out1 = run(proj, t / "out", t / "gl" / "glossary.json")
assert "KPI document Acme_KPI_Library.xlsx: 6 KPIs read" in out1 and "abbreviation(s) taken from the document's legend" in out1, out1[-2500:]
chk = (t / "out" / "KPI_Document_Check.txt").read_text(encoding="utf-8")
assert "definition(s) in the glossary come from the KPI document" in chk, chk
assert "Customer Complaints" in chk and "In the KPI document but not found in the report" in chk, chk
assert "PLEASE VERIFY" in chk and "Inventory Turnover" in chk and "speaks of a count" in chk, chk
g = "\n".join(c.text for tb in Document(str(next((t / "out").glob("*KPI_Glossary.docx")))).tables for r in tb.rows for c in r.cells)
assert "Units of stock physically in the warehouses on the snapshot date." in g, g[:1500]                  # the document's wording, not the built-in one
rows = list(csv.DictReader(open(t / "gl" / "my_definitions.csv", newline="", encoding="utf-8-sig")))
src_of = {r["Term"]: r["Where the suggestion came from"] for r in rows}
assert src_of["Stock On Hand"] == "KPI document: Acme_KPI_Library.xlsx (KPI Library)", src_of
assert src_of["Days of Supply"] != src_of["Stock On Hand"]                                               # calculation-only: not taken from the document
assert "TP = Time period" in (t / "gl" / "context.txt").read_text(encoding="utf-8")
print("KPI document run ok")

# scenario 2: no document -> no check file, nothing about a document
out2 = run(t / "syn" / "streaming", t / "out2", t / "gl2" / "glossary.json")
assert not (t / "out2" / "KPI_Document_Check.txt").exists() and "KPI document" not in out2
# --no-kpi-doc ignores a document that is there
out3 = run(proj, t / "out3", t / "gl3" / "glossary.json", "--no-kpi-doc")
assert not (t / "out3" / "KPI_Document_Check.txt").exists()
print("KPI document tests passed")
