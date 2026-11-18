"""Run:  python tests/test_compare_modes.py   -- two runs side by side (offline vs AI)."""
import sys, csv, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import compare_modes as CM
H = ["Term", "Your definition (type here)", "Suggested definition", "Where the suggestion came from", "Page", "Report formula (for reference)"]
def make(folder, rows):
    folder.mkdir()
    with open(folder / CM.CSV_NAME, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(H); w.writerows(rows)
t = Path(tempfile.mkdtemp())
make(t / "a", [["NPS", "", "Built-in text.", "Built-in glossary", "P1", ""], ["Hold", "", "From formula.", "Draft built from the formula", "P1", "x"],
               ["Only A", "", "Text.", "Built-in glossary", "P2", ""]])
make(t / "b", [["NPS", "", "Built-in text.", "Built-in glossary", "P1", ""], ["Hold", "", "An AI sentence.", "AI draft (gemini)", "P1", "x"],
               ["Typed", "My words.", "", "", "P2", ""]])
rows, ca, cb = CM.compare(t / "a", t / "b")
by = {r["term"]: r for r in rows}
assert len(rows) == 4 and by["NPS"]["same"] and not by["Hold"]["same"]
assert by["Hold"]["a_kind"] == "Draft from the formula" and by["Hold"]["b_kind"] == "AI draft"
assert by["Only A"]["b_kind"] == "(not in this run)" and by["Typed"]["b_kind"] == "Your own"
path, n, changed = CM.write(t / "a", t / "b", str(t / "x.xlsx"))
assert n == 4 and changed == 3 and Path(path).exists()
paths, n2, ch2 = CM.write_all(t / "a", t / "b", str(t / "both"))
assert n2 == 4 and ch2 == 3 and all(Path(x).exists() for x in paths) and paths[0].endswith(".docx")
from docx import Document
doc = Document(paths[0])
text = "\n".join(c.text for tb in doc.tables for r in tb.rows for c in r.cells)
assert "An AI sentence." in text and "From formula." in text and "Source: AI draft" in text and "Source: Draft from the formula" in text
assert "Hold" in text and "Only A" in text and "(no definition)" in text
assert any("differ" in p.text for p in doc.paragraphs) or any("differ" in h.text for h in doc.paragraphs)
# the glossary document fills what the CSV leaves empty (status badges), and what people read is what is compared
from docx import Document as D
for name in ("oa", "ob"):
    (t / name).mkdir()
    dd = D(); tb = dd.add_table(rows=2, cols=3)
    for c, h in zip(tb.rows[0].cells, ("KPI", "What it means", "How it is calculated")):
        c.text = h
    tb.rows[1].cells[0].text = "Revenue Status"; tb.rows[1].cells[1].text = "A status badge. Colour coding: red when EBIT < 0."; tb.rows[1].cells[2].text = "-"
    dd.save(str(t / name / "x_KPI_Glossary.docx"))
make(t / "c", [["Revenue Status", "", "", "", "P1", ""]]); make(t / "d", [["Revenue Status", "", "", "", "P1", ""]])
r2, _, _ = CM.compare(t / "c", t / "d")
assert r2[0]["a_text"] == "" and r2[0]["same"]
r3, _, _ = CM.compare(t / "c", t / "d", a_out=t / "oa", b_out=t / "ob")
assert r3[0]["a_text"].startswith("A status badge") and r3[0]["a_kind"] == "From the report (status badge)" and r3[0]["same"]
# "SET = SET" explains nothing: no note and no context line
from checks import Context
cx = Context(t / "ctx.txt"); cx.set_meanings({"SET": "SET", "CB": "comeback"})
assert "SET" not in cx.abbr and cx.abbr["CB"] == "comeback" and cx.note_for(["AVG SET"]) == ""
(t / "ctx2.txt").write_text("SET = SET\nDL = direct labour\n", encoding="utf-8")
assert Context(t / "ctx2.txt").abbr == {"DL": "direct labour"}
print("compare modes tests passed")
